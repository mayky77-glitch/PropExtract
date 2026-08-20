---
card_id: cgr-opc-v6-worksheet-native-cf-presence
status: frozen
version: 1
work_id: cgr-opc-worksheet-native-cf-presence-v1-20260820
task_id: cgr-opc-worksheet-native-cf-presence-v1
purpose: Inventory topology-owned native conditional-formatting presence and fail closed on any x14 CF content.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: b4fd718df4d7a6b8985783a4d905e53d7d6c7da5
dependency_shas: [b4fd718df4d7a6b8985783a4d905e53d7d6c7da5]
contract_reference_shas: [786fe2710fb964da282c9c87b1dbef590e9312f7]
branch: codex/cgr-opc-worksheet-native-cf-presence-v1
card_path: knowledge/tasks/cgr-opc-v6-worksheet-native-cf-presence.md
write_scope: [rns_import_server/opc_worksheet_native_cf_reader.py, tests/opc_worksheet_native_cf_fixture_factory.py, tests/test_opc_worksheet_native_cf_reader.py, knowledge/tasks/cgr-opc-v6-worksheet-native-cf-presence.md]
forbidden_paths: [rns_import_server/opc_workbook_topology.py, rns_import_server/opc_worksheet_native_dv_reader.py, rns_import_server/ooxml_native_cf_reader.py, rns_import_server/ooxml_rule_reader.py, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_opc_worksheet_native_cf_reader.py tests/test_opc_workbook_topology.py tests/test_opc_worksheet_cell_reader.py tests/test_opc_worksheet_structure_reader.py", "python3 -m pytest -q", "python3 -m compileall -q rns_import_server/opc_worksheet_native_cf_reader.py tests/opc_worksheet_native_cf_fixture_factory.py tests/test_opc_worksheet_native_cf_reader.py", "git diff --check"]
---

# OPC worksheet native-CF presence v1

## Clean-line and claim boundary

- Fresh implementation from accepted OPC base `b4fd718df4d7a6b8985783a4d905e53d7d6c7da5`. Accepted native-CF feature `786fe2710fb964da282c9c87b1dbef590e9312f7` is contract reference only, never dependency/ancestry/cherry-pick/copy source.
- Export only immutable `WorksheetNativeCfPresence(worksheet, has_native_conditional_formatting)` and `WorkbookNativeCfPresence(worksheets)` plus `read_worksheet_native_cf_presence(package_path)`.
- This Gate proves package ownership, native container presence, and x14 hard-stop only. It does not parse or qualify `sqref`, rules, priorities, formulas, dxf, payloads, or insertion safety. Those require later container-inventory, rule-core, payload/dxf, and x14 owners.

## Error and package contract

- Export `OPCWorksheetNativeCfReaderError(code, subject, field, detail)` with exact four-field `as_tuple()`. No partial/empty/warning success or alternate parser.
- Coerce caller `PathLike` exactly once; raising/non-string/bytes/NUL are typed and counted. Call accepted topology with normalized string and forward its exception by object identity.
- Read each ordered topology worksheet from exactly one raw canonical ZIP member. Reject missing, percent/case/dot aliases, canonical collision, invalid member names, ZIP/decompression/native errors. No new relationship/content-type/path resolver.
- Strict worksheet byte boundary: declaration/BOM/unknown or incompatible encoding/malformed XML/wrong SpreadsheetML root and native exceptions map to exact typed errors.

## Presence and X14 boundary

- Native SpreadsheetML `conditionalFormatting` must be a direct worksheet child. Native `cfRule` may occur only directly under a native direct-child container. Correctly namespaced owned tags at any other depth fail typed; foreign/empty namespace same-local-name at an owned position fails namespace-collision rather than becoming absence.
- Presence is `True` when one or more legal direct native `conditionalFormatting` containers exist, including an empty container. Presence is `False` only when none exists. Preserve worksheet topology order; no container/rule details are returned.
- Before any success, scan every descendant for x14 namespace `http://schemas.microsoft.com/office/spreadsheetml/2009/9/main` local names `conditionalFormattings`, `conditionalFormatting`, or `cfRule`. Any occurrence fails exact `unsupported_x14_content`, including content inside native/foreign `extLst`; unrelated extension elements may coexist.
- Do not treat serialized/opaque `extLst` preservation as semantic success. Existing publication reinjection code is not a reader fallback or oracle.

## Corpus and acceptance evidence

- Full exact projections for two worksheets/order, absent/native-empty/multiple native containers, immutable records, and native presence whose opaque source includes rows 6/10/104 only as evidence that later semantic layers are still required.
- Exact negative matrix: counted PathLike variants; topology sentinel identity/precedence; raw member/ZIP/XML/root/namespace boundaries; native container/rule legal and illegal parent/depth; owned foreign/empty namespace collisions; mixed/native malformed structure that this presence layer owns; x14 container/singular container/rule at worksheet, native container, rule/extLst, and foreign extension depths; x14 precedence before native success.
- Every case asserts an exact tuple/value, full default/populated records, and `FrozenInstanceError`; no observational assertion, alternate code, skip, mutation, or fallback.
- Exclude CF `sqref`/rule/formula/priority/dxf/payload semantics, native `extLst` interpretation, X14 parsing/composition, DV, styles, mutation/mapping, COM/UI/CrossOver/native Excel, source PDF/XLSX, and README. Human commit/push only; no amend/rebase/force after handoff.
