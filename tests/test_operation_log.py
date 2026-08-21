from __future__ import annotations

import json
import os
from pathlib import Path
import threading
from uuid import UUID

import pytest

from rns_import_server.operation_log import (
    MAX_AUXILIARY_FILES,
    OperationLogEntry,
    OperationLogEvent,
    OperationLogWriter,
)


OPERATION = UUID("12345678-1234-5678-1234-567812345678")
TIMESTAMP = "2026-08-22T00:00:00Z"


def _writer(root: Path, **limits: int) -> OperationLogWriter:
    return OperationLogWriter(str(root), **limits)


def _receipt(root: Path, event: OperationLogEvent = OperationLogEvent.OPERATION_STARTED, **limits: int):
    return _writer(root, **limits).append(OperationLogEntry(OPERATION, event, TIMESTAMP))


def _log(root: Path) -> Path:
    return root / "PropExtract" / "logs" / "operations" / f"{OPERATION}.jsonl"


def test_private_canonical_jsonl_and_public_receipt_only(tmp_path: Path) -> None:
    receipt = _receipt(tmp_path)
    assert receipt.operation_id == str(OPERATION) and receipt.log_saved and receipt.error is None
    assert set(receipt.__dict__) == {"operation_id", "log_saved", "error"}
    path = _log(tmp_path)
    assert path.exists() and path.parent == tmp_path / "PropExtract" / "logs" / "operations"
    assert stat_mode(path) == 0o600
    assert all(stat_mode(directory) == 0o700 for directory in (tmp_path / "PropExtract", path.parent.parent, path.parent))
    assert json.loads(path.read_text()) == {
        "event": "operation_started", "operation_id": str(OPERATION), "sequence": 0,
        "timestamp": TIMESTAMP, "version": 1,
    }


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


@pytest.mark.parametrize("entry", [
    object(),
    OperationLogEntry(UUID("12345678-1234-5678-1234-567812345678"), "operation_started", TIMESTAMP),  # type: ignore[arg-type]
    OperationLogEntry(OPERATION, OperationLogEvent.OPERATION_STARTED, "2026-08-22T00:00:00+00:00"),
])
def test_only_exact_allowlisted_entry_and_timestamp_are_accepted(tmp_path: Path, entry: object) -> None:
    receipt = _writer(tmp_path).append(entry)  # type: ignore[arg-type]
    assert not receipt.log_saved and receipt.error == "technical_log_unavailable"
    assert not _log(tmp_path).exists()


def test_existing_duplicate_nonfinite_and_bad_history_fail_closed(tmp_path: Path) -> None:
    operations = tmp_path / "PropExtract" / "logs" / "operations"
    operations.mkdir(parents=True, mode=0o700)
    path = operations / f"{OPERATION}.jsonl"
    cases = [
        b'{"event":"operation_started","event":"operation_started"}\n',
        b'{"event":NaN}\n',
        json.dumps({"version": 1, "operation_id": str(OPERATION), "event": "truncated", "timestamp": TIMESTAMP,
                    "sequence": 1, "dropped_bytes": 1, "dropped_records": 2}).encode() + b"\n",
    ]
    for data in cases:
        path.write_bytes(data)
        os.chmod(path, 0o600)
        before = path.read_bytes()
        receipt = _receipt(tmp_path)
        assert not receipt.log_saved and receipt.error == "technical_log_unavailable" and path.read_bytes() == before


@pytest.mark.parametrize("dropped_bytes,dropped_records", [(0, 0), (1, 0), (0, 1), (1, 2)])
def test_impossible_truncation_marker_matrix_fails_closed(tmp_path: Path, dropped_bytes: int, dropped_records: int) -> None:
    operations = tmp_path / "PropExtract" / "logs" / "operations"
    operations.mkdir(parents=True, mode=0o700)
    marker = {"version": 1, "operation_id": str(OPERATION), "event": "truncated", "timestamp": TIMESTAMP,
              "sequence": max(dropped_records - 1, 0), "dropped_bytes": dropped_bytes, "dropped_records": dropped_records}
    path = operations / f"{OPERATION}.jsonl"
    path.write_text(json.dumps(marker) + "\n")
    os.chmod(path, 0o600)
    assert not _receipt(tmp_path).log_saved


def test_fixed_temp_cleanup_failure_stays_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _receipt(tmp_path).log_saved
    directory = _log(tmp_path).parent
    temp = directory / f"{OPERATION}.jsonl.tmp"
    temp.write_bytes(_log(tmp_path).read_bytes())
    os.chmod(temp, 0o600)
    original_unlink = os.unlink

    def refuse_temp(name: str, *args: object, **kwargs: object) -> None:
        if name == temp.name:
            raise OSError("cleanup denied")
        original_unlink(name, *args, **kwargs)

    monkeypatch.setattr(os, "unlink", refuse_temp)
    for _ in range(3):
        assert not _receipt(tmp_path, OperationLogEvent.OPERATION_COMPLETED).log_saved
    operation_files = [item for item in directory.iterdir() if item.name.startswith(str(OPERATION) + ".")]
    assert {item.name for item in operation_files} == {f"{OPERATION}.jsonl", f"{OPERATION}.jsonl.lock", temp.name}
    assert len([item for item in operation_files if item.name.endswith((".lock", ".tmp"))]) == MAX_AUXILIARY_FILES


def test_bounded_history_writes_coherent_positive_marker(tmp_path: Path) -> None:
    writer = _writer(tmp_path, max_operation_bytes=430, max_operation_records=3)
    for second in range(5):
        timestamp = f"2026-08-22T00:00:0{second}Z"
        assert writer.append_event(OPERATION, OperationLogEvent.OPERATION_STARTED, timestamp).log_saved
    records = [json.loads(line) for line in _log(tmp_path).read_text().splitlines()]
    marker = records[0]
    assert marker["event"] == "truncated"
    assert marker["dropped_bytes"] > 0 and marker["dropped_records"] > 0
    assert marker["dropped_bytes"] >= marker["dropped_records"] and marker["sequence"] == marker["dropped_records"] - 1
    assert len(_log(tmp_path).read_bytes()) <= 430


def test_symlink_and_missing_capability_never_fall_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "outside"
    target.mkdir()
    try:
        (tmp_path / "PropExtract").symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    assert not _receipt(tmp_path).log_saved
    import rns_import_server.operation_log as module
    monkeypatch.setattr(module, "fcntl", None)
    assert not _receipt(tmp_path / "second").log_saved
    assert not (tmp_path / "second" / "PropExtract").exists()


def test_root_parent_is_fsynced_when_private_root_is_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = os.fsync
    root_inode = tmp_path.stat().st_ino
    fsynced: list[int] = []

    def observe(descriptor: int) -> None:
        fsynced.append(os.fstat(descriptor).st_ino)
        original(descriptor)

    monkeypatch.setattr(os, "fsync", observe)
    assert _receipt(tmp_path).log_saved
    assert root_inode in fsynced


def test_replace_and_cleanup_double_failure_preserves_old_canonical_and_fixed_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _receipt(tmp_path).log_saved
    path = _log(tmp_path)
    before = path.read_bytes()
    temporary = path.with_name(path.name + ".tmp")
    original_unlink = os.unlink

    def fail_replace(*args: object, **kwargs: object) -> None:
        raise OSError("replace denied")

    def fail_temp_cleanup(name: str, *args: object, **kwargs: object) -> None:
        if name == temporary.name:
            raise OSError("cleanup denied")
        original_unlink(name, *args, **kwargs)

    monkeypatch.setattr(os, "replace", fail_replace)
    monkeypatch.setattr(os, "unlink", fail_temp_cleanup)
    assert not _receipt(tmp_path, OperationLogEvent.OPERATION_COMPLETED).log_saved
    assert path.read_bytes() == before and temporary.exists()
    assert len([item for item in path.parent.iterdir() if item.name.startswith(str(OPERATION) + ".")]) == 3


def test_final_symlink_and_visible_inode_swap_fail_without_overwrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _receipt(tmp_path).log_saved
    path = _log(tmp_path)
    outside = tmp_path / "outside.jsonl"
    outside.write_bytes(b"outside")
    os.chmod(outside, 0o600)
    replacement = tmp_path / "replacement.jsonl"
    replacement.write_bytes(path.read_bytes())
    replacement_data = replacement.read_bytes()
    os.chmod(replacement, 0o600)
    original_stat = os.stat
    swapped = False

    def swap_before_binding(name: object, *args: object, **kwargs: object):
        nonlocal swapped
        if name == path.name and kwargs.get("dir_fd") is not None and temporary.exists() and not swapped:
            swapped = True
            os.replace(replacement, path)
        return original_stat(name, *args, **kwargs)

    monkeypatch.setattr(os, "stat", swap_before_binding)
    assert not _receipt(tmp_path, OperationLogEvent.OPERATION_COMPLETED).log_saved
    assert path.read_bytes() == replacement_data
    monkeypatch.undo()
    path.unlink()
    path.symlink_to(outside)
    assert not _receipt(tmp_path).log_saved and outside.read_bytes() == b"outside"


def test_per_operation_lock_serializes_two_appenders(tmp_path: Path) -> None:
    writer = _writer(tmp_path)
    ready = threading.Barrier(2)
    receipts: list[object] = []

    def append(timestamp: str) -> None:
        ready.wait()
        receipts.append(writer.append_event(OPERATION, OperationLogEvent.OPERATION_STARTED, timestamp))

    threads = [threading.Thread(target=append, args=(f"2026-08-22T00:00:0{second}Z",)) for second in (0, 1)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert all(receipt.log_saved for receipt in receipts)  # type: ignore[union-attr]
    assert [record["sequence"] for record in map(json.loads, _log(tmp_path).read_text().splitlines())] == [0, 1]
