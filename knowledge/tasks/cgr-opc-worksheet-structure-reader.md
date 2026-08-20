---
card_id: cgr-opc-worksheet-structure-reader
status: frozen
version: 1
work_id: cgr-opc-worksheet-structure-reader-v1-20260820
task_id: cgr-opc-worksheet-structure-reader-v1
purpose: Read immutable worksheet geometry, row properties, merges, and auto-filter extents for middle-row insertion preflight and oracle.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: ce864f484fd8e89cbcaa9aa805dbc336e7f94b25
dependency_shas: [ce864f484fd8e89cbcaa9aa805dbc336e7f94b25]
branch: codex/cgr-opc-worksheet-structure-reader-v1
card_path: knowledge/tasks/cgr-opc-worksheet-structure-reader.md
write_scope: [rns_import_server/opc_worksheet_structure_reader.py, tests/opc_worksheet_structure_fixture_factory.py, tests/test_opc_worksheet_structure_reader.py, knowledge/tasks/cgr-opc-worksheet-structure-reader.md]
forbidden_paths: [rns_import_server/opc_worksheet_cell_reader.py, rns_import_server/opc_workbook_topology.py, rns_import_server/opc_style_semantic_reader.py, rns_import_server/ooxml_native_cf_reader.py, rns_import_server/ooxml_native_dv_reader.py, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_opc_worksheet_structure_reader.py tests/test_opc_worksheet_cell_reader.py tests/test_opc_workbook_topology.py tests/test_opc_style_semantic_reader.py", "python3 -m pytest -q", "python3 -m compileall -q rns_import_server/opc_worksheet_structure_reader.py tests/opc_worksheet_structure_fixture_factory.py tests/test_opc_worksheet_structure_reader.py", "git diff --check"]
---

# OPC worksheet structure reader v1

## Frozen API and boundary

- Entry: `read_worksheet_structure_semantics(package_path) -> WorkbookWorksheetStructureSemantics`.
- Coerce `PathLike` exactly once. Call accepted topology and worksheet-cell readers first and preserve their exact typed errors. Reuse accepted canonical URI/member behavior; no second relationship/path resolver.
- Return immutable ordered slot records: `A1Range`, `WorksheetRowProperties`, `WorksheetAutoFilter`, `WorksheetStructuralSemantics`, `WorkbookWorksheetStructureSemantics`. New failures are `OPCWorksheetStructureReaderError(code, subject, field, detail)` with exact `as_tuple()`.
- Read only accepted worksheet parts and own only native SpreadsheetML `dimension`, `sheetData/row` attributes, `mergeCells/mergeCell`, and `autoFilter@ref`. Unowned real-sheet content may coexist but is never reported as interpreted.

## Structural semantics

- `A1Range` preserves normalized uppercase start/end coordinates plus min/max rows and columns. Accept absolute `$` markers but normalize them away. Bounds are rows 1..1048576 and columns A..XFD. Reject reversed, whole-row/whole-column, 3D, sheet-qualified, empty, duplicate, or malformed ranges.
- `WorksheetRowProperties` preserves ordered unique row number and optional `ht`, `s`, `customHeight`, `customFormat`, `hidden`, `outlineLevel`, and `collapsed`. Preserve absence separately from false/zero. Parse bounded numeric/boolean lexicals before conversion; enforce Excel row and outline bounds. Row numbers must be strictly increasing and align one-to-one with the accepted cell projection where cells exist.
- `dimension` is optional advisory evidence, never the sole safe row bound. `mergeCells@count` must exactly match ordered unique native `mergeCell` children. `autoFilter` is optional and owns only `ref`; filter columns and sort state are out of scope.
- Enforce native owned container order: dimension before sheetData; autoFilter before mergeCells. Reject duplicate containers, unknown owned attrs/children, mixed text/tails, nested owned content, malformed/unsupported-encoding/wrong-root/namespace XML, raw/canonical member ambiguity, and native exception leaks.

## Insertion-preflight contract

- Reader performs no mapping or mutation. Tests freeze downstream mapping evidence for insertion `k` at rows 6, 10, and 104: rows/ranges wholly below `k` shift by +1; wholly above remain; a merge with `min_row < k <= max_row` is a structural conflict. A filter or dimension spanning `k` is reported as evidence, never silently declared safe.
- Positive corpus has two worksheets; row properties and dimension/merge/filter boundaries at 6/10/104; hidden/custom-height/style/custom-format/outline/collapsed values; optional dimension/filter; A1 and XFD1048576 bounds; immutable/source-ordered records.
- Exact negatives cover one-shot PathLike, missing/canonical-alias member, malformed/encoding/root/namespace, owned order/duplicates/count mismatch/mixed/nested content, unknown attrs, bad/reversed/whole-axis/qualified/out-of-bounds A1, duplicate/out-of-order rows and merges, invalid numeric/boolean fields, and dependency-error forwarding.

## Exclusions

- No XLSX mutation/insertion, range rewriting, formulas/styles/hyperlink parsing, CF/DV/X14, tables, defined names or `_FilterDatabase`, drawings, comments, page/print settings, filter columns/sort state, or `sheetFormatPr` defaults.
- Do not reuse stale A1 mapper branches/commits `3f586c2` or `ae0d8cc`; they are not ancestors of the accepted line. No README, PDF, XLSX, accepted OPC module, CF, or DV edits.
- Run every acceptance command. Human identity commit/push only; no merge, rebase, amend, or force-push.
