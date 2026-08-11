"""Bounded local OCR.  It never retains rendered pages or OCR text on disk."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

TESSDATA = Path(__file__).with_name("tessdata")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
LANGUAGE_HASHES = {
    "eng": "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2",
    "rus": "e16e5e036cce1d9ec2b00063cf8b54472625b9e14d893a169e2b0dedeb4df225",
}
OCR_PAGE_BATCH_SIZE = 2


def _is_windows() -> bool:
    return os.name == "nt"


def _native_relative_path(value: str | Path, workspace: Path | None) -> str:
    """Return an ASCII path suitable for a legacy Windows native process."""
    text = str(value)
    if not (_is_windows() and workspace is not None):
        return text
    path = Path(text)
    relative = os.path.relpath(path, workspace) if path.is_absolute() else text
    if not relative.isascii():
        raise RuntimeError("windows_native_path_not_ascii")
    return relative


def _native_argv(command: str, arguments: list[str], workspace: Path | None = None) -> list[str]:
    return [
        _native_relative_path(command, workspace),
        *[_native_relative_path(argument, workspace) for argument in arguments],
    ]


def _native_environment(workspace: Path | None = None) -> dict[str, str] | None:
    """Keep inherited Unicode project paths out of Windows native environments."""
    if not (_is_windows() and workspace is not None):
        return None
    return {
        key: value
        for key, value in os.environ.items()
        if isinstance(key, str) and isinstance(value, str) and key.isascii() and value.isascii()
    }


@lru_cache(maxsize=1)
def bundled_language_status() -> dict[str, dict[str, object]]:
    """Verify bundled OCR models once per process."""
    status: dict[str, dict[str, object]] = {}
    for language, expected in LANGUAGE_HASHES.items():
        path = TESSDATA / f"{language}.traineddata"
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        status[language] = {
            "available": path.is_file(),
            "valid": actual == expected,
            "sha256": actual,
        }
    return status


def tesseract_environment(workspace: Path | None = None) -> dict[str, str]:
    invalid = [language for language, item in bundled_language_status().items() if not item["valid"]]
    if invalid:
        raise RuntimeError(f"ocr_models_invalid:{','.join(invalid)}")
    environment = _native_environment(workspace)
    if environment is None:
        environment = dict(os.environ)
    environment["TESSDATA_PREFIX"] = _native_relative_path(TESSDATA, workspace)
    return environment


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@lru_cache(maxsize=4)
def _verified_project_windows_runtime(project_root_text: str) -> tuple[Path, dict[str, object]] | None:
    project_root = Path(project_root_text)
    try:
        lock = json.loads((project_root / "windows-runtime.lock.json").read_text(encoding="utf-8"))
        native = lock["nativeTree"]
        runtime = project_root / ".runtime" / "windows" / f"native-{lock['runtime']}"
        if not runtime.is_dir():
            return None
        files = [path for path in runtime.rglob("*") if path.is_file()]
        if any(path.is_symlink() for path in files) or len(files) != int(native["files"]):
            return None
        entries = sorted((path.relative_to(runtime).as_posix(), _file_sha256(path)) for path in files)
        canonical = "".join(f"{digest}  {relative}\n" for relative, digest in entries).encode()
        if hashlib.sha256(canonical).hexdigest() != str(native["sha256"]).lower():
            return None
        return runtime, lock
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def project_windows_tool(name: str, project_root: Path = PROJECT_ROOT) -> str | None:
    """Find a tool only inside the exact, integrity-checked Windows runtime."""
    if name not in {"tesseract", "pdfinfo", "pdftoppm", "pdftotext"}:
        return None
    executable = f"{name}.exe"
    verified = _verified_project_windows_runtime(str(project_root.resolve()))
    if not verified:
        return None
    runtime, lock = verified
    native = lock["nativeTree"]
    candidate = (
        runtime / str(native["tesseractPath"])
        if name == "tesseract"
        else runtime / str(native["popplerBinPath"]) / executable
    )
    if candidate.is_file() and not candidate.is_symlink():
        return str(candidate)
    return None


@lru_cache(maxsize=None)
def find_tool(name: str) -> str | None:
    """Use the pinned runtime on Windows and system packages on Unix."""
    if _is_windows():
        return project_windows_tool(name)
    return shutil.which(name)


def _run(
    argv: list[str], *, timeout: int, env: dict[str, str] | None = None, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=timeout,
        env=env,
        cwd=str(cwd) if cwd is not None else None,
    )


def _captured_text(value: object) -> str:
    """Normalize an unexpectedly empty native-process stream to safe text."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def page_count(pdf: Path, *, native_workspace: Path | None = None) -> int:
    command = find_tool("pdfinfo")
    if not command:
        raise RuntimeError("pdfinfo_unavailable")
    try:
        result = _run(
            _native_argv(command, [str(pdf)], native_workspace),
            timeout=30,
            env=_native_environment(native_workspace),
            cwd=native_workspace,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("pdfinfo_timeout") from error
    if result.returncode:
        raise RuntimeError("pdfinfo_failed")
    for line in _captured_text(result.stdout).splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise RuntimeError("pdfinfo_invalid_output")


def _text_layer(pdf: Path, last_page: int, *, native_workspace: Path | None = None) -> str | None:
    command = find_tool("pdftotext")
    if not command:
        return None
    try:
        result = _run(
            _native_argv(command, ["-f", "1", "-l", str(last_page), str(pdf), "-"], native_workspace),
            timeout=90,
            env=_native_environment(native_workspace),
            cwd=native_workspace,
        )
    except subprocess.TimeoutExpired:
        return None
    output = _captured_text(result.stdout)
    if result.returncode or not output.strip():
        return None
    return output


def _ocr_image(image: Path, tesseract: str, *, native_workspace: Path | None = None) -> str:
    try:
        environment = (
            tesseract_environment(native_workspace) if native_workspace is not None else tesseract_environment()
        )
        result = _run(
            _native_argv(
                tesseract,
                [str(image), "stdout", "-l", "rus+eng", "--oem", "1", "--psm", "6"],
                native_workspace,
            ),
            timeout=120,
            env=environment,
            cwd=native_workspace,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"tesseract_timeout:{image.name}") from error
    if result.returncode:
        raise RuntimeError(f"tesseract_failed:{image.name}")
    return _captured_text(result.stdout)


def _read(pdf: Path, dpi: int, max_pages: int, native_workspace: Path | None = None) -> tuple[str, int]:
    total = page_count(pdf, native_workspace=native_workspace) if native_workspace is not None else page_count(pdf)
    last_page = min(total, max_pages) if max_pages else total
    text = (
        _text_layer(pdf, last_page, native_workspace=native_workspace)
        if native_workspace is not None
        else _text_layer(pdf, last_page)
    )
    if text:
        return text, total
    renderer, tesseract = find_tool("pdftoppm"), find_tool("tesseract")
    if not renderer:
        raise RuntimeError("pdftoppm_unavailable")
    if not tesseract:
        raise RuntimeError("tesseract_unavailable")

    def render_and_ocr(temporary: Path) -> tuple[str, int]:
        prefix = temporary / "page"
        cache = temporary / "cache" if native_workspace is not None else Path(tempfile.gettempdir()) / "rns-import-font-cache"
        cache.mkdir(exist_ok=True)
        environment = _native_environment(native_workspace) or dict(os.environ)
        environment["XDG_CACHE_HOME"] = _native_relative_path(cache, native_workspace)
        parts: list[str] = []
        for first_page in range(1, last_page + 1, OCR_PAGE_BATCH_SIZE):
            final_page = min(first_page + OCR_PAGE_BATCH_SIZE - 1, last_page)
            try:
                try:
                    rendered = _run(
                        _native_argv(
                            renderer,
                            [
                                "-png",
                                "-r",
                                str(dpi),
                                "-f",
                                str(first_page),
                                "-l",
                                str(final_page),
                                str(pdf),
                                str(prefix),
                            ],
                            native_workspace,
                        ),
                        timeout=600,
                        env=environment,
                        cwd=native_workspace,
                    )
                except subprocess.TimeoutExpired as error:
                    raise RuntimeError("pdf_render_timeout") from error
                images = sorted(temporary.glob("page-*.png"))
                expected_images = final_page - first_page + 1
                if rendered.returncode or len(images) != expected_images:
                    raise RuntimeError("pdf_render_failed")
                workers = min(2, len(images))
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    parts.extend(
                        executor.map(
                            lambda item: _ocr_image(item, tesseract, native_workspace=native_workspace), images
                        )
                    )
            finally:
                for image in temporary.glob("page-*.png"):
                    image.unlink()
        return "\n".join(_captured_text(part) for part in parts), total

    if native_workspace is not None:
        return render_and_ocr(native_workspace)
    with tempfile.TemporaryDirectory(prefix="rns-ocr-") as temporary_name:
        return render_and_ocr(Path(temporary_name))


def read(pdf: Path, dpi: int = 180, max_pages: int = 0) -> tuple[str, int]:
    """Prefer the PDF text layer, then render and OCR bounded page batches."""
    if not _is_windows():
        return _read(pdf, dpi, max_pages)
    with tempfile.TemporaryDirectory(prefix=".rns-ocr-", dir=PROJECT_ROOT) as temporary_name:
        workspace = Path(temporary_name)
        staged_pdf = workspace / "input.pdf"
        shutil.copyfile(pdf, staged_pdf)
        return _read(staged_pdf, dpi, max_pages, native_workspace=workspace)
