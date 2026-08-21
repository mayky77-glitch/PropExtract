"""Fail-closed authority checks for the Excel process lease.

This module deliberately does not launch, signal, or terminate a process.  It
turns observations supplied by the native adapter boundary into an immutable
record which can safely be made durable before a workbook is opened.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Protocol


class ExcelProcessAuthorityError(RuntimeError):
    """Stable, typed rejection of an untrusted process observation."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def strict_utc(value: object) -> str:
    """Normalize whole-second UTC only; local/nonzero-offset time is forbidden."""
    if not isinstance(value, str) or re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|\+00:00)", value
    ) is None:
        raise ExcelProcessAuthorityError("excel_lease_timestamp_invalid")
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
    except (TypeError, ValueError, OverflowError) as error:
        raise ExcelProcessAuthorityError("excel_lease_timestamp_invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed) or parsed.microsecond:
        raise ExcelProcessAuthorityError("excel_lease_timestamp_invalid")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    image: str
    started_at: str


class ExcelProcessInspector(Protocol):
    def prelaunch_excel_pids(self) -> frozenset[int]: ...
    def process_identity(self, pid: int) -> ProcessIdentity: ...
    def hwnd_process_id(self, hwnd: int) -> int: ...


@dataclass(frozen=True)
class ExcelProcessLease:
    operation_id: str
    owner_id: str
    pair_nonce: str
    adapter_type: str
    adapter_image: str
    adapter_pid: int
    adapter_started_at: str
    excel_image: str
    excel_pid: int
    excel_hwnd: int
    excel_process_started_at: str
    excel_build: str

    def __post_init__(self) -> None:
        for value in (self.operation_id, self.owner_id, self.pair_nonce, self.adapter_image, self.excel_build):
            if not isinstance(value, str) or not value:
                raise ExcelProcessAuthorityError("excel_lease_identity_invalid")
        if self.adapter_type != "com":
            raise ExcelProcessAuthorityError("excel_lease_adapter_invalid")
        if self.excel_image != "EXCEL.EXE":
            raise ExcelProcessAuthorityError("excel_lease_excel_image_invalid")
        for value in (self.adapter_pid, self.excel_pid, self.excel_hwnd):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ExcelProcessAuthorityError("excel_lease_identity_invalid")
        object.__setattr__(self, "adapter_started_at", strict_utc(self.adapter_started_at))
        object.__setattr__(self, "excel_process_started_at", strict_utc(self.excel_process_started_at))

    def journal_fields(self) -> dict[str, object]:
        """The seven durable fields; operation/owner/pair remain row identity."""
        return {
            "excel_adapter": self.adapter_type,
            "excel_adapter_pid": self.adapter_pid,
            "excel_adapter_started_at": self.adapter_started_at,
            "excel_pid": self.excel_pid,
            "excel_hwnd": self.excel_hwnd,
            "excel_process_started_at": self.excel_process_started_at,
            "excel_build": self.excel_build,
        }


def verify_excel_process_lease(
    lease: ExcelProcessLease,
    *, launched_adapter_pid: int,
    inspector: ExcelProcessInspector,
) -> ExcelProcessLease:
    """Verify one lease against fresh, injected OS observations.

    Every inspector failure is an authority failure.  In particular, failure
    to get a snapshot is not interpreted as an empty prelaunch set.
    """
    if not isinstance(launched_adapter_pid, int) or isinstance(launched_adapter_pid, bool) or launched_adapter_pid <= 0:
        raise ExcelProcessAuthorityError("excel_lease_adapter_pid_invalid")
    if lease.adapter_pid != launched_adapter_pid:
        raise ExcelProcessAuthorityError("excel_lease_adapter_pid_mismatch")
    try:
        before = inspector.prelaunch_excel_pids()
        if not isinstance(before, frozenset) or any(not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0 for pid in before):
            raise TypeError("snapshot")
    except ExcelProcessAuthorityError:
        raise
    except Exception as error:
        raise ExcelProcessAuthorityError("excel_lease_snapshot_unavailable") from error
    try:
        adapter = inspector.process_identity(lease.adapter_pid)
        excel = inspector.process_identity(lease.excel_pid)
        hwnd_pid = inspector.hwnd_process_id(lease.excel_hwnd)
        if (not isinstance(adapter, ProcessIdentity) or not isinstance(excel, ProcessIdentity)
                or not isinstance(hwnd_pid, int) or isinstance(hwnd_pid, bool) or hwnd_pid <= 0):
            raise TypeError("probe")
        for identity in (adapter, excel):
            if (not isinstance(identity.pid, int) or isinstance(identity.pid, bool) or identity.pid <= 0
                    or not isinstance(identity.image, str) or not isinstance(identity.started_at, str)):
                raise TypeError("identity")
        adapter_started = strict_utc(adapter.started_at)
        excel_started = strict_utc(excel.started_at)
    except ExcelProcessAuthorityError:
        raise
    except Exception as error:
        raise ExcelProcessAuthorityError("excel_lease_probe_unavailable") from error
    if (adapter.pid, adapter.image, adapter_started) != (lease.adapter_pid, lease.adapter_image, lease.adapter_started_at):
        raise ExcelProcessAuthorityError("excel_lease_adapter_identity_mismatch")
    if (excel.pid, excel.image, excel_started) != (lease.excel_pid, "EXCEL.EXE", lease.excel_process_started_at):
        raise ExcelProcessAuthorityError("excel_lease_excel_identity_mismatch")
    if hwnd_pid != lease.excel_pid:
        raise ExcelProcessAuthorityError("excel_lease_hwnd_pid_mismatch")
    if lease.excel_pid in before:
        raise ExcelProcessAuthorityError("excel_lease_excel_preexisting")
    adapter_start = datetime.fromisoformat(lease.adapter_started_at.replace("Z", "+00:00"))
    excel_start = datetime.fromisoformat(lease.excel_process_started_at.replace("Z", "+00:00"))
    if excel_start < adapter_start:
        raise ExcelProcessAuthorityError("excel_lease_excel_started_before_adapter")
    return lease
