---
card_id: construction-group-routing-v1-structural-oracle-remediation
status: frozen
version: 1
work_id: construction-group-routing-v1-row-remediation
task_id: structural-oracle-remediation
purpose: Завершить bidirectional raw-OOXML semantic oracle для paired control/candidate publication.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
launch_status: planned
actual_model: pending
actual_reasoning_effort: pending
fallback_reason: null
card_path: knowledge/tasks/construction-group-routing-v1-structural-oracle-remediation.md
card_commit_sha: runtime-envelope
planning_parent_sha: 2ff1f0df4cf5cbc379e2455a39ec75de53f55504
base_sha: runtime-envelope
dependency_shas:
  - 2ff1f0df4cf5cbc379e2455a39ec75de53f55504
branch: codex/cgr-structural-oracle-remediation
branch_base_sha: runtime-envelope
write_scope:
  - rns_import_server/workbook_structure.py
  - rns_import_server/workbook_mutation_manifest.py
  - tests/test_workbook_mutation_manifest.py
  - knowledge/tasks/construction-group-routing-v1-structural-oracle-remediation.md
forbidden_paths:
  - rns_import_server/group_row_insertion.py
  - rns_import_server/excel_native.py
  - scripts/windows_excel_insert.ps1
  - rns_import_server/workbook.py
  - README.md
contract_versions:
  input: native-group-row-insertion-v1
  output: workbook-semantic-oracle-v2
acceptance_commands:
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m pytest -q tests/test_workbook_mutation_manifest.py"
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m compileall -q rns_import_server tests"
  - git diff --check
---

# Remediation B — structural semantic oracle

## Required behavior

- Build read-only raw-package manifests for original, paired native control and candidate. Original→control admits only proven Excel normalization/calc-cache changes; candidate→control uses exact row mapping around insertion and an explicit inserted-row allowlist.
- Compare bidirectionally: reject missing, changed and candidate-only unauthorized cells such as `B1`. Cover values, formulas/R1C1 patterns, styles/number formats, hyperlinks/display, merges, autoFilter, defined names, formula/error sets, data validation and conditional formatting including x14 `extLst` fingerprints/sqref.
- Validate deterministic column-A ordinal rebasing rather than exempting all A mismatches. Validate Y/Z formula patterns, exactly one requested hyperlink, mapped old rows, dimension/row delta and no new formula errors.
- Include cross-sheet/dashboard formula/range and independent totals hooks; unrelated control recalculation/cache changes must not be misclassified as insertion changes.
- Python remains read-only and never saves these workbooks. No mutation fallback and no private fixture data.

## Tests and handoff

- Reproduce rejection of candidate-only `B1`, new/changed CF, x14/DV, filter/name/merge, style, hyperlink, formula/error and ordinal mutations; accept only exact mapped insertion plus allowlisted row construction.
- Cover original→control normalization separately from candidate→control; include insertion rows 6, 10 and 104 with sanitized synthetic fixtures.
- Set card `review`, record immutable SHA/evidence/risks, commit/push normally; no merge/amend/rebase/force-push.
