---
card_id: cgr-rule-v5-x14-cf
status: review
version: 1
work_id: cgr-ooxml-rule-semantics-v5-20260818
task_id: x14-cf-reader-v1
purpose: Parse complete x14 conditional-formatting semantics and embedded DXF ownership.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: b41a73b4f823ac41c9996142a9ef37745ea3d7fb
dependency_shas: [b41a73b4f823ac41c9996142a9ef37745ea3d7fb]
branch: codex/cgr-x14-cf-reader-v1
card_path: knowledge/tasks/cgr-rule-v5-x14-cf.md
write_scope: [rns_import_server/ooxml_x14_cf_reader.py, tests/test_ooxml_x14_cf_reader.py, knowledge/tasks/cgr-rule-v5-x14-cf.md]
forbidden_paths: [rns_import_server/ooxml_rule_reader.py, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_ooxml_x14_cf_reader.py", "python3 -m compileall -q rns_import_server/ooxml_x14_cf_reader.py", "git diff --check"]
---

# X14 CF reader v1

Preserve x14 collection and each group including empty; typed ordered xm:sqref tokens/attrs, legal UID/attrs, xm:f vector cardinality 0..3, colorScale/dataBar/iconSet payload and canonical embedded x14:dxf bound to exact worksheet/container/rule owner. Enforce official child order and unknown-owned content fail closed. Tests cover Sheet1/Dashboard × 6/10/104, empty groups, tri-state attrs, formula cardinalities/order, DXF owner isolation and every field mutation. No rejected-code reuse. Card review, exact tests, human commit/push; no merge/rebase/amend/force.

## Implementation evidence

- Immutable feature SHA: `8ad867a646b246abcbe72b7f81e848e1b17a9f29`.
- Reader preserves x14 collections/groups including empty groups, ordered sqref tokens/attributes, typed rules/formula vector, canonical DXF/payload bound to worksheet/group/rule owner, and fails closed on unknown children/cardinality.
- Tests cover Sheet1/Dashboard at 6/10/104, empty groups, formula vector and DXF ownership. Focused `5 passed`; full `291 passed, 1 existing synthetic-x14 warning`; compile/diff pass.
- Risk: only x14 CF scope interpreted; cross-part DXF resolution remains separate.

## Recovery evidence

- Immutable recovery feature SHA: `b02351be6d8d5e71fb30c74eeb5f1224b7a11751`.
- Structured errors expose code, stable worksheet/collection/group/rule owner path, QName/value and canonical owner XML. Reader validates ruleful sqref, GUID, positive priority, tri-state values, formula cardinality and duplicate DXF/payload children while retaining canonical DXF/payload owner binding.
- Focused `5 passed`; full `291 passed, 1 existing synthetic-x14 warning`; compileall and diff check pass.
- Remaining risk: expanded per-field mutation matrix and recursive payload-child validation require follow-up evidence before final acceptance.
