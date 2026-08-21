"""Portable SQLite storage for the construction registry.

The shipped seed is immutable.  ``RegistryStorage.bootstrap`` copies it to a
caller-controlled runtime data root (``%LOCALAPPDATA%`` on Windows), where all
future migration and reconciliation work occurs transactionally.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import uuid
from typing import Any, Iterator, Mapping, Sequence

from rns_import_server.construction_registry import (
    Construction,
    ConstructionValidationError,
    match_official_prefix,
    validate_construction_values,
)


SCHEMA_VERSION = 5
SEED_REVISION = "construction-registry-v5"
BUSY_TIMEOUT_MS = 1_500
DEFAULT_APP_NAME = "PropExtract"
DEFAULT_SEED_PATH = Path(__file__).with_name("data") / "construction_registry.seed.sqlite3"
DEFAULT_MANIFEST_PATH = Path(__file__).with_name("data") / "construction_registry.seed.manifest.json"


class RegistryError(RuntimeError):
    pass


class RegistryConflictError(RegistryError):
    pass


class RegistryStaleError(RegistryError):
    pass


class RegistrySchemaError(RegistryError):
    pass


class RegistryCorruptError(RegistryError):
    pass


_META_COLUMNS = frozenset({"id", "schema_version", "seed_revision", "generation", "created_at", "updated_at"})
_V1_JOURNAL_COLUMNS = frozenset({
    "operation_id", "idempotency_key", "consumer_id", "owner_id", "pair_nonce", "construction_id",
    "canonical_rns", "operation_kind", "mutation_mode", "target_identity", "sheet_identity",
    "template_version", "expected_generation", "intent_version", "intent_digest", "manifest_version",
    "manifest_digest", "operation_directory", "pre_hash", "staged_hash", "control_hash", "post_hash",
    "backup_hash", "validation_digest", "excel_adapter", "excel_pid", "excel_hwnd",
    "excel_process_started_at", "excel_build", "phase", "failure_code", "capability_finalized",
    "binding_finalized", "history_finalized", "report_finalized", "created_at", "updated_at", "staged_at",
    "validated_at", "backup_verified_at", "published_at", "finalized_at",
})
_REQUIRED_SCHEMA_COLUMNS = {
    "registry_meta": _META_COLUMNS,
    "constructions": frozenset({
        "id", "seed_entry_id", "origin", "code_prefix", "official_name", "normalized_name", "status",
        "row_revision", "created_at", "updated_at",
    }),
    "registry_seed_state": frozenset({
        "seed_entry_id", "last_applied_revision", "base_code_prefix", "base_official_name",
        "base_normalized_name", "base_status", "base_digest",
    }),
    "registry_conflicts": frozenset({
        "id", "seed_entry_id", "construction_id", "kind", "detail", "created_at", "resolved_at",
    }),
    "construction_bindings": frozenset({
        "id", "construction_id", "workbook_contract_id", "target_identity", "sheet_identity",
        "template_version", "verified_state", "verified_at", "created_at", "updated_at",
    }),
    "workbook_operation_journal": _V1_JOURNAL_COLUMNS,
}
_V2_JOURNAL_COLUMNS = frozenset({
    "capability_finalized_at", "binding_finalized_at", "history_finalized_at", "report_finalized_at",
})
_V3_JOURNAL_COLUMNS = frozenset({"excel_adapter_pid", "excel_adapter_started_at"})
_V4_JOURNAL_COLUMNS = frozenset({"workbook_contract_id"})
_V4_SNAPSHOT_COLUMNS = frozenset({"operation_id", "snapshot_version", "canonical_payload", "digest", "created_at"})
_V5_JOURNAL_COLUMNS = frozenset({"report_snapshot_digest"})
_V5_PENDING_ACTION_COLUMNS = frozenset({
    "action_id", "job_id", "construction_id", "workbook_contract_id", "target_identity", "target_path",
    "capability_digest", "state", "created_at", "updated_at",
})
_V5_ACTION_HISTORY_COLUMNS = frozenset({
    "action_id", "event_version", "event_type", "status", "target_row", "post_hash", "digest", "created_at",
})
_LEGACY_JOURNAL_STATE_FAILURE_CODE = "legacy_journal_state_invalid"
_LEGACY_LEASE_OWNERSHIP_FAILURE_CODE = "legacy_excel_lease_ownership_missing"


@dataclass(frozen=True)
class RegistryReadSnapshot:
    """Registry projection read from one SQLite snapshot transaction.

    The mapping values deliberately preserve the storage-level database shape;
    transport layers can project them into their own DTOs without issuing a
    second query against a newer generation.
    """

    generation: int
    constructions: tuple[Construction, ...]
    bindings: tuple[dict[str, object], ...]
    conflicts: tuple[dict[str, object], ...]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def runtime_registry_path(data_root: str | os.PathLike[str] | None = None) -> Path:
    """Return the writable registry path without touching the filesystem."""
    if data_root is None:
        if os.name == "nt":
            root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        else:
            # Importing/testing outside Windows remains safe and does not claim
            # that this is a supported release location.
            root = Path.home() / ".local" / "share"
    else:
        root = Path(data_root)
    return root / DEFAULT_APP_NAME / "construction-registry" / "registry.sqlite3"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_seed_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RegistryCorruptError("Не удалось прочитать manifest поставляемого справочника") from error
    required = {"schema_version", "seed_revision", "entry_count", "sha256"}
    if not isinstance(manifest, dict) or set(manifest) != required:
        raise RegistryCorruptError("Manifest поставляемого справочника имеет неподдерживаемый формат")
    if manifest["schema_version"] != SCHEMA_VERSION or not isinstance(manifest["entry_count"], int):
        raise RegistryCorruptError("Manifest поставляемого справочника несовместим с программой")
    if not isinstance(manifest["seed_revision"], str) or not isinstance(manifest["sha256"], str):
        raise RegistryCorruptError("Manifest поставляемого справочника имеет неверные поля")
    return manifest


def validate_seed(seed_path: Path = DEFAULT_SEED_PATH, manifest_path: Path = DEFAULT_MANIFEST_PATH) -> dict[str, Any]:
    manifest = load_seed_manifest(manifest_path)
    if not seed_path.is_file() or sha256_file(seed_path) != manifest["sha256"]:
        raise RegistryCorruptError("Контрольная сумма поставляемого справочника не совпадает")
    storage = RegistryStorage(seed_path, read_only=True)
    try:
        if storage.count() != manifest["entry_count"]:
            raise RegistryCorruptError("Количество записей поставляемого справочника не совпадает с manifest")
        if storage.seed_revision != manifest["seed_revision"]:
            raise RegistryCorruptError("Ревизия поставляемого справочника не совпадает с manifest")
    finally:
        storage.close()
    return manifest


class RegistryStorage:
    """A short-transaction SQLite registry with optimistic generation checks."""

    def __init__(self, path: str | os.PathLike[str], *, read_only: bool = False, timeout_ms: int = BUSY_TIMEOUT_MS,
                 allow_uninitialized: bool = False):
        self.path = Path(path)
        self.read_only = read_only
        self.timeout_ms = timeout_ms
        if read_only:
            uri = self.path.resolve().as_uri() + "?mode=ro"
            self.connection = sqlite3.connect(uri, uri=True, timeout=timeout_ms / 1000, isolation_level=None)
        else:
            self.connection = sqlite3.connect(self.path, timeout=timeout_ms / 1000, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(f"PRAGMA busy_timeout={int(timeout_ms)}")
        self.connection.execute("PRAGMA foreign_keys=ON")
        # FULL is deliberately the conservative default.  Journal transitions
        # are publication boundaries and must be durable before XLSX replace.
        if not read_only:
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA synchronous=FULL")
        self._verify_open(allow_uninitialized=allow_uninitialized)

    @classmethod
    def create_seed(
        cls,
        path: str | os.PathLike[str],
        entries: Sequence[Mapping[str, str]],
        *,
        seed_revision: str = SEED_REVISION,
    ) -> "RegistryStorage":
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.unlink()
        storage = cls(target, allow_uninitialized=True)
        # Seed bytes are a release artifact, so its timestamps must not make a
        # rebuild differ.  Runtime records continue to use real UTC time.
        storage._fixed_now = "2026-08-18T00:00:00Z"
        storage._create_schema(seed_revision=seed_revision)
        for entry in entries:
            storage._insert_seed_entry(entry)
        storage.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        storage.connection.execute("PRAGMA journal_mode=DELETE")
        storage.connection.execute("VACUUM")
        del storage._fixed_now
        return storage

    @classmethod
    def bootstrap(
        cls,
        data_root: str | os.PathLike[str] | None = None,
        *,
        seed_path: Path = DEFAULT_SEED_PATH,
        manifest_path: Path = DEFAULT_MANIFEST_PATH,
    ) -> "RegistryStorage":
        """Create the first writable runtime copy atomically, then reconcile."""
        validate_seed(seed_path, manifest_path)
        target = runtime_registry_path(data_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            fd, temporary = tempfile.mkstemp(prefix="registry-", suffix=".sqlite3", dir=target.parent)
            os.close(fd)
            try:
                shutil.copyfile(seed_path, temporary)
                with open(temporary, "rb") as stream:
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
            finally:
                Path(temporary).unlink(missing_ok=True)
        storage = cls(target)
        storage.reconcile_seed(seed_path, manifest_path)
        return storage

    def close(self) -> None:
        self.connection.close()

    def _verify_open(self, *, allow_uninitialized: bool = False) -> None:
        try:
            integrity = self.connection.execute("PRAGMA integrity_check").fetchone()
        except sqlite3.DatabaseError as error:
            raise RegistryCorruptError("Не удалось проверить целостность локального справочника") from error
        if integrity is None:
            raise RegistryCorruptError("Не удалось проверить целостность локального справочника")
        result = integrity[0]
        if result != "ok":
            raise RegistryCorruptError("Локальный справочник повреждён")
        meta_columns = self._table_columns("registry_meta")
        if not meta_columns:
            if allow_uninitialized and not self.read_only:
                return
            raise RegistrySchemaError("Локальный справочник не содержит обязательную схему")
        if _META_COLUMNS - meta_columns:
            raise RegistrySchemaError("Локальный справочник имеет неполную metadata-схему")
        try:
            meta_rows = self.connection.execute(
                "SELECT schema_version FROM registry_meta WHERE id=1"
            ).fetchall()
        except sqlite3.DatabaseError as error:
            raise RegistrySchemaError("Не удалось прочитать metadata локального справочника") from error
        if len(meta_rows) != 1:
            raise RegistrySchemaError("Локальный справочник не содержит поддерживаемую metadata-запись")
        version = meta_rows[0]["schema_version"]
        if not isinstance(version, int) or isinstance(version, bool):
            raise RegistrySchemaError("Версия схемы локального справочника имеет неверный формат")
        if version > SCHEMA_VERSION:
            raise RegistrySchemaError("Локальный справочник создан более новой версией программы")
        if version not in {0, 1, 2, 3, 4, SCHEMA_VERSION}:
            raise RegistrySchemaError(f"Нет миграции локального справочника {version} → {SCHEMA_VERSION}")
        self._validate_schema(version)
        if version < SCHEMA_VERSION:
            if self.read_only:
                raise RegistrySchemaError("Поставляемый справочник имеет устаревшую схему")
            self._migrate(version)
        elif not self.read_only:
            self._ensure_unresolved_conflict_identity_index()

    def _table_columns(self, table: str) -> set[str]:
        try:
            present = self.connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if not present:
                return set()
            return {str(row["name"]) for row in self.connection.execute(f"PRAGMA table_info({table})")}
        except sqlite3.DatabaseError as error:
            raise RegistrySchemaError("Не удалось прочитать схему локального справочника") from error

    def _validate_schema(self, version: int) -> None:
        required = dict(_REQUIRED_SCHEMA_COLUMNS)
        if version == 2:
            required["workbook_operation_journal"] = _V1_JOURNAL_COLUMNS | _V2_JOURNAL_COLUMNS
        elif version == 3:
            required["workbook_operation_journal"] = _V1_JOURNAL_COLUMNS | _V2_JOURNAL_COLUMNS | _V3_JOURNAL_COLUMNS
        elif version == 4:
            required["workbook_operation_journal"] = _V1_JOURNAL_COLUMNS | _V2_JOURNAL_COLUMNS | _V3_JOURNAL_COLUMNS | _V4_JOURNAL_COLUMNS
            required["workbook_finalization_snapshots"] = _V4_SNAPSHOT_COLUMNS
        elif version == SCHEMA_VERSION:
            required["workbook_operation_journal"] = _V1_JOURNAL_COLUMNS | _V2_JOURNAL_COLUMNS | _V3_JOURNAL_COLUMNS | _V4_JOURNAL_COLUMNS | _V5_JOURNAL_COLUMNS
            required["workbook_finalization_snapshots"] = _V4_SNAPSHOT_COLUMNS
            required["new_row_pending_actions"] = _V5_PENDING_ACTION_COLUMNS
            required["new_row_action_history"] = _V5_ACTION_HISTORY_COLUMNS
        for table, expected_columns in required.items():
            actual_columns = self._table_columns(table)
            if not actual_columns:
                raise RegistrySchemaError(f"Локальный справочник не содержит обязательную таблицу {table}")
            if expected_columns - actual_columns:
                raise RegistrySchemaError(f"Локальный справочник имеет неполную таблицу {table}")

    def _ensure_unresolved_conflict_identity_index(self) -> None:
        """Upgrade the old v2 seed index in writable runtime copies only."""
        row = self.connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name='registry_conflict_identity_idx'"
        ).fetchone()
        index_sql = str(row["sql"] or "").lower() if row else ""
        if "where resolved_at is null" in index_sql and "ifnull(construction_id" in index_sql:
            return
        with self.transaction() as connection:
            connection.execute(
                """DELETE FROM registry_conflicts AS duplicate
                   WHERE duplicate.resolved_at IS NULL
                     AND EXISTS (
                         SELECT 1 FROM registry_conflicts AS retained
                         WHERE retained.resolved_at IS NULL
                           AND retained.seed_entry_id=duplicate.seed_entry_id
                           AND retained.kind=duplicate.kind
                           AND (retained.construction_id=duplicate.construction_id
                                OR (retained.construction_id IS NULL AND duplicate.construction_id IS NULL))
                           AND retained.id < duplicate.id
                     )"""
            )
            connection.execute("DROP INDEX IF EXISTS registry_conflict_identity_idx")
            connection.execute(
                "CREATE UNIQUE INDEX registry_conflict_identity_idx "
                "ON registry_conflicts(seed_entry_id, IFNULL(construction_id, ''), kind) "
                "WHERE resolved_at IS NULL"
            )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        if self.read_only:
            raise RegistryError("Поставляемый справочник доступен только для чтения")
        begun = False
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            begun = True
            yield self.connection
            self.connection.execute("COMMIT")
        except Exception:
            if begun:
                self.connection.execute("ROLLBACK")
            raise

    def _create_schema(self, *, seed_revision: str) -> None:
        now = getattr(self, "_fixed_now", utc_now())
        # sqlite3.executescript manages its own transaction boundary, so do
        # not wrap it in ``transaction()`` (which would otherwise try to
        # commit a transaction that executescript already closed).
        self.connection.executescript(
            """
                CREATE TABLE registry_meta (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    schema_version INTEGER NOT NULL,
                    seed_revision TEXT NOT NULL,
                    generation INTEGER NOT NULL CHECK (generation >= 0),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE constructions (
                    id TEXT PRIMARY KEY,
                    seed_entry_id TEXT UNIQUE,
                    origin TEXT NOT NULL CHECK (origin IN ('seed', 'local')),
                    code_prefix TEXT NOT NULL UNIQUE,
                    official_name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL CHECK (status IN ('draft', 'active', 'archived')),
                    row_revision INTEGER NOT NULL CHECK (row_revision >= 1),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE registry_seed_state (
                    seed_entry_id TEXT PRIMARY KEY,
                    last_applied_revision TEXT NOT NULL,
                    base_code_prefix TEXT NOT NULL,
                    base_official_name TEXT NOT NULL,
                    base_normalized_name TEXT NOT NULL,
                    base_status TEXT NOT NULL,
                    base_digest TEXT NOT NULL
                );
                CREATE TABLE registry_conflicts (
                    id INTEGER PRIMARY KEY,
                    seed_entry_id TEXT NOT NULL,
                    construction_id TEXT,
                    kind TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                );
                CREATE TABLE construction_bindings (
                    id TEXT PRIMARY KEY,
                    construction_id TEXT NOT NULL REFERENCES constructions(id) ON DELETE RESTRICT,
                    workbook_contract_id TEXT NOT NULL,
                    target_identity TEXT NOT NULL,
                    sheet_identity TEXT NOT NULL,
                    template_version TEXT NOT NULL,
                    verified_state TEXT NOT NULL,
                    verified_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(construction_id, workbook_contract_id, target_identity, sheet_identity)
                );
                CREATE TABLE workbook_operation_journal (
                    operation_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    consumer_id TEXT NOT NULL UNIQUE,
                    owner_id TEXT NOT NULL,
                    pair_nonce TEXT NOT NULL,
                    construction_id TEXT NOT NULL REFERENCES constructions(id) ON DELETE RESTRICT,
                    canonical_rns TEXT,
                    workbook_contract_id TEXT,
                    operation_kind TEXT NOT NULL CHECK (operation_kind IN ('group_provision', 'new_row')),
                    mutation_mode TEXT NOT NULL CHECK (mutation_mode IN ('bootstrap_fill', 'blank_fill', 'middle_insert')),
                    target_identity TEXT NOT NULL,
                    sheet_identity TEXT NOT NULL,
                    template_version TEXT NOT NULL,
                    expected_generation INTEGER NOT NULL,
                    intent_version TEXT NOT NULL,
                    intent_digest TEXT NOT NULL,
                    manifest_version TEXT NOT NULL,
                    manifest_digest TEXT NOT NULL,
                    operation_directory TEXT NOT NULL,
                    pre_hash TEXT,
                    staged_hash TEXT,
                    control_hash TEXT,
                    post_hash TEXT,
                    backup_hash TEXT,
                    validation_digest TEXT,
                    excel_adapter TEXT,
                    excel_adapter_pid INTEGER,
                    excel_adapter_started_at TEXT,
                    excel_pid INTEGER,
                    excel_hwnd INTEGER,
                    excel_process_started_at TEXT,
                    excel_build TEXT,
                    phase TEXT NOT NULL,
                    failure_code TEXT,
                    capability_finalized INTEGER NOT NULL DEFAULT 0 CHECK (capability_finalized IN (0, 1)),
                    capability_finalized_at TEXT,
                    binding_finalized INTEGER NOT NULL DEFAULT 0 CHECK (binding_finalized IN (0, 1)),
                    binding_finalized_at TEXT,
                    history_finalized INTEGER NOT NULL DEFAULT 0 CHECK (history_finalized IN (0, 1)),
                    history_finalized_at TEXT,
                    report_finalized INTEGER NOT NULL DEFAULT 0 CHECK (report_finalized IN (0, 1)),
                    report_finalized_at TEXT,
                    report_snapshot_digest TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    staged_at TEXT,
                    validated_at TEXT,
                    backup_verified_at TEXT,
                    published_at TEXT,
                    finalized_at TEXT
                );
                CREATE TABLE workbook_finalization_snapshots (
                    operation_id TEXT PRIMARY KEY REFERENCES workbook_operation_journal(operation_id) ON DELETE RESTRICT,
                    snapshot_version INTEGER NOT NULL CHECK (snapshot_version = 1),
                    canonical_payload TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE new_row_pending_actions (
                    action_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    construction_id TEXT NOT NULL REFERENCES constructions(id) ON DELETE RESTRICT,
                    workbook_contract_id TEXT NOT NULL,
                    target_identity TEXT NOT NULL,
                    target_path TEXT NOT NULL,
                    capability_digest TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN ('pending', 'publishing', 'consumed')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE new_row_action_history (
                    action_id TEXT PRIMARY KEY REFERENCES new_row_pending_actions(action_id) ON DELETE RESTRICT,
                    event_version INTEGER NOT NULL CHECK (event_version = 1),
                    event_type TEXT NOT NULL CHECK (event_type = 'new_row'),
                    status TEXT NOT NULL CHECK (status = 'published'),
                    target_row INTEGER NOT NULL CHECK (target_row >= 2),
                    post_hash TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TRIGGER new_row_action_history_immutable_update
                BEFORE UPDATE ON new_row_action_history BEGIN SELECT RAISE(ABORT, 'new_row_action_history immutable'); END;
                CREATE TRIGGER new_row_action_history_immutable_delete
                BEFORE DELETE ON new_row_action_history BEGIN SELECT RAISE(ABORT, 'new_row_action_history immutable'); END;
                CREATE INDEX constructions_status_name_idx ON constructions(status, normalized_name);
                CREATE INDEX construction_bindings_construction_idx ON construction_bindings(construction_id);
                CREATE INDEX journal_phase_idx ON workbook_operation_journal(phase, updated_at);
                CREATE UNIQUE INDEX registry_conflict_identity_idx ON registry_conflicts(seed_entry_id, construction_id, kind);
            """
        )
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO registry_meta VALUES (1, ?, ?, 0, ?, ?)",
                (SCHEMA_VERSION, seed_revision, now, now),
            )

    def _migrate(self, version: int) -> None:
        # Every migration starts from a verified SQLite backup. The backup is
        # made before any runtime mutation and remains a direct rollback file.
        if version not in {0, 1, 2, 3, 4}:
            raise RegistrySchemaError(f"Нет миграции локального справочника {version} → {SCHEMA_VERSION}")
        backup = self.path.with_suffix(self.path.suffix + ".pre-migration.bak")
        temporary = backup.with_name(f"{backup.name}.{uuid.uuid4().hex}.tmp")
        try:
            destination = sqlite3.connect(temporary)
            try:
                self.connection.backup(destination)
            finally:
                destination.close()
            self._verify_migration_backup(temporary, version)
            os.replace(temporary, backup)
            self._verify_migration_backup(backup, version)
        finally:
            temporary.unlink(missing_ok=True)
        self.connection.close()
        self.connection = sqlite3.connect(self.path, timeout=self.timeout_ms / 1000, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(f"PRAGMA busy_timeout={int(self.timeout_ms)}")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        with self.transaction() as connection:
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(workbook_operation_journal)")}
            if "workbook_contract_id" not in columns:
                # Legacy rows are historical evidence.  v4 deliberately does
                # not fabricate a contract for them.
                connection.execute("ALTER TABLE workbook_operation_journal ADD COLUMN workbook_contract_id TEXT")
            if "report_snapshot_digest" not in columns:
                # v5 reserves report authority without creating any report
                # receipt or guessing a digest for legacy evidence.
                connection.execute("ALTER TABLE workbook_operation_journal ADD COLUMN report_snapshot_digest TEXT")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS workbook_finalization_snapshots (
                    operation_id TEXT PRIMARY KEY REFERENCES workbook_operation_journal(operation_id) ON DELETE RESTRICT,
                    snapshot_version INTEGER NOT NULL CHECK (snapshot_version = 1),
                    canonical_payload TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS new_row_pending_actions (
                    action_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    construction_id TEXT NOT NULL REFERENCES constructions(id) ON DELETE RESTRICT,
                    workbook_contract_id TEXT NOT NULL,
                    target_identity TEXT NOT NULL,
                    target_path TEXT NOT NULL,
                    capability_digest TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN ('pending', 'publishing', 'consumed')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS new_row_action_history (
                    action_id TEXT PRIMARY KEY REFERENCES new_row_pending_actions(action_id) ON DELETE RESTRICT,
                    event_version INTEGER NOT NULL CHECK (event_version = 1),
                    event_type TEXT NOT NULL CHECK (event_type = 'new_row'),
                    status TEXT NOT NULL CHECK (status = 'published'),
                    target_row INTEGER NOT NULL CHECK (target_row >= 2),
                    post_hash TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )"""
            )
            connection.execute(
                "CREATE TRIGGER IF NOT EXISTS new_row_action_history_immutable_update "
                "BEFORE UPDATE ON new_row_action_history BEGIN SELECT RAISE(ABORT, 'new_row_action_history immutable'); END"
            )
            connection.execute(
                "CREATE TRIGGER IF NOT EXISTS new_row_action_history_immutable_delete "
                "BEFORE DELETE ON new_row_action_history BEGIN SELECT RAISE(ABORT, 'new_row_action_history immutable'); END"
            )
            for flag in ("capability", "binding", "history", "report"):
                column = f"{flag}_finalized_at"
                if column not in columns:
                    connection.execute(f"ALTER TABLE workbook_operation_journal ADD COLUMN {column} TEXT")
                connection.execute(
                    f"UPDATE workbook_operation_journal SET {column}=COALESCE(NULLIF(updated_at, ''), created_at) "
                    f"WHERE {flag}_finalized=1 AND {column} IS NULL"
                )
            for column, sql_type in (("excel_adapter_pid", "INTEGER"), ("excel_adapter_started_at", "TEXT")):
                if column not in columns:
                    connection.execute(f"ALTER TABLE workbook_operation_journal ADD COLUMN {column} {sql_type}")
            any_finalized = " OR ".join(f"{flag}_finalized=1" for flag in ("capability", "binding", "history", "report"))
            missing_finalized = " OR ".join(f"{flag}_finalized IS NOT 1" for flag in ("capability", "binding", "history", "report"))
            # A legacy record without phase-gated finalization cannot be
            # resumed as a successful operation. Preserve its evidence but
            # make the repair requirement durable and visible after restart.
            connection.execute(
                f"""UPDATE workbook_operation_journal
                    SET phase='manual_repair', failure_code=?, updated_at=?
                    WHERE (phase='finalized' AND ({missing_finalized}))
                       OR (phase IN ('planned', 'staged', 'native', 'validated', 'backup_verified')
                           AND ({any_finalized}))""",
                (_LEGACY_JOURNAL_STATE_FAILURE_CODE, utc_now()),
            )
            # v2 lacks adapter PID/start evidence.  Native work may never be
            # resumed under a guessed ownership tuple; retain all history and
            # force a visible repair at the responsible boundary.
            if version == 2:
                connection.execute(
                    """UPDATE workbook_operation_journal
                       SET phase='manual_repair', failure_code=?, updated_at=?
                     WHERE mutation_mode IN ('middle_insert', 'blank_fill')
                       AND phase IN ('staged', 'native', 'validated', 'backup_verified')
                       AND (excel_adapter IS NULL OR excel_adapter='' OR excel_pid IS NULL
                            OR excel_hwnd IS NULL OR excel_process_started_at IS NULL
                            OR excel_process_started_at='' OR excel_build IS NULL OR excel_build=''
                            OR excel_adapter_pid IS NULL OR excel_adapter_started_at IS NULL
                            OR excel_adapter_started_at='')""",
                    (_LEGACY_LEASE_OWNERSHIP_FAILURE_CODE, utc_now()),
                )
            # v1 had no identity index, so repeated reconciliation could write
            # duplicate unresolved conflicts. Keep resolved history intact.
            connection.execute(
                """DELETE FROM registry_conflicts AS duplicate
                   WHERE duplicate.resolved_at IS NULL
                     AND EXISTS (
                         SELECT 1 FROM registry_conflicts AS retained
                         WHERE retained.resolved_at IS NULL
                           AND retained.seed_entry_id=duplicate.seed_entry_id
                           AND retained.kind=duplicate.kind
                           AND (retained.construction_id=duplicate.construction_id
                                OR (retained.construction_id IS NULL AND duplicate.construction_id IS NULL))
                           AND retained.id < duplicate.id
                     )"""
            )
            connection.execute("DROP INDEX IF EXISTS registry_conflict_identity_idx")
            connection.execute(
                "CREATE UNIQUE INDEX registry_conflict_identity_idx "
                "ON registry_conflicts(seed_entry_id, IFNULL(construction_id, ''), kind) "
                "WHERE resolved_at IS NULL"
            )
            connection.execute(
                "UPDATE registry_meta SET schema_version=?, updated_at=? WHERE id=1",
                (SCHEMA_VERSION, utc_now()),
            )
        self._validate_schema(SCHEMA_VERSION)

    @staticmethod
    def _verify_migration_backup(path: Path, version: int) -> None:
        try:
            connection = sqlite3.connect(path)
            try:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()
                meta = connection.execute("SELECT schema_version FROM registry_meta WHERE id=1").fetchone()
            finally:
                connection.close()
        except sqlite3.DatabaseError as error:
            raise RegistryCorruptError("Не удалось проверить backup миграции справочника") from error
        if integrity is None or integrity[0] != "ok" or meta is None or meta[0] != version:
            raise RegistryCorruptError("Backup миграции справочника не прошёл проверку")

    @property
    def generation(self) -> int:
        return int(self.connection.execute("SELECT generation FROM registry_meta WHERE id=1").fetchone()[0])

    @property
    def seed_revision(self) -> str:
        return str(self.connection.execute("SELECT seed_revision FROM registry_meta WHERE id=1").fetchone()[0])

    def count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM constructions").fetchone()[0])

    def _row_to_construction(self, row: sqlite3.Row) -> Construction:
        return Construction(**dict(row))

    def list_constructions(self, *, include_archived: bool = True) -> list[Construction]:
        statement = "SELECT * FROM constructions"
        params: tuple[object, ...] = ()
        if not include_archived:
            statement += " WHERE status != 'archived'"
        statement += " ORDER BY normalized_name"
        return [self._row_to_construction(row) for row in self.connection.execute(statement, params)]

    def _snapshot_generation(self, connection: sqlite3.Connection) -> int:
        """Read the snapshot anchor separately to make transaction ordering explicit."""
        return int(connection.execute("SELECT generation FROM registry_meta WHERE id=1").fetchone()[0])

    def read_snapshot(self) -> RegistryReadSnapshot:
        """Return list data from exactly one SQLite read transaction.

        WAL writers may commit while this method is running.  ``BEGIN`` pins
        every subsequent SELECT to the generation read first, so callers never
        receive a generation from one committed state and rows from another.
        """
        begun = False
        try:
            self.connection.execute("BEGIN")
            begun = True
            generation = self._snapshot_generation(self.connection)
            constructions = tuple(
                self._row_to_construction(row)
                for row in self.connection.execute("SELECT * FROM constructions ORDER BY normalized_name")
            )
            bindings = tuple(
                dict(row)
                for row in self.connection.execute(
                    "SELECT construction_id, workbook_contract_id, target_identity, sheet_identity, "
                    "template_version, verified_state FROM construction_bindings ORDER BY id"
                )
            )
            conflicts = tuple(
                dict(row)
                for row in self.connection.execute(
                    "SELECT * FROM registry_conflicts WHERE resolved_at IS NULL ORDER BY id"
                )
            )
            self.connection.execute("COMMIT")
            begun = False
            return RegistryReadSnapshot(generation, constructions, bindings, conflicts)
        except Exception:
            if begun:
                self.connection.execute("ROLLBACK")
            raise

    def get_construction(self, construction_id: str) -> Construction | None:
        row = self.connection.execute("SELECT * FROM constructions WHERE id=?", (construction_id,)).fetchone()
        return self._row_to_construction(row) if row else None

    def match(self, pdf_object: str | None, *, include_archived: bool = False):
        return match_official_prefix(pdf_object, self.list_constructions(include_archived=include_archived), include_archived=include_archived)

    def _increment_generation(self, connection: sqlite3.Connection) -> None:
        connection.execute("UPDATE registry_meta SET generation=generation+1, updated_at=? WHERE id=1", (utc_now(),))

    @staticmethod
    def _seed_digest(code: str, official_name: str, status: str) -> str:
        canonical = json.dumps([code, official_name, status], ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _insert_seed_entry(self, entry: Mapping[str, str], *, state_revision: str | None = None) -> Construction:
        seed_id = str(entry["seed_entry_id"])
        code = str(entry["code_prefix"])
        name = str(entry["official_name"])
        status = str(entry.get("status", "active"))
        validate_construction_values(code, name, status)
        now = getattr(self, "_fixed_now", utc_now())
        normalized = validate_construction_values(code, name, status)[1]
        construction_id = str(entry.get("id") or uuid.uuid5(uuid.NAMESPACE_URL, f"propextract:{seed_id}"))
        self.connection.execute(
            """INSERT INTO constructions VALUES (?, ?, 'seed', ?, ?, ?, ?, 1, ?, ?)""",
            (construction_id, seed_id, code, name, normalized, status, now, now),
        )
        self.connection.execute(
            "INSERT INTO registry_seed_state VALUES (?, ?, ?, ?, ?, ?, ?)",
            (seed_id, state_revision or self.seed_revision, code, name, normalized, status, self._seed_digest(code, name, status)),
        )
        return self.get_construction(construction_id)  # type: ignore[return-value]

    def create_construction(
        self,
        *,
        code_prefix: str,
        official_name: str,
        status: str = "draft",
        origin: str = "local",
        seed_entry_id: str | None = None,
        expected_generation: int | None = None,
    ) -> Construction:
        if origin != "local" or seed_entry_id is not None:
            raise ConstructionValidationError("Только внутренняя seed-загрузка может задавать seed ID или seed origin")
        code, normalized = validate_construction_values(code_prefix, official_name, status)
        with self.transaction() as connection:
            self._assert_generation(expected_generation)
            now = utc_now()
            construction_id = str(uuid.uuid4())
            try:
                connection.execute(
                    "INSERT INTO constructions VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                    (construction_id, seed_entry_id, origin, code, official_name, normalized, status, now, now),
                )
            except sqlite3.IntegrityError as error:
                raise RegistryConflictError("Наименование или код стройки уже существуют") from error
            self._increment_generation(connection)
        return self.get_construction(construction_id)  # type: ignore[return-value]

    def update_status(self, construction_id: str, status: str, *, expected_generation: int) -> Construction:
        with self.transaction() as connection:
            self._assert_generation(expected_generation)
            current = self.get_construction(construction_id)
            if not current:
                raise RegistryError("Стройка не найдена")
            allowed = {"active": {"archived"}, "archived": {"active"}, "draft": set()}
            if status not in allowed[current.status]:
                raise ConstructionValidationError("Недопустимый обычный переход статуса стройки")
            connection.execute(
                "UPDATE constructions SET status=?, row_revision=row_revision+1, updated_at=? WHERE id=?",
                (status, utc_now(), construction_id),
            )
            self._increment_generation(connection)
        return self.get_construction(construction_id)  # type: ignore[return-value]

    def update_construction(
        self,
        construction_id: str,
        *,
        code_prefix: str,
        official_name: str,
        expected_generation: int,
        expected_row_revision: int,
    ) -> Construction:
        """CAS-update an unbound local record; bound identity is immutable."""
        code, normalized = validate_construction_values(code_prefix, official_name, "draft")
        with self.transaction() as connection:
            self._assert_generation(expected_generation)
            current = self.get_construction(construction_id)
            if not current:
                raise RegistryError("Стройка не найдена")
            if current.origin != "local" or current.seed_entry_id is not None:
                raise RegistryConflictError("Поставляемая запись не редактируется обычным обновлением")
            if connection.execute("SELECT 1 FROM construction_bindings WHERE construction_id=?", (construction_id,)).fetchone():
                if current.code_prefix != code or current.official_name != official_name:
                    raise RegistryConflictError("Изменение кода или названия bound стройки требует alignment migration")
            if current.row_revision != expected_row_revision:
                raise RegistryStaleError("Стройка изменилась; повторите операцию")
            if current.code_prefix == code and current.official_name == official_name:
                return current
            try:
                updated = connection.execute(
                    """UPDATE constructions SET code_prefix=?, official_name=?, normalized_name=?, row_revision=row_revision+1,
                       updated_at=? WHERE id=? AND row_revision=?""",
                    (code, official_name, normalized, utc_now(), construction_id, expected_row_revision),
                ).rowcount
            except sqlite3.IntegrityError as error:
                raise RegistryConflictError("Наименование или код стройки уже существуют") from error
            if updated != 1:
                raise RegistryStaleError("Стройка изменилась; повторите операцию")
            self._increment_generation(connection)
        return self.get_construction(construction_id)  # type: ignore[return-value]

    def _assert_generation(self, expected_generation: int | None) -> None:
        if expected_generation is not None and expected_generation != self.generation:
            raise RegistryStaleError("Справочник изменился; повторите операцию")

    def bind_construction(
        self,
        construction_id: str,
        *,
        workbook_contract_id: str,
        target_identity: str,
        sheet_identity: str,
        template_version: str,
        verified_state: str,
        expected_generation: int,
    ) -> str:
        values = (workbook_contract_id, target_identity, sheet_identity, template_version, verified_state)
        if not all(isinstance(item, str) and item for item in values):
            raise ConstructionValidationError("Binding требует стабильные непустые идентификаторы")
        binding_id = str(uuid.uuid4())
        now = utc_now()
        with self.transaction() as connection:
            self._assert_generation(expected_generation)
            if not self.get_construction(construction_id):
                raise RegistryError("Стройка не найдена")
            connection.execute(
                """INSERT INTO construction_bindings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (binding_id, construction_id, workbook_contract_id, target_identity, sheet_identity, template_version,
                 verified_state, now, now, now),
            )
            self._increment_generation(connection)
        return binding_id

    def _seed_rows(self, seed_path: Path) -> tuple[str, list[dict[str, str]]]:
        seed = RegistryStorage(seed_path, read_only=True)
        try:
            return seed.seed_revision, [dict(row) for row in seed.connection.execute(
                "SELECT seed_entry_id, code_prefix, official_name, normalized_name, status FROM constructions "
                "WHERE origin='seed' ORDER BY seed_entry_id"
            )]
        finally:
            seed.close()

    def _record_conflict(self, connection: sqlite3.Connection, seed_id: str, construction_id: str | None, kind: str) -> None:
        connection.execute(
            "INSERT OR IGNORE INTO registry_conflicts(seed_entry_id, construction_id, kind, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            (seed_id, construction_id, kind, kind, utc_now()),
        )

    def reconcile_seed(self, seed_path: Path = DEFAULT_SEED_PATH, manifest_path: Path = DEFAULT_MANIFEST_PATH) -> None:
        """Three-way reconcile a new immutable seed without overwriting local work."""
        manifest = validate_seed(seed_path, manifest_path)
        revision, incoming = self._seed_rows(seed_path)
        incoming_by_id = {row["seed_entry_id"]: row for row in incoming}
        with self.transaction() as connection:
            states = {row["seed_entry_id"]: dict(row) for row in connection.execute("SELECT * FROM registry_seed_state")}
            current_by_seed = {row["seed_entry_id"]: dict(row) for row in connection.execute(
                "SELECT * FROM constructions WHERE seed_entry_id IS NOT NULL"
            )}
            changed = False
            for seed_id, incoming_row in incoming_by_id.items():
                current = current_by_seed.get(seed_id)
                state = states.get(seed_id)
                if current is None:
                    # New approved seed entry is safe to add.
                    self._insert_seed_entry({**incoming_row, "status": incoming_row["status"]}, state_revision=revision)
                    changed = True
                    continue
                if state is None:
                    self._record_conflict(connection, seed_id, current["id"], "missing_seed_state")
                    changed = changed or connection.execute("SELECT changes()").fetchone()[0] == 1
                    continue
                base = (state["base_code_prefix"], state["base_official_name"], state["base_status"])
                local = (current["code_prefix"], current["official_name"], current["status"])
                incoming_values = (incoming_row["code_prefix"], incoming_row["official_name"], incoming_row["status"])
                if local == base:
                    bound = connection.execute("SELECT 1 FROM construction_bindings WHERE construction_id=?", (current["id"],)).fetchone()
                    if bound and local[:2] != incoming_values[:2]:
                        self._record_conflict(connection, seed_id, current["id"], "binding_alignment_conflict")
                        changed = changed or connection.execute("SELECT changes()").fetchone()[0] == 1
                        continue
                    if local != incoming_values or state["last_applied_revision"] != revision:
                        connection.execute(
                            """UPDATE constructions SET code_prefix=?, official_name=?, normalized_name=?, status=?,
                               row_revision=row_revision+1, updated_at=? WHERE id=?""",
                            (*incoming_values[:2], incoming_row["normalized_name"], incoming_values[2], utc_now(), current["id"]),
                        )
                        connection.execute(
                            """UPDATE registry_seed_state SET last_applied_revision=?, base_code_prefix=?, base_official_name=?,
                               base_normalized_name=?, base_status=?, base_digest=? WHERE seed_entry_id=?""",
                            (revision, *incoming_values[:2], incoming_row["normalized_name"], incoming_values[2],
                             self._seed_digest(*incoming_values), seed_id),
                        )
                        changed = True
                elif local != incoming_values:
                    self._record_conflict(connection, seed_id, current["id"], "local_seed_divergence")
                    changed = changed or connection.execute("SELECT changes()").fetchone()[0] == 1
            for seed_id, current in current_by_seed.items():
                if seed_id in incoming_by_id:
                    continue
                state = states.get(seed_id)
                if state is None:
                    self._record_conflict(connection, seed_id, current["id"], "missing_seed_state")
                    changed = changed or connection.execute("SELECT changes()").fetchone()[0] == 1
                    continue
                base = (state["base_code_prefix"], state["base_official_name"], state["base_status"])
                local = (current["code_prefix"], current["official_name"], current["status"])
                if local == base and current["status"] != "archived":
                    connection.execute(
                        "UPDATE constructions SET status='archived', row_revision=row_revision+1, updated_at=? WHERE id=?",
                        (utc_now(), current["id"]),
                    )
                    connection.execute("UPDATE registry_seed_state SET base_status=? WHERE seed_entry_id=?", ("archived", seed_id))
                    changed = True
                elif local != base:
                    self._record_conflict(connection, seed_id, current["id"], "seed_removal_local_edit")
                    changed = changed or connection.execute("SELECT changes()").fetchone()[0] == 1
            # A revision is considered applied only when every three-way
            # decision is resolved.  Otherwise a repeated reconcile of the
            # same seed must be a strict no-op rather than bumping generation.
            unresolved = connection.execute(
                "SELECT 1 FROM registry_conflicts WHERE resolved_at IS NULL LIMIT 1"
            ).fetchone()
            if manifest["seed_revision"] != self.seed_revision and not unresolved:
                connection.execute("UPDATE registry_meta SET seed_revision=?, updated_at=? WHERE id=1", (revision, utc_now()))
                changed = True
            if changed:
                self._increment_generation(connection)

    def conflicts(self) -> list[dict[str, object]]:
        return [dict(row) for row in self.connection.execute("SELECT * FROM registry_conflicts WHERE resolved_at IS NULL ORDER BY id")]
