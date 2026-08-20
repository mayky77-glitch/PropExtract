---
card_id: cgr-opc-v6-workbook-defined-name-reader
status: frozen
version: 1
work_id: cgr-opc-workbook-defined-name-reader-v1-20260820
task_id: cgr-opc-workbook-defined-name-reader-v1
purpose: Read workbook-defined names and map the standard _xlnm._FilterDatabase range to the accepted worksheet topology.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: b12508d899c88efebf505b7986b0de99a40d5df6
dependency_shas: [b12508d899c88efebf505b7986b0de99a40d5df6]
branch: codex/cgr-opc-workbook-defined-name-reader-v1
card_path: knowledge/tasks/cgr-opc-v6-workbook-defined-name-reader.md
write_scope: [rns_import_server/opc_workbook_defined_name_reader.py, tests/opc_workbook_defined_name_fixture_factory.py, tests/test_opc_workbook_defined_name_reader.py, knowledge/tasks/cgr-opc-v6-workbook-defined-name-reader.md]
forbidden_paths: [rns_import_server/opc_workbook_topology.py, rns_import_server/opc_worksheet_structure_reader.py, rns_import_server/opc_worksheet_cell_reader.py, rns_import_server/opc_style_semantic_reader.py, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_opc_workbook_defined_name_reader.py tests/test_opc_workbook_topology.py tests/test_opc_worksheet_structure_reader.py", "python3 -m pytest -q", "python3 -m compileall -q rns_import_server/opc_workbook_defined_name_reader.py tests/opc_workbook_defined_name_fixture_factory.py tests/test_opc_workbook_defined_name_reader.py", "git diff --check"]
---

# OPC workbook defined-name reader v1

## Frozen output

- Export immutable `WorkbookDefinedName(name, local_sheet_index, hidden, expression)`, `WorkbookFilterDatabase(worksheet, reference)`, and `WorkbookDefinedNameSemantics(defined_names, filter_databases)` records.
- Export `OPCWorkbookDefinedNameReaderError(code, subject, field, detail)` with exact `as_tuple() == (code, subject, field, detail)` and `read_workbook_defined_name_semantics(package_path)`.
- `reference` is accepted structure-reader `A1Range`; preserve defined-name XML order. Ordinary names remain visible as opaque records and are never interpreted as formulas or claimed as insertion-safe.

## Frozen boundary

- Coerce caller `PathLike` exactly once before dependency calls; bytes, NUL, non-string, and raising coercions fail typed. Call accepted `read_workbook_topology()` with the normalized string and forward its typed failures unchanged.
- Use topology as sole workbook-part/relationship/content-type owner. Read exactly its raw canonical workbook member; reject missing, canonical alias/collision, and unsafe ZIP member names. No OpenPyXL/native/alternate parser and no path or relationship guess.
- Parse namespace-exact SpreadsheetML `workbook/definedNames/definedName`. Reject malformed or unsupported encoding, wrong root, duplicate containers, native local-name namespace collisions, illegal parent/depth, unknown owned attributes, children, non-whitespace container text/tails, and native exception leaks with exact typed tuples.
- Validate the standard defined-name attributes accepted by this reader. `name` is mandatory/nonblank; `localSheetId` uses bounded XML-whitespace integer rules and must index accepted topology; `hidden` uses exact XML boolean rules. Other standard native metadata may be accepted only through an explicit bounded allow-list and is out of semantic scope; foreign or unknown attributes fail closed.
- The only interpreted built-in is exact `_xlnm._FilterDatabase`. It requires `localSheetId`, one instance per worksheet, and one single-sheet A1 cell/range expression whose quoted/unquoted sheet name resolves exactly to the descriptor at that zero-based topology index. Normalize absolute/lowercase A1 to uppercase `A1Range`.
- Reject blank/filter formulas, union, 3D, external-book, function/formula, `#REF!`, whole-row/whole-column, reversed/out-of-bounds range, ambiguous quoting, sheet mismatch, duplicate scope, invalid boolean/index, and any unresolved range-owning built-in. No warning-only, partial, empty, or success fallback.
- Non-`_xlnm._FilterDatabase` names are returned opaque. Downstream insertion preflight must block any such name that may own a range until a separate exact semantic owner proves it safe; this reader never guesses.

## Corpus and insertion evidence

- Positive corpus: no `definedNames`; two sheets in topology order; quoted Russian sheet with escaped apostrophe; `localSheetId=0/1`; absolute/lowercase reference normalization; hidden absent/true/false; ordinary opaque local/global names; immutable ordered records; rows 6/10/104.
- For source `_xlnm._FilterDatabase` `A3:AQ605`, insertion at `k=6`, `10`, or `104` is evidence-only expected native candidate `A3:AQ606`: rows before `k` remain, rows at/after `k` shift by one. Reader performs no mapping or mutation.
- Exact negatives: one-shot failing/non-string/bytes/NUL PathLike; topology typed forwarding; missing/alias/colliding member; malformed/declaration/BOM/unsupported encoding; wrong root/namespace; duplicate/illegal-depth containers and names; unknown attrs/children/text/tails; blank/duplicate names; absent/invalid/out-of-range `localSheetId`; invalid `hidden`; duplicate filter scope; bad quoting/sheet mismatch; union/3D/external/function/`#REF!`/whole-axis/reversed/out-of-bounds A1.
- Exclude generic defined-name formula evaluation, tables, drawings, mutations, styles, cells/formulas/hyperlinks, CF/DV/X14, COM, UI, CrossOver, native Excel qualification, PDF/XLSX fixtures, and README. Commit/push with human identity; no amend, rebase, or force-push after handoff.
