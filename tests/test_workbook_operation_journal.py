from __future__ import annotations

from pathlib import Path
import threading

import pytest

from rns_import_server.registry_storage import RegistryConflictError, RegistryError, RegistryStorage
from rns_import_server.workbook_operation_journal import (
    JournalTransitionError,
    PHASE_BACKUP_VERIFIED,
    PHASE_EXCEL_LAUNCHING,
    PHASE_EXCEL_OWNED,
    PHASE_FINALIZED,
    PHASE_NATIVE,
    PHASE_PUBLISHED,
    PHASE_STAGED,
    PHASE_VALIDATED,
    WorkbookOperationJournal,
)


def _adapter_lease() -> dict[str, object]:
    return {
        "excel_adapter": "powershell-com",
        "adapter_pid": 101,
        "adapter_image": r"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
        "adapter_process_started_at": "2026-08-18T01:02:03Z",
    }


def _owned_lease() -> dict[str, object]:
    return {
        **_adapter_lease(),
        "excel_pid": 202,
        "excel_hwnd": 303,
        "excel_image": r"C:\\Program Files\\Microsoft Office\\root\\Office16\\EXCEL.EXE",
        "excel_process_started_at": "2026-08-18T01:02:04Z",
        "excel_build": "16.0.12345",
    }


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
        storage.connection.execute("PRAGMA synchronous=NORMAL")
        with pytest.raises(JournalTransitionError):
            journal.transition(operation_id, expected_phase="planned", next_phase=PHASE_VALIDATED)
        with pytest.raises(RegistryError):
            journal.transition(operation_id, expected_phase="planned", next_phase=PHASE_STAGED, hashes={"staged_hash": "s"})
        journal.transition(operation_id, expected_phase="planned", next_phase=PHASE_STAGED, hashes={"pre_hash": "pre", "staged_hash": "s"})
        assert storage.connection.execute("PRAGMA synchronous").fetchone()[0] == 2
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
        first_history_at = finished["history_finalized_at"]
        replayed = journal.finalize_flag(operation_id, "history_finalized")
        assert replayed["history_finalized_at"] == first_history_at
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
                operation_id=operation_id, idempotency_key="idempotency-1", consumer_id="consumer-1", owner_id="owner-1",
                pair_nonce="nonce-1", construction_id=construction_id, operation_kind="new_row", mutation_mode="middle_insert",
                target_identity="target", sheet_identity="sheet", template_version="template-v1",
                expected_generation=expected_generation, intent_version="intent-v1", intent_digest="intent-digest",
                manifest_version="manifest-v1", manifest_digest="manifest-digest", operation_directory="operation-dir",
                canonical_rns="RU-00000000-00-2026",
            )
            assert replayed.operation_id == operation_id
            with pytest.raises(RegistryConflictError):
                WorkbookOperationJournal(restarted).create(
                    operation_id=operation_id, idempotency_key="idempotency-1", consumer_id="consumer-1", owner_id="changed",
                    pair_nonce="nonce-1", construction_id=construction_id, operation_kind="new_row", mutation_mode="middle_insert",
                    target_identity="target", sheet_identity="sheet", template_version="template-v1",
                    expected_generation=expected_generation, intent_version="intent-v1", intent_digest="intent-digest",
                    manifest_version="manifest-v1", manifest_digest="manifest-digest", operation_directory="operation-dir",
                    canonical_rns="RU-00000000-00-2026",
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
        journal.transition(operation_id, expected_phase=PHASE_STAGED, next_phase=PHASE_NATIVE)
        journal.transition(operation_id, expected_phase=PHASE_NATIVE, next_phase=PHASE_VALIDATED,
                           hashes={"validation_digest": "v", "control_hash": "c"},
                           excel_lease={"excel_adapter": "com", "excel_pid": 1, "excel_hwnd": 2,
                                        "excel_process_started_at": "s", "excel_build": "b"})
        journal.transition(operation_id, expected_phase=PHASE_VALIDATED, next_phase=PHASE_BACKUP_VERIFIED, hashes={"backup_hash": "b"})
        journal.record_post_hash(operation_id, expected_phase=PHASE_BACKUP_VERIFIED, post_hash="post")
        journal.transition(operation_id, expected_phase=PHASE_BACKUP_VERIFIED, next_phase=PHASE_PUBLISHED)
        for flag in ("capability_finalized", "binding_finalized", "history_finalized", "report_finalized"):
            journal.finalize_flag(operation_id, flag)
        original_at = journal.get(operation_id)["report_finalized_at"]  # type: ignore[index]
        journal.transition(operation_id, expected_phase=PHASE_PUBLISHED, next_phase=PHASE_FINALIZED)
        storage.close()
        restarted = RegistryStorage(storage.path)
        try:
            replayed = WorkbookOperationJournal(restarted).finalize_flag(operation_id, "report_finalized")
            assert replayed["report_finalized_at"] == original_at
            assert replayed.phase == PHASE_FINALIZED
        finally:
            restarted.close()
    finally:
        if storage.connection:
            pass


def test_journal_contract_has_no_pdf_text_cell_content_or_source_path_fields(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        journal = WorkbookOperationJournal(storage)
        operation_id = _operation(journal, storage)
        columns = {row["name"] for row in storage.connection.execute("PRAGMA table_info(workbook_operation_journal)")}
        assert not {"pdf_text", "cell_content", "source_path", "secret"} & columns
        with pytest.raises(RegistryConflictError) as error:
            journal.create(
                operation_id=operation_id, idempotency_key="idempotency-1", consumer_id="consumer-1", owner_id="/private/source.pdf",
                pair_nonce="nonce-1", construction_id=storage.list_constructions()[0].id, operation_kind="new_row",
                mutation_mode="middle_insert", target_identity="target", sheet_identity="sheet", template_version="template-v1",
                expected_generation=storage.generation, intent_version="intent-v1", intent_digest="secret-pdf-text",
                manifest_version="manifest-v1", manifest_digest="cell-content", operation_directory="operation-dir",
                canonical_rns="RU-00000000-00-2026",
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


def test_v3_lease_is_nonce_bound_idempotent_and_ack_requires_owned_identity(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        journal = WorkbookOperationJournal(storage)
        operation_id = _operation(journal, storage)
        journal.transition(operation_id, expected_phase="planned", next_phase=PHASE_STAGED,
                           hashes={"pre_hash": "pre", "staged_hash": "staged"})
        with pytest.raises(JournalTransitionError):
            journal.authorize_excel_ack(operation_id, owner_id="owner-1", pair_nonce="nonce-1")
        with pytest.raises(RegistryError):
            journal.record_excel_launching(operation_id, owner_id="owner-1", pair_nonce="nonce-1",
                                           lease={"excel_adapter": "powershell-com"})
        launching = journal.record_excel_launching(
            operation_id, owner_id="owner-1", pair_nonce="nonce-1", lease=_adapter_lease()
        )
        assert launching.phase == PHASE_EXCEL_LAUNCHING
        assert journal.record_excel_launching(
            operation_id, owner_id="owner-1", pair_nonce="nonce-1", lease=_adapter_lease()
        ).phase == PHASE_EXCEL_LAUNCHING
        with pytest.raises(RegistryConflictError):
            journal.record_excel_launching(operation_id, owner_id="owner-1", pair_nonce="other", lease=_adapter_lease())
        with pytest.raises(RegistryError):
            journal.record_excel_owned(
                operation_id, owner_id="owner-1", pair_nonce="nonce-1",
                lease={**_owned_lease(), "excel_image": "not-excel.exe"},
            )
        assert journal.get(operation_id).phase == PHASE_EXCEL_LAUNCHING  # type: ignore[union-attr]
        owned = journal.record_excel_owned(
            operation_id, owner_id="owner-1", pair_nonce="nonce-1", lease=_owned_lease()
        )
        assert owned.phase == PHASE_EXCEL_OWNED
        assert journal.authorize_excel_ack(operation_id, owner_id="owner-1", pair_nonce="nonce-1")["excel_pid"] == 202
        with pytest.raises(JournalTransitionError):
            journal.record_excel_launching(operation_id, owner_id="owner-1", pair_nonce="nonce-1", lease=_adapter_lease())
        with pytest.raises(RegistryConflictError):
            journal.record_excel_owned(
                operation_id, owner_id="owner-1", pair_nonce="nonce-1",
                lease={**_owned_lease(), "excel_pid": 204},
            )
    finally:
        storage.close()


def test_v3_structured_primary_and_cleanup_failure_survive_restart(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        journal = WorkbookOperationJournal(storage)
        operation_id = _operation(journal, storage)
        failed = journal.record_failure(
            operation_id,
            expected_phase="planned",
            primary_failure={"stage": "excel_open", "code": "com_open_failed", "message": "COM open failed",
                             "hresult": -2147352567, "winerror": 5},
            cleanup_failure={"stage": "cleanup", "code": "excel_terminate_timeout", "message": "wait timed out",
                             "hresult": None, "winerror": 1460},
        )
        assert failed.phase == "manual_repair"
        assert failed["failure_code"] == "com_open_failed"
        assert failed["primary_failure_hresult"] == -2147352567
        assert failed["cleanup_failure_winerror"] == 1460
        with pytest.raises(RegistryConflictError):
            journal.record_failure(operation_id, expected_phase="planned",
                                   primary_failure={"stage": "other", "code": "replacement", "message": "replacement",
                                                    "hresult": None, "winerror": None})
        storage.close()
        restarted = RegistryStorage(storage.path)
        try:
            restored = WorkbookOperationJournal(restarted).get(operation_id)
            assert restored and restored["primary_failure_code"] == "com_open_failed"
            assert restored["cleanup_failure_code"] == "excel_terminate_timeout"
        finally:
            restarted.close()
    finally:
        if storage.connection:
            pass


def test_v3_owned_lease_preserves_adapter_identity_and_concurrent_exact_replay(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    path = storage.path
    try:
        journal = WorkbookOperationJournal(storage)
        operation_id = _operation(journal, storage)
        journal.transition(operation_id, expected_phase="planned", next_phase=PHASE_STAGED,
                           hashes={"pre_hash": "pre", "staged_hash": "staged"})
        journal.record_excel_launching(operation_id, owner_id="owner-1", pair_nonce="nonce-1", lease=_adapter_lease())
        swapped = {**_owned_lease(), "adapter_pid": 404}
        with pytest.raises(RegistryConflictError):
            journal.record_excel_owned(operation_id, owner_id="owner-1", pair_nonce="nonce-1", lease=swapped)
        launching = journal.get(operation_id)
        assert launching and launching.phase == PHASE_EXCEL_LAUNCHING and launching["adapter_pid"] == 101
    finally:
        storage.close()

    barrier = threading.Barrier(2)
    outcomes: list[object] = []

    def own() -> None:
        worker = RegistryStorage(path)
        try:
            barrier.wait(timeout=3)
            outcomes.append(WorkbookOperationJournal(worker).record_excel_owned(
                operation_id, owner_id="owner-1", pair_nonce="nonce-1", lease=_owned_lease()
            ).phase)
        except BaseException as error:  # assertions below retain both racing outcomes
            outcomes.append(error)
        finally:
            worker.close()

    first, second = threading.Thread(target=own), threading.Thread(target=own)
    first.start(); second.start(); first.join(timeout=4); second.join(timeout=4)
    assert not first.is_alive() and not second.is_alive()
    assert outcomes == [PHASE_EXCEL_OWNED, PHASE_EXCEL_OWNED]


def test_v3_cleanup_failure_is_write_once_with_concurrent_exact_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    path = storage.path
    cleanup = {"stage": "cleanup", "code": "terminate_timeout", "message": "timeout", "hresult": None, "winerror": 1460}
    try:
        journal = WorkbookOperationJournal(storage)
        operation_id = _operation(journal, storage)
        journal.record_failure(operation_id, expected_phase="planned", primary_failure={
            "stage": "open", "code": "open_failed", "message": "open", "hresult": -1, "winerror": 5,
        })
    finally:
        storage.close()

    barrier = threading.Barrier(2)
    outcomes: list[object] = []
    original_get = WorkbookOperationJournal.get
    local = threading.local()

    def pause_after_initial_read(self: WorkbookOperationJournal, requested_operation_id: str):
        value = original_get(self, requested_operation_id)
        if requested_operation_id == operation_id and not getattr(local, "cleanup_read", False):
            local.cleanup_read = True
            barrier.wait(timeout=3)
        return value

    def cleanup_writer() -> None:
        worker = RegistryStorage(path)
        try:
            outcomes.append(WorkbookOperationJournal(worker).record_cleanup_failure(
                operation_id, cleanup_failure=cleanup
            )["cleanup_failure_code"])
        except BaseException as error:
            outcomes.append(error)
        finally:
            worker.close()

    with monkeypatch.context() as context:
        context.setattr(WorkbookOperationJournal, "get", pause_after_initial_read)
        first, second = threading.Thread(target=cleanup_writer), threading.Thread(target=cleanup_writer)
        first.start(); second.start(); first.join(timeout=4); second.join(timeout=4)
        assert not first.is_alive() and not second.is_alive()
    assert outcomes == ["terminate_timeout", "terminate_timeout"]
    reopened = RegistryStorage(path)
    try:
        with pytest.raises(RegistryConflictError):
            WorkbookOperationJournal(reopened).record_cleanup_failure(
                operation_id,
                cleanup_failure={**cleanup, "code": "different", "message": "different"},
            )
    finally:
        reopened.close()


def test_v3_cleanup_failure_differing_concurrent_writers_conflict_and_keep_winner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    path = storage.path
    first_cleanup = {"stage": "cleanup", "code": "terminate_timeout", "message": "timeout", "hresult": None, "winerror": 1460}
    second_cleanup = {"stage": "cleanup", "code": "terminate_denied", "message": "denied", "hresult": None, "winerror": 5}
    try:
        journal = WorkbookOperationJournal(storage)
        operation_id = _operation(journal, storage)
        journal.record_failure(operation_id, expected_phase="planned", primary_failure={
            "stage": "open", "code": "open_failed", "message": "open", "hresult": -1, "winerror": 5,
        })
    finally:
        storage.close()

    barrier = threading.Barrier(2)
    outcomes: list[object] = []
    original_get = WorkbookOperationJournal.get
    local = threading.local()

    def pause_after_initial_read(self: WorkbookOperationJournal, requested_operation_id: str):
        value = original_get(self, requested_operation_id)
        if requested_operation_id == operation_id and not getattr(local, "cleanup_read", False):
            local.cleanup_read = True
            barrier.wait(timeout=3)
        return value

    def cleanup_writer(value: dict[str, object]) -> None:
        worker = RegistryStorage(path)
        try:
            outcomes.append(WorkbookOperationJournal(worker).record_cleanup_failure(
                operation_id, cleanup_failure=value
            )["cleanup_failure_code"])
        except BaseException as error:
            outcomes.append(error)
        finally:
            worker.close()

    with monkeypatch.context() as context:
        context.setattr(WorkbookOperationJournal, "get", pause_after_initial_read)
        first = threading.Thread(target=cleanup_writer, args=(first_cleanup,))
        second = threading.Thread(target=cleanup_writer, args=(second_cleanup,))
        first.start(); second.start(); first.join(timeout=4); second.join(timeout=4)
        assert not first.is_alive() and not second.is_alive()
    assert len([value for value in outcomes if isinstance(value, str)]) == 1
    assert len([value for value in outcomes if isinstance(value, RegistryConflictError)]) == 1
    reopened = RegistryStorage(path)
    try:
        stored = WorkbookOperationJournal(reopened).get(operation_id)
        assert stored and stored["cleanup_failure_code"] in {"terminate_timeout", "terminate_denied"}
        assert stored["cleanup_failure_code"] == next(value for value in outcomes if isinstance(value, str))
    finally:
        reopened.close()


def test_v3_failure_envelope_requires_exact_complete_typed_fields(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        journal = WorkbookOperationJournal(storage)
        operation_id = _operation(journal, storage)
        invalid = (
            {"stage": "open", "code": "failed", "message": "failure", "hresult": None},
            {"stage": "open", "code": "failed", "message": "", "hresult": None, "winerror": None},
            {"stage": "open", "code": "failed", "message": "failure", "hresult": "bad", "winerror": None},
            {"stage": "open", "code": "failed", "message": "failure", "hresult": None, "winerror": True},
        )
        for envelope in invalid:
            with pytest.raises(RegistryError):
                journal.record_failure(operation_id, expected_phase="planned", primary_failure=envelope)
    finally:
        storage.close()
