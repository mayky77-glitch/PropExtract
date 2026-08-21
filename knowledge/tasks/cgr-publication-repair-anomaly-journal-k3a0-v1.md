---
card_id: cgr-publication-repair-anomaly-journal-k3a0-v1
status: frozen
version: 1
supersedes: null
work_id: cgr-publication-repair-anomaly-journal-k3a0-v1
task_id: publication-repair-anomaly-journal
purpose: "Provide one durable idempotent journal operation for repair anomalies discovered after manual-repair or finalized phases."
role: database-engineer
card_path: knowledge/tasks/cgr-publication-repair-anomaly-journal-k3a0-v1.md
dependency_shas:
  - 0bd59c8522288170a53f9e99bb1e6e7ef7f5d986
branch: codex/cgr-publication-repair-anomaly-journal-k3a0-v1
write_scope:
  - knowledge/tasks/cgr-publication-repair-anomaly-journal-k3a0-v1.md
  - rns_import_server/workbook_operation_journal.py
  - tests/test_workbook_operation_journal.py
forbidden_paths:
  - rns_import_server/registry_storage.py
  - rns_import_server/group_row_insertion.py
  - rns_import_server/workbook_cutover.py
  - rns_import_server/server.py
  - rns_import_server/static
  - scripts/windows_excel_insert.ps1
contract_versions:
  input: excel-handshake-cleanup-k2b2b-v2
  output: publication-repair-anomaly-journal-k3a0-v1
acceptance_commands:
  - PYTHONPATH=. python3 -m pytest -q tests/test_workbook_operation_journal.py
  - PYTHONPATH=. python3 -m pytest -q tests/test_group_row_insertion.py tests/test_workbook_operation_journal.py tests/test_excel_native_contract.py
  - PYTHONPATH=. python3 -m pytest -q
  - python3 -m compileall -q rns_import_server/workbook_operation_journal.py tests/test_workbook_operation_journal.py
  - git diff --check
knowledge_paths:
  - knowledge/INDEX.md
  - knowledge/tasks/cgr-publication-repair-anomaly-journal-k3a0-v1.md
  - knowledge/tasks/cgr-publication-cutover-recovery-k3a-v1.md
---

# Publication repair-anomaly journal K3a0

## Frozen runtime contract

- Add one narrow journal operation for a hash/target repair anomaly discovered when an operation is already `manual_repair` or `finalized`. Do not widen the ordinary phase-transition graph.
- For `manual_repair`, an exact replay with the same bounded failure code is idempotent and returns the existing row without changing timestamps or prior evidence. A different failure code is a typed conflict; the first durable evidence is preserved.
- For `finalized`, the operation moves durably to `manual_repair`, records the bounded failure code, and preserves every completed finalizer flag/timestamp plus `finalized_at` as historical evidence. It must not clear post-hash, ownership, manifest, or authority fields.
- Missing operation, malformed failure code, unsupported phase, stale concurrent phase, or SQLite failure is typed and fail-closed. No boolean/blank/oversized code is accepted.
- The update is one SQLite transaction/CAS and is safe under two real connections. Concurrent exact callers produce one logical repair record; a competing different code cannot overwrite it.
- No migration, schema version change, workbook mutation, finalizer side effect, retry, compatibility fallback, or server/UI behavior is introduced.

## Minimal acceptance evidence

- Real SQLite tests cover `finalized -> manual_repair`, exact replay from `manual_repair`, conflicting replay, missing operation, unsupported phase, and bounded failure-code lexicals.
- Finalized flags/timestamps and `finalized_at` remain byte/value-identical after the anomaly is recorded; post-hash and authority fields are unchanged.
- A two-connection barrier proves one exact durable result and no lost update; a different-code contender returns typed conflict.
- Existing journal transition, lease, publication-authority, and recovery tests remain green.
