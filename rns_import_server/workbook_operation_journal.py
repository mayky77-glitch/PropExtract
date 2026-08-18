"""Durable, generic workbook publication operation journal.

The journal knows no Excel implementation details.  It records enough stable
identity and hash evidence for a later consumer to decide whether it may
finalize a publication, revalidate from pre-hash, or require manual repair.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import sqlite3
from typing import Any, Mapping

from rns_import_server.registry_storage import RegistryConflictError, RegistryError, RegistryStorage


PHASE_PLANNED = "planned"
PHASE_STAGED = "staged"
# These are a publication boundary, not an adapter implementation detail.  A
# native helper may not open a workbook until its exact process identities are
# in ``excel_owned`` and the journal authorizes its nonce-bound ACK.
PHASE_EXCEL_LAUNCHING = "excel_launching"
PHASE_EXCEL_OWNED = "excel_owned"
PHASE_NATIVE = "native"
PHASE_VALIDATED = "validated"
PHASE_BACKUP_VERIFIED = "backup_verified"
PHASE_PUBLISHED = "published"
PHASE_FINALIZED = "finalized"
PHASE_MANUAL_REPAIR = "manual_repair"

LEGAL_TRANSITIONS = {
    PHASE_PLANNED: {PHASE_STAGED, PHASE_MANUAL_REPAIR},
    # ``staged -> native`` remains for the existing generic v1/v2 consumer.
    # New Excel-native callers must use the two durable lease phases below.
    PHASE_STAGED: {PHASE_EXCEL_LAUNCHING, PHASE_NATIVE, PHASE_VALIDATED, PHASE_MANUAL_REPAIR},
    PHASE_EXCEL_LAUNCHING: {PHASE_EXCEL_OWNED, PHASE_MANUAL_REPAIR},
    PHASE_EXCEL_OWNED: {PHASE_NATIVE, PHASE_MANUAL_REPAIR},
    PHASE_NATIVE: {PHASE_VALIDATED, PHASE_MANUAL_REPAIR},
    PHASE_VALIDATED: {PHASE_BACKUP_VERIFIED, PHASE_MANUAL_REPAIR},
    PHASE_BACKUP_VERIFIED: {PHASE_PUBLISHED, PHASE_MANUAL_REPAIR},
    PHASE_PUBLISHED: {PHASE_FINALIZED, PHASE_MANUAL_REPAIR},
    PHASE_FINALIZED: set(),
    PHASE_MANUAL_REPAIR: set(),
}
FINALIZATION_FLAGS = frozenset({
    "capability_finalized", "binding_finalized", "history_finalized", "report_finalized",
})
_HASH_FIELDS = frozenset({"pre_hash", "staged_hash", "control_hash", "post_hash", "backup_hash", "validation_digest"})
_PHASE_TIMESTAMPS = {
    PHASE_STAGED: "staged_at",
    PHASE_VALIDATED: "validated_at",
    PHASE_BACKUP_VERIFIED: "backup_verified_at",
    PHASE_PUBLISHED: "published_at",
    PHASE_FINALIZED: "finalized_at",
}
_LEGACY_EXCEL_LEASE_FIELDS = frozenset({
    "excel_adapter", "excel_pid", "excel_hwnd", "excel_process_started_at", "excel_build",
})
_ADAPTER_LEASE_FIELDS = frozenset({"excel_adapter", "adapter_pid", "adapter_image", "adapter_process_started_at"})
_EXCEL_LEASE_FIELDS = frozenset({"excel_pid", "excel_hwnd", "excel_image", "excel_process_started_at", "excel_build"})
_V3_LEASE_FIELDS = _ADAPTER_LEASE_FIELDS | _EXCEL_LEASE_FIELDS
_FAILURE_FIELDS = frozenset({"stage", "code", "message", "hresult", "winerror"})


class JournalTransitionError(RegistryConflictError):
    pass


@dataclass(frozen=True)
class JournalOperation:
    values: Mapping[str, Any]

    @property
    def operation_id(self) -> str:
        return str(self.values["operation_id"])

    @property
    def phase(self) -> str:
        return str(self.values["phase"])

    def __getitem__(self, key: str) -> Any:
        return self.values[key]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _positive_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise RegistryError(f"Excel lease field {field} имеет неверный формат")
    return value


def _nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RegistryError(f"Excel lease field {field} имеет неверный формат")
    return value


def _image_name(value: object, field: str) -> str:
    return _nonempty_text(value, field).replace("\\", "/").rsplit("/", 1)[-1].upper()


def _validate_adapter_lease(lease: Mapping[str, object]) -> None:
    if set(lease) != _ADAPTER_LEASE_FIELDS:
        raise RegistryError("Launching lease требует только полный adapter identity")
    _nonempty_text(lease["excel_adapter"], "excel_adapter")
    _positive_int(lease["adapter_pid"], "adapter_pid")
    _image_name(lease["adapter_image"], "adapter_image")
    _nonempty_text(lease["adapter_process_started_at"], "adapter_process_started_at")


def _validate_owned_lease(lease: Mapping[str, object]) -> None:
    if set(lease) != _V3_LEASE_FIELDS:
        raise RegistryError("Owned lease требует полный adapter и Excel identity")
    _validate_adapter_lease({key: lease[key] for key in _ADAPTER_LEASE_FIELDS})
    _positive_int(lease["excel_pid"], "excel_pid")
    _positive_int(lease["excel_hwnd"], "excel_hwnd")
    if _image_name(lease["excel_image"], "excel_image") != "EXCEL.EXE":
        raise RegistryError("Owned lease требует image EXCEL.EXE")
    _nonempty_text(lease["excel_process_started_at"], "excel_process_started_at")
    _nonempty_text(lease["excel_build"], "excel_build")


def _normalize_failure(value: Mapping[str, object] | None, *, fallback_stage: str, fallback_code: str | None) -> dict[str, object] | None:
    if value is None:
        if fallback_code is None:
            return None
        value = {"stage": fallback_stage, "code": fallback_code, "message": fallback_code}
    if set(value) - _FAILURE_FIELDS:
        raise RegistryError("Неизвестное поле structured failure")
    stage = value.get("stage")
    code = value.get("code")
    if not isinstance(stage, str) or not stage or not isinstance(code, str) or not code:
        raise RegistryError("Structured failure требует stage и code")
    message = value.get("message")
    if message is not None and (not isinstance(message, str) or not message):
        raise RegistryError("Structured failure message имеет неверный формат")
    normalized: dict[str, object] = {"stage": stage, "code": code, "message": message}
    for key in ("hresult", "winerror"):
        item = value.get(key)
        if item is not None and (not isinstance(item, int) or isinstance(item, bool)):
            raise RegistryError(f"Structured failure {key} имеет неверный формат")
        normalized[key] = item
    return normalized


class WorkbookOperationJournal:
    """CAS journal backed by a :class:`RegistryStorage` runtime database."""

    def __init__(self, storage: RegistryStorage):
        self.storage = storage

    def get(self, operation_id: str) -> JournalOperation | None:
        row = self.storage.connection.execute(
            "SELECT * FROM workbook_operation_journal WHERE operation_id=?", (operation_id,)
        ).fetchone()
        return JournalOperation(dict(row)) if row else None

    @staticmethod
    def _lease_matches(operation: JournalOperation, lease: Mapping[str, object]) -> bool:
        return all(operation[key] == value for key, value in lease.items())

    @staticmethod
    def _assert_nonce(operation: JournalOperation, *, owner_id: str, pair_nonce: str) -> None:
        if operation["owner_id"] != owner_id or operation["pair_nonce"] != pair_nonce:
            raise RegistryConflictError("Excel lease nonce не совпадает с immutable operation")

    def _record_lease(
        self,
        operation_id: str,
        *,
        owner_id: str,
        pair_nonce: str,
        expected_phase: str,
        next_phase: str,
        lease: Mapping[str, object],
    ) -> JournalOperation:
        """CAS-write one lease boundary, allowing only exact replay.

        The operation/owner/pair tuple is checked in the UPDATE itself, so a
        stale reader cannot turn another operation's lease into ownership.
        """
        current = self.get(operation_id)
        if current is None:
            raise JournalTransitionError("Operation не найдена или её фаза уже изменилась")
        self._assert_nonce(current, owner_id=owner_id, pair_nonce=pair_nonce)
        if current.phase == next_phase:
            if self._lease_matches(current, lease):
                return current
            raise RegistryConflictError("Повтор Excel lease не совпадает с durable identity")
        if current.phase != expected_phase:
            raise JournalTransitionError("Operation не найдена или её фаза уже изменилась")
        assignments = ["phase=?", "updated_at=?"] + [f"{field}=?" for field in lease]
        values: list[object] = [next_phase, _now(), *lease.values(), operation_id, owner_id, pair_nonce, expected_phase]
        self.storage.connection.execute("PRAGMA synchronous=FULL")
        with self.storage.transaction() as connection:
            updated = connection.execute(
                f"UPDATE workbook_operation_journal SET {', '.join(assignments)} "
                "WHERE operation_id=? AND owner_id=? AND pair_nonce=? AND phase=?",
                values,
            ).rowcount
            if updated != 1:
                raise JournalTransitionError("Operation не найдена или её фаза уже изменилась")
        return self.get(operation_id)  # type: ignore[return-value]

    def record_excel_launching(
        self, operation_id: str, *, owner_id: str, pair_nonce: str, lease: Mapping[str, object]
    ) -> JournalOperation:
        """Durably bind the helper adapter before it can create Excel."""
        _validate_adapter_lease(lease)
        return self._record_lease(operation_id, owner_id=owner_id, pair_nonce=pair_nonce,
                                  expected_phase=PHASE_STAGED, next_phase=PHASE_EXCEL_LAUNCHING, lease=lease)

    # Semantic aliases keep the boundary discoverable for adapter consumers.
    begin_excel_lease = record_excel_launching

    def record_excel_owned(
        self, operation_id: str, *, owner_id: str, pair_nonce: str, lease: Mapping[str, object]
    ) -> JournalOperation:
        """Durably prove complete process identity before an ACK is possible."""
        _validate_owned_lease(lease)
        return self._record_lease(operation_id, owner_id=owner_id, pair_nonce=pair_nonce,
                                  expected_phase=PHASE_EXCEL_LAUNCHING, next_phase=PHASE_EXCEL_OWNED, lease=lease)

    confirm_excel_ownership = record_excel_owned

    def authorize_excel_ack(self, operation_id: str, *, owner_id: str, pair_nonce: str) -> JournalOperation:
        """Return the durable ownership evidence that authorizes a helper ACK."""
        operation = self.get(operation_id)
        if operation is None:
            raise JournalTransitionError("Operation не найдена или её фаза уже изменилась")
        self._assert_nonce(operation, owner_id=owner_id, pair_nonce=pair_nonce)
        if operation.phase != PHASE_EXCEL_OWNED:
            raise JournalTransitionError("Excel ACK разрешён только после durable excel_owned")
        _validate_owned_lease({key: operation[key] for key in _V3_LEASE_FIELDS})
        return operation

    issue_excel_ack = authorize_excel_ack

    def create(
        self,
        *,
        operation_id: str,
        idempotency_key: str,
        consumer_id: str,
        owner_id: str,
        pair_nonce: str,
        construction_id: str,
        operation_kind: str,
        mutation_mode: str,
        target_identity: str,
        sheet_identity: str,
        template_version: str,
        expected_generation: int,
        intent_version: str,
        intent_digest: str,
        manifest_version: str,
        manifest_digest: str,
        operation_directory: str,
        canonical_rns: str | None = None,
    ) -> JournalOperation:
        required = {
            "operation_id": operation_id, "idempotency_key": idempotency_key, "consumer_id": consumer_id,
            "owner_id": owner_id, "pair_nonce": pair_nonce, "construction_id": construction_id,
            "target_identity": target_identity, "sheet_identity": sheet_identity,
            "template_version": template_version, "intent_version": intent_version, "intent_digest": intent_digest,
            "manifest_version": manifest_version, "manifest_digest": manifest_digest,
            "operation_directory": operation_directory,
        }
        if any(not isinstance(value, str) or not value for value in required.values()):
            raise RegistryError("Journal operation требует все стабильные идентификаторы и digest")
        if operation_kind not in {"group_provision", "new_row"}:
            raise RegistryError("Неподдерживаемый тип workbook operation")
        if mutation_mode not in {"bootstrap_fill", "blank_fill", "middle_insert"}:
            raise RegistryError("Неподдерживаемый режим workbook mutation")
        if operation_kind == "new_row" and not canonical_rns:
            raise RegistryError("Операция новой строки требует canonical RNS")
        immutable = {
            "operation_id": operation_id, "idempotency_key": idempotency_key, "consumer_id": consumer_id,
            "owner_id": owner_id, "pair_nonce": pair_nonce, "construction_id": construction_id,
            "canonical_rns": canonical_rns, "operation_kind": operation_kind, "mutation_mode": mutation_mode,
            "target_identity": target_identity, "sheet_identity": sheet_identity, "template_version": template_version,
            "expected_generation": expected_generation, "intent_version": intent_version, "intent_digest": intent_digest,
            "manifest_version": manifest_version, "manifest_digest": manifest_digest, "operation_directory": operation_directory,
        }
        with self.storage.transaction() as connection:
            collisions = connection.execute(
                "SELECT * FROM workbook_operation_journal "
                "WHERE operation_id=? OR idempotency_key=? OR consumer_id=?",
                (operation_id, idempotency_key, consumer_id),
            ).fetchall()
            if collisions:
                if len(collisions) == 1 and all(collisions[0][key] == value for key, value in immutable.items()):
                    return JournalOperation(dict(collisions[0]))
                raise RegistryConflictError("Повтор journal operation не совпадает с исходным immutable intent")
            if expected_generation != self.storage.generation:
                raise RegistryConflictError("Справочник изменился до планирования операции")
            try:
                connection.execute(
                    """INSERT INTO workbook_operation_journal(
                       operation_id,idempotency_key,consumer_id,owner_id,pair_nonce,construction_id,canonical_rns,
                       operation_kind,mutation_mode,target_identity,sheet_identity,template_version,expected_generation,
                       intent_version,intent_digest,manifest_version,manifest_digest,operation_directory,phase,created_at,updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'planned', ?, ?)""",
                    (operation_id, idempotency_key, consumer_id, owner_id, pair_nonce, construction_id, canonical_rns,
                     operation_kind, mutation_mode, target_identity, sheet_identity, template_version, expected_generation,
                     intent_version, intent_digest, manifest_version, manifest_digest, operation_directory, _now(), _now()),
                )
            except sqlite3.IntegrityError as error:
                collisions = connection.execute(
                    "SELECT * FROM workbook_operation_journal WHERE operation_id=? OR idempotency_key=? OR consumer_id=?",
                    (operation_id, idempotency_key, consumer_id),
                ).fetchall()
                if len(collisions) == 1 and all(collisions[0][key] == value for key, value in immutable.items()):
                    return JournalOperation(dict(collisions[0]))
                raise RegistryConflictError("Повтор journal operation не совпадает с исходным immutable intent") from error
        return self.get(operation_id)  # type: ignore[return-value]

    def transition(
        self,
        operation_id: str,
        *,
        expected_phase: str,
        next_phase: str,
        failure_code: str | None = None,
        primary_failure: Mapping[str, object] | None = None,
        cleanup_failure: Mapping[str, object] | None = None,
        hashes: Mapping[str, str] | None = None,
        excel_lease: Mapping[str, object] | None = None,
    ) -> JournalOperation:
        if next_phase not in LEGAL_TRANSITIONS.get(expected_phase, set()):
            raise JournalTransitionError(f"Недопустимый переход journal: {expected_phase} → {next_phase}")
        hashes = hashes or {}
        if set(hashes) - _HASH_FIELDS or any(not isinstance(value, str) or not value for value in hashes.values()):
            raise RegistryError("Journal hashes имеют неверный формат")
        if failure_code is not None and (not isinstance(failure_code, str) or not failure_code):
            raise RegistryError("Journal failure code имеет неверный формат")
        primary = _normalize_failure(primary_failure, fallback_stage=expected_phase, fallback_code=failure_code)
        cleanup = _normalize_failure(cleanup_failure, fallback_stage=expected_phase, fallback_code=None)
        current = self.get(operation_id)
        if current is None or current.phase != expected_phase:
            raise JournalTransitionError("Operation не найдена или её фаза уже изменилась")
        if next_phase == PHASE_STAGED and not {"pre_hash", "staged_hash"}.issubset(hashes):
            raise RegistryError("Staged operation требует pre_hash и staged_hash до внешней публикации")
        if next_phase == PHASE_PUBLISHED:
            if hashes.get("post_hash") or not current["post_hash"]:
                raise RegistryError("Published CAS использует только заранее durable post_hash")
        if next_phase == PHASE_BACKUP_VERIFIED and not hashes.get("backup_hash"):
            raise RegistryError("До publication необходим verified backup hash")
        if next_phase == PHASE_VALIDATED and not hashes.get("validation_digest"):
            raise RegistryError("Validated operation требует validation digest")
        if next_phase == PHASE_VALIDATED and current["mutation_mode"] == "middle_insert":
            lease = {"excel_adapter", "excel_pid", "excel_hwnd", "excel_process_started_at", "excel_build"}
            persisted = {name: current[name] for name in lease}
            persisted.update(excel_lease or {})
            control_hash = hashes.get("control_hash") or current["control_hash"]
            if not control_hash or any(persisted[name] in {None, ""} for name in lease):
                raise RegistryError("Native mutation требует Excel lease и control_hash до validation")
        if next_phase == PHASE_MANUAL_REPAIR and primary is None:
            raise RegistryError("Manual repair требует durable failure code")
        if next_phase == PHASE_FINALIZED and not all(current[flag] for flag in FINALIZATION_FLAGS):
            raise RegistryError("Finalized operation требует все finalization flags")
        lease_fields = _LEGACY_EXCEL_LEASE_FIELDS | _V3_LEASE_FIELDS
        if excel_lease and set(excel_lease) - lease_fields:
            raise RegistryError("Неизвестное поле Excel lease")
        if next_phase == PHASE_EXCEL_LAUNCHING:
            if expected_phase != PHASE_STAGED or excel_lease is None:
                raise RegistryError("excel_launching требует staged CAS и adapter identity")
            _validate_adapter_lease(excel_lease)
        if next_phase == PHASE_EXCEL_OWNED:
            if expected_phase != PHASE_EXCEL_LAUNCHING or excel_lease is None:
                raise RegistryError("excel_owned требует excel_launching CAS и полный identity")
            _validate_owned_lease(excel_lease)
        assignments = ["phase=?", "failure_code=?", "updated_at=?"]
        values: list[object] = [next_phase, primary["code"] if primary else failure_code, _now()]
        timestamp = _PHASE_TIMESTAMPS.get(next_phase)
        if timestamp:
            assignments.append(f"{timestamp}=?")
            values.append(_now())
        for key, value in hashes.items():
            assignments.append(f"{key}=?")
            values.append(value)
        for key, value in (excel_lease or {}).items():
            assignments.append(f"{key}=?")
            values.append(value)
        for prefix, failure in (("primary_failure", primary), ("cleanup_failure", cleanup)):
            if failure is None:
                continue
            for field, value in failure.items():
                assignments.append(f"{prefix}_{field}=?")
                values.append(value)
        values.extend([operation_id, expected_phase])
        # Set this outside the transaction; SQLite rejects changing safety
        # level after BEGIN.  It is also the storage default, but making it
        # explicit guards an embedding consumer that changed the connection.
        self.storage.connection.execute("PRAGMA synchronous=FULL")
        with self.storage.transaction() as connection:
            updated = connection.execute(
                f"UPDATE workbook_operation_journal SET {', '.join(assignments)} "
                "WHERE operation_id=? AND phase=?",
                values,
            ).rowcount
            if updated != 1:
                raise JournalTransitionError("Operation не найдена или её фаза уже изменилась")
        return self.get(operation_id)  # type: ignore[return-value]

    def record_failure(
        self,
        operation_id: str,
        *,
        expected_phase: str,
        primary_failure: Mapping[str, object],
        cleanup_failure: Mapping[str, object] | None = None,
    ) -> JournalOperation:
        """Move to repair with primary/cleanup diagnostics kept separately.

        The first primary cause is immutable recovery evidence.  A cleanup
        error can be added later, but cannot replace the original failure.
        """
        primary = _normalize_failure(primary_failure, fallback_stage=expected_phase, fallback_code=None)
        cleanup = _normalize_failure(cleanup_failure, fallback_stage=expected_phase, fallback_code=None)
        assert primary is not None
        current = self.get(operation_id)
        if current is None:
            raise JournalTransitionError("Operation не найдена или её фаза уже изменилась")
        if current.phase == PHASE_MANUAL_REPAIR:
            persisted = {field.removeprefix("primary_failure_"): current[field] for field in (
                "primary_failure_stage", "primary_failure_code", "primary_failure_message",
                "primary_failure_hresult", "primary_failure_winerror",
            )}
            if persisted != primary:
                raise RegistryConflictError("Primary failure уже записан и не может быть заменён")
            return self.record_cleanup_failure(operation_id, cleanup_failure=cleanup) if cleanup else current
        return self.transition(
            operation_id, expected_phase=expected_phase, next_phase=PHASE_MANUAL_REPAIR,
            primary_failure=primary, cleanup_failure=cleanup,
        )

    record_structured_failure = record_failure

    def record_cleanup_failure(
        self,
        operation_id: str,
        *,
        cleanup_failure: Mapping[str, object],
        expected_phase: str | None = None,
    ) -> JournalOperation:
        """Add cleanup diagnostics without altering primary failure evidence."""
        cleanup = _normalize_failure(cleanup_failure, fallback_stage=expected_phase or "cleanup", fallback_code=None)
        assert cleanup is not None
        current = self.get(operation_id)
        if current is None or (expected_phase is not None and current.phase != expected_phase):
            raise JournalTransitionError("Operation не найдена или её фаза уже изменилась")
        existing = {field.removeprefix("cleanup_failure_"): current[field] for field in (
            "cleanup_failure_stage", "cleanup_failure_code", "cleanup_failure_message",
            "cleanup_failure_hresult", "cleanup_failure_winerror",
        )}
        if any(value is not None for value in existing.values()):
            if existing == cleanup:
                return current
            raise RegistryConflictError("Cleanup failure уже записан и не может быть заменён")
        assignments = [f"cleanup_failure_{field}=?" for field in cleanup] + ["updated_at=?"]
        values: list[object] = [*cleanup.values(), _now(), operation_id]
        where = "operation_id=?"
        if expected_phase is not None:
            where += " AND phase=?"
            values.append(expected_phase)
        self.storage.connection.execute("PRAGMA synchronous=FULL")
        with self.storage.transaction() as connection:
            updated = connection.execute(
                f"UPDATE workbook_operation_journal SET {', '.join(assignments)} WHERE {where}", values
            ).rowcount
            if updated != 1:
                raise JournalTransitionError("Operation не найдена или её фаза уже изменилась")
        return self.get(operation_id)  # type: ignore[return-value]

    def record_post_hash(self, operation_id: str, *, expected_phase: str, post_hash: str) -> JournalOperation:
        """Commit post-publication evidence before the caller may replace XLSX."""
        if expected_phase != PHASE_BACKUP_VERIFIED or not isinstance(post_hash, str) or not post_hash:
            raise RegistryError("post_hash допускается только после verified backup")
        self.storage.connection.execute("PRAGMA synchronous=FULL")
        with self.storage.transaction() as connection:
            updated = connection.execute(
                "UPDATE workbook_operation_journal SET post_hash=?, updated_at=? "
                "WHERE operation_id=? AND phase=? AND post_hash IS NULL",
                (post_hash, _now(), operation_id, expected_phase),
            ).rowcount
            if updated != 1:
                raise JournalTransitionError("post_hash уже записан или operation изменилась")
        return self.get(operation_id)  # type: ignore[return-value]

    def finalize_flag(self, operation_id: str, flag: str) -> JournalOperation:
        if flag not in FINALIZATION_FLAGS:
            raise RegistryError("Неизвестный флаг finalization")
        with self.storage.transaction() as connection:
            current = connection.execute(
                f"SELECT phase, {flag}, {flag}_at FROM workbook_operation_journal WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if not current:
                raise RegistryError("Operation не найдена")
            # A completed flag is durable evidence. Replays must not alter its
            # first timestamp, including after a restart/finalized transition.
            if current[flag]:
                return self.get(operation_id)  # type: ignore[return-value]
            if current["phase"] != PHASE_PUBLISHED:
                raise JournalTransitionError("Finalization flag разрешён только после publication")
            updated = connection.execute(
                f"UPDATE workbook_operation_journal SET {flag}=1, {flag}_at=?, updated_at=? WHERE operation_id=?",
                (_now(), _now(), operation_id),
            ).rowcount
            if updated != 1:
                raise RegistryError("Operation не найдена")
        return self.get(operation_id)  # type: ignore[return-value]

    def incomplete(self) -> list[JournalOperation]:
        rows = self.storage.connection.execute(
            "SELECT * FROM workbook_operation_journal WHERE phase != 'finalized' ORDER BY created_at"
        )
        return [JournalOperation(dict(row)) for row in rows]
