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
PHASE_NATIVE = "native"
PHASE_VALIDATED = "validated"
PHASE_BACKUP_VERIFIED = "backup_verified"
PHASE_PUBLISHED = "published"
PHASE_FINALIZED = "finalized"
PHASE_MANUAL_REPAIR = "manual_repair"

LEGAL_TRANSITIONS = {
    PHASE_PLANNED: {PHASE_STAGED, PHASE_MANUAL_REPAIR},
    PHASE_STAGED: {PHASE_NATIVE, PHASE_MANUAL_REPAIR},
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


class WorkbookOperationJournal:
    """CAS journal backed by a :class:`RegistryStorage` runtime database."""

    def __init__(self, storage: RegistryStorage):
        self.storage = storage

    def get(self, operation_id: str) -> JournalOperation | None:
        row = self.storage.connection.execute(
            "SELECT * FROM workbook_operation_journal WHERE operation_id=?", (operation_id,)
        ).fetchone()
        return JournalOperation(dict(row)) if row else None

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
        with self.storage.transaction() as connection:
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
                existing = connection.execute(
                    "SELECT operation_id FROM workbook_operation_journal WHERE idempotency_key=?", (idempotency_key,)
                ).fetchone()
                if existing and existing["operation_id"] == operation_id:
                    return self.get(operation_id)  # type: ignore[return-value]
                raise RegistryConflictError("operation/idempotency/consumer ID уже использован") from error
        return self.get(operation_id)  # type: ignore[return-value]

    def transition(
        self,
        operation_id: str,
        *,
        expected_phase: str,
        next_phase: str,
        failure_code: str | None = None,
        hashes: Mapping[str, str] | None = None,
        excel_lease: Mapping[str, object] | None = None,
    ) -> JournalOperation:
        if next_phase not in LEGAL_TRANSITIONS.get(expected_phase, set()):
            raise JournalTransitionError(f"Недопустимый переход journal: {expected_phase} → {next_phase}")
        hashes = hashes or {}
        if set(hashes) - _HASH_FIELDS or any(not isinstance(value, str) or not value for value in hashes.values()):
            raise RegistryError("Journal hashes имеют неверный формат")
        if next_phase == PHASE_PUBLISHED and not hashes.get("post_hash"):
            raise RegistryError("До publication необходим durable post-hash")
        if next_phase == PHASE_BACKUP_VERIFIED and not hashes.get("backup_hash"):
            raise RegistryError("До publication необходим verified backup hash")
        if next_phase == PHASE_VALIDATED and not hashes.get("validation_digest"):
            raise RegistryError("Validated operation требует validation digest")
        lease_fields = {"excel_adapter", "excel_pid", "excel_hwnd", "excel_process_started_at", "excel_build"}
        if excel_lease and set(excel_lease) - lease_fields:
            raise RegistryError("Неизвестное поле Excel lease")
        assignments = ["phase=?", "failure_code=?", "updated_at=?"]
        values: list[object] = [next_phase, failure_code, _now()]
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

    def finalize_flag(self, operation_id: str, flag: str) -> JournalOperation:
        if flag not in FINALIZATION_FLAGS:
            raise RegistryError("Неизвестный флаг finalization")
        with self.storage.transaction() as connection:
            updated = connection.execute(
                f"UPDATE workbook_operation_journal SET {flag}=1, updated_at=? WHERE operation_id=?",
                (_now(), operation_id),
            ).rowcount
            if updated != 1:
                raise RegistryError("Operation не найдена")
        return self.get(operation_id)  # type: ignore[return-value]

    def incomplete(self) -> list[JournalOperation]:
        rows = self.storage.connection.execute(
            "SELECT * FROM workbook_operation_journal WHERE phase NOT IN ('finalized', 'manual_repair') ORDER BY created_at"
        )
        return [JournalOperation(dict(row)) for row in rows]
