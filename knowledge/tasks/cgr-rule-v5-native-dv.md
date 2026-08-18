---
card_id: cgr-rule-v5-native-dv
status: frozen
version: 1
work_id: cgr-ooxml-rule-semantics-v5-20260818
task_id: native-dv-reader-v1
purpose: Parse complete native data-validation container and rule semantics.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: b41a73b4f823ac41c9996142a9ef37745ea3d7fb
dependency_shas: [b41a73b4f823ac41c9996142a9ef37745ea3d7fb]
branch: codex/cgr-native-dv-reader-v1
card_path: knowledge/tasks/cgr-rule-v5-native-dv.md
write_scope: [rns_import_server/ooxml_native_dv_reader.py, tests/test_ooxml_native_dv_reader.py, knowledge/tasks/cgr-rule-v5-native-dv.md]
forbidden_paths: [rns_import_server/ooxml_rule_reader.py, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_ooxml_native_dv_reader.py", "python3 -m compileall -q rns_import_server/ooxml_native_dv_reader.py", "git diff --check"]
---

# Native DV reader v1

Preserve dataValidations at count=0; typed count/disablePrompts/xWindow/yWindow and verify count against children. Typed ordered sqref; showDropDown/allowBlank/showErrorMessage/showInputMessage as bool-or-None without inversion; legal errorStyle, `{xr}uid`, formula1/2, prompt/error/title/type/operator/imeMode. Tests cover Sheet1/Dashboard × 6/10/104, zero containers, all tri-state flags and each field mutation. No rejected-code reuse. Card review, tests, human commit/push; no merge/rebase/amend/force.
