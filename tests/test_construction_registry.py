from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

from rns_import_server.construction_registry import ConstructionValidationError
from rns_import_server.registry_storage import (
    DEFAULT_MANIFEST_PATH,
    DEFAULT_SEED_PATH,
    RegistryConflictError,
    RegistryStaleError,
    RegistryStorage,
    runtime_registry_path,
)


PYTHON = sys.executable


def test_seed_is_deterministic_and_contains_only_approved_entries() -> None:
    subprocess.run([PYTHON, "scripts/build_construction_registry_seed.py", "--check"], check=True)
    storage = RegistryStorage(DEFAULT_SEED_PATH, read_only=True)
    try:
        assert storage.count() == 4
        assert {item.code_prefix for item in storage.list_constructions()} == {
            "051-2006437", "051-2006735", "051-2004430", "051-2000714"
        }
    finally:
        storage.close()


def test_unicode_prefix_match_is_boundary_limited_and_longest(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        parent = storage.create_construction(code_prefix="123-1234567", official_name="Тестовая стройка", status="active")
        child = storage.create_construction(code_prefix="123-1234568", official_name="Тестовая стройка Этап 1", status="active")
        match = storage.match("Тестовая\u00a0стройка Этап 1: объект")
        assert match and match.construction.id == child.id and match.object_tail == "объект"
        assert storage.match("Тестовая стройкаЭтап 1") is None
        assert storage.match("Не " + parent.official_name) is None
    finally:
        storage.close()


def test_duplicate_status_and_generation_conflicts(tmp_path: Path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        first = storage.create_construction(code_prefix="123-1234567", official_name="Локальная", status="draft")
        with pytest.raises(RegistryConflictError):
            storage.create_construction(code_prefix="123-1234567", official_name="Другая", status="draft")
        with pytest.raises(ConstructionValidationError):
            storage.update_status(first.id, "draft", expected_generation=storage.generation)
        generation = storage.generation
        storage.update_status(first.id, "archived", expected_generation=generation)
        with pytest.raises(RegistryStaleError):
            storage.update_status(first.id, "active", expected_generation=generation)
    finally:
        storage.close()


def test_windows_path_is_injectable_and_seed_is_never_modified(tmp_path: Path) -> None:
    seed_before = DEFAULT_SEED_PATH.read_bytes()
    assert runtime_registry_path(tmp_path) == tmp_path / "PropExtract" / "construction-registry" / "registry.sqlite3"
    storage = RegistryStorage.bootstrap(tmp_path)
    storage.create_construction(code_prefix="123-1234567", official_name="Локальная", status="draft")
    storage.close()
    assert DEFAULT_SEED_PATH.read_bytes() == seed_before
