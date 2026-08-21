from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rns_import_server.new_row_action_store import NewRowActionStore
from rns_import_server.registry_storage import RegistryError, RegistryStorage
import rns_import_server.workbook_finalization as finalization
from rns_import_server.workbook_finalization import finalize_published_operation
from rns_import_server.workbook_operation_journal import PHASE_BACKUP_VERIFIED, WorkbookOperationJournal


def _published(storage: RegistryStorage, target: Path, *, operation_id: str = "report-operation") -> str:
    construction = storage.list_constructions()[0]
    target.write_bytes(b"published workbook")
    post_hash = hashlib.sha256(target.read_bytes()).hexdigest()
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
    journal.record_finalization_authority(
        operation_id, expected_phase=PHASE_BACKUP_VERIFIED, post_hash=post_hash,
        payload={"action_id": operation_id, "target_row": 6, "report_payload": {"final_state": {"workbook_sha256": post_hash}, "count": 3}},
    )
    journal.transition(operation_id, expected_phase=PHASE_BACKUP_VERIFIED, next_phase="published")
    actions = NewRowActionStore(storage)
    actions.register(action_id=operation_id, job_id="job", construction_id=construction.id, workbook_contract_id="contract",
                     target_identity="target", target_path=str(target), capability="capability")
    assert actions.reserve_pending_to_publishing(operation_id, job_authorization="capability")
    return operation_id


def _report(target: Path) -> Path:
    return target.with_name(f"{target.stem} — отчет PropExtract.json")


def test_full_finalizer_writes_snapshot_report_consumes_once_and_replays_without_write(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path / "registry")
    try:
        target = tmp_path / "book.xlsx"; operation_id = _published(storage, target)
        first = finalize_published_operation(storage, operation_id)
        report = _report(target); expected = b'{"count":3,"final_state":{"workbook_sha256":"' + hashlib.sha256(target.read_bytes()).hexdigest().encode() + b'"}}\n'
        assert (first.status, first.completed_stage, first.next_stage) == ("finalized", "finalized", None)
        assert report.read_bytes() == expected
        row = WorkbookOperationJournal(storage).get(operation_id)
        action = storage.connection.execute("SELECT state FROM new_row_pending_actions WHERE action_id=?", (operation_id,)).fetchone()
        assert row is not None and action is not None
        evidence = (row["updated_at"], row["finalized_at"], row["report_finalized_at"], row["capability_finalized_at"], report.stat().st_mtime_ns)
        assert (row["report_finalized"], row["capability_finalized"], action["state"]) == (1, 1, "consumed")
        replay = finalize_published_operation(storage, operation_id)
        row = WorkbookOperationJournal(storage).get(operation_id)
        assert (replay.status, (row["updated_at"], row["finalized_at"], row["report_finalized_at"], row["capability_finalized_at"], report.stat().st_mtime_ns)) == ("finalized", evidence)  # type: ignore[index]
    finally:
        storage.close()


def test_corrupt_or_symlink_report_is_replaced_without_touching_external_target(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path / "registry")
    try:
        target = tmp_path / "book.xlsx"; operation_id = _published(storage, target)
        report = _report(target); external = tmp_path / "external"
        external.write_text("do not replace")
        report.symlink_to(external)
        assert finalize_published_operation(storage, operation_id).status == "finalized"
        assert external.read_text() == "do not replace"
        assert not report.is_symlink()
    finally:
        storage.close()


def test_finalized_replay_restores_a_deleted_snapshot_report(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path / "registry")
    try:
        target = tmp_path / "book.xlsx"; operation_id = _published(storage, target)
        assert finalize_published_operation(storage, operation_id).status == "finalized"
        report = _report(target); report.unlink()
        assert finalize_published_operation(storage, operation_id).status == "finalized"
        assert json.loads(report.read_text(encoding="utf-8"))["final_state"]["workbook_sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
    finally:
        storage.close()


def test_target_hash_mismatch_is_durable_repair_and_never_overwrites_target(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path / "registry")
    try:
        target = tmp_path / "book.xlsx"; operation_id = _published(storage, target)
        target.write_bytes(b"third workbook")
        result = finalize_published_operation(storage, operation_id)
        row = WorkbookOperationJournal(storage).get(operation_id)
        assert (result.status, result.error_code, row.phase, target.read_bytes()) == ("manual_repair", "finalization_target_hash_mismatch", "manual_repair", b"third workbook")  # type: ignore[union-attr]
    finally:
        storage.close()


def test_missing_target_repairs_before_binding_or_history_side_effects(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path / "registry")
    try:
        target = tmp_path / "book.xlsx"; operation_id = _published(storage, target); target.unlink()
        result = finalize_published_operation(storage, operation_id)
        row = WorkbookOperationJournal(storage).get(operation_id)
        assert row is not None
        assert (result.status, result.error_code, row["binding_finalized"], row["history_finalized"],
                storage.connection.execute("SELECT COUNT(*) FROM construction_bindings").fetchone()[0],
                storage.connection.execute("SELECT COUNT(*) FROM new_row_action_history").fetchone()[0]) == (
                    "manual_repair", "finalization_target_hash_mismatch", 0, 0, 0, 0,
                )
    finally:
        storage.close()


def test_transient_target_read_stays_pending_without_binding_or_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage = RegistryStorage.bootstrap(tmp_path / "registry")
    try:
        target = tmp_path / "book.xlsx"; operation_id = _published(storage, target)
        monkeypatch.setattr(finalization, "_sha256_file", lambda path: (_ for _ in ()).throw(OSError("EIO")))
        result = finalize_published_operation(storage, operation_id)
        row = WorkbookOperationJournal(storage).get(operation_id)
        assert row is not None and (result.status, result.error_code, row["binding_finalized"], row["history_finalized"]) == (
            "published_pending_finalization", "finalization_report_verify_failed", 0, 0,
        )
    finally:
        storage.close()


def test_report_write_failure_after_history_resumes_without_reentering_earlier_stages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage = RegistryStorage.bootstrap(tmp_path / "registry")
    try:
        target = tmp_path / "book.xlsx"; operation_id = _published(storage, target)
        original = finalization._publish_report_bytes
        calls = 0
        def fail_once(path: Path, content: bytes) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("injected")
            original(path, content)
        monkeypatch.setattr(finalization, "_publish_report_bytes", fail_once)
        first = finalize_published_operation(storage, operation_id)
        durable = WorkbookOperationJournal(storage).get(operation_id)
        assert durable is not None and (first.error_code, durable["binding_finalized"], durable["history_finalized"], durable["report_finalized"]) == (
            "finalization_report_write_failed", 1, 1, 0,
        )
        assert finalize_published_operation(storage, operation_id).status == "finalized"
        assert calls == 2
    finally:
        storage.close()


def test_directory_fsync_failure_requires_a_second_publish_before_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage = RegistryStorage.bootstrap(tmp_path / "registry")
    try:
        target = tmp_path / "book.xlsx"; operation_id = _published(storage, target)
        original_fsync = finalization.os.fsync
        calls = 0
        def fail_first_directory(descriptor: int) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:  # file fsync succeeds; parent-dir fsync fails after replace
                raise OSError("directory fsync")
            original_fsync(descriptor)
        monkeypatch.setattr(finalization.os, "fsync", fail_first_directory)
        first = finalize_published_operation(storage, operation_id)
        row = WorkbookOperationJournal(storage).get(operation_id)
        assert row is not None and (first.error_code, row["report_finalized"], _report(target).exists()) == (
            "finalization_report_write_failed", 0, True,
        )
        assert finalize_published_operation(storage, operation_id).status == "finalized"
        # The retry fsyncs the existing exact report's parent rather than
        # replacing the report again.
        assert calls == 3
    finally:
        storage.close()


def test_receiptless_exact_report_is_fsynced_and_receipted_without_replacement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage = RegistryStorage.bootstrap(tmp_path / "registry")
    try:
        target = tmp_path / "book.xlsx"; operation_id = _published(storage, target)
        original_fsync = finalization.os.fsync
        calls = 0

        def fail_first_directory(descriptor: int) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("directory fsync")
            original_fsync(descriptor)

        monkeypatch.setattr(finalization.os, "fsync", fail_first_directory)
        assert finalize_published_operation(storage, operation_id).error_code == "finalization_report_write_failed"
        report = _report(target); before = report.stat()
        assert finalize_published_operation(storage, operation_id).status == "finalized"
        after = report.stat()
        assert (after.st_ino, after.st_mtime_ns, calls) == (before.st_ino, before.st_mtime_ns, 3)
    finally:
        storage.close()


def test_interstage_target_mutation_keeps_binding_but_blocks_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage = RegistryStorage.bootstrap(tmp_path / "registry")
    try:
        target = tmp_path / "book.xlsx"; operation_id = _published(storage, target)
        original = finalization._finalize_published_binding

        def bind_then_mutate(*args: object, **kwargs: object) -> finalization.FinalizationProgress:
            result = original(*args, **kwargs)
            target.write_bytes(b"mutated after binding")
            return result

        monkeypatch.setattr(finalization, "_finalize_published_binding", bind_then_mutate)
        result = finalize_published_operation(storage, operation_id)
        row = WorkbookOperationJournal(storage).get(operation_id)
        assert row is not None and (result.status, result.error_code, row["binding_finalized"], row["history_finalized"],
                                    storage.connection.execute("SELECT COUNT(*) FROM new_row_action_history").fetchone()[0]) == (
                                        "manual_repair", "finalization_target_hash_mismatch", 1, 0, 0,
                                    )
    finally:
        storage.close()


def test_generic_finalization_markers_and_terminal_transition_are_rejected(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path / "registry")
    try:
        target = tmp_path / "book.xlsx"; operation_id = _published(storage, target)
        journal = WorkbookOperationJournal(storage)
        with pytest.raises(RegistryError, match="finalization_receipt_required"):
            journal.finalize_flag(operation_id, "report_finalized")
        with pytest.raises(RegistryError, match="finalization_receipt_required"):
            journal.transition(operation_id, expected_phase="published", next_phase="finalized")
    finally:
        storage.close()
