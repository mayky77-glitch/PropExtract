"""Privacy and typed OCR-observability contracts for import reports."""
from __future__ import annotations

import json
from pathlib import Path

from rns_import_server import app
from rns_import_server.ocr import OCRText


NUMBER = "RU-12345678-09-2026"


def test_safe_report_projection_is_recursive_and_does_not_mutate_internal_paths(tmp_path: Path):
    source = tmp_path / "private" / "permit.pdf"
    result = {
        "documents": [
            {
                "file": str(source),
                "ocr_text": "raw OCR must not escape",
                "stdout": "OCR subprocess output must not escape",
                "technical_error": (
                    f"Не удалось прочитать '{source.parent / 'Secret Project' / source.name}', "
                    "'C:\\Users\\Operator\\Secret Project\\permit.pdf' и "
                    "'\\\\server\\share\\Secret Folder\\permit.pdf'; "
                    "повтор Failed /Users/operator/Secret Project/permit.pdf и "
                    "каталог /Users/operator/Secret Project/"
                ),
                "nested": {"text": "also raw", "source": str(source)},
            }
        ],
        "selected_records": {NUMBER: {"pdf": str(source), "field_sources": {"object": str(source)}}},
        "input_hashes": {str(source): "digest"},
        "windows_directory": "C:\\Users\\Operator\\Secret Folder\\",
        "unc_directory": "\\\\server\\share\\Secret Folder\\",
        "capability": "must-never-reach-a-disk-report",
    }

    projected = app.safe_report_projection(result)
    encoded = json.dumps(projected, ensure_ascii=False)

    assert str(source) not in encoded
    assert "raw OCR must not escape" not in encoded
    assert "OCR subprocess output must not escape" not in encoded
    assert "also raw" not in encoded
    assert "must-never-reach-a-disk-report" not in encoded
    assert str(source) not in encoded
    assert "Secret Project" not in encoded
    assert "Operator" not in encoded
    assert projected["documents"][0]["technical_error"].count("[локальный путь]") == 4
    assert projected["documents"][0]["file"] == source.name
    assert projected["selected_records"][NUMBER]["pdf"] == source.name
    assert projected["input_hashes"] == {source.name: "digest"}
    assert projected["windows_directory"] == "Secret Folder"
    assert projected["unc_directory"] == "Secret Folder"
    assert result["documents"][0]["file"] == str(source)
    assert result["documents"][0]["ocr_text"] == "raw OCR must not escape"
    assert result["capability"] == "must-never-reach-a-disk-report"


def test_collect_emits_exact_typed_trace_and_run_aggregate(monkeypatch, tmp_path: Path):
    pdf = tmp_path / "Разрешение.pdf"
    pdf.write_bytes(b"pdf")
    text = OCRText(
        f"Номер разрешения на строительство: {NUMBER}",
        source="raster",
        trace={
            "ocr_trace_version": 1,
            "route": "raster",
            "requested_dpi": 180,
            "effective_dpi": 180,
            "total_pages": 2,
            "processed_pages": 2,
            "tesseract_calls": 2,
            "tesseract_started": True,
            "fallback_reason": None,
            "timings_ms": {"page_count": 1, "text_layer": 0, "render": 2, "tesseract": 3, "total": 6},
        },
    )
    monkeypatch.setattr(app, "read_ocr", lambda *args, **kwargs: (text, 2))

    records, documents = app.collect(tmp_path, 180, 0, pdfs=[pdf])
    trace = documents[0]["ocr_trace"]
    aggregate = app._aggregate_ocr_traces(documents)

    assert list(records) == [NUMBER]
    assert set(trace) == {"ocr_trace_version", "route", "requested_dpi", "effective_dpi", "total_pages", "processed_pages", "tesseract_calls", "tesseract_started", "fallback_reason", "timings_ms", "dpi", "pages", "ocr_calls"}
    assert trace["ocr_trace_version"] == 1
    assert trace["route"] == "raster"
    assert trace["dpi"] == trace["effective_dpi"]
    assert trace["pages"] == trace["processed_pages"]
    assert trace["ocr_calls"] == trace["tesseract_calls"]
    assert all(isinstance(trace["timings_ms"][stage], int) and trace["timings_ms"][stage] >= 0 for stage in ("page_count", "text_layer", "render", "tesseract", "total"))
    assert aggregate["document_count"] == 1
    assert aggregate["input_document_count"] == 1
    assert aggregate["untraced_document_count"] == 0
    assert aggregate["failed_document_count"] == 0
    assert aggregate["tesseract_calls"] == 2
    assert "permit.pdf" not in json.dumps({"trace": trace, "aggregate": aggregate})


def test_processing_failure_still_has_typed_trace_and_complete_aggregate(monkeypatch, tmp_path: Path):
    pdf = tmp_path / "Разрешение.pdf"
    pdf.write_bytes(b"pdf")
    monkeypatch.setattr(app, "read_ocr", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("pdfinfo_failed")))

    records, documents = app.collect(tmp_path, 400, 0, pdfs=[pdf])
    aggregate = app._aggregate_ocr_traces(documents)

    assert records == {}
    assert documents[0]["outcome"] == "processing_failed"
    trace = documents[0]["ocr_trace"]
    assert trace["route"] == "failed"
    assert trace["fallback_reason"] == "processing_failed"
    assert trace["dpi"] == 400 and trace["pages"] == 0 and trace["ocr_calls"] == 0
    assert aggregate["input_document_count"] == aggregate["document_count"] == 1
    assert aggregate["untraced_document_count"] == 0
    assert aggregate["failed_document_count"] == 1


def test_post_read_parser_failure_counts_as_failed_without_losing_ocr_route(monkeypatch, tmp_path: Path):
    pdf = tmp_path / "Разрешение.pdf"
    pdf.write_bytes(b"pdf")
    monkeypatch.setattr(app, "read_ocr", lambda *_args, **_kwargs: (OCRText("permit", source="text_layer"), 1))
    monkeypatch.setattr(app, "extract", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("parser_failed")))

    _, documents = app.collect(tmp_path, 180, 0, pdfs=[pdf])
    aggregate = app._aggregate_ocr_traces(documents)

    assert documents[0]["outcome"] == "processing_failed"
    assert documents[0]["ocr_trace"]["route"] == "text_layer"
    assert aggregate["failed_document_count"] == 1


def test_retry_failure_is_visible_in_existing_trace(monkeypatch, tmp_path: Path):
    pdf = tmp_path / "Разрешение.pdf"
    pdf.write_bytes(b"pdf")

    def reader(_source: Path, _dpi: int, _pages: int, *, force_ocr: bool = False):
        if force_ocr:
            raise RuntimeError("native retry detail")
        return OCRText("Разрешение на строительство без номера", source="text_layer"), 1

    monkeypatch.setattr(app, "read_ocr", reader)
    _, documents = app.collect(tmp_path, 400, 0, pdfs=[pdf])

    assert documents[0]["warnings"] == ["identity_retry_failed"]
    assert documents[0]["ocr_trace"]["route"] == "text_layer"
    assert documents[0]["ocr_trace"]["fallback_reason"] == "identity_retry_failed"
