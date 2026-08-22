from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from rns_import_server.new_row_action_store import NewRowActionError, NewRowActionStore
from rns_import_server.registry_storage import RegistryConflictError, RegistryStorage
from rns_import_server.workbook_operation_journal import WorkbookOperationJournal


class _StringSubclass(str):
    pass


def _register_reserved(storage: RegistryStorage, target: Path, *, action_id: str = "action-1", capability: str = "cap") -> tuple[NewRowActionStore, str]:
    construction = storage.list_constructions()[0]
    actions = NewRowActionStore(storage)
    actions.register(action_id=action_id, job_id="job", construction_id=construction.id, workbook_contract_id="contract",
                     target_identity="target", target_path=str(target), capability=capability)
    assert actions.reserve_pending_to_publishing(action_id, job_authorization=capability)
    return actions, construction.id


def _planned_authority(storage: RegistryStorage, construction_id: str, target: Path, *, action_id: str = "action-1", expected: str = "a" * 64) -> None:
    storage.connection.execute(
        "INSERT INTO workbook_authorities VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (action_id, construction_id, "contract", "target", str(target.resolve()), "sheet", "template", expected,
         "[]", "b" * 64, 24, "[]", "c" * 64, 1, 2, storage.generation, "2026-01-01T00:00:00Z"),
    )
    WorkbookOperationJournal(storage).create(
        operation_id=action_id, idempotency_key=f"key-{action_id}", consumer_id=action_id, owner_id="owner", pair_nonce="nonce",
        construction_id=construction_id, operation_kind="new_row", mutation_mode="blank_fill", target_identity="target",
        sheet_identity="sheet", template_version="template", expected_generation=storage.generation, intent_version="intent",
        intent_digest="intent", manifest_version="manifest", manifest_digest="manifest", operation_directory="operation",
        canonical_rns="RU-00000000-00-2026", workbook_contract_id="contract",
    )


@pytest.mark.parametrize("capability", ["", "не-ASCII", b"bytes", 1, True, _StringSubclass("cap")])
def test_capability_is_exact_nonempty_ascii_before_any_write(tmp_path: Path, capability: object) -> None:
    storage = RegistryStorage.bootstrap(tmp_path / "runtime")
    target = tmp_path / "registry.xlsx"; target.write_bytes(b"xlsx")
    try:
        construction = storage.list_constructions()[0]
        with pytest.raises(NewRowActionError, match="new_row_action_authority_invalid"):
            NewRowActionStore(storage).register(
                action_id="action-1", job_id="job", construction_id=construction.id, workbook_contract_id="contract",
                target_identity="target", target_path=str(target), capability=capability,  # type: ignore[arg-type]
            )
        assert storage.connection.execute("SELECT COUNT(*) FROM new_row_pending_actions").fetchone()[0] == 0
    finally:
        storage.close()


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


def test_malformed_stored_digest_conflicts_on_registration_and_never_crashes_authorization(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path / "runtime")
    target = tmp_path / "registry.xlsx"; target.write_bytes(b"xlsx")
    try:
        construction = storage.list_constructions()[0]
        actions = NewRowActionStore(storage)
        actions.register(action_id="action-1", job_id="job", construction_id=construction.id, workbook_contract_id="contract",
                         target_identity="target", target_path=str(target), capability="cap")
        for malformed in ("A" * 64, "я" * 64, "short"):
            storage.connection.execute("UPDATE new_row_pending_actions SET capability_digest=? WHERE action_id='action-1'", (malformed,))
            with pytest.raises(RegistryConflictError, match="new_row_action_conflict"):
                actions.register(action_id="action-1", job_id="job", construction_id=construction.id, workbook_contract_id="contract",
                                 target_identity="target", target_path=str(target), capability="cap")
            assert not actions.reserve_pending_to_publishing("action-1", job_authorization="cap")
    finally:
        storage.close()


def test_existing_receipt_is_atomic_replay_safe_and_effectively_terminal(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path / "runtime")
    target = tmp_path / "registry.xlsx"; target.write_bytes(b"xlsx")
    try:
        actions, _ = _register_reserved(storage, target)
        receipt = actions.close_existing("action-1", job_authorization="cap", terminal_state="resolved_existing", observed_row=2,
                                         observed_workbook_hash="d" * 64)
        before = storage.connection.total_changes
        assert actions.close_existing("action-1", job_authorization="cap", terminal_state="resolved_existing", observed_row=2,
                                      observed_workbook_hash="d" * 64) == receipt
        assert storage.connection.total_changes == before
        assert actions.get("action-1").state == "resolved_existing"  # type: ignore[union-attr]
        assert storage.connection.execute("SELECT COUNT(*) FROM workbook_operation_journal").fetchone()[0] == 0
        with pytest.raises(NewRowActionError, match="new_row_action_outcome_conflict"):
            actions.close_existing("action-1", job_authorization="cap", terminal_state="existing_review", observed_row=2,
                                   observed_workbook_hash="d" * 64)
    finally:
        storage.close()


def test_pre_hash_classification_abandons_only_pristine_planned_authority(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path / "runtime")
    target = tmp_path / "registry.xlsx"; target.write_bytes(b"xlsx")
    try:
        actions, construction_id = _register_reserved(storage, target)
        _planned_authority(storage, construction_id, target)
        before = storage.connection.total_changes
        assert actions.classify_planned_pre_hash("action-1", job_authorization="cap", observed_pre_hash="a" * 64) == "live"
        assert storage.connection.total_changes == before
        assert actions.classify_planned_pre_hash("action-1", job_authorization="cap", observed_pre_hash="d" * 64) == "abandoned"
        journal = WorkbookOperationJournal(storage).get("action-1")
        assert journal is not None and (journal.phase, journal["failure_code"]) == ("abandoned", "planned_pre_hash_abandoned")
        assert WorkbookOperationJournal(storage).incomplete() == []
    finally:
        storage.close()
