from __future__ import annotations

import json
from pathlib import Path
import shutil
import sqlite3
import threading
import time

import pytest

from rns_import_server.registry_storage import (
    RegistryCorruptError,
    RegistrySchemaError,
    RegistryStorage,
    SCHEMA_VERSION,
    load_seed_manifest,
    sha256_file,
)
from rns_import_server.workbook_operation_journal import WorkbookOperationJournal


def _seed(path: Path, revision: str, entries: list[dict[str, str]]) -> tuple[Path, Path]:
    seed = path / f"{revision}.sqlite3"
    storage = RegistryStorage.create_seed(seed, entries, seed_revision=revision)
    storage.close()
    manifest = path / f"{revision}.json"
    manifest.write_text(json.dumps({"schema_version": SCHEMA_VERSION, "seed_revision": revision, "entry_count": len(entries), "sha256": sha256_file(seed)}), encoding="utf-8")
    return seed, manifest


def _journal_operation(storage: RegistryStorage, suffix: str) -> str:
    construction = storage.list_constructions()[0]
    return WorkbookOperationJournal(storage).create(
        operation_id=f"legacy-operation-{suffix}", idempotency_key=f"legacy-idempotency-{suffix}",
        consumer_id=f"legacy-consumer-{suffix}", owner_id="legacy-owner", pair_nonce="legacy-nonce",
        construction_id=construction.id, operation_kind="new_row", mutation_mode="middle_insert",
        target_identity="legacy-target", sheet_identity="legacy-sheet", template_version="legacy-template",
        expected_generation=storage.generation, intent_version="legacy-intent", intent_digest="legacy-intent-digest",
        manifest_version="legacy-manifest", manifest_digest="legacy-manifest-digest",
        operation_directory="legacy-operation-directory", canonical_rns="RU-00000000-00-2026",
    ).operation_id


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
        before = (runtime.generation, runtime.get_construction(row.id).row_revision, len(runtime.conflicts()))  # type: ignore[union-attr]
        runtime.reconcile_seed(seed2, manifest2)
        assert (runtime.generation, runtime.get_construction(row.id).row_revision, len(runtime.conflicts())) == before  # type: ignore[union-attr]
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
        before = (runtime.generation, runtime.get_construction(row.id).row_revision, len(runtime.conflicts()))  # type: ignore[union-attr]
        runtime.reconcile_seed(seed3, manifest3)
        assert (runtime.generation, runtime.get_construction(row.id).row_revision, len(runtime.conflicts())) == before  # type: ignore[union-attr]
    finally:
        runtime.close()


def test_corrupt_seed_is_rejected(tmp_path: Path) -> None:
    seed = tmp_path / "broken.sqlite3"
    seed.write_bytes(b"not sqlite")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": SCHEMA_VERSION, "seed_revision": "r", "entry_count": 0, "sha256": sha256_file(seed)}), encoding="utf-8")
    with pytest.raises(RegistryCorruptError):
        RegistryStorage.bootstrap(tmp_path / "runtime", seed_path=seed, manifest_path=manifest)


def test_v0_migration_keeps_recoverable_backup_and_newer_schema_fails_closed(tmp_path: Path) -> None:
    runtime = RegistryStorage.bootstrap(tmp_path)
    path = runtime.path
    runtime.connection.execute("UPDATE registry_meta SET schema_version=0")
    runtime.close()
    migrated = RegistryStorage(path)
    try:
        assert migrated.connection.execute("SELECT schema_version FROM registry_meta").fetchone()[0] == SCHEMA_VERSION
        assert path.with_suffix(".sqlite3.pre-migration.bak").is_file()
    finally:
        migrated.close()
    newer = RegistryStorage(path)
    newer.connection.execute("UPDATE registry_meta SET schema_version=4")
    newer.close()
    with pytest.raises(RegistrySchemaError):
        RegistryStorage(path)


@pytest.mark.parametrize("mode", ["middle_insert", "blank_fill"])
@pytest.mark.parametrize("phase,expected_phase", [
    ("staged", "manual_repair"), ("native", "manual_repair"), ("validated", "manual_repair"),
    ("backup_verified", "manual_repair"), ("published", "published"), ("finalized", "finalized"),
])
def test_v2_lease_migration_quarantines_only_nonterminal_native_history(tmp_path: Path, mode: str, phase: str, expected_phase: str) -> None:
    runtime = RegistryStorage.bootstrap(tmp_path)
    path = runtime.path
    operation_id = _journal_operation(runtime, phase)
    runtime.connection.execute("UPDATE workbook_operation_journal SET mutation_mode=? WHERE operation_id=?", (mode, operation_id))
    runtime.connection.execute("UPDATE workbook_operation_journal SET phase=? WHERE operation_id=?", (phase, operation_id))
    if phase == "finalized":
        runtime.connection.execute(
            """UPDATE workbook_operation_journal
               SET capability_finalized=1, binding_finalized=1, history_finalized=1, report_finalized=1
             WHERE operation_id=?""",
            (operation_id,),
        )
    runtime.connection.execute("ALTER TABLE workbook_operation_journal DROP COLUMN excel_adapter_pid")
    runtime.connection.execute("ALTER TABLE workbook_operation_journal DROP COLUMN excel_adapter_started_at")
    runtime.connection.execute("UPDATE registry_meta SET schema_version=2")
    runtime.close()
    migrated = RegistryStorage(path)
    try:
        row = migrated.connection.execute("SELECT phase, failure_code FROM workbook_operation_journal WHERE operation_id=?", (operation_id,)).fetchone()
        assert row["phase"] == expected_phase
        if expected_phase == "manual_repair":
            assert row["failure_code"] == "legacy_excel_lease_ownership_missing"
        assert path.with_suffix(".sqlite3.pre-migration.bak").is_file()
    finally:
        migrated.close()


def test_schema_less_or_interrupted_runtime_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "PropExtract" / "construction-registry" / "registry.sqlite3"
    target.parent.mkdir(parents=True)
    target.touch()
    with pytest.raises(RegistrySchemaError):
        RegistryStorage(target)


def test_untouched_seed_update_and_edited_removal_are_explicit(tmp_path: Path) -> None:
    seed1, manifest1 = _seed(tmp_path, "r1", [
        {"seed_entry_id": "one", "code_prefix": "111-1111111", "official_name": "Первая", "status": "active"},
    ])
    runtime = RegistryStorage.bootstrap(tmp_path / "runtime", seed_path=seed1, manifest_path=manifest1)
    try:
        row = runtime.list_constructions()[0]
        seed2, manifest2 = _seed(tmp_path, "r2", [
            {"seed_entry_id": "one", "code_prefix": "111-1111111", "official_name": "Обновлена", "status": "active"},
        ])
        runtime.reconcile_seed(seed2, manifest2)
        assert runtime.get_construction(row.id).official_name == "Обновлена"  # type: ignore[union-attr]
        runtime.connection.execute(
            "UPDATE constructions SET official_name=?, normalized_name=? WHERE id=?",
            ("Локально изменена", "локально изменена", row.id),
        )
        seed3, manifest3 = _seed(tmp_path, "r3", [])
        runtime.reconcile_seed(seed3, manifest3)
        assert runtime.get_construction(row.id).status == "active"  # type: ignore[union-attr]
        assert runtime.conflicts()[0]["kind"] == "seed_removal_local_edit"
    finally:
        runtime.close()


def test_reconciliation_rolls_back_injected_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed1, manifest1 = _seed(tmp_path, "r1", [
        {"seed_entry_id": "one", "code_prefix": "111-1111111", "official_name": "Первая", "status": "active"},
    ])
    runtime = RegistryStorage.bootstrap(tmp_path / "runtime", seed_path=seed1, manifest_path=manifest1)
    try:
        seed2, manifest2 = _seed(tmp_path, "r2", [
            {"seed_entry_id": "one", "code_prefix": "111-1111111", "official_name": "Первая", "status": "active"},
            {"seed_entry_id": "two", "code_prefix": "222-2222222", "official_name": "Вторая", "status": "active"},
        ])
        original = runtime._insert_seed_entry

        def fail_after_insert(*args: object, **kwargs: object):
            original(*args, **kwargs)
            raise RuntimeError("injected reconcile failure")

        monkeypatch.setattr(runtime, "_insert_seed_entry", fail_after_insert)
        before = (runtime.count(), runtime.generation, runtime.seed_revision)
        with pytest.raises(RuntimeError, match="injected reconcile failure"):
            runtime.reconcile_seed(seed2, manifest2)
        assert (runtime.count(), runtime.generation, runtime.seed_revision) == before
        assert runtime.get_construction("two") is None
    finally:
        runtime.close()


def test_runtime_lock_uses_bounded_sqlite_timeout(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    contender = RegistryStorage(storage.path, timeout_ms=40)
    holder = sqlite3.connect(storage.path, isolation_level=None)
    try:
        holder.execute("BEGIN IMMEDIATE")
        started = time.monotonic()
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            contender.create_construction(code_prefix="999-9999999", official_name="Lock test")
        assert time.monotonic() - started < 0.8
    finally:
        holder.execute("ROLLBACK")
        holder.close()
        contender.close()
        storage.close()


def test_read_snapshot_never_mixes_generation_with_concurrent_writer_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    generation_read = threading.Event()
    allow_reader = threading.Event()
    result: dict[str, object] = {}
    original = RegistryStorage._snapshot_generation

    def pause_after_snapshot_anchor(self: RegistryStorage, connection: sqlite3.Connection) -> int:
        generation = original(self, connection)
        generation_read.set()
        assert allow_reader.wait(timeout=2)
        return generation

    monkeypatch.setattr(RegistryStorage, "_snapshot_generation", pause_after_snapshot_anchor)

    def read() -> None:
        reader = RegistryStorage(storage.path)
        try:
            result["snapshot"] = reader.read_snapshot()
        finally:
            reader.close()

    thread = threading.Thread(target=read)
    try:
        before = storage.generation
        thread.start()
        assert generation_read.wait(timeout=2)
        storage.create_construction(code_prefix="123-1234567", official_name="Concurrent")
        allow_reader.set()
        thread.join(timeout=2)
        assert not thread.is_alive()
        snapshot = result["snapshot"]
        assert snapshot.generation == before  # type: ignore[union-attr]
        assert all(item.code_prefix != "123-1234567" for item in snapshot.constructions)  # type: ignore[union-attr]
    finally:
        allow_reader.set()
        thread.join(timeout=2)
        storage.close()


def test_v1_53307beb_migration_deduplicates_active_conflicts_and_backup_rolls_back(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    seed = RegistryStorage.create_seed(path, [
        {"seed_entry_id": "one", "code_prefix": "111-1111111", "official_name": "Первая", "status": "active"},
    ], seed_revision="construction-registry-v1")
    construction_id = seed.list_constructions()[0].id
    seed.close()
    legacy = sqlite3.connect(path)
    try:
        legacy.execute("DROP INDEX registry_conflict_identity_idx")
        for flag in ("capability", "binding", "history", "report"):
            legacy.execute(f"ALTER TABLE workbook_operation_journal DROP COLUMN {flag}_finalized_at")
        legacy.execute("UPDATE registry_meta SET schema_version=1")
        for resolved_at in (None, None, "2026-08-18T00:00:00Z"):
            legacy.execute(
                "INSERT INTO registry_conflicts(seed_entry_id, construction_id, kind, detail, created_at, resolved_at) "
                "VALUES (?, ?, 'local_seed_divergence', 'history', '2026-08-18T00:00:00Z', ?)",
                ("one", construction_id, resolved_at),
            )
        legacy.commit()
    finally:
        legacy.close()

    migrated = RegistryStorage(path)
    backup = path.with_suffix(".sqlite3.pre-migration.bak")
    try:
        active = migrated.connection.execute(
            "SELECT id FROM registry_conflicts WHERE resolved_at IS NULL ORDER BY id"
        ).fetchall()
        history = migrated.connection.execute(
            "SELECT id FROM registry_conflicts WHERE resolved_at IS NOT NULL"
        ).fetchall()
        index_sql = migrated.connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name='registry_conflict_identity_idx'"
        ).fetchone()[0]
        assert len(active) == 1
        assert len(history) == 1
        assert "WHERE resolved_at IS NULL" in index_sql
        with pytest.raises(sqlite3.IntegrityError):
            migrated.connection.execute(
                "INSERT INTO registry_conflicts(seed_entry_id, construction_id, kind, detail, created_at) "
                "VALUES ('one', ?, 'local_seed_divergence', 'again', '2026-08-18T00:00:00Z')",
                (construction_id,),
            )
        assert backup.is_file()
    finally:
        migrated.close()

    archived = sqlite3.connect(backup)
    try:
        assert archived.execute("SELECT schema_version FROM registry_meta WHERE id=1").fetchone()[0] == 1
        assert archived.execute("SELECT COUNT(*) FROM registry_conflicts").fetchone()[0] == 3
    finally:
        archived.close()
    for suffix in ("-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)
    shutil.copy2(backup, path)
    rolled_back = sqlite3.connect(path)
    try:
        assert rolled_back.execute("SELECT schema_version FROM registry_meta WHERE id=1").fetchone()[0] == 1
        assert rolled_back.execute("SELECT COUNT(*) FROM registry_conflicts").fetchone()[0] == 3
    finally:
        rolled_back.close()
    reopened = RegistryStorage(path)
    try:
        assert len(reopened.conflicts()) == 1
    finally:
        reopened.close()


def test_v1_journal_migration_backfills_true_finalization_flag_timestamps(tmp_path: Path) -> None:
    path = tmp_path / "legacy-finalization-timestamps.sqlite3"
    storage = RegistryStorage.create_seed(path, [
        {"seed_entry_id": "one", "code_prefix": "111-1111111", "official_name": "Первая", "status": "active"},
    ], seed_revision="construction-registry-v1")
    operation_id = _journal_operation(storage, "timestamps")
    storage.close()
    legacy_timestamp = "2024-03-02T01:02:03Z"
    legacy = sqlite3.connect(path)
    try:
        legacy.execute("DROP INDEX registry_conflict_identity_idx")
        for flag in ("capability", "binding", "history", "report"):
            legacy.execute(f"ALTER TABLE workbook_operation_journal DROP COLUMN {flag}_finalized_at")
        legacy.execute("UPDATE registry_meta SET schema_version=1")
        legacy.execute(
            """UPDATE workbook_operation_journal
               SET phase='published', capability_finalized=1, binding_finalized=1,
                   history_finalized=1, report_finalized=1, updated_at=?
               WHERE operation_id=?""",
            (legacy_timestamp, operation_id),
        )
        legacy.commit()
    finally:
        legacy.close()

    migrated = RegistryStorage(path)
    try:
        row = migrated.connection.execute(
            "SELECT * FROM workbook_operation_journal WHERE operation_id=?", (operation_id,)
        ).fetchone()
        assert row["phase"] == "published"
        for flag in ("capability", "binding", "history", "report"):
            assert row[f"{flag}_finalized_at"] == legacy_timestamp
    finally:
        migrated.close()


def test_v1_journal_migration_quarantines_impossible_finalization_states_after_restart(tmp_path: Path) -> None:
    path = tmp_path / "legacy-finalization-quarantine.sqlite3"
    storage = RegistryStorage.create_seed(path, [
        {"seed_entry_id": "one", "code_prefix": "111-1111111", "official_name": "Первая", "status": "active"},
    ], seed_revision="construction-registry-v1")
    finalized_id = _journal_operation(storage, "finalized")
    premature_id = _journal_operation(storage, "premature")
    storage.close()
    legacy_timestamp = "2024-04-05T06:07:08Z"
    legacy = sqlite3.connect(path)
    try:
        legacy.execute("DROP INDEX registry_conflict_identity_idx")
        for flag in ("capability", "binding", "history", "report"):
            legacy.execute(f"ALTER TABLE workbook_operation_journal DROP COLUMN {flag}_finalized_at")
        legacy.execute("UPDATE registry_meta SET schema_version=1")
        legacy.execute(
            """UPDATE workbook_operation_journal
               SET phase='finalized', capability_finalized=0, binding_finalized=0,
                   history_finalized=0, report_finalized=0, updated_at=?
               WHERE operation_id=?""",
            (legacy_timestamp, finalized_id),
        )
        legacy.execute(
            """UPDATE workbook_operation_journal
               SET phase='validated', history_finalized=1, updated_at=?
               WHERE operation_id=?""",
            (legacy_timestamp, premature_id),
        )
        legacy.commit()
    finally:
        legacy.close()

    migrated = RegistryStorage(path)
    try:
        rows = {
            row["operation_id"]: row for row in migrated.connection.execute(
                "SELECT * FROM workbook_operation_journal WHERE operation_id IN (?, ?)",
                (finalized_id, premature_id),
            )
        }
        for operation_id in (finalized_id, premature_id):
            assert rows[operation_id]["phase"] == "manual_repair"
            assert rows[operation_id]["failure_code"] == "legacy_journal_state_invalid"
        assert rows[premature_id]["history_finalized_at"] == legacy_timestamp
    finally:
        migrated.close()

    restarted = RegistryStorage(path)
    try:
        incomplete_ids = {item.operation_id for item in WorkbookOperationJournal(restarted).incomplete()}
        assert {finalized_id, premature_id} <= incomplete_ids
    finally:
        restarted.close()


def test_missing_meta_row_table_or_column_raises_typed_schema_error(tmp_path: Path) -> None:
    empty_meta = tmp_path / "empty-meta.sqlite3"
    connection = sqlite3.connect(empty_meta)
    try:
        connection.execute(
            "CREATE TABLE registry_meta (id INTEGER PRIMARY KEY, schema_version INTEGER, seed_revision TEXT, "
            "generation INTEGER, created_at TEXT, updated_at TEXT)"
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(RegistrySchemaError):
        RegistryStorage(empty_meta)

    missing_table = tmp_path / "missing-table.sqlite3"
    storage = RegistryStorage.create_seed(missing_table, [], seed_revision="v2")
    storage.close()
    connection = sqlite3.connect(missing_table)
    try:
        connection.execute("DROP TABLE construction_bindings")
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(RegistrySchemaError):
        RegistryStorage(missing_table)

    missing_column = tmp_path / "missing-column.sqlite3"
    storage = RegistryStorage.create_seed(missing_column, [], seed_revision="v2")
    storage.close()
    connection = sqlite3.connect(missing_column)
    try:
        connection.execute("ALTER TABLE constructions DROP COLUMN updated_at")
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(RegistrySchemaError):
        RegistryStorage(missing_column)
