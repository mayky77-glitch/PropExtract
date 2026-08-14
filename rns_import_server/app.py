#!/usr/bin/env python3
"""Local CLI and HTTP orchestration for PDF-to-RNS workbook imports."""
from __future__ import annotations

import argparse
import inspect
import json
import ntpath
import re
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Callable

try:
    from rns_import_server.audit import atomic_json, digest, sha256
    from rns_import_server.files import discover_pdfs
    from rns_import_server.mapping import map_extracted_record
    from rns_import_server.normalization import canonical_rns_identities, field_comparison_equal
    from rns_import_server.ocr import read as read_ocr
    from rns_import_server.rns_adapter import date, extract
    from rns_import_server.workbook import apply
except ModuleNotFoundError:  # Direct ``python rns_import_server/app.py`` invocation.
    from audit import atomic_json, digest, sha256
    from files import discover_pdfs
    from mapping import map_extracted_record
    from normalization import canonical_rns_identities, field_comparison_equal
    from ocr import read as read_ocr
    from rns_adapter import date, extract
    from workbook import apply

EVIDENCE_FIELDS = ("issue", "end", "changed", "issuer", "developer", "builder", "district", "region", "stage", "object")
DATE_FIELDS = ("issue", "end", "changed")
MERGE_CONSENSUS_FIELDS = tuple(field for field in EVIDENCE_FIELDS if field not in {"end", "changed"})
FIELD_LABELS = {
    "issue": "Дата выдачи",
    "issuer": "Орган выдачи",
    "developer": "Разработчик ПД",
    "builder": "Застройщик",
    "district": "Муниципальный р-н",
    "region": "Субъект РФ",
    "stage": "Номер этапа",
    "object": "Наименование объекта",
}
IDENTITY_RETRY_DPI = 400
IDENTITY_RETRY_MAX_PAGES = 10
OCR_TRACE_VERSION = 1
_TRACE_TIMING_STAGES = ("page_count", "text_layer", "render", "tesseract", "total")
_PERMIT_BASENAME = re.compile(r"(?<![А-Яа-яЁё])разреш[её]н[А-Яа-яЁё-]*", re.IGNORECASE)
_PERMIT_MARKER = re.compile(r"(?<![А-Яа-яЁё])рнс(?![А-Яа-яЁё])", re.IGNORECASE)
_PERMIT_TEXT = re.compile(r"разрешени\w*\s+на\s+строительств\w*|номер\s+разрешения\s+на\s+строительств\w*", re.IGNORECASE)
_OUT_OF_SCOPE_TEXT = re.compile(r"\b(?:гро|ро|гпзу)\b|градостроительн\w*\s+план", re.IGNORECASE)
_OUT_OF_SCOPE_TITLE = re.compile(r"^\s*(?:(?:гро|ро|гпзу)\b|градостроительн\w*\s+план)", re.IGNORECASE)
_OUT_OF_SCOPE_BASENAME = re.compile(
    r"^\s*(?:\d+(?:[._-]\d+)*[.)_-]?\s*)?"
    r"(?:(?:гро|ро|гпзу)\b|градостроительн\w*\s+план)",
    re.IGNORECASE,
)
_QUOTED_LOCAL_PATH = re.compile(
    r"(?P<quote>['\"])(?P<path>(?:[A-Z]:[\\/]|\\\\[^\\/\r\n'\"]+[\\/][^\\/\r\n'\"]+|/)"
    r"[^'\"\r\n]*)(?P=quote)",
    re.IGNORECASE,
)
_UNQUOTED_POSIX_PATH_WITH_SPACES = re.compile(
    r"(?<![:\w])/(?:[^/\s:'\"<>|]+/)+(?:[^\s,;:'\"<>|]+(?:\s+[^\s,;:'\"<>|]+)*/)*"
    r"(?:[^\s,;:'\"<>|]+)?"
)
_WINDOWS_PATH_IN_TEXT = re.compile(
    r"(?i)(?<![0-9A-ZА-ЯЁ])(?:[A-Z]:[\\/]|\\\\[^\\/\s]+[\\/][^\\/\s]+[\\/])"
    r"(?:[^\\/:*?\"<>|'\r\n]+[\\/])*[^\\/:*?\"<>|'\r\n]+"
)
_POSIX_PATH_IN_TEXT = re.compile(r"(?<![:\w])/(?:[^/\s:'\"<>|]+/)*[^/\s:'\"<>|]+")
_REPORT_OMITTED_KEYS = {
    "authorization",
    "capability",
    "captured_text",
    "ocr_output",
    "ocr_text",
    "password",
    "raw_ocr_text",
    "raw_text",
    "secret",
    "stderr",
    "stdout",
    "text",
    "token",
}
_REPORT_DIAGNOSTIC_KEYS = {"error", "technical_error", "message"}
ProgressCallback = Callable[[int, str, str | None], None]


def _is_amendment(record: dict) -> bool:
    source = str(record.get("filename", "")).casefold()
    return any(token in source for token in ("измен", "продлен", "продлён", "приказ", "распоряжен", "extension", "amendment"))


def _evidence_count(record: dict) -> int:
    return sum(record.get(field) is not None for field in EVIDENCE_FIELDS)


def _parsed_date(value: object) -> datetime | None:
    try:
        return date(value) if isinstance(value, str) else None
    except (TypeError, ValueError):
        return None


def _adopt_directive_field(merged: dict, directive: dict, field: str) -> None:
    merged[field] = directive[field]
    merged["field_provenance"][field] = directive.get("field_provenance", {}).get(field, "ocr")
    merged["field_sources"][field] = str(directive["pdf"])
    quality = directive.get("field_quality", {})
    if isinstance(quality, dict) and isinstance(quality.get(field), dict):
        merged.setdefault("field_quality", {})[field] = dict(quality[field])
    elif isinstance(merged.get("field_quality"), dict):
        merged["field_quality"].pop(field, None)


def _adopt_primary_source(merged: dict, directive: dict) -> None:
    """Keep row-level source link aligned with a winning amendment."""
    merged["pdf"] = directive["pdf"]
    merged["filename"] = directive["filename"]


def _winning_date_directive(merged: dict, directives: list[dict], field: str) -> dict | None:
    """Select one strictly newer dated source independent of input order."""
    current = merged.get(field)
    current_date = _parsed_date(current)
    candidates = [
        directive
        for directive in directives
        if (proposed_date := _parsed_date(directive.get(field)))
        and (current_date is None or proposed_date > current_date)
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda directive: (
            _parsed_date(directive.get(field)) or datetime.min,
            str(directive["filename"]),
            str(directive["pdf"]),
        ),
    )


def _record_sort_key(record: dict) -> tuple[int, datetime, str, str]:
    return (
        _evidence_count(record),
        _parsed_date(record.get("changed")) or datetime.min,
        str(record.get("filename", "")),
        str(record.get("pdf", "")),
    )


def _consensus_equal(field: str, left: object, right: object) -> bool:
    if field == "issue":
        return _parsed_date(left) is not None and _parsed_date(left) == _parsed_date(right)
    return field_comparison_equal(FIELD_LABELS[field], str(left), str(right))


def _directive_consensus(directives: list[dict], field: str) -> tuple[dict | None, bool]:
    groups: list[list[dict]] = []
    for directive in directives:
        value = directive.get(field)
        if value is None or (field == "issue" and _parsed_date(value) is None):
            continue
        group = next(
            (items for items in groups if _consensus_equal(field, items[0][field], value)),
            None,
        )
        if group is None:
            groups.append([directive])
        else:
            group.append(directive)
    if len(groups) > 1:
        return None, True
    if not groups:
        return None, False
    return max(groups[0], key=lambda item: (str(item["filename"]), str(item["pdf"]))), False


def _append_merge_conflict(merged: dict, field: str) -> None:
    code = f"conflicting_directive_field:{field}"
    message = (
        f"Связанные изменения содержат разные значения поля «{FIELD_LABELS[field]}»; "
        "автоматический перенос поля не выполнен."
    )
    merged.setdefault("merge_issues", []).append({"code": code, "field": field, "message": message})


def _finalize_warnings(merged: dict, records: list[dict]) -> None:
    warnings = [
        warning
        for warning in merged.get("warnings", [])
        if warning not in EVIDENCE_FIELDS or merged.get(warning) is None
    ]
    for field in EVIDENCE_FIELDS:
        if merged.get(field) is None and field not in warnings:
            warnings.append(field)
    for field in DATE_FIELDS:
        invalid_seen = any(record.get(field) is not None and _parsed_date(record.get(field)) is None for record in records)
        if merged.get(field) is None and invalid_seen:
            code = f"invalid_date:{field}"
            if code not in warnings:
                warnings.append(code)
    for issue in merged.get("merge_issues", []):
        if issue["code"] not in warnings:
            warnings.append(issue["code"])
    merged["warnings"] = warnings


def _document_title(text: str) -> str:
    """Use only the opening title block; later body mentions are not type evidence."""
    lines = [line for line in text.splitlines() if line.strip()]
    return "\n".join(lines[:3])[:600]


def _is_permit_like(pdf: Path, text: str) -> bool:
    if _OUT_OF_SCOPE_BASENAME.search(pdf.stem.replace("_", " ")):
        return False
    return (
        _PERMIT_BASENAME.search(pdf.stem) is not None
        or _PERMIT_MARKER.search(pdf.stem) is not None
        or bool(canonical_rns_identities(pdf.stem))
        or _PERMIT_TEXT.search(_document_title(text)) is not None
    )


def _is_strong_out_of_scope(pdf: Path, text: str) -> bool:
    return (
        _OUT_OF_SCOPE_BASENAME.search(pdf.stem.replace("_", " ")) is not None
        or _OUT_OF_SCOPE_TITLE.search(_document_title(text)) is not None
    )


def _should_retry_identity(pdf: Path, text: str = "", source: str | None = None) -> bool:
    """Allow one recovery pass without escalating neutral raster misses."""
    if source == "text_layer":
        return _is_permit_like(pdf, text) or not _is_strong_out_of_scope(pdf, text)
    return _is_permit_like(pdf, text)


def _read_supports_force_ocr() -> bool:
    parameters = inspect.signature(read_ocr).parameters.values()
    return any(
        parameter.name == "force_ocr" or parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )


def _forced_raster_read(pdf: Path, dpi: int, max_pages: int):
    """Request real raster OCR, while keeping old three-argument test doubles usable."""
    if _read_supports_force_ocr():
        return read_ocr(pdf, dpi, max_pages, force_ocr=True)
    return read_ocr(pdf, dpi, max_pages)


def _document_outcome(pdf: Path, text: str, record: dict | None) -> str:
    if record and record.get("number"):
        return "processed_rns"
    if _is_permit_like(pdf, text):
        return "unidentified_permit"
    # A context document may be skipped only when its own filename/title says
    # so. A later-body reference is not evidence of a document type.
    if _is_strong_out_of_scope(pdf, text):
        return "out_of_scope"
    return "unidentified_permit"


def _trace_for_read(text: object, pages: int, dpi: int) -> dict[str, object]:
    """Normalize product and legacy-double OCR metadata to one public schema."""
    source = getattr(text, "source", "raster")
    raw = getattr(text, "trace", {})
    raw = raw if isinstance(raw, dict) else {}
    timings = raw.get("timings_ms", {})
    timings = timings if isinstance(timings, dict) else {}
    calls = raw.get("tesseract_calls", 0 if source == "text_layer" else 0)
    try:
        calls = max(0, int(calls))
    except (TypeError, ValueError):
        calls = 0
    return _with_trace_compatibility_aliases({
        "ocr_trace_version": OCR_TRACE_VERSION,
        "route": source if source in {"text_layer", "raster"} else "unknown",
        "requested_dpi": int(raw.get("requested_dpi", dpi)),
        "effective_dpi": int(raw.get("effective_dpi", dpi)),
        "total_pages": max(0, int(raw.get("total_pages", pages))),
        "processed_pages": max(0, int(raw.get("processed_pages", pages))),
        "tesseract_calls": calls,
        "tesseract_started": bool(raw.get("tesseract_started", calls)),
        "fallback_reason": raw.get("fallback_reason") if isinstance(raw.get("fallback_reason"), str) else None,
        "timings_ms": {
            stage: max(0, int(timings.get(stage, 0)))
            for stage in _TRACE_TIMING_STAGES
        },
    })


def _with_trace_compatibility_aliases(trace: dict[str, object]) -> dict[str, object]:
    """Keep the Windows tester's compact trace fields beside richer schema."""
    trace.update(
        dpi=int(trace["effective_dpi"]),
        pages=int(trace["processed_pages"]),
        ocr_calls=max(0, int(trace["tesseract_calls"])),
    )
    return trace


def _failure_trace(dpi: int, *, reason: str, elapsed_ms: int = 0) -> dict[str, object]:
    """Describe a failed read without inventing native-tool progress."""
    return _with_trace_compatibility_aliases({
        "ocr_trace_version": OCR_TRACE_VERSION,
        "route": "failed",
        "requested_dpi": dpi,
        "effective_dpi": dpi,
        "total_pages": 0,
        "processed_pages": 0,
        "tesseract_calls": 0,
        "tesseract_started": False,
        "fallback_reason": reason,
        "timings_ms": {
            stage: (max(0, int(elapsed_ms)) if stage == "total" else 0)
            for stage in _TRACE_TIMING_STAGES
        },
    })


def _combine_retry_trace(initial: dict[str, object], retry: dict[str, object], reason: str) -> dict[str, object]:
    return _with_trace_compatibility_aliases({
        "ocr_trace_version": OCR_TRACE_VERSION,
        "route": (
            f"{initial['route']}_then_{retry['route']}"
            if initial["route"] != retry["route"]
            else initial["route"]
        ),
        "requested_dpi": initial["requested_dpi"],
        "effective_dpi": retry["effective_dpi"],
        "total_pages": retry["total_pages"],
        "processed_pages": retry["processed_pages"],
        "tesseract_calls": int(initial["tesseract_calls"]) + int(retry["tesseract_calls"]),
        "tesseract_started": bool(initial["tesseract_started"] or retry["tesseract_started"]),
        "fallback_reason": reason,
        "timings_ms": {
            stage: int(initial["timings_ms"][stage]) + int(retry["timings_ms"][stage])
            for stage in _TRACE_TIMING_STAGES
        },
    })


def _aggregate_ocr_traces(documents: list[dict]) -> dict[str, object]:
    traces = [item.get("ocr_trace") for item in documents if isinstance(item.get("ocr_trace"), dict)]
    return {
        "ocr_trace_version": OCR_TRACE_VERSION,
        "input_document_count": len(documents),
        "document_count": len(traces),
        "untraced_document_count": len(documents) - len(traces),
        "failed_document_count": sum(1 for item in documents if item.get("outcome") == "processing_failed"),
        "route_counts": {
            route: sum(1 for trace in traces if trace.get("route") == route)
            for route in sorted({str(trace.get("route")) for trace in traces})
        },
        "total_pages": sum(int(trace["total_pages"]) for trace in traces),
        "processed_pages": sum(int(trace["processed_pages"]) for trace in traces),
        "tesseract_calls": sum(int(trace["tesseract_calls"]) for trace in traces),
        "tesseract_started_count": sum(1 for trace in traces if trace.get("tesseract_started")),
        "timings_ms": {
            stage: sum(int(trace["timings_ms"][stage]) for trace in traces)
            for stage in _TRACE_TIMING_STAGES
        },
    }


def _preclassified_out_of_scope_document(pdf: Path, dpi: int) -> dict[str, object]:
    """Skip OCR only for an unambiguous filename-level context document."""
    return {
        "file": str(pdf),
        "pages": 0,
        "ocr_characters": 0,
        "number": None,
        "extracted": {},
        "warnings": ["out_of_scope"],
        "outcome": "out_of_scope",
        "ocr_trace": _with_trace_compatibility_aliases({
            "ocr_trace_version": OCR_TRACE_VERSION,
            "route": "preclassified_title",
            "requested_dpi": dpi,
            "effective_dpi": dpi,
            "total_pages": 0,
            "processed_pages": 0,
            "tesseract_calls": 0,
            "tesseract_started": False,
            "fallback_reason": "strong_out_of_scope_filename",
            "timings_ms": {stage: 0 for stage in _TRACE_TIMING_STAGES},
        }),
    }


def _is_absolute_local_path(value: str) -> bool:
    return Path(value).is_absolute() or ntpath.isabs(value)


def _safe_report_string(value: str, key: str | None = None) -> str:
    if _is_absolute_local_path(value):
        normalized = value.replace("/", "\\")
        if re.fullmatch(r"[A-Za-z]:\\*|\\\\[^\\]+\\[^\\]+\\*", normalized):
            return "[локальный путь]"
        return ntpath.basename(normalized.rstrip("\\")) or "[локальный путь]"
    if (key or "").casefold() in _REPORT_DIAGNOSTIC_KEYS:
        value = _QUOTED_LOCAL_PATH.sub(
            lambda match: f"{match.group('quote')}[локальный путь]{match.group('quote')}",
            value,
        )
        value = _UNQUOTED_POSIX_PATH_WITH_SPACES.sub("[локальный путь]", value)
        value = _WINDOWS_PATH_IN_TEXT.sub("[локальный путь]", value)
        value = _POSIX_PATH_IN_TEXT.sub("[локальный путь]", value)
    return value


def safe_report_projection(value: object, key: str | None = None) -> object:
    """Return a disk-safe copy without OCR content or absolute local paths.

    The caller's in-memory result remains untouched for server-held capability
    actions. This is deliberately recursive because records nest source maps.
    """
    normalized_key = (key or "").casefold()
    if normalized_key in _REPORT_OMITTED_KEYS:
        return None
    if isinstance(value, dict):
        projected: dict[str, object] = {}
        for index, (item_key, item_value) in enumerate(value.items(), start=1):
            original_key = str(item_key)
            if original_key.casefold() in _REPORT_OMITTED_KEYS:
                continue
            safe_key = _safe_report_string(original_key, "message")
            if safe_key in projected:
                safe_key = f"{safe_key} ({index})"
            projected[safe_key] = safe_report_projection(item_value, original_key)
        return projected
    if isinstance(value, list):
        return [safe_report_projection(item, key) for item in value]
    if isinstance(value, tuple):
        return [safe_report_projection(item, key) for item in value]
    if isinstance(value, str):
        return _safe_report_string(value, key)
    return value


def _identity_retry_page_limit(max_pages: int, total_pages: int) -> int:
    requested = max_pages if max_pages > 0 else IDENTITY_RETRY_MAX_PAGES
    return min(max(total_pages, 1), requested, IDENTITY_RETRY_MAX_PAGES)


def _merge_group(number: str, versions: list[dict], documents: list[dict]) -> dict | None:
    """Keep a substantive permit, then fill its gaps from identified directives only."""
    permits = [record for record in versions if not _is_amendment(record)]
    directives = [record for record in versions if _is_amendment(record)]
    source_records = permits or directives
    if not source_records:
        return None
    selected = max(source_records, key=_record_sort_key)
    merged = dict(selected)
    merged["ocr_traces"] = [
        dict(record["ocr_trace"])
        for record in versions
        if isinstance(record.get("ocr_trace"), dict)
    ]
    merged["field_provenance"] = dict(selected.get("field_provenance", {}))
    merged["field_sources"] = {field: str(selected["pdf"]) for field in EVIDENCE_FIELDS if selected.get(field) is not None}
    merged["merge_issues"] = list(selected.get("merge_issues", []))
    if not permits:
        # Directive-only records may update one proven existing row, never add.
        # Build evidence across every same-ID directive instead of trusting one.
        merged["existing_only"] = True
        for field in EVIDENCE_FIELDS:
            merged[field] = None
        merged["field_provenance"] = {}
        merged["field_sources"] = {}
        merged["field_quality"] = {}
    else:
        for field in DATE_FIELDS:
            if merged.get(field) is not None and _parsed_date(merged.get(field)) is None:
                merged[field] = None
                merged["field_provenance"].pop(field, None)
                merged["field_sources"].pop(field, None)
                if isinstance(merged.get("field_quality"), dict):
                    merged["field_quality"].pop(field, None)
    merged["source_files"] = sorted(
        {str(record["filename"]) for record in ([selected] if permits else directives)},
        key=str.casefold,
    )
    linked_directives: list[dict] = []
    for directive in directives:
        # Explicit canonical ID is supplied by the parser; evidence must be
        # material before a directive can enrich a permit.
        if directive.get("number") != number or _evidence_count(directive) == 0:
            diagnostic = next(
                (item for item in documents if item.get("file") == directive.get("pdf")),
                None,
            )
            if diagnostic is not None:
                diagnostic["warnings"] = ["unlinked_directive"]
                diagnostic["error"] = "Изменение/продление не связано: недостаточно подтверждённых данных."
            else:
                # Direct unit callers may not supply the collect-time document.
                documents.append({"file": directive["pdf"], "pages": directive.get("pages"), "ocr_characters": None, "number": number, "extracted": {}, "warnings": ["unlinked_directive"], "error": "Изменение/продление не связано: недостаточно подтверждённых данных.", "ocr_trace": directive.get("ocr_trace")})
            continue
        linked_directives.append(directive)
    merged["source_files"] = sorted(
        set(merged["source_files"]) | {str(record["filename"]) for record in linked_directives},
        key=str.casefold,
    )
    for field in MERGE_CONSENSUS_FIELDS:
        if merged.get(field) is not None:
            continue
        winner, conflict = _directive_consensus(linked_directives, field)
        if conflict:
            _append_merge_conflict(merged, field)
        elif winner is not None:
            _adopt_directive_field(merged, winner, field)
    winning_dates = {
        field: winner
        for field in ("end", "changed")
        if (winner := _winning_date_directive(merged, linked_directives, field)) is not None
    }
    for field, winner in winning_dates.items():
        _adopt_directive_field(merged, winner, field)
    if primary := winning_dates.get("changed") or winning_dates.get("end"):
        _adopt_primary_source(merged, primary)
    _finalize_warnings(merged, versions)
    return merged


def collect(
    pdf_dir: Path,
    dpi: int,
    max_pages: int,
    progress: ProgressCallback | None = None,
    pdfs: list[Path] | None = None,
) -> tuple[dict[str, dict], list[dict]]:
    if max_pages < 0:
        raise ValueError("Количество страниц для распознавания не может быть отрицательным")
    groups: dict[str, list[dict]] = {}
    documents: list[dict] = []
    pdfs = pdfs if pdfs is not None else discover_pdfs(pdf_dir)
    for index, pdf in enumerate(pdfs, start=1):
        if progress:
            progress(8 + int((index - 1) / len(pdfs) * 68), "Распознаём PDF", pdf.name)
        # A permit basename may legitimately mention GPZU/ГРО/РО. Only a
        # context-document filename without stronger permit evidence may skip
        # OCR before its title/body can be classified.
        if not _is_permit_like(pdf, "") and _is_strong_out_of_scope(pdf, ""):
            documents.append(_preclassified_out_of_scope_document(pdf, dpi))
            if progress:
                progress(8 + int(index / len(pdfs) * 68), "PDF обработан", pdf.name)
            continue
        try:
            processing_started = time.monotonic()
            trace: dict[str, object] | None = None
            text, pages = read_ocr(pdf, dpi, max_pages)
            trace = _trace_for_read(text, pages, dpi)
            extracted = extract(pdf, text)
            retry_error: str | None = None
            text_source = getattr(text, "source", None)
            if (
                extracted is None
                and not canonical_rns_identities(text)
                and _should_retry_identity(pdf, text, text_source)
                and not (text_source == "raster" and dpi >= IDENTITY_RETRY_DPI)
            ):
                try:
                    # A failed text layer gets one real raster pass at the current
                    # 180-DPI default. A real raster miss can make one bounded
                    # 400-DPI fallback; neither path re-enters pdftotext.
                    retry_dpi = IDENTITY_RETRY_DPI if text_source == "raster" else dpi
                    # Legacy three-argument doubles cannot honour force_ocr, so
                    # preserve their former 400-DPI compatibility path only there.
                    if not _read_supports_force_ocr():
                        retry_dpi = IDENTITY_RETRY_DPI
                    retry_text, retry_pages = _forced_raster_read(
                        pdf, retry_dpi, _identity_retry_page_limit(max_pages, pages)
                    )
                    retry_trace = _trace_for_read(retry_text, retry_pages, retry_dpi)
                    retry_reason = "identity_missing_raster" if text_source == "raster" else "identity_missing_text_layer"
                    trace = _combine_retry_trace(trace, retry_trace, retry_reason)
                    retry_extracted = extract(pdf, retry_text)
                    if retry_extracted is not None:
                        text, pages, extracted = retry_text, retry_pages, retry_extracted
                except Exception as error:
                    retry_error = str(error) or type(error).__name__
                    trace["fallback_reason"] = "identity_retry_failed"
            # Dormant unless an owner-approved future extractor emits candidates.
            # Without candidates/configuration this preserves prior behavior.
            record = map_extracted_record(extracted) if extracted else None
            document = {
                "file": str(pdf),
                "pages": pages,
                "ocr_characters": len(text),
                "number": record.get("number") if record else None,
                "extracted": {key: record.get(key) for key in EVIDENCE_FIELDS} if record else {},
                "warnings": record.get("warnings", []) if record else ["unidentified"],
                "outcome": _document_outcome(pdf, text, record),
                "ocr_trace": trace,
            }
            trace["timings_ms"]["total"] = max(
                int(trace["timings_ms"]["total"]),
                int((time.monotonic() - processing_started) * 1000),
            )
            ocr_source = getattr(text, "source", None)
            if ocr_source in {"text_layer", "raster"}:
                document["ocr_source"] = ocr_source
            if record and record.get("number"):
                record["pages"] = pages
                record["ocr_trace"] = trace
                if ocr_source in {"text_layer", "raster"}:
                    record["ocr_source"] = ocr_source
                groups.setdefault(str(record["number"]), []).append(record)
            elif retry_error:
                document["warnings"] = ["identity_retry_failed"]
                document["error"] = (
                    "Повторное распознавание номера РНС при 400 DPI завершилось ошибкой."
                    if retry_dpi == IDENTITY_RETRY_DPI
                    else "Принудительное растровое распознавание номера РНС завершилось ошибкой."
                )
                document["technical_error"] = retry_error
            elif record and _is_amendment(record):
                document["warnings"] = ["unlinked_directive"]
                document["error"] = "Изменение/продление не связано: отсутствует явный номер РНС."
            elif document["outcome"] == "out_of_scope":
                document["warnings"] = ["out_of_scope"]
            else:
                document["error"] = "Не найден номер РНС"
            documents.append(document)
        except Exception as error:
            elapsed_ms = int((time.monotonic() - processing_started) * 1000) if "processing_started" in locals() else 0
            failed_trace = trace if "trace" in locals() and isinstance(trace, dict) else _failure_trace(
                dpi,
                reason="processing_failed",
                elapsed_ms=elapsed_ms,
            )
            failed_trace["fallback_reason"] = "processing_failed"
            failed_trace["timings_ms"]["total"] = max(
                int(failed_trace["timings_ms"]["total"]),
                elapsed_ms,
            )
            documents.append({"file": str(pdf), "pages": None, "ocr_characters": 0, "number": None, "extracted": {}, "warnings": ["processing_failed"], "outcome": "processing_failed", "error": str(error) or type(error).__name__, "ocr_trace": failed_trace})
        if progress:
            progress(8 + int(index / len(pdfs) * 68), "PDF обработан", pdf.name)
    chosen = {number: record for number, versions in groups.items() if (record := _merge_group(number, versions, documents)) is not None}
    return chosen, documents


def run(
    pdf_dir: Path,
    xlsx: Path,
    output: Path,
    dpi: int = 180,
    max_pages: int = 0,
    progress: ProgressCallback | None = None,
) -> dict:
    if progress:
        progress(2, "Проверяем пути", None)
    if not pdf_dir.is_dir() or pdf_dir.is_symlink():
        raise ValueError("pdf_dir must be a non-symlink directory")
    if not xlsx.is_file() or xlsx.is_symlink() or xlsx.suffix.lower() != ".xlsx":
        raise ValueError("xlsx must be a non-symlink .xlsx file")
    if output.suffix.lower() != ".xlsx" or output.resolve() == xlsx.resolve():
        raise ValueError("output must be a distinct .xlsx file")
    pdfs = discover_pdfs(pdf_dir)
    if not pdfs:
        raise ValueError("pdf_dir must contain non-symlink PDF files")
    if progress:
        progress(5, f"Найдено PDF: {len(pdfs)}", None)
    before = {"xlsx": sha256(xlsx), "pdfs": {str(path.relative_to(pdf_dir)): sha256(path) for path in pdfs}}
    records, documents = collect(pdf_dir, dpi, max_pages, progress, pdfs)
    if not records:
        failures = [f"{Path(str(item['file'])).name}: {item.get('error', 'номер РНС не найден')}" for item in documents]
        detail = "; ".join(failures[:3])
        if len(failures) > 3:
            detail += f"; ещё {len(failures) - 3}"
        raise RuntimeError(f"Не удалось извлечь ни одной записи РНС. {detail}")
    if progress:
        progress(80, "Переносим данные в Excel", None)
    result = apply(records, xlsx, output, before["xlsx"])
    if progress:
        progress(94, "Проверяем стили и формулы", None)
    after = {"xlsx": sha256(xlsx), "pdfs": {str(path.relative_to(pdf_dir)): sha256(path) for path in pdfs}}
    if before != after:
        output.unlink(missing_ok=True)
        raise RuntimeError("source_inputs_changed")
    selected = {
        number: {key: record.get(key) for key in ("filename", "pdf", "issue", "end", "changed", "warnings", "stage", "object", "issuer", "builder", "region", "district", "developer", "source_files", "field_sources", "field_provenance", "field_quality", "ocr_source", "ocr_trace", "ocr_traces", "merge_issues")}
        for number, record in records.items()
    }
    result.update({"contract_version": "rns-import-2", "input_hashes": before, "input_digest": digest(before), "documents": documents, "ocr_trace_summary": _aggregate_ocr_traces(documents), "logical_records": sorted(records), "selected_records": selected, "output": str(output)})
    if progress:
        progress(97, "Файл подготовлен", None)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Локальный импортёр PDF РНС → XLSX")
    commands = parser.add_subparsers(dest="command", required=True)
    process = commands.add_parser("process")
    process.add_argument("--pdf-dir", required=True, type=Path); process.add_argument("--xlsx", required=True, type=Path)
    process.add_argument("--output", required=True, type=Path); process.add_argument("--report", type=Path)
    process.add_argument("--dpi", type=int, default=180); process.add_argument("--max-pages", type=int, default=0)
    serve = commands.add_parser("serve"); serve.add_argument("--host", default="127.0.0.1"); serve.add_argument("--port", type=int, default=8775); serve.add_argument("--open-browser", action="store_true")
    options = parser.parse_args()
    if options.command == "serve":
        if options.host not in {"127.0.0.1", "localhost", "::1"}:
            parser.error("serve host must be loopback-only")
        try:
            from rns_import_server.server import create_server
        except ModuleNotFoundError:
            from server import create_server
        try:
            server = create_server(options.host, options.port, run)
        except OSError as error:
            print(f"Не удалось запустить PropExtract на порту {options.port}: {error}", file=sys.stderr)
            raise SystemExit(1) from error
        print(f"http://{options.host}:{options.port}")
        if options.open_browser:
            webbrowser.open(f"http://{options.host}:{options.port}")
        server.serve_forever()
        return
    report = options.report or options.output.with_suffix(".json")
    if report.resolve() in {options.xlsx.resolve(), options.output.resolve()}:
        parser.error("report must not collide with input or output")
    result = run(options.pdf_dir, options.xlsx, options.output, options.dpi, options.max_pages)
    atomic_json(report, safe_report_projection(result))
    print(json.dumps({"output": str(options.output), "report": str(report), "records": len(result["logical_records"]), "conflicts": len(result["conflicts"])}))


if __name__ == "__main__":
    main()
