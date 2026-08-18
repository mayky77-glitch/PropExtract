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
from typing import Any, Callable, Mapping


class NativeExcelError(RuntimeError):
    """Typed pre-publication failure; its ``code`` is stable for recovery UI."""

    def __init__(self, code: str, *, stage: str, cause: BaseException | None = None, cleanup: BaseException | None = None):
        self.code, self.stage, self.cause, self.cleanup = code, stage, cause, cleanup
        detail = f": {cause}" if cause else ""
        if cleanup: detail += f"; cleanup: {cleanup}"
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
    template_formula_r1c1: Mapping[int, str] | None = None
    sheet_token: str = ""
    source_row: int = 0
    template_row: int = 0
    group_end: int = 0
    ordinal_base: int = 0

    def payload(self) -> dict[str, Any]:
        value = asdict(self)
        return {key: str(item) if isinstance(item, Path) else item for key, item in value.items()}


def native_excel_available() -> bool:
    return os.name == "nt" and bool(os.environ.get("ProgramFiles"))


_ALLOWLISTED = frozenset(range(1, 25)) | {27}


def validate_request(request: NativeInsertRequest) -> None:
    """Reject unsafe COM requests before a helper or workbook exists."""
    if (request.insertion_row < 4 or not isinstance(request.sheet, str) or not request.sheet.strip()
            or request.sheet_token != request.sheet or request.source_row < 1 or request.template_row < 1
            or request.group_end < request.insertion_row or request.ordinal_base < 0):
        raise NativeExcelError("native_insert_request_invalid", stage="pre_open")
    if any(not isinstance(column, int) or column not in _ALLOWLISTED for column in request.fields):
        raise NativeExcelError("native_field_not_allowlisted", stage="pre_open")
    if request.hyperlink is not None and (not isinstance(request.hyperlink, str) or not request.hyperlink.startswith(("file:", "https:"))):
        raise NativeExcelError("native_hyperlink_invalid", stage="pre_open")
    formulas = request.template_formula_r1c1 or {}
    if set(formulas) != {25, 26} or any(not isinstance(value, str) or not value.startswith("=") for value in formulas.values()):
        raise NativeExcelError("native_template_formula_invalid", stage="pre_open")


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
        stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)


def _lease_from_file(request: NativeInsertRequest, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + min(timeout, 20.0)
    while time.monotonic() < deadline:
        try:
            value = json.loads(request.lease_file.read_text(encoding="utf-8-sig"))
            if (value.get("operation_id"), value.get("owner_nonce"), value.get("pair_nonce")) == (request.operation_id, request.owner_nonce, request.pair_nonce):
                required = {"excel_adapter", "adapter_pid", "adapter_started_at", "excel_pid", "excel_hwnd", "excel_process_started_at", "excel_image", "excel_build"}
                if required <= value.keys(): return value
            raise NativeExcelError("excel_lease_invalid", stage="lease")
        except FileNotFoundError:
            time.sleep(0.05)
    raise NativeExcelError("excel_lease_timeout", stage="lease")


def validate_lease(lease: Mapping[str, Any], request: NativeInsertRequest, *, process_probe: Callable[[int], Mapping[str, Any]] | None = None) -> None:
    """Validate current ownership, not merely a PID observed before launch."""
    if lease.get("excel_adapter") != "com" or str(lease.get("excel_image", "")).upper() != "EXCEL.EXE":
        raise NativeExcelError("excel_lease_identity_invalid", stage="lease")
    if not all(isinstance(lease.get(name), int) and lease[name] > 0 for name in ("adapter_pid", "excel_pid", "excel_hwnd")):
        raise NativeExcelError("excel_lease_identity_invalid", stage="lease")
    if process_probe:
        observed = process_probe(int(lease["excel_pid"]))
        if (str(observed.get("image", "")).upper() != "EXCEL.EXE" or observed.get("started_at") != lease.get("excel_process_started_at")
                or observed.get("hwnd") != lease.get("excel_hwnd")):
            raise NativeExcelError("excel_lease_process_mismatch", stage="lease")


def cleanup_lease(request: NativeInsertRequest, *, process_probe: Callable[[int], Mapping[str, Any]], terminate: Callable[[int], None]) -> None:
    """Terminate only the still nonce-bound Excel process; never a user PID."""
    try:
        lease = json.loads(request.lease_file.read_text(encoding="utf-8-sig"))
        if (lease.get("operation_id"), lease.get("owner_nonce"), lease.get("pair_nonce")) != (request.operation_id, request.owner_nonce, request.pair_nonce): return
        validate_lease(lease, request, process_probe=process_probe)
        terminate(int(lease["excel_pid"]))
    except (FileNotFoundError, NativeExcelError):
        return


def run_native_insert(request: NativeInsertRequest, *, script: Path, timeout: float = 120.0,
                      lease_recorder: Callable[[Mapping[str, Any]], None] | None = None,
                      process_probe: Callable[[int], Mapping[str, Any]] | None = None,
                      terminate: Callable[[int], None] | None = None) -> dict[str, Any]:
    """Run exactly the native helper or fail before either staged file changes."""
    if lease_recorder is None or process_probe is None:
        raise NativeExcelError("excel_concrete_lease_authority_required", stage="authorize")
    if not native_excel_available():
        raise NativeExcelError("excel_required_for_middle_insert", stage="pre_open")
    validate_request(request)
    request.lease_file.parent.mkdir(parents=True, exist_ok=True)
    request_file = request.lease_file.with_name("excel-request.json")
    _atomic_json(request_file, request.payload())
    process = None
    primary: BaseException | None = None
    try:
        process = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Request", str(request_file)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        lease = _lease_from_file(request, timeout); validate_lease(lease, request, process_probe=process_probe)
        adapter = process_probe(process.pid)
        if (adapter.get("started_at") != lease.get("adapter_started_at") or str(adapter.get("image", "")).upper() not in {"POWERSHELL.EXE", "PWSH.EXE"}):
            raise NativeExcelError("excel_adapter_process_mismatch", stage="lease")
        lease_recorder(lease)
        _atomic_json(request.ack_file, {"operation_id": request.operation_id, "owner_nonce": request.owner_nonce, "pair_nonce": request.pair_nonce})
        stdout, stderr = process.communicate(timeout=timeout)
    except BaseException as error:
        primary = error
        cleanup = None
        try:
            if process and terminate: cleanup_lease(request, process_probe=process_probe, terminate=terminate)
            if process: process.kill(); process.communicate(timeout=5)
        except BaseException as cleanup_error: cleanup = cleanup_error
        if isinstance(error, NativeExcelError): raise NativeExcelError(error.code, stage=error.stage, cause=error.cause or error, cleanup=cleanup) from error
        code = "excel_timeout" if isinstance(error, subprocess.TimeoutExpired) else "excel_adapter_failed"
        raise NativeExcelError(code, stage="adapter", cause=error, cleanup=cleanup) from error
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
