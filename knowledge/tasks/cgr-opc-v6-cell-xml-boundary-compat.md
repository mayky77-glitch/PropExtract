---
card_id: cgr-opc-v6-cell-xml-boundary-compat
status: frozen
version: 1
work_id: cgr-opc-cell-xml-boundary-compat-v1-20260820
task_id: cgr-opc-cell-xml-boundary-compat-v1
purpose: Close the accepted worksheet-cell XML declaration, encoding, and BOM boundary with exact typed errors.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: 2ce47c8f38c44d589ff61addf94179060d0b5e6f
dependency_shas: [bb38faef0b0d771559f7a6480e43bd9f4e77b67b]
branch: codex/cgr-opc-cell-xml-boundary-compat-v1
card_path: knowledge/tasks/cgr-opc-v6-cell-xml-boundary-compat.md
write_scope: [rns_import_server/opc_worksheet_cell_reader.py, tests/test_opc_worksheet_cell_reader.py, knowledge/tasks/cgr-opc-v6-cell-xml-boundary-compat.md]
forbidden_paths: [rns_import_server/opc_worksheet_structure_reader.py, tests/test_opc_worksheet_structure_reader.py, rns_import_server/opc_style_semantic_reader.py, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_opc_worksheet_cell_reader.py tests/test_opc_style_semantic_reader.py tests/test_opc_workbook_topology.py", "python3 -m pytest -q", "python3 -m compileall -q rns_import_server/opc_worksheet_cell_reader.py tests/test_opc_worksheet_cell_reader.py", "git diff --check"]
---

# OPC cell-reader XML boundary compatibility

- Preserve the full accepted cell/formula/hyperlink API, projections, row-attribute compatibility, and every existing exact semantic error.
- No raw `xml.etree.ElementTree.ParseError`, `LookupError`, `UnicodeError`, `TypeError`, or encoding-library exception may escape `read_worksheet_cell_semantics` for a worksheet payload.
- Map malformed XML, XML declarations, BOM/declaration conflicts, unknown or unsupported encodings, truncated input, and declared UTF-16 over incompatible bytes to stable exact `OPCWorksheetCellReaderError(code, subject, field, detail)` tuples retaining the canonical worksheet subject. Do not expose host exception text as an unstable contract.
- Positive cases: UTF-8 bytes with/without BOM and a matching XML declaration produce byte-for-value identical cell/formula/hyperlink projections. Negative exact cases: truncated declared UTF-8; BOM plus truncated XML; declared UTF-16 over UTF-8 bytes; unknown encoding; malformed declaration; wrong root/namespace retains its existing typed semantics.
- Preserve one-shot PathLike behavior, canonical member rules, dependency precedence, legacy `_unsigned`, and row lexical behavior. No fallback decoding, encoding guessing, partial result, empty success, or structure-reader change.
- No structure reader/corpus, styles, mutation, CF/DV/X14, README, PDF, or XLSX edits. Run every acceptance command; human identity commit/push only; no merge, rebase, amend, or force-push.

## Implementation evidence

- The XML boundary converts native parser encoding and malformed-input exceptions to stable `OPCWorksheetCellReaderError` tuples without exposing host exception text.
- UTF-8 XML declarations with and without a UTF-8 BOM preserve the complete cell, formula, and hyperlink projections.
- Direct ZIP/XML cases freeze truncated declared UTF-8, BOM plus truncated XML, incompatible declared UTF-16, unknown encodings, and malformed declarations with their canonical worksheet subject.
- Focused composite, full suite, compileall, and diff checks pass; no parser fallback, encoding guessing, partial result, or structure-reader change was added.
