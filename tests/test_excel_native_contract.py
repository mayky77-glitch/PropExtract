from pathlib import Path
import math
import os
import queue
import subprocess
import threading

import pytest

import rns_import_server.excel_native as native
from rns_import_server.excel_native import NativeExcelError, NativeInsertRequest, native_excel_available, run_native_insert


class Journal:
    def transition(self, *args, **kwargs):
        raise AssertionError("safe negative path must not transition")


def _request(tmp_path: Path, **changes: object) -> NativeInsertRequest:
    values: dict[str, object] = {
        "operation_id": "op", "owner_nonce": "owner", "pair_nonce": "pair",
        "control": tmp_path / "control.xlsx", "candidate": tmp_path / "candidate.xlsx",
        "insertion_row": 6, "lease_file": tmp_path / "ops" / "lease.json",
        "ack_file": tmp_path / "ops" / "ack.json", "sheet": "Реестр РНС",
        "fields": {6: "value"}, "hyperlink": None, "mutation_mode": "middle_insert",
    }
    values.update(changes)
    return NativeInsertRequest(**values)  # type: ignore[arg-type]


def test_hosted_non_windows_is_typed_safe_negative_path(tmp_path: Path) -> None:
    if not native_excel_available():
        with pytest.raises(NativeExcelError) as captured:
            run_native_insert(_request(tmp_path), tmp_path / "helper.ps1", Journal())
        assert (captured.value.code, captured.value.stage) == ("excel_required_for_middle_insert", "pre_open")


@pytest.mark.parametrize(("changes", "code"), [
    ({"insertion_row": 0}, "native_insert_row_invalid"),
    ({"insertion_row": True}, "native_insert_row_invalid"),
    ({"fields": {0: "x"}}, "native_request_invalid"),
    ({"fields": {6: float("nan")}}, "native_request_invalid"),
    ({"mutation_mode": "MIDDLE_INSERT"}, "native_mutation_mode_invalid"),
    ({"control": "not-a-path"}, "native_path_invalid"),
])
def test_invalid_exact_request_fails_before_directory_or_launch(tmp_path: Path, changes: dict[str, object], code: str) -> None:
    with pytest.raises(NativeExcelError) as captured:
        run_native_insert(_request(tmp_path, **changes), tmp_path / "helper.ps1", Journal())
    assert (captured.value.code, captured.value.stage) == (code, "pre_open")
    assert not (tmp_path / "ops").exists()


@pytest.mark.parametrize("timeout", [0, -1, math.inf, float("nan"), True])
def test_invalid_timeout_fails_before_directory(tmp_path: Path, timeout: object) -> None:
    with pytest.raises(NativeExcelError) as captured:
        run_native_insert(_request(tmp_path), tmp_path / "helper.ps1", Journal(), timeout=timeout)  # type: ignore[arg-type]
    assert (captured.value.code, captured.value.stage) == ("native_timeout_invalid", "pre_open")
    assert not (tmp_path / "ops").exists()


def test_request_payload_preserves_pair_paths_and_canonical_fields(tmp_path: Path) -> None:
    request = _request(tmp_path, mutation_mode="blank_fill")
    assert request.payload()["pair_nonce"] == "pair"
    assert request.payload()["insertion_row"] == 6
    assert request.payload()["mutation_mode"] == "blank_fill"


def test_helper_has_single_background_stdin_owner_and_no_forbidden_readers() -> None:
    script = (Path(__file__).parents[1] / "scripts" / "windows_excel_insert.ps1").read_text(encoding="utf-8")
    assert "Console.OpenStandardInput()" in script
    assert "reader.IsBackground = true" in script
    assert script.count("new StreamReader(Console.OpenStandardInput()") == 1
    for forbidden in ("Console.In", "Peek()", "ReadLineAsync", "Task.Run", "Start-Job", "Start-ThreadJob"):
        assert forbidden not in script
    assert script.index("Write-DurableUtf8NoBom $temporary") < script.index("$control = $excel.Workbooks.Open")
    assert script.index("$controlReader.Start()") < script.index("$control = $excel.Workbooks.Open")
    assert script.count("Test-NativeCancel $controlReader") >= 7
    assert script.index("$excel.Quit()") < script.index("if ($success)")


def test_helper_reader_accepts_exact_ordered_open_then_optional_cancel() -> None:
    script = (Path(__file__).parents[1] / "scripts" / "windows_excel_insert.ps1").read_text(encoding="utf-8")
    assert 'message.Count != 1' in script and 'message.ContainsKey("command")' in script
    assert 'if (!opened)' in script and 'if (command == "cancel") { cancelled = true; return; }' in script
    assert 'if (command == "cancel") { cancelled = true; return; }' in script
    assert script.index('reader.IsBackground = true') < script.index('reader.Start()')


def _native_reader_probe(tmp_path: Path, *, cancel: bool) -> tuple[int, str]:
    if os.name != "nt":
        pytest.skip("native Windows PowerShell 5.1 qualification required")
    script = (Path(__file__).parents[1] / "scripts" / "windows_excel_insert.ps1").read_text(encoding="utf-8")
    start = script.index("using System;", script.index("Add-Type -ReferencedAssemblies"))
    end = script.index("\n'@\n\nfunction Test-NativeCancel", start)
    probe = tmp_path / "native-reader-probe.ps1"
    probe.write_text(
        "Add-Type -ReferencedAssemblies 'System.Web.Extensions.dll' -TypeDefinition @'\n" + script[start:end] +
        "\n'@\n$r=New-Object NativeControlReader;$r.Start();if(-not $r.WaitForOpen(1000)){exit 6};[Console]::Out.WriteLine('ready');" +
        ("for($i=0;$i -lt 300;$i++){" if cancel else "for($i=0;$i -lt 30;$i++){") +
        "if($r.Failed){exit 5};if($r.IsCancellationRequested){[Console]::Out.WriteLine('cancelled');exit 4};Start-Sleep -Milliseconds 10};[Console]::Out.WriteLine('complete');exit 0\n",
        encoding="utf-8",
    )
    process = subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(probe)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert process.stdin is not None and process.stdout is not None
    lines: queue.Queue[str] = queue.Queue()
    threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
    process.stdin.write('{"command":"open"}\n'); process.stdin.flush()
    assert lines.get(timeout=5).strip() == "ready"
    if cancel:
        process.stdin.write('{"command":"cancel"}\n'); process.stdin.flush()
    try:
        return process.wait(timeout=4 if cancel else 2), process.stdout.read().strip()
    finally:
        if process.poll() is None:
            process.terminate(); process.wait(timeout=1)


def test_native_background_reader_exits_while_parent_stdin_stays_open(tmp_path: Path) -> None:
    assert _native_reader_probe(tmp_path, cancel=False) == (0, "complete")


def test_native_background_reader_consumes_post_open_cancel(tmp_path: Path) -> None:
    assert _native_reader_probe(tmp_path, cancel=True) == (4, "cancelled")


def test_ordered_handshake_dacl_and_capped_concurrent_drain() -> None:
    adapter = (Path(__file__).parents[1] / "rns_import_server" / "excel_native.py").read_text(encoding="utf-8")
    assert adapter.index("_private_logs(request)") < adapter.index("subprocess.Popen(")
    assert adapter.index("verify_excel_process_lease") < adapter.index("journal.transition") < adapter.index("_audit_ack(request)") < adapter.index('_send(process, "open")')
    assert "_LOG_LIMIT = 64 * 1024" in adapter and adapter.count("threading.Thread(target=_drain") == 2
    assert "cannot find a process" not in adapter and "$null -eq $p" in adapter
    assert native._canonical_windows_image("Excel") == native._canonical_windows_image("eXcEl.ExE") == "EXCEL.EXE"
