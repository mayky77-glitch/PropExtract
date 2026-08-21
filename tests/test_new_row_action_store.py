from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from rns_import_server.new_row_action_store import NewRowActionStore
from rns_import_server.registry_storage import RegistryConflictError, RegistryStorage
from rns_import_server.workbook_operation_journal import WorkbookOperationJournal


def test_register_reserve_replay_and_reopen_are_durable_and_capability_free(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path / "runtime")
    target = tmp_path / "registry.xlsx"; target.write_bytes(b"xlsx")
    secret = "do-not-persist-this-capability"
    try:
        construction = storage.list_constructions()[0]
        actions = NewRowActionStore(storage)
        registered = actions.register(
            action_id="action-1", job_id="job-1", construction_id=construction.id, workbook_contract_id="contract",
            target_identity="target", target_path=str(target), capability=secret,
        )
        assert registered.state == "pending"
        replay = actions.register(
            action_id="action-1", job_id="job-1", construction_id=construction.id, workbook_contract_id="contract",
            target_identity="target", target_path=str(target), capability=secret,
        )
        assert replay == registered
        with pytest.raises(RegistryConflictError, match="new_row_action_conflict"):
            actions.register(
                action_id="action-1", job_id="other", construction_id=construction.id, workbook_contract_id="contract",
                target_identity="target", target_path=str(target), capability=secret,
            )
        assert secret not in str(dict(storage.connection.execute("SELECT * FROM new_row_pending_actions").fetchone()))
        assert actions.reserve_pending_to_publishing("action-1", job_authorization=secret)
        assert not actions.reserve_pending_to_publishing("action-1", job_authorization=secret)
        assert actions.reopen_after_pre_hash_failure("action-1", job_authorization=secret)
        assert actions.get("action-1").state == "pending"  # type: ignore[union-attr]
        assert actions.reserve_pending_to_publishing("action-1", job_authorization=secret)
        journal = WorkbookOperationJournal(storage)
        journal.create(
            operation_id="action-1", idempotency_key="key-1", consumer_id="action-1", owner_id="owner", pair_nonce="nonce",
            construction_id=construction.id, operation_kind="new_row", mutation_mode="blank_fill", target_identity="target",
            sheet_identity="sheet", template_version="template", expected_generation=storage.generation, intent_version="intent",
            intent_digest="intent", manifest_version="manifest", manifest_digest="manifest", operation_directory="operation",
            canonical_rns="RU-00000000-00-2026", workbook_contract_id="contract",
        )
        assert not actions.reopen_after_pre_hash_failure("action-1", job_authorization=secret)
    finally:
        storage.close()


def test_two_connections_reserve_exactly_one_pending_action(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path / "runtime")
    target = tmp_path / "registry.xlsx"; target.write_bytes(b"xlsx")
    construction = storage.list_constructions()[0]
    NewRowActionStore(storage).register(action_id="action-1", job_id="job", construction_id=construction.id,
                                        workbook_contract_id="contract", target_identity="target", target_path=str(target), capability="cap")
    path = storage.path; storage.close()
    def reserve() -> bool:
        connection = RegistryStorage(path)
        try:
            return NewRowActionStore(connection).reserve_pending_to_publishing("action-1", job_authorization="cap")
        finally:
            connection.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: reserve(), range(2))) == [False, True]
