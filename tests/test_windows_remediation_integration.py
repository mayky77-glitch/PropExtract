"""Public-flow boundary acceptance for the Windows remediation."""
from __future__ import annotations

from pathlib import Path

from rns_import_server import app
from rns_import_server.ocr import OCRText


def test_permit_filename_with_gpzu_reference_is_not_preclassified_before_ocr(monkeypatch, tmp_path: Path):
    """A later GPZU reference cannot outrank permit evidence in the basename."""
    pdf = tmp_path / "Разрешение по ГПЗУ.pdf"
    pdf.write_bytes(b"synthetic")
    calls: list[tuple[Path, bool]] = []

    def reader(source: Path, *_args, force_ocr: bool = False, **_kwargs):
        calls.append((source, force_ocr))
        return OCRText("Разрешение на строительство без номера", source="text_layer"), 1

    monkeypatch.setattr(app, "read_ocr", reader)

    records, documents = app.collect(tmp_path, 400, 0, pdfs=[pdf])

    assert records == {}
    assert calls == [(pdf, False), (pdf, True)]
    assert documents[0]["outcome"] == "unidentified_permit"
    assert documents[0]["ocr_trace"]["route"] == "text_layer"


def test_rns_identity_in_filename_outranks_gpzu_reference(monkeypatch, tmp_path: Path):
    number = "RU-12345678-09-2026"
    pdf = tmp_path / f"РНС {number} по ГПЗУ.pdf"
    pdf.write_bytes(b"synthetic")
    calls: list[Path] = []

    def reader(source: Path, *_args, **_kwargs):
        calls.append(source)
        return OCRText(f"Номер разрешения на строительство: {number}", source="text_layer"), 1

    monkeypatch.setattr(app, "read_ocr", reader)

    records, documents = app.collect(tmp_path, 180, 0, pdfs=[pdf])

    assert calls == [pdf]
    assert list(records) == [number]
    assert documents[0]["outcome"] == "processed_rns"


def test_leading_gpzu_type_outranks_later_rns_reference(monkeypatch, tmp_path: Path):
    number = "RU-12345678-09-2026"
    pdf = tmp_path / f"ГПЗУ для РНС {number}.pdf"
    pdf.write_bytes(b"synthetic")
    monkeypatch.setattr(
        app,
        "read_ocr",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("context file must skip OCR")),
    )

    records, documents = app.collect(tmp_path, 180, 0, pdfs=[pdf])

    assert records == {}
    assert len(documents) == 1
    assert documents[0]["outcome"] == "out_of_scope"
    assert documents[0]["ocr_trace"]["route"] == "preclassified_title"
