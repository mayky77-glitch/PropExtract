"""Loopback-only admin server with background import jobs."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

try:
    from rns_import_server.audit import atomic_json, sha256
except ModuleNotFoundError:
    from audit import atomic_json, sha256

Runner = Callable[..., dict]
MAX_BODY = 64 * 1024
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
                timeout=600,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("Время выбора пути истекло") from error
        if result.returncode:
            detail = result.stderr.strip()
            if "tkinter_unavailable" in detail:
                raise RuntimeError("Системное окно недоступно: установите Tkinter")
            raise RuntimeError(detail or "Не удалось открыть системное окно")
        selected = result.stdout.strip()
        return selected or None
    finally:
        PICKER_LOCK.release()


def _tool_status() -> dict[str, object]:
    commands = {name: shutil.which(name) for name in ("tesseract", "pdfinfo", "pdftoppm", "pdftotext")}
    languages: list[str] = []
    if commands["tesseract"]:
        try:
            result = subprocess.run(
                [str(commands["tesseract"]), "--list-langs"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            languages = [line.strip() for line in result.stdout.splitlines()[1:] if line.strip()]
        except (OSError, subprocess.TimeoutExpired):
            pass
    required = all(commands[name] for name in ("tesseract", "pdfinfo", "pdftoppm")) and {"rus", "eng"}.issubset(languages)
    return {"ready": bool(required), "commands": {key: bool(value) for key, value in commands.items()}, "languages": languages}


class BusyError(RuntimeError):
    pass


class JobManager:
    """Own one OCR job at a time and retain a small in-memory history."""

    def __init__(self, runner: Runner, history_limit: int = 20):
        self.runner = runner
        self.history_limit = history_limit
        self._jobs: dict[str, dict[str, object]] = {}
        self._lock = threading.Lock()

    def start(self, pdf_dir: str, xlsx: str, dpi: int = 180) -> dict[str, object]:
        pdf_value, xlsx_value = pdf_dir.strip(), xlsx.strip()
        if not pdf_value or not xlsx_value:
            raise ValueError("Укажите папку с PDF и целевой файл Excel")
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
            }
            self._jobs[job_id] = job
            self._trim_locked()
        threading.Thread(target=self._execute, args=(job_id, Path(pdf_value), Path(xlsx_value), dpi), daemon=True).start()
        return self.get(job_id) or {}

    def get(self, job_id: str) -> dict[str, object] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

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

    def _execute(self, job_id: str, pdf_dir: Path, target: Path, dpi: int) -> None:
        temporary: Path | None = None
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
            if sha256(target) != expected_hash:
                raise RuntimeError("Целевой Excel изменился во время обработки")
            backup_dir = target.parent / "Резервные копии PropExtract"
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
            backup = backup_dir / f"{target.stem} — до импорта {stamp}.xlsx"
            shutil.copy2(target, backup)
            if sha256(backup) != expected_hash:
                backup.unlink(missing_ok=True)
                raise RuntimeError("Не удалось проверить резервную копию")
            os.replace(temporary, target)
            temporary = None
            result["output"] = str(target)
            result["backup"] = str(backup)
            report = target.with_name(f"{target.stem} — отчет PropExtract.json")
            report_error = None
            try:
                atomic_json(report, result)
            except Exception as error:  # Workbook is already safely published and backed up.
                report_error = str(error)
            summary = {
                "pdf_count": len(result.get("documents", [])),
                "record_count": len(result.get("logical_records", [])),
                "changed_rows": len(result.get("changes", [])),
                "new_rows": sum(1 for item in result.get("changes", []) if item.get("new")),
                "conflicts": len(result.get("conflicts", [])),
                "row_numbers": [item.get("row") for item in result.get("changes", []) if item.get("row")],
                "new_row_numbers": [item.get("row") for item in result.get("changes", []) if item.get("new") and item.get("row")],
            }
            self._update(
                job_id,
                status="done",
                progress=100,
                stage="Готово",
                summary=summary,
                backup=str(backup),
                report=str(report) if report_error is None else None,
                warning=f"Excel обновлён, но отчёт не записан: {report_error}" if report_error else None,
            )
        except Exception as error:
            self._update(job_id, status="error", stage="Обработка остановлена", error=str(error), current_file=None)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)


def create_server(host: str, port: int, runner: Runner) -> ThreadingHTTPServer:
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
                job = manager.get(path.removeprefix("/api/jobs/"))
                self.send_json(200, job) if job else self.send_json(404, {"error": "Задача не найдена"})
            else:
                self.send_json(404, {"error": "Страница не найдена"})

        def do_POST(self) -> None:
            path = urlparse(self.path).path.rstrip("/")
            try:
                payload = self.body_json()
                if path == "/api/jobs":
                    job = manager.start(str(payload.get("pdf_dir", "")), str(payload.get("xlsx", "")), int(payload.get("dpi", 180)))
                    self.send_json(202, job)
                elif path == "/api/picker":
                    selected = select_path(str(payload.get("kind", "")))
                    self.send_json(200, {"path": selected, "cancelled": selected is None})
                elif path == "/process":
                    for key in ("pdf_dir", "xlsx", "output"):
                        if key not in payload:
                            raise ValueError(f"missing {key}")
                    result = runner(Path(str(payload["pdf_dir"])), Path(str(payload["xlsx"])), Path(str(payload["output"])), int(payload.get("dpi", 180)), int(payload.get("max_pages", 0)))
                    self.send_json(200, result)
                else:
                    self.send_json(404, {"error": "Метод не найден"})
            except BusyError as error:
                self.send_json(409, {"error": str(error)})
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                self.send_json(400, {"error": str(error)})
            except Exception as error:
                self.send_json(500, {"error": str(error)})

        def log_message(self, format: str, *args: object) -> None:
            print("HTTP", format % args)

    server = ThreadingHTTPServer((host, port), Handler)
    server.job_manager = manager  # type: ignore[attr-defined]
    return server
