"""One durable successor authority after a verified v3 publication.

This boundary has no workbook mutator and accepts no caller evidence.  Its
only input is an operation id; journal, pending action, snapshot, authority,
and the descriptor-bound target are read together before the one authority
successor and immutable receipt are committed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

from rns_import_server.registry_storage import RegistryError, RegistryStorage, utc_now
from rns_import_server.workbook_authority import (
    WorkbookAuthorityError, WorkbookAuthorityStore, _ownership_payload, _template_payload,
)
from rns_import_server.workbook_finalization_snapshot import verify_snapshot
from rns_import_server.workbook_projection import GroupOwnershipEvidence, TemplateCellEvidence


_V3_MANIFEST = "group-row-manifest-v3"
_LEGACY_MANIFESTS = frozenset({"group-row-manifest-v1", "group-row-manifest-v2"})
_HASH = frozenset("0123456789abcdef")
_AUTHORITY_FIELDS = (
    "action_id", "construction_id", "workbook_contract_id", "target_identity", "target_path", "sheet_identity",
    "template_version", "source_sha256", "template_evidence", "template_digest", "template_count",
    "ownership_evidence", "ownership_digest", "ownership_count", "max_row", "registry_generation", "created_at",
)


class WorkbookAuthorityRefreshError(RegistryError):
    """Typed, fail-closed authority refresh error."""


@dataclass(frozen=True)
class WorkbookAuthorityRefreshProgress:
    operation_id: str
    status: str
    refreshed: bool
    error_code: str | None = None


def _hash(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(char in _HASH for char in value)


def _target_sha256(value: object) -> str:
    if type(value) is not str or not value:
        raise WorkbookAuthorityRefreshError("workbook_authority_refresh_target_invalid")
    path = Path(value)
    try:
        before = os.lstat(path)
        if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode):
            raise OSError("target is not a regular file")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise OSError("target changed before descriptor binding")
            digest = hashlib.sha256()
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        finally:
            os.close(descriptor)
        after = os.lstat(path)
        if (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino):
            raise OSError("target changed during descriptor read")
        return digest.hexdigest()
    except OSError as error:
        raise WorkbookAuthorityRefreshError("workbook_authority_refresh_target_invalid") from error


def _manual_repair(connection: sqlite3.Connection, operation_id: str, code: str) -> WorkbookAuthorityRefreshProgress:
    if connection.execute(
        "UPDATE workbook_operation_journal SET phase='manual_repair', failure_code=?, updated_at=? "
        "WHERE operation_id=? AND phase='published'",
        (code, utc_now(), operation_id),
    ).rowcount != 1:
        raise WorkbookAuthorityRefreshError("workbook_authority_refresh_phase_invalid")
    return WorkbookAuthorityRefreshProgress(operation_id, "manual_repair", False, code)


def _snapshot_target_row(operation: sqlite3.Row, snapshot: sqlite3.Row | None) -> int | None:
    if snapshot is None or not verify_snapshot(
        operation_id=operation["operation_id"], consumer_id=operation["consumer_id"],
        workbook_contract_id=operation["workbook_contract_id"], post_hash=operation["post_hash"],
        snapshot_version=snapshot["snapshot_version"], canonical_payload=snapshot["canonical_payload"], digest=snapshot["digest"],
    ):
        return None
    # ``verify_snapshot`` has already checked canonical shape and target-row
    # type. Avoid accepting any alternate source for this row.
    try:
        target_row = json.loads(snapshot["canonical_payload"])["target_row"]
    except (KeyError, TypeError, ValueError):
        return None
    return target_row if type(target_row) is int and target_row >= 2 else None


def _authority_state(authority: sqlite3.Row | dict[str, object]) -> tuple[dict[str, object], str, str]:
    """Canonical immutable authority state, suitable for a receipt snapshot."""
    try:
        if set(authority.keys()) != set(_AUTHORITY_FIELDS):
            raise ValueError
        values = {field: authority[field] for field in _AUTHORITY_FIELDS}
        WorkbookAuthorityStore._decode(values)  # type: ignore[arg-type]
        canonical = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (KeyError, TypeError, ValueError, WorkbookAuthorityError) as error:
        raise WorkbookAuthorityRefreshError("workbook_authority_refresh_authority_corrupt") from error
    return values, canonical, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _receipt_prior_state(receipt: sqlite3.Row) -> tuple[dict[str, object], str] | None:
    value = receipt["prior_authority_payload"]
    if type(value) is not str:
        return None
    try:
        parsed = json.loads(value)
        if type(parsed) is not dict:
            return None
        state, canonical, digest = _authority_state(parsed)
    except (TypeError, ValueError, json.JSONDecodeError, WorkbookAuthorityRefreshError):
        return None
    if canonical != value or digest != receipt["old_authority_sha256"]:
        return None
    return state, digest


def _successor(
    authority: sqlite3.Row | dict[str, object], *, mutation_mode: str, target_row: int,
) -> tuple[str, str, str, str, int]:
    decoded = WorkbookAuthorityStore._decode(authority)
    ownership = decoded.group_ownership
    template = decoded.template_cells
    if target_row > len(ownership):
        raise WorkbookAuthorityRefreshError("workbook_authority_refresh_mapping_invalid")
    if mutation_mode == "blank_fill":
        changed_ownership = tuple(
            GroupOwnershipEvidence(item.row, True if item.row == target_row else item.owned) for item in ownership
        )
        changed_template = template
        max_row = authority["max_row"]
    elif mutation_mode == "middle_insert":
        changed_ownership = tuple(
            GroupOwnershipEvidence(item.row + 1 if item.row >= target_row else item.row, item.owned)
            for item in ownership
        )
        changed_ownership = tuple(
            list(changed_ownership[:target_row - 1]) + [GroupOwnershipEvidence(target_row, True)] + list(changed_ownership[target_row - 1:])
        )
        changed_template = tuple(
            TemplateCellEvidence(item.row + 1 if item.row >= target_row else item.row, item.column, item.value)
            for item in template
        )
        max_row = authority["max_row"] + 1
    else:
        raise WorkbookAuthorityRefreshError("workbook_authority_refresh_mapping_invalid")
    _, template_json, template_digest = _template_payload(changed_template)
    _, ownership_json, ownership_digest = _ownership_payload(changed_ownership, max_row)
    return template_json, template_digest, ownership_json, ownership_digest, max_row


def _receipt_valid(
    receipt: sqlite3.Row | None, operation: sqlite3.Row, action: sqlite3.Row, authority: sqlite3.Row,
    *, target_row: int,
) -> bool:
    if receipt is None:
        return False
    if (operation["operation_id"] != operation["consumer_id"] or operation["operation_kind"] != "new_row"
            or operation["manifest_version"] != _V3_MANIFEST or operation["mutation_mode"] not in {"blank_fill", "middle_insert"}
            or not _hash(operation["pre_hash"]) or not _hash(operation["post_hash"])):
        return False
    if (action["action_id"] != operation["operation_id"]
            or any(action[key] != operation[key] for key in ("construction_id", "workbook_contract_id", "target_identity"))
            or any(authority[key] != operation[key] for key in ("construction_id", "workbook_contract_id", "target_identity", "sheet_identity", "template_version"))
            or authority["target_path"] != action["target_path"]):
        return False
    fields = {
        "operation_id": operation["operation_id"], "action_id": action["action_id"], "consumer_id": operation["consumer_id"],
        "mutation_mode": operation["mutation_mode"], "target_row": target_row,
        "pre_hash": operation["pre_hash"], "post_hash": operation["post_hash"],
        "template_digest": authority["template_digest"], "ownership_digest": authority["ownership_digest"],
        "ownership_count": authority["ownership_count"], "max_row": authority["max_row"],
        "generation_after": authority["registry_generation"],
    }
    if any(receipt[key] != value for key, value in fields.items()):
        return False
    prior = _receipt_prior_state(receipt)
    if prior is None:
        return False
    prior_state, _ = prior
    if (prior_state["source_sha256"] != operation["pre_hash"] or prior_state["registry_generation"] != receipt["generation_before"]
            or any(prior_state[key] != authority[key] for key in ("action_id", "construction_id", "workbook_contract_id", "target_identity", "target_path", "sheet_identity", "template_version", "created_at"))):
        return False
    try:
        template_json, template_digest, ownership_json, ownership_digest, max_row = _successor(
            prior_state, mutation_mode=operation["mutation_mode"], target_row=target_row,
        )
        expected = dict(prior_state)
        expected.update(source_sha256=operation["post_hash"], template_evidence=template_json, template_digest=template_digest,
                        ownership_evidence=ownership_json, ownership_digest=ownership_digest, ownership_count=max_row,
                        max_row=max_row, registry_generation=receipt["generation_after"])
        _, _, expected_digest = _authority_state(expected)
        _, _, actual_digest = _authority_state(authority)
    except WorkbookAuthorityRefreshError:
        return False
    return (expected_digest == actual_digest == receipt["new_authority_sha256"]
            and _hash(receipt["old_authority_sha256"]) and _hash(receipt["new_authority_sha256"])
            and _hash(receipt["pre_hash"]) and _hash(receipt["post_hash"])
            and _hash(receipt["template_digest"]) and _hash(receipt["ownership_digest"])
            and type(receipt["generation_before"]) is int and type(receipt["generation_after"]) is int
            and receipt["generation_before"] + 1 == receipt["generation_after"]
            and type(receipt["created_at"]) is str and receipt["created_at"].endswith("Z"))


def has_valid_authority_refresh_receipt(connection: sqlite3.Connection, operation: sqlite3.Row) -> bool:
    """Verify the v3 receipt against the live successor authority, read-only."""
    if operation["manifest_version"] in _LEGACY_MANIFESTS:
        return True
    if operation["manifest_version"] != _V3_MANIFEST:
        return False
    action = connection.execute("SELECT * FROM new_row_pending_actions WHERE action_id=?", (operation["operation_id"],)).fetchone()
    authority = connection.execute("SELECT * FROM workbook_authorities WHERE action_id=?", (operation["operation_id"],)).fetchone()
    snapshot = connection.execute(
        "SELECT * FROM workbook_finalization_snapshots WHERE operation_id=?", (operation["operation_id"],)
    ).fetchone()
    if action is None or authority is None:
        return False
    target_row = _snapshot_target_row(operation, snapshot)
    if target_row is None:
        return False
    receipt = connection.execute(
        "SELECT * FROM workbook_authority_refresh_receipts WHERE operation_id=?", (operation["operation_id"],)
    ).fetchone()
    try:
        WorkbookAuthorityStore._decode(authority)
    except WorkbookAuthorityError:
        return False
    return _receipt_valid(receipt, operation, action, authority, target_row=target_row)


def refresh_published_authority(storage: RegistryStorage, operation_id: str) -> WorkbookAuthorityRefreshProgress:
    """Atomically advance one v3 authority, or retain published-pending on I/O faults."""
    if type(operation_id) is not str or not operation_id:
        raise WorkbookAuthorityRefreshError("workbook_authority_refresh_operation_missing")
    try:
        storage.connection.execute("PRAGMA synchronous=FULL")
        with storage.transaction() as connection:
            operation = connection.execute(
                "SELECT * FROM workbook_operation_journal WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if operation is None:
                raise WorkbookAuthorityRefreshError("workbook_authority_refresh_operation_missing")
            if operation["phase"] != "published":
                raise WorkbookAuthorityRefreshError("workbook_authority_refresh_phase_invalid")
            action = connection.execute("SELECT * FROM new_row_pending_actions WHERE action_id=?", (operation_id,)).fetchone()
            authority = connection.execute("SELECT * FROM workbook_authorities WHERE action_id=?", (operation_id,)).fetchone()
            snapshot = connection.execute(
                "SELECT * FROM workbook_finalization_snapshots WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if (operation["operation_id"] != operation["consumer_id"] or operation["operation_id"] != operation_id
                    or operation["operation_kind"] != "new_row" or operation["manifest_version"] != _V3_MANIFEST
                    or operation["mutation_mode"] not in {"blank_fill", "middle_insert"} or not _hash(operation["pre_hash"])
                    or not _hash(operation["post_hash"])):
                return _manual_repair(connection, operation_id, "workbook_authority_refresh_journal_invalid")
            if action is None or authority is None or action["action_id"] != operation_id:
                return _manual_repair(connection, operation_id, "workbook_authority_refresh_authority_missing")
            identities = ("construction_id", "workbook_contract_id", "target_identity")
            if (any(action[key] != operation[key] for key in identities)
                    or any(authority[key] != operation[key] for key in ("construction_id", "workbook_contract_id", "target_identity", "sheet_identity", "template_version"))
                    or authority["target_path"] != action["target_path"]):
                return _manual_repair(connection, operation_id, "workbook_authority_refresh_identity_conflict")
            target_row = _snapshot_target_row(operation, snapshot)
            if target_row is None:
                return _manual_repair(connection, operation_id, "workbook_authority_refresh_snapshot_invalid")
            try:
                prior_state, prior_payload, prior_digest = _authority_state(authority)
            except WorkbookAuthorityError:
                return _manual_repair(connection, operation_id, "workbook_authority_refresh_authority_corrupt")
            except WorkbookAuthorityRefreshError:
                return _manual_repair(connection, operation_id, "workbook_authority_refresh_authority_corrupt")
            try:
                target_sha256 = _target_sha256(action["target_path"])
            except WorkbookAuthorityRefreshError:
                return _manual_repair(connection, operation_id, "workbook_authority_refresh_target_invalid")
            if target_sha256 != operation["post_hash"]:
                return _manual_repair(connection, operation_id, "workbook_authority_refresh_target_invalid")
            receipt = connection.execute(
                "SELECT * FROM workbook_authority_refresh_receipts WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if authority["source_sha256"] == operation["post_hash"]:
                if _receipt_valid(receipt, operation, action, authority, target_row=target_row):
                    return WorkbookAuthorityRefreshProgress(operation_id, "published_pending_finalization", True)
                return _manual_repair(connection, operation_id, "workbook_authority_refresh_receipt_invalid")
            if authority["source_sha256"] != operation["pre_hash"] or receipt is not None:
                return _manual_repair(connection, operation_id, "workbook_authority_refresh_conflict")
            if action["state"] != "publishing":
                return _manual_repair(connection, operation_id, "workbook_authority_refresh_action_invalid")
            current_generation = connection.execute("SELECT generation FROM registry_meta WHERE id=1").fetchone()
            if current_generation is None or authority["registry_generation"] != current_generation["generation"]:
                return _manual_repair(connection, operation_id, "workbook_authority_refresh_generation_conflict")
            try:
                template_json, template_digest, ownership_json, ownership_digest, max_row = _successor(
                    prior_state, mutation_mode=operation["mutation_mode"], target_row=target_row,
                )
            except WorkbookAuthorityRefreshError as error:
                return _manual_repair(connection, operation_id, str(error))
            before = int(current_generation["generation"])
            after = before + 1
            successor_state = dict(prior_state)
            successor_state.update(source_sha256=operation["post_hash"], template_evidence=template_json, template_digest=template_digest,
                                   ownership_evidence=ownership_json, ownership_digest=ownership_digest, ownership_count=max_row,
                                   max_row=max_row, registry_generation=after)
            _, _, successor_digest = _authority_state(successor_state)
            now = utc_now()
            if connection.execute(
                "UPDATE workbook_authorities SET source_sha256=?, template_evidence=?, template_digest=?, ownership_evidence=?, "
                "ownership_digest=?, ownership_count=?, max_row=?, registry_generation=? "
                "WHERE action_id=? AND source_sha256=? AND registry_generation=?",
                (operation["post_hash"], template_json, template_digest, ownership_json, ownership_digest, max_row, max_row, after,
                 operation_id, operation["pre_hash"], before),
            ).rowcount != 1:
                raise sqlite3.OperationalError("authority successor CAS failed")
            connection.execute(
                "INSERT INTO workbook_authority_refresh_receipts("
                "operation_id,action_id,consumer_id,mutation_mode,target_row,old_authority_sha256,new_authority_sha256,"
                "pre_hash,post_hash,template_digest,ownership_digest,ownership_count,max_row,generation_before,generation_after,"
                "prior_authority_payload,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (operation_id, operation_id, operation_id, operation["mutation_mode"], target_row,
                 prior_digest, successor_digest, operation["pre_hash"], operation["post_hash"],
                 template_digest, ownership_digest, max_row, max_row, before, after, prior_payload, now),
            )
            if connection.execute(
                "UPDATE registry_meta SET generation=?, updated_at=? WHERE id=1 AND generation=?", (after, now, before)
            ).rowcount != 1:
                raise sqlite3.OperationalError("authority refresh generation CAS failed")
            return WorkbookAuthorityRefreshProgress(operation_id, "published_pending_finalization", True)
    except WorkbookAuthorityRefreshError:
        raise
    except sqlite3.Error:
        return WorkbookAuthorityRefreshProgress(
            operation_id, "published_pending_finalization", False, "workbook_authority_refresh_storage_failed",
        )


# The longer name documents the phase without creating another input surface.
refresh_published_workbook_authority = refresh_published_authority
