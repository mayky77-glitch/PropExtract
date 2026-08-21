from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from rns_import_server.registry_storage import RegistryError, RegistryStorage
import rns_import_server.workbook_finalization as finalization
from rns_import_server.workbook_finalization import FinalizationError, finalize_published_binding
from rns_import_server.workbook_operation_journal import PHASE_BACKUP_VERIFIED, WorkbookOperationJournal


def _published(storage: RegistryStorage, *, operation_id: str = "binding-operation") -> str:
    construction = storage.list_constructions()[0]
    journal = WorkbookOperationJournal(storage)
    journal.create(
        operation_id=operation_id, idempotency_key=f"key-{operation_id}", consumer_id=operation_id,
        owner_id="owner", pair_nonce="pair", construction_id=construction.id, operation_kind="new_row",
        mutation_mode="blank_fill", target_identity="target", sheet_identity="sheet", template_version="template",
        expected_generation=storage.generation, intent_version="intent-v2", intent_digest="intent",
        manifest_version="manifest-v2", manifest_digest="manifest", operation_directory="operation",
        canonical_rns="RU-00000000-00-2026", workbook_contract_id="contract",
    )
    journal.transition(operation_id, expected_phase="planned", next_phase="staged", hashes={"pre_hash": "pre", "staged_hash": "staged"})
    journal.transition(operation_id, expected_phase="staged", next_phase="validated", hashes={"validation_digest": "valid"})
    journal.transition(operation_id, expected_phase="validated", next_phase=PHASE_BACKUP_VERIFIED, hashes={"backup_hash": "backup"})
    post_hash = "a" * 64
    journal.record_finalization_authority(
        operation_id, expected_phase=PHASE_BACKUP_VERIFIED, post_hash=post_hash,
        payload={"action_id": operation_id, "target_row": 6, "report_payload": {"final_state": {"workbook_sha256": post_hash}}},
    )
    journal.transition(operation_id, expected_phase=PHASE_BACKUP_VERIFIED, next_phase="published")
    return operation_id


def test_binding_finalizer_inserts_once_receipts_once_and_exact_replay_is_no_write(tmp_path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        operation_id = _published(storage); before_generation = storage.generation
        first = finalize_published_binding(storage, operation_id)
        row = storage.connection.execute("SELECT * FROM construction_bindings").fetchone()
        receipt = WorkbookOperationJournal(storage).get(operation_id)
        assert (first.status, first.completed_stage, first.next_stage, first.stage, storage.generation) == (
            "published_pending_finalization", "binding", "history", "binding", before_generation + 1,
        )
        assert row is not None and row["verified_state"] == "verified"
        assert receipt is not None and (receipt.phase, receipt["binding_finalized"], receipt["history_finalized"], receipt["report_finalized"], receipt["capability_finalized"]) == ("published", 1, 0, 0, 0)
        evidence = (first.binding_id, storage.generation, receipt["binding_finalized_at"])
        replay = finalize_published_binding(storage, operation_id)
        assert (replay.binding_id, storage.generation, WorkbookOperationJournal(storage).get(operation_id)["binding_finalized_at"]) == evidence  # type: ignore[index]
    finally:
        storage.close()


def test_existing_exact_binding_is_receipted_without_generation_change(tmp_path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        operation_id = _published(storage); construction = storage.list_constructions()[0]
        binding_id = storage.bind_construction(
            construction.id, workbook_contract_id="contract", target_identity="target", sheet_identity="sheet",
            template_version="template", verified_state="verified", expected_generation=storage.generation,
        )
        generation = storage.generation
        result = finalize_published_binding(storage, operation_id)
        assert (result.binding_id, storage.generation) == (binding_id, generation)
    finally:
        storage.close()


@pytest.mark.parametrize("column,value", [("id", "not-a-uuid"), ("id", None), ("verified_at", "broken")])
def test_existing_exact_binding_requires_valid_durable_identity_and_evidence(tmp_path, column: str, value: object) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        operation_id = _published(storage); construction = storage.list_constructions()[0]
        binding_id = storage.bind_construction(
            construction.id, workbook_contract_id="contract", target_identity="target", sheet_identity="sheet",
            template_version="template", verified_state="verified", expected_generation=storage.generation,
        )
        storage.connection.execute(f"UPDATE construction_bindings SET {column}=? WHERE id=?", (value, binding_id))
        result = finalize_published_binding(storage, operation_id)
        assert (result.status, result.error_code, storage.connection.execute("SELECT COUNT(*) FROM construction_bindings").fetchone()[0]) == (
            "manual_repair", "finalization_binding_conflict", 1,
        )
    finally:
        storage.close()


def test_missing_generation_authority_rolls_back_binding_and_receipt(tmp_path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        operation_id = _published(storage)
        storage.connection.execute("DELETE FROM registry_meta WHERE id=1")
        result = finalize_published_binding(storage, operation_id)
        operation = WorkbookOperationJournal(storage).get(operation_id)
        assert result.error_code == "finalization_binding_storage_failed"
        assert operation is not None and (operation.phase, operation["binding_finalized"], storage.connection.execute("SELECT COUNT(*) FROM construction_bindings").fetchone()[0]) == (
            "published", 0, 0,
        )
    finally:
        storage.close()


@pytest.mark.parametrize("mutation", [
    "UPDATE workbook_finalization_snapshots SET digest='broken'",
    "UPDATE workbook_operation_journal SET post_hash='A' || substr(post_hash, 2) WHERE operation_id='binding-operation'",
])
def test_corrupt_authority_moves_to_manual_repair_without_binding(tmp_path, mutation: str) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        operation_id = _published(storage); storage.connection.execute(mutation)
        result = finalize_published_binding(storage, operation_id)
        assert (result.status, result.error_code, storage.connection.execute("SELECT COUNT(*) FROM construction_bindings").fetchone()[0]) == (
            "manual_repair", "finalization_authority_corrupt", 0,
        )
    finally:
        storage.close()


def test_missing_authority_and_receipt_without_binding_are_durable_manual_repair(tmp_path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        operation_id = _published(storage)
        storage.connection.execute("DELETE FROM workbook_finalization_snapshots WHERE operation_id=?", (operation_id,))
        missing = finalize_published_binding(storage, operation_id)
        assert (missing.status, missing.error_code) == ("manual_repair", "finalization_authority_missing")
        storage.close(); storage = RegistryStorage.bootstrap(tmp_path / "receipt")
        operation_id = _published(storage)
        storage.connection.execute(
            "UPDATE workbook_operation_journal SET binding_finalized=1, binding_finalized_at='2026-01-01T00:00:00Z' WHERE operation_id=?",
            (operation_id,),
        )
        receipt = finalize_published_binding(storage, operation_id)
        assert (receipt.status, receipt.error_code, storage.connection.execute("SELECT COUNT(*) FROM construction_bindings").fetchone()[0]) == (
            "manual_repair", "finalization_receipt_required", 0,
        )
    finally:
        storage.close()


@pytest.mark.parametrize("timestamp", [" ", "2026-01-01", "2026-01-01T00:00:00+00:00"])
def test_existing_binding_receipt_requires_canonical_utc_timestamp(tmp_path, timestamp: str) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        operation_id = _published(storage)
        storage.connection.execute(
            "UPDATE workbook_operation_journal SET binding_finalized=1, binding_finalized_at=? WHERE operation_id=?",
            (timestamp, operation_id),
        )
        result = finalize_published_binding(storage, operation_id)
        assert (result.status, result.error_code, storage.connection.execute("SELECT COUNT(*) FROM construction_bindings").fetchone()[0]) == (
            "manual_repair", "finalization_receipt_required", 0,
        )
    finally:
        storage.close()


def test_conflict_and_direct_binding_flag_fail_closed(tmp_path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        operation_id = _published(storage); construction = storage.list_constructions()[0]
        storage.bind_construction(
            construction.id, workbook_contract_id="different", target_identity="target", sheet_identity="sheet",
            template_version="template", verified_state="verified", expected_generation=storage.generation,
        )
        result = finalize_published_binding(storage, operation_id)
        assert (result.status, result.error_code) == ("manual_repair", "finalization_binding_conflict")
        with pytest.raises(RegistryError, match="finalization_receipt_required"):
            WorkbookOperationJournal(storage).finalize_flag(operation_id, "binding_finalized")
    finally:
        storage.close()


def test_insert_and_receipt_rollback_together_on_receipt_failure(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        operation_id = _published(storage)
        def fail_receipt(*_args: object, **_kwargs: object) -> bool:
            raise __import__("sqlite3").OperationalError("injected receipt failure")
        monkeypatch.setattr(finalization, "_write_binding_receipt", fail_receipt)
        result = finalize_published_binding(storage, operation_id)
        assert result.error_code == "finalization_binding_storage_failed"
        row = WorkbookOperationJournal(storage).get(operation_id)
        assert row is not None and (row.phase, row["binding_finalized"], storage.connection.execute("SELECT COUNT(*) FROM construction_bindings").fetchone()[0]) == ("published", 0, 0)
    finally:
        storage.close()


def test_two_connections_converge_on_one_binding(tmp_path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path); operation_id = _published(storage); path = storage.path; storage.close()
    barrier = Barrier(2)
    def finalize() -> str | None:
        connection = RegistryStorage(path)
        try:
            barrier.wait()
            return finalize_published_binding(connection, operation_id).binding_id
        finally:
            connection.close()
    with ThreadPoolExecutor(max_workers=2) as executor:
        ids = [future.result() for future in (executor.submit(finalize), executor.submit(finalize))]
    verifier = RegistryStorage(path)
    try:
        assert ids[0] == ids[1]
        assert verifier.connection.execute("SELECT COUNT(*) FROM construction_bindings").fetchone()[0] == 1
        operation = WorkbookOperationJournal(verifier).get(operation_id)
        assert operation is not None and (operation.phase, operation["binding_finalized"]) == ("published", 1)
    finally:
        verifier.close()


def test_missing_or_wrong_phase_has_stable_typed_error(tmp_path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        with pytest.raises(FinalizationError, match="finalization_operation_missing"):
            finalize_published_binding(storage, "missing")
        operation_id = _published(storage)
        WorkbookOperationJournal(storage).transition(operation_id, expected_phase="published", next_phase="manual_repair", failure_code="test_failure")
        with pytest.raises(FinalizationError, match="finalization_phase_invalid"):
            finalize_published_binding(storage, operation_id)
    finally:
        storage.close()
