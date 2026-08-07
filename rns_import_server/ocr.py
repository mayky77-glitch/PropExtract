"""Bounded local OCR.  It never retains rendered pages or OCR text on disk."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

TESSDATA = Path(__file__).with_name("tessdata")
LANGUAGE_HASHES = {
    "eng": "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2",
    "rus": "e16e5e036cce1d9ec2b00063cf8b54472625b9e14d893a169e2b0dedeb4df225",
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


def tesseract_environment() -> dict[str, str]:
    invalid = [language for language, item in bundled_language_status().items() if not item["valid"]]
    if invalid:
        raise RuntimeError(f"ocr_models_invalid:{','.join(invalid)}")
    return dict(os.environ, TESSDATA_PREFIX=str(TESSDATA))


def _tool(name: str) -> str | None:
    return shutil.which(name)


def _run(argv: list[str], *, timeout: int, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, check=False, timeout=timeout, env=env)


def page_count(pdf: Path) -> int:
    command = _tool("pdfinfo")
    if not command:
        raise RuntimeError("pdfinfo_unavailable")
    try:
        result = _run([command, str(pdf)], timeout=30)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("pdfinfo_timeout") from error
    if result.returncode:
        raise RuntimeError("pdfinfo_failed")
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise RuntimeError("pdfinfo_invalid_output")


def _text_layer(pdf: Path, last_page: int) -> str | None:
    command = _tool("pdftotext")
    if not command:
        return None
    try:
        result = _run([command, "-f", "1", "-l", str(last_page), str(pdf), "-"], timeout=90)
    except subprocess.TimeoutExpired:
        return None
    if result.returncode or not result.stdout.strip():
        return None
    return result.stdout


def _ocr_image(image: Path, tesseract: str) -> str:
    try:
        result = _run(
            [tesseract, str(image), "stdout", "-l", "rus+eng", "--oem", "1", "--psm", "6"],
            timeout=120,
            env=tesseract_environment(),
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"tesseract_timeout:{image.name}") from error
    if result.returncode:
        raise RuntimeError(f"tesseract_failed:{image.name}")
    return result.stdout


def read(pdf: Path, dpi: int = 180, max_pages: int = 0) -> tuple[str, int]:
    """Prefer the PDF text layer, then render all requested pages once for OCR."""
    total = page_count(pdf)
    last_page = min(total, max_pages) if max_pages else total
    if text := _text_layer(pdf, last_page):
        return text, total
    renderer, tesseract = _tool("pdftoppm"), _tool("tesseract")
    if not renderer:
        raise RuntimeError("pdftoppm_unavailable")
    if not tesseract:
        raise RuntimeError("tesseract_unavailable")
    with tempfile.TemporaryDirectory(prefix="rns-ocr-") as temporary_name:
        temporary = Path(temporary_name)
        prefix = temporary / "page"
        cache = Path(tempfile.gettempdir()) / "rns-import-font-cache"
        cache.mkdir(exist_ok=True)
        environment = dict(os.environ, XDG_CACHE_HOME=str(cache))
        try:
            rendered = _run(
                [renderer, "-png", "-r", str(dpi), "-f", "1", "-l", str(last_page), str(pdf), str(prefix)],
                timeout=600,
                env=environment,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("pdf_render_timeout") from error
        images = sorted(temporary.glob("page-*.png"))
        if rendered.returncode or len(images) != last_page:
            raise RuntimeError("pdf_render_failed")
        workers = min(2, len(images))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            parts = list(executor.map(lambda item: _ocr_image(item, tesseract), images))
    return "\n".join(parts), total
