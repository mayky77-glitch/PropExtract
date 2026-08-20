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

Implemented in `scripts/WindowsExcelRequestSchema.psm1`. The sole exported
entry point is `Test-WindowsExcelRequestSchema -RequestJson <raw JSON>
[-BeforeCom <scriptblock>]` (with `Assert-WindowsExcelRequestSchema` alias).
It scans raw JSON before `ConvertFrom-Json`, so duplicate object keys and the
lexical type of every row/count/ordinal are rejected before the optional
COM-bound callback can run.

The frozen wire shape has explicit top-level fields for operation/nonces,
control/candidate/sheet identities, lease and ACK paths, bounds, same-group
source/template rows, ordinal mapping, writes, `FormulaR1C1` Y/Z values, and
the W hyperlink. `fields` permits only B:V, X, and AA; A is supplied only by
the positive unique ordinal mapping, W only by `hyperlink`, and Y/Z only by
`formulas`. The validator requires `next_header = group_end + 1`,
`insertion_row = next_header`, same-group source/template membership, and
available capacity below Excel's 1,048,576th row.

Evidence (2026-08-20): `git diff --check` passed on macOS. `pwsh` is absent on
this host, therefore executable Pester was not run here; Windows Pester
execution remains mandatory and is not represented as a pass or skip.

P6 remediation: the scanner now compares against a single PowerShell
backslash literal and restricts escapes to the JSON grammar. Pester coverage
adds escaped quote/backslash formula round trips at rows 6/10/104, malformed
escape rejection before the callback, and a serialized object mutation that
proves the lease property is absent before the required-field assertion.
