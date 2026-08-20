---
card_id: cgr-excel-fake-com-pester-scope-v1
status: frozen
version: 1
work_id: cgr-excel-fake-com-pester-scope-v1-20260820
task_id: fake-com-pester-scope-v1
purpose: Restore exact fake-COM corpus execution under Pester 5 run scope without changing product behavior.
role: tester
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: 6f689ae27163eff18a4472727d94407d5f9334fb
dependency_shas: [6f689ae27163eff18a4472727d94407d5f9334fb]
branch: codex/cgr-excel-fake-com-pester-scope-v1
card_path: knowledge/tasks/cgr-excel-fake-com-pester-scope-v1.md
write_scope: [tests/WindowsExcelFakeCom.Tests.ps1, knowledge/tasks/cgr-excel-fake-com-pester-scope-v1.md]
forbidden_paths: [scripts, rns_import_server, tests/support/WindowsExcelFakeCom.psm1, tests/WindowsExcelAtomicProtocol.Tests.ps1, tests/WindowsExcelRequestSchema.Tests.ps1, .github, README.md]
acceptance_commands: ["pwsh -NoProfile -File tests/WindowsExcelFakeCom.Tests.ps1", "git diff --check"]
---

# Fake-COM Pester run-scope v1

Windows run `32335701771` at qualification SHA `6725aa82468115426e45cc5c6519d69aa2b4ae78` discovered nine fake-COM tests and failed all nine. Pester 5 executes `It` bodies in run scope, where discovery-scope module import and helper functions were absent. Scalar `-ForEach` datasets also passed `0` or null instead of intended rows/stages.

Move fake-module import and all four test helpers (`New-ExpectedFakeComCall`, `Get-ExpectedFakeComTrace`, `Assert-ExactFakeComTrace`, `Assert-ExactFailureEnvelope`) into the suite `BeforeAll`. Replace scalar datasets with named hashtable cases for `row` and `stage`. Preserve exactly nine expanded test cases, full 55-event trace comparison, fault occurrence/envelope assertions, and fail-closed wrapper. Do not edit production or weaken a release-only assertion; first verify whether its null-valued-expression result remains after Pester scope/data repair.

Local macOS validation is restricted to static/diff checks because `pwsh` and `powershell` are unavailable. Exact-SHA Windows Pester evidence remains mandatory for acceptance.
