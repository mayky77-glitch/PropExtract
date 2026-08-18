---
card_id: cgr-rule-v5-x14-dv
status: frozen
version: 1
work_id: cgr-ooxml-rule-semantics-v5-20260818
task_id: x14-dv-reader-v1
purpose: Parse complete x14 data-validation container and rule semantics.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: b41a73b4f823ac41c9996142a9ef37745ea3d7fb
dependency_shas: [b41a73b4f823ac41c9996142a9ef37745ea3d7fb]
branch: codex/cgr-x14-dv-reader-v1
card_path: knowledge/tasks/cgr-rule-v5-x14-dv.md
write_scope: [rns_import_server/ooxml_x14_dv_reader.py, tests/test_ooxml_x14_dv_reader.py, knowledge/tasks/cgr-rule-v5-x14-dv.md]
forbidden_paths: [rns_import_server/ooxml_rule_reader.py, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_ooxml_x14_dv_reader.py", "python3 -m compileall -q rns_import_server/ooxml_x14_dv_reader.py", "git diff --check"]
---

# X14 DV reader v1

Preserve x14 containers/groups and attrs with zero rules; typed ordered xm:sqref, tri-state flags including showDropDown, legal errorStyle/UID, formula1/2 with exact ordered xm:f, exact worksheet/container/rule owner. Tests cover Sheet1/Dashboard × 6/10/104, empty groups, every flag/field mutation and order. No rejected-code reuse. Card review, tests, human commit/push; no merge/rebase/amend/force.
