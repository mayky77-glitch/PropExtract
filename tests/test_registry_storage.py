from __future__ import annotations

import json
from pathlib import Path

import pytest

from rns_import_server.registry_storage import (
    RegistryCorruptError,
    RegistrySchemaError,
    RegistryStorage,
    load_seed_manifest,
    sha256_file,
)


def _seed(path: Path, revision: str, entries: list[dict[str, str]]) -> tuple[Path, Path]:
    seed = path / f"{revision}.sqlite3"
    storage = RegistryStorage.create_seed(seed, entries, seed_revision=revision)
    storage.close()
    manifest = path / f"{revision}.json"
    manifest.write_text(json.dumps({"schema_version": 1, "seed_revision": revision, "entry_count": len(entries), "sha256": sha256_file(seed)}), encoding="utf-8")
    return seed, manifest


def test_seed_reconciliation_preserves_local_and_records_divergence(tmp_path: Path) -> None:
    first_entries = [{"seed_entry_id": "one", "code_prefix": "111-1111111", "official_name": "Первая", "status": "active"}]
    seed1, manifest1 = _seed(tmp_path, "r1", first_entries)
    runtime = RegistryStorage.bootstrap(tmp_path / "runtime", seed_path=seed1, manifest_path=manifest1)
    try:
        runtime.create_construction(code_prefix="222-2222222", official_name="Только локальная", status="draft")
        row = runtime.list_constructions()[0]
        runtime.connection.execute("UPDATE constructions SET official_name='Локальная правка', normalized_name='локальная правка' WHERE id=?", (row.id,))
        second_entries = [{"seed_entry_id": "one", "code_prefix": "111-1111111", "official_name": "Изменена поставка", "status": "active"}]
        seed2, manifest2 = _seed(tmp_path, "r2", second_entries)
        runtime.reconcile_seed(seed2, manifest2)
        assert runtime.count() == 2
        assert runtime.get_construction(row.id).official_name == "Локальная правка"  # type: ignore[union-attr]
        assert runtime.conflicts()[0]["kind"] == "local_seed_divergence"
    finally:
        runtime.close()


def test_untouched_removal_archives_and_bound_rename_is_alignment_conflict(tmp_path: Path) -> None:
    entries = [{"seed_entry_id": "one", "code_prefix": "111-1111111", "official_name": "Первая", "status": "active"}]
    seed1, manifest1 = _seed(tmp_path, "r1", entries)
    runtime = RegistryStorage.bootstrap(tmp_path / "runtime", seed_path=seed1, manifest_path=manifest1)
    try:
        row = runtime.list_constructions()[0]
        runtime.bind_construction(row.id, workbook_contract_id="contract", target_identity="target", sheet_identity="sheet", template_version="v1", verified_state="verified", expected_generation=runtime.generation)
        seed2, manifest2 = _seed(tmp_path, "r2", [{"seed_entry_id": "one", "code_prefix": "111-1111111", "official_name": "Переименована", "status": "active"}])
        runtime.reconcile_seed(seed2, manifest2)
        assert runtime.get_construction(row.id).official_name == "Первая"  # type: ignore[union-attr]
        assert runtime.conflicts()[0]["kind"] == "binding_alignment_conflict"
        seed3, manifest3 = _seed(tmp_path, "r3", [])
        # Existing bound entry is untouched and can be safely archived on removal.
        runtime.reconcile_seed(seed3, manifest3)
        assert runtime.get_construction(row.id).status == "archived"  # type: ignore[union-attr]
    finally:
        runtime.close()


def test_corrupt_seed_is_rejected(tmp_path: Path) -> None:
    seed = tmp_path / "broken.sqlite3"
    seed.write_bytes(b"not sqlite")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": 1, "seed_revision": "r", "entry_count": 0, "sha256": sha256_file(seed)}), encoding="utf-8")
    with pytest.raises(RegistryCorruptError):
        RegistryStorage.bootstrap(tmp_path / "runtime", seed_path=seed, manifest_path=manifest)


def test_v0_migration_keeps_recoverable_backup_and_newer_schema_fails_closed(tmp_path: Path) -> None:
    runtime = RegistryStorage.bootstrap(tmp_path)
    path = runtime.path
    runtime.connection.execute("UPDATE registry_meta SET schema_version=0")
    runtime.close()
    migrated = RegistryStorage(path)
    try:
        assert migrated.connection.execute("SELECT schema_version FROM registry_meta").fetchone()[0] == 1
        assert path.with_suffix(".sqlite3.pre-migration.bak").is_file()
    finally:
        migrated.close()
    newer = RegistryStorage(path)
    newer.connection.execute("UPDATE registry_meta SET schema_version=2")
    newer.close()
    with pytest.raises(RegistrySchemaError):
        RegistryStorage(path)
