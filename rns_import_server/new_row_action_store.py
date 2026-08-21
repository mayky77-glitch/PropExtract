"""Private durable authority for a requested new workbook row.

This module deliberately keeps the raw capability at the boundary.  SQLite
stores only its action-bound digest, so a database, log, or exception cannot
be used as a bearer token source.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from pathlib import Path
import sqlite3

from rns_import_server.registry_storage import RegistryConflictError, RegistryError, RegistryStorage, utc_now


_CAPABILITY_DOMAIN = b"PropExtract/new-row-capability/v1\x00"


class NewRowActionError(RegistryError):
    """Stable, payload-free failure at the pending-action authority boundary."""


def capability_digest(*, action_id: str, capability: str) -> str:
    if type(action_id) is not str or not action_id or type(capability) is not str or not capability:
        raise NewRowActionError("new_row_action_authority_invalid")
    return hashlib.sha256(_CAPABILITY_DOMAIN + action_id.encode("utf-8") + b"\x00" + capability.encode("utf-8")).hexdigest()


def _canonical_target_path(value: object) -> str:
    if type(value) is not str or not value:
        raise NewRowActionError("new_row_action_target_invalid")
    path = Path(value)
    # resolve(strict=True) would follow a final symlink before we could reject
    # it, so inspect the supplied object first and only retain its canonical
    # absolute path after every link component was rejected.
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise NewRowActionError("new_row_action_target_invalid")
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        if current.is_symlink():
            raise NewRowActionError("new_row_action_target_invalid")
    return str(path.resolve(strict=True))


@dataclass(frozen=True)
class NewRowPendingAction:
    action_id: str
    job_id: str
    construction_id: str
    workbook_contract_id: str
    target_identity: str
    target_path: str
    state: str


class NewRowActionStore:
    """Concrete ``NewRowPendingPort`` backed by one private SQLite table."""

    def __init__(self, storage: RegistryStorage):
        self.storage = storage

    def register(
        self,
        *,
        action_id: str,
        job_id: str,
        construction_id: str,
        workbook_contract_id: str,
        target_identity: str,
        target_path: str,
        capability: str,
    ) -> NewRowPendingAction:
        """Insert one immutable pending authority or verify its exact replay."""
        stable = {
            "action_id": action_id, "job_id": job_id, "construction_id": construction_id,
            "workbook_contract_id": workbook_contract_id, "target_identity": target_identity,
        }
        if any(type(value) is not str or not value.strip() for value in stable.values()):
            raise NewRowActionError("new_row_action_authority_invalid")
        canonical_path = _canonical_target_path(target_path)
        digest = capability_digest(action_id=action_id, capability=capability)
        try:
            with self.storage.transaction() as connection:
                if connection.execute("SELECT 1 FROM constructions WHERE id=?", (construction_id,)).fetchone() is None:
                    raise NewRowActionError("new_row_action_authority_invalid")
                existing = connection.execute(
                    "SELECT * FROM new_row_pending_actions WHERE action_id=?", (action_id,)
                ).fetchone()
                if existing is None:
                    now = utc_now()
                    connection.execute(
                        "INSERT INTO new_row_pending_actions(action_id,job_id,construction_id,workbook_contract_id,target_identity,target_path,capability_digest,state,created_at,updated_at) "
                        "VALUES(?,?,?,?,?,?,?,'pending',?,?)",
                        (action_id, job_id, construction_id, workbook_contract_id, target_identity, canonical_path, digest, now, now),
                    )
                    row = connection.execute("SELECT * FROM new_row_pending_actions WHERE action_id=?", (action_id,)).fetchone()
                else:
                    expected = (job_id, construction_id, workbook_contract_id, target_identity, canonical_path)
                    actual = tuple(existing[name] for name in ("job_id", "construction_id", "workbook_contract_id", "target_identity", "target_path"))
                    if actual != expected or not hmac.compare_digest(str(existing["capability_digest"]), digest):
                        raise RegistryConflictError("new_row_action_conflict")
                    row = existing
                assert row is not None
                return self._public(row)
        except sqlite3.Error as error:
            raise NewRowActionError("new_row_action_storage_failed") from error

    # Explicit name keeps hosts from treating a registration as a generic
    # ``pending`` assignment.
    register_pending_action = register

    def get(self, action_id: str) -> NewRowPendingAction | None:
        row = self.storage.connection.execute("SELECT * FROM new_row_pending_actions WHERE action_id=?", (action_id,)).fetchone()
        return self._public(row) if row is not None else None

    @staticmethod
    def _public(row: sqlite3.Row) -> NewRowPendingAction:
        return NewRowPendingAction(
            action_id=str(row["action_id"]), job_id=str(row["job_id"]), construction_id=str(row["construction_id"]),
            workbook_contract_id=str(row["workbook_contract_id"]), target_identity=str(row["target_identity"]),
            target_path=str(row["target_path"]), state=str(row["state"]),
        )

    def _authorized(self, connection: sqlite3.Connection, action_id: str, capability: str) -> sqlite3.Row | None:
        if type(action_id) is not str or not action_id or type(capability) is not str or not capability:
            return None
        row = connection.execute("SELECT * FROM new_row_pending_actions WHERE action_id=?", (action_id,)).fetchone()
        if row is None:
            return None
        expected = capability_digest(action_id=action_id, capability=capability)
        if not hmac.compare_digest(str(row["capability_digest"]), expected):
            return None
        return row

    def reserve_pending_to_publishing(self, action_id: str, *, job_authorization: str) -> bool:
        try:
            with self.storage.transaction() as connection:
                row = self._authorized(connection, action_id, job_authorization)
                if row is None or row["state"] != "pending":
                    return False
                now = utc_now()
                return connection.execute(
                    "UPDATE new_row_pending_actions SET state='publishing', updated_at=? WHERE action_id=? AND state='pending'",
                    (now, action_id),
                ).rowcount == 1
        except sqlite3.Error as error:
            raise NewRowActionError("new_row_action_storage_failed") from error

    def reopen_after_pre_hash_failure(self, action_id: str, *, job_authorization: str) -> bool:
        """Reopen only a proven pre-hash failure with no journal authority."""
        try:
            with self.storage.transaction() as connection:
                row = self._authorized(connection, action_id, job_authorization)
                if row is None or row["state"] != "publishing":
                    return False
                journal = connection.execute(
                    "SELECT pre_hash, post_hash FROM workbook_operation_journal WHERE operation_id=?", (action_id,)
                ).fetchone()
                # An absent journal proves the publisher never acquired its
                # durable publication authority. Once a journal exists its
                # lifecycle (including any pre-hash classification) is the
                # only authority; this port must not guess a safe reopen.
                if journal is not None:
                    return False
                now = utc_now()
                return connection.execute(
                    "UPDATE new_row_pending_actions SET state='pending', updated_at=? WHERE action_id=? AND state='publishing'",
                    (now, action_id),
                ).rowcount == 1
        except sqlite3.Error as error:
            raise NewRowActionError("new_row_action_storage_failed") from error
