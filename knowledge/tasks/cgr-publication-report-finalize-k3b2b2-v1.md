---
card_id: cgr-publication-report-finalize-k3b2b2-v1
status: frozen
version: 2
supersedes: null
work_id: cgr-publication-report-finalize-k3b2b2-v1
task_id: publication-report-finalize
purpose: "Publish the snapshot-owned report, consume action capability, and complete finalization without replaying mutation."
role: developer
card_path: knowledge/tasks/cgr-publication-report-finalize-k3b2b2-v1.md
dependency_shas:
  - cde0653a3622b1cf9f3df76370e0b198d2c20f36
branch: codex/cgr-publication-report-finalize-k3b2b2-v1
write_scope:
  - knowledge/tasks/cgr-publication-report-finalize-k3b2b2-v1.md
  - rns_import_server/workbook_finalization.py
  - rns_import_server/workbook_operation_journal.py
  - rns_import_server/new_row_action_store.py
  - rns_import_server/job_report.py
  - rns_import_server/new_row.py
  - tests/test_workbook_finalization.py
  - tests/test_workbook_finalization_report.py
  - tests/test_new_row_action_store.py
  - tests/test_new_row_action.py
forbidden_paths:
  - rns_import_server/server.py
  - rns_import_server/registry_storage.py
  - rns_import_server/group_row_insertion.py
  - rns_import_server/excel_native.py
  - rns_import_server/action_history.py
  - rns_import_server/audit.py
  - rns_import_server/data
  - scripts/windows_excel_insert.ps1
  - rns_import_server/static
  - README.md
contract_versions:
  input: publication-action-history-k3b2b1-v1
  output: publication-report-finalize-k3b2b2-v1
acceptance_commands:
  - PYTHONPATH=. python3 -m pytest -q tests/test_workbook_finalization.py tests/test_workbook_finalization_report.py tests/test_new_row_action_store.py tests/test_new_row_action.py tests/test_workbook_operation_journal.py tests/test_report_observability.py tests/test_admin_row_edit_regressions.py tests/test_admin_server.py
  - RNS_REAL_CORPUS_PATH='/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/Автоматизация РнС и ГРО/Реестр РНС Иркутск.xlsx' PYTHONPATH=. python3 -m pytest -q
  - python3 -m compileall -q rns_import_server/workbook_finalization.py rns_import_server/workbook_operation_journal.py rns_import_server/new_row_action_store.py rns_import_server/job_report.py rns_import_server/new_row.py tests/test_workbook_finalization.py tests/test_workbook_finalization_report.py tests/test_new_row_action_store.py tests/test_new_row_action.py
  - git diff --check
knowledge_paths:
  - knowledge/INDEX.md
  - knowledge/tasks/cgr-publication-report-finalize-k3b2b2-v1.md
  - knowledge/components/workbook-publication.md
  - knowledge/tasks/implement-construction-group-routing-20260820.md
---

# Publication report/capability/finalized K3b2b2

## Frozen contract

- Add `finalize_published_operation(storage, operation_id) -> FinalizationProgress`. For a published operation it verifies/runs accepted binding then history, publishes the report, consumes the action, and performs the sole terminal transition. It never invokes workbook/native mutation and never reopens pending.
- Resolve the workbook target only from the private durable pending-action row. Require canonical absolute regular non-symlink target and exact journal `post_hash` before every post-publication stage. Missing/third hash is durable `manual_repair`; never overwrite the workbook.
- Revalidate K3b1 canonical snapshot and decode only its stored sanitized `report_payload`. The disk report is never authority. Capability, target path, raw OCR and the snapshot envelope must not appear in report/errors.
- Report bytes are strict canonical JSON plus one LF. Publish with a same-directory private temporary file, file fsync, atomic replace and parent-directory fsync; no permissive `default=str`, chmod-only security claim or weaker writer fallback. Reopen without following links, require regular file, exact bytes and digest. Existing corrupt/deleted report is replaced from snapshot; an exact report is no-write. Replacing a report symlink must leave the external target unchanged.
- After disk verification, atomically set `report_finalized`, first timestamp and `report_snapshot_digest`. A crash after replace but before receipt reuses the exact file and records only the receipt.
- Capability consumption is one SQLite transaction: revalidate current journal/snapshot/history and action `publishing`, CAS it to `consumed`, then set `capability_finalized` and its first timestamp. Because `action_id == operation_id`, immutable journal `post_hash` and snapshot `target_row` are the authority; no duplicate schema columns are added. Exact consumed replay is no-write; incoherent state/evidence fails closed.
- Reverify target/report/binding/history/action receipts, then perform the only `published -> finalized` CAS. Disable generic report/capability flags and generic finalization transition without concrete receipts. Exact finalized replay verifies every side effect and changes no DB row, report byte or timestamp.
- Failure before/after any receipt returns explicit `published_pending_finalization` with next stage. Deterministic authority/target/conflict becomes durable `manual_repair`; transient filesystem/SQLite failure stays visibly pending. No success/no-op/fallback may hide incomplete finalization.

## Stable errors

- Preserve operation ID and stage; never include path/report contents/capability.
- `finalization_report_path_invalid`, `finalization_target_hash_mismatch`, `finalization_report_write_failed`, `finalization_report_verify_failed`, `finalization_report_receipt_failed`, `finalization_capability_order_invalid`, `finalization_capability_conflict`, `finalization_capability_storage_failed`, `finalization_order_invalid`, `finalization_journal_failed`.

## Compact acceptance

- Exact happy path: binding → history → report → capability → finalized, with one event and no native/workbook call.
- Crash/replay after report replace, report receipt and capability CAS; exact finalized replay is fully no-write.
- Report missing/corrupt/symlink, target missing/third hash, capability state/hash/row conflicts and restart without plaintext capability.
- Strict canonical bytes/privacy/private-file behavior; no directory-fsync or permission fallback.
- Stage order, typed errors and full preservation of prior report/history behavior.
