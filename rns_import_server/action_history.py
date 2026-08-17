"""Strict, bounded carry-over of anonymized audit actions between jobs."""
from __future__ import annotations

import errno
import json
import os
import re
import stat
from pathlib import Path
from typing import Callable

try:
    from rns_import_server.audit import sha256
    from rns_import_server.job_report import report_path
    from rns_import_server.workbook import EDITABLE_FIELDS
except ModuleNotFoundError:
    from audit import sha256
    from job_report import report_path
    from workbook import EDITABLE_FIELDS


INVALID_WARNING = (
    "История действий из предыдущего отчёта не перенесена: "
    "отчёт повреждён или имеет неподдерживаемый формат."
)
STALE_WARNING = (
    "История действий из предыдущего отчёта не перенесена: "
    "Excel изменён после создания отчёта."
)
READ_WARNING = (
    "История действий из предыдущего отчёта не перенесена: "
    "не удалось безопасно прочитать отчёт."
)
MAX_REPORT_SIZE = 16 * 1024 * 1024


def open_windows_descriptor(
    path: Path,
    *,
    kernel32: object | None = None,
    open_osfhandle: Callable[[int, int], int] | None = None,
) -> int:
    """Open one Windows file handle without traversing a reparse point."""
    import ctypes
    from ctypes import wintypes

    class ByHandleFileInformation(ctypes.Structure):
        _fields_ = [
            ("dwFileAttributes", wintypes.DWORD),
            ("ftCreationTime", wintypes.FILETIME),
            ("ftLastAccessTime", wintypes.FILETIME),
            ("ftLastWriteTime", wintypes.FILETIME),
            ("dwVolumeSerialNumber", wintypes.DWORD),
            ("nFileSizeHigh", wintypes.DWORD),
            ("nFileSizeLow", wintypes.DWORD),
            ("nNumberOfLinks", wintypes.DWORD),
            ("nFileIndexHigh", wintypes.DWORD),
            ("nFileIndexLow", wintypes.DWORD),
        ]

    if kernel32 is None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    if open_osfhandle is None:
        import msvcrt
        open_osfhandle = msvcrt.open_osfhandle

    create_file = kernel32.CreateFileW  # type: ignore[attr-defined]
    create_file.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    get_information = kernel32.GetFileInformationByHandle  # type: ignore[attr-defined]
    get_information.argtypes = [wintypes.HANDLE, ctypes.POINTER(ByHandleFileInformation)]
    get_information.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle  # type: ignore[attr-defined]
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    handle = create_file(
        str(path),
        0x80000000,  # GENERIC_READ
        0x00000001 | 0x00000002 | 0x00000004,  # FILE_SHARE_READ|WRITE|DELETE
        None,
        3,  # OPEN_EXISTING
        0x00200000,  # FILE_FLAG_OPEN_REPARSE_POINT
        None,
    )
    invalid_handle = wintypes.HANDLE(-1).value
    handle_value = getattr(handle, "value", handle)
    if handle_value in {None, invalid_handle}:
        code = getattr(ctypes, "get_last_error", lambda: 0)()
        raise OSError(code, "Не удалось безопасно открыть отчёт")
    information = ByHandleFileInformation()
    try:
        if not get_information(handle, ctypes.byref(information)):
            code = getattr(ctypes, "get_last_error", lambda: 0)()
            raise OSError(code, "Не удалось проверить файл отчёта")
        if information.dwFileAttributes & 0x00000400:  # FILE_ATTRIBUTE_REPARSE_POINT
            raise OSError(errno.ELOOP, "Отчёт не должен быть reparse point")
        descriptor = open_osfhandle(int(handle_value), os.O_RDONLY | getattr(os, "O_BINARY", 0))
    except Exception:
        close_handle(handle)
        raise
    return descriptor


def open_descriptor(path: Path) -> int:
    if os.name == "nt":
        return open_windows_descriptor(path)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return os.open(path, flags)


def load(target: Path) -> tuple[list[dict[str, object]], str | None]:
    """Load only valid audit actions; never import report state or authority."""
    path = report_path(target)
    try:
        try:
            before = path.lstat()
        except FileNotFoundError:
            return [], None
        if not stat.S_ISREG(before.st_mode):
            return [], READ_WARNING
        descriptor = open_descriptor(path)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
                return [], READ_WARNING
            if opened.st_size > MAX_REPORT_SIZE:
                return [], INVALID_WARNING
            payload = bytearray()
            limit = MAX_REPORT_SIZE + 1
            while len(payload) < limit:
                chunk = os.read(descriptor, min(64 * 1024, limit - len(payload)))
                if not chunk:
                    break
                payload.extend(chunk)
        finally:
            os.close(descriptor)
        if len(payload) > MAX_REPORT_SIZE:
            return [], INVALID_WARNING
        report = json.loads(bytes(payload).decode("utf-8", errors="strict"))
        if not isinstance(report, dict):
            return [], INVALID_WARNING
        final = report.get("final_state")
        if not isinstance(final, dict):
            return [], None  # Older reports contain no action history.
        if final.get("schema") != "propextract.final-action.v1":
            return [], INVALID_WARNING
        expected_hash = final.get("workbook_sha256")
        if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            return [], INVALID_WARNING
        if sha256(target) != expected_hash:
            return [], STALE_WARNING
        raw = final.get("actions")
        if not isinstance(raw, list) or len(raw) > 10_000:
            return [], INVALID_WARNING
        allowed_fields = frozenset(EDITABLE_FIELDS.values())
        actions: list[dict[str, object]] = []
        for item in raw:
            if not isinstance(item, dict):
                return [], INVALID_WARNING
            kind, row, field, status = item.get("type"), item.get("row"), item.get("field"), item.get("status")
            expected_status = {"proposal_approved": "approved", "manual_edit": "edited"}.get(kind)
            if (
                expected_status is None
                or not isinstance(row, int)
                or isinstance(row, bool)
                or row < 4
                or field not in allowed_fields
                or status != expected_status
            ):
                return [], INVALID_WARNING
            actions.append({"type": kind, "row": row, "field": field, "status": status})
        return actions, None
    except (OSError, UnicodeError):
        return [], READ_WARNING
    except (json.JSONDecodeError, TypeError, ValueError):
        return [], INVALID_WARNING
