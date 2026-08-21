"""Private, bounded, operation-scoped JSONL technical logs.

This module is deliberately an injected local-storage boundary.  It has no
server, report, workbook, or native-process integration.  An unavailable
platform or an unsafe filesystem observation is a typed public failure, never
a fallback to another location.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import json
import os
from pathlib import Path
import re
import stat
from typing import Final
from uuid import UUID

try:  # Imported lazily enough that non-POSIX hosts fail closed at the boundary.
    import fcntl
except ImportError:  # pragma: no cover - exercised by the capability guard.
    fcntl = None  # type: ignore[assignment]


MAX_OPERATION_BYTES: Final = 64 * 1024
MAX_OPERATION_RECORDS: Final = 256
MAX_AUXILIARY_FILES: Final = 2  # stable lock plus one fixed recovery temp
_VERSION: Final = 1
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")


class OperationLogEvent(StrEnum):
    """The finite, payload-free event vocabulary permitted in a log."""

    OPERATION_STARTED = "operation_started"
    OPERATION_COMPLETED = "operation_completed"
    OPERATION_FAILED = "operation_failed"


class OperationLogError(RuntimeError):
    """Internal typed failure; its public representation is intentionally fixed."""

    code = "technical_log_unavailable"

    def __init__(self) -> None:
        super().__init__(self.code)


@dataclass(frozen=True)
class OperationLogEntry:
    operation_id: UUID
    event: OperationLogEvent
    timestamp: str


@dataclass(frozen=True)
class OperationLogReceipt:
    """The sole public result.  Do not add diagnostic/path/content fields."""

    operation_id: str
    log_saved: bool
    error: str | None


def strict_operation_timestamp(value: object) -> str:
    """Accept only an exact whole-second UTC representation."""
    if type(value) is not str or _TIMESTAMP.fullmatch(value) is None:
        raise OperationLogError()
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except (TypeError, ValueError, OverflowError) as error:
        raise OperationLogError() from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed) or parsed.microsecond:
        raise OperationLogError()
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_operation_id(value: object) -> str:
    if type(value) is not UUID:
        raise OperationLogError()
    canonical = str(value)
    if UUID(canonical) != value or canonical != str(value):
        raise OperationLogError()
    return canonical


def _json_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            raise ValueError("duplicate json member")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> object:
    raise ValueError("non-finite json")


def _encoded(record: dict[str, object]) -> bytes:
    return json.dumps(record, ensure_ascii=True, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("ascii") + b"\n"


def _strict_line(line: bytes, operation_id: str) -> dict[str, object]:
    if not line or not line.endswith(b"\n"):
        raise OperationLogError()
    try:
        raw = line[:-1].decode("utf-8")
        value = json.loads(raw, object_pairs_hook=_json_pairs, parse_constant=_reject_nonfinite)
    except (UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise OperationLogError() from error
    if type(value) is not dict:
        raise OperationLogError()
    common = {"version", "operation_id", "event", "timestamp", "sequence"}
    event = value.get("event")
    if event == "truncated":
        if set(value) != common | {"dropped_bytes", "dropped_records"}:
            raise OperationLogError()
        if (type(value["dropped_bytes"]) is not int or type(value["dropped_records"]) is not int
                or value["dropped_bytes"] <= 0 or value["dropped_records"] <= 0
                or value["dropped_bytes"] < value["dropped_records"]):
            raise OperationLogError()
    else:
        if set(value) != common or event not in {member.value for member in OperationLogEvent}:
            raise OperationLogError()
    if (value.get("version") != _VERSION or value.get("operation_id") != operation_id
            or type(value.get("sequence")) is not int or value["sequence"] < 0):
        raise OperationLogError()
    strict_operation_timestamp(value.get("timestamp"))
    return value


def _parse_jsonl(data: bytes, operation_id: str) -> tuple[list[dict[str, object]], list[bytes]]:
    if not data:
        return [], []
    if not data.endswith(b"\n") or b"\r" in data:
        raise OperationLogError()
    lines = data.splitlines(keepends=True)
    records = [_strict_line(line, operation_id) for line in lines]
    marker = records[0] if records and records[0]["event"] == "truncated" else None
    if any(item["event"] == "truncated" for item in records[1:]):
        raise OperationLogError()
    expected = 0
    if marker is not None:
        dropped = marker["dropped_records"]
        if marker["sequence"] != dropped - 1:
            raise OperationLogError()
        expected = dropped
    for record in records[1 if marker is not None else 0:]:
        if record["sequence"] != expected:
            raise OperationLogError()
        expected += 1
    return records, lines


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino, left.st_mode, left.st_nlink, left.st_size, left.st_mtime_ns, left.st_ctime_ns) == (
        right.st_dev, right.st_ino, right.st_mode, right.st_nlink, right.st_size, right.st_mtime_ns, right.st_ctime_ns
    )


def _same_inode(left: os.stat_result, right: os.stat_result) -> bool:
    """Rename may legitimately advance ctime; identity and private shape may not."""
    return (left.st_dev, left.st_ino, left.st_mode, left.st_nlink, left.st_size) == (
        right.st_dev, right.st_ino, right.st_mode, right.st_nlink, right.st_size
    )


class OperationLogWriter:
    """Append one allowlisted event using a private LocalAppData-style root."""

    def __init__(self, local_app_data: str, *, max_operation_bytes: int = MAX_OPERATION_BYTES,
                 max_operation_records: int = MAX_OPERATION_RECORDS) -> None:
        self._local_app_data = local_app_data
        self._max_bytes = max_operation_bytes
        self._max_records = max_operation_records

    def append(self, entry: OperationLogEntry) -> OperationLogReceipt:
        operation_id = ""
        try:
            if type(entry) is not OperationLogEntry:
                raise OperationLogError()
            operation_id = _canonical_operation_id(entry.operation_id)
            if type(entry.event) is not OperationLogEvent:
                raise OperationLogError()
            timestamp = strict_operation_timestamp(entry.timestamp)
            if (type(self._local_app_data) is not str or type(self._max_bytes) is not int
                    or type(self._max_records) is not int or self._max_bytes <= 0 or self._max_records <= 0):
                raise OperationLogError()
            self._append(operation_id, entry.event.value, timestamp)
            return OperationLogReceipt(operation_id, True, None)
        except Exception:
            return OperationLogReceipt(operation_id, False, OperationLogError.code)

    def append_event(self, operation_id: UUID, event: OperationLogEvent, timestamp: str) -> OperationLogReceipt:
        return self.append(OperationLogEntry(operation_id, event, timestamp))

    def _capabilities(self) -> None:
        required = ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC")
        if (os.name != "posix" or fcntl is None or any(not hasattr(os, item) for item in required)
                or not hasattr(os, "supports_dir_fd") or os.open not in os.supports_dir_fd
                or not hasattr(os, "replace")):
            raise OperationLogError()

    @staticmethod
    def _directory_flags() -> int:
        return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC

    def _open_root(self) -> int:
        raw = self._local_app_data
        if not os.path.isabs(raw) or os.path.normpath(raw) != raw:
            raise OperationLogError()
        # macOS exposes its writable /var hierarchy via the system /private
        # alias.  Resolve that host-owned prefix once, then perform the actual
        # application-root walk descriptor-relatively.  The injected leaf
        # itself must still be a real directory, never a caller-supplied link.
        try:
            leaf = os.lstat(raw)
            resolved = os.path.realpath(raw)
        except OSError as error:
            raise OperationLogError() from error
        if stat.S_ISLNK(leaf.st_mode):
            raise OperationLogError()
        path = Path(resolved)
        descriptor = os.open(path.anchor, self._directory_flags())
        try:
            for component in path.parts[1:]:
                child = os.open(component, self._directory_flags(), dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            self._verify_directory(descriptor)
            return descriptor
        except Exception:
            os.close(descriptor)
            raise

    @staticmethod
    def _verify_directory(descriptor: int) -> None:
        observed = os.fstat(descriptor)
        if not stat.S_ISDIR(observed.st_mode):
            raise OperationLogError()

    def _private_child(self, parent: int, name: str) -> int:
        created = False
        try:
            child = os.open(name, self._directory_flags(), dir_fd=parent)
        except FileNotFoundError:
            try:
                try:
                    os.mkdir(name, 0o700, dir_fd=parent)
                    created = True
                    os.fsync(parent)  # Includes the injected root when PropExtract is first created.
                except FileExistsError:
                    # A concurrent writer may have created the same private
                    # component; reopen and verify it instead of bypassing it.
                    pass
                child = os.open(name, self._directory_flags(), dir_fd=parent)
            except Exception as error:
                raise OperationLogError() from error
        except OSError as error:
            raise OperationLogError() from error
        try:
            observed = os.fstat(child)
            if (not stat.S_ISDIR(observed.st_mode) or stat.S_IMODE(observed.st_mode) != 0o700
                    or observed.st_uid != os.geteuid()):
                raise OperationLogError()
            if created:
                os.fsync(child)
            return child
        except Exception:
            os.close(child)
            raise

    @staticmethod
    def _private_regular(descriptor: int, name: str) -> os.stat_result:
        observed = os.fstat(descriptor)
        if (not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1
                or stat.S_IMODE(observed.st_mode) != 0o600 or observed.st_uid != os.geteuid()):
            raise OperationLogError()
        return observed

    def _open_lock(self, directory: int, name: str) -> int:
        flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC
        created = False
        try:
            descriptor = os.open(name, flags | os.O_EXCL, 0o600, dir_fd=directory)
            created = True
        except FileExistsError:
            descriptor = os.open(name, flags, dir_fd=directory)
        except OSError as error:
            raise OperationLogError() from error
        try:
            self._private_regular(descriptor, name)
            if created:
                os.fsync(descriptor)
                os.fsync(directory)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            return descriptor
        except Exception:
            os.close(descriptor)
            raise

    def _read_bound(self, directory: int, name: str, operation_id: str) -> tuple[list[dict[str, object]], list[bytes], os.stat_result] | None:
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
        try:
            descriptor = os.open(name, flags, dir_fd=directory)
        except FileNotFoundError:
            return None
        except OSError as error:
            raise OperationLogError() from error
        try:
            before = self._private_regular(descriptor, name)
            parts: list[bytes] = []
            while True:
                chunk = os.read(descriptor, 64 * 1024)
                if not chunk:
                    break
                parts.append(chunk)
            after = self._private_regular(descriptor, name)
            visible = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if not _same_file(before, after) or not _same_file(before, visible):
                raise OperationLogError()
            records, lines = _parse_jsonl(b"".join(parts), operation_id)
            return records, lines, before
        except Exception:
            raise
        finally:
            os.close(descriptor)

    def _operation_artifacts(self, directory: int, operation_id: str, allowed: set[str]) -> int:
        try:
            names = os.listdir(directory)
        except OSError as error:
            raise OperationLogError() from error
        used = 0
        auxiliary = 0
        prefix = operation_id + "."
        for name in names:
            if not name.startswith(prefix):
                continue
            if name not in allowed:
                raise OperationLogError()
            try:
                observed = os.stat(name, dir_fd=directory, follow_symlinks=False)
            except OSError as error:
                raise OperationLogError() from error
            if not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1:
                raise OperationLogError()
            used += observed.st_size
            if name.endswith(".lock") or name.endswith(".tmp"):
                auxiliary += 1
        if auxiliary > MAX_AUXILIARY_FILES or used > self._max_bytes:
            raise OperationLogError()
        return used

    def _recover_temp(self, directory: int, canonical: str, temporary: str, operation_id: str) -> None:
        stale = self._read_bound(directory, temporary, operation_id)
        if stale is None:
            return
        current = self._read_bound(directory, canonical, operation_id)
        try:
            if current is None:
                os.replace(temporary, canonical, src_dir_fd=directory, dst_dir_fd=directory)
                visible = os.stat(canonical, dir_fd=directory, follow_symlinks=False)
                if not _same_inode(stale[2], visible):
                    raise OperationLogError()
            else:
                os.unlink(temporary, dir_fd=directory)
            os.fsync(directory)
        except (OSError, OperationLogError) as error:
            raise OperationLogError() from error

    def _make_history(self, records: list[dict[str, object]], lines: list[bytes], event: str,
                      timestamp: str, operation_id: str, byte_budget: int) -> bytes:
        if len(records) != len(lines):
            raise OperationLogError()
        if type(byte_budget) is not int or byte_budget <= 0:
            raise OperationLogError()
        previous = records[-1]["sequence"] if records else -1
        normal = {"event": event, "operation_id": operation_id, "sequence": previous + 1,
                  "timestamp": timestamp, "version": _VERSION}
        normal_line = _encoded(normal)
        records = [*records, normal]
        lines = [*lines, normal_line]
        marker = records[0] if records and records[0]["event"] == "truncated" else None
        prior_bytes = marker["dropped_bytes"] if marker is not None else 0
        prior_records = marker["dropped_records"] if marker is not None else 0
        start = 1 if marker is not None else 0
        dropped_bytes = prior_bytes
        dropped_records = prior_records
        while len(records) > self._max_records or sum(len(line) for line in lines) > byte_budget:
            if start >= len(records):
                raise OperationLogError()
            dropped_bytes += len(lines[start])
            dropped_records += 1
            del records[start]
            del lines[start]
        if dropped_records:
            marker = {
                "dropped_bytes": dropped_bytes,
                "dropped_records": dropped_records,
                "event": "truncated",
                "operation_id": operation_id,
                "sequence": dropped_records - 1,
                "timestamp": timestamp,
                "version": _VERSION,
            }
            marker_line = _encoded(marker)
            if records and records[0].get("event") == "truncated":
                records[0], lines[0] = marker, marker_line
            else:
                records.insert(0, marker)
                lines.insert(0, marker_line)
            while len(records) > self._max_records or sum(len(line) for line in lines) > byte_budget:
                if len(records) <= 1:
                    raise OperationLogError()
                dropped_bytes += len(lines[1])
                dropped_records += 1
                del records[1]
                del lines[1]
                marker["dropped_bytes"] = dropped_bytes
                marker["dropped_records"] = dropped_records
                marker["sequence"] = dropped_records - 1
                lines[0] = _encoded(marker)
        payload = b"".join(lines)
        _parse_jsonl(payload, operation_id)
        if not payload or len(payload) > byte_budget:
            raise OperationLogError()
        return payload

    def _write_atomic(self, directory: int, canonical: str, temporary: str, operation_id: str,
                      expected: os.stat_result | None, payload: bytes) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
        descriptor: int | None = None
        try:
            descriptor = os.open(temporary, flags, 0o600, dir_fd=directory)
            self._private_regular(descriptor, temporary)
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OperationLogError()
                view = view[written:]
            os.fsync(descriptor)
            temp_stat = self._private_regular(descriptor, temporary)
            visible_temp = os.stat(temporary, dir_fd=directory, follow_symlinks=False)
            if not _same_file(temp_stat, visible_temp):
                raise OperationLogError()
            if expected is None:
                try:
                    os.stat(canonical, dir_fd=directory, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise OperationLogError()
            else:
                visible = os.stat(canonical, dir_fd=directory, follow_symlinks=False)
                if not _same_file(expected, visible):
                    raise OperationLogError()
            os.replace(temporary, canonical, src_dir_fd=directory, dst_dir_fd=directory)
            final = os.stat(canonical, dir_fd=directory, follow_symlinks=False)
            if not _same_inode(temp_stat, final):
                raise OperationLogError()
            os.fsync(directory)
        except Exception as error:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
                descriptor = None
            try:
                os.unlink(temporary, dir_fd=directory)
                os.fsync(directory)
            except OSError:
                pass  # Fixed name remains the sole bounded recovery artifact.
            if isinstance(error, OperationLogError):
                raise
            raise OperationLogError() from error
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def _append(self, operation_id: str, event: str, timestamp: str) -> None:
        self._capabilities()
        root = self._open_root()
        descriptors = [root]
        try:
            for component in ("PropExtract", "logs", "operations"):
                descriptors.append(self._private_child(descriptors[-1], component))
            directory = descriptors[-1]
            canonical = operation_id + ".jsonl"
            temporary = operation_id + ".jsonl.tmp"
            lock_name = operation_id + ".jsonl.lock"
            lock = self._open_lock(directory, lock_name)
            try:
                allowed = {canonical, temporary, lock_name}
                self._operation_artifacts(directory, operation_id, allowed)
                self._recover_temp(directory, canonical, temporary, operation_id)
                used_before_write = self._operation_artifacts(directory, operation_id, allowed)
                bound = self._read_bound(directory, canonical, operation_id)
                records, lines, expected = bound if bound is not None else ([], [], None)
                # Atomic replacement temporarily contains old canonical plus the
                # one fixed temp, so reserve both against the operation cap.
                payload = self._make_history(
                    records, lines, event, timestamp, operation_id, self._max_bytes - used_before_write,
                )
                if used_before_write + len(payload) > self._max_bytes:
                    raise OperationLogError()
                self._write_atomic(directory, canonical, temporary, operation_id, expected, payload)
                self._operation_artifacts(directory, operation_id, allowed)
            finally:
                try:
                    fcntl.flock(lock, fcntl.LOCK_UN)
                finally:
                    os.close(lock)
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)


# A descriptive alias for call sites that prefer a service name.
OperationLogService = OperationLogWriter


def append_operation_event(local_app_data: str, operation_id: UUID, event: OperationLogEvent,
                           timestamp: str) -> OperationLogReceipt:
    return OperationLogWriter(local_app_data).append_event(operation_id, event, timestamp)
