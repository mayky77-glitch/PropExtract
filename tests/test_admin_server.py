from __future__ import annotations

import json
import hashlib
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.styles import PatternFill

from rns_import_server.audit import sha256
from rns_import_server import app, ocr, picker, server
from rns_import_server.normalization import normalize_text
from rns_import_server.files import discover_pdfs
from rns_import_server.ocr import (
    LANGUAGE_HASHES,
    bundled_language_status,
    project_windows_tool,
    tesseract_environment,
)
from rns_import_server.runtime import _is_supported_tesseract_version, runtime_status
from rns_import_server.server import JobManager, create_server, error_hint, retry_file_operation, user_path, validated_job_paths
from rns_import_server.workbook import SHEET, _change_outcome, _validate, apply, transfer_issue
from scripts.build_windows_python_runtime import build as build_windows_python_runtime


def _fake_runner(pdf_dir: Path, xlsx: Path, output: Path, dpi: int, max_pages: int, progress=None) -> dict:
    assert dpi == 180 and max_pages == 0
    progress(30, "Распознаём PDF", "sample.pdf")
    progress(80, "Переносим данные в Excel", None)
    output.write_bytes(xlsx.read_bytes() + b"-updated")
    return {
        "input_hashes": {"xlsx": sha256(xlsx)},
        "documents": [{"file": str(pdf_dir / "sample.pdf")}],
        "logical_records": ["00-00-00-0000"],
        "changes": [{
            "new": False,
            "row": 42,
            "issues": [],
            "outcome": "already_present",
            "document": "sample.pdf",
        }],
        "conflicts": [],
    }


def _wait(manager: JobManager, job_id: str) -> dict:
    for _ in range(100):
        job = manager.get(job_id)
        if job and job["status"] in {"done", "error"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_job_replaces_target_only_after_verified_backup(tmp_path: Path):
    pdf_dir = tmp_path / "pdf"
    pdf_dir.mkdir()
    (pdf_dir / "sample.pdf").write_bytes(b"pdf")
    target = tmp_path / "register.xlsx"
    target.write_bytes(b"original")
    manager = JobManager(_fake_runner)

    started = manager.start(str(pdf_dir), str(target))
    finished = _wait(manager, str(started["id"]))

    assert finished["status"] == "done"
    assert target.read_bytes() == b"original-updated"
    backup = Path(str(finished["backup"]))
    assert backup.read_bytes() == b"original"
    assert finished["summary"] == {
        "pdf_count": 1,
        "failed_pdf_count": 0,
        "record_count": 1,
        "changed_rows": 0,
        "new_rows": 0,
        "already_present_count": 1,
        "already_present_files": ["sample.pdf"],
        "already_present_rows": [42],
        "conflicts": 0,
        "issue_count": 0,
        "rows_with_issues": [],
        "row_numbers": [42],
        "new_row_numbers": [],
    }


def test_partial_pdf_failure_is_reported_without_stopping_valid_records(tmp_path: Path):
    pdf_dir = tmp_path / "pdf"
    pdf_dir.mkdir()
    (pdf_dir / "sample.pdf").write_bytes(b"pdf")
    target = tmp_path / "register.xlsx"
    target.write_bytes(b"original")

    def partial_runner(*args, **kwargs):
        result = _fake_runner(*args, **kwargs)
        result["documents"].append({"file": str(pdf_dir / "broken.pdf"), "error": "pdfinfo_failed"})
        return result

    manager = JobManager(partial_runner, error_log=tmp_path / "error.log")
    finished = _wait(manager, str(manager.start(str(pdf_dir), str(target))["id"]))

    assert finished["status"] == "done"
    assert finished["summary"]["pdf_count"] == 1
    assert finished["summary"]["failed_pdf_count"] == 1
    assert finished["warning"] == "PDF пропущено: 1. Причины сохранены в отчёте."


def test_failed_job_leaves_target_unchanged(tmp_path: Path):
    target = tmp_path / "register.xlsx"
    target.write_bytes(b"original")
    (tmp_path / "sample.pdf").write_bytes(b"pdf")

    def fail(*args, **kwargs):
        raise RuntimeError("test failure")

    error_log = tmp_path / "propextract-error.log"
    manager = JobManager(fail, error_log=error_log)
    finished = _wait(manager, str(manager.start(str(tmp_path), str(target))["id"]))
    assert finished["status"] == "error"
    assert target.read_bytes() == b"original"
    assert not (tmp_path / "Резервные копии PropExtract").exists()
    assert finished["error_hint"] == "Исправьте указанную причину и повторите запуск. Исходный Excel не изменён."
    assert finished["error_log"] == str(error_log)
    assert "RuntimeError: test failure" in error_log.read_text(encoding="utf-8")


def test_new_record_style_is_allowed_but_existing_row_style_change_is_rejected(tmp_path: Path):
    source = tmp_path / "register.xlsx"
    output = tmp_path / "output.xlsx"
    pdf = tmp_path / "new-record.pdf"
    pdf.write_bytes(b"pdf")
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = SHEET
    sheet["W3"] = "Ссылка на документ"
    sheet["A4"] = 1
    sheet["F4"] = "38-1-1-2026"
    sheet["Y4"] = '=IF(A4<>"",ROW(),"")'
    sheet["Z4"] = '=IF(F4<>"",ROW(),"")'
    sheet["A4"].fill = PatternFill("solid", fgColor="00FF00")
    sheet["A5"].fill = PatternFill("solid", fgColor="FFFF00")
    sheet["Y5"] = '=IF(A5<>"",ROW(),"")'
    sheet["Z5"] = '=IF(F5<>"",ROW(),"")'
    workbook.save(source)
    record = {
        "stage": "13.5",
        "object": "Новый объект",
        "issue": "10.08.2026",
        "end": "10.08.2027",
        "changed": "10.08.2026",
        "issuer": "Администрация",
        "builder": "Застройщик",
        "region": "Иркутская область",
        "district": "Иркутский район",
        "developer": "Разработчик",
        "filename": pdf.name,
        "pdf": str(pdf),
    }

    result = apply({"38-2-2-2026": record}, source, output, sha256(source))

    saved_book = load_workbook(output)
    saved = saved_book[SHEET]
    assert result["changes"][0]["row"] == 5
    assert saved["F5"].value == "38-2-2-2026"
    assert saved["A5"]._style == saved["A4"]._style
    assert saved["Y5"].value == '=IF(A5<>"",ROW(),"")'
    assert saved["Z5"].value == '=IF(F5<>"",ROW(),"")'
    saved["W5"] = "Старая ссылка"
    saved["W5"].hyperlink = "https://example.invalid/old.pdf"
    saved["AA5"] = "Старый статус"
    saved_book.save(output)
    repeated = apply({"38-2-2-2026": record}, output, tmp_path / "repeated.xlsx", sha256(output))
    assert repeated["changes"][0]["outcome"] == "already_present"
    repeated_sheet = load_workbook(tmp_path / "repeated.xlsx")[SHEET]
    assert repeated_sheet["W5"].value == "Старая ссылка"
    assert repeated_sheet["W5"].hyperlink.target == "https://example.invalid/old.pdf"
    assert repeated_sheet["AA5"].value == "Старый статус"

    saved["A4"].fill = PatternFill("solid", fgColor="FF0000")
    saved_book.save(output)
    with pytest.raises(RuntimeError, match=r"^style_changed:A4$"):
        _validate(
            source,
            output,
            {"38-2-2-2026": record},
            {"38-2-2-2026": result["changes"][0]["status"]},
            {"38-2-2-2026": "added"},
        )


def test_empty_native_ocr_stdout_is_safe_text(monkeypatch, tmp_path: Path):
    image = tmp_path / "blank-page.png"
    image.write_bytes(b"png")
    monkeypatch.setattr(
        ocr,
        "_run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, None, None),
    )

    assert ocr._ocr_image(image, "tesseract") == ""
    assert ocr._captured_text(None) == ""
    assert ocr._captured_text("текст") == "текст"


def test_native_process_output_is_always_decoded_as_utf8(monkeypatch):
    captured: dict[str, object] = {}

    def completed(argv, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, "текст", "")

    monkeypatch.setattr(ocr.subprocess, "run", completed)
    result = ocr._run(["tesseract"], timeout=1)

    assert result.stdout == "текст"
    assert captured["encoding"] == "utf-8"
    assert captured["errors"] == "replace"


def test_pdf_discovery_is_case_insensitive_and_skips_symlinks(tmp_path: Path):
    lower = tmp_path / "lower.pdf"
    upper = tmp_path / "UPPER.PDF"
    lower.write_bytes(b"pdf")
    upper.write_bytes(b"pdf")
    (tmp_path / "notes.txt").write_text("not a pdf", encoding="utf-8")
    try:
        (tmp_path / "linked.pdf").symlink_to(lower)
    except OSError:
        pass

    assert discover_pdfs(tmp_path) == [lower, upper]


def test_collect_keeps_valid_pdf_when_another_pdf_fails(monkeypatch, tmp_path: Path):
    broken = tmp_path / "broken.pdf"
    valid = tmp_path / "VALID.PDF"
    broken.write_bytes(b"broken")
    valid.write_bytes(b"valid")

    def read(pdf: Path, dpi: int, max_pages: int):
        if pdf == broken:
            raise RuntimeError("pdfinfo_failed")
        return "38-1-1-2026", 1

    def extract(pdf: Path, text: str):
        return {
            "number": "38-1-1-2026",
            "changed": None,
            "end": None,
            "filename": pdf.name,
            "pdf": str(pdf),
            "warnings": [],
        }

    monkeypatch.setattr(app, "read_ocr", read)
    monkeypatch.setattr(app, "extract", extract)
    records, documents = app.collect(tmp_path, 180, 0)

    assert list(records) == ["38-1-1-2026"]
    assert len(documents) == 2
    assert next(item for item in documents if item["file"] == str(broken))["error"] == "pdfinfo_failed"


def test_run_does_not_publish_when_no_rns_record_is_found(monkeypatch, tmp_path: Path):
    pdf_dir = tmp_path / "pdf"
    pdf_dir.mkdir()
    pdf = pdf_dir / "blank.PDF"
    pdf.write_bytes(b"pdf")
    xlsx = tmp_path / "register.xlsx"
    xlsx.write_bytes(b"xlsx")
    output = tmp_path / "output.xlsx"
    monkeypatch.setattr(
        app,
        "collect",
        lambda *args, **kwargs: ({}, [{"file": str(pdf), "error": "Не найден номер РНС"}]),
    )
    monkeypatch.setattr(app, "apply", lambda *args, **kwargs: pytest.fail("Excel must not be published"))

    with pytest.raises(RuntimeError, match="ни одной записи РНС"):
        app.run(pdf_dir, xlsx, output)
    assert not output.exists()


def test_transient_file_lock_is_retried_with_a_bound(monkeypatch):
    attempts: list[int] = []
    delays: list[float] = []

    def operation():
        attempts.append(1)
        if len(attempts) < 3:
            raise PermissionError("[WinError 32] used by another process")
        return "ready"

    monkeypatch.setattr(server.time, "sleep", delays.append)

    assert retry_file_operation(operation) == "ready"
    assert len(attempts) == 3
    assert delays == [0.2, 0.4]


def test_error_hint_mentions_excel_only_for_access_errors():
    generic = error_hint(RuntimeError("unexpected data"))
    denied = error_hint(PermissionError("[WinError 32] used by another process"))
    javascript = (Path(__file__).parents[1] / "rns_import_server/static/app.js").read_text(encoding="utf-8")

    assert "Закройте" not in generic
    assert "Система запретила запись" in denied
    assert "Проверьте пути, закройте Excel" not in javascript


def _unused_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _get(url: str) -> tuple[int, str, dict[str, str]]:
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.status, response.read().decode("utf-8"), dict(response.headers)


def _post(url: str, payload: dict, headers: dict[str, str] | None = None) -> tuple[int, dict]:
    request_headers = {"Content-Type": "application/json"}
    request_headers.update(headers or {})
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers=request_headers,
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_http_serves_admin_help_health_and_security_headers():
    port = _unused_port()
    server = create_server("127.0.0.1", port, _fake_runner)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, body, headers = _get(f"http://127.0.0.1:{port}/")
        assert status == 200 and "Перенести данные" in body and "Остановить" in body
        assert headers["X-Frame-Options"] == "DENY"
        status, body, _ = _get(f"http://127.0.0.1:{port}/help")
        assert status == 200 and "Инструкция оператора" in body
        status, body, _ = _get(f"http://127.0.0.1:{port}/health")
        assert status == 200 and json.loads(body) == {"status": "ok", "service": "rns-import"}
        status, body, _ = _get(f"http://127.0.0.1:{port}/api/system")
        assert status == 200 and "commands" in json.loads(body)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_invalid_job_request_is_rejected():
    port = _unused_port()
    server = create_server("127.0.0.1", port, _fake_runner)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/jobs",
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(request, timeout=5)
            raise AssertionError("invalid request must fail")
        except urllib.error.HTTPError as error:
            assert error.code == 400
            assert "PDF" in error.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_explorer_paths_with_quotes_are_normalized_before_job(tmp_path: Path):
    pdf_dir = tmp_path / "PDF документы"
    pdf_dir.mkdir()
    (pdf_dir / "sample.pdf").write_bytes(b"pdf")
    target = tmp_path / "Реестр РНС.xlsx"
    target.write_bytes(b"original")

    normalized_pdf, normalized_xlsx = validated_job_paths(f'"{pdf_dir}"', f'«{target}»')

    assert normalized_pdf == pdf_dir
    assert normalized_xlsx == target
    assert user_path(pdf_dir.as_uri()) == pdf_dir


def test_manual_paths_report_which_value_is_invalid(tmp_path: Path):
    target = tmp_path / "register.xlsx"
    target.write_bytes(b"xlsx")
    with pytest.raises(ValueError, match="Папка с PDF не найдена"):
        validated_job_paths(str(tmp_path / "missing"), str(target))
    with pytest.raises(ValueError, match="указан файл"):
        validated_job_paths(str(target), str(target))


def test_native_picker_endpoint_returns_selected_path(monkeypatch, tmp_path: Path):
    selected = tmp_path / "register.xlsx"
    monkeypatch.setattr("rns_import_server.server.select_path", lambda kind: str(selected) if kind == "xlsx" else None)
    port = _unused_port()
    server = create_server("127.0.0.1", port, _fake_runner)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, payload = _post(f"http://127.0.0.1:{port}/api/picker", {"kind": "xlsx"})
        assert status == 200
        assert payload == {"path": str(selected), "cancelled": False}
        status, payload = _post(f"http://127.0.0.1:{port}/api/picker", {"kind": "directory"})
        assert status == 200
        assert payload == {"path": None, "cancelled": True}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_shutdown_endpoint_stops_idle_server():
    port = _unused_port()
    server = create_server("127.0.0.1", port, _fake_runner)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, payload = _post(
            f"http://127.0.0.1:{port}/api/shutdown",
            {},
            {"X-PropExtract-Action": "shutdown"},
        )
        assert status == 202
        assert payload == {"status": "stopping"}
        thread.join(timeout=5)
        assert not thread.is_alive()
    finally:
        server.server_close()


def test_shutdown_is_rejected_while_excel_job_is_running(tmp_path: Path):
    release = threading.Event()
    pdf_dir = tmp_path / "pdf"
    pdf_dir.mkdir()
    (pdf_dir / "sample.pdf").write_bytes(b"pdf")
    target = tmp_path / "register.xlsx"
    target.write_bytes(b"original")

    def slow_runner(*args, **kwargs):
        release.wait(timeout=5)
        return _fake_runner(*args, **kwargs)

    port = _unused_port()
    server = create_server("127.0.0.1", port, slow_runner)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    server.job_manager.start(str(pdf_dir), str(target))  # type: ignore[attr-defined]
    try:
        with pytest.raises(urllib.error.HTTPError) as caught:
            _post(
                f"http://127.0.0.1:{port}/api/shutdown",
                {},
                {"X-PropExtract-Action": "shutdown"},
            )
        assert caught.value.code == 409
        assert "идёт перенос данных" in caught.value.read().decode("utf-8")
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_macos_picker_uses_native_osascript_and_handles_cancel(monkeypatch, tmp_path: Path):
    selected = tmp_path / "pdf"
    selected.mkdir()
    calls: list[list[str]] = []

    def completed(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, f"{selected}\n", "")

    monkeypatch.setattr(picker.sys, "platform", "darwin")
    monkeypatch.setattr(picker.subprocess, "run", completed)
    assert picker.choose("directory") == str(selected)
    assert calls[0][0] == "/usr/bin/osascript"

    monkeypatch.setattr(
        picker.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 1, "", "execution error: cancelled (-128)"),
    )
    assert picker.choose("xlsx") == ""


def test_windows_picker_uses_exact_system_powershell(monkeypatch, tmp_path: Path):
    system_directory = tmp_path / "Windows/System32"
    powershell = system_directory / "WindowsPowerShell/v1.0/powershell.exe"
    selected = tmp_path / "pdf"
    powershell.parent.mkdir(parents=True)
    powershell.write_bytes(b"")
    selected.mkdir()
    calls: list[list[str]] = []

    def completed(argv, **kwargs):
        calls.append(argv)
        assert kwargs["encoding"] == "utf-8"
        assert kwargs["timeout"] == 120
        return subprocess.CompletedProcess(argv, 0, f"{selected}\n", "")

    monkeypatch.setattr(picker.sys, "platform", "win32")
    monkeypatch.setattr(picker, "_windows_system_directory", lambda: system_directory)
    monkeypatch.setattr(picker.subprocess, "run", completed)

    assert picker.choose("directory") == str(selected.resolve())
    assert calls[0][0] == str(powershell)
    assert "FolderBrowserDialog" in picker._windows_dialog_script("directory")
    assert "OpenFileDialog" in picker._windows_dialog_script("xlsx")
    assert "$Owner.StartPosition = 'CenterScreen'" in calls[0][-1]
    assert "$Owner.Opacity = 0.01" in calls[0][-1]


def test_transfer_issue_explains_missing_and_conflicting_values():
    assert transfer_issue("Орган выдачи", None, None) == (
        "Не перенесено «Орган выдачи»: значение не найдено в PDF."
    )
    assert transfer_issue("Орган выдачи", "Администрация", None) == (
        "Не подтверждено «Орган выдачи»: значение не найдено в PDF; "
        "значение Excel «Администрация» сохранено."
    )
    assert transfer_issue("Срок действия", "28.11.2026", "28.11.2025") == (
        "Не перенесено «Срок действия»: в Excel — «28.11.2026», "
        "в PDF — «28.11.2025»; значение Excel сохранено."
    )
    assert transfer_issue("Срок действия", "28.11.2025", "28.11.2025") is None
    assert transfer_issue("Застройщик", 'ПАО "Газпром"', "ПАО «Газпром»") is None
    assert transfer_issue("Орган выдачи", "СЛУЖБА НАДЗОРА", "Служба надзора") is None
    assert _change_outcome(False, [], []) == "already_present"
    assert _change_outcome(False, ["D42"], []) == "updated"
    assert _change_outcome(False, [], ["расхождение"]) == "review"
    assert _change_outcome(True, ["D43"], []) == "added"


def test_document_optimizer_text_normalization_contract_is_preserved():
    assert normalize_text("  Монтаж\u00a0  ТРУБ Ёлка ") == "монтаж труб елка"
    assert normalize_text("  ПАО «Газпром»  ", casefold=False) == "ПАО «Газпром»"


def test_bundled_ocr_models_are_verified_and_forced():
    status = bundled_language_status()
    assert set(status) == set(LANGUAGE_HASHES)
    assert all(item["valid"] for item in status.values())
    assert Path(tesseract_environment()["TESSDATA_PREFIX"]).name == "tessdata"


def test_runtime_reports_bundled_ocr_models():
    status = runtime_status()
    assert set(status["models"]) == {"rus", "eng"}


def test_tesseract_version_formats_used_by_portable_and_system_builds():
    assert _is_supported_tesseract_version("tesseract 5.5.1")
    assert _is_supported_tesseract_version("tesseract v5.5.3.20260724")
    assert not _is_supported_tesseract_version("tesseract 4.1.1")


def test_one_command_installers_cover_required_runtime():
    root = Path(__file__).resolve().parents[1]
    windows = (root / "install_windows.ps1").read_text(encoding="utf-8")
    windows_start = (root / "start_windows.ps1").read_text(encoding="utf-8")
    windows_stop = (root / "stop_windows.ps1").read_text(encoding="utf-8")
    linux = (root / "install_linux.sh").read_text(encoding="utf-8")
    lock = json.loads((root / "windows-runtime.lock.json").read_text(encoding="utf-8"))
    assert lock["architectures"] == ["x64", "arm64-x64-emulation"]
    for artifact in lock["artifacts"].values():
        path = root / artifact["path"]
        assert path.is_file()
        assert sha256(path) == artifact["sha256"]
    for package in lock["pythonTree"]["packages"]:
        path = root / package["path"]
        assert path.is_file()
        assert sha256(path) == package["sha256"]
    assert "WinGet, Microsoft Store, network downloads" in windows
    assert "Test-PropExtractFileSha256" in windows
    assert "Test-PropExtractPythonTree" in windows
    assert "Assert-SupportedWindows" in windows
    assert 'GetEnvironmentVariable("PYTHONDONTWRITEBYTECODE", "Process")' in windows
    assert 'GetEnvironmentVariable("TESSDATA_PREFIX", "Process")' in windows
    assert "sys.maxsize > 2**32" in windows
    assert "struct.calcsize" not in windows
    assert "sys.maxsize > 2**32" in windows_start
    assert "struct.calcsize" not in windows_start
    assert windows_start.isascii() and windows_stop.isascii()
    assert "/api/shutdown" in windows_stop
    assert "X-PropExtract-Action" in windows_stop
    assert (root / "Запустить PropExtract.cmd").is_file()
    assert (root / "Остановить PropExtract.cmd").is_file()
    assert 'function Invoke-NativeProbe' in windows
    assert '$ErrorActionPreference = "Continue"' in windows
    assert 'tesseract v?5\\.' in windows
    assert "-Verb RunAs" not in windows
    assert "EncodedCommand" not in windows
    assert "winget source reset" not in windows.lower()
    assert "Invoke-WebRequest" not in windows
    assert "WebClient" not in windows
    assert "PEP-514" not in windows
    assert "-Verb RunAs" not in (root / "install_windows.cmd").read_text(encoding="utf-8")
    assert "raw/codex/admin-ui" not in json.dumps(lock)
    assert "IO.Compression.ZipFile" in windows
    for package in ("python3-venv", "poppler-utils", "tesseract-ocr"):
        assert package in linux
    assert "-m rns_import_server.runtime" in windows
    assert "-m rns_import_server.runtime" in linux


def test_windows_python_tree_is_reproducible(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    lock = json.loads((root / "windows-runtime.lock.json").read_text(encoding="utf-8"))
    digest, count = build_windows_python_runtime(
        root / "packages",
        root / lock["pythonTree"]["pthTemplatePath"],
        tmp_path / "python-runtime",
    )

    assert count == lock["pythonTree"]["files"]
    assert digest == lock["pythonTree"]["sha256"]


def test_project_windows_tool_finds_versioned_portable_runtime(tmp_path: Path):
    tesseract = tmp_path / ".runtime/windows/native-5.5.3/tesseract/tesseract.exe"
    poppler = tmp_path / ".runtime/windows/native-5.5.3/poppler/release/Library/bin/pdfinfo.exe"
    invalid = tmp_path / ".runtime/windows/native-9.invalid.20260810/tesseract/tesseract.exe"
    staging = tmp_path / ".runtime/windows/native-staging-test/tesseract/tesseract.exe"
    tesseract.parent.mkdir(parents=True)
    poppler.parent.mkdir(parents=True)
    invalid.parent.mkdir(parents=True)
    staging.parent.mkdir(parents=True)
    tesseract.write_bytes(b"tesseract")
    poppler.write_bytes(b"pdfinfo")
    runtime = tesseract.parents[1]
    entries = sorted(
        (path.relative_to(runtime).as_posix(), sha256(path))
        for path in runtime.rglob("*")
        if path.is_file()
    )
    digest = hashlib.sha256(
        "".join(f"{item_hash}  {relative}\n" for relative, item_hash in entries).encode()
    ).hexdigest()
    (tmp_path / "windows-runtime.lock.json").write_text(
        json.dumps(
            {
                "runtime": "5.5.3",
                "nativeTree": {
                    "files": len(entries),
                    "sha256": digest,
                    "tesseractPath": "tesseract/tesseract.exe",
                    "popplerBinPath": "poppler/release/Library/bin",
                },
            }
        ),
        encoding="utf-8",
    )
    invalid.write_bytes(b"")
    staging.write_bytes(b"")

    assert project_windows_tool("tesseract", tmp_path) == str(tesseract)
    assert project_windows_tool("pdfinfo", tmp_path) == str(poppler)
    assert project_windows_tool("unknown", tmp_path) is None


def test_project_windows_tool_rejects_a_tampered_runtime(tmp_path: Path):
    runtime = tmp_path / ".runtime/windows/native-1"
    executable = runtime / "tesseract/tesseract.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"tampered")
    (tmp_path / "windows-runtime.lock.json").write_text(
        json.dumps(
            {
                "runtime": "1",
                "nativeTree": {
                    "files": 1,
                    "sha256": "0" * 64,
                    "tesseractPath": "tesseract/tesseract.exe",
                    "popplerBinPath": "poppler/bin",
                },
            }
        ),
        encoding="utf-8",
    )

    assert project_windows_tool("tesseract", tmp_path) is None
