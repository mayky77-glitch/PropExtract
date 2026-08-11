#!/usr/bin/env python3
"""Windows-only offline smoke for PropExtract's exact portable runtime.

The workflow starts this module with the installed app-local Python.  Fixtures
are generated under ``TemporaryDirectory`` and never leave the runner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import threading
import time
from http.client import HTTPConnection
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PERMIT_NUMBER = "38-1-1-2026"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _pdf_literal(value: str) -> bytes:
    """Escape the ASCII fixture text used in a minimal, text-layer PDF."""
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("ascii")


def _write_text_pdf(path: Path, lines: list[str]) -> None:
    """Write a deterministic one-page PDF without a generator dependency."""
    if not lines or any(not line.isascii() for line in lines):
        raise ValueError("synthetic PDF lines must be non-empty ASCII")
    commands = [b"BT", b"/F1 12 Tf", b"72 720 Td"]
    for index, line in enumerate(lines):
        if index:
            commands.append(b"0 -18 Td")
        commands.append(b"(" + _pdf_literal(line) + b") Tj")
    commands.append(b"ET")
    stream = b"\n".join(commands) + b"\n"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"endstream",
    ]
    payload = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload.extend(f"{number} 0 obj\n".encode("ascii"))
        payload.extend(body)
        payload.extend(b"\nendobj\n")
    xref = len(payload)
    payload.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    payload.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    path.write_bytes(payload)


def _require_portable_windows_runtime() -> None:
    if os.name != "nt":
        raise RuntimeError("Windows smoke must run on Windows")
    lock = json.loads((PROJECT_ROOT / "windows-runtime.lock.json").read_text(encoding="utf-8"))
    expected = (
        PROJECT_ROOT
        / ".runtime"
        / "windows"
        / f"python-{lock['artifacts']['python']['version']}"
        / str(lock["pythonTree"]["executablePath"])
    ).resolve()
    if Path(sys.executable).resolve() != expected:
        raise RuntimeError("Windows smoke must use the installed app-local portable Python")


def _request(port: int, method: str, path: str, payload: dict[str, object] | None = None) -> tuple[int, dict[str, object], str | None]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    raw = response.read()
    instance = response.getheader("X-PropExtract-Instance")
    connection.close()
    return response.status, json.loads(raw.decode("utf-8")), instance


def _wait_for_job(port: int, job_id: str) -> dict[str, object]:
    for _ in range(120):
        status, job, _ = _request(port, "GET", f"/api/jobs/{job_id}")
        if status != 200:
            raise RuntimeError(f"job polling failed: HTTP {status}")
        if job.get("status") in {"done", "error"}:
            return job
        time.sleep(0.25)
    raise RuntimeError("synthetic import did not complete within 30 seconds")


def _make_register(path: Path) -> None:
    from openpyxl import Workbook
    from rns_import_server.workbook import HEADERS, SHEET

    book = Workbook()
    sheet = book.active
    sheet.title = SHEET
    for label, column in HEADERS.items():
        sheet.cell(3, column).value = label
    sheet["Y3"] = "service formula one"
    sheet["Z3"] = "service formula two"
    sheet["Y4"] = '=IF(A4<>"",ROW(),"")'
    sheet["Z4"] = '=IF(F4<>"",ROW(),"")'
    book.save(path)


def run() -> dict[str, object]:
    _require_portable_windows_runtime()
    from rns_import_server.app import run as import_run
    from rns_import_server.runtime import runtime_status
    from rns_import_server.server import create_server, project_instance_id

    runtime = runtime_status()
    if not runtime.get("ready") or not all(runtime.get("commands", {}).values()):
        raise RuntimeError("portable Poppler/Tesseract runtime is not ready")

    with tempfile.TemporaryDirectory(prefix="propextract-e2e-") as temporary_name:
        temporary = Path(temporary_name) / "Проверка_Юникод"
        pdf_dir = temporary / "PDF"
        pdf_dir.mkdir(parents=True)
        permit = pdf_dir / "permit_38-1-1-2026.pdf"
        _write_text_pdf(permit, [PERMIT_NUMBER, "1.1: 01.02.2026"])
        register = temporary / "register.xlsx"
        _make_register(register)
        original_register_hash = _sha256(register)
        original_pdf_hash = _sha256(permit)

        server = create_server("127.0.0.1", 0, import_run)
        port = int(server.server_address[1])
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, health, instance = _request(port, "GET", "/health")
            if status != 200 or health.get("status") != "ok" or instance != project_instance_id():
                raise RuntimeError("server health identity mismatch")

            status, started, _ = _request(port, "POST", "/api/jobs", {"pdf_dir": str(pdf_dir), "xlsx": str(register), "dpi": 180})
            if status != 202 or not isinstance(started.get("id"), str):
                raise RuntimeError("first synthetic job was not accepted")
            first = _wait_for_job(port, str(started["id"]))
            if first.get("status") != "done":
                raise RuntimeError(f"first synthetic job failed: {first.get('error')}")
            if _sha256(permit) != original_pdf_hash:
                raise RuntimeError("source PDF hash changed during publication")
            first_hash = _sha256(register)
            first_mtime = register.stat().st_mtime_ns
            report = register.with_name(f"{register.stem} — отчет PropExtract.json")
            first_report = json.loads(report.read_text(encoding="utf-8"))
            if first_report.get("input_hashes") != {
                "xlsx": original_register_hash,
                "pdfs": {permit.name: original_pdf_hash},
            }:
                raise RuntimeError("first publication did not preserve its source hashes")
            backups = register.parent / "Резервные копии PropExtract"
            first_backups = sorted(item.name for item in backups.glob("*.xlsx")) if backups.is_dir() else []
            if not first_backups:
                raise RuntimeError("published XLSX did not create a verified backup")

            status, started, _ = _request(port, "POST", "/api/jobs", {"pdf_dir": str(pdf_dir), "xlsx": str(register), "dpi": 180})
            if status != 202 or not isinstance(started.get("id"), str):
                raise RuntimeError("second synthetic job was not accepted")
            second = _wait_for_job(port, str(started["id"]))
            if second.get("status") != "done":
                raise RuntimeError(f"second synthetic job failed: {second.get('error')}")
            if _sha256(register) != first_hash or register.stat().st_mtime_ns != first_mtime:
                raise RuntimeError("identical no-op changed XLSX bytes or mtime")
            second_report = json.loads(report.read_text(encoding="utf-8"))
            if second_report.get("input_hashes") != {
                "xlsx": first_hash,
                "pdfs": {permit.name: original_pdf_hash},
            }:
                raise RuntimeError("no-op did not preserve its source hashes")
            second_backups = sorted(item.name for item in backups.glob("*.xlsx")) if backups.is_dir() else []
            if second_backups != first_backups:
                raise RuntimeError("identical no-op created another Excel backup")
            if _sha256(permit) != original_pdf_hash:
                raise RuntimeError("source PDF hash changed during no-op")
            return {
                "status": "ok",
                "portable_python": str(Path(sys.executable).resolve()),
                "unicode_fixture": temporary.name,
                "first_backup_count": len(first_backups),
                "no_op_backup_count": len(second_backups),
                "runtime_commands": runtime["commands"],
            }
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=10)
            if thread.is_alive():
                raise RuntimeError("synthetic server did not stop")


def self_test() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="propextract-e2e-self-test-") as temporary_name:
        fixture = Path(temporary_name) / "fixture.pdf"
        _write_text_pdf(fixture, [PERMIT_NUMBER, "1.1: 01.02.2026"])
        payload = fixture.read_bytes()
        if not payload.startswith(b"%PDF-1.4\n") or b"xref\n0 6\n" not in payload or not payload.endswith(b"%%EOF\n"):
            raise RuntimeError("synthetic PDF structure is invalid")
        return {"status": "ok", "fixture_sha256": _sha256(fixture), "temporary_fixture_deleted": True}


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline Windows portable-runtime smoke")
    parser.add_argument("--self-test", action="store_true", help="validate the dependency-free fixture generator only")
    options = parser.parse_args()
    result = self_test() if options.self_test else run()
    # Windows PowerShell 5.1 can give a redirected portable Python process a
    # legacy console encoding. JSON escapes keep the complete Unicode payload
    # representable without depending on that code page.
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
