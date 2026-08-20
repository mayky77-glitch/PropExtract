---
card_id: cgr-opc-v6-worksheet-native-cf-rule-core
status: frozen
version: 1
work_id: cgr-opc-worksheet-native-cf-rule-core-v1-20260820
task_id: cgr-opc-worksheet-native-cf-rule-core-v1
purpose: Read ordered native conditional-formatting rule core with strict priority, basic attributes, and formula cardinality.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: aea4149c5b71897bfc9034979ce7339e5103a63a
dependency_shas: [aea4149c5b71897bfc9034979ce7339e5103a63a]
contract_reference_shas: [786fe2710fb964da282c9c87b1dbef590e9312f7]
branch: codex/cgr-opc-worksheet-native-cf-rule-core-v1
card_path: knowledge/tasks/cgr-opc-v6-worksheet-native-cf-rule-core.md
write_scope: [rns_import_server/opc_worksheet_native_cf_reader.py, tests/opc_worksheet_native_cf_fixture_factory.py, tests/test_opc_worksheet_native_cf_reader.py, knowledge/tasks/cgr-opc-v6-worksheet-native-cf-rule-core.md]
forbidden_paths: [rns_import_server/opc_workbook_topology.py, rns_import_server/opc_style_semantic_reader.py, rns_import_server/ooxml_native_cf_reader.py, rns_import_server/ooxml_rule_reader.py, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_opc_worksheet_native_cf_reader.py tests/test_opc_workbook_topology.py tests/test_opc_worksheet_cell_reader.py tests/test_opc_worksheet_structure_reader.py", "python3 -m pytest -q", "python3 -m compileall -q rns_import_server/opc_worksheet_native_cf_reader.py tests/opc_worksheet_native_cf_fixture_factory.py tests/test_opc_worksheet_native_cf_reader.py", "git diff --check"]
---

# OPC worksheet native-CF rule core v1

## Clean line and composition

- Implement from exact accepted common OPC head `aea4149c5b71897bfc9034979ce7339e5103a63a`. Accepted container V2 `c328ff1...` is ancestry. Old CF `786fe271...` is contract reference only; rejected container V1 `e72b4e5...`/`8a387dd...` must not enter ancestry or source.
- Preserve presence and container-inventory APIs and exact error behavior. Extend the same module and one private PathLike→topology→member→single `ET.fromstring(bytes)` pipeline; do not chain public readers, reopen, reparse, decode, or create a resolver.
- Preserve owner order: complete XML validity, then any-depth x14 hard-stop, then native placement/content/container/sqref checks, then rule-core semantics. No partial record survives a responsible-boundary error.

## Frozen public API

- Add immutable `NativeCfRuleCore(owner_path, document_order, type, priority, dxf_id, stop_if_true, formulas)`.
- Add immutable `NativeCfRuleCoreContainer(container, rules)`, `WorksheetNativeCfRuleCoreSemantics(worksheet, containers)`, `WorkbookNativeCfRuleCoreSemantics(worksheets)`.
- Add `read_worksheet_native_cf_rule_core_semantics(package_path)`. Reuse exact four-field `OPCWorksheetNativeCfReaderError`.
- Rule owner path is `${container.owner_path}/cfRule[N]` with one-based container-local `N`. `document_order` is one-based across all direct native rules in worksheet/container XML order. Numeric priority does not reorder output.

## Supported rule contract

- Support only `expression` with exactly one formula and formula-free `uniqueValues`, `duplicateValues`, `containsBlanks`, `notContainsBlanks`, `containsErrors`, `notContainsErrors` with zero formula/children.
- Deterministically reject every other type as `unsupported-native-cf-rule-type`, including `cellIs`, text/begins/ends, `top10`, `aboveAverage`, `timePeriod`, `colorScale`, `dataBar`, and `iconSet`. Unsupported types never yield partial rule/container/workbook output.
- Allowed rule attrs only required `type`, required `priority`, optional `dxfId`, optional `stopIfTrue`. Missing required and unknown attrs fail exact typed errors; first unknown is deterministic. No omitted type-specific attr is ignored.
- `priority`: XML-whitespace-collapsed signed integer lexical, accepting leading plus/zeros, normalized to `int`, range `1..2147483647`. It is unique worksheet-wide across containers; duplicate error retains original lexical detail. Preserve document order; do not require numeric sort.
- `dxfId`: optional XML-whitespace-collapsed UInt32 lexical, accepting plus/leading zeros/signed zero, range `0..4294967295`, returned as index only. Do not open styles/dxfs or assert index existence.
- `stopIfTrue`: exact `0/1/false/true`, absence `None`. Invalid boolean is typed and retains raw detail.

## Formula and owned-content boundary

- Formula is a direct native `formula` child only, with no attrs/nested elements; text must be nonblank after XML whitespace check and is retained exactly. Reject mixed text/tails, attributes, nesting, blank content, wrong namespace, and other direct children with deterministic exact errors.
- `expression` requires exactly one formula. Formula-free supported types require exactly zero. Cardinality errors name the rule type; formula XML order is retained.
- Direct rule `extLst`, payloads, `cfvo`, colors, and all other children fail typed; they are not opaque-preserved as semantic success. Existing x14 hard-stop always precedes rule semantic errors.
- No fallback, warning-only downgrade, empty/partial success, OpenPyXL interpretation, or formula evaluation.

## Required corpus and exclusions

- Exact immutable two-sheet recursive projections covering all seven supported types, multiple containers, worksheet-global priorities, owner/document order, formulas at rows 6/10/104, dxf `None/0/4294967295`, stopIfTrue `None/False/True`.
- Exact priority matrix: whitespace/plus/leading zero, malformed/zero/negative/overlong/Int32 overflow, and duplicate across containers. Exact dxf UInt32 and boolean matrices.
- Exact missing/unknown attrs, every unsupported type, formula missing/two/blank/whitespace/attr/nested/tail/wrong child/namespace, rule extLst/payload, and x14 precedence at every owned/foreign depth. Assert full four-field tuples, public field order, and `FrozenInstanceError` at every new record level.
- Re-run all accepted presence/container PathLike/topology/member/XML/native-placement/sqref/x14 tests and prove one parse per worksheet for the new reader.
- Exclude dxf table/style semantics, `cellIs` operator/cardinality, text/top10/aboveAverage/time attributes, payload/cfvo/color semantics, native extension interpretation, x14 parsing/composition, mutation/range mapping/insertion safety, DV/styles/COM/UI/CrossOver/native Excel/source PDF/XLSX/README. Further extended-rule, payload/dxf, and x14 Gates remain mandatory before CF insertion qualification.

## Completion evidence

- Added the immutable rule-core projection and retained the accepted single PathLike→topology→member→`ElementTree.fromstring(bytes)` pipeline, XML/x14 precedence, and existing presence/container APIs.
- The gate admits only `expression` plus the six formula-free rule types; it validates worksheet-global priorities, `dxfId` as an unresolved index, exact `stopIfTrue`, and strict direct formula XML without resolving styles or evaluating payloads.
- Passed `python3 -m pytest -q tests/test_opc_worksheet_native_cf_reader.py tests/test_opc_workbook_topology.py tests/test_opc_worksheet_cell_reader.py tests/test_opc_worksheet_structure_reader.py` (383 passed) and `python3 -m pytest -q` (1135 passed, one pre-existing OpenPyXL extension warning); compileall and `git diff --check` also passed.
