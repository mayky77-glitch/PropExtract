---
card_id: cgr-excel-atomic-windows-replace-v1
status: ready
version: 1
work_id: cgr-excel-atomic-windows-replace-v1-20260820
task_id: atomic-windows-replace-v1
purpose: Fix Windows File.Replace backup semantics and Pester run scope without weakening atomic publication.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: 20eb66a2328ac201803e16c30de8f08ca9541b85
dependency_shas: [20eb66a2328ac201803e16c30de8f08ca9541b85]
branch: codex/cgr-excel-atomic-windows-replace-v1
card_path: knowledge/tasks/cgr-excel-atomic-windows-replace-v1.md
write_scope: [scripts/WindowsExcelAtomicProtocol.psm1, tests/WindowsExcelAtomicProtocol.Tests.ps1, knowledge/tasks/cgr-excel-atomic-windows-replace-v1.md]
forbidden_paths: [rns_import_server, tests/WindowsExcelRequestSchema.Tests.ps1, tests/WindowsExcelFakeCom.Tests.ps1, .github, README.md]
acceptance_commands: ["pwsh -NoProfile -Command \"Import-Module Pester -RequiredVersion 5.6.1 -Force; $env:WINDOWS_EXCEL_ATOMIC_PROTOCOL_PESTER='1'; $r=Invoke-Pester -Path tests/WindowsExcelAtomicProtocol.Tests.ps1 -PassThru; if ($null -eq $r -or $r.Result -ne 'Passed' -or $r.TotalCount -le 0 -or $r.PassedCount -ne $r.TotalCount -or $r.FailedCount -ne 0) { exit 1 }\"", "git diff --check"]
---

# Atomic Windows replace v1

Windows run `32334764251` at exact `0f9c472...` used pwsh/Pester 5.6.1. Atomic suite discovered 13: 10 passed, 3 failed.

## Frozen remediation

- Production failure: `[IO.File]::Replace($temporary, $destination, $null)` throws `ArgumentException: The path is empty` on the Windows runner. Use a unique same-directory backup path for `File.Replace`, then remove that backup deterministically. Preserve Flush(true) → Dispose → atomic Replace ordering, final artifact XOR, stale-artifact invalidation, exact primary/cleanup diagnostics, and no false success. Cleanup failure must surface explicitly; never silently fall back to non-atomic copy/move when destination exists.
- Test-scope failures: `$modulePath` defined only in Pester discovery scope was null in two run-phase tests. Put module path/import in `BeforeAll` or equivalent Pester 5 run scope. Preserve all 13 test bodies/semantics and every fault assertion.
- Add assertions that replacement leaves neither `*.tmp` nor backup artifacts and that the old destination is replaced with BOM-free new JSON.

Required: independent P6, then exact-SHA Windows Pester with all 13 passed and zero failed/skipped/not-run. Human commit/push; no merge, rebase, amend, force-push, or unrelated edits.
