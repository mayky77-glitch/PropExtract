from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import threading
import uuid

import pytest

from rns_import_server import operation_log


OPERATION_ID = "123e4567-e89b-42d3-a456-426614174000"


def event(detail_code: str = "safe_diagnostic", *, stage: str = "publication", code: str = "checkpoint_reached") -> dict[str, str]:
    return {"event_type": "checkpoint", "stage": stage, "code": code, "detail_code": detail_code}


def append(root: Path, **kwargs: object) -> operation_log.OperationLogReceipt:
    return operation_log.append_operation_log(root, OPERATION_ID, kwargs.pop("event", event()), recorded_at="2026-08-22T00:00:00Z", sequence=1, **kwargs)


def log_path(root: Path) -> Path:
    return root / "logs" / "operations" / f"{OPERATION_ID}.jsonl"


def test_writes_exact_private_canonical_jsonl_and_public_receipt(tmp_path: Path):
    root = tmp_path / "PropExtract"
    receipt = append(root)

    assert receipt.as_dict() == {"operation_id": OPERATION_ID, "log_saved": True, "error": None}
    path = log_path(root)
    assert path.read_bytes().endswith(b"\n")
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "event": event(), "recorded_at": "2026-08-22T00:00:00Z", "schema": "operation-private-log-v1", "sequence": 1,
    }
    # POSIX modes are only a local proof; this does not qualify Windows DACLs.
    assert stat.S_IMODE(path.stat().st_mode) & 0o077 == 0
    assert all(stat.S_IMODE(path.parent.parent.stat().st_mode) & 0o077 == 0 for _ in [0])


@pytest.mark.parametrize("bad", [uuid.UUID(OPERATION_ID), OPERATION_ID.upper(), "{" + OPERATION_ID + "}", OPERATION_ID.replace("-", ""), "not-a-uuid"])
def test_rejects_noncanonical_or_non_string_uuid_without_creating_log(tmp_path: Path, bad: object):
    with pytest.raises(operation_log.OperationLogError, match="technical_log_unavailable"):
        operation_log.append_operation_log(tmp_path / "PropExtract", bad, event(), recorded_at="2026-08-22T00:00:00Z", sequence=1)
    assert not (tmp_path / "PropExtract").exists()


@pytest.mark.parametrize("bad", [
    {"event_type": "checkpoint", "stage": "x", "code": "x", "detail_code": float("nan")},
    {"event_type": "checkpoint", "stage": "x", "code": "x", "detail_code": object()},
    {"event_type": "checkpoint", "stage": "x", "code": "x", "detail_code": "raw_private_path_secret", "private_path": "/secret"},
    {"event_type": "unlisted", "stage": "x", "code": "x", "detail_code": "x"},
    {"event_type": "checkpoint", "stage": "x", "code": "x", "detail_code": "/private/raw_ocr_text"},
])
def test_strict_allowlisted_dto_rejects_unserializable_and_extra_input(tmp_path: Path, bad: object):
    assert append(tmp_path / "PropExtract", event=bad).as_dict() == {"operation_id": OPERATION_ID, "log_saved": False, "error": "technical_log_unavailable"}


def test_content_and_history_caps_emit_deterministic_metadata(monkeypatch, tmp_path: Path):
    root = tmp_path / "PropExtract"
    monkeypatch.setattr(operation_log, "MAX_RECORD_BYTES", 500)
    monkeypatch.setattr(operation_log, "MAX_OPERATION_BYTES", 1100)
    monkeypatch.setattr(operation_log, "_TRUNCATION_RESERVE", 300)
    first = append(root, event=event("d" * 128, stage="s" * 128, code="c" * 128))
    second = operation_log.append_operation_log(root, OPERATION_ID, event("second"), recorded_at="2026-08-22T00:00:01Z", sequence=2)
    third = operation_log.append_operation_log(root, OPERATION_ID, event("third"), recorded_at="2026-08-22T00:00:02Z", sequence=3)
    lines = [json.loads(line) for line in log_path(root).read_text(encoding="utf-8").splitlines()]
    assert first.log_saved and second.log_saved and third.log_saved
    assert len(log_path(root).read_bytes()) <= operation_log.MAX_OPERATION_BYTES
    assert lines[0]["truncation"]["dropped_characters"] > 0
    assert lines[-1]["event"] == "history_truncated"
    assert lines[-1]["truncation"]["dropped_records"] == 1


def test_concurrent_appends_keep_framing_and_replay_is_deterministic(tmp_path: Path):
    root = tmp_path / "PropExtract"
    results: list[operation_log.OperationLogReceipt] = []

    def write(number: int) -> None:
        results.append(operation_log.append_operation_log(root, OPERATION_ID, event(f"item_{number}"), recorded_at="2026-08-22T00:00:00Z", sequence=number))

    threads = [threading.Thread(target=write, args=(number,)) for number in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert all(receipt.log_saved for receipt in results)
    lines = log_path(root).read_bytes().splitlines()
    assert len(lines) == 12
    assert all(json.loads(line)["schema"] == "operation-private-log-v1" for line in lines)


def test_symlink_nonregular_and_insecure_targets_fail_closed(tmp_path: Path):
    root = tmp_path / "PropExtract"
    root.mkdir(mode=0o700)
    (root / "logs").symlink_to(tmp_path)
    assert append(root).log_saved is False

    root2 = tmp_path / "Second"
    operations = root2 / "logs" / "operations"
    operations.mkdir(parents=True, mode=0o700)
    path = log_path(root2)
    path.mkdir()
    assert append(root2).log_saved is False

    root3 = tmp_path / "Third"
    target = log_path(root3)
    target.parent.mkdir(parents=True, mode=0o700)
    target.write_text("", encoding="utf-8")
    os.chmod(target, 0o644)
    assert append(root3).log_saved is False


def test_replacement_race_before_directory_open_fails_closed(monkeypatch, tmp_path: Path):
    root = tmp_path / "PropExtract"
    (root / "logs" / "operations").mkdir(parents=True, mode=0o700)
    original_open = operation_log.os.open
    replaced = False

    def racing_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        nonlocal replaced
        if path == "operations" and not replaced:
            replaced = True
            os.rmdir(root / "logs" / "operations")
            (root / "logs" / "operations").symlink_to(tmp_path)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(operation_log.os, "open", racing_open)
    assert append(root).as_dict() == {"operation_id": OPERATION_ID, "log_saved": False, "error": "technical_log_unavailable"}


def test_secure_write_and_parent_fsync_failures_return_only_typed_receipt(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(operation_log.os, "write", lambda *_args: (_ for _ in ()).throw(OSError("write failure")))
    assert append(tmp_path / "One").as_dict() == {"operation_id": OPERATION_ID, "log_saved": False, "error": "technical_log_unavailable"}

    original_fsync = operation_log.os.fsync
    monkeypatch.setattr(operation_log.os, "fsync", lambda descriptor: (_ for _ in ()).throw(OSError("fsync failure")) if descriptor != -1 else original_fsync(descriptor))
    assert append(tmp_path / "Two").as_dict() == {"operation_id": OPERATION_ID, "log_saved": False, "error": "technical_log_unavailable"}
