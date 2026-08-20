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

Implemented test-only fake COM graph in `tests/support/WindowsExcelFakeCom.psm1` with observable proxy acquisition/release, operation trace envelopes, and injectable open/insert/calc/save/cleanup/release faults. `tests/WindowsExcelFakeCom.Tests.ps1` self-validates rows 6, 10, and 104, including returned `Hyperlinks.Add` proxy and reverse release order. It imports only the fake module, never production code.

Validation is blocked on this macOS host because neither `pwsh` nor `powershell` is installed. Static/diff checks are required locally; Windows Pester remains mandatory before acceptance.
