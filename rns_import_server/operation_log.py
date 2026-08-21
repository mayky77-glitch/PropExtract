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
import stat
import threading
import uuid
from typing import Final

try:  # ``fcntl`` is unavailable on Windows; do not pretend its lock exists.
    import fcntl
except ImportError:  # pragma: no cover - exercised on Windows only
    fcntl = None  # type: ignore[assignment]


LOG_ERROR_CODE: Final = "technical_log_unavailable"
LOG_SCHEMA: Final = "operation-private-log-v1"
MAX_RECORD_BYTES: Final = 4 * 1024
MAX_OPERATION_BYTES: Final = 64 * 1024
_TRUNCATION_RESERVE: Final = 1024
_EVENT_KEYS: Final = frozenset({"event_type", "stage", "code", "detail_code"})
_EVENTS: Final = frozenset({
    ("operation_started", "operation", "started", "none"),
    ("checkpoint", "publication", "checkpoint_reached", "none"),
    ("operation_failed", "operation", "technical_log_unavailable", "none"),
    ("operation_finished", "operation", "finished", "none"),
})
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


def _event_dto(value: object) -> dict[str, str]:
    if type(value) is not dict or set(value) != _EVENT_KEYS:
        raise OperationLogError()
    fields = (value["event_type"], value["stage"], value["code"], value["detail_code"])
    if fields not in _EVENTS:
        raise OperationLogError()
    return {
        "event_type": fields[0], "stage": fields[1], "code": fields[2], "detail_code": fields[3],
    }


def _canonical_line(record: dict[str, object]) -> bytes:
    try:
        return (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise OperationLogError() from exc


def _truncate_record(record: dict[str, object]) -> bytes:
    """Fit one safe DTO in the record cap without retaining dropped bytes."""
    line = _canonical_line(record)
    if len(line) <= MAX_RECORD_BYTES:
        return line
    # No caller-provided content is serializable.  If a future cap cannot
    # hold this finite schema, fail closed rather than silently changing it.
    raise OperationLogError()


def _private_mode(info: os.stat_result, *, directory: bool) -> bool:
    expected_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    return expected_type and (stat.S_IMODE(info.st_mode) & 0o077) == 0


def _require_no_follow() -> int:
    value = getattr(os, "O_NOFOLLOW", None)
    if not isinstance(value, int):
        raise OperationLogError()
    return value


def _open_directory_component(parent_descriptor: int, name: str, *, private: bool, create: bool) -> int:
    """Create/open a static child through an already verified parent FD."""
    no_follow = _require_no_follow()
    if create:
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_descriptor)
        except FileExistsError:
            pass
        except OSError as exc:
            raise OperationLogError() from exc
    try:
        info = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or (private and not _private_mode(info, directory=True)):
            raise OperationLogError()
        descriptor = os.open(name, os.O_RDONLY | os.O_DIRECTORY | no_follow, dir_fd=parent_descriptor)
        current = os.fstat(descriptor)
        if not stat.S_ISDIR(current.st_mode) or (private and not _private_mode(current, directory=True)):
            os.close(descriptor)
            raise OperationLogError()
        return descriptor
    except OperationLogError:
        raise
    except (OSError, ValueError) as exc:
        raise OperationLogError() from exc


def _root_descriptors(data_root: Path, *, create_root: bool) -> list[int]:
    """Walk every visible data-root ancestor by FD, refusing links and races."""
    if not data_root.is_absolute():
        raise OperationLogError()
    descriptors: list[int] = []
    try:
        anchor = data_root.anchor
        if not anchor or any(part in {".", ".."} for part in data_root.parts):
            raise OperationLogError()
        descriptors.append(os.open(anchor, os.O_RDONLY | os.O_DIRECTORY | _require_no_follow()))
        parts = data_root.parts[1:]
        if not parts:
            raise OperationLogError()
        for index, part in enumerate(parts):
            descriptors.append(_open_directory_component(
                descriptors[-1], part, private=index == len(parts) - 1, create=create_root and index == len(parts) - 1,
            ))
        return descriptors
    except BaseException:
        for descriptor in descriptors:
            os.close(descriptor)
        raise


def _private_log_path(data_root: Path, operation_id: str, *, create: bool) -> tuple[Path, list[int]]:
    descriptors = _root_descriptors(data_root, create_root=create)
    try:
        descriptors.append(_open_directory_component(descriptors[-1], "logs", private=True, create=create))
        descriptors.append(_open_directory_component(descriptors[-1], "operations", private=True, create=create))
        return data_root / "logs" / "operations" / f"{operation_id}.jsonl", descriptors
    except BaseException:
        for descriptor in descriptors:
            os.close(descriptor)
        raise


def _close_descriptors(descriptors: list[int]) -> None:
    for descriptor in descriptors:
        os.close(descriptor)


def _visible_file_matches(data_root: Path, operation_id: str, expected: os.stat_result) -> bool:
    descriptors: list[int] = []
    try:
        _path, descriptors = _private_log_path(data_root, operation_id, create=False)
        current = os.stat(f"{operation_id}.jsonl", dir_fd=descriptors[-1], follow_symlinks=False)
        return stat.S_ISREG(current.st_mode) and (current.st_dev, current.st_ino) == (expected.st_dev, expected.st_ino)
    except (OperationLogError, OSError, ValueError):
        return False
    finally:
        _close_descriptors(descriptors)


def _all_write(descriptor: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(descriptor, data[offset:])
        if written <= 0:
            raise OSError("short operation log write")
        offset += written


def _valid_existing_jsonl(descriptor: int, size: int) -> bool:
    if size < 0 or size > MAX_OPERATION_BYTES:
        return False
    data = os.pread(descriptor, size, 0)
    if len(data) != size or (data and not data.endswith(b"\n")):
        return False
    try:
        return all(type(json.loads(line)) is dict for line in data.decode("utf-8").splitlines())
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False


def _write_with_rollback(descriptor: int, prior_size: int, line: bytes) -> None:
    try:
        _all_write(descriptor, line)
        os.fsync(descriptor)
    except BaseException:
        try:
            os.ftruncate(descriptor, prior_size)
            os.fsync(descriptor)
        except BaseException as restore_error:
            raise OperationLogError() from restore_error
        raise


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
        line = _truncate_record(record)
        root = Path(data_root)
        path, directories = _private_log_path(root, canonical_id, create=True)
        try:
            lock_key = str(path)
            with _thread_locks_guard:
                lock = _thread_locks.setdefault(lock_key, threading.Lock())
            with lock:
                no_follow = _require_no_follow()
                flags = os.O_RDWR | os.O_APPEND | os.O_CREAT | no_follow
                descriptor = os.open(path.name, flags, 0o600, dir_fd=directories[-1])
                try:
                    info = os.fstat(descriptor)
                    if not _private_mode(info, directory=False):
                        raise OperationLogError()
                    if not _visible_file_matches(root, canonical_id, info):
                        raise OperationLogError()
                    if fcntl is None:
                        raise OperationLogError()
                    fcntl.flock(descriptor, fcntl.LOCK_EX)
                    try:
                        current_size = os.fstat(descriptor).st_size
                        if not _valid_existing_jsonl(descriptor, current_size):
                            raise OperationLogError()
                        if current_size < 0 or current_size + len(line) > MAX_OPERATION_BYTES - _TRUNCATION_RESERVE:
                            marker = _canonical_line({
                                "event": "history_truncated", "schema": LOG_SCHEMA,
                                "truncation": {"dropped_bytes": len(line), "dropped_records": 1},
                            })
                            if current_size + len(marker) > MAX_OPERATION_BYTES:
                                raise OperationLogError()
                            _write_with_rollback(descriptor, current_size, marker)
                        else:
                            _write_with_rollback(descriptor, current_size, line)
                        if not _visible_file_matches(root, canonical_id, info):
                            raise OperationLogError()
                    finally:
                        fcntl.flock(descriptor, fcntl.LOCK_UN)
                finally:
                    os.close(descriptor)
                for directory in directories[-3:]:
                    os.fsync(directory)
        finally:
            _close_descriptors(directories)
    except (OperationLogError, OSError, ValueError, TypeError):
        return _receipt(canonical_id, saved=False)
    return _receipt(canonical_id, saved=True)
