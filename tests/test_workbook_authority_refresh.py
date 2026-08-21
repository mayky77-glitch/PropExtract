from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
import threading

import pytest

from rns_import_server.new_row_action_store import NewRowActionStore
from rns_import_server.registry_storage import RegistryStorage
from rns_import_server.workbook_authority import (
    RegistryWorkbookProjectionAuthority, WorkbookAuthorityEnrollment, WorkbookAuthorityError, WorkbookAuthorityStore,
)
from rns_import_server.workbook_authority_refresh import (
    AuthorityRefreshError, refresh_published_authority, verify_authority_refresh_receipt,
)
from rns_import_server.workbook_finalization_snapshot import build_payload
from rns_import_server.workbook_operation_journal import WorkbookOperationJournal
from rns_import_server.workbook_projection import GroupOwnershipEvidence, TemplateCellEvidence


def _setup(tmp_path: Path, mode: str = "blank_fill", row: int = 2) -> tuple[RegistryStorage, str, Path, str, str]:
    storage = RegistryStorage.create_seed(tmp_path / "registry.sqlite3", [{
        "seed_entry_id": "seed", "code_prefix": "123-1234567", "official_name": "Стройка", "status": "active",
    }])
    construction_id = storage.list_constructions()[0].id
    operation_id = "action"
    target = tmp_path / "target.xlsx"
    pre, post = b"before", b"after"
    target.write_bytes(pre)
    NewRowActionStore(storage).register(
        action_id=operation_id, job_id="job", construction_id=construction_id, workbook_contract_id="contract",
        target_identity="target", target_path=str(target), capability="capability",
    )
    WorkbookAuthorityStore(storage).enroll(WorkbookAuthorityEnrollment(
        action_id=operation_id, construction_id=construction_id, workbook_contract_id="contract", target_identity="target",
        target_path=str(target), sheet_identity="Sheet", template_version="v1", source_sha256=hashlib.sha256(pre).hexdigest(),
        template_cells=tuple(TemplateCellEvidence(3, column, f"header-{column}") for column in range(1, 25)),
        group_ownership=tuple(GroupOwnershipEvidence(number, number == 3 and not (mode == "blank_fill" and row == 3)) for number in range(1, 4)), max_row=3,
    ))
    journal = WorkbookOperationJournal(storage)
    journal.create(
        operation_id=operation_id, idempotency_key="key", consumer_id=operation_id, owner_id="owner", pair_nonce="pair",
        construction_id=construction_id, operation_kind="new_row", mutation_mode=mode, target_identity="target",
        sheet_identity="Sheet", template_version="v1", expected_generation=storage.generation, intent_version="intent",
        intent_digest="digest", manifest_version="group-row-manifest-v3", manifest_digest="manifest", operation_directory="op",
        canonical_rns="rns", workbook_contract_id="contract",
    )
    post_hash = hashlib.sha256(post).hexdigest()
    storage.connection.execute(
        "UPDATE workbook_operation_journal SET phase='backup_verified', pre_hash=?, staged_hash=?, validation_digest=?, backup_hash=? "
        "WHERE operation_id=?",
        (hashlib.sha256(pre).hexdigest(), hashlib.sha256(pre).hexdigest(), "validation", "backup", operation_id),
    )
    journal.record_finalization_authority(
        operation_id, expected_phase="backup_verified", post_hash=post_hash,
        payload=build_payload(action_id=operation_id, target_row=row, report={"final_state": {"workbook_sha256": post_hash}}),
    )
    journal.transition(operation_id, expected_phase="backup_verified", next_phase="published")
    target.write_bytes(post)
    return storage, operation_id, target, hashlib.sha256(pre).hexdigest(), post_hash


@pytest.mark.parametrize(("mode", "row", "expected_rows", "template_row"), [
    ("blank_fill", 2, [(1, False), (2, True), (3, True)], 3),
    ("blank_fill", 3, [(1, False), (2, False), (3, True)], 3),
    ("middle_insert", 2, [(1, False), (2, True), (3, False), (4, True)], 4),
    ("middle_insert", 4, [(1, False), (2, False), (3, True), (4, True)], 3),
])
def test_refresh_maps_exact_successor_and_replay_is_zero_write(
    tmp_path: Path, mode: str, row: int, expected_rows: list[tuple[int, bool]], template_row: int,
) -> None:
    storage, operation_id, target, pre_hash, post_hash = _setup(tmp_path, mode, row)
    try:
        first = refresh_published_authority(storage, operation_id)
        assert (first.status, first.error_code, first.prior_generation, first.successor_generation) == (
            "refreshed", None, 1, 2,
        )
        authority = storage.connection.execute("SELECT * FROM workbook_authorities").fetchone()
        assert authority["source_sha256"] == post_hash
        assert [(item["row"], item["owned"]) for item in __import__("json").loads(authority["ownership_evidence"])] == expected_rows
        assert {item["row"] for item in __import__("json").loads(authority["template_evidence"])} == {template_row}
        assert authority["max_row"] == len(expected_rows)
        receipt = verify_authority_refresh_receipt(storage, operation_id)
        assert (receipt.pre_hash, receipt.post_hash, receipt.mutation_mode, receipt.target_row) == (pre_hash, post_hash, mode, row)
        before = (storage.generation, authority["created_at"], storage.connection.total_changes)
        replay = refresh_published_authority(storage, operation_id)
        after = storage.connection.execute("SELECT created_at FROM workbook_authorities").fetchone()[0]
        assert replay.status == "replayed"
        assert (storage.generation, after, storage.connection.total_changes) == before
    finally:
        storage.close()


@pytest.mark.parametrize("mutation", [
    "UPDATE workbook_finalization_snapshots SET digest='broken'",
    "UPDATE workbook_authorities SET ownership_count=1",
])
def test_missing_or_corrupt_durable_evidence_requires_manual_repair(tmp_path: Path, mutation: str) -> None:
    storage, operation_id, target, pre_hash, post_hash = _setup(tmp_path)
    try:
        storage.connection.execute(mutation)
        result = refresh_published_authority(storage, operation_id)
        assert result.status == "manual_repair"
        assert storage.connection.execute("SELECT COUNT(*) FROM workbook_authority_refresh_receipts").fetchone()[0] == 0
    finally:
        storage.close()


def test_target_mismatch_is_manual_repair_but_unreadable_target_is_pending(tmp_path: Path) -> None:
    storage, operation_id, target, pre_hash, post_hash = _setup(tmp_path)
    try:
        target.write_bytes(b"third")
        assert refresh_published_authority(storage, operation_id).status == "manual_repair"
        target.unlink()
        pending = refresh_published_authority(storage, operation_id)
        assert (pending.status, pending.error_code) == ("published_pending_finalization", "refresh_target_unreadable")
    finally:
        storage.close()


def test_receipt_is_immutable_and_forged_successor_fails_closed(tmp_path: Path) -> None:
    storage, operation_id, target, pre_hash, post_hash = _setup(tmp_path)
    try:
        assert refresh_published_authority(storage, operation_id).status == "refreshed"
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            storage.connection.execute("DELETE FROM workbook_authority_refresh_receipts WHERE operation_id=?", (operation_id,))
        storage.connection.execute("DROP TRIGGER workbook_authority_refresh_receipts_immutable_update")
        storage.connection.execute(
            "UPDATE workbook_authority_refresh_receipts SET successor_digest="
            "CASE WHEN substr(successor_digest,1,1)='a' THEN 'b' ELSE 'a' END || substr(successor_digest,2)"
        )
        with pytest.raises(AuthorityRefreshError):
            verify_authority_refresh_receipt(storage, operation_id)
    finally:
        storage.close()


def test_concurrent_exact_refresh_has_one_receipt_and_generation(tmp_path: Path) -> None:
    storage, operation_id, target, pre_hash, post_hash = _setup(tmp_path)
    results: list[str] = []

    def run() -> None:
        contender = RegistryStorage(storage.path)
        try:
            results.append(refresh_published_authority(contender, operation_id).status)
        finally:
            contender.close()

    try:
        first = threading.Thread(target=run)
        second = threading.Thread(target=run)
        first.start(); second.start(); first.join(timeout=2); second.join(timeout=2)
        assert not first.is_alive() and not second.is_alive()
        assert sorted(results) == ["refreshed", "replayed"]
        assert storage.generation == 2
        assert storage.connection.execute("SELECT COUNT(*) FROM workbook_authority_refresh_receipts").fetchone()[0] == 1
    finally:
        storage.close()


def test_receipt_insert_failure_rolls_back_authority_and_generation(tmp_path: Path) -> None:
    storage, operation_id, target, pre_hash, post_hash = _setup(tmp_path)
    try:
        storage.connection.execute(
            "CREATE TRIGGER injected_refresh_failure BEFORE INSERT ON workbook_authority_refresh_receipts "
            "BEGIN SELECT RAISE(ABORT, 'injected'); END"
        )
        result = refresh_published_authority(storage, operation_id)
        authority = storage.connection.execute("SELECT source_sha256, registry_generation FROM workbook_authorities").fetchone()
        assert (result.status, result.error_code) == ("published_pending_finalization", "refresh_sqlite_failed")
        assert (authority["source_sha256"], authority["registry_generation"], storage.generation) == (pre_hash, 1, 1)
        assert storage.connection.execute("SELECT COUNT(*) FROM workbook_authority_refresh_receipts").fetchone()[0] == 0
    finally:
        storage.close()


def test_shifted_successor_remains_rejected_by_unchanged_wa1_projection(tmp_path: Path) -> None:
    storage, operation_id, target, pre_hash, post_hash = _setup(tmp_path, "middle_insert", 2)
    try:
        assert refresh_published_authority(storage, operation_id).status == "refreshed"
        with pytest.raises(WorkbookAuthorityError, match="workbook_authority_corrupt"):
            RegistryWorkbookProjectionAuthority(storage, operation_id).read_authority()
    finally:
        storage.close()
