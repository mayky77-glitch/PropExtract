---
card_id: cgr-opc-v6-worksheet-cell-reader
status: frozen
version: 1
work_id: cgr-opc-worksheet-cell-reader-v1-20260820
task_id: worksheet-cell-reader
purpose: Read immutable worksheet cells, formula metadata, and hyperlinks from accepted OPC topology and graph contracts.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: 740763af0d5b1f6e1ae1ef0e11f751381edadd7e
dependency_shas: [740763af0d5b1f6e1ae1ef0e11f751381edadd7e]
branch: codex/cgr-opc-worksheet-cell-reader-v1
card_path: knowledge/tasks/cgr-opc-v6-worksheet-cell-reader.md
write_scope: [rns_import_server/opc_worksheet_cell_reader.py, tests/opc_worksheet_cell_fixture_factory.py, tests/test_opc_worksheet_cell_reader.py, knowledge/tasks/cgr-opc-v6-worksheet-cell-reader.md]
forbidden_paths: [rns_import_server/opc_workbook_topology.py, rns_import_server/opc_package_graph.py, rns_import_server/opc_part_uri.py, rns_import_server/opc_relationship_xml.py, tests/opc_workbook_fixture_factory.py, tests/test_opc_workbook_topology.py, tests/test_opc_package_graph.py, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_opc_worksheet_cell_reader.py tests/test_opc_workbook_topology.py tests/test_opc_package_graph.py tests/test_opc_part_uri.py tests/test_opc_relationship_xml.py tests/test_opc_package_v6_corpus.py", "python3 -m pytest -q", "python3 -m compileall -q rns_import_server tests", "git diff --check"]
---

# OPC worksheet cell reader v1

Implement fresh from the exact frozen base. Do not merge, copy, or import stale V5/rejected worksheet-reader code.

## Public contract

- Export frozen records `CellFormula`, `WorksheetCell`, `WorksheetHyperlink`, `WorksheetCells`, and `WorkbookCellSemantics`; typed `OPCWorksheetCellReaderError`; and `read_worksheet_cell_semantics(package_path)`.
- Error tuple is exactly `(code, subject, field, detail)`. Never return partial output, silently skip malformed content, guess a value, leak a native exception, or report false success.
- Preserve workbook/sheet order from `WorkbookTopology`, then worksheet XML order for cells and hyperlinks. Every public collection is immutable.
- Coerce the public `PathLike` exactly once to a stable string. Use accepted `read_workbook_topology` and `build_opc_package_graph` with that stable string; do not implement another part or relationship resolver. A second graph scan inside the current topology API is a documented performance cost, not permission for a permissive fallback.

## Cell and formula rules

1. Read only worksheet parts resolved by topology. Match raw ZIP members to canonical parts through accepted part-URI canonicalization; reject alias ambiguity and missing members deterministically.
2. Require namespace-exact SpreadsheetML `worksheet/sheetData/row/c`. Reject malformed/unsupported-encoding XML, invalid children in owned structures, duplicate/out-of-order rows or cells, and duplicate coordinates.
3. Validate bounded A1 cell coordinates and row consistency. Preserve cell `t`, raw `<v>` lexical text, simple inline `<is><t>` text, and shared-string index only. Supported types are default/numeric, `b`, `d`, `e`, `inlineStr`, `s`, and `str`; enforce type-specific required/exclusive payloads. Do not read or interpret `sharedStrings.xml`, dates, styles, or rich inline runs.
4. For a formula cell, preserve `<f>` text, kind (`normal` default, `shared`, or `array`), shared index, and reference lexical attributes; preserve `<v>` separately as cached text. Reject duplicate `f/v/is`, invalid attributes, malformed shared indices/references, and unsupported formula kinds such as data-table formulas. Do not evaluate formulas or expand shared/array formulas across cells.

## Hyperlink rules

1. Parse optional namespace-exact `hyperlinks/hyperlink` in XML order. Validate a bounded single-cell/range A1 `ref`, nonblank optional display/tooltip, unique ref, and unique relationship id.
2. A hyperlink must use exactly one of relationship `r:id` or internal `location`. Location-only anchors are retained without dereferencing.
3. Resolve `r:id` only through accepted graph relationships whose source is the worksheet part. Require exactly one matching hyperlink-type relationship. Preserve target mode/raw target and accepted resolved Internal target; reject missing/ambiguous/wrong-type/dangling mappings deterministically.

## Exclusions and verification

- No value coercion, formula evaluation, rich strings, shared-string interpretation, styles, dimensions, merges, defined names, filters, conditional formatting, data validation, row insertion, or mutation.
- Own a namespace-valid direct ZIP/XML fixture corpus with two sheets and cells at rows 6, 10, and 104; raw scalar types; simple inline/shared index; normal/shared/array formula metadata and cache; external, internal-package, and location hyperlinks; Unicode sheet/target text.
- Negative corpus covers wrong root/namespace/encoding, missing or aliased worksheet member, row/cell order and coordinates, type/payload/formula defects, rich inline text, malformed shared index, hyperlink ref/id/type/mode/target/duplicates, and one-shot stateful `PathLike` errors with full exact tuples.
- Focused composite, full suite, compileall, and diff checks pass. Human commit/push; no merge, amend, rebase, force-push, or unrelated edits.
