---
card_id: cgr-opc-worksheet-structure-reader-v2
status: frozen
version: 1
work_id: cgr-opc-worksheet-structure-reader-v2-20260820
task_id: cgr-opc-worksheet-structure-reader-v2
purpose: Read immutable worksheet geometry, row properties, merges, and auto-filter extents after accepted row-attribute compatibility.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: bb38faef0b0d771559f7a6480e43bd9f4e77b67b
dependency_shas: [bb38faef0b0d771559f7a6480e43bd9f4e77b67b]
branch: codex/cgr-opc-worksheet-structure-reader-v2
card_path: knowledge/tasks/cgr-opc-worksheet-structure-reader-v2.md
write_scope: [rns_import_server/opc_worksheet_structure_reader.py, tests/opc_worksheet_structure_fixture_factory.py, tests/test_opc_worksheet_structure_reader.py, knowledge/tasks/cgr-opc-worksheet-structure-reader-v2.md]
forbidden_paths: [rns_import_server/opc_worksheet_cell_reader.py, rns_import_server/opc_workbook_topology.py, rns_import_server/opc_style_semantic_reader.py, rns_import_server/ooxml_native_cf_reader.py, rns_import_server/ooxml_native_dv_reader.py, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_opc_worksheet_structure_reader.py tests/test_opc_worksheet_cell_reader.py tests/test_opc_workbook_topology.py tests/test_opc_style_semantic_reader.py", "python3 -m pytest -q", "python3 -m compileall -q rns_import_server/opc_worksheet_structure_reader.py tests/opc_worksheet_structure_fixture_factory.py tests/test_opc_worksheet_structure_reader.py", "git diff --check"]
---

# OPC worksheet structure reader v2

- Fresh restart from accepted compatibility integration `bb38faef0b0d771559f7a6480e43bd9f4e77b67b`; the suspended v1 branch is not reused or rebased.
- Entry `read_worksheet_structure_semantics(package_path)` returns immutable ordered `WorkbookWorksheetStructureSemantics` containing per-sheet `WorksheetStructuralSemantics`, `A1Range`, `WorksheetRowProperties`, and optional `WorksheetAutoFilter`. New errors are exact `OPCWorksheetStructureReaderError(code, subject, field, detail)` tuples.
- Coerce PathLike once; call accepted topology and cell readers first and forward their typed failures. Read accepted worksheet parts using canonical member rules. Own only native `dimension`, `sheetData/row` attributes, `mergeCells/mergeCell`, and `autoFilter@ref`; unowned content may coexist but is not interpreted.
- `A1Range` normalizes `$` and uppercase coordinates, preserving start/end and min/max row/column. Enforce A1..XFD1048576; reject malformed, reversed, whole-axis, 3D, qualified, empty, duplicate, and out-of-grid ranges.
- Preserve ordered unique row `r` plus optional `ht`, `s`, `customHeight`, `customFormat`, `hidden`, `outlineLevel`, `collapsed`. Use the same accepted lexical/domain contract as the cell compatibility reader; preserve absent/false/zero distinctly. Rows strictly increase and align with accepted cells where cells exist.
- `dimension` is optional advisory evidence. `mergeCells@count` exactly matches ordered unique children. `autoFilter` owns only `ref`. Enforce native owned container order: dimension before sheetData, autoFilter before mergeCells; reject duplicates, unknown owned attrs/children, mixed/nested content, malformed/unsupported encoding/wrong root/namespace, and native leaks.
- Corpus: two sheets; rows/merges/filter at 6/10/104; all row properties; absent dimension/filter; A1 and XFD1048576; immutable ordering. Exact negatives: PathLike, member alias, XML/root/namespace/order/duplicate/count/mixed/nested, unknown attrs, every A1 failure, row/merge order/duplicate, numeric/boolean boundaries, dependency forwarding.
- Reader performs no mutation/mapping. Downstream evidence only: rows/ranges below insertion k shift +1, above remain; merge spanning `min_row < k <= max_row` conflicts; filter/dimension spanning k are reported, never silently safe.
- Exclude mutation, tables, defined names/`_FilterDatabase`, drawings, CF/DV/X14, formulas/styles/hyperlinks, filter columns/sort state, `sheetFormatPr`, README, PDFs/XLSX, and stale A1 commits `3f586c2`/`ae0d8cc`.
- Run every acceptance command; human identity commit/push only; no merge, rebase, amend, or force-push.
