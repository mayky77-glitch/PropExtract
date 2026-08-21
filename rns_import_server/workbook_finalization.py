"""Durable post-publication finalizers.

K3b2a implements only the construction/workbook binding stage.  It receives
no workbook paths, report contents, or caller-supplied binding values: every
value comes from the published journal and the K3b1 authority snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
import uuid

from rns_import_server.registry_storage import RegistryError, RegistryStorage, utc_now
from rns_import_server.workbook_finalization_snapshot import verify_snapshot
from rns_import_server.workbook_operation_journal import PHASE_FINALIZED, PHASE_MANUAL_REPAIR, PHASE_PUBLISHED
from rns_import_server.workbook_finalization_snapshot import canonical_json


_SHA256 = re.compile(r"[0-9a-f]{64}")
_BINDING_FAILURE_CODES = frozenset({
    "finalization_authority_missing",
    "finalization_authority_corrupt",
    "finalization_binding_construction_invalid",
    "finalization_binding_conflict",
    "finalization_receipt_required",
})
_HISTORY_FAILURE_CODES = frozenset({
    "finalization_action_missing", "finalization_action_conflict", "finalization_history_order_invalid",
    "finalization_history_authority_corrupt", "finalization_history_conflict",
})
_REPORT_FAILURE_CODES = frozenset({
    "finalization_report_path_invalid", "finalization_target_hash_mismatch",
    "finalization_report_verify_failed", "finalization_capability_order_invalid",
    "finalization_capability_conflict", "finalization_order_invalid", "finalization_journal_failed",
})


@dataclass(frozen=True)
class FinalizationProgress:
    """Public, payload-free result of one post-publication finalizer stage."""

    operation_id: str
    status: str
    completed_stage: str | None
    next_stage: str | None
    stage: str = "binding"
    binding_id: str | None = None
    error_code: str | None = None


class FinalizationError(RegistryError):
    """A typed, non-secret binding finalization error."""

    def __init__(self, code: str, operation_id: str, *, stage: str = "binding"):
        self.code = code
        self.operation_id = operation_id
        self.stage = stage
        super().__init__(code)


def _pending(operation_id: str, code: str) -> FinalizationProgress:
    return FinalizationProgress(
        operation_id=operation_id,
        status="published_pending_finalization",
        completed_stage=None,
        next_stage="binding",
        error_code=code,
    )


def _history_pending(operation_id: str, code: str) -> FinalizationProgress:
    return FinalizationProgress(
        operation_id=operation_id, status="published_pending_finalization", completed_stage="binding",
        next_stage="history", stage="history", error_code=code,
    )


def _manual_repair(connection: sqlite3.Connection, operation_id: str, code: str) -> FinalizationProgress:
    if code not in _BINDING_FAILURE_CODES | _HISTORY_FAILURE_CODES | _REPORT_FAILURE_CODES:
        raise AssertionError("finalizer failure code must be frozen")
    updated = connection.execute(
        "UPDATE workbook_operation_journal SET phase=?, failure_code=?, updated_at=? "
        "WHERE operation_id=? AND phase=?",
        (PHASE_MANUAL_REPAIR, code, utc_now(), operation_id, PHASE_PUBLISHED),
    ).rowcount
    if updated != 1:
        raise FinalizationError("finalization_phase_invalid", operation_id)
    return FinalizationProgress(
        operation_id=operation_id,
        status=PHASE_MANUAL_REPAIR,
        completed_stage=None,
        next_stage=None,
        error_code=code,
    )


def _history_manual_repair(connection: sqlite3.Connection, operation_id: str, code: str) -> FinalizationProgress:
    result = _manual_repair(connection, operation_id, code)
    return FinalizationProgress(
        operation_id=result.operation_id, status=result.status, completed_stage=None, next_stage=None,
        stage="history", error_code=result.error_code,
    )


def _authority_failure(connection: sqlite3.Connection, operation: sqlite3.Row) -> str | None:
    snapshot = connection.execute(
        "SELECT snapshot_version, canonical_payload, digest "
        "FROM workbook_finalization_snapshots WHERE operation_id=?",
        (operation["operation_id"],),
    ).fetchone()
    if snapshot is None:
        return "finalization_authority_missing"
    post_hash = operation["post_hash"]
    if type(post_hash) is not str or not _SHA256.fullmatch(post_hash):
        return "finalization_authority_corrupt"
    if not verify_snapshot(
        operation_id=operation["operation_id"],
        consumer_id=operation["consumer_id"],
        workbook_contract_id=operation["workbook_contract_id"],
        post_hash=post_hash,
        snapshot_version=snapshot["snapshot_version"],
        canonical_payload=snapshot["canonical_payload"],
        digest=snapshot["digest"],
    ):
        return "finalization_authority_corrupt"
    return None


def _binding_values(operation: sqlite3.Row) -> tuple[str, str, str, str, str] | None:
    values = (
        operation["construction_id"],
        operation["workbook_contract_id"],
        operation["target_identity"],
        operation["sheet_identity"],
        operation["template_version"],
    )
    if any(type(value) is not str or not value.strip() for value in values):
        return None
    return values  # type: ignore[return-value]


def _is_canonical_utc(value: object) -> bool:
    if type(value) is not str:
        return False
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%dT%H:%M:%SZ") == value
    except ValueError:
        return False


def _valid_exact_binding(row: sqlite3.Row, values: tuple[str, str, str, str, str]) -> bool:
    binding_id = row["id"]
    if type(binding_id) is not str or not binding_id:
        return False
    try:
        if str(uuid.UUID(binding_id)) != binding_id:
            return False
    except ValueError:
        return False
    construction_id, workbook_contract_id, target_identity, sheet_identity, template_version = values
    if (row["construction_id"], row["workbook_contract_id"], row["target_identity"], row["sheet_identity"],
            row["template_version"], row["verified_state"]) != (
                construction_id, workbook_contract_id, target_identity, sheet_identity, template_version, "verified"):
        return False
    return all(_is_canonical_utc(row[column]) for column in ("verified_at", "created_at", "updated_at"))


def _increment_generation(connection: sqlite3.Connection, now: str) -> None:
    if connection.execute(
        "UPDATE registry_meta SET generation=generation+1, updated_at=? WHERE id=1", (now,)
    ).rowcount != 1:
        raise sqlite3.OperationalError("registry generation authority is missing or ambiguous")


def _write_binding_receipt(connection: sqlite3.Connection, operation_id: str) -> bool:
    now = utc_now()
    return connection.execute(
        "UPDATE workbook_operation_journal SET binding_finalized=1, binding_finalized_at=?, updated_at=? "
        "WHERE operation_id=? AND phase=? AND binding_finalized=0",
        (now, now, operation_id, PHASE_PUBLISHED),
    ).rowcount == 1


def finalize_published_binding(storage: RegistryStorage, operation_id: str) -> FinalizationProgress:
    """Insert-or-verify the one binding and receipt for a published operation.

    A SQLite fault is intentionally surfaced as a pending, non-successful
    result.  Since both the binding and receipt are one transaction, rollback
    keeps the operation published and makes a later explicit retry safe.
    """
    if type(operation_id) is not str or not operation_id:
        raise FinalizationError("finalization_operation_missing", operation_id if type(operation_id) is str else "")
    try:
        storage.connection.execute("PRAGMA synchronous=FULL")
        with storage.transaction() as connection:
            operation = connection.execute(
                "SELECT * FROM workbook_operation_journal WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if operation is None:
                raise FinalizationError("finalization_operation_missing", operation_id)
            if operation["phase"] != PHASE_PUBLISHED:
                raise FinalizationError("finalization_phase_invalid", operation_id)
            if operation["operation_kind"] != "new_row" or operation["consumer_id"] != operation_id:
                return _manual_repair(connection, operation_id, "finalization_authority_corrupt")
            authority_failure = _authority_failure(connection, operation)
            if authority_failure:
                return _manual_repair(connection, operation_id, authority_failure)
            if any(operation[flag] for flag in ("capability_finalized", "history_finalized", "report_finalized")):
                return _manual_repair(connection, operation_id, "finalization_authority_corrupt")
            values = _binding_values(operation)
            if values is None:
                return _manual_repair(connection, operation_id, "finalization_binding_construction_invalid")
            construction_id, workbook_contract_id, target_identity, sheet_identity, template_version = values
            if connection.execute("SELECT 1 FROM constructions WHERE id=?", (construction_id,)).fetchone() is None:
                return _manual_repair(connection, operation_id, "finalization_binding_construction_invalid")
            bindings = connection.execute(
                "SELECT * FROM construction_bindings WHERE construction_id=? ORDER BY id", (construction_id,)
            ).fetchall()
            exact = [
                row for row in bindings
                if (row["workbook_contract_id"], row["target_identity"], row["sheet_identity"],
                    row["template_version"], row["verified_state"])
                == (workbook_contract_id, target_identity, sheet_identity, template_version, "verified")
            ]
            if operation["binding_finalized"] and not _is_canonical_utc(operation["binding_finalized_at"]):
                return _manual_repair(connection, operation_id, "finalization_receipt_required")
            if operation["binding_finalized"] and not bindings:
                return _manual_repair(connection, operation_id, "finalization_receipt_required")
            if len(bindings) > 1 or (bindings and len(exact) != 1):
                return _manual_repair(connection, operation_id, "finalization_binding_conflict")
            if bindings:
                if not _valid_exact_binding(exact[0], values):
                    return _manual_repair(connection, operation_id, "finalization_binding_conflict")
                binding_id = exact[0]["id"]
            else:
                binding_id = str(uuid.uuid4())
                now = utc_now()
                connection.execute(
                    "INSERT INTO construction_bindings VALUES (?, ?, ?, ?, ?, ?, 'verified', ?, ?, ?)",
                    (binding_id, construction_id, workbook_contract_id, target_identity, sheet_identity,
                     template_version, now, now, now),
                )
                _increment_generation(connection, now)
            if operation["binding_finalized"]:
                # The exact canonical timestamp was already verified above.
                pass
            else:
                if not _write_binding_receipt(connection, operation_id):
                    raise FinalizationError("finalization_phase_invalid", operation_id)
            return FinalizationProgress(
                operation_id=operation_id,
                status="published_pending_finalization",
                completed_stage="binding",
                next_stage="history",
                binding_id=binding_id,
            )
    except FinalizationError:
        raise
    except sqlite3.Error:
        return _pending(operation_id, "finalization_binding_storage_failed")


def _history_event(*, action_id: str, target_row: int, post_hash: str) -> tuple[str, str]:
    payload = {
        "action_id": action_id, "event_version": 1, "event_type": "new_row", "status": "published",
        "target_row": target_row, "post_hash": post_hash,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(b"PropExtract/new-row-history/v1\x00" + canonical.encode("utf-8")).hexdigest()
    return canonical, digest


def _valid_history_row(row: sqlite3.Row, *, operation_id: str, target_row: int, post_hash: str, digest: str) -> bool:
    return (
        row["action_id"] == operation_id and row["event_version"] == 1 and row["event_type"] == "new_row"
        and row["status"] == "published" and row["target_row"] == target_row and row["post_hash"] == post_hash
        and row["digest"] == digest and _is_canonical_utc(row["created_at"])
    )


def _write_history_receipt(connection: sqlite3.Connection, operation_id: str, now: str) -> bool:
    """Write only the first history receipt; never repair a partial marker."""
    return connection.execute(
        "UPDATE workbook_operation_journal SET history_finalized=1, history_finalized_at=?, updated_at=? "
        "WHERE operation_id=? AND phase=? AND history_finalized=0 AND history_finalized_at IS NULL",
        (now, now, operation_id, PHASE_PUBLISHED),
    ).rowcount == 1


def _valid_history_action(operation: sqlite3.Row, action: sqlite3.Row) -> str | None:
    if action["action_id"] != operation["operation_id"]:
        return "finalization_action_conflict"
    expected = (operation["construction_id"], operation["workbook_contract_id"], operation["target_identity"])
    actual = (action["construction_id"], action["workbook_contract_id"], action["target_identity"])
    if actual != expected:
        return "finalization_action_conflict"
    if any(type(action[key]) is not str or not action[key] for key in ("job_id", "target_path", "capability_digest")):
        return "finalization_history_authority_corrupt"
    if not _SHA256.fullmatch(str(action["capability_digest"])):
        return "finalization_history_authority_corrupt"
    # The durable path itself remains an authority: stale, relative, or
    # symlinked targets cannot be finalized as though they were the original.
    from rns_import_server.new_row_action_store import _canonical_target_path, NewRowActionError
    try:
        if _canonical_target_path(action["target_path"]) != action["target_path"]:
            return "finalization_history_authority_corrupt"
    except NewRowActionError:
        return "finalization_history_authority_corrupt"
    if action["state"] not in {"publishing", "consumed"}:
        return "finalization_action_conflict"
    return None


def finalize_published_history(storage: RegistryStorage, operation_id: str) -> FinalizationProgress:
    """Atomically write the canonical new-row history event and its receipt.

    Binding is prerequisite evidence, not a caller promise.  No report or
    capability receipt is touched here; later stages own those boundaries.
    """
    if type(operation_id) is not str or not operation_id:
        raise FinalizationError("finalization_operation_missing", operation_id if type(operation_id) is str else "", stage="history")
    try:
        storage.connection.execute("PRAGMA synchronous=FULL")
        with storage.transaction() as connection:
            operation = connection.execute("SELECT * FROM workbook_operation_journal WHERE operation_id=?", (operation_id,)).fetchone()
            if operation is None:
                raise FinalizationError("finalization_operation_missing", operation_id, stage="history")
            if operation["phase"] != PHASE_PUBLISHED:
                raise FinalizationError("finalization_phase_invalid", operation_id, stage="history")
            if operation["operation_kind"] != "new_row" or operation["consumer_id"] != operation_id:
                return _history_manual_repair(connection, operation_id, "finalization_history_authority_corrupt")
            if _authority_failure(connection, operation):
                return _history_manual_repair(connection, operation_id, "finalization_history_authority_corrupt")
            if not operation["binding_finalized"] or not _is_canonical_utc(operation["binding_finalized_at"]):
                return _history_manual_repair(connection, operation_id, "finalization_history_order_invalid")
            values = _binding_values(operation)
            if values is None:
                return _history_manual_repair(connection, operation_id, "finalization_history_order_invalid")
            bindings = connection.execute("SELECT * FROM construction_bindings WHERE construction_id=? ORDER BY id", (values[0],)).fetchall()
            if len(bindings) != 1 or not _valid_exact_binding(bindings[0], values):
                return _history_manual_repair(connection, operation_id, "finalization_history_order_invalid")
            action = connection.execute("SELECT * FROM new_row_pending_actions WHERE action_id=?", (operation_id,)).fetchone()
            if action is None:
                return _history_manual_repair(connection, operation_id, "finalization_action_missing")
            action_failure = _valid_history_action(operation, action)
            if action_failure:
                return _history_manual_repair(connection, operation_id, action_failure)
            snapshot = connection.execute("SELECT canonical_payload FROM workbook_finalization_snapshots WHERE operation_id=?", (operation_id,)).fetchone()
            if snapshot is None:
                return _history_manual_repair(connection, operation_id, "finalization_history_authority_corrupt")
            try:
                payload = json.loads(snapshot["canonical_payload"])
                target_row = payload["target_row"]
            except (TypeError, ValueError, KeyError):
                return _history_manual_repair(connection, operation_id, "finalization_history_authority_corrupt")
            if type(target_row) is not int or target_row < 2 or type(operation["post_hash"]) is not str:
                return _history_manual_repair(connection, operation_id, "finalization_history_authority_corrupt")
            _, digest = _history_event(action_id=operation_id, target_row=target_row, post_hash=operation["post_hash"])
            history = connection.execute("SELECT * FROM new_row_action_history WHERE action_id=?", (operation_id,)).fetchone()
            if action["state"] == "consumed" and not operation["history_finalized"]:
                # Consumed belongs to a later terminal boundary. It can only
                # be replayed with an already durable history receipt.
                return _history_manual_repair(connection, operation_id, "finalization_action_conflict")
            if operation["history_finalized"]:
                if not _is_canonical_utc(operation["history_finalized_at"]) or history is None or not _valid_history_row(
                    history, operation_id=operation_id, target_row=target_row, post_hash=operation["post_hash"], digest=digest,
                ):
                    return _history_manual_repair(connection, operation_id, "finalization_history_conflict")
                # History is already durable. Coherent later finalizers own
                # their receipts and must not turn this exact replay into a
                # write or a false repair requirement.
                return FinalizationProgress(operation_id, "published_pending_finalization", "history", "report", stage="history")
            if history is not None:
                return _history_manual_repair(connection, operation_id, "finalization_history_conflict")
            if (any(operation[flag] for flag in ("report_finalized", "capability_finalized"))
                    or any(operation[f"{flag}_at"] is not None for flag in ("report_finalized", "capability_finalized"))
                    or operation["report_snapshot_digest"] is not None):
                return _history_manual_repair(connection, operation_id, "finalization_history_order_invalid")
            if operation["history_finalized_at"] is not None:
                return _history_manual_repair(connection, operation_id, "finalization_history_order_invalid")
            now = utc_now()
            connection.execute(
                "INSERT INTO new_row_action_history(action_id,event_version,event_type,status,target_row,post_hash,digest,created_at) VALUES(?,1,'new_row','published',?,?,?,?)",
                (operation_id, target_row, operation["post_hash"], digest, now),
            )
            if not _write_history_receipt(connection, operation_id, now):
                raise sqlite3.OperationalError("history receipt CAS failed")
            return FinalizationProgress(operation_id, "published_pending_finalization", "history", "report", stage="history")
    except FinalizationError:
        raise
    except sqlite3.Error:
        return _history_pending(operation_id, "finalization_history_storage_failed")


def _stage_pending(operation_id: str, completed: str, next_stage: str, code: str) -> FinalizationProgress:
    return FinalizationProgress(operation_id, "published_pending_finalization", completed, next_stage,
                                stage=next_stage, error_code=code)


def _preflight_target(connection: sqlite3.Connection, operation: sqlite3.Row) -> tuple[sqlite3.Row, Path] | str:
    """Check the immutable workbook authority before *any* finalizer write."""
    if operation["operation_kind"] != "new_row" or operation["consumer_id"] != operation["operation_id"]:
        return "finalization_journal_failed"
    if _authority_failure(connection, operation):
        return "finalization_journal_failed"
    action = connection.execute("SELECT * FROM new_row_pending_actions WHERE action_id=?", (operation["operation_id"],)).fetchone()
    if action is None:
        return "finalization_capability_conflict"
    if (action["action_id"] != operation["operation_id"]
            or (action["construction_id"], action["workbook_contract_id"], action["target_identity"])
            != (operation["construction_id"], operation["workbook_contract_id"], operation["target_identity"])
            or action["state"] not in {"publishing", "consumed"}
            or not _SHA256.fullmatch(str(action["capability_digest"]))):
        return "finalization_capability_conflict"
    target_text = action["target_path"]
    if type(target_text) is not str or not target_text:
        return "finalization_report_path_invalid"
    target = Path(target_text)
    if not target.is_absolute():
        return "finalization_report_path_invalid"
    try:
        target.lstat()
    except FileNotFoundError:
        return "finalization_target_hash_mismatch"
    except OSError:
        return "finalization_report_verify_failed"
    try:
        from rns_import_server.new_row_action_store import NewRowActionError, _canonical_target_path
        if _canonical_target_path(target_text) != target_text:
            return "finalization_report_path_invalid"
    except NewRowActionError:  # canonical path rejects non-regular/symlink authority
        return "finalization_report_path_invalid"
    try:
        actual_hash = _sha256_file(target)
    except OSError:
        return "finalization_report_verify_failed"
    if actual_hash != operation["post_hash"]:
        return "finalization_target_hash_mismatch"
    return action, target


def _verify_completed_binding(connection: sqlite3.Connection, operation: sqlite3.Row) -> str | None:
    if not operation["binding_finalized"] or not _is_canonical_utc(operation["binding_finalized_at"]):
        return "finalization_order_invalid"
    values = _binding_values(operation)
    if values is None:
        return "finalization_order_invalid"
    bindings = connection.execute("SELECT * FROM construction_bindings WHERE construction_id=? ORDER BY id", (values[0],)).fetchall()
    if len(bindings) != 1 or not _valid_exact_binding(bindings[0], values):
        return "finalization_order_invalid"
    return None


def _terminal_manual_repair(storage: RegistryStorage, operation_id: str, code: str) -> FinalizationProgress:
    """Make a post-terminal authority contradiction visible and durable."""
    from rns_import_server.workbook_operation_journal import WorkbookOperationJournal
    WorkbookOperationJournal(storage).record_repair_anomaly(operation_id, failure_code=code)
    return FinalizationProgress(operation_id, PHASE_MANUAL_REPAIR, None, None, stage="finalized", error_code=code)


def _report_path(target: Path) -> Path:
    return target.with_name(f"{target.stem} — отчет PropExtract.json")


def _sha256_file(path: Path) -> str:
    if not hasattr(os, "O_NOFOLLOW"):
        raise OSError("secure no-follow open unavailable")
    flags = os.O_RDONLY | os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise OSError("not a regular file")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def _read_exact_regular(path: Path, expected: bytes) -> bool:
    try:
        if not hasattr(os, "O_NOFOLLOW"):
            return False
        flags = os.O_RDONLY | os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                return False
            chunks: list[bytes] = []
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks) == expected
        finally:
            os.close(descriptor)
    except OSError:
        return False


def _publish_report_bytes(path: Path, payload: bytes) -> None:
    """Write one private same-directory file and durably replace the report."""
    parent = path.parent
    # A symlinked parent is authority confusion: unlike an existing report
    # symlink, it would redirect where the private replacement is created.
    if not parent.is_dir() or parent.is_symlink():
        raise OSError("report parent invalid")
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=parent)
        temporary = Path(name)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or (info.st_mode & 0o077):
                raise OSError("report temporary is not private")
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("report write incomplete")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, path)
        temporary = None
        directory = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _finalization_payload(connection: sqlite3.Connection, operation: sqlite3.Row) -> tuple[sqlite3.Row, dict[str, object], bytes] | None:
    snapshot = connection.execute(
        "SELECT snapshot_version, canonical_payload, digest FROM workbook_finalization_snapshots WHERE operation_id=?",
        (operation["operation_id"],),
    ).fetchone()
    if snapshot is None or _authority_failure(connection, operation):
        return None
    try:
        payload = json.loads(snapshot["canonical_payload"])
        if type(payload) is not dict or type(payload.get("report_payload")) is not dict:
            return None
        report = payload["report_payload"]
        encoded = (canonical_json(report) + "\n").encode("utf-8")
    except (TypeError, ValueError):
        return None
    return snapshot, report, encoded


def _valid_report_receipt(operation: sqlite3.Row, content: bytes) -> bool:
    digest = hashlib.sha256(content).hexdigest()
    return (operation["report_finalized"] == 1 and _is_canonical_utc(operation["report_finalized_at"])
            and operation["report_snapshot_digest"] == digest)


def _valid_late_prerequisites(connection: sqlite3.Connection, operation: sqlite3.Row) -> tuple[sqlite3.Row, Path, bytes] | str:
    if operation["operation_kind"] != "new_row" or operation["consumer_id"] != operation["operation_id"]:
        return "finalization_journal_failed"
    payload = _finalization_payload(connection, operation)
    if payload is None:
        return "finalization_journal_failed"
    _, _, content = payload
    action = connection.execute("SELECT * FROM new_row_pending_actions WHERE action_id=?", (operation["operation_id"],)).fetchone()
    if action is None:
        return "finalization_capability_conflict"
    failure = _valid_history_action(operation, action)
    if failure:
        return "finalization_capability_conflict"
    try:
        target_text = action["target_path"]
        from rns_import_server.new_row_action_store import _canonical_target_path
        raw_target = Path(target_text)
        if raw_target.is_absolute() and not raw_target.exists() and not raw_target.is_symlink():
            return "finalization_target_hash_mismatch"
        if _canonical_target_path(target_text) != target_text:
            return "finalization_report_path_invalid"
        target = Path(target_text)
        if _sha256_file(target) != operation["post_hash"]:
            return "finalization_target_hash_mismatch"
    except (OSError, ValueError):
        return "finalization_report_path_invalid"
    if not operation["binding_finalized"] or not _is_canonical_utc(operation["binding_finalized_at"]):
        return "finalization_order_invalid"
    if not operation["history_finalized"] or not _is_canonical_utc(operation["history_finalized_at"]):
        return "finalization_order_invalid"
    snapshot = connection.execute(
        "SELECT canonical_payload FROM workbook_finalization_snapshots WHERE operation_id=?", (operation["operation_id"],)
    ).fetchone()
    history = connection.execute("SELECT * FROM new_row_action_history WHERE action_id=?", (operation["operation_id"],)).fetchone()
    try:
        target_row = json.loads(snapshot["canonical_payload"])["target_row"] if snapshot is not None else None
        _, history_digest = _history_event(action_id=operation["operation_id"], target_row=target_row, post_hash=operation["post_hash"])
    except (TypeError, ValueError, KeyError):
        return "finalization_journal_failed"
    if type(target_row) is not int or history is None or not _valid_history_row(
        history, operation_id=operation["operation_id"], target_row=target_row,
        post_hash=operation["post_hash"], digest=history_digest,
    ):
        return "finalization_order_invalid"
    return action, target, content


def _report_receipt(storage: RegistryStorage, operation_id: str, content: bytes) -> FinalizationProgress | None:
    """Record report evidence after a verified disk replacement, never before."""
    digest = hashlib.sha256(content).hexdigest()
    try:
        with storage.transaction() as connection:
            operation = connection.execute("SELECT * FROM workbook_operation_journal WHERE operation_id=?", (operation_id,)).fetchone()
            if operation is None or operation["phase"] != PHASE_PUBLISHED:
                raise FinalizationError("finalization_phase_invalid", operation_id, stage="report")
            required = _valid_late_prerequisites(connection, operation)
            if isinstance(required, str):
                return _manual_repair(connection, operation_id, required)
            _, target, expected = required
            if expected != content or not _read_exact_regular(_report_path(target), content):
                return _stage_pending(operation_id, "history", "report", "finalization_report_verify_failed")
            if operation["report_finalized"]:
                if _valid_report_receipt(operation, content):
                    return None
                return _manual_repair(connection, operation_id, "finalization_order_invalid")
            if operation["report_finalized_at"] is not None or operation["report_snapshot_digest"] is not None:
                return _manual_repair(connection, operation_id, "finalization_order_invalid")
            now = utc_now()
            if connection.execute(
                "UPDATE workbook_operation_journal SET report_finalized=1, report_finalized_at=?, report_snapshot_digest=?, updated_at=? "
                "WHERE operation_id=? AND phase='published' AND report_finalized=0 AND report_finalized_at IS NULL AND report_snapshot_digest IS NULL",
                (now, digest, now, operation_id),
            ).rowcount != 1:
                raise sqlite3.OperationalError("report receipt CAS failed")
    except FinalizationError:
        raise
    except sqlite3.Error:
        return _stage_pending(operation_id, "history", "report", "finalization_report_receipt_failed")
    return None


def _consume_capability(storage: RegistryStorage, operation_id: str) -> FinalizationProgress | None:
    try:
        with storage.transaction() as connection:
            operation = connection.execute("SELECT * FROM workbook_operation_journal WHERE operation_id=?", (operation_id,)).fetchone()
            if operation is None or operation["phase"] != PHASE_PUBLISHED:
                raise FinalizationError("finalization_phase_invalid", operation_id, stage="capability")
            required = _valid_late_prerequisites(connection, operation)
            if isinstance(required, str):
                return _manual_repair(connection, operation_id, required)
            action, target, content = required
            if not _valid_report_receipt(operation, content) or not _read_exact_regular(_report_path(target), content):
                return _manual_repair(connection, operation_id, "finalization_capability_order_invalid")
            if action["state"] == "consumed":
                if operation["capability_finalized"] and _is_canonical_utc(operation["capability_finalized_at"]):
                    return None
                return _manual_repair(connection, operation_id, "finalization_capability_conflict")
            if action["state"] != "publishing" or operation["capability_finalized"] or operation["capability_finalized_at"] is not None:
                return _manual_repair(connection, operation_id, "finalization_capability_conflict")
            now = utc_now()
            if connection.execute("UPDATE new_row_pending_actions SET state='consumed', updated_at=? WHERE action_id=? AND state='publishing'", (now, operation_id)).rowcount != 1:
                raise sqlite3.OperationalError("capability CAS failed")
            if connection.execute(
                "UPDATE workbook_operation_journal SET capability_finalized=1, capability_finalized_at=?, updated_at=? "
                "WHERE operation_id=? AND phase='published' AND capability_finalized=0 AND capability_finalized_at IS NULL",
                (now, now, operation_id),
            ).rowcount != 1:
                raise sqlite3.OperationalError("capability receipt CAS failed")
    except FinalizationError:
        raise
    except sqlite3.Error:
        return _stage_pending(operation_id, "report", "capability", "finalization_capability_storage_failed")
    return None


def _complete_finalization(storage: RegistryStorage, operation_id: str) -> FinalizationProgress | None:
    try:
        with storage.transaction() as connection:
            operation = connection.execute("SELECT * FROM workbook_operation_journal WHERE operation_id=?", (operation_id,)).fetchone()
            if operation is None:
                raise FinalizationError("finalization_operation_missing", operation_id, stage="finalized")
            if operation["phase"] == PHASE_FINALIZED:
                required = _valid_late_prerequisites(connection, operation)
                if isinstance(required, str):
                    return _stage_pending(operation_id, "capability", "finalized", required)
                action, target, content = required
                if (action["state"] == "consumed" and operation["capability_finalized"]
                        and _is_canonical_utc(operation["capability_finalized_at"])
                        and _valid_report_receipt(operation, content) and _read_exact_regular(_report_path(target), content)
                        and _is_canonical_utc(operation["finalized_at"])):
                    return FinalizationProgress(operation_id, PHASE_FINALIZED, "finalized", None, stage="finalized")
                return _stage_pending(operation_id, "capability", "finalized", "finalization_order_invalid")
            if operation["phase"] != PHASE_PUBLISHED:
                raise FinalizationError("finalization_phase_invalid", operation_id, stage="finalized")
            required = _valid_late_prerequisites(connection, operation)
            if isinstance(required, str):
                return _manual_repair(connection, operation_id, required)
            action, target, content = required
            if (action["state"] != "consumed" or not operation["capability_finalized"]
                    or not _is_canonical_utc(operation["capability_finalized_at"])
                    or not _valid_report_receipt(operation, content) or not _read_exact_regular(_report_path(target), content)):
                return _manual_repair(connection, operation_id, "finalization_order_invalid")
            now = utc_now()
            if connection.execute(
                "UPDATE workbook_operation_journal SET phase='finalized', finalized_at=?, updated_at=? "
                "WHERE operation_id=? AND phase='published'", (now, now, operation_id),
            ).rowcount != 1:
                raise sqlite3.OperationalError("finalized CAS failed")
            return FinalizationProgress(operation_id, PHASE_FINALIZED, "finalized", None, stage="finalized")
    except FinalizationError:
        raise
    except sqlite3.Error:
        return _stage_pending(operation_id, "capability", "finalized", "finalization_journal_failed")


def finalize_published_operation(storage: RegistryStorage, operation_id: str) -> FinalizationProgress:
    """Finalize the snapshot-owned report and consume the one action capability.

    The workflow is deliberately restartable at each durable receipt.  No
    call accepts a path, report payload, capability, or workbook adapter.
    """
    if type(operation_id) is not str or not operation_id:
        raise FinalizationError("finalization_operation_missing", operation_id if type(operation_id) is str else "", stage="report")
    try:
        with storage.transaction() as connection:
            current = connection.execute("SELECT * FROM workbook_operation_journal WHERE operation_id=?", (operation_id,)).fetchone()
            if current is None:
                raise FinalizationError("finalization_operation_missing", operation_id, stage="binding")
            if current["phase"] not in {PHASE_PUBLISHED, PHASE_FINALIZED}:
                raise FinalizationError("finalization_phase_invalid", operation_id, stage="binding")
            checked_target = _preflight_target(connection, current)
            if isinstance(checked_target, str):
                if checked_target == "finalization_report_verify_failed":
                    return _pending(operation_id, checked_target)
                if current["phase"] == PHASE_FINALIZED:
                    repair_code = checked_target
                else:
                    return _manual_repair(connection, operation_id, checked_target)
            else:
                repair_code = None
        if repair_code is not None:
            return _terminal_manual_repair(storage, operation_id, repair_code)
    except FinalizationError:
        raise
    except sqlite3.Error:
        return _pending(operation_id, "finalization_journal_failed")

    existing = storage.connection.execute("SELECT * FROM workbook_operation_journal WHERE operation_id=?", (operation_id,)).fetchone()
    assert existing is not None
    if existing["phase"] == PHASE_FINALIZED:
        # A terminal replay only restores the snapshot report if needed; it
        # never re-enters binding/history and never changes a receipt.
        try:
            with storage.transaction() as connection:
                current = connection.execute("SELECT * FROM workbook_operation_journal WHERE operation_id=?", (operation_id,)).fetchone()
                assert current is not None
                required = _valid_late_prerequisites(connection, current)
                if isinstance(required, str):
                    repair_code = required
                else:
                    repair_code = None
                    _, target, content = required
                    path = _report_path(target)
            if repair_code is not None:
                return _terminal_manual_repair(storage, operation_id, repair_code)
            if not _read_exact_regular(path, content):
                _publish_report_bytes(path, content)
        except OSError:
            return _stage_pending(operation_id, "capability", "finalized", "finalization_report_write_failed")
        except sqlite3.Error:
            return _stage_pending(operation_id, "capability", "finalized", "finalization_journal_failed")
        completed = _complete_finalization(storage, operation_id)
        assert completed is not None
        return completed

    if not existing["binding_finalized"]:
        binding = finalize_published_binding(storage, operation_id)
        if binding.status == PHASE_MANUAL_REPAIR or binding.next_stage != "history":
            return binding
    else:
        with storage.transaction() as connection:
            current = connection.execute("SELECT * FROM workbook_operation_journal WHERE operation_id=?", (operation_id,)).fetchone()
            assert current is not None
            binding_failure = _verify_completed_binding(connection, current)
            if binding_failure:
                return _manual_repair(connection, operation_id, binding_failure)
    current = storage.connection.execute("SELECT * FROM workbook_operation_journal WHERE operation_id=?", (operation_id,)).fetchone()
    assert current is not None
    if not current["history_finalized"]:
        history = finalize_published_history(storage, operation_id)
        if history.status == PHASE_MANUAL_REPAIR or history.next_stage != "report":
            return history
    try:
        operation = storage.connection.execute("SELECT * FROM workbook_operation_journal WHERE operation_id=?", (operation_id,)).fetchone()
        if operation is None or operation["phase"] != PHASE_PUBLISHED:
            raise FinalizationError("finalization_phase_invalid", operation_id, stage="report")
        with storage.transaction() as connection:
            current = connection.execute("SELECT * FROM workbook_operation_journal WHERE operation_id=?", (operation_id,)).fetchone()
            assert current is not None
            required = _valid_late_prerequisites(connection, current)
            if isinstance(required, str):
                return _manual_repair(connection, operation_id, required)
            _, target, content = required
            path = _report_path(target)
            report_receipted = _valid_report_receipt(current, content)
        # An exact file is not proof that a prior rename survived a directory
        # fsync failure.  Until the DB receipt exists, republish and fsync.
        if not report_receipted or not _read_exact_regular(path, content):
            _publish_report_bytes(path, content)
        if not _read_exact_regular(path, content):
            return _stage_pending(operation_id, "history", "report", "finalization_report_verify_failed")
    except FinalizationError:
        raise
    except OSError:
        return _stage_pending(operation_id, "history", "report", "finalization_report_write_failed")
    except sqlite3.Error:
        return _stage_pending(operation_id, "history", "report", "finalization_journal_failed")
    report = _report_receipt(storage, operation_id, content)
    if report is not None:
        return report
    capability = _consume_capability(storage, operation_id)
    if capability is not None:
        return capability
    completed = _complete_finalization(storage, operation_id)
    assert completed is not None
    return completed
