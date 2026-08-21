from __future__ import annotations

import hashlib
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from rns_import_server.new_row_action_store import NewRowActionStore
from rns_import_server.registry_storage import RegistryStorage
from rns_import_server.workbook_authority import WorkbookAuthorityEnrollment, WorkbookAuthorityStore
from rns_import_server.workbook_authority_refresh import refresh_published_authority
from rns_import_server.workbook_finalization import finalize_published_binding, finalize_published_operation
from rns_import_server.workbook_operation_journal import PHASE_BACKUP_VERIFIED, WorkbookOperationJournal
from rns_import_server.workbook_projection import GroupOwnershipEvidence, TemplateCellEvidence


def _published(tmp_path: Path, *, mode: str, target_row: int) -> tuple[RegistryStorage, str, Path]:
    storage = RegistryStorage.bootstrap(tmp_path / "runtime")
    construction = storage.list_constructions()[0]
    target = tmp_path / "disposable.xlsx"
    target.write_bytes(b"before authority refresh")
    operation_id = f"{mode}-{target_row}"
    actions = NewRowActionStore(storage)
    actions.register(action_id=operation_id, job_id="job", construction_id=construction.id, workbook_contract_id="contract",
                     target_identity="target", target_path=str(target), capability="capability")
    WorkbookAuthorityStore(storage).enroll(WorkbookAuthorityEnrollment(
        action_id=operation_id, construction_id=construction.id, workbook_contract_id="contract", target_identity="target",
        target_path=str(target), sheet_identity="sheet", template_version="template",
        source_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        template_cells=tuple(TemplateCellEvidence(3, column, f"template-{column}") for column in range(1, 25)),
        group_ownership=tuple(GroupOwnershipEvidence(row, row == 2) for row in range(1, 5)), max_row=4,
    ))
    journal = WorkbookOperationJournal(storage)
    journal.create(operation_id=operation_id, idempotency_key=f"key-{operation_id}", consumer_id=operation_id,
                   owner_id="owner", pair_nonce="nonce", construction_id=construction.id, operation_kind="new_row",
                   mutation_mode=mode, target_identity="target", sheet_identity="sheet", template_version="template",
                   expected_generation=storage.generation, intent_version="intent-v3", intent_digest="intent",
                   manifest_version="group-row-manifest-v3", manifest_digest="manifest", operation_directory="operation",
                   canonical_rns="RU-00000000-00-2026", workbook_contract_id="contract")
    pre_hash = hashlib.sha256(target.read_bytes()).hexdigest()
    # The current publisher deliberately remains v2/out of scope.  These
    # tests construct only the frozen v3 durable journal evidence.
    storage.connection.execute(
        "UPDATE workbook_operation_journal SET phase=?, pre_hash=?, staged_hash='s', validation_digest='v', backup_hash='b' WHERE operation_id=?",
        (PHASE_BACKUP_VERIFIED, pre_hash, operation_id),
    )
    target.write_bytes(f"after {mode} row {target_row}".encode())
    post_hash = hashlib.sha256(target.read_bytes()).hexdigest()
    journal.record_finalization_authority(
        operation_id, expected_phase=PHASE_BACKUP_VERIFIED, post_hash=post_hash,
        payload={"action_id": operation_id, "target_row": target_row,
                 "report_payload": {"final_state": {"workbook_sha256": post_hash}}},
    )
    journal.transition(operation_id, expected_phase=PHASE_BACKUP_VERIFIED, next_phase="published")
    assert actions.reserve_pending_to_publishing(operation_id, job_authorization="capability")
    return storage, operation_id, target


@pytest.mark.parametrize(("mode", "target_row", "expected_rows", "expected_template_row", "expected_max"), [
    ("blank_fill", 3, (False, True, True, False), 3, 4),
    ("middle_insert", 3, (False, True, True, False, False), 4, 5),
])
def test_refresh_applies_only_the_frozen_evidence_mapping(
    tmp_path: Path, mode: str, target_row: int, expected_rows: tuple[bool, ...], expected_template_row: int, expected_max: int,
) -> None:
    storage, operation_id, target = _published(tmp_path, mode=mode, target_row=target_row)
    try:
        before_target = target.read_bytes()
        result = refresh_published_authority(storage, operation_id)
        authority = storage.connection.execute("SELECT * FROM workbook_authorities WHERE action_id=?", (operation_id,)).fetchone()
        receipt = storage.connection.execute("SELECT * FROM workbook_authority_refresh_receipts WHERE operation_id=?", (operation_id,)).fetchone()
        assert result.refreshed and result.error_code is None and target.read_bytes() == before_target
        assert authority is not None and receipt is not None
        import json
        assert tuple(item["owned"] for item in json.loads(authority["ownership_evidence"])) == expected_rows
        assert {item["row"] for item in json.loads(authority["template_evidence"])} == {expected_template_row}
        assert (authority["max_row"], receipt["target_row"], receipt["generation_after"]) == (expected_max, target_row, authority["registry_generation"])
    finally:
        storage.close()


def test_exact_refresh_replay_is_a_zero_write_and_binding_requires_receipt(tmp_path: Path) -> None:
    storage, operation_id, _ = _published(tmp_path, mode="blank_fill", target_row=2)
    try:
        refused = finalize_published_binding(storage, operation_id)
        assert (refused.status, refused.error_code) == ("manual_repair", "finalization_authority_refresh_required")
    finally:
        storage.close()

    storage, operation_id, _ = _published(tmp_path / "replay", mode="blank_fill", target_row=2)
    try:
        first = refresh_published_authority(storage, operation_id)
        authority = dict(storage.connection.execute("SELECT * FROM workbook_authorities WHERE action_id=?", (operation_id,)).fetchone())
        receipt = dict(storage.connection.execute("SELECT * FROM workbook_authority_refresh_receipts WHERE operation_id=?", (operation_id,)).fetchone())
        generation = storage.generation
        assert refresh_published_authority(storage, operation_id) == first
        assert (dict(storage.connection.execute("SELECT * FROM workbook_authorities WHERE action_id=?", (operation_id,)).fetchone()),
                dict(storage.connection.execute("SELECT * FROM workbook_authority_refresh_receipts WHERE operation_id=?", (operation_id,)).fetchone()),
                storage.generation) == (authority, receipt, generation)
    finally:
        storage.close()


def test_invalid_current_target_is_durable_manual_repair_without_successor(tmp_path: Path) -> None:
    storage, operation_id, target = _published(tmp_path, mode="blank_fill", target_row=2)
    try:
        target.write_bytes(b"contradiction")
        result = refresh_published_authority(storage, operation_id)
        assert result.status == "manual_repair"
        assert storage.connection.execute("SELECT COUNT(*) FROM workbook_authority_refresh_receipts").fetchone()[0] == 0
    finally:
        storage.close()


def test_receipt_storage_failure_rolls_back_the_successor_and_keeps_published_pending(tmp_path: Path) -> None:
    storage, operation_id, _ = _published(tmp_path, mode="blank_fill", target_row=2)
    try:
        before = dict(storage.connection.execute("SELECT * FROM workbook_authorities WHERE action_id=?", (operation_id,)).fetchone())
        storage.connection.execute(
            "CREATE TRIGGER fail_authority_refresh BEFORE INSERT ON workbook_authority_refresh_receipts "
            "BEGIN SELECT RAISE(ABORT, 'injected'); END"
        )
        result = refresh_published_authority(storage, operation_id)
        operation = WorkbookOperationJournal(storage).get(operation_id)
        assert (result.status, result.refreshed, result.error_code) == (
            "published_pending_finalization", False, "workbook_authority_refresh_storage_failed",
        )
        assert dict(storage.connection.execute("SELECT * FROM workbook_authorities WHERE action_id=?", (operation_id,)).fetchone()) == before
        assert operation is not None and operation.phase == "published"
        assert storage.connection.execute("SELECT COUNT(*) FROM workbook_authority_refresh_receipts").fetchone()[0] == 0
    finally:
        storage.close()


@pytest.mark.parametrize(("mode", "target_row", "forged_template_row"), [
    ("blank_fill", 3, 4),
    ("middle_insert", 3, 3),
])
def test_replay_reconstructs_receipt_bound_predecessor_and_rejects_forged_successor(
    tmp_path: Path, mode: str, target_row: int, forged_template_row: int,
) -> None:
    storage, operation_id, _ = _published(tmp_path, mode=mode, target_row=target_row)
    try:
        assert refresh_published_authority(storage, operation_id).refreshed
        authority = storage.connection.execute("SELECT * FROM workbook_authorities WHERE action_id=?", (operation_id,)).fetchone()
        assert authority is not None
        forged_template = json.loads(authority["template_evidence"])
        for item in forged_template:
            item["row"] = forged_template_row
        encoded = json.dumps(forged_template, ensure_ascii=False, separators=(",", ":"))
        storage.connection.execute(
            "UPDATE workbook_authorities SET template_evidence=?, template_digest=? WHERE action_id=?",
            (encoded, hashlib.sha256(encoded.encode()).hexdigest(), operation_id),
        )
        result = refresh_published_authority(storage, operation_id)
        assert (result.status, result.error_code) == ("manual_repair", "workbook_authority_refresh_receipt_invalid")
    finally:
        storage.close()


def test_concurrent_exact_refresh_commits_one_successor_and_receipt(tmp_path: Path) -> None:
    storage, operation_id, _ = _published(tmp_path, mode="blank_fill", target_row=3)
    path = storage.path
    before = storage.generation
    storage.close()
    barrier = Barrier(2)

    def refresh() -> bool:
        connection = RegistryStorage(path)
        try:
            barrier.wait()
            return refresh_published_authority(connection, operation_id).refreshed
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert all(future.result() for future in (executor.submit(refresh), executor.submit(refresh)))
    verifier = RegistryStorage(path)
    try:
        assert (verifier.generation, verifier.connection.execute("SELECT COUNT(*) FROM workbook_authority_refresh_receipts").fetchone()[0]) == (before + 1, 1)
    finally:
        verifier.close()


@pytest.mark.parametrize("manifest_version", ["group-row-manifest-v1", "group-row-manifest-v2"])
def test_exact_legacy_manifest_versions_keep_finalizer_behavior(tmp_path: Path, manifest_version: str) -> None:
    storage, operation_id, _ = _published(tmp_path, mode="blank_fill", target_row=2)
    try:
        storage.connection.execute("UPDATE workbook_operation_journal SET manifest_version=? WHERE operation_id=?", (manifest_version, operation_id))
        assert finalize_published_operation(storage, operation_id).status == "finalized"
        assert storage.connection.execute("SELECT COUNT(*) FROM workbook_authority_refresh_receipts").fetchone()[0] == 0
    finally:
        storage.close()


def test_unknown_manifest_blocks_before_any_finalizer_or_refresh_write(tmp_path: Path) -> None:
    storage, operation_id, _ = _published(tmp_path, mode="blank_fill", target_row=2)
    try:
        storage.connection.execute("UPDATE workbook_operation_journal SET manifest_version='group-row-manifest-v4' WHERE operation_id=?", (operation_id,))
        result = finalize_published_operation(storage, operation_id)
        operation = WorkbookOperationJournal(storage).get(operation_id)
        assert (result.status, result.error_code) == ("manual_repair", "finalization_authority_refresh_required")
        assert operation is not None and (operation["binding_finalized"], operation["history_finalized"], operation["report_finalized"], operation["capability_finalized"]) == (0, 0, 0, 0)
        assert storage.connection.execute("SELECT COUNT(*) FROM workbook_authority_refresh_receipts").fetchone()[0] == 0
    finally:
        storage.close()


def test_full_v3_finalizer_refreshes_before_binding_and_legacy_stays_covered_elsewhere(tmp_path: Path) -> None:
    storage, operation_id, target = _published(tmp_path, mode="blank_fill", target_row=2)
    try:
        published_bytes = target.read_bytes()
        result = finalize_published_operation(storage, operation_id)
        operation = WorkbookOperationJournal(storage).get(operation_id)
        assert result.status == "finalized"
        assert operation is not None and operation["binding_finalized"] == 1
        assert storage.connection.execute("SELECT COUNT(*) FROM workbook_authority_refresh_receipts").fetchone()[0] == 1
        assert target.read_bytes() == published_bytes
    finally:
        storage.close()
