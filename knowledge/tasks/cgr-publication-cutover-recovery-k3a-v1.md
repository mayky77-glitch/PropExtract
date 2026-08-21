---
card_id: cgr-publication-cutover-recovery-k3a-v1
status: frozen
version: 2
supersedes: null
work_id: cgr-publication-cutover-recovery-k3a-v1
task_id: publication-cutover-recovery
purpose: "Make workbook cutover and post-hash recovery authoritative, durable, and replay-safe without performing finalizer side effects."
role: developer
card_path: knowledge/tasks/cgr-publication-cutover-recovery-k3a-v1.md
dependency_shas:
  - 0bd59c8522288170a53f9e99bb1e6e7ef7f5d986
branch: codex/cgr-publication-cutover-recovery-k3a-v1
write_scope:
  - knowledge/tasks/cgr-publication-cutover-recovery-k3a-v1.md
  - rns_import_server/workbook_cutover.py
  - rns_import_server/group_row_insertion.py
  - tests/test_workbook_cutover.py
  - tests/test_group_row_insertion.py
forbidden_paths:
  - rns_import_server/workbook_operation_journal.py
  - rns_import_server/registry_storage.py
  - rns_import_server/server.py
  - rns_import_server/static
  - scripts/windows_excel_insert.ps1
contract_versions:
  input: excel-handshake-cleanup-k2b2b-v2
  output: publication-cutover-recovery-k3a-v1
acceptance_commands:
  - PYTHONPATH=. python3 -m pytest -q tests/test_workbook_cutover.py tests/test_group_row_insertion.py tests/test_workbook_operation_journal.py tests/test_excel_native_contract.py
  - PYTHONPATH=. python3 -m pytest -q
  - python3 -m compileall -q rns_import_server/workbook_cutover.py rns_import_server/group_row_insertion.py tests/test_workbook_cutover.py tests/test_group_row_insertion.py
  - git diff --check
knowledge_paths:
  - knowledge/INDEX.md
  - knowledge/tasks/cgr-publication-cutover-recovery-k3a-v1.md
  - knowledge/tasks/orda-middle-row-insertion-plan.md
---

# Publication cutover and recovery K3a

## Frozen runtime contract

- K3a owns mutation only through durable phase `published`. It must not set capability/binding/history/report flags and must not transition to `finalized`; those are K3b side effects.
- Candidate `post_hash` is durable while the operation is `backup_verified`, before cutover. Cutover is one same-filesystem atomic replace to the request output, followed by file and parent-directory durability and exact post-hash verification. No copy/OpenPyXL/LibreOffice/raw-OOXML fallback is allowed.
- For an existing operation, the request output is the authoritative target when present; otherwise the prepublication source is authoritative. Same-path source/output remains supported. An existing unrelated output is a third hash and must not be overwritten.
- Recovery under the publication lock is hash/phase exact:
  - target equals `post_hash` and phase `backup_verified` -> transition once to `published`, return finalization pending, never invoke native mutation or replace again;
  - target equals `post_hash` and phase `published|finalized` -> return finalization pending/already finalized without mutation;
  - target equals `pre_hash` and phase is pre-publication -> re-resolution required;
  - target equals `pre_hash` at/after `published`, or any third/missing hash -> durable `manual_repair`, never overwrite.
- A failure after atomic replace must retain the known post-hash state and operation ID for recovery; it must never be rewritten as a prepublication retry. Journal/manual-repair failures are observable typed secondary evidence and are never swallowed.
- Both `new_row` mutation modes preserve the existing accepted validation/native/backup contracts. `group_provision`, finalizer ports, cleanup retention, server/UI and native Excel success evidence are excluded.

## Minimal acceptance evidence

- Real `WorkbookOperationJournal` restart tests cover crash after durable post-hash and after replace: exactly one physical cutover, no second native call, and `backup_verified→published` recovery.
- Compact matrix covers same-path and separate output, pre/post/third/missing target hashes, published/finalized replay, CAS failure after replace, manual-repair journal failure, and both mutation modes.
- Publication ordering proves candidate fsync → backup fsync/hash → durable post-hash → recheck → replace → target/parent fsync → post-hash verify → published. No finalizer flag or `finalized` transition occurs.
- Existing K1/K2A/K2B1/K2B2a/K2B2b tests stay green. Native Excel COM and full UI journey remain external Gates.

## K3a implementation evidence

- `workbook_cutover.py` provides same-filesystem replace, target and parent fsync, exact post-hash verification, and hash/phase-only recovery classification.
- `group_row_insertion.py` records post-hash before cutover, leaves finalizer flags and `finalized` to K3b, and exposes journal/manual-repair failures.
- Focused gate: `66 passed, 2 skipped` (native-Excel host skips). Full suite remains environment-blocked only by absent external corpus `/Users/x/Автоматизация РнС и ГРО/Реестр РНС Иркутск.xlsx`.
