"""Fail-closed Win32 process identity and cleanup authority."""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Protocol


class ProcessAuthorityError(RuntimeError):
    def __init__(self, code: str): self.code = code; super().__init__(code)


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    image: str
    started_at: str


class Win32Facade(Protocol):
    def hwnd_pid(self, hwnd: int) -> int: ...
    def identity(self, pid: int) -> ProcessIdentity: ...
    def terminate(self, pid: int) -> None: ...
    def wait(self, pid: int, timeout_seconds: float) -> bool: ...


def _image(value: str) -> str: return value.rsplit("\\", 1)[-1].upper()


def verify_adapter(facade: Win32Facade | None, *, popen_pid: int, expected_image: str, expected_started_at: str) -> ProcessIdentity:
    if facade is None or os.name != "nt": raise ProcessAuthorityError("windows_process_authority_unsupported")
    try: identity = facade.identity(popen_pid)
    except PermissionError as error: raise ProcessAuthorityError("process_access_denied") from error
    except ProcessLookupError as error: raise ProcessAuthorityError("process_vanished") from error
    if identity.pid != popen_pid or _image(identity.image) != _image(expected_image) or identity.started_at != expected_started_at:
        raise ProcessAuthorityError("adapter_identity_mismatch")
    return identity


def verify_excel_lease(facade: Win32Facade | None, *, pid: int, hwnd: int, started_at: str) -> ProcessIdentity:
    if facade is None or os.name != "nt": raise ProcessAuthorityError("windows_process_authority_unsupported")
    try:
        if facade.hwnd_pid(hwnd) != pid: raise ProcessAuthorityError("excel_hwnd_pid_mismatch")
        identity = facade.identity(pid)
    except PermissionError as error: raise ProcessAuthorityError("process_access_denied") from error
    except ProcessLookupError as error: raise ProcessAuthorityError("process_vanished") from error
    if _image(identity.image) != "EXCEL.EXE" or identity.started_at != started_at:
        raise ProcessAuthorityError("excel_identity_mismatch")
    return identity


def terminate_leased_excel(facade: Win32Facade | None, *, pid: int, hwnd: int, started_at: str, timeout_seconds: float) -> None:
    """Revalidate then terminate exactly the leased process, or do nothing."""
    verify_excel_lease(facade, pid=pid, hwnd=hwnd, started_at=started_at)
    assert facade is not None
    try:
        facade.terminate(pid)
        if not facade.wait(pid, timeout_seconds): raise ProcessAuthorityError("excel_termination_timeout")
    except PermissionError as error: raise ProcessAuthorityError("process_access_denied") from error
    except ProcessLookupError as error: raise ProcessAuthorityError("process_vanished") from error
