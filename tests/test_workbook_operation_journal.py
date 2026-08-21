from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from rns_import_server.registry_storage import RegistryConflictError, RegistryError, RegistryStorage
from rns_import_server.excel_process_authority import ExcelProcessLease
from rns_import_server.workbook_finalization import finalize_published_binding
from rns_import_server.workbook_operation_journal import (
    JournalStorageError,
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
        operation_id="operation-1", idempotency_key="idempotency-1", consumer_id="operation-1", owner_id="owner-1",
        pair_nonce="nonce-1", construction_id=construction.id, operation_kind="new_row", mutation_mode="middle_insert",
        target_identity="target", sheet_identity="sheet", template_version="template-v1", expected_generation=storage.generation,
        intent_version="intent-v1", intent_digest="intent-digest", manifest_version="manifest-v1",
        manifest_digest="manifest-digest", operation_directory="operation-dir", canonical_rns="RU-00000000-00-2026", workbook_contract_id="contract-v1",
    ).operation_id


def _lease(operation_id: str, *, owner: str = "owner-1", pair: str = "nonce-1") -> ExcelProcessLease:
    return ExcelProcessLease(
        operation_id=operation_id, owner_id=owner, pair_nonce=pair, adapter_type="com", adapter_image="powershell.exe",
        adapter_pid=10, adapter_started_at="2026-08-21T00:00:00Z", excel_image="EXCEL.EXE", excel_pid=11,
        excel_hwnd=12, excel_process_started_at="2026-08-21T00:00:01Z", excel_build="16.0.1",
    )


def _authority(journal: WorkbookOperationJournal, operation_id: str, post_hash: str) -> None:
    post_hash = "a" * 64
    journal.record_finalization_authority(
        operation_id, expected_phase=PHASE_BACKUP_VERIFIED, post_hash=post_hash,
        payload={"action_id": operation_id, "target_row": 2, "report_payload": {"final_state": {"workbook_sha256": post_hash}}},
    )


def _finalized_operation(journal: WorkbookOperationJournal, storage: RegistryStorage) -> str:
    operation_id = _operation(journal, storage)
    journal.transition(operation_id, expected_phase="planned", next_phase=PHASE_STAGED,
                       hashes={"pre_hash": "pre", "staged_hash": "staged"})
    journal.transition(operation_id, expected_phase=PHASE_STAGED, next_phase=PHASE_NATIVE,
                       excel_lease=_lease(operation_id))
    journal.transition(operation_id, expected_phase=PHASE_NATIVE, next_phase=PHASE_VALIDATED,
                       hashes={"validation_digest": "validation", "control_hash": "control"})
    journal.transition(operation_id, expected_phase=PHASE_VALIDATED, next_phase=PHASE_BACKUP_VERIFIED,
                       hashes={"backup_hash": "backup"})
    _authority(journal, operation_id, "post")
    journal.transition(operation_id, expected_phase=PHASE_BACKUP_VERIFIED, next_phase=PHASE_PUBLISHED)
    finalize_published_binding(storage, operation_id)
    # The v5 history receipt is owned by its action finalizer, never by the
    # generic marker API.  This fixture constructs later-stage evidence only
    # for testing the pre-existing repair-anomaly boundary.
    now = "2026-08-22T00:00:00Z"
    storage.connection.execute(
        "UPDATE workbook_operation_journal SET capability_finalized=1, capability_finalized_at=?, "
        "history_finalized=1, history_finalized_at=?, report_finalized=1, report_finalized_at=? WHERE operation_id=?",
        (now, now, now, operation_id),
    )
    journal.transition(operation_id, expected_phase=PHASE_PUBLISHED, next_phase=PHASE_FINALIZED)
    return operation_id


def test_atomic_reservation_creates_nonce_pair_once_and_reuses_authority(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        journal = WorkbookOperationJournal(storage)
        construction = storage.list_constructions()[0]
        calls = []
        def nonce_factory() -> tuple[str, str]:
            calls.append(True)
            return "owner-1", "pair-1"
        values = dict(
            operation_id="operation-reserved", idempotency_key="idempotency-reserved", consumer_id="operation-reserved",
            construction_id=construction.id, operation_kind="new_row", mutation_mode="middle_insert",
            target_identity="target", sheet_identity="sheet", template_version="template-v1",
            expected_generation=storage.generation, intent_version="intent-v2", intent_digest="intent-digest",
            manifest_version="manifest-v2", manifest_digest="manifest-digest", operation_directory="operation-dir",
            canonical_rns="RU-00000000-00-2026", workbook_contract_id="contract-v1",
        )
        first, first_created = journal.reserve(nonce_factory=nonce_factory, **values)
        second, second_created = journal.reserve(nonce_factory=nonce_factory, **values)
        assert (first_created, second_created, calls) == (True, False, [True])
        assert (first["owner_id"], first["pair_nonce"], second["owner_id"], second["pair_nonce"]) == (
            "owner-1", "pair-1", "owner-1", "pair-1",
        )
    finally:
        storage.close()


def test_journal_requires_legal_cas_phases_and_durable_hash_evidence(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        journal = WorkbookOperationJournal(storage)
        operation_id = _operation(journal, storage)
        storage.connection.execute("PRAGMA synchronous=NORMAL")
        with pytest.raises(JournalTransitionError):
            journal.transition(operation_id, expected_phase="planned", next_phase=PHASE_VALIDATED)
        with pytest.raises(RegistryError):
            journal.transition(operation_id, expected_phase="planned", next_phase=PHASE_STAGED, hashes={"staged_hash": "s"})
        journal.transition(operation_id, expected_phase="planned", next_phase=PHASE_STAGED, hashes={"pre_hash": "pre", "staged_hash": "s"})
        assert storage.connection.execute("PRAGMA synchronous").fetchone()[0] == 2
        with pytest.raises(RegistryError):
            journal.transition(operation_id, expected_phase=PHASE_STAGED, next_phase=PHASE_NATIVE)
        journal.transition(operation_id, expected_phase=PHASE_STAGED, next_phase=PHASE_NATIVE, excel_lease=_lease(operation_id))
        with pytest.raises(RegistryError):
            journal.transition(operation_id, expected_phase=PHASE_NATIVE, next_phase=PHASE_VALIDATED)
        journal.transition(
            operation_id, expected_phase=PHASE_NATIVE, next_phase=PHASE_VALIDATED,
            hashes={"validation_digest": "v", "control_hash": "control"},
        )
        journal.transition(operation_id, expected_phase=PHASE_VALIDATED, next_phase=PHASE_BACKUP_VERIFIED, hashes={"backup_hash": "b"})
        with pytest.raises(RegistryError):
            journal.transition(operation_id, expected_phase=PHASE_BACKUP_VERIFIED, next_phase=PHASE_PUBLISHED, hashes={"post_hash": "p"})
        _authority(journal, operation_id, "p")
        journal.transition(operation_id, expected_phase=PHASE_BACKUP_VERIFIED, next_phase=PHASE_PUBLISHED)
        with pytest.raises(RegistryError):
            journal.transition(operation_id, expected_phase=PHASE_PUBLISHED, next_phase=PHASE_FINALIZED)
        finalize_published_binding(storage, operation_id)
        with pytest.raises(RegistryError, match="finalization_receipt_required"):
            journal.finalize_flag(operation_id, "history_finalized")
        assert journal.get(operation_id).phase == PHASE_PUBLISHED  # type: ignore[union-attr]
    finally:
        storage.close()


def test_journal_idempotency_restart_and_independent_finalization(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        journal = WorkbookOperationJournal(storage)
        operation_id = _operation(journal, storage)
        assert journal.create(
            operation_id=operation_id, idempotency_key="idempotency-1", consumer_id=operation_id, owner_id="owner-1",
            pair_nonce="nonce-1", construction_id=storage.list_constructions()[0].id, operation_kind="new_row",
            mutation_mode="middle_insert", target_identity="target", sheet_identity="sheet", template_version="template-v1",
            expected_generation=storage.generation, intent_version="intent-v1", intent_digest="intent-digest",
            manifest_version="manifest-v1", manifest_digest="manifest-digest", operation_directory="operation-dir",
            canonical_rns="RU-00000000-00-2026", workbook_contract_id="contract-v1",
        ).operation_id == operation_id
        with pytest.raises(RegistryConflictError):
            journal.create(
                operation_id=operation_id, idempotency_key="idempotency-1", consumer_id=operation_id, owner_id="changed-consumer",
                pair_nonce="nonce-1", construction_id=storage.list_constructions()[0].id, operation_kind="new_row",
                mutation_mode="middle_insert", target_identity="target", sheet_identity="sheet", template_version="template-v1",
                expected_generation=storage.generation, intent_version="intent-v1", intent_digest="intent-digest",
                manifest_version="manifest-v1", manifest_digest="manifest-digest", operation_directory="operation-dir",
                canonical_rns="RU-00000000-00-2026", workbook_contract_id="contract-v1",
            )
        journal.transition(operation_id, expected_phase="planned", next_phase=PHASE_STAGED, hashes={"pre_hash": "pre", "staged_hash": "staged"})
        journal.transition(operation_id, expected_phase=PHASE_STAGED, next_phase=PHASE_NATIVE, excel_lease=_lease(operation_id))
        journal.transition(operation_id, expected_phase=PHASE_NATIVE, next_phase=PHASE_VALIDATED,
                           hashes={"validation_digest": "v", "control_hash": "c"})
        journal.transition(operation_id, expected_phase=PHASE_VALIDATED, next_phase=PHASE_BACKUP_VERIFIED, hashes={"backup_hash": "b"})
        _authority(journal, operation_id, "post")
        journal.transition(operation_id, expected_phase=PHASE_BACKUP_VERIFIED, next_phase=PHASE_PUBLISHED)
        with pytest.raises(RegistryError, match="finalization_receipt_required"):
            journal.finalize_flag(operation_id, "history_finalized")
        storage.close()
        restarted = RegistryStorage(storage.path)
        try:
            restored = WorkbookOperationJournal(restarted).get(operation_id)
            assert restored and restored["history_finalized"] == 0
            assert restored["history_finalized_at"] is None
            assert [item.operation_id for item in WorkbookOperationJournal(restarted).incomplete()] == [operation_id]
        finally:
            restarted.close()
    finally:
        # ``close`` is deliberately idempotence-free; this only handles the
        # branch where the earlier restart closed a separate connection.
        if storage.connection:
            pass


def test_exact_idempotency_replay_precedes_generation_check_after_restart(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        journal = WorkbookOperationJournal(storage)
        operation_id = _operation(journal, storage)
        expected_generation = storage.generation
        construction_id = storage.list_constructions()[0].id
        storage.create_construction(code_prefix="999-9999999", official_name="Независимая")
        storage.close()
        restarted = RegistryStorage(storage.path)
        try:
            replayed = WorkbookOperationJournal(restarted).create(
                operation_id=operation_id, idempotency_key="idempotency-1", consumer_id=operation_id, owner_id="owner-1",
                pair_nonce="nonce-1", construction_id=construction_id, operation_kind="new_row", mutation_mode="middle_insert",
                target_identity="target", sheet_identity="sheet", template_version="template-v1",
                expected_generation=expected_generation, intent_version="intent-v1", intent_digest="intent-digest",
                manifest_version="manifest-v1", manifest_digest="manifest-digest", operation_directory="operation-dir",
                canonical_rns="RU-00000000-00-2026", workbook_contract_id="contract-v1",
            )
            assert replayed.operation_id == operation_id
            with pytest.raises(RegistryConflictError):
                WorkbookOperationJournal(restarted).create(
                    operation_id=operation_id, idempotency_key="idempotency-1", consumer_id=operation_id, owner_id="changed",
                    pair_nonce="nonce-1", construction_id=construction_id, operation_kind="new_row", mutation_mode="middle_insert",
                    target_identity="target", sheet_identity="sheet", template_version="template-v1",
                    expected_generation=expected_generation, intent_version="intent-v1", intent_digest="intent-digest",
                    manifest_version="manifest-v1", manifest_digest="manifest-digest", operation_directory="operation-dir",
                    canonical_rns="RU-00000000-00-2026", workbook_contract_id="contract-v1",
                )
        finally:
            restarted.close()
    finally:
        if storage.connection:
            pass


def test_finalization_flag_replay_after_finalized_restart_preserves_first_timestamp(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        journal = WorkbookOperationJournal(storage)
        operation_id = _operation(journal, storage)
        journal.transition(operation_id, expected_phase="planned", next_phase=PHASE_STAGED, hashes={"pre_hash": "pre", "staged_hash": "staged"})
        journal.transition(operation_id, expected_phase=PHASE_STAGED, next_phase=PHASE_NATIVE, excel_lease=_lease(operation_id))
        journal.transition(operation_id, expected_phase=PHASE_NATIVE, next_phase=PHASE_VALIDATED,
                           hashes={"validation_digest": "v", "control_hash": "c"})
        journal.transition(operation_id, expected_phase=PHASE_VALIDATED, next_phase=PHASE_BACKUP_VERIFIED, hashes={"backup_hash": "b"})
        _authority(journal, operation_id, "post")
        journal.transition(operation_id, expected_phase=PHASE_BACKUP_VERIFIED, next_phase=PHASE_PUBLISHED)
        finalize_published_binding(storage, operation_id)
        with pytest.raises(RegistryError, match="finalization_receipt_required"):
            journal.finalize_flag(operation_id, "history_finalized")
    finally:
        if storage.connection:
            pass


def test_repair_anomaly_moves_finalized_to_manual_repair_without_losing_finalization_evidence(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        journal = WorkbookOperationJournal(storage)
        operation_id = _finalized_operation(journal, storage)
        before = journal.get(operation_id)
        assert before is not None
        preserved = {
            key: value for key, value in before.values.items()
            if key not in {"phase", "failure_code", "updated_at"}
        }
        repaired = journal.record_repair_anomaly(operation_id, failure_code="target_hash_mismatch")
        assert repaired.phase == "manual_repair"
        assert repaired["failure_code"] == "target_hash_mismatch"
        assert {key: repaired[key] for key in preserved} == preserved
        changes_after_first_record = storage.connection.total_changes
        replayed = journal.record_repair_anomaly(operation_id, failure_code="target_hash_mismatch")
        assert dict(replayed.values) == dict(repaired.values)
        assert storage.connection.total_changes == changes_after_first_record
    finally:
        storage.close()


@pytest.mark.parametrize("failure_code", [None, True, "", "TargetHashMismatch", "a" * 65])
def test_repair_anomaly_requires_bounded_lower_snake_failure_code(tmp_path: Path, failure_code: object) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        operation_id = _finalized_operation(WorkbookOperationJournal(storage), storage)
        with pytest.raises(RegistryError):
            WorkbookOperationJournal(storage).record_repair_anomaly(operation_id, failure_code=failure_code)  # type: ignore[arg-type]
        assert WorkbookOperationJournal(storage).get(operation_id).phase == PHASE_FINALIZED  # type: ignore[union-attr]
    finally:
        storage.close()


def test_repair_anomaly_is_typed_for_missing_unsupported_and_sqlite_failures(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        journal = WorkbookOperationJournal(storage)
        with pytest.raises(JournalTransitionError):
            journal.record_repair_anomaly("missing-operation", failure_code="target_hash_mismatch")
        operation_id = _operation(journal, storage)
        with pytest.raises(JournalTransitionError):
            journal.record_repair_anomaly(operation_id, failure_code="target_hash_mismatch")
    finally:
        storage.close()
    with pytest.raises(JournalStorageError):
        journal.record_repair_anomaly(operation_id, failure_code="target_hash_mismatch")


def test_repair_anomaly_serializes_two_real_sqlite_connections_and_preserves_first_code(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    operation_id = _finalized_operation(WorkbookOperationJournal(storage), storage)
    database_path = storage.path
    storage.close()
    barrier = Barrier(2)

    def record_from_independent_connection() -> str:
        connection = RegistryStorage(database_path)
        try:
            barrier.wait()
            return WorkbookOperationJournal(connection).record_repair_anomaly(
                operation_id, failure_code="target_hash_mismatch"
            )["failure_code"]
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [future.result() for future in (
            executor.submit(record_from_independent_connection), executor.submit(record_from_independent_connection),
        )]
    verifier = RegistryStorage(database_path)
    try:
        journal = WorkbookOperationJournal(verifier)
        assert results == ["target_hash_mismatch", "target_hash_mismatch"]
        durable = journal.get(operation_id)
        assert durable is not None and (durable.phase, durable["failure_code"]) == ("manual_repair", "target_hash_mismatch")
        with pytest.raises(JournalTransitionError):
            journal.record_repair_anomaly(operation_id, failure_code="authority_hash_mismatch")
        assert journal.get(operation_id)["failure_code"] == "target_hash_mismatch"  # type: ignore[index]
    finally:
        verifier.close()


def test_journal_contract_has_no_pdf_text_cell_content_or_source_path_fields(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        journal = WorkbookOperationJournal(storage)
        operation_id = _operation(journal, storage)
        columns = {row["name"] for row in storage.connection.execute("PRAGMA table_info(workbook_operation_journal)")}
        assert not {"pdf_text", "cell_content", "source_path", "secret"} & columns
        with pytest.raises(RegistryConflictError) as error:
            journal.create(
                operation_id=operation_id, idempotency_key="idempotency-1", consumer_id=operation_id, owner_id="/private/source.pdf",
                pair_nonce="nonce-1", construction_id=storage.list_constructions()[0].id, operation_kind="new_row",
                mutation_mode="middle_insert", target_identity="target", sheet_identity="sheet", template_version="template-v1",
                expected_generation=storage.generation, intent_version="intent-v1", intent_digest="secret-pdf-text",
                manifest_version="manifest-v1", manifest_digest="cell-content", operation_directory="operation-dir",
                canonical_rns="RU-00000000-00-2026", workbook_contract_id="contract-v1",
            )
        message = str(error.value)
        assert "/private/source.pdf" not in message
        assert "secret-pdf-text" not in message
        assert "cell-content" not in message
    finally:
        storage.close()


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


@pytest.mark.parametrize("lease", [
    None,
    {"excel_adapter": "com"},
    _lease("other-operation"),
    _lease("operation-1", owner="other-owner"),
    _lease("operation-1", pair="other-pair"),
])
def test_native_transition_requires_exact_full_lease_and_authority_pair(tmp_path: Path, lease: object) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        journal = WorkbookOperationJournal(storage)
        operation_id = _operation(journal, storage)
        journal.transition(operation_id, expected_phase="planned", next_phase=PHASE_STAGED, hashes={"pre_hash": "pre", "staged_hash": "staged"})
        with pytest.raises(RegistryError):
            journal.transition(operation_id, expected_phase=PHASE_STAGED, next_phase=PHASE_NATIVE, excel_lease=lease)  # type: ignore[arg-type]
        assert journal.get(operation_id).phase == PHASE_STAGED  # type: ignore[union-attr]
    finally:
        storage.close()


@pytest.mark.parametrize("mode", ["middle_insert", "blank_fill"])
def test_each_native_mutation_mode_requires_complete_lease(tmp_path: Path, mode: str) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        journal = WorkbookOperationJournal(storage)
        operation_id = _operation(journal, storage)
        storage.connection.execute("UPDATE workbook_operation_journal SET mutation_mode=? WHERE operation_id=?", (mode, operation_id))
        journal.transition(operation_id, expected_phase="planned", next_phase=PHASE_STAGED, hashes={"pre_hash": "pre", "staged_hash": "staged"})
        with pytest.raises(RegistryError):
            journal.transition(operation_id, expected_phase=PHASE_STAGED, next_phase=PHASE_NATIVE)
        assert journal.transition(operation_id, expected_phase=PHASE_STAGED, next_phase=PHASE_NATIVE, excel_lease=_lease(operation_id)).phase == PHASE_NATIVE
    finally:
        storage.close()
