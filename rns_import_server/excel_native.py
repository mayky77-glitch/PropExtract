"""Strict Windows Excel adapter contract for middle-row insertion.

The adapter deliberately has no OpenPyXL or OOXML fallback.  It only creates a
request for the audited PowerShell helper, so callers can test the safe
negative path on every platform.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any


class NativeExcelError(RuntimeError):
    """Typed pre-publication failure; its ``code`` is stable for recovery UI."""

    def __init__(self, code: str, *, stage: str, cause: BaseException | None = None):
        self.code, self.stage, self.cause = code, stage, cause
        detail = f": {cause}" if cause else ""
        super().__init__(f"{code}@{stage}{detail}")


@dataclass(frozen=True)
class ExcelLease:
    operation_id: str
    owner_nonce: str
    pair_nonce: str
    adapter_pid: int
    adapter_started_at: str
    excel_pid: int
    excel_hwnd: int
    excel_process_started_at: str
    excel_build: str


@dataclass(frozen=True)
class NativeInsertRequest:
    operation_id: str
    owner_nonce: str
    pair_nonce: str
    control: Path
    candidate: Path
    insertion_row: int
    lease_file: Path
    ack_file: Path
    sheet: str
    fields: dict[int, object]
    hyperlink: str | None
    mutation_mode: str

    def payload(self) -> dict[str, Any]:
        value = asdict(self)
        return {key: str(item) if isinstance(item, Path) else item for key, item in value.items()}


def native_excel_available() -> bool:
    return os.name == "nt" and bool(os.environ.get("ProgramFiles"))


def _lease_from_file(request: NativeInsertRequest, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + min(timeout, 20.0)
    while time.monotonic() < deadline:
        try:
            value = json.loads(request.lease_file.read_text(encoding="utf-8"))
            if (value.get("operation_id"), value.get("owner_nonce"), value.get("pair_nonce")) == (request.operation_id, request.owner_nonce, request.pair_nonce):
                required = {"excel_adapter", "excel_pid", "excel_hwnd", "excel_process_started_at", "excel_build"}
                if required <= value.keys(): return value
            raise NativeExcelError("excel_lease_invalid", stage="lease")
        except FileNotFoundError:
            time.sleep(0.05)
    raise NativeExcelError("excel_lease_timeout", stage="lease")


def run_native_insert(request: NativeInsertRequest, *, script: Path, timeout: float = 120.0) -> dict[str, Any]:
    """Run exactly the native helper or fail before either staged file changes."""
    if not isinstance(request.mutation_mode, str) or request.mutation_mode not in {"middle_insert", "blank_fill"}:
        raise NativeExcelError("native_mutation_mode_invalid", stage="pre_open")
    if not native_excel_available():
        raise NativeExcelError("excel_required_for_middle_insert", stage="pre_open")
    if request.insertion_row < 1:
        raise NativeExcelError("native_insert_row_invalid", stage="pre_open")
    request.lease_file.parent.mkdir(parents=True, exist_ok=True)
    request_file = request.lease_file.with_name("excel-request.json")
    request_file.write_text(json.dumps(request.payload(), ensure_ascii=False), encoding="utf-8")
    try:
        process = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Request", str(request_file)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        lease = _lease_from_file(request, timeout)
        request.ack_file.write_text(json.dumps({"operation_id": request.operation_id, "owner_nonce": request.owner_nonce, "pair_nonce": request.pair_nonce}), encoding="utf-8")
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        process.kill()
        raise NativeExcelError("excel_timeout", stage="adapter", cause=error) from error
    except OSError as error:
        raise NativeExcelError("excel_adapter_launch_failed", stage="adapter", cause=error) from error
    if process.returncode:
        raise NativeExcelError("excel_native_failed", stage="adapter", cause=RuntimeError(stderr.strip() or stdout.strip()))
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise NativeExcelError("excel_adapter_protocol_invalid", stage="adapter", cause=error) from error
    if not isinstance(result, dict) or result.get("status") != "ok":
        raise NativeExcelError("excel_adapter_protocol_invalid", stage="adapter")
    result["lease"] = lease
    return result
