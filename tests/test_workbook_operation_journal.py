from __future__ import annotations

from pathlib import Path

import pytest

from rns_import_server.registry_storage import RegistryError, RegistryStorage
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
        staged = journal.transition(operation_id, expected_phase="planned", next_phase=PHASE_STAGED, hashes={"staged_hash": "s"})
        journal.transition(operation_id, expected_phase=PHASE_STAGED, next_phase=PHASE_NATIVE, excel_lease={"excel_adapter": "com", "excel_pid": 10})
        with pytest.raises(RegistryError):
            journal.transition(operation_id, expected_phase=PHASE_NATIVE, next_phase=PHASE_VALIDATED)
        journal.transition(operation_id, expected_phase=PHASE_NATIVE, next_phase=PHASE_VALIDATED, hashes={"validation_digest": "v"})
        journal.transition(operation_id, expected_phase=PHASE_VALIDATED, next_phase=PHASE_BACKUP_VERIFIED, hashes={"backup_hash": "b"})
        with pytest.raises(RegistryError):
            journal.transition(operation_id, expected_phase=PHASE_BACKUP_VERIFIED, next_phase=PHASE_PUBLISHED)
        journal.transition(operation_id, expected_phase=PHASE_BACKUP_VERIFIED, next_phase=PHASE_PUBLISHED, hashes={"post_hash": "p"})
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
        journal.finalize_flag(operation_id, "history_finalized")
        storage.close()
        restarted = RegistryStorage(storage.path)
        try:
            restored = WorkbookOperationJournal(restarted).get(operation_id)
            assert restored and restored["history_finalized"] == 1
            assert [item.operation_id for item in WorkbookOperationJournal(restarted).incomplete()] == [operation_id]
        finally:
            restarted.close()
    finally:
        # ``close`` is deliberately idempotence-free; this only handles the
        # branch where the earlier restart closed a separate connection.
        if storage.connection:
            pass
