"""Synthetic regressions for the one-shot forced-raster identity recovery."""
from __future__ import annotations

import subprocess
from pathlib import Path

from rns_import_server import app, ocr
from rns_import_server.ocr import OCRText


NUMBER = "RU-12345678-09-2026"


def test_forced_raster_bypasses_nonempty_text_layer_and_respects_page_bound(monkeypatch, tmp_path: Path):
    pdf = tmp_path / "permit.pdf"
    pdf.write_bytes(b"synthetic")
    calls: list[str] = []
    ranges: list[tuple[int, int]] = []
    monkeypatch.setattr(ocr, "page_count", lambda source: 14)
    monkeypatch.setattr(ocr, "_text_layer", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("text layer must be bypassed")))
    monkeypatch.setattr(ocr, "find_tool", lambda name: {"pdftoppm": "renderer", "tesseract": "tesseract"}.get(name))
    monkeypatch.setattr(ocr, "tesseract_environment", lambda: {})

    def runner(argv, **kwargs):
        calls.append(argv[0])
        if argv[0] == "renderer":
            assert argv[argv.index("-r") + 1] == "180"
            first, last = int(argv[argv.index("-f") + 1]), int(argv[argv.index("-l") + 1])
            ranges.append((first, last))
            prefix = Path(argv[-1])
            for page in range(first, last + 1):
                (prefix.parent / f"page-{page:02d}.png").write_bytes(b"png")
            return subprocess.CompletedProcess(argv, 0, "", "")
        return subprocess.CompletedProcess(argv, 0, "Номер разрешения на строительство: " + NUMBER, "")

    monkeypatch.setattr(ocr, "_run", runner)
    text, pages = ocr.read(pdf, 180, 10, force_ocr=True)

    assert pages == 14
    assert text.source == "raster"
    assert NUMBER in text
    assert ranges == [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10)]
    assert calls.count("renderer") == 5
    assert "pdftotext" not in calls


def test_collect_retries_bad_text_layer_once_with_true_raster_at_180(monkeypatch, tmp_path: Path):
    pdf = tmp_path / "Разрешение на строительство.pdf"
    pdf.write_bytes(b"synthetic")
    calls: list[tuple[int, int, bool]] = []

    def reader(source: Path, dpi: int, max_pages: int, *, force_ocr: bool = False):
        calls.append((dpi, max_pages, force_ocr))
        if not force_ocr:
            return OCRText("Н о м е р Р Н С не читается", source="text_layer"), 16
        return OCRText(f"Номер разрешения на строительство: {NUMBER}", source="raster"), 16

    monkeypatch.setattr(app, "read_ocr", reader)
    records, documents = app.collect(tmp_path, 180, 0, pdfs=[pdf])

    assert calls == [(180, 0, False), (180, 10, True)]
    assert list(records) == [NUMBER]
    assert documents[0]["outcome"] == "processed_rns"
    assert documents[0]["ocr_source"] == "raster"


def test_collect_uses_one_bounded_400_fallback_after_an_actual_raster_miss(monkeypatch, tmp_path: Path):
    pdf = tmp_path / "Разрешение на строительство.pdf"
    pdf.write_bytes(b"synthetic")
    calls: list[tuple[int, int, bool]] = []

    def reader(source: Path, dpi: int, max_pages: int, *, force_ocr: bool = False):
        calls.append((dpi, max_pages, force_ocr))
        if not force_ocr:
            return OCRText("растр без номера", source="raster"), 14
        return OCRText(f"Номер разрешения на строительство: {NUMBER}", source="raster"), 14

    monkeypatch.setattr(app, "read_ocr", reader)
    records, documents = app.collect(tmp_path, 180, 0, pdfs=[pdf])

    assert calls == [(180, 0, False), (400, 10, True)]
    assert list(records) == [NUMBER]
    assert documents[0]["ocr_source"] == "raster"


def test_collect_classifies_only_positive_gro_ro_gpzu_as_out_of_scope(monkeypatch, tmp_path: Path):
    gro = tmp_path / "ГРО.pdf"
    permit = tmp_path / "Разрешение.pdf"
    garbled = tmp_path / "scan.pdf"
    for pdf in (gro, permit, garbled):
        pdf.write_bytes(b"synthetic")
    text = {
        gro: OCRText("ГПЗУ: градостроительный план земельного участка", source="text_layer"),
        permit: OCRText("Разрешение на строительство без номера", source="text_layer"),
        garbled: OCRText("%% ? ? ?", source="text_layer"),
    }
    monkeypatch.setattr(app, "read_ocr", lambda pdf, *args, **kwargs: (text[pdf], 1))

    records, documents = app.collect(tmp_path, 400, 0, pdfs=[gro, permit, garbled])

    assert records == {}
    by_file = {Path(item["file"]): item for item in documents}
    assert by_file[gro]["outcome"] == "out_of_scope"
    assert by_file[gro]["warnings"] == ["out_of_scope"]
    assert "error" not in by_file[gro]
    assert by_file[permit]["outcome"] == "unidentified_permit"
    assert by_file[garbled]["outcome"] == "unidentified_permit"
