"""Private, operation-scoped technical JSONL logging.

This module is deliberately a standalone port.  Its only persistence target is
the caller-injected PropExtract data root; it neither discovers nor falls back
to another location.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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


def _canonical_timestamp(value: object) -> str:
    if type(value) is not str or len(value) != 20 or not value.endswith("Z"):
        raise OperationLogError()
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise OperationLogError() from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise OperationLogError()
    return value


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


def _require_directory_flags() -> int:
    no_follow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    if not isinstance(no_follow, int) or not isinstance(directory, int):
        raise OperationLogError()
    return no_follow | directory


def _require_locking() -> None:
    if fcntl is None or not callable(getattr(fcntl, "flock", None)) or not isinstance(getattr(fcntl, "LOCK_EX", None), int) or not isinstance(getattr(fcntl, "LOCK_UN", None), int):
        raise OperationLogError()


def _open_directory_component(parent_descriptor: int, name: str, *, private: bool, create: bool, created_parents: list[int]) -> int:
    """Create/open a static child through an already verified parent FD."""
    flags = _require_directory_flags()
    if create:
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_descriptor)
            created_parents.append(parent_descriptor)
        except FileExistsError:
            pass
        except OSError as exc:
            raise OperationLogError() from exc
    try:
        info = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or (private and not _private_mode(info, directory=True)):
            raise OperationLogError()
        descriptor = os.open(name, os.O_RDONLY | flags, dir_fd=parent_descriptor)
        current = os.fstat(descriptor)
        if not stat.S_ISDIR(current.st_mode) or (private and not _private_mode(current, directory=True)):
            os.close(descriptor)
            raise OperationLogError()
        return descriptor
    except OperationLogError:
        raise
    except (OSError, ValueError) as exc:
        raise OperationLogError() from exc


def _root_descriptors(data_root: Path, *, create_root: bool, created_parents: list[int]) -> list[int]:
    """Walk every visible data-root ancestor by FD, refusing links and races."""
    if not data_root.is_absolute():
        raise OperationLogError()
    descriptors: list[int] = []
    try:
        anchor = data_root.anchor
        if not anchor or any(part in {".", ".."} for part in data_root.parts):
            raise OperationLogError()
        descriptors.append(os.open(anchor, os.O_RDONLY | _require_directory_flags()))
        parts = data_root.parts[1:]
        if not parts:
            raise OperationLogError()
        for index, part in enumerate(parts):
            descriptors.append(_open_directory_component(
                descriptors[-1], part, private=index == len(parts) - 1, create=create_root and index == len(parts) - 1, created_parents=created_parents,
            ))
        return descriptors
    except BaseException:
        for descriptor in descriptors:
            os.close(descriptor)
        raise


def _private_log_path(data_root: Path, operation_id: str, *, create: bool, created_parents: list[int] | None = None) -> tuple[Path, list[int]]:
    created = created_parents if created_parents is not None else []
    descriptors = _root_descriptors(data_root, create_root=create, created_parents=created)
    try:
        descriptors.append(_open_directory_component(descriptors[-1], "logs", private=True, create=create, created_parents=created))
        descriptors.append(_open_directory_component(descriptors[-1], "operations", private=True, create=create, created_parents=created))
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


def _reject_json_constant(_value: str) -> None:
    raise ValueError("non-finite JSON constant")


def _no_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _strict_json(value: bytes) -> object:
    return json.loads(value.decode("utf-8"), parse_constant=_reject_json_constant, object_pairs_hook=_no_duplicate_json_keys)


def _valid_existing_record(value: object) -> bool:
    if type(value) is not dict:
        return False
    if set(value) == {"schema", "event", "recorded_at", "sequence"}:
        try:
            return value["schema"] == LOG_SCHEMA and _event_dto(value["event"]) is not None and _canonical_timestamp(value["recorded_at"]) is not None and type(value["sequence"]) is int and value["sequence"] >= 0
        except OperationLogError:
            return False
    if set(value) == {"schema", "event", "truncation"}:
        truncation = value["truncation"]
        return value["schema"] == LOG_SCHEMA and value["event"] == "history_truncated" and type(truncation) is dict and set(truncation) == {"dropped_bytes", "dropped_records"} and all(type(truncation[key]) is int and truncation[key] >= 0 for key in truncation)
    return False


def _read_existing_jsonl(descriptor: int, size: int) -> bytes | None:
    if size < 0 or size > MAX_OPERATION_BYTES:
        return None
    data = os.pread(descriptor, size, 0)
    if len(data) != size or (data and not data.endswith(b"\n")):
        return None
    try:
        return data if all(_valid_existing_record(_strict_json(line)) for line in data.splitlines()) else None
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None


def _atomic_replace(operation_descriptor: int, filename: str, data: bytes) -> None:
    """Publish a complete old-or-new JSONL file; partial temp writes stay invisible."""
    _require_directory_flags()
    no_follow = getattr(os, "O_NOFOLLOW")
    temporary = f".{filename}.{uuid.uuid4().hex}.tmp"
    descriptor = -1
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | no_follow, 0o600, dir_fd=operation_descriptor)
        _all_write(descriptor, data)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, filename, src_dir_fd=operation_descriptor, dst_dir_fd=operation_descriptor)
        os.fsync(operation_descriptor)
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=operation_descriptor)
        except OSError:
            pass
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
        timestamp = _canonical_timestamp(recorded_at)
        if type(sequence) is not int or sequence < 0:
            raise OperationLogError()
        dto = _event_dto(event)
        record: dict[str, object] = {"event": dto, "recorded_at": timestamp, "schema": LOG_SCHEMA, "sequence": sequence}
        line = _truncate_record(record)
        root = Path(data_root)
        created_parents: list[int] = []
        path, directories = _private_log_path(root, canonical_id, create=True, created_parents=created_parents)
        try:
            lock_key = str(path)
            with _thread_locks_guard:
                lock = _thread_locks.setdefault(lock_key, threading.Lock())
            with lock:
                _require_locking()
                no_follow = getattr(os, "O_NOFOLLOW")
                lock_name = f".{path.name}.lock"
                descriptor = os.open(lock_name, os.O_RDWR | os.O_CREAT | no_follow, 0o600, dir_fd=directories[-1])
                try:
                    info = os.fstat(descriptor)
                    if not _private_mode(info, directory=False):
                        raise OperationLogError()
                    fcntl.flock(descriptor, fcntl.LOCK_EX)
                    try:
                        try:
                            file_descriptor = os.open(path.name, os.O_RDONLY | no_follow, dir_fd=directories[-1])
                        except FileNotFoundError:
                            file_descriptor = -1
                            current = b""
                        else:
                            try:
                                file_info = os.fstat(file_descriptor)
                                if not _private_mode(file_info, directory=False) or not _visible_file_matches(root, canonical_id, file_info):
                                    raise OperationLogError()
                                current = _read_existing_jsonl(file_descriptor, file_info.st_size)
                            finally:
                                os.close(file_descriptor)
                        if current is None:
                            raise OperationLogError()
                        if len(current) + len(line) > MAX_OPERATION_BYTES - _TRUNCATION_RESERVE:
                            marker = _canonical_line({
                                "event": "history_truncated", "schema": LOG_SCHEMA,
                                "truncation": {"dropped_bytes": len(line), "dropped_records": 1},
                            })
                            if len(current) + len(marker) > MAX_OPERATION_BYTES:
                                raise OperationLogError()
                            next_data = current + marker
                        else:
                            next_data = current + line
                        _atomic_replace(directories[-1], path.name, next_data)
                        current_info = os.stat(path.name, dir_fd=directories[-1], follow_symlinks=False)
                        if not _visible_file_matches(root, canonical_id, current_info):
                            raise OperationLogError()
                    finally:
                        fcntl.flock(descriptor, fcntl.LOCK_UN)
                finally:
                    os.close(descriptor)
                for directory in created_parents:
                    os.fsync(directory)
                for directory in directories[-3:]:
                    os.fsync(directory)
        finally:
            _close_descriptors(directories)
    except (OperationLogError, OSError, ValueError, TypeError, AttributeError):
        return _receipt(canonical_id, saved=False)
    return _receipt(canonical_id, saved=True)
