---
card_id: cgr-excel-v4-fake-com-fault-corpus-remediation
status: implemented_pending_windows_pester
version: 2
work_id: cgr-excel-row-contract-v4-20260818
task_id: fake-com-fault-corpus-p6-remediation
purpose: Make the fake Excel COM trace and fault envelopes exact, ordered, and non-successful on any failure.
role: developer
route: P6
assigned_model: gpt-5.6-terra
reasoning_effort: high
branch: codex/cgr-excel-fake-com-corpus-v1
write_scope: [tests/support/WindowsExcelFakeCom.psm1, tests/WindowsExcelFakeCom.Tests.ps1, knowledge/tasks/cgr-excel-v4-fake-com-fault-corpus.md]
acceptance_commands: ["pwsh -NoProfile -File tests/WindowsExcelFakeCom.Tests.ps1", "git diff --check"]
---

# Fake COM fault corpus P6 remediation

The test-only graph has an occurrence counter for every fault stage. A fault may target `occurrence` (or an explicit `occurrences` set), so `calc` and `save` occurrence 2 prove the candidate post-insert path; `cleanup` occurrence 2 and `release` occurrence 1 prove primary-before-cleanup ordering. The module returns a final classification: `success`, `primary_failure`, `primary_and_cleanup_failure`, or `cleanup_failure`; any primary or cleanup envelope makes `Final.success` false.

The Pester corpus compares the complete ordered 55-call happy-path trace for rows 6, 10, and 104: every proxy acquisition, open/insert/mutation/Hyperlinks.Add/calc/save/close/Quit call, proxy IDs and kinds, all arguments, returned hyperlink proxy, and reverse release sequence. Fault cases assert exact `stage`, `occurrence`, `message`, `hresult`, and `winerror`; the combined primary/cleanup case asserts two release envelopes in occurrence order and an exact cleanup count.

Validation remains pending on a Windows host with Pester because this macOS worktree has neither `pwsh` nor `powershell`. `git diff --check` and static shell checks are run locally; no PowerShell pass is claimed without that runtime.
