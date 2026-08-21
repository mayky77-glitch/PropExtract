---
card_id: cgr-publication-action-history-k3b2b1-v1
status: frozen
version: 2
supersedes: null
work_id: cgr-publication-action-history-k3b2b1-v1
task_id: publication-action-history
purpose: "Persist new-row action authority and execute the real history finalizer after accepted binding."
role: database-engineer
card_path: knowledge/tasks/cgr-publication-action-history-k3b2b1-v1.md
dependency_shas:
  - a6e80ddbe3dc511a284f04f3d9d2b99a2b1c328b
branch: codex/cgr-publication-action-history-k3b2b1-v1
write_scope:
  - knowledge/tasks/cgr-publication-action-history-k3b2b1-v1.md
  - rns_import_server/new_row_action_store.py
  - rns_import_server/new_row.py
  - rns_import_server/registry_storage.py
  - rns_import_server/workbook_finalization.py
  - rns_import_server/workbook_operation_journal.py
  - rns_import_server/data/construction_registry.seed.sqlite3
  - rns_import_server/data/construction_registry.seed.manifest.json
  - tests/test_new_row_action_store.py
  - tests/test_new_row_action.py
  - tests/test_new_row_concurrency.py
  - tests/test_workbook_finalization.py
  - tests/test_registry_storage.py
  - tests/test_workbook_operation_journal.py
forbidden_paths:
  - rns_import_server/server.py
  - rns_import_server/group_row_insertion.py
  - rns_import_server/excel_native.py
  - rns_import_server/job_report.py
  - rns_import_server/action_history.py
  - scripts/windows_excel_insert.ps1
  - rns_import_server/static
  - README.md
contract_versions:
  input: publication-binding-finalizer-k3b2a-v1
  output: publication-action-history-k3b2b1-v1
acceptance_commands:
  - PYTHONPATH=. python3 -m pytest -q tests/test_new_row_action_store.py tests/test_new_row_action.py tests/test_new_row_concurrency.py tests/test_workbook_finalization.py tests/test_registry_storage.py tests/test_workbook_operation_journal.py tests/test_workbook_finalization_snapshot.py
  - RNS_REAL_CORPUS_PATH='/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/Автоматизация РнС и ГРО/Реестр РНС Иркутск.xlsx' PYTHONPATH=. python3 -m pytest -q
  - python3 scripts/build_construction_registry_seed.py --check
  - python3 scripts/validate_construction_registry_seed.py
  - python3 -m compileall -q rns_import_server/new_row_action_store.py rns_import_server/new_row.py rns_import_server/registry_storage.py rns_import_server/workbook_finalization.py rns_import_server/workbook_operation_journal.py tests/test_new_row_action_store.py tests/test_new_row_action.py tests/test_new_row_concurrency.py tests/test_workbook_finalization.py
  - git diff --check
knowledge_paths:
  - knowledge/INDEX.md
  - knowledge/tasks/cgr-publication-action-history-k3b2b1-v1.md
  - knowledge/components/workbook-publication.md
  - knowledge/tasks/implement-construction-group-routing-20260820.md
---

# Publication action/history finalizer K3b2b1

## Frozen contract

- Schema v5 adds private durable `new_row_pending_actions`, immutable `new_row_action_history`, and nullable journal `report_snapshot_digest`; verified v4 migration never invents authority or receipts. Seed and manifest are deterministic.
- `NewRowActionStore` is the concrete `NewRowPendingPort`. Registration is insert-or-verify; a changed job/construction/contract/target identity/canonical absolute non-symlink target path/capability digest conflicts. Raw capability is never persisted, reported or included in errors. Its domain-separated digest is bound to `action_id` and compared in constant time.
- Reservation is one durable `pending -> publishing` CAS. Concurrent callers have one winner. Reopen is allowed only after explicit pre-hash classification and only while no journal/post-hash authority exists. `published`/uncertain actions never reopen; `consumed` is replay-only.
- `finalize_published_history(storage, operation_id)` runs only after accepted K3b2a binding. In one `BEGIN IMMEDIATE`, revalidate current journal/snapshot/binding receipt and exact pending action authority, insert-or-verify the canonical version-1 event derived only from authority, and set `history_finalized` with its first timestamp.
- Canonical event: `action_id=operation_id`, `type=new_row`, `status=published`, snapshot `target_row`, journal `post_hash`; deterministic digest and no caller payload.
- Exact replay is zero-write. Concurrent callers converge. Generic `finalize_flag("history_finalized")` is forbidden. Report/capability flags remain zero, action remains `publishing`, phase remains `published`, and result is `published_pending_finalization` with next stage `report`.
- Deterministic action/authority/binding/history conflicts become durable `manual_repair`. SQLite faults roll back event+receipt, leave `published`, and return visible pending finalization. No workbook/native/report/server/UI side effect or fallback.

## Stable errors

- Stage `history`; operation ID retained; no capability/path/snapshot data in errors.
- `finalization_action_missing`, `finalization_action_conflict`, `finalization_history_order_invalid`, `finalization_history_authority_corrupt`, `finalization_history_conflict`, `finalization_history_storage_failed`, plus unchanged K3b1/K3b2a authority errors.

## Compact acceptance

- v4→v5 verified backup/schema/seed; legacy rows unchanged and unclaimed.
- Registration/reservation/reopen/restart/exact replay; raw capability absent; concurrent reserve one winner.
- Atomic history row+receipt, fault rollback and two-connection convergence; exact replay preserves every row/timestamp/generation.
- Missing/mismatched pending action, construction/contract/target, binding/snapshot/event evidence fail closed.
- History is ordered after binding and before report/capability/finalized; no forbidden side effects.
