from __future__ import annotations

import pytest

from rns_import_server.excel_process_authority import ExcelProcessLease, ProcessIdentity
from rns_import_server.excel_process_cleanup import ExcelProcessCleanupError, ProcessMissingError, cleanup_excel_process


def _lease(**changes: object) -> ExcelProcessLease:
    values: dict[str, object] = {
        "operation_id": "op", "owner_id": "owner", "pair_nonce": "pair", "adapter_type": "com",
        "adapter_image": "powershell.exe", "adapter_pid": 11, "adapter_started_at": "2026-08-21T00:00:00Z",
        "excel_image": "EXCEL.EXE", "excel_pid": 22, "excel_hwnd": 33,
        "excel_process_started_at": "2026-08-21T00:00:01Z", "excel_build": "16.0",
    }
    values.update(changes)
    return ExcelProcessLease(**values)  # type: ignore[arg-type]


class Inspector:
    def __init__(self, *, identity: object | None = None, hwnd_pid: int = 22, wait: bool = True):
        self.identity = identity if identity is not None else ProcessIdentity(22, "EXCEL.EXE", "2026-08-21T00:00:01Z")
        self.hwnd_pid, self.wait, self.kills = hwnd_pid, wait, []

    def process_identity(self, pid: int) -> ProcessIdentity:
        if isinstance(self.identity, BaseException): raise self.identity
        return self.identity  # type: ignore[return-value]

    def hwnd_process_id(self, hwnd: int) -> int: return self.hwnd_pid
    def terminate_process(self, pid: int) -> None: self.kills.append(pid)
    def wait_for_process_exit(self, pid: int, timeout: float) -> bool:
        if self.wait: self.identity = ProcessMissingError()
        return self.wait


def test_cleanup_returns_only_after_positive_disappearance() -> None:
    inspector = Inspector()
    cleanup_excel_process(_lease(), prelaunch_excel_pids=frozenset(), inspector=inspector, grace=0.01)
    assert inspector.kills == [22]


@pytest.mark.parametrize("lease_changes,inspector", [
    ({}, Inspector(hwnd_pid=99)),
    ({}, Inspector(identity=ProcessIdentity(22, "other.exe", "2026-08-21T00:00:01Z"))),
    ({}, Inspector(identity=ProcessIdentity(22, "EXCEL.EXE", "2026-08-21T00:00:02Z"))),
])
def test_tuple_mismatch_or_pid_reuse_never_kills(lease_changes: dict[str, object], inspector: Inspector) -> None:
    with pytest.raises(ExcelProcessCleanupError, match="excel_cleanup_identity_mismatch"):
        cleanup_excel_process(_lease(**lease_changes), prelaunch_excel_pids=frozenset(), inspector=inspector)
    assert inspector.kills == []


def test_preexisting_or_inaccessible_process_never_kills() -> None:
    preexisting = Inspector()
    with pytest.raises(ExcelProcessCleanupError, match="excel_cleanup_preexisting"):
        cleanup_excel_process(_lease(), prelaunch_excel_pids=frozenset({22}), inspector=preexisting)
    inaccessible = Inspector(identity=RuntimeError("denied"))
    with pytest.raises(ExcelProcessCleanupError, match="excel_cleanup_evidence_unavailable"):
        cleanup_excel_process(_lease(), prelaunch_excel_pids=frozenset(), inspector=inaccessible)
    assert preexisting.kills == inaccessible.kills == []


def test_cleanup_refuses_success_when_process_survives_grace() -> None:
    inspector = Inspector(wait=False)
    with pytest.raises(ExcelProcessCleanupError, match="excel_cleanup_process_still_alive"):
        cleanup_excel_process(_lease(), prelaunch_excel_pids=frozenset(), inspector=inspector, grace=0.01)
    assert inspector.kills == [22]
