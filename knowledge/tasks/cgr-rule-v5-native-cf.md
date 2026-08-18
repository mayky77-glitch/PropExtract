---
card_id: cgr-rule-v5-native-cf
status: frozen
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
