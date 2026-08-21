"""Durable, generic workbook publication operation journal.

The journal knows no Excel implementation details.  It records enough stable
identity and hash evidence for a later consumer to decide whether it may
finalize a publication, revalidate from pre-hash, or require manual repair.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
import sqlite3
from typing import Any, Callable, Mapping

from rns_import_server.excel_process_authority import ExcelProcessLease
from rns_import_server.registry_storage import RegistryConflictError, RegistryError, RegistryStorage
from rns_import_server.workbook_finalization_snapshot import FinalizationSnapshotError, validate_payload, verify_snapshot


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
    PHASE_STAGED: {PHASE_NATIVE, PHASE_VALIDATED, PHASE_MANUAL_REPAIR},
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
_REPAIR_FAILURE_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}")
_PHASE_TIMESTAMPS = {
    PHASE_STAGED: "staged_at",
    PHASE_VALIDATED: "validated_at",
    PHASE_BACKUP_VERIFIED: "backup_verified_at",
    PHASE_PUBLISHED: "published_at",
    PHASE_FINALIZED: "finalized_at",
}


class JournalTransitionError(RegistryConflictError):
    pass


class JournalStorageError(RegistryError):
    """A SQLite failure at the durable journal boundary."""


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

    def reserve(
        self,
        *,
        nonce_factory: Callable[[], tuple[str, str]],
        operation_id: str,
        idempotency_key: str,
        consumer_id: str,
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
        workbook_contract_id: str | None = None,
    ) -> tuple[JournalOperation, bool]:
        """Atomically return an existing authority or create its nonce pair once."""
        required = {
            "operation_id": operation_id, "idempotency_key": idempotency_key, "consumer_id": consumer_id,
            "construction_id": construction_id, "target_identity": target_identity,
            "sheet_identity": sheet_identity, "template_version": template_version,
            "intent_version": intent_version, "intent_digest": intent_digest,
            "manifest_version": manifest_version, "manifest_digest": manifest_digest,
            "operation_directory": operation_directory,
        }
        if any(not isinstance(value, str) or not value for value in required.values()):
            raise RegistryError("Journal operation требует все стабильные идентификаторы и digest")
        if operation_kind not in {"group_provision", "new_row"}:
            raise RegistryError("Неподдерживаемый тип workbook operation")
        if mutation_mode not in {"bootstrap_fill", "blank_fill", "middle_insert"}:
            raise RegistryError("Неподдерживаемый режим workbook mutation")
        immutable = {
            **required,
            "canonical_rns": canonical_rns,
            "operation_kind": operation_kind,
            "mutation_mode": mutation_mode,
            "expected_generation": expected_generation,
            "workbook_contract_id": workbook_contract_id,
        }
        self.storage.connection.execute("PRAGMA synchronous=FULL")
        created = False
        with self.storage.transaction() as connection:
            collisions = connection.execute(
                "SELECT * FROM workbook_operation_journal "
                "WHERE operation_id=? OR idempotency_key=? OR consumer_id=?",
                (operation_id, idempotency_key, consumer_id),
            ).fetchall()
            if collisions:
                if (
                    len(collisions) == 1
                    and all(collisions[0][key] == value for key, value in immutable.items())
                    and all(isinstance(collisions[0][key], str) and collisions[0][key] for key in ("owner_id", "pair_nonce"))
                ):
                    return JournalOperation(dict(collisions[0])), False
                raise RegistryConflictError("Повтор journal operation не совпадает с исходным immutable intent")
            if operation_kind == "new_row" and (not canonical_rns or not isinstance(workbook_contract_id, str) or not workbook_contract_id.strip()):
                raise RegistryError("workbook_contract_id_required")
            if operation_kind == "new_row" and consumer_id != operation_id:
                raise RegistryError("consumer_action_identity_mismatch")
            if expected_generation != self.storage.generation:
                raise RegistryConflictError("Справочник изменился до планирования операции")
            owner_id, pair_nonce = nonce_factory()
            if any(not isinstance(value, str) or not value for value in (owner_id, pair_nonce)):
                raise RegistryError("Journal nonce имеет неверный формат")
            connection.execute(
                """INSERT INTO workbook_operation_journal(
                   operation_id,idempotency_key,consumer_id,owner_id,pair_nonce,construction_id,canonical_rns,workbook_contract_id,
                   operation_kind,mutation_mode,target_identity,sheet_identity,template_version,expected_generation,
                   intent_version,intent_digest,manifest_version,manifest_digest,operation_directory,phase,created_at,updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'planned', ?, ?)""",
                (operation_id, idempotency_key, consumer_id, owner_id, pair_nonce, construction_id, canonical_rns, workbook_contract_id,
                 operation_kind, mutation_mode, target_identity, sheet_identity, template_version, expected_generation,
                 intent_version, intent_digest, manifest_version, manifest_digest, operation_directory, _now(), _now()),
            )
            created = True
        operation = self.get(operation_id)
        if operation is None:
            raise RegistryError("Journal operation не найдена после durable reservation")
        return operation, created

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
        workbook_contract_id: str | None = None,
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
        immutable = {
            "operation_id": operation_id, "idempotency_key": idempotency_key, "consumer_id": consumer_id,
            "owner_id": owner_id, "pair_nonce": pair_nonce, "construction_id": construction_id,
            "canonical_rns": canonical_rns, "workbook_contract_id": workbook_contract_id, "operation_kind": operation_kind, "mutation_mode": mutation_mode,
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
            if operation_kind == "new_row" and (not canonical_rns or not isinstance(workbook_contract_id, str) or not workbook_contract_id.strip()):
                raise RegistryError("workbook_contract_id_required")
            if operation_kind == "new_row" and consumer_id != operation_id:
                raise RegistryError("consumer_action_identity_mismatch")
            if expected_generation != self.storage.generation:
                raise RegistryConflictError("Справочник изменился до планирования операции")
            try:
                connection.execute(
                    """INSERT INTO workbook_operation_journal(
                       operation_id,idempotency_key,consumer_id,owner_id,pair_nonce,construction_id,canonical_rns,workbook_contract_id,
                       operation_kind,mutation_mode,target_identity,sheet_identity,template_version,expected_generation,
                       intent_version,intent_digest,manifest_version,manifest_digest,operation_directory,phase,created_at,updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'planned', ?, ?)""",
                    (operation_id, idempotency_key, consumer_id, owner_id, pair_nonce, construction_id, canonical_rns, workbook_contract_id,
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
        hashes: Mapping[str, str] | None = None,
        excel_lease: ExcelProcessLease | None = None,
    ) -> JournalOperation:
        if next_phase == PHASE_FINALIZED:
            # Finalization is a compound external/durable protocol.  A
            # generic phase switch can neither prove the report bytes nor the
            # consumed action capability, so only workbook_finalization owns
            # this terminal CAS.
            raise RegistryError("finalization_receipt_required")
        if next_phase not in LEGAL_TRANSITIONS.get(expected_phase, set()):
            raise JournalTransitionError(f"Недопустимый переход journal: {expected_phase} → {next_phase}")
        hashes = hashes or {}
        if set(hashes) - _HASH_FIELDS or any(not isinstance(value, str) or not value for value in hashes.values()):
            raise RegistryError("Journal hashes имеют неверный формат")
        current = self.get(operation_id)
        if current is None or current.phase != expected_phase:
            raise JournalTransitionError("Operation не найдена или её фаза уже изменилась")
        if next_phase == PHASE_STAGED and not {"pre_hash", "staged_hash"}.issubset(hashes):
            raise RegistryError("Staged operation требует pre_hash и staged_hash до внешней публикации")
        if next_phase == PHASE_PUBLISHED:
            if hashes.get("post_hash") or not current["post_hash"]:
                raise RegistryError("Published CAS использует только заранее durable post_hash")
            snapshot = self.storage.connection.execute(
                "SELECT snapshot_version, canonical_payload, digest FROM workbook_finalization_snapshots WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if snapshot is None:
                raise RegistryError("finalization_snapshot_required")
            if not verify_snapshot(operation_id=operation_id, consumer_id=current["consumer_id"],
                                   workbook_contract_id=current["workbook_contract_id"], post_hash=current["post_hash"],
                                   snapshot_version=snapshot["snapshot_version"],
                                   canonical_payload=snapshot["canonical_payload"], digest=snapshot["digest"]):
                raise RegistryError("finalization_snapshot_invalid")
        if next_phase == PHASE_BACKUP_VERIFIED and not hashes.get("backup_hash"):
            raise RegistryError("До publication необходим verified backup hash")
        if next_phase == PHASE_VALIDATED and not hashes.get("validation_digest"):
            raise RegistryError("Validated operation требует validation digest")
        lease_fields = {
            "excel_adapter", "excel_adapter_pid", "excel_adapter_started_at", "excel_pid", "excel_hwnd",
            "excel_process_started_at", "excel_build",
        }
        if excel_lease is not None:
            if type(excel_lease) is not ExcelProcessLease:
                raise RegistryError("Excel lease имеет неподдерживаемый формат")
            if next_phase != PHASE_NATIVE or expected_phase != PHASE_STAGED:
                raise RegistryError("Excel lease допускается только при staged → native")
            if (excel_lease.operation_id, excel_lease.owner_id, excel_lease.pair_nonce) != (
                current["operation_id"], current["owner_id"], current["pair_nonce"],
            ):
                raise RegistryError("Excel lease не соответствует authority journal operation")
            lease_values = {
                "excel_adapter": excel_lease.adapter_type,
                "excel_adapter_pid": excel_lease.adapter_pid,
                "excel_adapter_started_at": excel_lease.adapter_started_at,
                "excel_pid": excel_lease.excel_pid,
                "excel_hwnd": excel_lease.excel_hwnd,
                "excel_process_started_at": excel_lease.excel_process_started_at,
                "excel_build": excel_lease.excel_build,
            }
            if (set(lease_values) != lease_fields or lease_values["excel_adapter"] != "com"
                    or not isinstance(lease_values["excel_adapter_started_at"], str)
                    or not isinstance(lease_values["excel_process_started_at"], str)
                    or not isinstance(lease_values["excel_build"], str)
                    or any(not isinstance(lease_values[name], int) or isinstance(lease_values[name], bool)
                           or lease_values[name] <= 0 for name in ("excel_adapter_pid", "excel_pid", "excel_hwnd"))):
                raise RegistryError("Excel lease имеет неполную durable projection")
        else:
            lease_values = {}
        if next_phase == PHASE_NATIVE and current["mutation_mode"] in {"middle_insert", "blank_fill"} and not excel_lease:
            raise RegistryError("Native mutation требует полный Excel lease до открытия workbook")
        if next_phase == PHASE_VALIDATED and current["mutation_mode"] == "middle_insert":
            control_hash = hashes.get("control_hash") or current["control_hash"]
            if not control_hash or any(current[name] in {None, ""} for name in lease_fields):
                raise RegistryError("Native mutation требует Excel lease и control_hash до validation")
        if next_phase == PHASE_MANUAL_REPAIR and not failure_code:
            raise RegistryError("Manual repair требует durable failure code")
        if next_phase == PHASE_FINALIZED and not all(current[flag] for flag in FINALIZATION_FLAGS):
            raise RegistryError("Finalized operation требует все finalization flags")
        assignments = ["phase=?", "failure_code=?", "updated_at=?"]
        values: list[object] = [next_phase, failure_code, _now()]
        timestamp = _PHASE_TIMESTAMPS.get(next_phase)
        if timestamp:
            assignments.append(f"{timestamp}=?")
            values.append(_now())
        for key, value in hashes.items():
            assignments.append(f"{key}=?")
            values.append(value)
        for key, value in lease_values.items():
            assignments.append(f"{key}=?")
            values.append(value)
        values.extend([operation_id, expected_phase])
        where = "WHERE operation_id=? AND phase=?"
        if excel_lease is not None:
            values.extend([excel_lease.owner_id, excel_lease.pair_nonce])
            where += " AND owner_id=? AND pair_nonce=?"
        # Set this outside the transaction; SQLite rejects changing safety
        # level after BEGIN.  It is also the storage default, but making it
        # explicit guards an embedding consumer that changed the connection.
        self.storage.connection.execute("PRAGMA synchronous=FULL")
        with self.storage.transaction() as connection:
            updated = connection.execute(
                f"UPDATE workbook_operation_journal SET {', '.join(assignments)} {where}",
                values,
            ).rowcount
            if updated != 1:
                raise JournalTransitionError("Operation не найдена или её фаза уже изменилась")
        return self.get(operation_id)  # type: ignore[return-value]

    def record_repair_anomaly(self, operation_id: str, *, failure_code: str) -> JournalOperation:
        """Durably preserve a terminal repair anomaly without reopening finalization.

        This is intentionally separate from the ordinary phase graph.  It is
        the sole path that may change a completed operation from ``finalized``
        to ``manual_repair``.  ``BEGIN IMMEDIATE`` in ``storage.transaction``
        serializes two live SQLite connections before either observes the
        terminal phase, so an exact retry is a no-write replay and a different
        code cannot replace the first evidence.
        """
        if not isinstance(operation_id, str) or not operation_id:
            raise RegistryError("Operation ID repair anomaly имеет неверный формат")
        if not isinstance(failure_code, str) or not _REPAIR_FAILURE_CODE.fullmatch(failure_code):
            raise RegistryError("Repair anomaly failure code имеет неверный формат")
        try:
            self.storage.connection.execute("PRAGMA synchronous=FULL")
            with self.storage.transaction() as connection:
                current = connection.execute(
                    "SELECT * FROM workbook_operation_journal WHERE operation_id=?", (operation_id,)
                ).fetchone()
                if current is None:
                    raise JournalTransitionError("Operation не найдена или её фаза уже изменилась")
                if current["phase"] == PHASE_MANUAL_REPAIR:
                    if current["failure_code"] != failure_code:
                        raise JournalTransitionError("Repair anomaly conflict сохраняет первый failure code")
                    return JournalOperation(dict(current))
                if current["phase"] != PHASE_FINALIZED:
                    raise JournalTransitionError("Repair anomaly допускается только для finalized или manual_repair")
                updated = connection.execute(
                    "UPDATE workbook_operation_journal SET phase=?, failure_code=?, updated_at=? "
                    "WHERE operation_id=? AND phase=?",
                    (PHASE_MANUAL_REPAIR, failure_code, _now(), operation_id, PHASE_FINALIZED),
                ).rowcount
                if updated != 1:
                    raise JournalTransitionError("Operation не найдена или её фаза уже изменилась")
                repaired = connection.execute(
                    "SELECT * FROM workbook_operation_journal WHERE operation_id=?", (operation_id,)
                ).fetchone()
                if repaired is None:
                    raise JournalStorageError("Repair anomaly не прочитан после durable CAS")
                return JournalOperation(dict(repaired))
        except sqlite3.Error as error:
            raise JournalStorageError("SQLite не сохранил repair anomaly") from error

    def record_post_hash(self, operation_id: str, *, expected_phase: str, post_hash: str) -> JournalOperation:
        raise RegistryError("finalization_snapshot_required")

    def record_finalization_authority(
        self, operation_id: str, *, expected_phase: str, post_hash: str, payload: object,
    ) -> JournalOperation:
        """Atomically persist the only post-hash and its sanitised authority."""
        if expected_phase != PHASE_BACKUP_VERIFIED:
            raise RegistryError("finalization_authority_missing")
        self.storage.connection.execute("PRAGMA synchronous=FULL")
        try:
            with self.storage.transaction() as connection:
                current = connection.execute("SELECT * FROM workbook_operation_journal WHERE operation_id=?", (operation_id,)).fetchone()
                if current is None or current["phase"] != expected_phase:
                    raise JournalTransitionError("finalization_authority_journal_failed")
                canonical, digest = validate_payload(
                    operation_id=operation_id, consumer_id=current["consumer_id"],
                    workbook_contract_id=current["workbook_contract_id"], post_hash=post_hash, payload=payload,
                )
                existing = connection.execute(
                    "SELECT snapshot_version, canonical_payload, digest FROM workbook_finalization_snapshots WHERE operation_id=?", (operation_id,)
                ).fetchone()
                if existing is not None:
                    if (existing["canonical_payload"], existing["digest"], current["post_hash"]) == (canonical, digest, post_hash):
                        return JournalOperation(dict(current))
                    raise RegistryConflictError("finalization_snapshot_conflict")
                if current["post_hash"] is not None:
                    raise RegistryConflictError("finalization_snapshot_conflict")
                connection.execute(
                    "INSERT INTO workbook_finalization_snapshots(operation_id,snapshot_version,canonical_payload,digest,created_at) VALUES(?,?,?,?,?)",
                    (operation_id, 1, canonical, digest, _now()),
                )
                if connection.execute(
                    "UPDATE workbook_operation_journal SET post_hash=?, updated_at=? WHERE operation_id=? AND phase=? AND post_hash IS NULL",
                    (post_hash, _now(), operation_id, expected_phase),
                ).rowcount != 1:
                    raise JournalTransitionError("finalization_authority_journal_failed")
        except FinalizationSnapshotError as error:
            raise RegistryError(error.code) from error
        except sqlite3.Error as error:
            raise JournalStorageError("finalization_authority_journal_failed") from error
        return self.get(operation_id)  # type: ignore[return-value]

    def finalize_flag(self, operation_id: str, flag: str) -> JournalOperation:
        if flag not in FINALIZATION_FLAGS:
            raise RegistryError("Неизвестный флаг finalization")
        # Binding is not a generic marker: K3b2a must first prove that the
        # durable construction/workbook tuple exists in the same transaction
        # as this receipt.  Keeping that proof outside the generic flag API
        # prevents an older caller from claiming the side effect happened.
        if flag in {"binding_finalized", "history_finalized", "report_finalized", "capability_finalized"}:
            raise RegistryError("finalization_receipt_required")
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
