"""Exact, fail-closed cleanup for the Excel process named by a verified lease."""
from __future__ import annotations

from typing import Protocol

from rns_import_server.excel_process_authority import ExcelProcessLease, ProcessIdentity, strict_utc


class ExcelProcessCleanupError(RuntimeError):
    """Cleanup evidence is deliberately separate from the primary native error."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ProcessMissingError(LookupError):
    """The OS positively reported that the process no longer exists."""


class ExcelCleanupInspector(Protocol):
    def process_identity(self, pid: int) -> ProcessIdentity: ...
    def hwnd_process_id(self, hwnd: int) -> int: ...
    def terminate_process(self, pid: int) -> None: ...
    def wait_for_process_exit(self, pid: int, timeout: float) -> bool: ...


def _matching_live_lease(lease: ExcelProcessLease, inspector: ExcelCleanupInspector) -> bool:
    """Return false only for a positively absent PID; every other uncertainty fails."""
    try:
        identity = inspector.process_identity(lease.excel_pid)
    except ProcessMissingError:
        return False
    except Exception as error:
        raise ExcelProcessCleanupError("excel_cleanup_evidence_unavailable") from error
    try:
        hwnd_pid = inspector.hwnd_process_id(lease.excel_hwnd)
        if type(identity) is not ProcessIdentity or type(hwnd_pid) is not int:
            raise TypeError("process evidence")
        observed = (identity.pid, identity.image, strict_utc(identity.started_at), hwnd_pid)
    except Exception as error:
        raise ExcelProcessCleanupError("excel_cleanup_evidence_unavailable") from error
    expected = (lease.excel_pid, lease.excel_image, lease.excel_process_started_at, lease.excel_pid)
    if observed != expected:
        raise ExcelProcessCleanupError("excel_cleanup_identity_mismatch")
    return True


def cleanup_excel_process(
    lease: ExcelProcessLease,
    *,
    prelaunch_excel_pids: frozenset[int],
    inspector: ExcelCleanupInspector,
    grace: float = 8.0,
) -> None:
    """Prove disappearance, terminating only the exact new leased Excel process."""
    if type(lease) is not ExcelProcessLease or type(prelaunch_excel_pids) is not frozenset:
        raise ExcelProcessCleanupError("excel_cleanup_evidence_invalid")
    if any(type(pid) is not int or pid <= 0 for pid in prelaunch_excel_pids):
        raise ExcelProcessCleanupError("excel_cleanup_evidence_invalid")
    if lease.excel_pid in prelaunch_excel_pids:
        raise ExcelProcessCleanupError("excel_cleanup_preexisting")
    if not _matching_live_lease(lease, inspector):
        return
    try:
        inspector.terminate_process(lease.excel_pid)
    except Exception as error:
        raise ExcelProcessCleanupError("excel_cleanup_terminate_failed") from error
    try:
        gone = inspector.wait_for_process_exit(lease.excel_pid, grace)
    except Exception as error:
        raise ExcelProcessCleanupError("excel_cleanup_wait_failed") from error
    if gone is not True:
        raise ExcelProcessCleanupError("excel_cleanup_process_still_alive")
    if _matching_live_lease(lease, inspector):
        raise ExcelProcessCleanupError("excel_cleanup_process_still_alive")
