"""Process-isolated, fail-closed Windows Excel native insertion adapter."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import subprocess
import threading
import time
from typing import Any, Protocol

from rns_import_server.excel_process_authority import ExcelProcessAuthorityError, ExcelProcessLease, ProcessIdentity, verify_excel_process_lease
from rns_import_server.excel_process_cleanup import ExcelProcessCleanupError, ProcessMissingError, cleanup_excel_process

_LOG_LIMIT = 64 * 1024
_CANCEL_GRACE = 8.0
_LEASE_KEYS = frozenset({"operation_id", "owner_id", "pair_nonce", "adapter_type", "adapter_image", "adapter_pid", "adapter_started_at", "excel_image", "excel_pid", "excel_hwnd", "excel_process_started_at", "excel_build"})


class NativeExcelError(RuntimeError):
    """Typed pre-publication failure; public callers expose only code and stage."""
    def __init__(self, code: str, *, stage: str, cause: BaseException | None = None, cleanup: BaseException | None = None, durable_phase: str = "staged"):
        self.code, self.stage, self.cause = code, stage, cause
        self.cleanup, self.durable_phase = cleanup, durable_phase
        super().__init__(f"{code}@{stage}")


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


class _Journal(Protocol):
    def transition(self, operation_id: str, *, expected_phase: str, next_phase: str, **kwargs: object) -> object: ...


class _WindowsInspector:
    """OS observations used only after a frozen prelaunch Excel snapshot."""
    def __init__(self, snapshot: frozenset[int]): self._snapshot = snapshot
    def prelaunch_excel_pids(self) -> frozenset[int]: return self._snapshot

    @staticmethod
    def _powershell(expression: str) -> dict[str, Any]:
        completed = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", expression], capture_output=True, text=True, timeout=10, check=False)
        if completed.returncode: raise RuntimeError("process probe failed")
        value = json.loads(completed.stdout)
        if not isinstance(value, dict): raise TypeError("process probe")
        return value

    def process_identity(self, pid: int) -> ProcessIdentity:
        value = self._powershell("$p=Get-Process -Id %d -ErrorAction SilentlyContinue; if ($null -eq $p) { @{found=$false}|ConvertTo-Json -Compress } else { @{found=$true;pid=[int]$p.Id;image=([string]$p.ProcessName);started_at=$p.StartTime.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')}|ConvertTo-Json -Compress }" % pid)
        if value.get("found") is False: raise ProcessMissingError()
        if value.get("found") is not True: raise TypeError("process presence")
        return ProcessIdentity(value["pid"], _canonical_windows_image(value["image"]), value["started_at"])

    def hwnd_process_id(self, hwnd: int) -> int:
        import ctypes
        result = ctypes.c_ulong()
        if not ctypes.windll.user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(result)): raise RuntimeError("HWND unavailable")
        return int(result.value)

    def terminate_process(self, pid: int) -> None:
        completed = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "Stop-Process -Id %d -ErrorAction Stop" % pid], capture_output=True, text=True, timeout=10, check=False)
        if completed.returncode: raise RuntimeError("process termination failed")

    def wait_for_process_exit(self, pid: int, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try: self.process_identity(pid)
            except ProcessMissingError: return True
            time.sleep(0.05)
        return False


def native_excel_available() -> bool:
    return os.name == "nt" and bool(os.environ.get("ProgramFiles"))


def _canonical_windows_image(value: object) -> str:
    """Normalize runtime ProcessName values at the observation boundary."""
    if type(value) is not str or not value: raise TypeError("process image")
    name = value[:-4] if value.lower().endswith(".exe") else value
    if not name or any(character in "\\/\x00" for character in name): raise TypeError("process image")
    return "EXCEL.EXE" if name.lower() == "excel" else name.lower() + ".exe"


def _snapshot_excel_pids() -> frozenset[int]:
    try:
        completed = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "@(Get-Process -Name EXCEL -ErrorAction SilentlyContinue|ForEach-Object {[int]$_.Id})|ConvertTo-Json -Compress"], capture_output=True, text=True, timeout=10, check=False)
        if completed.returncode: raise RuntimeError("snapshot failed")
        value = json.loads(completed.stdout or "[]")
        values = value if isinstance(value, list) else [value]
        if any(type(pid) is not int or pid <= 0 for pid in values): raise TypeError("snapshot")
        return frozenset(values)
    except Exception as error:
        raise NativeExcelError("excel_lease_snapshot_unavailable", stage="lease", cause=error) from error


def _fsync_write(path: Path, value: bytes, *, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(value); stream.flush(); os.fsync(stream.fileno())
    finally: os.close(descriptor)


def _verify_private_windows_acl(path: Path) -> None:
    """Install then verify a protected DACL containing only the current SID."""
    if os.name != "nt": return
    command = (
        "$p=$args[0];$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User;"
        "$acl=Get-Acl -LiteralPath $p;$acl.SetAccessRuleProtection($true,$false);"
        "foreach($r in @($acl.Access)){$acl.RemoveAccessRuleAll($r)|Out-Null};"
        "$inherit=if((Get-Item -LiteralPath $p).PSIsContainer){[Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit'}else{[Security.AccessControl.InheritanceFlags]::None};"
        "$rule=New-Object Security.AccessControl.FileSystemAccessRule($sid,[Security.AccessControl.FileSystemRights]::FullControl,$inherit,[Security.AccessControl.PropagationFlags]::None,[Security.AccessControl.AccessControlType]::Allow);"
        "$acl.AddAccessRule($rule);Set-Acl -LiteralPath $p -AclObject $acl;$actual=Get-Acl -LiteralPath $p;"
        "$rules=@($actual.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]));"
        "if(-not $actual.AreAccessRulesProtected -or $rules.Count -ne 1 -or $rules[0].IdentityReference.Value -ne $sid.Value -or $rules[0].AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow -or (($rules[0].FileSystemRights -band [Security.AccessControl.FileSystemRights]::FullControl) -ne [Security.AccessControl.FileSystemRights]::FullControl)){exit 19}"
    )
    completed = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command, str(path)], capture_output=True, text=True, timeout=10, check=False)
    if completed.returncode: raise RuntimeError("current-user DACL verification failed")


def _private_logs(request: NativeInsertRequest) -> tuple[Path, Path]:
    try:
        directory = request.lease_file.parent / "native-private-logs"
        directory.mkdir(mode=0o700, parents=False, exist_ok=False); os.chmod(directory, 0o700)
        stdout, stderr = directory / "stdout.log", directory / "stderr.log"
        _fsync_write(stdout, b""); _fsync_write(stderr, b"")
        for path in (directory, stdout, stderr): _verify_private_windows_acl(path)
        return stdout, stderr
    except Exception as error:
        raise NativeExcelError("technical_log_unavailable", stage="launch", cause=error) from error


def _append_capped(path: Path, data: bytes, state: dict[str, object]) -> None:
    kept = int(state["kept"]); remaining = max(0, _LOG_LIMIT - kept); piece = data[:remaining]
    if len(data) > remaining: state["truncated"] = True
    if piece:
        with path.open("ab") as stream:
            stream.write(piece); stream.flush(); os.fsync(stream.fileno())
        state["kept"] = kept + len(piece)


def _drain(stream: Any, path: Path, state: dict[str, object]) -> None:
    while True:
        chunk = stream.read(4096)
        if not chunk: return
        _append_capped(path, chunk, state)


def _record_log_limit(path: Path, state: dict[str, object]) -> None:
    """Keep truncation evidence private and durable without growing the stream."""
    metadata = path.with_suffix(path.suffix + ".meta.json")
    temporary = metadata.with_name(metadata.name + ".tmp")
    _fsync_write(temporary, json.dumps({"bytes_retained": int(state["kept"]), "truncated": bool(state["truncated"])}, separators=(",", ":")).encode("utf-8"))
    os.replace(temporary, metadata)
    with metadata.open("rb") as stream: os.fsync(stream.fileno())


def _read_lease(request: NativeInsertRequest, timeout: float) -> ExcelProcessLease:
    deadline = time.monotonic() + min(timeout, 20.0)
    while time.monotonic() < deadline:
        try:
            raw = request.lease_file.read_bytes()
            if raw.startswith(b"\xef\xbb\xbf"): raise NativeExcelError("excel_lease_invalid", stage="lease")
            value = json.loads(raw.decode("utf-8"))
            if not isinstance(value, dict) or frozenset(value) != _LEASE_KEYS: raise NativeExcelError("excel_lease_invalid", stage="lease")
            lease = ExcelProcessLease(**value)
            if (lease.operation_id, lease.owner_id, lease.pair_nonce) != (request.operation_id, request.owner_nonce, request.pair_nonce): raise NativeExcelError("excel_lease_invalid", stage="lease")
            return lease
        except FileNotFoundError: time.sleep(0.05)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ExcelProcessAuthorityError) as error:
            raise NativeExcelError("excel_lease_invalid", stage="lease", cause=error) from error
    raise NativeExcelError("excel_lease_timeout", stage="lease")


def _audit_ack(request: NativeInsertRequest) -> None:
    try:
        temporary = request.ack_file.with_name(request.ack_file.name + ".tmp")
        payload = json.dumps({"operation_id": request.operation_id, "owner_id": request.owner_nonce, "pair_nonce": request.pair_nonce}, separators=(",", ":")).encode("utf-8")
        _fsync_write(temporary, payload); os.replace(temporary, request.ack_file)
        with request.ack_file.open("rb") as stream: os.fsync(stream.fileno())
    except Exception as error:
        raise NativeExcelError("excel_lease_ack_failed", stage="ack", cause=error, durable_phase="native") from error


def _send(process: subprocess.Popen[bytes], command: str) -> None:
    if process.stdin is None: raise RuntimeError("adapter stdin unavailable")
    process.stdin.write((json.dumps({"command": command}) + "\n").encode("utf-8")); process.stdin.flush()


def _validate_native_inputs(request: object, script: object, timeout: object) -> NativeInsertRequest:
    """Reject malformed built-ins before a directory, snapshot, or child exists."""
    if type(request) is not NativeInsertRequest:
        raise NativeExcelError("native_request_invalid", stage="pre_open")
    if any(type(value) is not str or not value for value in (request.operation_id, request.owner_nonce, request.pair_nonce, request.sheet)):
        raise NativeExcelError("native_request_invalid", stage="pre_open")
    if type(request.fields) is not dict or type(request.hyperlink) not in {str, type(None)}:
        raise NativeExcelError("native_request_invalid", stage="pre_open")
    if type(request.mutation_mode) is not str or request.mutation_mode not in {"middle_insert", "blank_fill"}:
        raise NativeExcelError("native_mutation_mode_invalid", stage="pre_open")
    if type(request.insertion_row) is not int or request.insertion_row < 1:
        raise NativeExcelError("native_insert_row_invalid", stage="pre_open")
    if type(timeout) not in {int, float} or not math.isfinite(float(timeout)) or timeout <= 0:
        raise NativeExcelError("native_timeout_invalid", stage="pre_open")
    builtin_path = type(Path("."))
    if type(script) is not builtin_path or any(type(value) is not builtin_path for value in (request.control, request.candidate, request.lease_file, request.ack_file)):
        raise NativeExcelError("native_path_invalid", stage="pre_open")
    return request


def run_native_insert(request: NativeInsertRequest, script: Path, journal: _Journal, timeout: float = 120.0) -> dict[str, Any]:
    """Launch the only publisher; durable native permission precedes ``open``."""
    request = _validate_native_inputs(request, script, timeout)
    if not native_excel_available(): raise NativeExcelError("excel_required_for_middle_insert", stage="pre_open")
    snapshot = _snapshot_excel_pids()
    request.lease_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(request.lease_file.parent, 0o700)
        request_file = request.lease_file.with_name("excel-request.json")
        _fsync_write(request_file, json.dumps(request.payload(), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        stdout_log, stderr_log = _private_logs(request)
    except NativeExcelError: raise
    except Exception as error: raise NativeExcelError("technical_log_unavailable", stage="launch", cause=error) from error
    process: subprocess.Popen[bytes] | None = None; lease: ExcelProcessLease | None = None; primary: NativeExcelError | None = None; native_committed = False
    streams: dict[str, dict[str, object]] = {"stdout": {"kept": 0, "truncated": False}, "stderr": {"kept": 0, "truncated": False}}
    try:
        process = subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Request", str(request_file)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert process.stdout is not None and process.stderr is not None
        readers = [threading.Thread(target=_drain, args=(process.stdout, stdout_log, streams["stdout"]), daemon=True), threading.Thread(target=_drain, args=(process.stderr, stderr_log, streams["stderr"]), daemon=True)]
        for reader in readers: reader.start()
        lease = _read_lease(request, timeout); inspector = _WindowsInspector(snapshot)
        try: verify_excel_process_lease(lease, launched_adapter_pid=process.pid, inspector=inspector)
        except ExcelProcessAuthorityError as error: raise NativeExcelError(error.code, stage="lease", cause=error) from error
        try: journal.transition(request.operation_id, expected_phase="staged", next_phase="native", excel_lease=lease)
        except Exception as error: raise NativeExcelError("excel_native_journal_cas_failed", stage="journal", cause=error) from error
        native_committed = True
        _audit_ack(request); _send(process, "open")
        deadline = time.monotonic() + timeout
        while process.poll() is None and time.monotonic() < deadline: time.sleep(0.05)
        if process.poll() is None:
            _send(process, "cancel")
            try: process.wait(timeout=_CANCEL_GRACE)
            except subprocess.TimeoutExpired as error: raise NativeExcelError("excel_timeout", stage="adapter", cause=error, durable_phase="native") from error
        for reader in readers: reader.join(timeout=8.0)
        if any(reader.is_alive() for reader in readers): raise NativeExcelError("excel_adapter_stream_drain_failed", stage="adapter", durable_phase="native")
        try:
            _record_log_limit(stdout_log, streams["stdout"])
            _record_log_limit(stderr_log, streams["stderr"])
        except Exception as error:
            raise NativeExcelError("technical_log_unavailable", stage="adapter", cause=error, durable_phase="native") from error
        stdout = stdout_log.read_bytes()
        if process.returncode: raise NativeExcelError("excel_native_failed", stage="adapter", durable_phase="native")
        try: result = json.loads(stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error: raise NativeExcelError("excel_adapter_protocol_invalid", stage="adapter", cause=error, durable_phase="native") from error
        if not isinstance(result, dict) or result.get("status") != "ok": raise NativeExcelError("excel_adapter_protocol_invalid", stage="adapter", durable_phase="native")
        if any(bool(item["truncated"]) for item in streams.values()): raise NativeExcelError("excel_adapter_stream_truncated", stage="adapter", durable_phase="native")
        result["durable_phase"] = "native"
        return result
    except NativeExcelError as error:
        primary = error; raise
    except OSError as error:
        primary = NativeExcelError("excel_adapter_launch_failed" if not native_committed else "excel_adapter_io_failed", stage="adapter", cause=error, durable_phase="native" if native_committed else "staged"); raise primary from error
    except Exception as error:
        primary = NativeExcelError("excel_adapter_io_failed", stage="adapter", cause=error, durable_phase="native" if native_committed else "staged"); raise primary from error
    finally:
        cleanup_error: ExcelProcessCleanupError | None = None
        if lease is not None and process is not None and process.poll() is None:
            # A rejected CAS/ACK or any primary failure never grants open.  The
            # live stdin control remains the cancellation channel through the
            # same bounded helper grace period used for timeout.
            try:
                _send(process, "cancel")
                process.wait(timeout=_CANCEL_GRACE)
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                pass
        if lease is not None:
            try: cleanup_excel_process(lease, prelaunch_excel_pids=snapshot, inspector=_WindowsInspector(snapshot))
            except ExcelProcessCleanupError as error: cleanup_error = error
        if primary is not None and cleanup_error is not None: primary.cleanup = cleanup_error
        elif cleanup_error is not None: raise NativeExcelError(cleanup_error.code, stage="cleanup", cause=cleanup_error, durable_phase="native")
