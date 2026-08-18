---
card_id: cgr-rule-v5-native-cf
status: review
version: 1
work_id: cgr-ooxml-rule-semantics-v5-20260818
task_id: native-cf-reader-v1
purpose: Parse complete native conditional-formatting container and rule semantics.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: b41a73b4f823ac41c9996142a9ef37745ea3d7fb
dependency_shas: [b41a73b4f823ac41c9996142a9ef37745ea3d7fb]
branch: codex/cgr-native-cf-reader-v1
card_path: knowledge/tasks/cgr-rule-v5-native-cf.md
write_scope: [rns_import_server/ooxml_native_cf_reader.py, tests/test_ooxml_native_cf_reader.py, knowledge/tasks/cgr-rule-v5-native-cf.md]
forbidden_paths: [rns_import_server/ooxml_rule_reader.py, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_ooxml_native_cf_reader.py", "python3 -m compileall -q rns_import_server/ooxml_native_cf_reader.py", "git diff --check"]
---

# Native CF reader v1

Input is `(worksheet_part, worksheet_xml)`; output immutable ordered typed models/findings. Preserve every conditionalFormatting container including zero rules; typed ordered sqref, pivot tri-state, legal `{xr}uid`, owner path, all group/rule attrs, required type/priority, dxfId, ordered formulas and type payloads. Reject invalid bool/int/UID, duplicate/conflicting attrs, missing required fields, malformed/empty sqref; unknown content inside owned vocabulary fails closed. Tests cover Sheet1/Dashboard × 6/10/104, every field mutation and absent/false/true distinctions. No rejected-code reuse. Card review, exact tests, human commit/push; no merge/rebase/amend/force.

## Implementation review — 2026-08-18

- Added a standalone strict parser, with frozen slot dataclasses for worksheet
  result, containers, rules, formulas, and color-scale/data-bar/icon-set
  payloads.  Owner paths are one-based, worksheet-part-qualified paths.
- It preserves native container/rule and `sqref` order; a container with no
  `cfRule` is retained.  Boolean values are exact XML booleans and `pivot` is
  represented as `None`, `False`, or `True`; `xr:uid` is checked as a braced
  UUID.
- It fails closed before returning a partial model for malformed XML, duplicate
  XML attributes, invalid typed values, missing required values, conflicting
  color sources, or unknown children/attributes in the owned vocabulary.

## Evidence and residual risk — 2026-08-18

- `python3 -m pytest -q tests/test_ooxml_native_cf_reader.py` — 40 passed.
- `python3 -m pytest -q` — 326 passed, with one pre-existing OpenPyXL warning
  for an unsupported x14 extension in an unrelated preservation test.
- `python3 -m compileall -q rns_import_server/ooxml_native_cf_reader.py` and
  `git diff --check` — passed.
- Scope is parsing only: it does not write XLSX files or touch production data.
  Native CF extensions are deliberately rejected rather than discarded; a
  dedicated extension reader must own them before they can be accepted.

## P6 recovery review — 2026-08-18

- Aligned the reader to the native 2006 vocabulary: the 12 native comparison
  operators are accepted, while x14-only `autoMin`, `3Stars`, `gradient`, and
  `axisPosition` are rejected in native elements.
- Native `extLst` is now an immutable opaque model at container, rule, and
  CFVO owner paths.  This preserves x14 coexistence without treating foreign
  extension children as native payloads.
- Formula particles have native order/cardinality checks; `expression`,
  `cellIs` (including between/notBetween), and payload rules are validated.
  All owned composites reject non-whitespace text/tails.  `priority`/`dxfId`/
  `stdDev` use Int32 and rank/data-bar/color index fields use UInt32 bounds;
  top10 rank applies its 0..100 percentage and 1..1000 count semantics.
- Recovery evidence: focused suite 50 passed; full suite 336 passed with the
  same unrelated OpenPyXL x14 warning; compileall and diff checks passed.
- Residual risk: foreign extension XML is retained as opaque serialized XML,
  not interpreted; its URI-specific semantics remain owned by the x14 reader.
