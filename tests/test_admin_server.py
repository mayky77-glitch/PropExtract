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

from rns_import_server.audit import sha256
from rns_import_server import picker
from rns_import_server.normalization import normalize_text
from rns_import_server.ocr import (
    LANGUAGE_HASHES,
    bundled_language_status,
    project_windows_tool,
    tesseract_environment,
)
from rns_import_server.runtime import runtime_status
from rns_import_server.server import JobManager, create_server
from rns_import_server.workbook import transfer_issue
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
        "changes": [{"new": False, "row": 42, "issues": []}],
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
        "record_count": 1,
        "changed_rows": 1,
        "new_rows": 0,
        "conflicts": 0,
        "issue_count": 0,
        "rows_with_issues": [],
        "row_numbers": [42],
        "new_row_numbers": [],
    }


def test_failed_job_leaves_target_unchanged(tmp_path: Path):
    target = tmp_path / "register.xlsx"
    target.write_bytes(b"original")

    def fail(*args, **kwargs):
        raise RuntimeError("test failure")

    manager = JobManager(fail)
    finished = _wait(manager, str(manager.start(str(tmp_path), str(target))["id"]))
    assert finished["status"] == "error"
    assert target.read_bytes() == b"original"
    assert not (tmp_path / "Резервные копии PropExtract").exists()


def _unused_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _get(url: str) -> tuple[int, str, dict[str, str]]:
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.status, response.read().decode("utf-8"), dict(response.headers)


def _post(url: str, payload: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
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
        assert status == 200 and "Перенести данные" in body
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
        return subprocess.CompletedProcess(argv, 0, f"{selected}\n", "")

    monkeypatch.setattr(picker.sys, "platform", "win32")
    monkeypatch.setattr(picker, "_windows_system_directory", lambda: system_directory)
    monkeypatch.setattr(picker.subprocess, "run", completed)

    assert picker.choose("directory") == str(selected.resolve())
    assert calls[0][0] == str(powershell)
    assert "FolderBrowserDialog" in calls[0][-1]


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


def test_one_command_installers_cover_required_runtime():
    root = Path(__file__).resolve().parents[1]
    windows = (root / "install_windows.ps1").read_text(encoding="utf-8")
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
