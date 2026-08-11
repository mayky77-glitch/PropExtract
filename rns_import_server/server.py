"""Loopback-only admin server with background import jobs."""
from __future__ import annotations

import json
import errno
import hashlib
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlparse

try:
    from rns_import_server.audit import atomic_json, sha256
    from rns_import_server.workbook import apply_proposal, iso_date
    from rns_import_server.files import discover_pdfs
    from rns_import_server.runtime import runtime_status
except ModuleNotFoundError:
    from audit import atomic_json, sha256
    from workbook import apply_proposal, iso_date
    from files import discover_pdfs
    from runtime import runtime_status

Runner = Callable[..., dict]
MAX_BODY = 64 * 1024
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_INSTANCE_ID = re.compile(r"^[0-9a-f]{64}$")
STATIC = Path(__file__).with_name("static")
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/help": ("help.html", "text/html; charset=utf-8"),
    "/assets/app.css": ("app.css", "text/css; charset=utf-8"),
    "/assets/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/assets/logo.png": ("logo.png", "image/png"),
    "/favicon.png": ("logo.png", "image/png"),
}
PICKER_LOCK = threading.Lock()
ERROR_LOG = Path(__file__).resolve().parents[1] / "propextract-error.log"


def select_path(kind: str) -> str | None:
    """Open a native picker without running Tk on an HTTP worker thread."""
    if kind not in {"directory", "xlsx"}:
        raise ValueError("Неизвестный тип окна выбора")
    if not PICKER_LOCK.acquire(blocking=False):
        raise BusyError("Окно выбора уже открыто")
    try:
        try:
            result = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("picker.py")), kind],
                capture_output=True,
                text=True,
                check=False,
                timeout=150,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("Окно выбора не ответило за 2 минуты. Закройте скрытое окно в панели задач и повторите попытку.") from error
        if result.returncode:
            detail = result.stderr.strip()
            if "tkinter_unavailable" in detail:
                raise RuntimeError("Системное окно недоступно: установите Tkinter")
            if "windows_picker_timeout" in detail:
                raise RuntimeError("Окно выбора не ответило за 2 минуты. Проверьте панель задач Windows и повторите попытку.")
            if "windows_powershell_unavailable" in detail:
                raise RuntimeError("Не найден системный Windows PowerShell для открытия окна выбора.")
            if "windows_picker_failed" in detail:
                raise RuntimeError("Windows не смог открыть окно выбора. Вставьте путь вручную или перезапустите PropExtract.")
            raise RuntimeError(detail or "Не удалось открыть системное окно")
        selected = result.stdout.strip()
        return selected or None
    finally:
        PICKER_LOCK.release()


def _tool_status() -> dict[str, object]:
    return runtime_status()


def user_path(value: str) -> Path:
    """Normalize paths pasted from Explorer without changing valid filename characters."""
    text = value.strip()
    for opening, closing in (("\"", "\""), ("“", "”"), ("«", "»")):
        if len(text) >= 2 and text.startswith(opening) and text.endswith(closing):
            text = text[len(opening) : -len(closing)].strip()
            break
    if text.lower().startswith("file://"):
        parsed = urlparse(text)
        decoded = unquote(parsed.path)
        if os.name == "nt":
            if parsed.netloc:
                decoded = f"//{parsed.netloc}{decoded}"
            elif len(decoded) >= 3 and decoded[0] == "/" and decoded[2] == ":":
                decoded = decoded[1:]
        text = decoded
    return Path(os.path.expandvars(os.path.expanduser(text)))


def validated_job_paths(pdf_dir: str, xlsx: str) -> tuple[Path, Path]:
    if not pdf_dir.strip() or not xlsx.strip():
        raise ValueError("Укажите папку с PDF и целевой файл Excel")
    pdf_path, xlsx_path = user_path(pdf_dir), user_path(xlsx)
    if pdf_path.is_symlink():
        raise ValueError("Папка с PDF не должна быть символической ссылкой")
    if not pdf_path.exists():
        raise ValueError(f"Папка с PDF не найдена: {pdf_path}")
    if pdf_path.is_file():
        raise ValueError(f"В поле «Папка с PDF» указан файл: {pdf_path}. Укажите папку, в которой лежат PDF.")
    if not pdf_path.is_dir():
        raise ValueError(f"Путь к PDF не является папкой: {pdf_path}")
    if not discover_pdfs(pdf_path):
        raise ValueError(f"В папке не найдено PDF: {pdf_path}")
    if xlsx_path.is_symlink():
        raise ValueError("Файл Excel не должен быть символической ссылкой")
    if not xlsx_path.exists():
        raise ValueError(f"Файл Excel не найден: {xlsx_path}")
    if xlsx_path.is_dir():
        raise ValueError(f"Указана папка вместо файла Excel: {xlsx_path}")
    if not xlsx_path.is_file() or xlsx_path.suffix.lower() != ".xlsx":
        raise ValueError(f"Нужен существующий файл Excel с расширением .xlsx: {xlsx_path}")
    return pdf_path, xlsx_path


class BusyError(RuntimeError):
    pass


def error_hint(error: Exception) -> str:
    """Return an actionable hint without assuming that Excel is open."""
    message = str(error).lower()
    lock_markers = (
        "permission denied",
        "access is denied",
        "used by another process",
        "winerror 5",
        "winerror 32",
    )
    if isinstance(error, PermissionError) or any(marker in message for marker in lock_markers):
        return "Система запретила запись в файл. Проверьте права доступа, Excel, Проводник и защитное ПО."
    if "expected str instance, nonetype found" in message:
        return "Обнаружено пустое значение при разборе PDF или Excel. Установите последнюю версию PropExtract и повторите запуск."
    return "Исправьте указанную причину и повторите запуск. Исходный Excel не изменён."


def public_error(error: Exception) -> tuple[str, str]:
    """Translate all public failures; preserve diagnostics only in the local log."""
    code = str(error)
    if "native_conditional_formatting" in code:
        return (
            "Не удалось сохранить исходные правила цветовой подсветки Excel. Реестр не изменён.",
            "Обновите PropExtract и повторите перенос. Если ошибка повторится, передайте разработчику технический журнал.",
        )
    if "proposal_" in code or "source_inputs_changed" in code or "Целевой Excel изменился" in code:
        return ("Данные изменились после запуска. Реестр не изменён.", "Запустите проверку заново и подтвердите изменение ещё раз.")
    if isinstance(error, BusyError):
        return (str(error), "Дождитесь завершения текущей операции.")
    if isinstance(error, (ValueError, TypeError)):
        return ("Проверьте папку с PDF, файл Excel и параметры операции.", "Исправьте данные и повторите действие.")
    if isinstance(error, PermissionError):
        return ("Не удалось получить доступ к файлу.", error_hint(error))
    return ("Не удалось завершить операцию. Реестр не изменён.", error_hint(error))


def _display_filename(value: object) -> str | None:
    """Return a filename suitable for the operator UI, never a local path."""
    if value in (None, ""):
        return None
    return str(value).replace("\\", "/").rsplit("/", 1)[-1] or None


def _public_issue(value: object) -> str:
    """Keep internal diagnostic codes out of operator-facing row cards."""
    text = str(value or "").strip()
    if text == "no_transferable_evidence":
        return "В PDF недостаточно подтверждённых данных для переноса."
    if text and " " not in text and "_" in text:
        return "Строка требует ручной проверки."
    return text


def _capability_matches(expected: object, candidate: object) -> bool:
    """Compare opaque ASCII capabilities without leaking TypeError for Unicode input."""
    return (
        isinstance(candidate, str)
        and candidate.isascii()
        and secrets.compare_digest(str(expected), candidate)
    )


def project_instance_id(project_root: Path | None = None) -> str:
    """Return a stable opaque identifier for one local project copy.

    The source location intentionally affects the digest, so two unpacked
    copies sharing port 8775 cannot authorize each other's lifecycle actions.
    Only the digest is sent over HTTP; the path never leaves this process.
    """
    root = (project_root or Path(__file__).resolve().parents[1]).resolve()
    value = f"propextract-instance-v1\0{root}".encode("utf-8", "surrogateescape")
    return hashlib.sha256(value).hexdigest()


def retry_file_operation(
    operation: Callable[[], object],
    attempts: int = 20,
    deadline: float = 15.0,
    initial_delay: float = 0.2,
) -> object:
    """Retry transient Excel/share locks with both an attempt and time bound."""
    if attempts < 1:
        raise ValueError("attempts must be positive")
    if deadline < 0 or initial_delay < 0:
        raise ValueError("retry deadline and delay must not be negative")
    expires_at = time.monotonic() + deadline
    last_error: OSError | None = None
    for attempt in range(attempts):
        if last_error is not None and time.monotonic() >= expires_at:
            raise last_error
        try:
            return operation()
        except OSError as error:
            last_error = error
            transient = (
                isinstance(error, PermissionError)
                or error.errno in {errno.EACCES, errno.EBUSY, errno.EPERM, errno.ETXTBSY}
                or getattr(error, "winerror", None) in {5, 32, 33}
            )
            if not transient or attempt + 1 >= attempts:
                raise last_error
            remaining = expires_at - time.monotonic()
            if remaining <= 0:
                raise last_error
            time.sleep(min(1.0, initial_delay * (2**attempt), remaining))
    assert last_error is not None
    raise last_error


class JobManager:
    """Own one OCR job at a time and retain a small in-memory history."""

    def __init__(self, runner: Runner, history_limit: int = 20, error_log: Path = ERROR_LOG):
        self.runner = runner
        self.history_limit = history_limit
        self.error_log = error_log
        self._jobs: dict[str, dict[str, object]] = {}
        self._lock = threading.Lock()
        self._publish_lock = threading.Lock()

    def start(self, pdf_dir: str, xlsx: str, dpi: int = 180) -> dict[str, object]:
        pdf_path, xlsx_path = validated_job_paths(pdf_dir, xlsx)
        pdf_value, xlsx_value = str(pdf_path), str(xlsx_path)
        if dpi < 120 or dpi > 400:
            raise ValueError("DPI должен быть от 120 до 400")
        with self._lock:
            if any(job["status"] in {"queued", "running"} for job in self._jobs.values()):
                raise BusyError("Уже выполняется другой импорт")
            job_id = uuid.uuid4().hex
            now = datetime.now().isoformat(timespec="seconds")
            job: dict[str, object] = {
                "id": job_id,
                "status": "queued",
                "progress": 0,
                "stage": "В очереди",
                "current_file": None,
                "created_at": now,
                "updated_at": now,
                "pdf_dir": pdf_value,
                "xlsx": xlsx_value,
                "capability": secrets.token_urlsafe(32),
            }
            self._jobs[job_id] = job
            self._trim_locked()
        threading.Thread(target=self._execute, args=(job_id, pdf_path, xlsx_path, dpi), daemon=True).start()
        return self.get(job_id) or {}

    def get(self, job_id: str) -> dict[str, object] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def public(self, job_id: str) -> dict[str, object] | None:
        job = self.get(job_id)
        if not job:
            return None
        hidden = {"pdf_dir", "xlsx", "backup", "report", "error_log", "documents_internal", "target_hash", "pdf_hashes", "proposals_internal"}
        value = {key: item for key, item in job.items() if key not in hidden}
        for key in ("current_file", "error_file"):
            if key in value:
                value[key] = _display_filename(value[key])
        # Capability is an opaque per-job authorization value, not a filesystem path.
        return value

    def has_active_job(self) -> bool:
        with self._lock:
            return any(job["status"] in {"queued", "running"} for job in self._jobs.values())

    def _trim_locked(self) -> None:
        finished = [key for key, job in self._jobs.items() if job["status"] in {"done", "error"}]
        for key in finished[: max(0, len(self._jobs) - self.history_limit)]:
            self._jobs.pop(key, None)

    def _update(self, job_id: str, **values: object) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if "progress" in values:
                values["progress"] = max(int(job["progress"]), min(100, int(values["progress"])))
            values["updated_at"] = datetime.now().isoformat(timespec="seconds")
            job.update(values)

    def _write_error_log(self, job_id: str, error: Exception, job: dict[str, object]) -> str | None:
        details = (
            f"PropExtract error {datetime.now().isoformat(timespec='seconds')}\n"
            f"Job: {job_id}\n"
            f"Stage: {job.get('stage') or '-'}\n"
            f"PDF: {job.get('current_file') or '-'}\n"
            f"Error: {type(error).__name__}: {error}\n\n"
            f"{traceback.format_exc()}"
        )
        try:
            self.error_log.write_text(details, encoding="utf-8")
            return str(self.error_log)
        except OSError:
            return None

    def _execute(self, job_id: str, pdf_dir: Path, target: Path, dpi: int) -> None:
        temporary: Path | None = None
        backup: Path | None = None
        try:
            self._update(job_id, status="running", progress=1, stage="Начинаем обработку")
            if not target.parent.is_dir():
                raise ValueError("Папка целевого Excel не существует")
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{target.stem}.propextract-",
                suffix=".xlsx",
                dir=target.parent,
            )
            os.close(descriptor)
            temporary = Path(temporary_name)
            temporary.unlink()

            def progress(value: int, stage: str, current_file: str | None) -> None:
                self._update(job_id, progress=value, stage=stage, current_file=current_file)

            result = self.runner(pdf_dir, target, temporary, dpi, 0, progress)
            self._update(job_id, progress=98, stage="Создаём резервную копию", current_file=None)
            expected_hash = str(result["input_hashes"]["xlsx"])
            changes = result.get("changes", [])
            is_noop = all(item.get("outcome") == "already_present" for item in changes)
            # Imports and delayed proposal approvals publish to the same target.
            # Serialize both paths, then recheck the user's workbook immediately
            # before replacement because Excel/sync tools do not share this lock.
            with self._publish_lock:
                if sha256(target) != expected_hash:
                    raise RuntimeError("Целевой Excel изменился во время обработки")
                if is_noop:
                    temporary.unlink(missing_ok=True)
                    temporary = None
                else:
                    backup_dir = target.parent / "Резервные копии PropExtract"
                    backup_dir.mkdir(parents=True, exist_ok=True)
                    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
                    backup = backup_dir / f"{target.stem} — до импорта {stamp}.xlsx"
                    retry_file_operation(lambda: shutil.copy2(target, backup))
                    if sha256(backup) != expected_hash:
                        backup.unlink(missing_ok=True)
                        backup = None
                        raise RuntimeError("Не удалось проверить резервную копию")
                    if sha256(target) != expected_hash:
                        backup.unlink(missing_ok=True)
                        backup = None
                        raise RuntimeError("Целевой Excel изменился во время обработки")
                    retry_file_operation(lambda: os.replace(temporary, target))
                    temporary = None
            result["output"] = str(target)
            result["backup"] = str(backup) if backup else None
            report = target.with_name(f"{target.stem} — отчет PropExtract.json")
            report_error = None
            try:
                atomic_json(report, result)
            except Exception as error:  # Workbook is already safely published and backed up.
                report_error = str(error)
            documents = result.get("documents", [])
            failed_documents = [item for item in documents if item.get("error")]
            input_hashes = result.get("input_hashes", {})
            pdf_hashes = dict(input_hashes.get("pdfs", {})) if isinstance(input_hashes, dict) else {}
            documents_internal: dict[str, dict[str, object]] = {}
            public_documents: list[dict[str, object]] = []
            for item in documents:
                raw = Path(str(item.get("file", "")))
                document_id = uuid.uuid4().hex
                try:
                    relative = str(raw.relative_to(pdf_dir))
                    file_hash = pdf_hashes.get(relative)
                except ValueError:
                    file_hash = None
                documents_internal[document_id] = {"path": raw, "hash": file_hash}
                public_documents.append({"id": document_id, "filename": raw.name, "error": "PDF не обработан." if item.get("error") else None})

            def document_reference(source: object) -> tuple[str | None, str | None]:
                candidate = Path(str(source or ""))
                if not candidate.is_absolute():
                    candidate = pdf_dir / candidate
                try:
                    identity = candidate.resolve()
                except OSError:
                    return None, None
                for public_document in public_documents:
                    internal = documents_internal[str(public_document["id"])]
                    path = internal.get("path")
                    try:
                        if isinstance(path, Path) and path.resolve() == identity:
                            return str(public_document["id"]), str(public_document["filename"])
                    except OSError:
                        continue
                return None, None

            proposals_internal: dict[str, dict[str, object]] = {}
            public_proposals: list[dict[str, object]] = []
            records = result.get("selected_records", {})
            for conflict in result.get("conflicts", []):
                if conflict.get("action") != "Перенести изменения":
                    continue
                number, field = str(conflict["number"]), str(conflict["field"])
                record = records.get(number, {}) if isinstance(records, dict) else {}
                field_key = {
                    "Номер этапа": "stage", "Наименование объекта": "object", "Дата выдачи": "issue",
                    "Срок действия": "end", "Дата последн. измен.": "changed", "Орган выдачи": "issuer",
                    "Застройщик": "builder", "Субъект РФ": "region", "Муниципальный р-н": "district",
                    "Разработчик ПД": "developer",
                }.get(field)
                source = record.get("field_sources", {}).get(field_key, "") if field_key else ""
                document_id, source_name = document_reference(source)
                if not document_id or not source_name:
                    continue
                proposal_id = uuid.uuid4().hex
                proposals_internal[proposal_id] = {"number": number, "field": field, "value": conflict["pdf"], "document_id": document_id, "status": "pending"}
                public_proposals.append({"id": proposal_id, "number": number, "row": next((change.get("row") for change in changes if change.get("number") == number), None), "field": field, "existing": conflict["existing"], "proposed": conflict["pdf"], "object": record.get("object"), "action": "Перенести изменения", "document_id": document_id, "filename": source_name})
            row_cards = []
            for change in changes:
                number = str(change.get("number", ""))
                record = records.get(number, {}) if isinstance(records, dict) else {}
                filename = str(change.get("document") or record.get("filename") or "PDF")
                document_id, source_name = document_reference(record.get("pdf") or filename)
                row_cards.append({"row": change.get("row"), "number": number, "object": record.get("object"), "details": "; ".join(filter(None, (_public_issue(issue) for issue in change.get("issues", [])))), "outcome": change.get("outcome"), "filename": source_name or Path(filename).name, "document_id": document_id})
            already_present = [item for item in changes if item.get("outcome") == "already_present"]
            summary = {
                "pdf_count": len(documents) - len(failed_documents),
                "failed_pdf_count": len(failed_documents),
                "record_count": len(result.get("logical_records", [])),
                "changed_rows": sum(1 for item in changes if item.get("outcome") != "already_present"),
                "new_rows": sum(1 for item in changes if item.get("new")),
                "already_present_count": len(already_present),
                "already_present_files": [str(item["document"]) for item in already_present if item.get("document")],
                "already_present_rows": [item["row"] for item in already_present if item.get("row")],
                "conflicts": len(result.get("conflicts", [])),
                "issue_count": sum(len(item.get("issues", [])) for item in changes),
                "rows_with_issues": [item.get("row") for item in changes if item.get("issues") and item.get("row")],
                "row_numbers": [item.get("row") for item in changes if item.get("row")],
                "new_row_numbers": [item.get("row") for item in changes if item.get("new") and item.get("row")],
            }
            warnings = []
            if failed_documents:
                warnings.append(f"PDF пропущено: {len(failed_documents)}. Причины сохранены в отчёте.")
            if report_error:
                warnings.append("Excel обновлён, но отчёт не записан.")
            self._update(
                job_id,
                status="done",
                progress=100,
                stage="Готово",
                summary=summary,
                backup=str(backup) if backup else None,
                report=str(report) if report_error is None else None,
                warning=" ".join(warnings) or None,
                documents=public_documents,
                documents_internal=documents_internal,
                proposals=public_proposals,
                proposals_internal=proposals_internal,
                row_cards=row_cards,
                target_hash=sha256(target),
                pdf_hashes=pdf_hashes,
            )
        except Exception as error:
            failed_job = self.get(job_id) or {}
            error_log = self._write_error_log(job_id, error, failed_job)
            self._update(
                job_id,
                status="error",
                stage="Обработка остановлена",
                error=public_error(error)[0],
                error_hint=public_error(error)[1],
                error_phase=failed_job.get("stage"),
                error_file=failed_job.get("current_file"),
                technical_log=bool(error_log),
                error_log=error_log,
                current_file=None,
            )
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)

    def _authorized(self, job_id: str, capability: object) -> dict[str, object]:
        job = self.get(job_id)
        if not job or not _capability_matches(job.get("capability", ""), capability):
            raise ValueError("Действие недоступно. Запустите перенос заново.")
        return job

    def open_document(self, job_id: str, document_id: str, capability: object) -> None:
        job = self._authorized(job_id, capability)
        if job.get("status") != "done":
            raise ValueError("Документ доступен только после завершения переноса.")
        item = dict(job.get("documents_internal", {}).get(document_id, {}))
        path = item.get("path")
        try:
            if isinstance(path, Path):
                path.resolve().relative_to(Path(str(job["pdf_dir"])).resolve())
            else:
                raise ValueError
        except ValueError:
            raise RuntimeError("document_unavailable")
        if not isinstance(path, Path) or not path.is_file() or path.is_symlink() or item.get("hash") != sha256(path):
            raise RuntimeError("document_unavailable")
        if os.name != "nt" or not hasattr(os, "startfile"):
            raise RuntimeError("document_open_unavailable")
        os.startfile(str(path))  # type: ignore[attr-defined]  # Windows API; no shell.

    def approve(self, job_id: str, proposal_id: str, capability: object) -> dict[str, object]:
        # Reserve this proposal under the manager lock before staging any file.
        # Do not call _update while holding it: _update deliberately takes it too.
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or not _capability_matches(job.get("capability", ""), capability):
                raise ValueError("Действие недоступно. Запустите перенос заново.")
            if job.get("status") != "done":
                raise ValueError("Подтверждение доступно только после завершения переноса.")
            proposals = dict(job.get("proposals_internal", {}))
            proposal = dict(proposals.get(proposal_id, {}))
            if not proposal or proposal.get("status") != "pending":
                raise ValueError("Предложение недоступно или уже обработано.")
            proposal["status"] = "approving"
            proposals[proposal_id] = proposal
            job["proposals_internal"] = proposals
            job["updated_at"] = datetime.now().isoformat(timespec="seconds")
        staged: Path | None = None
        self._publish_lock.acquire()
        try:
            target = Path(str(job["xlsx"]))
            expected = str(job.get("target_hash", ""))
            doc = dict(job.get("documents_internal", {}).get(proposal.get("document_id"), {}))
            pdf = doc.get("path")
            if isinstance(pdf, Path):
                pdf.resolve().relative_to(Path(str(job["pdf_dir"])).resolve())
            else:
                raise ValueError
            if (not expected or not target.is_file() or target.is_symlink() or not isinstance(pdf, Path)
                    or pdf.suffix.lower() != ".pdf" or not pdf.is_file() or pdf.is_symlink()
                    or doc.get("hash") != sha256(pdf)):
                raise RuntimeError("proposal_source_unavailable")
            if sha256(target) != expected:
                raise RuntimeError("proposal_target_stale")
            descriptor, name = tempfile.mkstemp(prefix=f".{target.stem}.proposal-", suffix=".xlsx", dir=target.parent)
            os.close(descriptor)
            staged = Path(name)
            staged.unlink(missing_ok=True)
            value: object = proposal["value"]
            if proposal["field"] in {"Дата выдачи", "Срок действия", "Дата последн. измен."}:
                value = iso_date(str(value))
            apply_proposal(target, staged, expected, str(proposal["number"]), str(proposal["field"]), value, pdf)
            backup_dir = target.parent / "Резервные копии PropExtract"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup = backup_dir / f"{target.stem} — до подтверждения {datetime.now().strftime('%Y-%m-%d_%H-%M-%S_%f')}.xlsx"
            retry_file_operation(lambda: shutil.copy2(target, backup))
            if sha256(backup) != expected:
                backup.unlink(missing_ok=True)
                raise RuntimeError("proposal_backup_invalid")
            if sha256(target) != expected:
                raise RuntimeError("proposal_target_stale")
            retry_file_operation(lambda: os.replace(staged, target))
            proposal["status"] = "approved"
            with self._lock:
                current = self._jobs[job_id]
                proposals = dict(current.get("proposals_internal", {}))
                proposals[proposal_id] = proposal
                public = list(current.get("proposals", []))
                for item in public:
                    if item.get("id") == proposal_id:
                        item["status"] = "approved"
                current.update(proposals_internal=proposals, proposals=public, target_hash=sha256(target), updated_at=datetime.now().isoformat(timespec="seconds"))
            return {"status": "approved", "backup": backup.name}
        except Exception:
            with self._lock:
                current = self._jobs.get(job_id)
                if current:
                    proposals = dict(current.get("proposals_internal", {}))
                    pending = dict(proposals.get(proposal_id, {}))
                    if pending.get("status") == "approving":
                        pending["status"] = "pending"
                        proposals[proposal_id] = pending
                        current["proposals_internal"] = proposals
            raise
        finally:
            if staged:
                staged.unlink(missing_ok=True)
            self._publish_lock.release()


def create_server(host: str, port: int, runner: Runner, instance_id: str | None = None) -> ThreadingHTTPServer:
    """Create a loopback server whose health response identifies this copy."""
    if host not in LOOPBACK_HOSTS:
        raise ValueError("Сервер PropExtract может слушать только loopback-адрес")
    resolved_instance_id = instance_id or project_instance_id()
    if not isinstance(resolved_instance_id, str) or not _INSTANCE_ID.fullmatch(resolved_instance_id):
        raise ValueError("Некорректный идентификатор экземпляра PropExtract")
    manager = JobManager(runner)

    class Handler(BaseHTTPRequestHandler):
        def _headers(self, status: int, content_type: str, length: int) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-PropExtract-Instance", resolved_instance_id)
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()

        def send_json(self, status: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self._headers(status, "application/json; charset=utf-8", len(body))
            self.wfile.write(body)

        def send_asset(self, filename: str, content_type: str) -> None:
            body = (STATIC / filename).read_bytes()
            self._headers(200, content_type, len(body))
            self.wfile.write(body)

        def body_json(self) -> dict[str, object]:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as error:
                raise ValueError("Некорректный размер запроса") from error
            if length <= 0 or length > MAX_BODY:
                raise ValueError("Некорректный размер запроса")
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict):
                raise ValueError("Ожидается JSON-объект")
            return value

        def do_GET(self) -> None:
            path = urlparse(self.path).path.rstrip("/") or "/"
            if path in ASSETS:
                filename, content_type = ASSETS[path]
                self.send_asset(filename, content_type)
            elif path == "/health":
                self.send_json(200, {"status": "ok", "service": "rns-import"})
            elif path == "/api/system":
                self.send_json(200, _tool_status())
            elif path.startswith("/api/jobs/"):
                job = manager.public(path.removeprefix("/api/jobs/"))
                self.send_json(200, job) if job else self.send_json(404, {"error": "Задача не найдена"})
            else:
                self.send_json(404, {"error": "Страница не найдена"})

        def do_POST(self) -> None:
            path = urlparse(self.path).path.rstrip("/")
            try:
                payload = self.body_json()
                if path == "/api/jobs":
                    job = manager.start(str(payload.get("pdf_dir", "")), str(payload.get("xlsx", "")), int(payload.get("dpi", 180)))
                    self.send_json(202, manager.public(str(job["id"])) or {})
                elif path == "/api/picker":
                    selected = select_path(str(payload.get("kind", "")))
                    self.send_json(200, {"path": selected, "cancelled": selected is None})
                elif path == "/api/shutdown":
                    if self.headers.get("X-PropExtract-Action") != "shutdown":
                        raise ValueError("Остановка разрешена только из интерфейса PropExtract")
                    if manager.has_active_job():
                        raise BusyError("Сейчас идёт перенос данных. Дождитесь завершения, затем остановите программу.")
                    self.send_json(202, {"status": "stopping"})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                elif path.startswith("/api/jobs/") and path.endswith("/approve"):
                    parts = path.split("/")
                    if len(parts) != 7 or parts[4] != "proposals":
                        raise ValueError("Метод не найден")
                    self.send_json(200, manager.approve(parts[3], parts[5], payload.get("capability")))
                elif path.startswith("/api/jobs/") and path.endswith("/open"):
                    parts = path.split("/")
                    if len(parts) != 7 or parts[4] != "documents":
                        raise ValueError("Метод не найден")
                    manager.open_document(parts[3], parts[5], payload.get("capability"))
                    self.send_json(202, {"status": "opening"})
                else:
                    self.send_json(404, {"error": "Метод не найден"})
            except BusyError as error:
                message, hint = public_error(error); self.send_json(409, {"error": message, "hint": hint})
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                message, hint = public_error(error); self.send_json(400, {"error": message, "hint": hint})
            except Exception as error:
                message, hint = public_error(error); self.send_json(500, {"error": message, "hint": hint})

        def log_message(self, format: str, *args: object) -> None:
            print("HTTP", format % args)

    server = ThreadingHTTPServer((host, port), Handler)
    server.job_manager = manager  # type: ignore[attr-defined]
    return server
