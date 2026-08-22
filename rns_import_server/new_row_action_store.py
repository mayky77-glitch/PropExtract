"""Private durable authority for a requested new workbook row.

This module deliberately keeps the raw capability at the boundary.  SQLite
stores only its action-bound digest, so a database, log, or exception cannot
be used as a bearer token source.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
from pathlib import Path
import re
import sqlite3

from rns_import_server.registry_storage import RegistryConflictError, RegistryError, RegistryStorage, utc_now


_CAPABILITY_DOMAIN = b"PropExtract/new-row-capability/v1\x00"
_LIFECYCLE_DOMAIN = b"PropExtract/new-row-lifecycle-receipt/v1\x00"
_DIGEST_RE = re.compile(r"[0-9a-f]{64}", flags=re.ASCII)


class NewRowActionError(RegistryError):
    """Stable, payload-free failure at the pending-action authority boundary."""


def _is_nonempty_ascii(value: object) -> bool:
    return type(value) is str and bool(value) and value.isascii()


def _is_capability_digest(value: object) -> bool:
    return type(value) is str and bool(_DIGEST_RE.fullmatch(value))


def capability_digest(*, action_id: str, capability: str) -> str:
    if type(action_id) is not str or not action_id or not _is_nonempty_ascii(capability):
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


@dataclass(frozen=True)
class NewRowLifecycleReceipt:
    action_id: str
    terminal_state: str
    operation_id: str | None
    observed_row: int | None
    expected_pre_hash: str | None
    observed_workbook_hash: str
    digest: str
    created_at: str


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
        predecessor_action_id: str | None = None,
    ) -> NewRowPendingAction:
        """Insert one immutable pending authority or verify its exact replay."""
        stable = {
            "action_id": action_id, "job_id": job_id, "construction_id": construction_id,
            "workbook_contract_id": workbook_contract_id, "target_identity": target_identity,
        }
        if any(type(value) is not str or not value.strip() for value in stable.values()):
            raise NewRowActionError("new_row_action_authority_invalid")
        canonical_path = _canonical_target_path(target_path)
        if predecessor_action_id is not None and (type(predecessor_action_id) is not str or not predecessor_action_id or predecessor_action_id == action_id):
            raise NewRowActionError("new_row_action_abandonment_invalid")
        digest = capability_digest(action_id=action_id, capability=capability)
        try:
            with self.storage.transaction() as connection:
                if connection.execute("SELECT 1 FROM constructions WHERE id=?", (construction_id,)).fetchone() is None:
                    raise NewRowActionError("new_row_action_authority_invalid")
                if predecessor_action_id is not None:
                    predecessor = connection.execute(
                        "SELECT action_id, capability_digest FROM new_row_pending_actions WHERE action_id=?", (predecessor_action_id,)
                    ).fetchone()
                    receipt = connection.execute(
                        "SELECT terminal_state FROM new_row_action_lifecycle_receipts WHERE action_id=?", (predecessor_action_id,)
                    ).fetchone()
                    if predecessor is None or receipt is None or receipt["terminal_state"] != "abandoned":
                        raise NewRowActionError("new_row_action_abandonment_invalid")
                    if _is_capability_digest(predecessor["capability_digest"]) and hmac.compare_digest(
                        predecessor["capability_digest"], capability_digest(action_id=predecessor_action_id, capability=capability)
                    ):
                        raise NewRowActionError("new_row_action_capability_reused")
                existing = connection.execute(
                    "SELECT * FROM new_row_pending_actions WHERE action_id=?", (action_id,)
                ).fetchone()
                if existing is None:
                    now = utc_now()
                    connection.execute(
                        "INSERT INTO new_row_pending_actions(action_id,job_id,construction_id,workbook_contract_id,target_identity,target_path,capability_digest,predecessor_action_id,state,created_at,updated_at) "
                        "VALUES(?,?,?,?,?,?,?,?,'pending',?,?)",
                        (action_id, job_id, construction_id, workbook_contract_id, target_identity, canonical_path, digest, predecessor_action_id, now, now),
                    )
                    row = connection.execute("SELECT * FROM new_row_pending_actions WHERE action_id=?", (action_id,)).fetchone()
                else:
                    expected = (job_id, construction_id, workbook_contract_id, target_identity, canonical_path, predecessor_action_id)
                    actual = tuple(existing[name] for name in ("job_id", "construction_id", "workbook_contract_id", "target_identity", "target_path", "predecessor_action_id"))
                    if (actual != expected or not _is_capability_digest(existing["capability_digest"])
                            or not hmac.compare_digest(existing["capability_digest"], digest)):
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
        row = self.storage.connection.execute(
            "SELECT actions.*, COALESCE(receipts.terminal_state, actions.state) AS effective_state "
            "FROM new_row_pending_actions AS actions LEFT JOIN new_row_action_lifecycle_receipts AS receipts "
            "ON receipts.action_id=actions.action_id WHERE actions.action_id=?", (action_id,)
        ).fetchone()
        return self._public(row) if row is not None else None

    def receipt(self, action_id: str) -> NewRowLifecycleReceipt | None:
        row = self.storage.connection.execute("SELECT * FROM new_row_action_lifecycle_receipts WHERE action_id=?", (action_id,)).fetchone()
        return self._receipt(row) if row is not None else None

    @staticmethod
    def _receipt(row: sqlite3.Row) -> NewRowLifecycleReceipt:
        return NewRowLifecycleReceipt(
            action_id=str(row["action_id"]), terminal_state=str(row["terminal_state"]),
            operation_id=row["operation_id"], observed_row=row["observed_row"], expected_pre_hash=row["expected_pre_hash"],
            observed_workbook_hash=str(row["observed_workbook_hash"]), digest=str(row["digest"]), created_at=str(row["created_at"]),
        )

    @staticmethod
    def _hash(value: object) -> bool:
        return type(value) is str and bool(_DIGEST_RE.fullmatch(value))

    @staticmethod
    def _receipt_digest(values: dict[str, object]) -> str:
        payload = json.dumps(values, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii")
        return hashlib.sha256(_LIFECYCLE_DOMAIN + payload).hexdigest()

    def _insert_receipt(self, connection: sqlite3.Connection, values: dict[str, object]) -> NewRowLifecycleReceipt:
        digest = self._receipt_digest(values)
        connection.execute(
            "INSERT INTO new_row_action_lifecycle_receipts(action_id,receipt_version,terminal_state,operation_id,observed_row,expected_pre_hash,observed_workbook_hash,digest,created_at) VALUES(?,1,?,?,?,?,?,?,?)",
            (values["action_id"], values["terminal_state"], values["operation_id"], values["observed_row"], values["expected_pre_hash"], values["observed_workbook_hash"], digest, values["created_at"]),
        )
        row = connection.execute("SELECT * FROM new_row_action_lifecycle_receipts WHERE action_id=?", (values["action_id"],)).fetchone()
        assert row is not None
        return self._receipt(row)

    def close_existing(self, action_id: str, *, job_authorization: str, terminal_state: str, observed_row: int,
                       observed_workbook_hash: str) -> NewRowLifecycleReceipt:
        if terminal_state not in {"resolved_existing", "existing_review"} or type(observed_row) is not int or isinstance(observed_row, bool) or observed_row < 2 or not self._hash(observed_workbook_hash):
            raise NewRowActionError("new_row_action_outcome_invalid")
        try:
            with self.storage.transaction() as connection:
                row = self._authorized(connection, action_id, job_authorization)
                if row is None:
                    raise NewRowActionError("new_row_action_authority_invalid")
                existing = connection.execute("SELECT * FROM new_row_action_lifecycle_receipts WHERE action_id=?", (action_id,)).fetchone()
                if existing is not None:
                    receipt = self._receipt(existing)
                    if (receipt.terminal_state, receipt.observed_row, receipt.observed_workbook_hash) == (terminal_state, observed_row, observed_workbook_hash):
                        return receipt
                    raise NewRowActionError("new_row_action_outcome_conflict")
                if row["state"] != "publishing":
                    raise NewRowActionError("new_row_action_outcome_terminal")
                if connection.execute("SELECT 1 FROM workbook_operation_journal WHERE operation_id=?", (action_id,)).fetchone() is not None:
                    raise NewRowActionError("new_row_action_outcome_invalid")
                return self._insert_receipt(connection, {"action_id": action_id, "terminal_state": terminal_state,
                    "operation_id": None, "observed_row": observed_row, "expected_pre_hash": None,
                    "observed_workbook_hash": observed_workbook_hash, "created_at": utc_now()})
        except NewRowActionError:
            raise
        except sqlite3.Error as error:
            raise NewRowActionError("new_row_action_storage_failed") from error

    def classify_planned_pre_hash(self, action_id: str, *, job_authorization: str, observed_pre_hash: str) -> str:
        if not self._hash(observed_pre_hash):
            raise NewRowActionError("new_row_action_pre_hash_observation_invalid")
        try:
            with self.storage.transaction() as connection:
                action = self._authorized(connection, action_id, job_authorization)
                if action is None or action["state"] != "publishing":
                    raise NewRowActionError("new_row_action_abandonment_invalid")
                receipt = connection.execute("SELECT * FROM new_row_action_lifecycle_receipts WHERE action_id=?", (action_id,)).fetchone()
                if receipt is not None:
                    if receipt["terminal_state"] == "abandoned" and receipt["observed_workbook_hash"] == observed_pre_hash:
                        return "abandoned"
                    raise NewRowActionError("new_row_action_outcome_terminal")
                authority = connection.execute("SELECT * FROM workbook_authorities WHERE action_id=?", (action_id,)).fetchone()
                journal = connection.execute("SELECT * FROM workbook_operation_journal WHERE operation_id=?", (action_id,)).fetchone()
                if authority is None or journal is None or journal["phase"] != "planned":
                    raise NewRowActionError("new_row_action_abandonment_invalid")
                if tuple(authority[key] for key in ("construction_id", "workbook_contract_id", "target_identity", "target_path")) != tuple(action[key] for key in ("construction_id", "workbook_contract_id", "target_identity", "target_path")):
                    raise NewRowActionError("new_row_action_abandonment_invalid")
                if tuple(journal[key] for key in ("operation_id", "consumer_id", "construction_id", "workbook_contract_id", "target_identity")) != (
                    action_id, action_id, action["construction_id"], action["workbook_contract_id"], action["target_identity"]
                ):
                    raise NewRowActionError("new_row_action_abandonment_invalid")
                expected = authority["source_sha256"]
                if not self._hash(expected):
                    raise NewRowActionError("new_row_action_abandonment_invalid")
                if observed_pre_hash == expected:
                    return "live"
                # Only completely pristine planned evidence may become abandoned.
                if any(journal[key] is not None for key in ("pre_hash", "staged_hash", "control_hash", "post_hash", "backup_hash", "validation_digest", "failure_code")):
                    raise NewRowActionError("new_row_action_abandonment_invalid")
                now = utc_now()
                receipt = self._insert_receipt(connection, {"action_id": action_id, "terminal_state": "abandoned",
                    "operation_id": action_id, "observed_row": None, "expected_pre_hash": expected,
                    "observed_workbook_hash": observed_pre_hash, "created_at": now})
                if connection.execute("UPDATE workbook_operation_journal SET phase='abandoned', failure_code='planned_pre_hash_abandoned', updated_at=? WHERE operation_id=? AND phase='planned'", (now, action_id)).rowcount != 1:
                    raise NewRowActionError("new_row_action_abandonment_invalid")
                return receipt.terminal_state
        except NewRowActionError:
            raise
        except sqlite3.Error as error:
            raise NewRowActionError("new_row_action_storage_failed") from error

    @staticmethod
    def _public(row: sqlite3.Row) -> NewRowPendingAction:
        return NewRowPendingAction(
            action_id=str(row["action_id"]), job_id=str(row["job_id"]), construction_id=str(row["construction_id"]),
            workbook_contract_id=str(row["workbook_contract_id"]), target_identity=str(row["target_identity"]),
            target_path=str(row["target_path"]), state=str(row["effective_state"] if "effective_state" in row.keys() else row["state"]),
        )

    def _authorized(self, connection: sqlite3.Connection, action_id: str, capability: str) -> sqlite3.Row | None:
        if type(action_id) is not str or not action_id or not _is_nonempty_ascii(capability):
            return None
        row = connection.execute("SELECT * FROM new_row_pending_actions WHERE action_id=?", (action_id,)).fetchone()
        if row is None:
            return None
        if not _is_capability_digest(row["capability_digest"]):
            return None
        expected = capability_digest(action_id=action_id, capability=capability)
        if not hmac.compare_digest(row["capability_digest"], expected):
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
