---
card_id: cgr-opc-v6-worksheet-native-cf-container-inventory-v2
status: frozen
version: 2
work_id: cgr-opc-worksheet-native-cf-container-inventory-v2-20260820
task_id: cgr-opc-worksheet-native-cf-container-inventory-v2
purpose: Inventory ordered native conditional-formatting containers and strict sqref geometry through the accepted ElementTree XML boundary.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: dbba5b446b3db701f31a4e24b06958c6e94d49f5
dependency_shas: [dbba5b446b3db701f31a4e24b06958c6e94d49f5]
contract_reference_shas: [786fe2710fb964da282c9c87b1dbef590e9312f7]
branch: codex/cgr-opc-worksheet-native-cf-container-inventory-v2
card_path: knowledge/tasks/cgr-opc-v6-worksheet-native-cf-container-inventory-v2.md
write_scope: [rns_import_server/opc_worksheet_native_cf_reader.py, tests/opc_worksheet_native_cf_fixture_factory.py, tests/test_opc_worksheet_native_cf_reader.py, knowledge/tasks/cgr-opc-v6-worksheet-native-cf-container-inventory-v2.md]
forbidden_paths: [knowledge/tasks/cgr-opc-v6-worksheet-native-cf-container-inventory.md, rns_import_server/opc_workbook_topology.py, rns_import_server/opc_worksheet_native_dv_reader.py, rns_import_server/ooxml_native_cf_reader.py, rns_import_server/ooxml_rule_reader.py, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_opc_worksheet_native_cf_reader.py tests/test_opc_workbook_topology.py tests/test_opc_worksheet_cell_reader.py tests/test_opc_worksheet_structure_reader.py", "python3 -m pytest -q", "python3 -m compileall -q rns_import_server/opc_worksheet_native_cf_reader.py tests/opc_worksheet_native_cf_fixture_factory.py tests/test_opc_worksheet_native_cf_reader.py", "git diff --check"]
---

# OPC worksheet native-CF container inventory v2

## Clean line and owner decision

- Fresh implementation from exact accepted integration `dbba5b446b3db701f31a4e24b06958c6e94d49f5`; rejected V1 features `e72b4e5...` and `8a387dd...` are not ancestors and must not be cherry-picked, rebased, or copied. Old CF `786fe271...` remains contract reference only.
- Owner-fixed precedence: package/member boundary, then one complete XML well-formedness and namespace-validity parse, then full-tree x14 hard-stop, then native CF placement/container semantics. Malformed XML never promises QName/duplicate detail.
- Preserve accepted presence public API and exact successful values. Both public readers share one private package/topology/member/XML pipeline; neither calls the other or opens/parses the worksheet twice.

## Single XML boundary

- Parse each worksheet payload exactly once with `xml.etree.ElementTree.fromstring(payload_bytes)`. Pass original bytes so BOM/declaration/encoding handling remains native. No raw decode, regex, Expat/PullParser, secondary attribute scan, fallback parser, partial tree, or guessed encoding.
- Map `ParseError`, unsupported/incompatible declarations, undeclared prefixes, duplicate lexical or expanded-QName attributes, malformed BOM/XML, and other parser failures through the accepted typed worksheet XML boundary. Duplicate attributes are `malformed-worksheet-xml`; no `duplicate-native-cf-attribute` or QName detail is promised for malformed XML.
- Only after a complete well-formed tree exists, scan every descendant for x14 CF tags and return exact accepted `unsupported_x14_content`. Only after that validate native placement, namespaces, attributes, and inventory. Native semantic errors can never mask a well-formed-tree x14 owner.

## Frozen public API

- Add immutable `NativeCfA1Range(start_coordinate, end_coordinate, min_row, min_column, max_row, max_column)` with uppercase endpoints and `$` removed.
- Add immutable `NativeCfContainerInventory(owner_path, sqref, pivot, uid, rule_count)`, `WorksheetNativeCfContainerInventory(worksheet, containers)`, `WorkbookNativeCfContainerInventory(worksheets)`.
- Add `read_worksheet_native_cf_container_inventory(package_path)`. Reuse exact `OPCWorksheetNativeCfReaderError(code, subject, field, detail).as_tuple()`.
- Preserve topology worksheet order and direct native container order. Inventory does not return rule bodies or imply rule validity.

## Native container and sqref semantics

- Own only direct SpreadsheetML `conditionalFormatting`. Allowed attrs: required nonblank `sqref`, optional `pivot`, optional `{http://schemas.microsoft.com/office/spreadsheetml/2014/revision}uid`; any well-formed unknown attr or namespace collision fails typed.
- `pivot`: exact XML booleans `0/1/false/true`, absence `None`. `uid`: retained exact nonblank braced GUID.
- Parse XML-whitespace-separated sqref tokens in source order. Accept cell/rectangular A1 within `A1:XFD1048576`, optional `$`; normalize endpoints uppercase without `$`. Reject qualified/3D/external/whole-axis/malformed/overlong/out-of-bounds/reversed tokens, lexical or normalized duplicate rectangles, and every overlap including containment, crossing, and shared-cell edge.
- `rule_count` counts direct native `cfRule` children only. Reject any other direct container child, including native `extLst`, with deterministic typed unsupported/child error. Existing x14 hard-stop retains earlier precedence; unrelated non-CF worksheet extensions remain allowed.
- No alternate parser, partial/empty success after a responsible-boundary failure, warning-only downgrade, OpenPyXL fallback, or hidden semantic interpretation.

## Required corpus and exclusions

- Full immutable two-sheet projections: absent, empty-rule, single/multiple containers; sqrefs at rows 6/10/104; pivot tri-state; UID; exact owner paths/order/rule counts.
- Exact A1 matrix: min/max, `$`, XML whitespace, multiple ordered tokens, overlong, lexical+normalized duplicates, reverse, bounds, containment/cross/shared-cell overlap.
- Exact XML precedence: UTF-8/UTF-16 BOM/declarations; malformed/unknown/UTF-7; undeclared prefix; duplicate same-name and two-prefix same-expanded-name attrs all malformed; nested x14 plus malformed duplicate remains malformed because no complete tree; well-formed nested x14 plus native semantic defect returns x14; unused DTD text never acts as markup.
- Re-run every accepted presence PathLike/topology identity/member alias/decompression/XML/native-placement/x14 regression. Assert complete recursive records, field order, and `FrozenInstanceError` at all new levels.
- Exclude rule type/priority/dxfId/stopIfTrue/formulas/cardinality, payloads/cfvo/colors, dxf resolution, native extension interpretation, x14 parsing/composition, mutation/mapping/insertion safety, DV/styles/COM/UI/CrossOver/native Excel/source PDF/XLSX/README. Rule-core remains the next separate Gate after V2 acceptance.

## Implementation evidence

- Implemented the frozen V2 inventory records and reader while retaining the accepted presence API and values.
- Both readers use the same private package/topology/member/byte-ElementTree pipeline; each worksheet payload crosses one ElementTree.fromstring(payload_bytes) boundary before x14 or native validation.
- Added exact projection, immutability, strict A1/sqref, attribute/child, XML/x14 precedence, and single-parse regression coverage.
- Validation on 2026-08-20: targeted acceptance 314 passed; full suite 1066 passed (one existing OpenPyXL extension warning).
- P6 parity remediation on 2026-08-20: inventory now executes the accepted content boundary after placement and before projection; focused acceptance 332 passed and full suite 1084 passed (the same existing OpenPyXL warning).
