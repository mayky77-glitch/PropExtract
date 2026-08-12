#!/usr/bin/env python3
"""Local CLI and HTTP orchestration for PDF-to-RNS workbook imports."""
from __future__ import annotations

import argparse
import json
import re
import sys
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
_PERMIT_BASENAME = re.compile(r"(?<![А-Яа-яЁё])разреш[её]н[А-Яа-яЁё-]*", re.IGNORECASE)
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


def _should_retry_identity(pdf: Path, dpi: int) -> bool:
    return dpi < IDENTITY_RETRY_DPI and _PERMIT_BASENAME.search(pdf.stem) is not None


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
    else:
        for field in DATE_FIELDS:
            if merged.get(field) is not None and _parsed_date(merged.get(field)) is None:
                merged[field] = None
                merged["field_provenance"].pop(field, None)
                merged["field_sources"].pop(field, None)
    merged["source_files"] = sorted(
        {str(record["filename"]) for record in ([selected] if permits else directives)},
        key=str.casefold,
    )
    linked_directives: list[dict] = []
    for directive in directives:
        # Explicit canonical ID is supplied by the parser; evidence must be
        # material before a directive can enrich a permit.
        if directive.get("number") != number or _evidence_count(directive) == 0:
            documents.append({"file": directive["pdf"], "pages": directive.get("pages"), "ocr_characters": None, "number": number, "extracted": {}, "warnings": ["unlinked_directive"], "error": "Изменение/продление не связано: недостаточно подтверждённых данных."})
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
        try:
            text, pages = read_ocr(pdf, dpi, max_pages)
            extracted = extract(pdf, text)
            retry_error: str | None = None
            if extracted is None and not canonical_rns_identities(text) and _should_retry_identity(pdf, dpi):
                try:
                    retry_text, retry_pages = read_ocr(
                        pdf,
                        IDENTITY_RETRY_DPI,
                        _identity_retry_page_limit(max_pages, pages),
                    )
                    retry_extracted = extract(pdf, retry_text)
                    if retry_extracted is not None:
                        text, pages, extracted = retry_text, retry_pages, retry_extracted
                except Exception as error:
                    retry_error = str(error) or type(error).__name__
            # Dormant unless an owner-approved future extractor emits candidates.
            # Without candidates/configuration this preserves prior behavior.
            record = map_extracted_record(extracted) if extracted else None
            document = {"file": str(pdf), "pages": pages, "ocr_characters": len(text), "number": record.get("number") if record else None, "extracted": {key: record.get(key) for key in EVIDENCE_FIELDS} if record else {}, "warnings": record.get("warnings", []) if record else ["unidentified"]}
            if record and record.get("number"):
                record["pages"] = pages
                groups.setdefault(str(record["number"]), []).append(record)
            elif retry_error:
                document["warnings"] = ["identity_retry_failed"]
                document["error"] = "Повторное распознавание номера РНС при 400 DPI завершилось ошибкой."
                document["technical_error"] = retry_error
            elif record and _is_amendment(record):
                document["warnings"] = ["unlinked_directive"]
                document["error"] = "Изменение/продление не связано: отсутствует явный номер РНС."
            else:
                document["error"] = "Не найден номер РНС"
            documents.append(document)
        except Exception as error:
            documents.append({"file": str(pdf), "pages": None, "ocr_characters": 0, "number": None, "extracted": {}, "warnings": ["processing_failed"], "error": str(error) or type(error).__name__})
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
        number: {key: record.get(key) for key in ("filename", "pdf", "issue", "end", "changed", "warnings", "stage", "object", "issuer", "builder", "region", "district", "developer", "source_files", "field_sources", "field_provenance", "merge_issues")}
        for number, record in records.items()
    }
    result.update({"contract_version": "rns-import-2", "input_hashes": before, "input_digest": digest(before), "documents": documents, "logical_records": sorted(records), "selected_records": selected, "output": str(output)})
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
    atomic_json(report, result)
    print(json.dumps({"output": str(options.output), "report": str(report), "records": len(result["logical_records"]), "conflicts": len(result["conflicts"])}))


if __name__ == "__main__":
    main()
