from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rns_import_server.registry_storage import RegistryConflictError, RegistryError, RegistryStorage
from rns_import_server.workbook_finalization_snapshot import FinalizationSnapshotError, canonical_json
from rns_import_server.workbook_operation_journal import PHASE_BACKUP_VERIFIED, WorkbookOperationJournal


def _operation(storage: RegistryStorage) -> tuple[WorkbookOperationJournal, str]:
    journal = WorkbookOperationJournal(storage)
    construction = storage.list_constructions()[0]
    operation_id = "00000000-0000-4000-8000-000000000001"
    journal.create(
        operation_id=operation_id, idempotency_key="snapshot-key", consumer_id=operation_id, owner_id="owner", pair_nonce="pair",
        construction_id=construction.id, operation_kind="new_row", mutation_mode="blank_fill", target_identity="target",
        sheet_identity="sheet", template_version="template", expected_generation=storage.generation, intent_version="intent-v2",
        intent_digest="intent", manifest_version="manifest-v2", manifest_digest="manifest", operation_directory="operation",
        canonical_rns="RU-00000000-00-2026", workbook_contract_id="contract-v1",
    )
    journal.transition(operation_id, expected_phase="planned", next_phase="staged", hashes={"pre_hash": "pre", "staged_hash": "staged"})
    journal.transition(operation_id, expected_phase="staged", next_phase="validated", hashes={"validation_digest": "valid"})
    journal.transition(operation_id, expected_phase="validated", next_phase=PHASE_BACKUP_VERIFIED, hashes={"backup_hash": "backup"})
    return journal, operation_id


def _payload(operation_id: str, post_hash: str) -> dict[str, object]:
    return {"action_id": operation_id, "target_row": 6, "report_payload": {"final_state": {"workbook_sha256": post_hash}}}


def test_authority_atomically_binds_exact_snapshot_and_post_hash(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        journal, operation_id = _operation(storage); post_hash = "a" * 64
        first = journal.record_finalization_authority(operation_id, expected_phase=PHASE_BACKUP_VERIFIED, post_hash=post_hash, payload=_payload(operation_id, post_hash))
        timestamp = storage.connection.execute("SELECT created_at FROM workbook_finalization_snapshots WHERE operation_id=?", (operation_id,)).fetchone()[0]
        replay = journal.record_finalization_authority(operation_id, expected_phase=PHASE_BACKUP_VERIFIED, post_hash=post_hash, payload=_payload(operation_id, post_hash))
        assert (first["post_hash"], replay["post_hash"], storage.connection.execute("SELECT created_at FROM workbook_finalization_snapshots WHERE operation_id=?", (operation_id,)).fetchone()[0]) == (post_hash, post_hash, timestamp)
        with pytest.raises(RegistryConflictError, match="finalization_snapshot_conflict"):
            journal.record_finalization_authority(operation_id, expected_phase=PHASE_BACKUP_VERIFIED, post_hash="b" * 64, payload=_payload(operation_id, "b" * 64))
    finally:
        storage.close()


def test_invalid_authority_rolls_back_snapshot_and_post_hash(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        journal, operation_id = _operation(storage)
        with pytest.raises(RegistryError, match="finalization_snapshot_invalid"):
            journal.record_finalization_authority(operation_id, expected_phase=PHASE_BACKUP_VERIFIED, post_hash="a" * 64, payload=_payload(operation_id, "b" * 64))
        assert storage.connection.execute("SELECT post_hash FROM workbook_operation_journal WHERE operation_id=?", (operation_id,)).fetchone()[0] is None
        assert storage.connection.execute("SELECT 1 FROM workbook_finalization_snapshots WHERE operation_id=?", (operation_id,)).fetchone() is None
    finally:
        storage.close()


def test_v2_new_row_requires_contract_and_action_consumer_identity(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        journal = WorkbookOperationJournal(storage); construction = storage.list_constructions()[0]
        values = dict(operation_id="action", idempotency_key="key", consumer_id="other", owner_id="owner", pair_nonce="pair",
                      construction_id=construction.id, operation_kind="new_row", mutation_mode="blank_fill", target_identity="target",
                      sheet_identity="sheet", template_version="template", expected_generation=storage.generation, intent_version="intent-v2",
                      intent_digest="intent", manifest_version="manifest-v2", manifest_digest="manifest", operation_directory="operation",
                      canonical_rns="RU-00000000-00-2026")
        with pytest.raises(RegistryError, match="workbook_contract_id_required"):
            journal.create(**values)
        values["workbook_contract_id"] = "contract"
        with pytest.raises(RegistryError, match="consumer_action_identity_mismatch"):
            journal.create(**values)
    finally:
        storage.close()


@pytest.mark.parametrize("value", [{"x": float("nan")}, {1: "x"}, b"bytes"])
def test_snapshot_json_rejects_lossy_values(value: object) -> None:
    with pytest.raises(FinalizationSnapshotError):
        canonical_json(value)
