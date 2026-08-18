---
card_id: cgr-excel-v4-request-schema
status: frozen
version: 1
work_id: cgr-excel-row-contract-v4-20260818
task_id: request-schema-validator-v1
purpose: Validate the complete Excel row request before any COM acquisition.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: aed40af042647ccaea5b455f4dfee8b311f6c0e3
dependency_shas: [aed40af042647ccaea5b455f4dfee8b311f6c0e3]
branch: codex/cgr-excel-request-schema-v1
card_path: knowledge/tasks/cgr-excel-v4-request-schema.md
write_scope: [scripts/WindowsExcelRequestSchema.psm1, tests/WindowsExcelRequestSchema.Tests.ps1, knowledge/tasks/cgr-excel-v4-request-schema.md]
forbidden_paths: [scripts/windows_excel_insert.ps1, scripts/WindowsExcelInsert.Contract.psm1, README.md]
acceptance_commands: ["pwsh -NoProfile -File tests/WindowsExcelRequestSchema.Tests.ps1", "git diff --check"]
---

# Request schema validator v1

Validate parsed JSON without PowerShell coercion: every row/count/ordinal must be numeric integral and in Excel bounds; positive unique ordinal mapping; exact group start/end/next-header relation; source/template/insertion membership; worksheet capacity; required lease/ACK/nonce/identity; explicit allowed fields and Y/Z/W/A contract; reject duplicates/unknowns before any COM callback. Pester covers negative/fractional/string/duplicate/out-of-range and valid 6/10/104. Windows Pester is mandatory; no skip placeholder. Human commit/push; no merge/rebase/amend/force.
