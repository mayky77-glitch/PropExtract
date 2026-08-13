"""Synthetic regressions for calendar quarantine and raster field quality."""
from __future__ import annotations

from pathlib import Path

from rns_import_server import app
from rns_import_server.ocr import OCRLine, OCRText, OCRWord
from rns_import_server.rns_adapter import extract


NUMBER = "RU-12345678-09-2026"


def test_invalid_changed_date_keeps_extension_and_other_document_evidence(monkeypatch, tmp_path: Path):
    pdf = tmp_path / f"Продление РНС {NUMBER} до 17.12.2026.pdf"
    pdf.write_bytes(b"synthetic")
    text = OCRText(
        f"""Номер разрешения на строительство: {NUMBER}
Дата последнего изменения: 11.41.2025
Разработчик ПД: ООО «Надёжный проектировщик»
""",
        source="text_layer",
    )
    monkeypatch.setattr(app, "read_ocr", lambda *args, **kwargs: (text, 3))
    records, documents = app.collect(tmp_path, 180, 0, pdfs=[pdf])

    record = records[NUMBER]
    assert record["end"] == "17.12.2026"
    assert record["developer"] == "ООО «Надёжный проектировщик»"
    assert record["field_sources"]["end"] == str(pdf.resolve())
    assert record["changed"] is None
    assert "invalid_date:changed" in record["warnings"]
    assert documents[0]["pages"] == 3
    assert documents[0]["ocr_characters"] == len(text)
    assert documents[0]["outcome"] == "processed_rns"


def test_low_confidence_raster_field_is_review_only_with_bounded_confidence():
    value = f"Номер разрешения на строительство: {NUMBER}\nРазработчик ПД: ООО Проект"
    words = tuple(OCRWord(token, 10 + index * 30, 20, 20, 10, 24.0) for index, token in enumerate(value.replace("\n", " ").split()))
    text = OCRText(value, (OCRLine(1, 10000, 1000, words),), source="raster")

    record = extract(Path("permit.pdf"), text)

    assert record is not None
    assert record["field_quality"]["developer"] == {"status": "review", "reason": "low_ocr_confidence", "confidence": 24.0}


def test_invalid_labeled_issue_uses_valid_filename_date_with_filename_provenance():
    pdf = Path(f"Разрешение {NUMBER} от 03.02.2026.pdf")
    record = extract(pdf, f"Номер разрешения на строительство: {NUMBER}\nДата выдачи: 11.41.2025")

    assert record is not None
    assert record["issue"] == "03.02.2026"
    assert record["field_provenance"]["issue"] == "filename"
    assert "invalid_date:issue" in record["warnings"]


def test_filename_extension_date_has_no_ocr_quality_verdict():
    pdf = Path(f"Продление РНС {NUMBER} до 17.12.2026.pdf")
    value = f"Номер разрешения на строительство: {NUMBER}\nСрок действия: 17.12.2025"
    words = tuple(OCRWord(token, 10 + index * 30, 20, 20, 10, 24.0) for index, token in enumerate(value.split()))

    record = extract(pdf, OCRText(value, (OCRLine(1, 10000, 1000, words),), source="raster"))

    assert record is not None
    assert record["field_provenance"]["end"] == "filename"
    assert "end" not in record.get("field_quality", {})
