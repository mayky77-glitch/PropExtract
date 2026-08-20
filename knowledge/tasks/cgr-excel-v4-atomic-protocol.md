---
card_id: cgr-excel-v4-atomic-protocol
status: review
version: 1
work_id: cgr-excel-row-contract-v4-20260818
task_id: atomic-protocol-wrapper-v1
purpose: Implement lease/ACK and single atomic outcome protocol through injected callbacks.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: aed40af042647ccaea5b455f4dfee8b311f6c0e3
dependency_shas: [aed40af042647ccaea5b455f4dfee8b311f6c0e3]
branch: codex/cgr-excel-atomic-protocol-v1
card_path: knowledge/tasks/cgr-excel-v4-atomic-protocol.md
write_scope: [scripts/WindowsExcelAtomicProtocol.psm1, tests/WindowsExcelAtomicProtocol.Tests.ps1, knowledge/tasks/cgr-excel-v4-atomic-protocol.md]
forbidden_paths: [scripts/windows_excel_insert.ps1, scripts/WindowsExcelInsert.Contract.psm1, README.md]
acceptance_commands: ["pwsh -NoProfile -File tests/WindowsExcelAtomicProtocol.Tests.ps1", "git diff --check"]
---

# Atomic protocol wrapper v1

Through injected callbacks, atomically write BOM-free JSON only after writer/stream Flush(true)+dispose; durable truthful lease precedes exact nonce ACK; no open callback before ACK. Preserve exact stage/HRESULT/WinError primary and first cleanup cause. Execute all cleanup callbacks independently, then publish exactly one final result/error artifact. Tests execute success/fault orders and replacement durability; unavailable Pester is blocking. No rejected PS reuse. Human commit/push; no merge/rebase/amend/force.

## Implementation evidence

- Feature SHA: `2b0da0c3916fce8d75e78d8dd9d6af8183b114ca`.
- Added `scripts/WindowsExcelAtomicProtocol.psm1`: an injected-callback wrapper that writes JSON with a BOM-free UTF-8 `FileStream`, calls `Flush($true)`, disposes the stream, then atomically replaces an existing destination with `File.Replace`. The lease is published before ACK read; `Open` is unreachable on any ACK mismatch.
- Added executable Pester coverage in `tests/WindowsExcelAtomicProtocol.Tests.ps1` for durable replacement/BOM absence, successful ordering and the single result artifact, invalid-ACK open exclusion, and independent cleanup with primary/first-cleanup diagnostics.
- Local host has neither `pwsh` nor `powershell`; Pester could not be executed. The test entry point deliberately fails if Pester is absent, so Windows Pester remains a blocking acceptance check.

## P6 remediation evidence

- Remediation SHA: `3bf3f8a7efb766439f91c7e3c9a6d7540572dc2f`.
- Before a result write, the wrapper removes a stale error artifact; before an error write, it removes a stale result artifact. If stale removal or atomic publication fails, it throws `excel_atomic_protocol_final_publication_failed:<artifact>:...`, attaches the captured primary/cleanup diagnostics, and never returns a successful result.
- Pester coverage now pre-seeds both stale-outcome directions and verifies the result/error XOR. Table-driven injected lease/open/execute/cleanup cases verify downstream exclusion, primary and first-cleanup HRESULT/WinError, and later-cleanup execution after the first cleanup failure. Final-publication failure handling is static-reviewed because the local host lacks PowerShell.

## False-success remediation evidence

- Remediation SHA: `b314f6ac9fd63580a8f242086c9e17a0eac845db`.
- Before any operation callback, the wrapper invalidates both prior final artifact paths. A locked or otherwise undeletable path raises `excel_atomic_protocol_final_artifact_invalidation_failed:<artifact>:...` with the original exception retained as `InnerException`; no lease, ACK, open, execute, or cleanup callback is entered.
- Final publication also removes an unexpected selected destination before its write, so a write/replace failure cannot expose an old selected artifact as this operation's outcome. The executable Windows Pester test uses a `FileShare.None` lock, proves zero callback events/no lease/no new result, and preserves the old artifact only as explicitly stale evidence after the failed gate.

## Residual risk

- The wrapper is not integrated into `windows_excel_insert.ps1` by design: that file is forbidden by this card. A Windows owner must run `pwsh -NoProfile -File tests/WindowsExcelAtomicProtocol.Tests.ps1` before merge/use with COM callbacks.
