---
card_id: cgr-opc-v6-style-semantic-reader
status: frozen
version: 1
work_id: cgr-opc-style-semantic-reader-v1-20260820
task_id: opc-style-semantic-reader-v1
purpose: Resolve native workbook styles and explicit worksheet style usage for the row-insertion preservation oracle.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: d4c6a324bddb2d16344c50845e72af9bc35493aa
dependency_shas: [d4c6a324bddb2d16344c50845e72af9bc35493aa]
branch: codex/cgr-opc-style-semantic-reader-v1
card_path: knowledge/tasks/cgr-opc-v6-style-semantic-reader.md
write_scope: [rns_import_server/opc_style_semantic_reader.py, tests/opc_style_fixture_factory.py, tests/test_opc_style_semantic_reader.py, knowledge/tasks/cgr-opc-v6-style-semantic-reader.md]
forbidden_paths: [rns_import_server/opc_worksheet_cell_reader.py, rns_import_server/opc_workbook_topology.py, rns_import_server/opc_package_graph.py, rns_import_server/ooxml_native_cf_reader.py, rns_import_server/ooxml_native_dv_reader.py, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_opc_style_semantic_reader.py tests/test_opc_worksheet_cell_reader.py tests/test_opc_workbook_topology.py", "python3 -m pytest -q", "python3 -m compileall -q rns_import_server/opc_style_semantic_reader.py tests/opc_style_fixture_factory.py tests/test_opc_style_semantic_reader.py", "git diff --check"]
---

# OPC style semantic reader v1

## Frozen boundary

- Entry point: `read_workbook_style_semantics(package_path) -> WorkbookStyleSemantics`.
- Coerce `PathLike` exactly once. Call accepted `read_workbook_topology` and `read_worksheet_cell_semantics` first; preserve their exact typed failures. Use the accepted graph and canonical part URI/member rules; do not create another relationship or path resolver.
- Return immutable, ordered, slot-based records for the style table and explicit worksheet cell-style uses. Error type is `OPCStyleSemanticReaderError(code, subject, field, detail)` and exposes the exact four-field tuple. No native exception, partial output, silent skip, permissive fallback, or false success may cross this boundary.
- Public records cover `StyleColor`, `FontStyle`, `FillStyle`, `BorderSide`, `BorderStyle`, `NumberFormat`, `CellAlignment`, `CellProtection`, `CellFormat`, `StyleTable`, `CellStyleUse`, `WorksheetStyleUsage`, and `WorkbookStyleSemantics`. Preserve source order. Worksheet usage contains only cells with explicit `c@s`, in accepted workbook/sheet/cell order.

## Package contract

- Require exactly one internal workbook relationship with the native SpreadsheetML `styles` relationship type. Reject missing, ambiguous, external, wrong-type, or dangling mappings with stable exact codes.
- Require exactly one canonical ZIP member and one exact `[Content_Types].xml` Override for the resolved styles part using the native SpreadsheetML styles content type. Reject canonical aliases/collisions, missing or ambiguous Overrides, wrong content type, malformed XML, unsupported encoding, wrong namespace/root, and mixed/unknown owned content.
- Read no package part except dependencies, `[Content_Types].xml`, and the resolved styles part.

## Native style semantics

- Parse and preserve ordered native `numFmts`, `fonts`, `fills`, `borders`, `cellStyleXfs`, and `cellXfs`. Validate each declared `count` exactly against owned children and reject duplicate owned containers or out-of-order native containers.
- Parse bounded XSD integer/boolean lexicals before numeric conversion. Validate duplicate custom `numFmtId`, every component index in each `xf`, `xfId` against `cellStyleXfs`, and every explicit worksheet `c@s` against `cellXfs`.
- Preserve cell-format component IDs, `xfId`, `applyNumberFormat`, `applyFont`, `applyFill`, `applyBorder`, `applyAlignment`, `applyProtection`, `quotePrefix`, `pivotButton`, plus typed alignment and protection fields. Preserve absence separately from false/zero.
- Preserve native font/fill/border/number-format/color attributes required to prove semantic equality. Colors remain typed structural values (`rgb`, indexed, theme, tint, auto as applicable); do not calculate rendered colors. Preserve simple gradient/pattern/fill and border structure only where native `cellXfs` can reference it; reject unknown owned structures rather than fingerprinting arbitrary XML.
- Cell coordinates and style usage must retain accepted row boundaries 6, 10, and 104. Style index `0` and the final valid `cellXfs` index are explicit boundaries.

## Required exact errors and corpus

- Stable codes include relationship/content-type/member failures, `malformed-styles-xml`, `invalid-styles-root`, `invalid-styles-content`, `unknown-styles-attribute`, `invalid-style-count`, `invalid-style-index`, `invalid-xf-id`, `duplicate-numFmt-id`, and `invalid-cell-style-reference`. Dependency errors retain their original type/code unchanged.
- Positive corpus: two worksheets; explicit style uses at rows 6/10/104; default and final valid style indices; custom number format; font, pattern/gradient fill, border, alignment, protection, `cellStyleXfs` inheritance, all apply flags, quotePrefix and pivotButton; immutable/source-ordered output.
- Negative corpus: missing/duplicate/external/wrong/dangling styles relationship; missing/duplicate/wrong content-type Override; missing/canonical-alias member; malformed/unsupported-encoding/wrong-root/namespace/order/mixed XML; count mismatch; unknown owned attributes/children; duplicate numFmt IDs; invalid integer/boolean/component/xfId/cell-style indices; one-shot PathLike failures.

## Exclusions

- No XLSX mutation or row insertion, formatting writes, shared-string/value/formula interpretation, conditional formatting, data validation, X14, `dxfs`, named/table/pivot styles, theme rendering, locale rendering, or visual color resolution.
- Do not merge, copy, or reuse stale V5 branch `codex/cgr-style-table-semantic-reader-v1` or its obsolete API/card. No README, source PDF/XLSX, accepted topology/cell/graph, CF, or DV edits.
- Run every acceptance command; human identity commit/push only. No merge, rebase, amend, or force-push.
