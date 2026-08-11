from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from rns_import_server import ocr


def _configure_ocr(monkeypatch, pdf: Path, pages: int, runner):
    monkeypatch.setattr(ocr, "page_count", lambda source: pages)
    monkeypatch.setattr(ocr, "_text_layer", lambda source, last_page: None)
    monkeypatch.setattr(ocr, "find_tool", lambda name: {"pdftoppm": "renderer", "tesseract": "tesseract"}.get(name))
    monkeypatch.setattr(ocr, "tesseract_environment", lambda: {})
    monkeypatch.setattr(ocr, "_run", runner)


def test_ocr_renders_bounded_unicode_batches_in_page_order(monkeypatch, tmp_path: Path):
    pdf = tmp_path / "разрешение № 42.pdf"
    pdf.write_bytes(b"pdf")
    before_render, rendered_counts, rendered_ranges = [], [], []

    def runner(argv, **kwargs):
        if argv[0] == "renderer":
            prefix = Path(argv[-1])
            first = int(argv[argv.index("-f") + 1])
            last = int(argv[argv.index("-l") + 1])
            before_render.append(len(list(prefix.parent.glob("page-*.png"))))
            rendered_ranges.append((first, last))
            assert str(pdf) in argv
            for page in range(first, last + 1):
                (prefix.parent / f"page-{page:02d}.png").write_text(str(page), encoding="utf-8")
            rendered_counts.append(len(list(prefix.parent.glob("page-*.png"))))
            return subprocess.CompletedProcess(argv, 0, "", "")
        return subprocess.CompletedProcess(argv, 0, Path(argv[1]).read_text(encoding="utf-8"), "")

    _configure_ocr(monkeypatch, pdf, 5, runner)

    assert ocr.read(pdf) == ("1\n2\n3\n4\n5", 5)
    assert rendered_ranges == [(1, 2), (3, 4), (5, 5)]
    assert rendered_counts == [2, 2, 1]
    assert before_render == [0, 0, 0]


def test_ocr_empty_native_stdout_is_preserved_as_empty_page(monkeypatch, tmp_path: Path):
    pdf = tmp_path / "blank.pdf"
    pdf.write_bytes(b"pdf")

    def runner(argv, **kwargs):
        if argv[0] == "renderer":
            prefix = Path(argv[-1])
            (prefix.parent / "page-01.png").write_bytes(b"png")
            return subprocess.CompletedProcess(argv, 0, "", "")
        return subprocess.CompletedProcess(argv, 0, None, None)

    _configure_ocr(monkeypatch, pdf, 1, runner)

    assert ocr.read(pdf) == ("", 1)


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (subprocess.TimeoutExpired(["tesseract"], 120), r"^tesseract_timeout:page-01[.]png$"),
        (subprocess.CompletedProcess(["tesseract"], 1, "", "failed"), r"^tesseract_failed:page-01[.]png$"),
    ],
)
def test_ocr_cleans_rendered_pngs_after_timeout_or_failure(monkeypatch, tmp_path: Path, result, expected: str):
    pdf = tmp_path / "broken.pdf"
    pdf.write_bytes(b"pdf")
    rendered_dirs: list[Path] = []

    def runner(argv, **kwargs):
        if argv[0] == "renderer":
            prefix = Path(argv[-1])
            rendered_dirs.append(prefix.parent)
            (prefix.parent / "page-01.png").write_bytes(b"png")
            return subprocess.CompletedProcess(argv, 0, "", "")
        if isinstance(result, Exception):
            raise result
        return result

    _configure_ocr(monkeypatch, pdf, 1, runner)

    with pytest.raises(RuntimeError, match=expected):
        ocr.read(pdf)
    assert rendered_dirs and not rendered_dirs[0].exists()


def test_ocr_fails_and_cleans_rendered_pngs_after_render_failure(monkeypatch, tmp_path: Path):
    pdf = tmp_path / "render-failure.pdf"
    pdf.write_bytes(b"pdf")
    rendered_dirs: list[Path] = []

    def runner(argv, **kwargs):
        prefix = Path(argv[-1])
        rendered_dirs.append(prefix.parent)
        (prefix.parent / "page-01.png").write_bytes(b"partial")
        return subprocess.CompletedProcess(argv, 1, "", "failed")

    _configure_ocr(monkeypatch, pdf, 1, runner)

    with pytest.raises(RuntimeError, match=r"^pdf_render_failed$"):
        ocr.read(pdf)
    assert rendered_dirs and not rendered_dirs[0].exists()
