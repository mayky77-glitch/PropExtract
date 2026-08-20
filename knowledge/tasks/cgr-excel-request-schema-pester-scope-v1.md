---
card_id: cgr-excel-request-schema-pester-scope-v1
status: ready
version: 1
work_id: cgr-excel-request-schema-pester-scope-v1-20260820
task_id: request-schema-pester-scope-v1
purpose: Make request-schema helpers available in Pester 5 run scope without changing production behavior.
role: tester
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: c38198251e30e9d17aeb85cae5d20954ca861224
dependency_shas: [c38198251e30e9d17aeb85cae5d20954ca861224]
branch: codex/cgr-excel-request-schema-pester-scope-v1
card_path: knowledge/tasks/cgr-excel-request-schema-pester-scope-v1.md
write_scope: [tests/WindowsExcelRequestSchema.Tests.ps1, knowledge/tasks/cgr-excel-request-schema-pester-scope-v1.md]
forbidden_paths: [scripts, rns_import_server, tests/WindowsExcelAtomicProtocol.Tests.ps1, tests/WindowsExcelFakeCom.Tests.ps1, .github, README.md]
acceptance_commands: ["pwsh -NoProfile -Command \"Import-Module Pester -RequiredVersion 5.6.1 -Force; $r = Invoke-Pester -Path tests/WindowsExcelRequestSchema.Tests.ps1 -PassThru; if ($null -eq $r -or $r.Result -ne 'Passed' -or $r.TotalCount -le 0 -or $r.PassedCount -ne $r.TotalCount -or $r.FailedCount -ne 0) { exit 1 }\"", "git diff --check"]
---

# Request-schema Pester run-scope v1

Windows run `32334308647` at exact `86fd903...` used PowerShell 7/Pester 5.6.1, discovered seven tests, then all seven failed because top-level helper `New-ValidRequestJson` was unavailable in Pester run scope.

Move module import and helper function definitions into the suite's `BeforeAll` run scope (or an equivalently explicit Pester 5 run-scope construct). Preserve all seven test bodies, assertions, Cyrillic/escaping cases, rows 6/10/104, callback no-op checks, and production module unchanged. No wrapper/fallback that bypasses Pester discovery.

Required: local static/diff checks, independent P6, then exact-SHA Windows Pester evidence. Human commit/push; no merge, rebase, amend, force-push, or unrelated edits.
