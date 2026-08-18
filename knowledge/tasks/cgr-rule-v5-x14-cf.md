---
card_id: cgr-rule-v5-x14-cf
status: frozen
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
