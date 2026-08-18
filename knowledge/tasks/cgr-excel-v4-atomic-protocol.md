---
card_id: cgr-excel-v4-atomic-protocol
status: frozen
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
