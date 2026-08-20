---
card_id: cgr-opc-worksheet-structure-runtime-v3
status: implemented
version: 1
work_id: cgr-opc-worksheet-structure-runtime-v3-20260820
task_id: cgr-opc-worksheet-structure-runtime-v3
purpose: Rebuild the worksheet structure runtime from the accepted XML-boundary line; exhaustive corpus completes in a separate test-only Gate.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: 1e237886d937a33aed7c9e4256b7265c8a0cc676
dependency_shas: [1e237886d937a33aed7c9e4256b7265c8a0cc676]
branch: codex/cgr-opc-worksheet-structure-runtime-v3
card_path: knowledge/tasks/cgr-opc-worksheet-structure-runtime-v3.md
write_scope: [rns_import_server/opc_worksheet_structure_reader.py, tests/opc_worksheet_structure_fixture_factory.py, tests/test_opc_worksheet_structure_reader.py, knowledge/tasks/cgr-opc-worksheet-structure-runtime-v3.md]
forbidden_paths: [rns_import_server/opc_worksheet_cell_reader.py, rns_import_server/opc_workbook_topology.py, rns_import_server/opc_style_semantic_reader.py, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_opc_worksheet_structure_reader.py tests/test_opc_worksheet_cell_reader.py tests/test_opc_workbook_topology.py tests/test_opc_style_semantic_reader.py", "python3 -m pytest -q", "python3 -m compileall -q rns_import_server/opc_worksheet_structure_reader.py tests/opc_worksheet_structure_fixture_factory.py tests/test_opc_worksheet_structure_reader.py", "git diff --check"]
---

# OPC worksheet structure runtime v3

- Fresh implementation from accepted XML-boundary integration `1e237886d937a33aed7c9e4256b7265c8a0cc676`. Commits `5fb526a7` and `2478fabd` are evidence only and must not be merged, rebased, or become ancestors.
- Public immutable API remains: `A1Range`, `WorksheetRowProperties`, `WorksheetAutoFilter`, `WorksheetStructuralSemantics`, `WorkbookWorksheetStructureSemantics`, exact `OPCWorksheetStructureReaderError`, and `read_worksheet_structure_semantics(package_path)`.
- Coerce PathLike once; call accepted topology and cell readers first. Typed dependency errors remain unchanged. The accepted cell reader now owns XML declaration/BOM/encoding fail-closed translation and row-property lexical compatibility; do not duplicate or bypass it.
- Own native `dimension`, `sheetData/row` attributes, `mergeCells/mergeCell`, and `autoFilter@ref`. Strict A1..XFD1048576 normalization/bounds; ordered row properties; required exact merge count, row-major ordered unique merges; optional advisory dimension/filter; owned XML order/attrs/content/namespace collisions fail closed.
- Runtime regression set must cover every previously reproduced defect: accepted ht/s/outline lexicals and semantic outputs; malformed declaration/BOM/UTF-16 dependency typed forwarding; bare root attrs; foreign/empty namespace collisions for all owned local names; merge missing/mismatch/order/$+case duplicate; rows 6/10/104 on two sheets; no mutation-safety inference or fallback.
- This runtime Gate does not claim the full frozen combinatorial corpus. After P6 runtime acceptance, a separate test-only Orda card will expand PathLike/member/XML/A1/mixed/unknown/second-sheet/dependency-precedence coverage before integration into the accepted OPC line.
- Exclude mutation/mapping, tables, defined names/`_FilterDatabase`, drawings, CF/DV/X14, formulas/styles/hyperlinks interpretation, filter children, `sheetFormatPr`, README, PDF, XLSX. Run every command; human commit/push only; no history rewrite.

## Implementation evidence — 2026-08-20

- Implemented the runtime-only reader on the accepted cell-boundary parent. It forwards topology/cell typed errors unchanged and does not re-own XML declaration, BOM, encoding, or row lexical validation.
- Runtime cases: immutable dimensions, rows (including accepted `ht`, `s`, and `outlineLevel` lexicals), strict A1 bounds, required exact merge count with row-major canonical merge order, optional auto-filter, and owned namespace/order/content failures.
- Validation: focused 165 passed; full 604 passed with the pre-existing OpenPyXL x14 warning; compileall and `git diff --check` clean.
