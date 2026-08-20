---
card_id: cgr-rule-v6-native-dv
status: frozen
version: 1
work_id: cgr-native-dv-reader-v2-20260820
task_id: native-dv-reader-v2
purpose: Parse strict native worksheet data-validation containers and rules from the accepted native-CF line.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: 123e7b889c5904ff0be1ab4e60302d571a4d61eb
dependency_shas: [123e7b889c5904ff0be1ab4e60302d571a4d61eb]
branch: codex/cgr-native-dv-reader-v2
card_path: knowledge/tasks/cgr-rule-v6-native-dv.md
write_scope: [rns_import_server/ooxml_native_dv_reader.py, tests/test_ooxml_native_dv_reader.py, knowledge/tasks/cgr-rule-v6-native-dv.md]
forbidden_paths: [rns_import_server/ooxml_native_cf_reader.py, tests/test_ooxml_native_cf_reader.py, rns_import_server/ooxml_rule_reader.py, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_ooxml_native_dv_reader.py tests/test_ooxml_native_cf_reader.py", "python3 -m pytest -q", "python3 -m compileall -q rns_import_server/ooxml_native_dv_reader.py tests/test_ooxml_native_dv_reader.py", "git diff --check"]
---

# Native DV reader v2

## Frozen input and output

- Input is `(worksheet_part, worksheet_xml)` and the entry point is `read_native_data_validations(worksheet_part, worksheet_xml)`.
- Return immutable, ordered, slot-based models. Preserve the native `dataValidations` container even when `count="0"`; preserve child order, `sqref` token order, formula lexical text, and absent/false/true distinctions.
- Fail before returning partial output with one typed `NativeDvParseError(code, owner_path, detail)`. Error tuples and owner paths are stable and asserted exactly.
- Public records expose the worksheet part, the single optional native container, and ordered rules. Container fields are `count`, `disable_prompts`, `x_window`, `y_window`; rule fields include ordered `sqref`, `type`, `operator`, `allow_blank`, `show_drop_down`, `show_input_message`, `show_error_message`, `error_style`, `ime_mode`, prompt/error titles and text, optional `{xr}uid`, and optional `formula1`/`formula2`.

## Native vocabulary contract

- Parse only SpreadsheetML 2006 `worksheet/dataValidations/dataValidation` and its native `formula1`/`formula2` children. Reject multiple native containers, unexpected owned elements/attributes, duplicate attributes/children, mixed content, invalid child order, malformed XML, unsupported XML encodings, and empty required values.
- `count`, `xWindow`, and `yWindow` are XSD `unsignedInt` with XML-whitespace collapse and UInt32 bounds; signed zero is accepted consistently with the accepted native-CF integer contract. `count` must exactly equal the number of rules.
- Native booleans use exact XML boolean lexicals and remain tri-state. `showDropDown` is preserved exactly as stored; do not invert it into UI semantics.
- Accept only native enum values:
  - `type`: `none`, `whole`, `decimal`, `list`, `date`, `time`, `textLength`, `custom`;
  - `operator`: `between`, `notBetween`, `equal`, `notEqual`, `lessThan`, `lessThanOrEqual`, `greaterThan`, `greaterThanOrEqual`;
  - `errorStyle`: `stop`, `warning`, `information`;
  - `imeMode`: `noControl`, `off`, `on`, `disabled`, `hiragana`, `fullKatakana`, `halfKatakana`, `fullAlpha`, `halfAlpha`, `fullHangul`, `halfHangul`.
- `sqref` is required and contains one or more valid, bounded A1 cell/range references. Preserve token order and reject empty, malformed, reversed, out-of-grid, duplicate, or overlapping tokens rather than silently normalizing them.
- `{xr}uid` is optional and must be a braced GUID. No other extension attribute is interpreted.
- Enforce native formula/operator cardinality: `between`/`notBetween` require both formulas; the other comparison operators require only `formula1`; comparison operators are valid only for `whole`, `decimal`, `date`, `time`, and `textLength`; `list` and `custom` require `formula1` and reject `formula2`/`operator`; `none` rejects formulas and `operator`.
- Preserve formula text without evaluation, locale rewriting, external-link resolution, or shared-formula expansion. Reject duplicate formula elements and non-whitespace tails.

## Scope boundaries

- Read-only parser. No XLSX mutation, combined rule reader, conditional formatting changes, x14 data validations, style/shared-string interpretation, formula evaluation, or composition layer.
- Do not reuse rejected or blocked X14/monolithic implementations. The only planning/dependency line is accepted native-CF integration `123e7b889c5904ff0be1ab4e60302d571a4d61eb`.
- No silent fallback: unsupported native-owned content produces an exact typed error; foreign extension semantics are out of scope and must not be reported as successfully interpreted.

## Required evidence

- Tests cover at least two worksheet parts and `sqref` rows 6, 10, and 104; zero-rule container; absent/false/true for every boolean; every enum and field; legal XML whitespace/integer boundaries; formulas and comparison cardinality.
- Negative tests assert exact tuples for malformed XML/root/namespace, duplicate/multiple containers, count mismatch, invalid booleans/integers/enums/GUID/sqref, unknown native content, mixed content, formula order/cardinality, and unsupported x14 content.
- Run every acceptance command. Human-authored commit and push only; no merge, rebase, amend, force-push, README edits, or source workbook/PDF changes.

## Remediation evidence

- P6 remediation: reject x14 `dataValidations` at every worksheet descendant depth before returning a result; map unknown XML byte encodings to stable `invalid_xml` at the worksheet boundary. Unrelated extension content remains outside this native-reader scope.
