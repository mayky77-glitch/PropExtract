from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from rns_import_server.new_row_action_store import NewRowActionStore
from rns_import_server.registry_storage import RegistryConflictError, RegistryStorage
from rns_import_server.workbook_authority import (
    RegistryWorkbookProjectionAuthority, WorkbookAuthorityEnrollment, WorkbookAuthorityError, WorkbookAuthorityStore,
)
from rns_import_server.workbook_projection import GroupOwnershipEvidence, TemplateCellEvidence


def _enrollment(path: Path, construction_id: str, **changes: object) -> WorkbookAuthorityEnrollment:
    values: dict[str, object] = {
        "action_id": "action", "construction_id": construction_id, "workbook_contract_id": "contract",
        "target_identity": "target", "target_path": str(path), "sheet_identity": "Sheet",
        "template_version": "v1", "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "template_cells": tuple(TemplateCellEvidence(3, column, f"header-{column}") for column in range(1, 25)),
        "group_ownership": tuple(GroupOwnershipEvidence(row, row == 2) for row in range(1, 4)), "max_row": 3,
    }
    values.update(changes)
    return WorkbookAuthorityEnrollment(**values)  # type: ignore[arg-type]


def _storage(tmp_path: Path) -> tuple[RegistryStorage, Path, str]:
    database = tmp_path / "registry.sqlite3"
    storage = RegistryStorage.create_seed(database, [{
        "seed_entry_id": "seed", "code_prefix": "123-1234567", "official_name": "Стройка", "status": "active",
    }])
    construction_id = storage.list_constructions()[0].id
    target = tmp_path / "private-copy.xlsx"
    target.write_bytes(b"private disposable bytes")
    NewRowActionStore(storage).register(
        action_id="action", job_id="job", construction_id=construction_id, workbook_contract_id="contract",
        target_identity="target", target_path=str(target), capability="capability",
    )
    return storage, target, construction_id


def test_enrollment_exact_replay_is_no_write_and_produces_explicit_authority(tmp_path: Path) -> None:
    storage, target, construction_id = _storage(tmp_path)
    try:
        store = WorkbookAuthorityStore(storage)
        enrollment = _enrollment(target, construction_id)
        store.enroll(enrollment)
        generation = storage.generation
        created_at = storage.connection.execute("SELECT created_at FROM workbook_authorities").fetchone()[0]
        store.enroll(enrollment)
        authority = RegistryWorkbookProjectionAuthority(storage, "action").read_authority()
        assert storage.generation == generation
        assert storage.connection.execute("SELECT created_at FROM workbook_authorities").fetchone()[0] == created_at
        assert authority.expected_source_sha256 == enrollment.source_sha256
        assert authority.group_ownership == enrollment.group_ownership
    finally:
        storage.close()


def test_enrollment_conflict_and_corrupt_authority_fail_closed(tmp_path: Path) -> None:
    storage, target, construction_id = _storage(tmp_path)
    try:
        store = WorkbookAuthorityStore(storage)
        enrollment = _enrollment(target, construction_id)
        store.enroll(enrollment)
        with pytest.raises(RegistryConflictError):
            store.enroll(_enrollment(target, construction_id, template_version="v2"))
        storage.connection.execute("UPDATE workbook_authorities SET ownership_count=1")
        with pytest.raises(WorkbookAuthorityError, match="workbook_authority_corrupt"):
            RegistryWorkbookProjectionAuthority(storage, "action").read_authority()
    finally:
        storage.close()


def test_producer_rejects_stale_generation_and_nonexact_optional_binding(tmp_path: Path) -> None:
    storage, target, construction_id = _storage(tmp_path)
    try:
        WorkbookAuthorityStore(storage).enroll(_enrollment(target, construction_id))
        with storage.transaction() as connection:
            connection.execute(
                "INSERT INTO construction_bindings VALUES ('binding', ?, 'other', 'target', 'Sheet', 'v1', 'verified', 't', 't', 't')",
                (construction_id,),
            )
        with pytest.raises(WorkbookAuthorityError, match="workbook_authority_binding_invalid"):
            RegistryWorkbookProjectionAuthority(storage, "action").read_authority()
        storage.connection.execute("DELETE FROM construction_bindings")
        with storage.transaction() as connection:
            storage._increment_generation(connection)
        with pytest.raises(WorkbookAuthorityError, match="workbook_authority_tuple_invalid"):
            RegistryWorkbookProjectionAuthority(storage, "action").read_authority()
    finally:
        storage.close()


@pytest.mark.parametrize("change", [
    {"target_path": "relative.xlsx"},
    {"source_sha256": "A" * 64},
    {"template_cells": tuple(TemplateCellEvidence(3, column, "x") for column in range(1, 24))},
    {"group_ownership": (GroupOwnershipEvidence(1, False), GroupOwnershipEvidence(3, False))},
])
def test_enrollment_rejects_noncanonical_or_incomplete_explicit_evidence(tmp_path: Path, change: dict[str, object]) -> None:
    storage, target, construction_id = _storage(tmp_path)
    try:
        with pytest.raises(WorkbookAuthorityError):
            WorkbookAuthorityStore(storage).enroll(_enrollment(target, construction_id, **change))
        assert storage.connection.execute("SELECT COUNT(*) FROM workbook_authorities").fetchone()[0] == 0
    finally:
        storage.close()
