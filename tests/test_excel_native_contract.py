from pathlib import Path
import io
import math

import pytest

import rns_import_server.excel_native as native
from rns_import_server.excel_native import NativeExcelError, NativeInsertRequest, native_excel_available, run_native_insert
from rns_import_server.excel_process_authority import ExcelProcessLease


class Journal:
    def transition(self, *args, **kwargs):
        raise AssertionError("safe negative path must not use journal")


def test_hosted_non_windows_is_a_typed_safe_negative_path(tmp_path: Path) -> None:
    request = NativeInsertRequest("op", "owner", "pair", tmp_path / "control.xlsx", tmp_path / "candidate.xlsx", 6, tmp_path / "lease.json", tmp_path / "ack.json", "Реестр РНС", {}, None, "middle_insert")
    if not native_excel_available():
        with pytest.raises(NativeExcelError, match="excel_required_for_middle_insert"):
            run_native_insert(request, tmp_path / "helper.ps1", Journal())


def test_native_request_carries_pair_and_lease_paths(tmp_path: Path) -> None:
    request = NativeInsertRequest("op", "owner", "pair", tmp_path / "control.xlsx", tmp_path / "candidate.xlsx", 10, tmp_path / "lease.json", tmp_path / "ack.json", "Реестр РНС", {}, None, "blank_fill")
    assert request.payload()["pair_nonce"] == "pair"
    assert request.payload()["insertion_row"] == 10
    assert request.payload()["mutation_mode"] == "blank_fill"


def test_invalid_native_mutation_mode_fails_before_request_file_or_helper_launch(tmp_path: Path) -> None:
    request = NativeInsertRequest("op", "owner", "pair", tmp_path / "control.xlsx", tmp_path / "candidate.xlsx", 10, tmp_path / "ops" / "lease.json", tmp_path / "ops" / "ack.json", "Реестр РНС", {}, None, "wrong")
    with pytest.raises(NativeExcelError) as captured:
        run_native_insert(request, tmp_path / "helper.ps1", Journal())
    assert (captured.value.code, captured.value.stage) == ("native_mutation_mode_invalid", "pre_open")
    assert not (tmp_path / "ops").exists()


@pytest.mark.parametrize("mode", ["MIDDLE_INSERT", "Middle_Insert", None])
def test_powershell_rejects_noncanonical_mode_before_com_and_has_one_middle_insert(mode: str | None) -> None:
    script = (Path(__file__).parents[1] / "scripts" / "windows_excel_insert.ps1").read_text(encoding="utf-8")
    guard = "if ($data.mutation_mode -cnotin @('middle_insert', 'blank_fill'))"
    assert guard in script and mode not in {"middle_insert", "blank_fill"}
    assert script.index(guard) < script.index("New-Object -ComObject Excel.Application")
    assert "if ($data.mutation_mode -ceq 'middle_insert')" in script
    assert script.count(".Insert(-4121, 0)") == 1


def test_helper_lease_precedes_open_and_uses_stdin_not_ack_polling() -> None:
    script = (Path(__file__).parents[1] / "scripts" / "windows_excel_insert.ps1").read_text(encoding="utf-8")
    assert script.index("Write-DurableUtf8NoBom $temporary") < script.index("$control = $excel.Workbooks.Open")
    assert "[Console]::In.ReadLine()" in script
    assert "ack_file" not in script and "Task.Run" not in script and "taskkill /T" not in script
    assert script.index("$excel.Quit()") < script.index("if ($success)")
    assert script.count("Test-NativeCancel") >= 7
    assert script.index("$control = $excel.Workbooks.Open") < script.index("Test-NativeCancel", script.index("$control = $excel.Workbooks.Open"))


def test_adapter_contains_ordered_native_permission_and_bounded_private_logs() -> None:
    adapter = (Path(__file__).parents[1] / "rns_import_server" / "excel_native.py").read_text(encoding="utf-8")
    assert adapter.index("snapshot = _snapshot_excel_pids()") < adapter.index("subprocess.Popen(")
    start = adapter.index("lease = _read_lease")
    assert start < adapter.index("verify_excel_process_lease", start) < adapter.index("journal.transition", start) < adapter.index("_audit_ack", start) < adapter.index('_send(process, "open")', start)
    assert "_LOG_LIMIT = 64 * 1024" in adapter and "threading.Thread(target=_drain" in adapter
    assert "cleanup_excel_process" in adapter and "durable_phase" in adapter
    assert "_CANCEL_GRACE = 8.0" in adapter and '"cancel"' in adapter


@pytest.mark.parametrize("change,timeout,code", [
    (None, 1.0, "native_request_invalid"), ("row-string", 1.0, "native_insert_row_invalid"),
    ("row-bool", 1.0, "native_insert_row_invalid"), ("path-proxy", 1.0, "native_path_invalid"),
    (None, True, "native_timeout_invalid"), (None, "1", "native_timeout_invalid"), (None, math.nan, "native_timeout_invalid"),
])
def test_builtin_request_validation_precedes_all_side_effects(tmp_path: Path, change: str | None, timeout: object, code: str) -> None:
    request: object = NativeInsertRequest("op", "owner", "pair", tmp_path / "control.xlsx", tmp_path / "candidate.xlsx", 6, tmp_path / "ops" / "lease.json", tmp_path / "ops" / "ack.json", "sheet", {}, None, "middle_insert")
    if change == "row-string": object.__setattr__(request, "insertion_row", "6")
    if change == "row-bool": object.__setattr__(request, "insertion_row", True)
    if change == "path-proxy": object.__setattr__(request, "control", "control.xlsx")
    if request is not None and change is None and code == "native_request_invalid": request = object()
    with pytest.raises(NativeExcelError) as captured:
        run_native_insert(request, tmp_path / "helper.ps1", Journal(), timeout=timeout)  # type: ignore[arg-type]
    assert (captured.value.code, captured.value.stage) == (code, "pre_open")
    assert not (tmp_path / "ops").exists()


def _lease() -> ExcelProcessLease:
    return ExcelProcessLease("op", "owner", "pair", "com", "powershell.exe", 11, "2026-08-21T00:00:00Z", "EXCEL.EXE", 22, 33, "2026-08-21T00:00:01Z", "16.0")


class _Input:
    def __init__(self, *, fail: bool = False): self.values, self.fail = [], fail
    def write(self, value: bytes) -> None:
        self.values.append(value)
        if self.fail: raise OSError("pipe")
    def flush(self) -> None: pass


class _Process:
    def __init__(self, *, fail_send: bool = False):
        self.pid, self.stdin, self.stdout, self.stderr, self.returncode = 11, _Input(fail=fail_send), io.BytesIO(), io.BytesIO(), None
    def poll(self): return self.returncode
    def wait(self, timeout: float): self.returncode = 1; return 1


def _native_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, fail_send: bool = False, fail_ack: bool = False) -> tuple[_Process, list[object]]:
    process, calls = _Process(fail_send=fail_send), []
    monkeypatch.setattr(native, "native_excel_available", lambda: True)
    monkeypatch.setattr(native, "_snapshot_excel_pids", lambda: frozenset())
    monkeypatch.setattr(native.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(native, "_read_lease", lambda *args, **kwargs: _lease())
    monkeypatch.setattr(native, "verify_excel_process_lease", lambda *args, **kwargs: _lease())
    monkeypatch.setattr(native, "cleanup_excel_process", lambda *args, **kwargs: None)
    monkeypatch.setattr(native, "_audit_ack", (lambda *args: (_ for _ in ()).throw(OSError("ack"))) if fail_ack else (lambda *args: None))
    class RuntimeJournal:
        def transition(self, *args, **kwargs): calls.append((args, kwargs))
    request = NativeInsertRequest("op", "owner", "pair", tmp_path / "control.xlsx", tmp_path / "candidate.xlsx", 6, tmp_path / "lease.json", tmp_path / "ack.json", "sheet", {}, None, "middle_insert")
    with pytest.raises(NativeExcelError) as captured:
        run_native_insert(request, tmp_path / "helper.ps1", RuntimeJournal(), timeout=0.01)
    assert captured.value.durable_phase == "native" and calls
    return process, calls


@pytest.mark.parametrize("fail_send,fail_ack", [(False, True), (True, False)])
def test_post_cas_ack_and_stdin_io_failures_are_durable_native(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail_send: bool, fail_ack: bool) -> None:
    process, _ = _native_runtime(monkeypatch, tmp_path, fail_send=fail_send, fail_ack=fail_ack)
    assert process.stdin.values


def test_timeout_fake_runtime_sends_live_cancel_then_reports_native_phase(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class TimeoutProcess(_Process):
        def poll(self): return None
        def wait(self, timeout: float): raise native.subprocess.TimeoutExpired("helper", timeout)
    process = TimeoutProcess()
    monkeypatch.setattr(native, "native_excel_available", lambda: True)
    monkeypatch.setattr(native, "_snapshot_excel_pids", lambda: frozenset())
    monkeypatch.setattr(native.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(native, "_read_lease", lambda *args, **kwargs: _lease())
    monkeypatch.setattr(native, "verify_excel_process_lease", lambda *args, **kwargs: _lease())
    monkeypatch.setattr(native, "cleanup_excel_process", lambda *args, **kwargs: None)
    monkeypatch.setattr(native, "_audit_ack", lambda *args: None)
    class RuntimeJournal:
        def transition(self, *args, **kwargs): pass
    request = NativeInsertRequest("op", "owner", "pair", tmp_path / "control.xlsx", tmp_path / "candidate.xlsx", 6, tmp_path / "lease.json", tmp_path / "ack.json", "sheet", {}, None, "middle_insert")
    with pytest.raises(NativeExcelError) as captured:
        run_native_insert(request, tmp_path / "helper.ps1", RuntimeJournal(), timeout=0.001)
    assert captured.value.code == "excel_timeout" and captured.value.durable_phase == "native"
    assert any(b'"command": "cancel"' in value for value in process.stdin.values)


def test_acl_rejection_fails_before_helper_launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request = NativeInsertRequest("op", "owner", "pair", tmp_path / "control.xlsx", tmp_path / "candidate.xlsx", 6, tmp_path / "lease.json", tmp_path / "ack.json", "sheet", {}, None, "middle_insert")
    monkeypatch.setattr(native, "native_excel_available", lambda: True)
    monkeypatch.setattr(native, "_snapshot_excel_pids", lambda: frozenset())
    monkeypatch.setattr(native, "_verify_private_windows_acl", lambda path: (_ for _ in ()).throw(RuntimeError("acl")))
    monkeypatch.setattr(native.subprocess, "Popen", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("launch")))
    with pytest.raises(NativeExcelError) as captured:
        run_native_insert(request, tmp_path / "helper.ps1", Journal())
    assert (captured.value.code, captured.value.stage) == ("technical_log_unavailable", "launch")


def test_windows_probe_is_locale_neutral_and_canonicalizes_runtime_image() -> None:
    source = Path(__file__).parents[1] / "rns_import_server" / "excel_native.py"
    adapter = source.read_text(encoding="utf-8")
    assert "cannot find a process" not in adapter and "$null -eq $p" in adapter
    assert native._canonical_windows_image("Excel") == native._canonical_windows_image("eXcEl.ExE") == "EXCEL.EXE"
    assert native._canonical_windows_image("PowerShell") == "powershell.exe"
