from __future__ import annotations

from pathlib import Path

import pytest

from rns_import_server.registry_storage import RegistryConflictError, RegistryError, RegistryStorage
from rns_import_server.workbook_operation_journal import (
    JournalTransitionError,
    PHASE_BACKUP_VERIFIED,
    PHASE_FINALIZED,
    PHASE_NATIVE,
    PHASE_PUBLISHED,
    PHASE_STAGED,
    PHASE_VALIDATED,
    WorkbookOperationJournal,
)


def _operation(journal: WorkbookOperationJournal, storage: RegistryStorage) -> str:
    construction = storage.list_constructions()[0]
    return journal.create(
        operation_id="operation-1", idempotency_key="idempotency-1", consumer_id="consumer-1", owner_id="owner-1",
        pair_nonce="nonce-1", construction_id=construction.id, operation_kind="new_row", mutation_mode="middle_insert",
        target_identity="target", sheet_identity="sheet", template_version="template-v1", expected_generation=storage.generation,
        intent_version="intent-v1", intent_digest="intent-digest", manifest_version="manifest-v1",
        manifest_digest="manifest-digest", operation_directory="operation-dir", canonical_rns="RU-00000000-00-2026",
    ).operation_id


def test_journal_requires_legal_cas_phases_and_durable_hash_evidence(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        journal = WorkbookOperationJournal(storage)
        operation_id = _operation(journal, storage)
        with pytest.raises(JournalTransitionError):
            journal.transition(operation_id, expected_phase="planned", next_phase=PHASE_VALIDATED)
        with pytest.raises(RegistryError):
            journal.transition(operation_id, expected_phase="planned", next_phase=PHASE_STAGED, hashes={"staged_hash": "s"})
        journal.transition(operation_id, expected_phase="planned", next_phase=PHASE_STAGED, hashes={"pre_hash": "pre", "staged_hash": "s"})
        journal.transition(operation_id, expected_phase=PHASE_STAGED, next_phase=PHASE_NATIVE, excel_lease={"excel_adapter": "com", "excel_pid": 10})
        with pytest.raises(RegistryError):
            journal.transition(operation_id, expected_phase=PHASE_NATIVE, next_phase=PHASE_VALIDATED)
        journal.transition(
            operation_id, expected_phase=PHASE_NATIVE, next_phase=PHASE_VALIDATED,
            hashes={"validation_digest": "v", "control_hash": "control"},
            excel_lease={"excel_adapter": "com", "excel_pid": 10, "excel_hwnd": 11,
                         "excel_process_started_at": "started", "excel_build": "build"},
        )
        journal.transition(operation_id, expected_phase=PHASE_VALIDATED, next_phase=PHASE_BACKUP_VERIFIED, hashes={"backup_hash": "b"})
        with pytest.raises(RegistryError):
            journal.transition(operation_id, expected_phase=PHASE_BACKUP_VERIFIED, next_phase=PHASE_PUBLISHED, hashes={"post_hash": "p"})
        journal.record_post_hash(operation_id, expected_phase=PHASE_BACKUP_VERIFIED, post_hash="p")
        journal.transition(operation_id, expected_phase=PHASE_BACKUP_VERIFIED, next_phase=PHASE_PUBLISHED)
        with pytest.raises(RegistryError):
            journal.transition(operation_id, expected_phase=PHASE_PUBLISHED, next_phase=PHASE_FINALIZED)
        for flag in ("capability_finalized", "binding_finalized", "history_finalized", "report_finalized"):
            journal.finalize_flag(operation_id, flag)
        finished = journal.transition(operation_id, expected_phase=PHASE_PUBLISHED, next_phase=PHASE_FINALIZED)
        assert finished.phase == PHASE_FINALIZED
        assert journal.incomplete() == []
    finally:
        storage.close()


def test_journal_idempotency_restart_and_independent_finalization(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        journal = WorkbookOperationJournal(storage)
        operation_id = _operation(journal, storage)
        assert journal.create(
            operation_id=operation_id, idempotency_key="idempotency-1", consumer_id="consumer-1", owner_id="owner-1",
            pair_nonce="nonce-1", construction_id=storage.list_constructions()[0].id, operation_kind="new_row",
            mutation_mode="middle_insert", target_identity="target", sheet_identity="sheet", template_version="template-v1",
            expected_generation=storage.generation, intent_version="intent-v1", intent_digest="intent-digest",
            manifest_version="manifest-v1", manifest_digest="manifest-digest", operation_directory="operation-dir",
            canonical_rns="RU-00000000-00-2026",
        ).operation_id == operation_id
        with pytest.raises(RegistryConflictError):
            journal.create(
                operation_id=operation_id, idempotency_key="idempotency-1", consumer_id="consumer-different", owner_id="owner-1",
                pair_nonce="nonce-1", construction_id=storage.list_constructions()[0].id, operation_kind="new_row",
                mutation_mode="middle_insert", target_identity="target", sheet_identity="sheet", template_version="template-v1",
                expected_generation=storage.generation, intent_version="intent-v1", intent_digest="intent-digest",
                manifest_version="manifest-v1", manifest_digest="manifest-digest", operation_directory="operation-dir",
                canonical_rns="RU-00000000-00-2026",
            )
        journal.transition(operation_id, expected_phase="planned", next_phase=PHASE_STAGED, hashes={"pre_hash": "pre", "staged_hash": "staged"})
        journal.transition(operation_id, expected_phase=PHASE_STAGED, next_phase=PHASE_NATIVE)
        journal.transition(operation_id, expected_phase=PHASE_NATIVE, next_phase=PHASE_VALIDATED,
                           hashes={"validation_digest": "v", "control_hash": "c"},
                           excel_lease={"excel_adapter": "com", "excel_pid": 1, "excel_hwnd": 2,
                                        "excel_process_started_at": "s", "excel_build": "b"})
        journal.transition(operation_id, expected_phase=PHASE_VALIDATED, next_phase=PHASE_BACKUP_VERIFIED, hashes={"backup_hash": "b"})
        journal.record_post_hash(operation_id, expected_phase=PHASE_BACKUP_VERIFIED, post_hash="post")
        journal.transition(operation_id, expected_phase=PHASE_BACKUP_VERIFIED, next_phase=PHASE_PUBLISHED)
        journal.finalize_flag(operation_id, "history_finalized")
        storage.close()
        restarted = RegistryStorage(storage.path)
        try:
            restored = WorkbookOperationJournal(restarted).get(operation_id)
            assert restored and restored["history_finalized"] == 1
            assert restored["history_finalized_at"]
            assert [item.operation_id for item in WorkbookOperationJournal(restarted).incomplete()] == [operation_id]
        finally:
            restarted.close()
    finally:
        # ``close`` is deliberately idempotence-free; this only handles the
        # branch where the earlier restart closed a separate connection.
        if storage.connection:
            pass


def test_manual_repair_is_visible_and_requires_failure_evidence(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        journal = WorkbookOperationJournal(storage)
        operation_id = _operation(journal, storage)
        with pytest.raises(RegistryError):
            journal.transition(operation_id, expected_phase="planned", next_phase="manual_repair")
        journal.transition(operation_id, expected_phase="planned", next_phase="manual_repair", failure_code="hash_mismatch")
        assert [item.operation_id for item in journal.incomplete()] == [operation_id]
    finally:
        storage.close()
