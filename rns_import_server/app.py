#!/usr/bin/env python3
"""Local CLI and HTTP orchestration for PDF-to-RNS workbook imports."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Callable

try:
    from rns_import_server.audit import atomic_json, digest, sha256
    from rns_import_server.ocr import read as read_ocr
    from rns_import_server.rns_adapter import date, extract
    from rns_import_server.workbook import apply
except ModuleNotFoundError:  # Direct ``python rns_import_server/app.py`` invocation.
    from audit import atomic_json, digest, sha256
    from ocr import read as read_ocr
    from rns_adapter import date, extract
    from workbook import apply

EVIDENCE_FIELDS = ("issue", "end", "changed", "issuer", "developer", "builder", "district", "stage", "object")
ProgressCallback = Callable[[int, str, str | None], None]


def collect(
    pdf_dir: Path,
    dpi: int,
    max_pages: int,
    progress: ProgressCallback | None = None,
) -> tuple[dict[str, dict], list[dict]]:
    groups: dict[str, list[dict]] = {}
    documents: list[dict] = []
    pdfs = sorted(pdf_dir.rglob("*.pdf"))
    for index, pdf in enumerate(pdfs, start=1):
        if progress:
            progress(8 + int((index - 1) / len(pdfs) * 68), "Распознаём PDF", pdf.name)
        text, pages = read_ocr(pdf, dpi, max_pages)
        record = extract(pdf, text)
        documents.append({"file": str(pdf), "pages": pages, "ocr_characters": len(text), "number": record.get("number") if record else None, "extracted": {key: record.get(key) for key in EVIDENCE_FIELDS} if record else {}, "warnings": record.get("warnings", []) if record else ["unidentified"]})
        if record:
            record["pages"] = pages
            groups.setdefault(str(record["number"]), []).append(record)
        if progress:
            progress(8 + int(index / len(pdfs) * 68), "PDF обработан", pdf.name)
    chosen = {number: max(versions, key=lambda item: (date(item.get("changed")) or date(item.get("end")) or datetime.min, str(item["filename"]))) for number, versions in groups.items()}
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
    pdfs = sorted(pdf_dir.rglob("*.pdf"))
    if not pdfs or any(path.is_symlink() for path in pdfs):
        raise ValueError("pdf_dir must contain non-symlink PDF files")
    if progress:
        progress(5, f"Найдено PDF: {len(pdfs)}", None)
    before = {"xlsx": sha256(xlsx), "pdfs": {str(path.relative_to(pdf_dir)): sha256(path) for path in pdfs}}
    records, documents = collect(pdf_dir, dpi, max_pages, progress)
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
        number: {key: record.get(key) for key in ("filename", "issue", "end", "changed", "warnings")}
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
    serve = commands.add_parser("serve"); serve.add_argument("--host", default="127.0.0.1"); serve.add_argument("--port", type=int, default=8775)
    options = parser.parse_args()
    if options.command == "serve":
        if options.host not in {"127.0.0.1", "localhost", "::1"}:
            parser.error("serve host must be loopback-only")
        try:
            from rns_import_server.server import create_server
        except ModuleNotFoundError:
            from server import create_server
        print(f"http://{options.host}:{options.port}")
        create_server(options.host, options.port, run).serve_forever()
        return
    report = options.report or options.output.with_suffix(".json")
    if report.resolve() in {options.xlsx.resolve(), options.output.resolve()}:
        parser.error("report must not collide with input or output")
    result = run(options.pdf_dir, options.xlsx, options.output, options.dpi, options.max_pages)
    atomic_json(report, result)
    print(json.dumps({"output": str(options.output), "report": str(report), "records": len(result["logical_records"]), "conflicts": len(result["conflicts"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
