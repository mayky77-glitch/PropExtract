#!/usr/bin/env python3
"""Verify Tesseract stdout behavior through PropExtract's exact subprocess path."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from rns_import_server import ocr


FONT = {
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    " ": ("00000",) * 7,
}


def write_pgm(path: Path, text: str, scale: int = 12, margin: int = 40) -> None:
    glyph_width, glyph_height, gap = 5, 7, 2
    width = margin * 2 + (len(text) * glyph_width + max(0, len(text) - 1) * gap) * scale
    height = margin * 2 + glyph_height * scale
    pixels = bytearray([255]) * (width * height)
    for index, character in enumerate(text):
        pattern = FONT[character]
        x_origin = margin + index * (glyph_width + gap) * scale
        for row, bits in enumerate(pattern):
            for column, bit in enumerate(bits):
                if bit != "1":
                    continue
                for y in range(margin + row * scale, margin + (row + 1) * scale):
                    start = y * width + x_origin + column * scale
                    pixels[start : start + scale] = b"\0" * scale
    path.write_bytes(f"P5\n{width} {height}\n255\n".encode("ascii") + pixels)


def invoke(image: Path, tesseract: str, psm: int, native_workspace: Path | None = None) -> object:
    return ocr._run(
        ocr._native_argv(
            tesseract,
            [str(image), "stdout", "-l", "eng", "--oem", "1", "--psm", str(psm)],
            native_workspace,
        ),
        timeout=60,
        env=(
            ocr.tesseract_environment(native_workspace)
            if native_workspace is not None
            else ocr.tesseract_environment()
        ),
        cwd=native_workspace,
    )


def main() -> None:
    tesseract = ocr.find_tool("tesseract")
    if not tesseract:
        raise RuntimeError("tesseract_unavailable")
    temporary_directory = {"prefix": "propextract-ocr-stdio-"}
    if ocr._is_windows():
        temporary_directory["dir"] = ocr.PROJECT_ROOT
    with tempfile.TemporaryDirectory(**temporary_directory) as temporary_name:
        temporary = Path(temporary_name)
        native_workspace = temporary if ocr._is_windows() else None
        blank, text_image = temporary / "blank.pgm", temporary / "text.pgm"
        write_pgm(blank, " " * 8)
        write_pgm(text_image, "TEST 123")
        blank_result = invoke(blank, tesseract, 6, native_workspace)
        text_result = invoke(text_image, tesseract, 7, native_workspace)
        app_blank = ocr._ocr_image(blank, tesseract, native_workspace=native_workspace)

    if blank_result.returncode != 0:
        raise RuntimeError(f"blank_tesseract_failed:{blank_result.returncode}")
    if text_result.returncode != 0:
        raise RuntimeError(f"text_tesseract_failed:{text_result.returncode}")
    if blank_result.stdout is None or not isinstance(blank_result.stdout, str):
        raise RuntimeError(f"blank_stdout_invalid:{type(blank_result.stdout).__name__}")
    if text_result.stdout is None or not isinstance(text_result.stdout, str):
        raise RuntimeError(f"text_stdout_invalid:{type(text_result.stdout).__name__}")
    if blank_result.stdout.strip() or app_blank:
        raise RuntimeError("blank_stdout_not_empty")
    if not text_result.stdout.strip():
        raise RuntimeError("text_stdout_empty")

    print(
        json.dumps(
            {
                "blank_returncode": blank_result.returncode,
                "blank_stdout_type": type(blank_result.stdout).__name__,
                "blank_stdout_length": len(blank_result.stdout),
                "app_blank_type": type(app_blank).__name__,
                "app_blank_length": len(app_blank),
                "text_returncode": text_result.returncode,
                "text_stdout_type": type(text_result.stdout).__name__,
                "text_stdout": text_result.stdout.strip(),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
