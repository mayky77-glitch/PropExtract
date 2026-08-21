from __future__ import annotations

import pytest

from rns_import_server.excel_process_authority import (
    ExcelProcessAuthorityError,
    ExcelProcessLease,
    ProcessIdentity,
    verify_excel_process_lease,
)


class Inspector:
    def __init__(self, *, snapshot: object = frozenset(), adapter: object | None = None, excel: object | None = None, hwnd_pid: object = 22):
        self.snapshot, self.adapter, self.excel, self.hwnd_pid = snapshot, adapter, excel, hwnd_pid

    def prelaunch_excel_pids(self) -> frozenset[int]:
        if isinstance(self.snapshot, BaseException):
            raise self.snapshot
        return self.snapshot  # type: ignore[return-value]

    def process_identity(self, pid: int) -> ProcessIdentity:
        result = self.adapter if pid == 11 else self.excel
        if isinstance(result, BaseException):
            raise result
        return result  # type: ignore[return-value]

    def hwnd_process_id(self, hwnd: int) -> int:
        if isinstance(self.hwnd_pid, BaseException):
            raise self.hwnd_pid
        return self.hwnd_pid  # type: ignore[return-value]


def _lease(**changes: object) -> ExcelProcessLease:
    values: dict[str, object] = {
        "operation_id": "op", "owner_id": "owner", "pair_nonce": "pair", "adapter_type": "com",
        "adapter_image": "powershell.exe", "adapter_pid": 11, "adapter_started_at": "2026-08-21T00:00:00Z",
        "excel_image": "EXCEL.EXE", "excel_pid": 22, "excel_hwnd": 33,
        "excel_process_started_at": "2026-08-21T00:00:01Z", "excel_build": "16.0.1",
    }
    values.update(changes)
    return ExcelProcessLease(**values)  # type: ignore[arg-type]


def test_verifier_returns_exact_immutable_full_lease() -> None:
    lease = _lease()
    inspector = Inspector(
        adapter=ProcessIdentity(11, "powershell.exe", "2026-08-21T00:00:00Z"),
        excel=ProcessIdentity(22, "EXCEL.EXE", "2026-08-21T00:00:01Z"),
    )
    assert verify_excel_process_lease(lease, launched_adapter_pid=11, inspector=inspector) is lease
    assert lease.journal_fields() == {
        "excel_adapter": "com", "excel_adapter_pid": 11, "excel_adapter_started_at": "2026-08-21T00:00:00Z",
        "excel_pid": 22, "excel_hwnd": 33, "excel_process_started_at": "2026-08-21T00:00:01Z", "excel_build": "16.0.1",
    }


def test_lease_constructor_normalizes_zero_offset_and_rejects_non_utc_timestamp() -> None:
    assert _lease(adapter_started_at="2026-08-21T00:00:00+00:00").adapter_started_at == "2026-08-21T00:00:00Z"
    with pytest.raises(ExcelProcessAuthorityError) as error:
        _lease(adapter_started_at="2026-08-21T00:00:00+01:00")
    assert error.value.code == "excel_lease_timestamp_invalid"


@pytest.mark.parametrize("value", [
    "2026-08-21 00:00:00+00:00", "20260821T000000Z", "2026-08-21T00:00+00:00",
    "2026-08-21T00:00:00+0000", "2026-08-21T00:00:00+00", "2026-08-21T00:00:00-00:00",
    "2026-W34-5T00:00:00+00:00", "2026-08-21T00:00:00.1Z",
])
def test_lease_constructor_rejects_noncanonical_utc_lexicals(value: str) -> None:
    with pytest.raises(ExcelProcessAuthorityError) as error:
        _lease(adapter_started_at=value)
    assert error.value.code == "excel_lease_timestamp_invalid"


@pytest.mark.parametrize("lease_change,snapshot,adapter,excel,hwnd_pid,launched,code", [
    ({}, RuntimeError(), None, None, 22, 11, "excel_lease_snapshot_unavailable"),
    ({}, frozenset({22}), None, None, 22, 11, "excel_lease_excel_preexisting"),
    ({}, frozenset(), ProcessIdentity(11, "wrong.exe", "2026-08-21T00:00:00Z"), ProcessIdentity(22, "EXCEL.EXE", "2026-08-21T00:00:01Z"), 22, 11, "excel_lease_adapter_identity_mismatch"),
    ({}, frozenset(), ProcessIdentity(11, "powershell.exe", "2026-08-21T00:00:00Z"), ProcessIdentity(22, "EXCEL.EXE", "2026-08-21T00:00:01Z"), 99, 11, "excel_lease_hwnd_pid_mismatch"),
    ({}, frozenset(), None, None, 22, 12, "excel_lease_adapter_pid_mismatch"),
])
def test_verifier_fails_closed_for_identity_timestamp_and_snapshot(
    lease_change: dict[str, object], snapshot: object, adapter: object | None, excel: object | None, hwnd_pid: object,
    launched: int, code: str,
) -> None:
    lease = _lease(**lease_change)
    adapter = adapter or ProcessIdentity(11, "powershell.exe", "2026-08-21T00:00:00Z")
    excel = excel or ProcessIdentity(22, "EXCEL.EXE", "2026-08-21T00:00:01Z")
    with pytest.raises(ExcelProcessAuthorityError) as error:
        verify_excel_process_lease(lease, launched_adapter_pid=launched, inspector=Inspector(snapshot=snapshot, adapter=adapter, excel=excel, hwnd_pid=hwnd_pid))
    assert error.value.code == code
