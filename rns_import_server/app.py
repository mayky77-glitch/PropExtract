#!/usr/bin/env python3
"""Local CLI and HTTP orchestration for PDF-to-RNS workbook imports."""
from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Callable

try:
    from rns_import_server.audit import atomic_json, digest, sha256
    from rns_import_server.files import discover_pdfs
    from rns_import_server.ocr import read as read_ocr
    from rns_import_server.rns_adapter import date, extract
    from rns_import_server.workbook import apply
except ModuleNotFoundError:  # Direct ``python rns_import_server/app.py`` invocation.
    from audit import atomic_json, digest, sha256
    from files import discover_pdfs
    from ocr import read as read_ocr
    from rns_adapter import date, extract
    from workbook import apply

EVIDENCE_FIELDS = ("issue", "end", "changed", "issuer", "developer", "builder", "district", "region", "stage", "object")
ProgressCallback = Callable[[int, str, str | None], None]


def _is_amendment(record: dict) -> bool:
    source = str(record.get("filename", "")).casefold()
    return any(token in source for token in ("измен", "продлен", "продлён", "приказ", "распоряжен", "extension", "amendment"))


def _evidence_count(record: dict) -> int:
    return sum(record.get(field) is not None for field in EVIDENCE_FIELDS)


def _merge_group(number: str, versions: list[dict], documents: list[dict]) -> dict | None:
    """Keep a substantive permit, then fill its gaps from identified directives only."""
    permits = [record for record in versions if not _is_amendment(record)]
    directives = [record for record in versions if _is_amendment(record)]
    if not permits:
        # Explicit ID can update one proven existing row only.  ``apply``
        # emits a diagnostic instead of appending when that proof is absent.
        selected = max(directives, key=lambda item: (_evidence_count(item), date(item.get("changed")) or datetime.min, str(item["filename"])))
        existing_only = dict(selected)
        existing_only["existing_only"] = True
        existing_only["source_files"] = [record["filename"] for record in directives]
        existing_only["field_sources"] = {field: str(selected["pdf"]) for field in EVIDENCE_FIELDS if selected.get(field) is not None}
        return existing_only
    selected = max(permits, key=lambda item: (_evidence_count(item), date(item.get("changed")) or datetime.min, str(item["filename"])))
    merged = dict(selected)
    merged["field_provenance"] = dict(selected.get("field_provenance", {}))
    merged["field_sources"] = {field: str(selected["pdf"]) for field in EVIDENCE_FIELDS if selected.get(field) is not None}
    merged["source_files"] = [selected["filename"]]
    for directive in directives:
        # Explicit canonical ID is supplied by the parser; evidence must be
        # material before a directive can enrich a permit.
        if directive.get("number") != number or _evidence_count(directive) == 0:
            documents.append({"file": directive["pdf"], "pages": directive.get("pages"), "ocr_characters": None, "number": number, "extracted": {}, "warnings": ["unlinked_directive"], "error": "Изменение/продление не связано: недостаточно подтверждённых данных."})
            continue
        for field in EVIDENCE_FIELDS:
            proposed = directive.get(field)
            if proposed is None:
                continue
            if field == "changed":
                current = merged.get(field)
                if current is None or (date(proposed) and date(proposed) > (date(current) or datetime.min)):
                    merged[field] = proposed
                    merged["field_provenance"][field] = "ocr"
                    merged["field_sources"][field] = str(directive["pdf"])
            elif merged.get(field) is None:
                merged[field] = proposed
                merged["field_provenance"][field] = "ocr"
                merged["field_sources"][field] = str(directive["pdf"])
        merged["source_files"].append(directive["filename"])
    merged["warnings"] = [field for field in merged.get("warnings", []) if merged.get(field) is None]
    return merged


def collect(
    pdf_dir: Path,
    dpi: int,
    max_pages: int,
    progress: ProgressCallback | None = None,
    pdfs: list[Path] | None = None,
) -> tuple[dict[str, dict], list[dict]]:
    groups: dict[str, list[dict]] = {}
    documents: list[dict] = []
    pdfs = pdfs if pdfs is not None else discover_pdfs(pdf_dir)
    for index, pdf in enumerate(pdfs, start=1):
        if progress:
            progress(8 + int((index - 1) / len(pdfs) * 68), "Распознаём PDF", pdf.name)
        try:
            text, pages = read_ocr(pdf, dpi, max_pages)
            record = extract(pdf, text)
            document = {"file": str(pdf), "pages": pages, "ocr_characters": len(text), "number": record.get("number") if record else None, "extracted": {key: record.get(key) for key in EVIDENCE_FIELDS} if record else {}, "warnings": record.get("warnings", []) if record else ["unidentified"]}
            if record and record.get("number"):
                record["pages"] = pages
                groups.setdefault(str(record["number"]), []).append(record)
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
        number: {key: record.get(key) for key in ("filename", "pdf", "issue", "end", "changed", "warnings", "stage", "object", "issuer", "builder", "region", "district", "developer", "source_files", "field_sources")}
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
    print(json.dumps({"output": str(options.output), "report": str(report), "records": len(result["logical_records"]), "conflicts": len(result["conflicts"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
