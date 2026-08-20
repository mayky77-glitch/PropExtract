---
card_id: cgr-opc-v6-worksheet-native-dv-adapter
status: frozen
version: 1
work_id: cgr-opc-worksheet-native-dv-adapter-v2-20260820
task_id: cgr-opc-worksheet-native-dv-adapter-v1
purpose: Read strict native worksheet data-validation semantics from topology-owned package parts and fail closed on x14 DV.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: d3d40ac02eca22fc5a053c38ae1ecf754a381479
dependency_shas: [d3d40ac02eca22fc5a053c38ae1ecf754a381479]
contract_reference_shas: [e66392bdf51937487ce9ed6a73eee28e54f3a6b0]
branch: codex/cgr-opc-worksheet-native-dv-adapter-v1
card_path: knowledge/tasks/cgr-opc-v6-worksheet-native-dv-adapter.md
write_scope: [rns_import_server/opc_worksheet_native_dv_reader.py, tests/opc_worksheet_native_dv_fixture_factory.py, tests/test_opc_worksheet_native_dv_reader.py, knowledge/tasks/cgr-opc-v6-worksheet-native-dv-adapter.md]
forbidden_paths: [rns_import_server/opc_workbook_topology.py, rns_import_server/opc_worksheet_structure_reader.py, rns_import_server/ooxml_native_dv_reader.py, rns_import_server/ooxml_native_cf_reader.py, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_opc_worksheet_native_dv_reader.py tests/test_opc_workbook_topology.py tests/test_opc_worksheet_structure_reader.py", "python3 -m pytest -q", "python3 -m compileall -q rns_import_server/opc_worksheet_native_dv_reader.py tests/opc_worksheet_native_dv_fixture_factory.py tests/test_opc_worksheet_native_dv_reader.py", "git diff --check"]
---

# OPC worksheet native-DV package adapter v1

## Clean-line rule

- Implement fresh from current accepted OPC base `d3d40ac02eca22fc5a053c38ae1ecf754a381479`. Accepted native-DV feature `e66392bdf51937487ce9ed6a73eee28e54f3a6b0` is a contract/evidence reference only, not ancestry.
- Do not cherry-pick, copy a branch tree, merge the separate `f4918e6` line, or import absent legacy modules. Rejected structure `5fb526a7`/`2478fabd`, blocked X14 `8ad867a`/`b02351b`/`387a8d2`, monolithic readers, and their ancestry must remain absent.

## Frozen API and semantics

- Export immutable ordered `NativeDataValidation`, `NativeDataValidations`, `WorksheetNativeDvSemantics(worksheet, container)`, and `WorkbookNativeDvSemantics(worksheets)` records plus `read_worksheet_native_data_validation_semantics(package_path)`.
- Rule fields: owner path; ordered lexical `sqref`; `type`; optional `operator`; tri-state `allow_blank`, `show_drop_down`, `show_input_message`, `show_error_message`; optional `error_style`, `ime_mode`, error/prompt title/text, braced `{xr}uid`, `formula1`, `formula2`. Container fields: owner path, exact count, tri-state `disable_prompts`, optional UInt32 `x_window`/`y_window`, ordered rules.
- Preserve an explicit native container with `count="0"`; absent container remains `None`. Preserve XML rule/token order, formula lexical text, and absent/false/true distinctions. Never invert `showDropDown`.
- Export `OPCWorksheetNativeDvReaderError(code, subject, field, detail)` with exact four-field `as_tuple()`. Own package/member and native-DV faults use this family. Native semantic codes/owner paths stay deterministic; topology dependency exceptions are forwarded unchanged by object identity.

## Package and XML boundary

- Coerce caller `PathLike` once before dependencies; raising/non-string/bytes/NUL cases fail typed with `calls == 1`. Call accepted `read_workbook_topology(normalized_str)` once and use its ordered worksheet descriptors only.
- Open the package only to read each topology-owned worksheet part. Require exactly one raw canonical member per part; reject missing, percent/case/dot aliases, canonical collisions, invalid member names, ZIP/decompression errors, and native exceptions. No new relationship/content-type/path resolver.
- Parse worksheet bytes with strict declaration/BOM/encoding boundary. Unknown/incompatible encoding, malformed XML, wrong SpreadsheetML root/namespace, native local-name namespace collisions, illegal owned parent/depth, duplicate containers/children, unknown owned attrs/elements, mixed text/tails, and non-leaf formulas fail before any partial workbook result.
- Detect exact `{http://schemas.microsoft.com/office/spreadsheetml/2009/9/main}dataValidations` at every descendant depth before success. Return typed `unsupported_x14_content`; unrelated extension elements and foreign same-local-name content remain out of native-DV semantics and may coexist only when they cannot masquerade as owned native tags.

## Native vocabulary

- Native owner tree is direct `worksheet/dataValidations/dataValidation`, then optional native `formula1`/`formula2` in legal order. Container attrs: required UInt32 `count`, optional tri-state `disablePrompts`, optional UInt32 `xWindow`/`yWindow`; count must equal rules.
- Rule requires one or more valid bounded, non-reversed, nonduplicate, nonoverlapping A1 cell/range `sqref` tokens. Preserve token order/lexical form. Bounds are `A1:XFD1048576`; reject whole-axis, qualified/3D, malformed, empty, duplicate, overlap, and oversized integer lexemes before `int()`.
- Exact enums: types `none/whole/decimal/list/date/time/textLength/custom`; operators `between/notBetween/equal/notEqual/lessThan/lessThanOrEqual/greaterThan/greaterThanOrEqual`; error styles `stop/warning/information`; IME modes from accepted native-DV v2 contract.
- XML booleans accept only `0/1/false/true`. UInt32 accepts bounded XML-whitespace, optional plus, and signed zero. `{xr}uid` is optional braced GUID; no other extension attr is interpreted.
- Enforce accepted formula/operator cardinality: range operators need formula1+formula2; other comparison operators need only formula1 and only comparison types; `list/custom` need formula1 with no operator/formula2; `none` rejects formulas/operator. No formula evaluation, locale rewrite, external resolution, shared expansion, or warning-only success.

## Corpus and insertion evidence

- Positive exact corpus: two worksheets/topology order; absent and zero-rule containers; every field/enum; every boolean absent/false/true; UInt32 lexicals/bounds; GUID; formulas/cardinality; immutability and full default/populated projections.
- Exact `sqref` includes `A6`, `B10:C10`, `XFD104`, and real-shaped `R104:R154`/`S104:S159`. Reader does not mutate/map; tests freeze expected native candidate evidence for insertion at rows 6/10/104 while retaining rule fingerprints and shifting/expanding only affected coverage.
- Negative exact tuples: every PathLike/member/ZIP/XML/owned-tree boundary; all enum/boolean/integer/GUID/sqref/formula/cardinality/count failures; nested x14 at every depth; sentinel topology exception identity and precedence. No observational assertions, alternate accepted codes, skip, partial output, empty fallback, OpenPyXL/native parser fallback, or test-only mutation claim.
- Exclude conditional formatting, x14 parsing/composition, styles/shared strings, generic formulas, workbook mutation/mapping, COM/UI/CrossOver/native Excel, source PDF/XLSX, and README. Commit/push with human identity; no amend/rebase/force after handoff.
