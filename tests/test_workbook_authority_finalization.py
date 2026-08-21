from __future__ import annotations

import hashlib
from pathlib import Path
import threading

import pytest

import rns_import_server.workbook_finalization as finalization
from rns_import_server.new_row_action_store import NewRowActionStore
from rns_import_server.registry_storage import RegistryStorage
from rns_import_server.workbook_authority import WorkbookAuthorityEnrollment, WorkbookAuthorityStore
from rns_import_server.workbook_authority_refresh import AuthorityRefreshError, AuthorityRefreshResult
from rns_import_server.workbook_finalization import finalize_published_operation
from rns_import_server.workbook_finalization_snapshot import build_payload
from rns_import_server.workbook_operation_journal import WorkbookOperationJournal
from rns_import_server.workbook_projection import GroupOwnershipEvidence, TemplateCellEvidence


def _published(tmp_path: Path, *, manifest_version: object = "group-row-manifest-v3") -> tuple[RegistryStorage, str, Path]:
    storage = RegistryStorage.create_seed(tmp_path / "registry.sqlite3", [{
        "seed_entry_id": "seed", "code_prefix": "123-1234567", "official_name": "Стройка", "status": "active",
    }])
    operation_id = "action"
    construction_id = storage.list_constructions()[0].id
    target = tmp_path / "target.xlsx"; pre, post = b"before", b"after"; target.write_bytes(pre)
    NewRowActionStore(storage).register(
        action_id=operation_id, job_id="job", construction_id=construction_id, workbook_contract_id="contract",
        target_identity="target", target_path=str(target), capability="capability",
    )
    WorkbookAuthorityStore(storage).enroll(WorkbookAuthorityEnrollment(
        action_id=operation_id, construction_id=construction_id, workbook_contract_id="contract", target_identity="target",
        target_path=str(target), sheet_identity="Sheet", template_version="v1", source_sha256=hashlib.sha256(pre).hexdigest(),
        template_cells=tuple(TemplateCellEvidence(3, column, f"header-{column}") for column in range(1, 25)),
        group_ownership=tuple(GroupOwnershipEvidence(number, number == 3) for number in range(1, 4)), max_row=3,
    ))
    journal = WorkbookOperationJournal(storage)
    journal.create(
        operation_id=operation_id, idempotency_key="key", consumer_id=operation_id, owner_id="owner", pair_nonce="pair",
        construction_id=construction_id, operation_kind="new_row", mutation_mode="blank_fill", target_identity="target",
        sheet_identity="Sheet", template_version="v1", expected_generation=storage.generation, intent_version="intent",
        intent_digest="digest", manifest_version=manifest_version if type(manifest_version) is str else "manifest-v1",
        manifest_digest="manifest", operation_directory="op",
        canonical_rns="rns", workbook_contract_id="contract",
    )
    if type(manifest_version) is not str:
        storage.connection.execute(
            "UPDATE workbook_operation_journal SET manifest_version=? WHERE operation_id=?", (manifest_version, operation_id)
        )
    pre_hash, post_hash = hashlib.sha256(pre).hexdigest(), hashlib.sha256(post).hexdigest()
    storage.connection.execute(
        "UPDATE workbook_operation_journal SET phase='backup_verified', pre_hash=?, staged_hash=?, validation_digest=?, backup_hash=? WHERE operation_id=?",
        (pre_hash, pre_hash, "validation", "backup", operation_id),
    )
    journal.record_finalization_authority(
        operation_id, expected_phase="backup_verified", post_hash=post_hash,
        payload=build_payload(action_id=operation_id, target_row=2, report={"final_state": {"workbook_sha256": post_hash}}),
    )
    journal.transition(operation_id, expected_phase="backup_verified", next_phase="published")
    target.write_bytes(post)
    if type(manifest_version) is str and manifest_version in {"manifest-v1", "manifest-v2"}:
        assert NewRowActionStore(storage).reserve_pending_to_publishing(operation_id, job_authorization="capability")
    return storage, operation_id, target


def _downstream_counts(storage: RegistryStorage) -> tuple[int, int, int, int]:
    row = WorkbookOperationJournal(storage).get("action")
    return (
        row["binding_finalized"], row["history_finalized"], row["report_finalized"], row["capability_finalized"],
    )  # type: ignore[index]


def test_v3_refresh_and_receipt_precede_every_existing_finalizer_stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage, operation_id, target = _published(tmp_path); calls: list[str] = []
    try:
        for name, label in (("refresh_published_authority", "refresh"), ("verify_authority_refresh_receipt", "verify"),
                            ("_finalize_published_binding", "binding"), ("_finalize_published_history", "history"),
                            ("_publish_report_bytes", "report"), ("_consume_capability", "capability"),
                            ("_complete_finalization", "finalized")):
            original = getattr(finalization, name)

            def traced(*args: object, _original: object = original, _label: str = label, **kwargs: object) -> object:
                calls.append(_label)
                return _original(*args, **kwargs)  # type: ignore[operator]

            monkeypatch.setattr(finalization, name, traced)
        assert finalize_published_operation(storage, operation_id).status == "finalized"
        assert calls == ["refresh", "verify", "binding", "history", "report", "capability", "finalized"]
    finally:
        storage.close()


def test_restart_after_committed_refresh_replays_without_refresh_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage, operation_id, target = _published(tmp_path)
    original_binding = finalization._finalize_published_binding
    try:
        monkeypatch.setattr(finalization, "_finalize_published_binding", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("crash")))
        with pytest.raises(RuntimeError, match="crash"):
            finalize_published_operation(storage, operation_id)
        monkeypatch.setattr(finalization, "_finalize_published_binding", original_binding)
        evidence: list[tuple[int, int]] = []
        original_refresh = finalization.refresh_published_authority

        def replay(*args: object, **kwargs: object) -> object:
            before = (storage.generation, storage.connection.total_changes)
            result = original_refresh(*args, **kwargs)
            evidence.append((storage.generation - before[0], storage.connection.total_changes - before[1]))
            return result

        monkeypatch.setattr(finalization, "refresh_published_authority", replay)
        assert finalize_published_operation(storage, operation_id).status == "finalized"
        assert evidence == [(0, 0)]
    finally:
        storage.close()


def test_v3_transient_refresh_stays_publicly_pending_at_refresh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage, operation_id, target = _published(tmp_path)
    try:
        monkeypatch.setattr(finalization, "refresh_published_authority", lambda *args: AuthorityRefreshResult(
            operation_id, "published_pending_finalization", "refresh_target_unreadable",
        ))
        result = finalize_published_operation(storage, operation_id)
        assert (result.status, result.stage, result.next_stage, result.error_code, _downstream_counts(storage)) == (
            "published_pending_finalization", "refresh", "refresh", "refresh_target_unreadable", (0, 0, 0, 0),
        )
    finally:
        storage.close()


@pytest.mark.parametrize("code", ["refresh_evidence_contradictory", "refresh_receipt_missing", "refresh_receipt_corrupt"])
def test_v3_bad_refresh_or_receipt_is_durable_repair_before_downstream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: str,
) -> None:
    storage, operation_id, target = _published(tmp_path)
    try:
        if code == "refresh_evidence_contradictory":
            monkeypatch.setattr(finalization, "refresh_published_authority", lambda *args: AuthorityRefreshResult(operation_id, "manual_repair", code))
        else:
            monkeypatch.setattr(finalization, "verify_authority_refresh_receipt", lambda *args: (_ for _ in ()).throw(AuthorityRefreshError(code)))
        result = finalize_published_operation(storage, operation_id)
        assert (result.status, result.stage, result.error_code, _downstream_counts(storage)) == (
            "manual_repair", "refresh", code, (0, 0, 0, 0),
        )
    finally:
        storage.close()


def test_unknown_or_nonexact_manifest_fails_closed_before_refresh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for manifest in ("manifest-v3", b"manifest-v1"):
        storage, operation_id, target = _published(tmp_path, manifest_version=manifest)
        try:
            monkeypatch.setattr(finalization, "refresh_published_authority", lambda *args: (_ for _ in ()).throw(AssertionError("refresh")))
            result = finalize_published_operation(storage, operation_id)
            assert (result.status, result.stage, result.error_code, _downstream_counts(storage)) == (
                "manual_repair", "refresh", "finalization_manifest_invalid", (0, 0, 0, 0),
            )
        finally:
            storage.close()


@pytest.mark.parametrize("manifest", ["manifest-v1", "manifest-v2"])
def test_exact_legacy_manifest_preserves_finalizer_and_skips_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, manifest: str,
) -> None:
    storage, operation_id, target = _published(tmp_path, manifest_version=manifest)
    try:
        monkeypatch.setattr(finalization, "refresh_published_authority", lambda *args: (_ for _ in ()).throw(AssertionError("refresh")))
        assert finalize_published_operation(storage, operation_id).status == "finalized"
    finally:
        storage.close()


def test_concurrent_v3_finalization_has_one_refresh_and_no_workbook_or_native_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage, operation_id, target = _published(tmp_path); refresh_states: list[str] = []; statuses: list[str] = []
    start = threading.Barrier(2); lock = threading.Lock()
    original = finalization.refresh_published_authority

    def traced(*args: object, **kwargs: object) -> object:
        result = original(*args, **kwargs)
        with lock:
            refresh_states.append(result.status)  # type: ignore[union-attr]
        return result

    def run() -> None:
        contender = RegistryStorage(storage.path)
        try:
            start.wait(timeout=5)
            statuses.append(finalize_published_operation(contender, operation_id).status)
        finally:
            contender.close()

    try:
        monkeypatch.setattr(finalization, "refresh_published_authority", traced)
        first, second = threading.Thread(target=run), threading.Thread(target=run)
        first.start(); second.start(); first.join(timeout=5); second.join(timeout=5)
        assert not first.is_alive() and not second.is_alive()
        assert len(statuses) == 2 and all(status == "finalized" for status in statuses)
        assert refresh_states.count("refreshed") == 1 and set(refresh_states) <= {"refreshed", "replayed"}
        assert storage.connection.execute("SELECT COUNT(*) FROM workbook_authority_refresh_receipts").fetchone()[0] == 1
        assert storage.connection.execute("SELECT COUNT(*) FROM construction_bindings").fetchone()[0] == 1
        assert not hasattr(finalization, "excel_native") and not hasattr(finalization, "workbook")
    finally:
        storage.close()
