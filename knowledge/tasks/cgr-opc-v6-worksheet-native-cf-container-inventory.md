---
card_id: cgr-opc-v6-worksheet-native-cf-container-inventory
status: frozen
version: 1
work_id: cgr-opc-worksheet-native-cf-container-inventory-v1-20260820
task_id: cgr-opc-worksheet-native-cf-container-inventory-v1
purpose: Inventory ordered native conditional-formatting containers and strict sqref geometry without interpreting rules or payloads.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: dbba5b446b3db701f31a4e24b06958c6e94d49f5
dependency_shas: [dbba5b446b3db701f31a4e24b06958c6e94d49f5]
contract_reference_shas: [786fe2710fb964da282c9c87b1dbef590e9312f7]
branch: codex/cgr-opc-worksheet-native-cf-container-inventory-v1
card_path: knowledge/tasks/cgr-opc-v6-worksheet-native-cf-container-inventory.md
write_scope: [rns_import_server/opc_worksheet_native_cf_reader.py, tests/opc_worksheet_native_cf_fixture_factory.py, tests/test_opc_worksheet_native_cf_reader.py, knowledge/tasks/cgr-opc-v6-worksheet-native-cf-container-inventory.md]
forbidden_paths: [rns_import_server/opc_workbook_topology.py, rns_import_server/opc_worksheet_native_dv_reader.py, rns_import_server/ooxml_native_cf_reader.py, rns_import_server/ooxml_rule_reader.py, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_opc_worksheet_native_cf_reader.py tests/test_opc_workbook_topology.py tests/test_opc_worksheet_cell_reader.py tests/test_opc_worksheet_structure_reader.py", "python3 -m pytest -q", "python3 -m compileall -q rns_import_server/opc_worksheet_native_cf_reader.py tests/opc_worksheet_native_cf_fixture_factory.py tests/test_opc_worksheet_native_cf_reader.py", "git diff --check"]
---

# OPC worksheet native-CF container inventory v1

## Clean line and compatibility

- Implement from exact accepted OPC integration `dbba5b446b3db701f31a4e24b06958c6e94d49f5`. Old native-CF `786fe271...` and `123e7b8...` are contract references only: no ancestry, cherry-pick, rebase, or source-tree copy.
- Preserve the accepted presence API and exact error behavior byte-for-contract. Extend the same module; do not create another resolver or call the public presence reader and reopen the package.
- One public call performs one PathLike coercion, one topology pass, one exact canonical member read per worksheet, one XML parse, accepted all-depth x14 hard-stop, and accepted native-placement validation.

## Frozen public API

- Add immutable `NativeCfA1Range(start_coordinate, end_coordinate, min_row, min_column, max_row, max_column)` with normalized uppercase endpoint coordinates.
- Add immutable `NativeCfContainerInventory(owner_path, sqref, pivot, uid, rule_count)`, `WorksheetNativeCfContainerInventory(worksheet, containers)`, and `WorkbookNativeCfContainerInventory(worksheets)`.
- Add `read_worksheet_native_cf_container_inventory(package_path) -> WorkbookNativeCfContainerInventory`. Reuse `OPCWorksheetNativeCfReaderError(code, subject, field, detail)` and exact four-field `as_tuple()`.
- Preserve worksheet topology order and direct native container XML order. Empty workbook/container tuples are valid only where the source is genuinely absent/empty under this contract.

## Container and sqref semantics

- Own direct SpreadsheetML `conditionalFormatting` containers only. Allowed attributes are required nonblank `sqref`, optional `pivot`, and optional `{http://schemas.microsoft.com/office/spreadsheetml/2014/revision}uid`; unknown/duplicate/foreign same-local attributes fail typed.
- `pivot` uses exact XML boolean lexicals `0`, `1`, `false`, `true`; absence is `None`. `uid` is a nonblank braced GUID and is retained exactly.
- Parse XML-whitespace-separated `sqref` tokens in order. Each token is one A1 cell or rectangular range within `A1:XFD1048576`; optional `$` is accepted and normalized away. Reject qualified/3D/external names, whole row/column, malformed/overlong tokens, reversed rectangles, lexical/canonical duplicates, and any overlapping rectangles. No union/formula/name interpretation.
- `rule_count` counts direct native `cfRule` children in XML order. Inventory must not validate, return, or imply rule attributes, priority, formulas, dxf, or payload semantics.
- Reject any non-`cfRule` direct container child with deterministic typed error. Preserve accepted native `cfRule` parent/namespace checks. Reject direct native `extLst` as `unsupported_native_cf_extension`; any x14 CF descendant retains accepted earlier `unsupported_x14_content` precedence. Unrelated non-CF worksheet extensions remain allowed.
- No partial result, opaque semantic success, alternate parser, OpenPyXL fallback, warning-only downgrade, or silent absence.

## Corpus and claim boundary

- Exact full immutable two-sheet projections with absent, one, empty-rule, and multiple containers; sqrefs covering rows 6, 10, and 104; pivot tri-state; UID; container/rule order and counts.
- Exact boundary matrix for A1 minimum/maximum, `$` normalization, multiple ordered ranges, malformed/overlong/out-of-bounds/reversed/duplicate/overlap tokens, required sqref, unknown attrs/children, native extension rejection, and owned placement/namespace errors.
- Re-run and preserve every accepted presence PathLike/topology/member/ZIP/XML/x14 regression, including sentinel dependency identity, combined percent/case aliases, decompression errors, declarations/BOM/UTF-7, empty XML, and unrelated extension coexistence.
- Every negative asserts one exact four-field tuple; every positive asserts complete recursive records and immutability. No alternate codes, observational assertions, skips, or fallback.
- Explicitly exclude rule type/priority/dxfId/stopIfTrue/formulas/cardinality; colorScale/dataBar/iconSet/cfvo/color; dxf table resolution; native extension interpretation; x14 parsing/composition; coordinate mutation/mapping; insertion safety; DV/styles/COM/UI/CrossOver/native Excel/source PDF/XLSX/README. Rule-core is the next separate Gate after this one is accepted.

## Execution evidence

- Implemented from clean base `29c55d1d21716b429bc6769d2acce587b9aa321e`; no native-CF reference-line ancestry, cherry-pick, or source copy.
- Added immutable ordered native-container inventory and strict A1 `sqref` geometry in the existing single-pass package boundary. Projection deliberately retains only owner path, geometry, pivot, UID, and direct native `cfRule` count.
- Local acceptance on 2026-08-20: focused command passed `315`; full `python3 -m pytest -q` passed `1067` with one existing OpenPyXL unknown-extension warning; compileall and `git diff --check` passed.
