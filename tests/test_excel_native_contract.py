from pathlib import Path
import io
import json
import math
import os
import queue
import subprocess
import threading

import pytest

import rns_import_server.excel_native as native
from rns_import_server.excel_native import NativeExcelError, NativeInsertRequest, native_excel_available, run_native_insert
from rns_import_server.excel_process_authority import ExcelProcessLease, ProcessIdentity
from rns_import_server.registry_storage import RegistryStorage
from rns_import_server.workbook_operation_journal import PHASE_NATIVE, PHASE_STAGED, WorkbookOperationJournal


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


def test_verified_lease_commits_real_sqlite_journal_before_ack_and_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage = RegistryStorage.bootstrap(tmp_path / "registry")
    try:
        journal = WorkbookOperationJournal(storage)
        operation_id = "00000000-0000-4000-8000-000000000001"
        journal.create(
            operation_id=operation_id, idempotency_key="native-idempotency", consumer_id=operation_id,
            owner_id="owner", pair_nonce="pair", construction_id=storage.list_constructions()[0].id,
            operation_kind="new_row", mutation_mode="middle_insert", target_identity="target", sheet_identity="sheet",
            template_version="template-v1", expected_generation=storage.generation, intent_version="intent-v1",
            intent_digest="intent-digest", manifest_version="manifest-v1", manifest_digest="manifest-digest",
            operation_directory="operation-dir", canonical_rns="RU-00000000-00-2026",
            workbook_contract_id="native-contract-v1",
        )
        journal.transition(operation_id, expected_phase="planned", next_phase=PHASE_STAGED, hashes={"pre_hash": "pre", "staged_hash": "staged"})
        request = _request(tmp_path, operation_id=operation_id)
        lease = ExcelProcessLease(
            operation_id=operation_id, owner_id="owner", pair_nonce="pair", adapter_type="com",
            adapter_image="powershell.exe", adapter_pid=71, adapter_started_at="2026-08-21T00:00:00Z",
            excel_image="EXCEL.EXE", excel_pid=72, excel_hwnd=73,
            excel_process_started_at="2026-08-21T00:00:01Z", excel_build="16.0.1",
        )

        class Inspector:
            excel_calls = 0
            def __init__(self, snapshot): pass
            def prelaunch_excel_pids(self): return frozenset()
            def process_identity(self, pid):
                if pid == 71: return ProcessIdentity(71, "powershell.exe", "2026-08-21T00:00:00Z")
                if type(self).excel_calls == 0:
                    type(self).excel_calls += 1
                    return ProcessIdentity(72, "EXCEL.EXE", "2026-08-21T00:00:01Z")
                raise native.ProcessMissingError()
            def hwnd_process_id(self, hwnd): return 72
            def terminate_process(self, pid): raise AssertionError("verified helper already quit")
            def wait_for_process_exit(self, pid, timeout): raise AssertionError("verified helper already quit")

        class Process:
            pid, returncode = 71, 0
            def __init__(self): self.stdin = io.BytesIO(); self.stdout = io.BytesIO(b'{"status":"ok"}'); self.stderr = io.BytesIO()
            def poll(self): return 0
            def wait(self, timeout=None): return 0

        processes = []
        def popen(*args, **kwargs):
            request.lease_file.write_text(json.dumps({
                "operation_id": lease.operation_id, "owner_id": lease.owner_id, "pair_nonce": lease.pair_nonce,
                "adapter_type": lease.adapter_type, "adapter_image": lease.adapter_image, "adapter_pid": lease.adapter_pid,
                "adapter_started_at": lease.adapter_started_at, "excel_image": lease.excel_image, "excel_pid": lease.excel_pid,
                "excel_hwnd": lease.excel_hwnd, "excel_process_started_at": lease.excel_process_started_at,
                "excel_build": lease.excel_build,
            }), encoding="utf-8")
            process = Process(); processes.append(process); return process

        original_ack = native._audit_ack
        def check_ack(current):
            assert journal.get(operation_id).phase == PHASE_NATIVE  # type: ignore[union-attr]
            original_ack(current)

        monkeypatch.setattr(native, "native_excel_available", lambda: True)
        monkeypatch.setattr(native, "_snapshot_excel_pids", lambda: frozenset())
        monkeypatch.setattr(native, "_WindowsInspector", Inspector)
        monkeypatch.setattr(native.subprocess, "Popen", popen)
        monkeypatch.setattr(native, "_audit_ack", check_ack)
        assert run_native_insert(request, tmp_path / "helper.ps1", journal) == {"status": "ok", "durable_phase": "native"}
        assert processes[0].stdin.getvalue() == b'{"command":"open"}\n'
        persisted = journal.get(operation_id)
        assert persisted is not None and persisted.phase == PHASE_NATIVE
        assert tuple(persisted[name] for name in (
            "excel_adapter", "excel_adapter_pid", "excel_adapter_started_at", "excel_pid", "excel_hwnd",
            "excel_process_started_at", "excel_build",
        )) == ("com", 71, "2026-08-21T00:00:00Z", 72, 73, "2026-08-21T00:00:01Z", "16.0.1")
    finally:
        storage.close()


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
