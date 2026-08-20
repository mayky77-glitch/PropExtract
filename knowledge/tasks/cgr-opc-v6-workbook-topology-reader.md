---
card_id: cgr-opc-v6-workbook-topology-reader
status: frozen
version: 1
work_id: cgr-opc-workbook-topology-reader-v1-20260820
task_id: workbook-topology-reader
purpose: Read a deterministic workbook sheet topology from the accepted OPC package graph.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: d6a6ba8cdfcf6654314597ef4313085506d3dc18
dependency_shas: [d6a6ba8cdfcf6654314597ef4313085506d3dc18]
branch: codex/cgr-opc-workbook-topology-reader-v1
card_path: knowledge/tasks/cgr-opc-v6-workbook-topology-reader.md
write_scope: [rns_import_server/opc_workbook_topology.py, tests/opc_workbook_fixture_factory.py, tests/test_opc_workbook_topology.py, knowledge/tasks/cgr-opc-v6-workbook-topology-reader.md]
forbidden_paths: [rns_import_server/opc_package_graph.py, rns_import_server/opc_part_uri.py, rns_import_server/opc_relationship_xml.py, tests/test_opc_package_graph.py, tests/opc_package_v6_corpus.py, tests/test_opc_package_v6_corpus.py, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_opc_workbook_topology.py tests/test_opc_package_graph.py tests/test_opc_part_uri.py tests/test_opc_relationship_xml.py tests/test_opc_package_v6_corpus.py", "python3 -m pytest -q", "python3 -m compileall -q rns_import_server tests", "git diff --check"]
---

# OPC workbook topology reader v1

Implement fresh from the exact frozen base. Do not merge, cherry-pick, import, or copy stale V5/workbook-reader branches or rejected graph ancestry.

## Public contract

- Export frozen records `WorkbookTopology` and `WorksheetDescriptor`, typed `OPCWorkbookTopologyError`, and `read_workbook_topology(package_path)`.
- Build only through accepted `build_opc_package_graph`; do not add a second ZIP/relationship resolver.
- Return worksheet descriptors in workbook order with exact `name`, positive integer `sheet_id`, `state`, relationship Id, and resolved internal worksheet part.
- Error tuple is exactly `(code, subject, field, detail)`. No native exception leak, partial result, silent skip, permissive fallback, warning-only result, or false success.

## Required rules

1. Locate exactly one workbook part through the package relationship graph and require its relationship type to be the supported office-document workbook type.
2. Read only that workbook part plus its resolved internal relationships. Require the namespace-exact SpreadsheetML workbook root and sheets structure.
3. Require every sheet to have a nonblank unique name, unique positive integer `sheetId`, and unique nonblank relationship Id. Preserve workbook order and the declared sheet state.
4. Resolve every sheet relationship through the accepted graph. It must be Internal, exist, and use the supported worksheet relationship type. Reject dangling, external, non-worksheet, duplicate, or ambiguous mappings deterministically.
5. Reject missing/multiple workbook parts, malformed or unsupported-encoding workbook XML, missing/duplicate sheets structures, unknown required attributes, and graph/read failures with stable typed context.
6. This block does not parse worksheet cells, formulas, hyperlinks, shared strings, styles, defined names, cached values, or mutate a package.
7. The uniquely resolved workbook part must have exactly one content-types Override and its content type must be an accepted SpreadsheetML main-workbook type.

## Required verification

- Valid two-sheet workbook, preserved order/state, Unicode names/targets, and deterministic immutable records.
- Row-number fixture boundaries 6, 10, and 104 are represented in direct ZIP/XML fixtures for the next reader without parsing their cells here.
- Missing/multiple workbook relationship; malformed root/sheets; duplicate name/sheetId/rId; zero/negative/non-integer sheetId; missing/external/dangling/non-worksheet relationship; unsupported XML encoding; deterministic exact error tuples.
- Focused composite, full suite, compileall, and diff checks pass. Human commit/push; no merge, rebase, amend, force-push, or unrelated edits.

## Implementation evidence

- The reader uses `build_opc_package_graph` as the sole package/relationship resolver.  It reads only the already-resolved workbook part and the mandatory content-types control part; no sheet payload is read.
- Main-workbook content type is required as a single Override for the resolved part and is limited to `.xlsx` and macro-enabled SpreadsheetML main types.
- Direct fixtures cover preserved order/state, Unicode, row-boundary sheet IDs 6/10/104, malformed identity and mapping states, encoding, and missing/wrong content type.
