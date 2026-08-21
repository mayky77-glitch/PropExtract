"""Private, operation-scoped technical JSONL logging.

This module is deliberately a standalone port.  Its only persistence target is
the caller-injected PropExtract data root; it neither discovers nor falls back
to another location.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat
import threading
import uuid
from typing import Final, Mapping

try:  # ``fcntl`` is unavailable on Windows; do not pretend its lock exists.
    import fcntl
except ImportError:  # pragma: no cover - exercised on Windows only
    fcntl = None  # type: ignore[assignment]


LOG_ERROR_CODE: Final = "technical_log_unavailable"
LOG_SCHEMA: Final = "operation-private-log-v1"
MAX_RECORD_BYTES: Final = 4 * 1024
MAX_OPERATION_BYTES: Final = 64 * 1024
_TRUNCATION_RESERVE: Final = 1024
_EVENT_TYPES: Final = frozenset({"operation_started", "checkpoint", "operation_failed", "operation_finished"})
_EVENT_KEYS: Final = frozenset({"event_type", "stage", "code", "detail_code"})
_SAFE_CODE: Final = re.compile(r"[a-z][a-z0-9_]{0,127}\Z")
_thread_locks: dict[str, threading.Lock] = {}
_thread_locks_guard = threading.Lock()


class OperationLogError(RuntimeError):
    """A technical log failure whose public code is intentionally stable."""

    code: str = LOG_ERROR_CODE

    def __init__(self) -> None:
        super().__init__(LOG_ERROR_CODE)


@dataclass(frozen=True)
class OperationLogReceipt:
    """The safe public result; it intentionally contains no diagnostic data."""

    operation_id: str
    log_saved: bool
    error: str | None

    def as_dict(self) -> dict[str, str | bool | None]:
        return {"operation_id": self.operation_id, "log_saved": self.log_saved, "error": self.error}


def _canonical_operation_id(value: object) -> str:
    if type(value) is not str:
        raise OperationLogError()
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise OperationLogError() from exc
    canonical = str(parsed)
    if value != canonical or parsed.variant != uuid.RFC_4122 or parsed.version is None:
        raise OperationLogError()
    return canonical


def _validate_code(value: object) -> str:
    if type(value) is not str or _SAFE_CODE.fullmatch(value) is None:
        raise OperationLogError()
    return value


def _event_dto(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping) or type(value) is not dict or set(value) != _EVENT_KEYS:
        raise OperationLogError()
    event_type = _validate_code(value["event_type"])
    if event_type not in _EVENT_TYPES:
        raise OperationLogError()
    return {
        "event_type": event_type,
        "stage": _validate_code(value["stage"]),
        "code": _validate_code(value["code"]),
        "detail_code": _validate_code(value["detail_code"]),
    }


def _canonical_line(record: dict[str, object]) -> bytes:
    try:
        return (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise OperationLogError() from exc


def _truncate_message(record: dict[str, object]) -> bytes:
    """Fit one safe DTO in the record cap without retaining dropped bytes."""
    line = _canonical_line(record)
    if len(line) <= MAX_RECORD_BYTES:
        return line
    event = record["event"]
    assert isinstance(event, dict)
    detail_code = event["detail_code"]
    assert type(detail_code) is str
    original_bytes = len(detail_code.encode("utf-8"))
    low, high, chosen = 1, len(detail_code), ""
    while low <= high:
        middle = (low + high) // 2
        candidate = dict(record)
        candidate_event = dict(event)
        candidate_event["detail_code"] = detail_code[:middle]
        candidate["event"] = candidate_event
        candidate["truncation"] = {
            "dropped_bytes": original_bytes - len(detail_code[:middle].encode("utf-8")),
            "dropped_characters": len(detail_code) - middle,
        }
        candidate_line = _canonical_line(candidate)
        if len(candidate_line) <= MAX_RECORD_BYTES:
            chosen = detail_code[:middle]
            line = candidate_line
            low = middle + 1
        else:
            high = middle - 1
    if not chosen:
        # The fixed DTO can always fit this cap; retaining this boundary keeps
        # a future cap change fail-closed instead of emitting invalid JSONL.
        raise OperationLogError()
    return line


def _private_mode(info: os.stat_result, *, directory: bool) -> bool:
    expected_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    return expected_type and (stat.S_IMODE(info.st_mode) & 0o077) == 0


def _require_no_follow() -> int:
    value = getattr(os, "O_NOFOLLOW", None)
    if not isinstance(value, int):
        raise OperationLogError()
    return value


def _open_private_directory(path: Path) -> int:
    """Create and open a directory only when it is private and not a link."""
    no_follow = _require_no_follow()
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not _private_mode(info, directory=True):
            raise OperationLogError()
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | no_follow)
        current = os.fstat(descriptor)
        if not _private_mode(current, directory=True):
            os.close(descriptor)
            raise OperationLogError()
        return descriptor
    except OperationLogError:
        raise
    except (OSError, ValueError) as exc:
        raise OperationLogError() from exc


def _open_private_child(parent_descriptor: int, name: str) -> int:
    """Create/open a static child through an already verified parent FD."""
    no_follow = _require_no_follow()
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent_descriptor)
    except FileExistsError:
        pass
    except OSError as exc:
        raise OperationLogError() from exc
    try:
        info = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        if stat.S_ISLNK(info.st_mode) or not _private_mode(info, directory=True):
            raise OperationLogError()
        descriptor = os.open(name, os.O_RDONLY | os.O_DIRECTORY | no_follow, dir_fd=parent_descriptor)
        current = os.fstat(descriptor)
        if not _private_mode(current, directory=True):
            os.close(descriptor)
            raise OperationLogError()
        return descriptor
    except OperationLogError:
        raise
    except (OSError, ValueError) as exc:
        raise OperationLogError() from exc


def _private_log_path(data_root: Path, operation_id: str) -> tuple[Path, list[int]]:
    if not data_root.is_absolute():
        raise OperationLogError()
    descriptors: list[int] = []
    try:
        descriptors.append(_open_private_directory(data_root))
        descriptors.append(_open_private_child(descriptors[-1], "logs"))
        descriptors.append(_open_private_child(descriptors[-1], "operations"))
        return data_root / "logs" / "operations" / f"{operation_id}.jsonl", descriptors
    except BaseException:
        for descriptor in descriptors:
            os.close(descriptor)
        raise


def _all_write(descriptor: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(descriptor, data[offset:])
        if written <= 0:
            raise OSError("short operation log write")
        offset += written


def _receipt(operation_id: str, *, saved: bool) -> OperationLogReceipt:
    return OperationLogReceipt(operation_id=operation_id, log_saved=saved, error=None if saved else LOG_ERROR_CODE)


def append_operation_log(
    data_root: Path | str,
    operation_id: object,
    event: object,
    *,
    recorded_at: str,
    sequence: int,
) -> OperationLogReceipt:
    """Append one deterministic, sanitized record or return a typed failure.

    ``recorded_at`` and ``sequence`` are injected authority.  They are kept
    strict so this port never manufactures clock or ordering values.
    """
    canonical_id = _canonical_operation_id(operation_id)
    try:
        if type(recorded_at) is not str or not recorded_at or len(recorded_at) > 64:
            raise OperationLogError()
        if type(sequence) is not int or sequence < 0:
            raise OperationLogError()
        dto = _event_dto(event)
        record: dict[str, object] = {"event": dto, "recorded_at": recorded_at, "schema": LOG_SCHEMA, "sequence": sequence}
        line = _truncate_message(record)
        root = Path(data_root)
        path, directories = _private_log_path(root, canonical_id)
        try:
            lock_key = str(path)
            with _thread_locks_guard:
                lock = _thread_locks.setdefault(lock_key, threading.Lock())
            with lock:
                no_follow = _require_no_follow()
                flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | no_follow
                descriptor = os.open(path.name, flags, 0o600, dir_fd=directories[-1])
                try:
                    info = os.fstat(descriptor)
                    if not _private_mode(info, directory=False):
                        raise OperationLogError()
                    if fcntl is None:
                        raise OperationLogError()
                    fcntl.flock(descriptor, fcntl.LOCK_EX)
                    try:
                        current_size = os.fstat(descriptor).st_size
                        if current_size < 0 or current_size + len(line) > MAX_OPERATION_BYTES - _TRUNCATION_RESERVE:
                            marker = _canonical_line({
                                "event": "history_truncated", "schema": LOG_SCHEMA,
                                "truncation": {"dropped_bytes": len(line), "dropped_records": 1},
                            })
                            if current_size + len(marker) > MAX_OPERATION_BYTES:
                                raise OperationLogError()
                            _all_write(descriptor, marker)
                        else:
                            _all_write(descriptor, line)
                        os.fsync(descriptor)
                    finally:
                        fcntl.flock(descriptor, fcntl.LOCK_UN)
                finally:
                    os.close(descriptor)
                for directory in directories:
                    os.fsync(directory)
        finally:
            for directory in directories:
                os.close(directory)
    except (OperationLogError, OSError, ValueError, TypeError):
        return _receipt(canonical_id, saved=False)
    return _receipt(canonical_id, saved=True)
