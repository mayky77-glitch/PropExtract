---
card_id: cgr-excel-v4-fake-com-corpus
status: frozen
version: 1
work_id: cgr-excel-row-contract-v4-20260818
task_id: fake-com-fault-corpus-v1
purpose: Provide an executable self-validating fake Excel COM graph and fault corpus.
role: tester
route: P3
assigned_model: gpt-5.6-terra
reasoning_effort: medium
planning_parent_sha: aed40af042647ccaea5b455f4dfee8b311f6c0e3
dependency_shas: [aed40af042647ccaea5b455f4dfee8b311f6c0e3]
branch: codex/cgr-excel-fake-com-corpus-v1
card_path: knowledge/tasks/cgr-excel-v4-fake-com-corpus.md
write_scope: [tests/support/WindowsExcelFakeCom.psm1, tests/WindowsExcelFakeCom.Tests.ps1, knowledge/tasks/cgr-excel-v4-fake-com-corpus.md]
forbidden_paths: [scripts, rns_import_server, README.md]
acceptance_commands: ["pwsh -NoProfile -File tests/WindowsExcelFakeCom.Tests.ps1", "git diff --check"]
---

# Fake COM fault corpus v1

Build a real executable fake object graph for Application→Workbooks→Workbook→Worksheets→Sheet→Rows/Cells/Hyperlinks, logging every proxy acquisition, insert/mutation/save/close/Quit and reverse release. Inject open/insert/calc/save/cleanup/release faults and self-validate expected calls/envelopes for 6/10/104. Every chained/returned proxy, including Hyperlinks.Add result, is observable. No production imports or source-string assertions. Windows Pester mandatory. Human commit/push; no merge/rebase/amend/force.
