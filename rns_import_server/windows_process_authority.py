"""Fail-closed Win32 process identity and cleanup authority.

The public functions take an injectable facade so Linux CI can exercise the
same hostile-process contract. ``CtypesWin32Facade`` is the concrete Windows
implementation; it is deliberately not constructed on non-Windows hosts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import ctypes
from ctypes import wintypes
import os
from typing import Protocol


class ProcessAuthorityError(RuntimeError):
    def __init__(self, code: str, *, winerror: int | None = None):
        self.code, self.winerror = code, winerror
        detail = f" [WinError {winerror}]" if winerror is not None else ""
        super().__init__(f"{code}{detail}")


class Win32ApiError(ProcessAuthorityError):
    def __init__(self, api: str, winerror: int):
        self.api = api
        super().__init__(f"win32_{api}_failed", winerror=winerror)


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    image: str
    started_at: str


class ProcessAuthorityFacade(Protocol):
    def hwnd_pid(self, hwnd: int) -> int: ...
    def open_process(self, pid: int, *, terminate: bool) -> object: ...
    def identity_from_handle(self, handle: object, pid: int) -> ProcessIdentity: ...
    def terminate_handle(self, handle: object) -> None: ...
    def wait_handle(self, handle: object, timeout_seconds: float) -> bool: ...
    def close_handle(self, handle: object) -> None: ...


class _FileTime(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class CtypesWin32Facade:
    """Explicit ctypes binding for the required process-authority API."""

    PROCESS_TERMINATE = 0x0001
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    SYNCHRONIZE = 0x00100000
    WAIT_OBJECT_0 = 0
    WAIT_TIMEOUT = 258

    def __init__(self) -> None:
        if os.name != "nt" or not hasattr(ctypes, "WinDLL"):
            raise ProcessAuthorityError("windows_process_authority_unsupported")
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._configure()

    def _configure(self) -> None:
        self.kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        self.kernel32.OpenProcess.restype = wintypes.HANDLE
        self.kernel32.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
        self.kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        self.kernel32.GetProcessTimes.argtypes = (wintypes.HANDLE, ctypes.POINTER(_FileTime), ctypes.POINTER(_FileTime), ctypes.POINTER(_FileTime), ctypes.POINTER(_FileTime))
        self.kernel32.GetProcessTimes.restype = wintypes.BOOL
        self.kernel32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
        self.kernel32.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.kernel32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
        self.kernel32.TerminateProcess.restype = wintypes.BOOL
        self.kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        self.kernel32.WaitForSingleObject.restype = wintypes.DWORD
        self.kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        self.kernel32.CloseHandle.restype = wintypes.BOOL

    @staticmethod
    def _error(api: str) -> Win32ApiError:
        return Win32ApiError(api, ctypes.get_last_error())

    def hwnd_pid(self, hwnd: int) -> int:
        pid = wintypes.DWORD()
        thread_id = self.kernel32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
        if not thread_id or not pid.value:
            raise self._error("get_window_thread_process_id")
        return int(pid.value)

    def open_process(self, pid: int, *, terminate: bool) -> object:
        access = self.PROCESS_QUERY_LIMITED_INFORMATION
        if terminate:
            access |= self.PROCESS_TERMINATE | self.SYNCHRONIZE
        handle = self.kernel32.OpenProcess(access, False, pid)
        if not handle:
            raise self._error("open_process")
        return handle

    def identity_from_handle(self, handle: object, pid: int) -> ProcessIdentity:
        size = wintypes.DWORD(32_768)
        image = ctypes.create_unicode_buffer(size.value)
        if not self.kernel32.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)):
            raise self._error("query_full_process_image_name")
        created, exited, kernel, user = _FileTime(), _FileTime(), _FileTime(), _FileTime()
        if not self.kernel32.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)):
            raise self._error("get_process_times")
        ticks = (int(created.dwHighDateTime) << 32) | int(created.dwLowDateTime)
        started = datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=ticks // 10)
        return ProcessIdentity(pid=pid, image=image.value, started_at=started.isoformat(timespec="microseconds").replace("+00:00", "Z"))

    def terminate_handle(self, handle: object) -> None:
        if not self.kernel32.TerminateProcess(handle, 1):
            raise self._error("terminate_process")

    def wait_handle(self, handle: object, timeout_seconds: float) -> bool:
        if timeout_seconds < 0:
            raise ProcessAuthorityError("excel_termination_timeout")
        timeout_ms = min(int(timeout_seconds * 1000), 0xFFFFFFFE)
        result = int(self.kernel32.WaitForSingleObject(handle, timeout_ms))
        if result == self.WAIT_OBJECT_0:
            return True
        if result == self.WAIT_TIMEOUT:
            return False
        raise self._error("wait_for_single_object")

    def close_handle(self, handle: object) -> None:
        if not self.kernel32.CloseHandle(handle):
            raise self._error("close_handle")


def _image(value: str) -> str:
    return value.replace("/", "\\").rsplit("\\", 1)[-1].upper()


def _require(facade: ProcessAuthorityFacade | None) -> ProcessAuthorityFacade:
    if os.name != "nt":
        raise ProcessAuthorityError("windows_process_authority_unsupported")
    return facade if facade is not None else CtypesWin32Facade()


def _map_os_error(error: BaseException) -> ProcessAuthorityError:
    if isinstance(error, ProcessAuthorityError):
        if error.winerror == 5:
            return ProcessAuthorityError("process_access_denied", winerror=error.winerror)
        if error.winerror in {6, 87, 1168, 128}:
            return ProcessAuthorityError("process_vanished", winerror=error.winerror)
        return error
    if isinstance(error, PermissionError):
        return ProcessAuthorityError("process_access_denied", winerror=getattr(error, "winerror", None))
    if isinstance(error, ProcessLookupError):
        return ProcessAuthorityError("process_vanished", winerror=getattr(error, "winerror", None))
    raise error


def _with_identity(facade: ProcessAuthorityFacade, pid: int, *, terminate: bool) -> ProcessIdentity:
    handle: object | None = None
    try:
        handle = facade.open_process(pid, terminate=terminate)
        return facade.identity_from_handle(handle, pid)
    except (PermissionError, ProcessLookupError, ProcessAuthorityError) as error:
        raise _map_os_error(error) from error
    finally:
        if handle is not None:
            facade.close_handle(handle)


def _assert_adapter(identity: ProcessIdentity, *, popen_pid: int, expected_image: str, expected_started_at: str) -> None:
    if (identity.pid != popen_pid or _image(identity.image) != _image(expected_image)
            or identity.started_at != expected_started_at):
        raise ProcessAuthorityError("adapter_identity_mismatch")


def _assert_excel(identity: ProcessIdentity, *, pid: int, started_at: str) -> None:
    if identity.pid != pid or _image(identity.image) != "EXCEL.EXE" or identity.started_at != started_at:
        raise ProcessAuthorityError("excel_identity_mismatch")


def verify_adapter(facade: ProcessAuthorityFacade | None, *, popen_pid: int, expected_image: str, expected_started_at: str) -> ProcessIdentity:
    """Verify the returned process identity is exactly the launched adapter."""
    if not isinstance(popen_pid, int) or isinstance(popen_pid, bool) or popen_pid <= 0:
        raise ProcessAuthorityError("adapter_identity_mismatch")
    result = _with_identity(_require(facade), popen_pid, terminate=False)
    _assert_adapter(result, popen_pid=popen_pid, expected_image=expected_image, expected_started_at=expected_started_at)
    return result


def verify_excel_lease(facade: ProcessAuthorityFacade | None, *, pid: int, hwnd: int, started_at: str) -> ProcessIdentity:
    """Verify HWND and process creation identity without termination access."""
    resolved = _require(facade)
    try:
        if resolved.hwnd_pid(hwnd) != pid:
            raise ProcessAuthorityError("excel_hwnd_pid_mismatch")
    except (PermissionError, ProcessLookupError, ProcessAuthorityError) as error:
        raise _map_os_error(error) from error
    result = _with_identity(resolved, pid, terminate=False)
    _assert_excel(result, pid=pid, started_at=started_at)
    return result


def terminate_leased_excel(facade: ProcessAuthorityFacade | None, *, pid: int, hwnd: int, started_at: str, timeout_seconds: float) -> None:
    """Terminate only one still-matching leased Excel handle, or do nothing."""
    resolved = _require(facade)
    handle: object | None = None
    primary: BaseException | None = None
    try:
        handle = resolved.open_process(pid, terminate=True)
        # Revalidate immediately before termination using the same handle.
        if resolved.hwnd_pid(hwnd) != pid:
            raise ProcessAuthorityError("excel_hwnd_pid_mismatch")
        identity = resolved.identity_from_handle(handle, pid)
        _assert_excel(identity, pid=pid, started_at=started_at)
        resolved.terminate_handle(handle)
        if not resolved.wait_handle(handle, timeout_seconds):
            raise ProcessAuthorityError("excel_termination_timeout")
    except (PermissionError, ProcessLookupError, ProcessAuthorityError) as error:
        primary = _map_os_error(error)
        raise primary from error
    finally:
        if handle is not None:
            try:
                resolved.close_handle(handle)
            except (PermissionError, ProcessLookupError, ProcessAuthorityError) as error:
                if primary is None:
                    raise _map_os_error(error) from error
