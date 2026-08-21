---
card_id: cgr-publication-binding-finalizer-k3b2a-v1
status: frozen
version: 2
supersedes: null
work_id: cgr-publication-binding-finalizer-k3b2a-v1
task_id: publication-binding-finalizer
purpose: "Execute and receipt the first real post-publication side effect: replay-safe construction/workbook binding."
role: database-engineer
card_path: knowledge/tasks/cgr-publication-binding-finalizer-k3b2a-v1.md
dependency_shas:
  - 905421cb8c7fe02b2018146dc23580e84af37fa4
branch: codex/cgr-publication-binding-finalizer-k3b2a-v1
write_scope:
  - knowledge/tasks/cgr-publication-binding-finalizer-k3b2a-v1.md
  - rns_import_server/workbook_finalization.py
  - rns_import_server/registry_storage.py
  - rns_import_server/workbook_operation_journal.py
  - tests/test_workbook_finalization.py
  - tests/test_registry_storage.py
  - tests/test_workbook_operation_journal.py
forbidden_paths:
  - rns_import_server/server.py
  - rns_import_server/new_row.py
  - rns_import_server/group_provisioning.py
  - rns_import_server/group_row_insertion.py
  - rns_import_server/excel_native.py
  - scripts/windows_excel_insert.ps1
  - rns_import_server/static
  - README.md
contract_versions:
  input: publication-finalization-authority-k3b1-v1
  output: publication-binding-finalizer-k3b2a-v1
acceptance_commands:
  - RNS_REAL_CORPUS_PATH='/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/Автоматизация РнС и ГРО/Реестр РНС Иркутск.xlsx' PYTHONPATH=. python3 -m pytest -q tests/test_workbook_finalization.py tests/test_registry_storage.py tests/test_workbook_operation_journal.py tests/test_workbook_finalization_snapshot.py
  - RNS_REAL_CORPUS_PATH='/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/Автоматизация РнС и ГРО/Реестр РНС Иркутск.xlsx' PYTHONPATH=. python3 -m pytest -q
  - python3 -m compileall -q rns_import_server/workbook_finalization.py rns_import_server/registry_storage.py rns_import_server/workbook_operation_journal.py tests/test_workbook_finalization.py tests/test_registry_storage.py tests/test_workbook_operation_journal.py
  - git diff --check
knowledge_paths:
  - knowledge/INDEX.md
  - knowledge/tasks/cgr-publication-binding-finalizer-k3b2a-v1.md
  - knowledge/components/workbook-publication.md
  - knowledge/tasks/implement-construction-group-routing-20260820.md
---

# Publication binding finalizer K3b2a

## Frozen contract

- Add `finalize_published_binding(storage, operation_id) -> FinalizationProgress`. It owns only the binding stage and returns `published_pending_finalization`, `completed_stage="binding"`, `next_stage="history"` after success. It never executes history/report/capability, never touches XLSX/native Excel and never transitions to `finalized`.
- In one `BEGIN IMMEDIATE` transaction join the published journal row and K3b1 snapshot. Revalidate phase, operation kind, action/consumer identity, nonblank workbook contract, lowercase 64-hex post hash and canonical snapshot/digest bound to current authority.
- Derive the binding tuple only from durable journal authority: construction ID, workbook contract ID, target/sheet identity, template version and `verified_state="verified"`.
- Zero binding rows: insert exactly once and increment registry generation exactly once. One exact row: verify with zero insert/generation/timestamp change. Different or ambiguous rows fail closed. Concurrent SQLite callers converge on one binding.
- Set `binding_finalized` and its first timestamp in the same transaction as insert/verification. Exact restart replay performs zero writes and preserves binding ID, generation and timestamp.
- Direct `finalize_flag("binding")` without a verified binding is forbidden. History/report/capability flags stay zero and phase stays `published`.
- Deterministic authority/binding conflicts become durable `manual_repair` with a bounded code. Transient SQLite failure rolls back insert+receipt, leaves `published`, and returns visible pending finalization; it never retries workbook insertion or claims binding success.

## Stable errors

- Stage is `binding`, operation ID is retained and snapshot/report contents are never exposed.
- Codes: `finalization_operation_missing`, `finalization_phase_invalid`, `finalization_authority_missing`, `finalization_authority_corrupt`, `finalization_binding_construction_invalid`, `finalization_binding_conflict`, `finalization_binding_storage_failed`, `finalization_receipt_required`.

## Compact acceptance

- Fresh unbound construction gets one exact binding and one receipt; exact replay is no-write.
- Pre-existing exact binding is accepted. Different/ambiguous binding, corrupt snapshot, wrong phase and receipt-without-binding fail closed.
- Fault between insert and receipt rolls both back; two database connections converge on one row.
- No history/report/capability flag or finalizer side effect; phase remains `published` on success.
- Full suite, compileall and diff check. K3b2b server-adjacent history/report/capability remains a separate Gate.
