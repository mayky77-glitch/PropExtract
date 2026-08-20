---
card_id: cgr-excel-fake-com-runtime-v1
status: frozen
version: 1
work_id: cgr-excel-fake-com-runtime-v1-20260820
task_id: fake-com-runtime-v1
purpose: Repair fake-COM PowerShell 7 runtime behavior while retaining strict Pester 5 assertions.
role: tester
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: 3fa36b730aa13c41264698d67d01e910b98ab6d6
dependency_shas: [3fa36b730aa13c41264698d67d01e910b98ab6d6]
branch: codex/cgr-excel-fake-com-runtime-v1
card_path: knowledge/tasks/cgr-excel-fake-com-runtime-v1.md
write_scope: [tests/support/WindowsExcelFakeCom.psm1, tests/WindowsExcelFakeCom.Tests.ps1, knowledge/tasks/cgr-excel-fake-com-runtime-v1.md]
forbidden_paths: [scripts, rns_import_server, tests/WindowsExcelAtomicProtocol.Tests.ps1, tests/WindowsExcelRequestSchema.Tests.ps1, .github, README.md]
acceptance_commands: ["pwsh -NoProfile -File tests/WindowsExcelFakeCom.Tests.ps1", "git diff --check"]
---

# Fake-COM runtime v1

Exact Windows Pester 5.6.1 runs `32336263772` and `32336271382` at candidate `e687b55237beeb5495b2aedcd3c5e66081d347eb` discover all nine cases yet fail all nine. Successful row scenarios report only 20 instead of the required 55 trace events. Controlled fault envelopes lose their `stage`, `occurrence`, `hresult`, and `winerror`; release-only additionally creates an unintended null-valued-expression primary failure.

Repair only `tests/support/WindowsExcelFakeCom.psm1` runtime behavior. Keep the run-scope helpers and named parameter cases from parent `3fa36b7`; keep exact trace, fault occurrence/envelope, reverse release, classification, and wrapper assertions. No production/workflow changes. Static macOS checks cannot establish PowerShell behavior; acceptance requires a fresh exact-SHA Windows qualification run after review/integration.
