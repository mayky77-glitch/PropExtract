---
card_id: cgr-publication-finalization-authority-k3b1-v1
status: frozen
version: 2
supersedes: null
work_id: cgr-publication-finalization-authority-k3b1-v1
task_id: publication-finalization-authority
purpose: "Make post-publication finalization input durable, sanitized, hash-bound and replay-safe before any finalizer side effect."
role: database-engineer
card_path: knowledge/tasks/cgr-publication-finalization-authority-k3b1-v1.md
dependency_shas:
  - e5f8dec41c0c00f8ce8c6e717a8db4163b8a7154
branch: codex/cgr-publication-finalization-authority-k3b1-v1
write_scope:
  - knowledge/tasks/cgr-publication-finalization-authority-k3b1-v1.md
  - rns_import_server/registry_storage.py
  - rns_import_server/workbook_operation_journal.py
  - rns_import_server/workbook_finalization_snapshot.py
  - rns_import_server/report_sanitization.py
  - rns_import_server/app.py
  - rns_import_server/group_row_insertion.py
  - rns_import_server/data/construction_registry.seed.sqlite3
  - rns_import_server/data/construction_registry.seed.manifest.json
  - tests/test_workbook_finalization_snapshot.py
  - tests/test_workbook_operation_journal.py
  - tests/test_registry_storage.py
  - tests/test_group_row_insertion.py
  - tests/test_report_observability.py
forbidden_paths:
  - rns_import_server/server.py
  - rns_import_server/new_row.py
  - rns_import_server/group_provisioning.py
  - rns_import_server/excel_native.py
  - scripts/windows_excel_insert.ps1
  - rns_import_server/static
  - README.md
contract_versions:
  input: publication-cutover-recovery-k3a-v1
  output: publication-finalization-authority-k3b1-v1
acceptance_commands:
  - PYTHONPATH=. python3 -m pytest -q tests/test_workbook_finalization_snapshot.py tests/test_workbook_operation_journal.py tests/test_registry_storage.py tests/test_group_row_insertion.py tests/test_report_observability.py
  - python3 scripts/build_construction_registry_seed.py --check
  - python3 scripts/validate_construction_registry_seed.py
  - PYTHONPATH=. python3 -m pytest -q
  - python3 -m compileall -q rns_import_server/registry_storage.py rns_import_server/workbook_operation_journal.py rns_import_server/workbook_finalization_snapshot.py rns_import_server/report_sanitization.py rns_import_server/app.py rns_import_server/group_row_insertion.py tests/test_workbook_finalization_snapshot.py tests/test_workbook_operation_journal.py tests/test_registry_storage.py tests/test_group_row_insertion.py tests/test_report_observability.py
  - git diff --check
knowledge_paths:
  - knowledge/INDEX.md
  - knowledge/tasks/cgr-publication-finalization-authority-k3b1-v1.md
  - knowledge/components/workbook-publication.md
  - knowledge/tasks/implement-construction-group-routing-20260820.md
---

# Publication finalization authority K3b1

## Frozen authority contract

- `new_row` durable `consumer_id` is exactly its action ID. New journal operations also require a nonblank `workbook_contract_id`; it is immutable replay authority and part of the intent identity. Legacy rows may retain `NULL`, but migration never invents a contract.
- Registry schema v4 adds nullable legacy journal `workbook_contract_id` and a one-row-per-operation `workbook_finalization_snapshots` table: operation ID, snapshot version, canonical payload JSON, SHA-256 digest and created-at timestamp. Migration starts from a verified backup and preserves all legacy values.
- Before cutover, while journal phase is `backup_verified`, one `BEGIN IMMEDIATE` transaction atomically insert-or-verifies the snapshot and records the same candidate `post_hash`. Either both become durable or neither does.
- Snapshot input comes only from an obligatory server-held-state builder port. Disk JSON/report is never read as authority. Payload is exactly action ID, target row and sanitized report payload; journal join supplies construction/RNS, workbook contract, target/sheet/template and hashes.
- The canonical envelope digest covers operation ID, snapshot version and payload. Action ID must equal journal consumer ID; `report_payload.final_state.workbook_sha256` must equal the lowercase 64-hex post hash. Payload is strict JSON: no proxies, bytes, non-string keys, NaN/Infinity or lossy `default=str`; maximum canonical payload size is 16 MiB.
- Move the one canonical safe report projection to `report_sanitization.py`; `app.safe_report_projection` remains a behavior-compatible import/re-export. Capability/auth/raw OCR/local paths remain excluded and callers' in-memory objects are not mutated.
- `backup_verified -> published` requires a present snapshot whose canonical payload/digest still verifies. Exact replay performs no write. Different action, contract, hash or payload fails closed and preserves first authority.
- K3b1 stops at `published`. It executes no binding/history/report/capability finalizer, sets no finalizer flag, never transitions to `finalized`, and deletes no operation artifact. Seed binding insert-or-verify is a later K3b2 Gate.

## Errors and ordering

- Stable typed codes: `workbook_contract_id_required`, `consumer_action_identity_mismatch`, `finalization_snapshot_required`, `finalization_snapshot_invalid`, `finalization_snapshot_too_large`, `finalization_snapshot_conflict`, `finalization_authority_missing`, `finalization_authority_corrupt`, `finalization_authority_journal_failed`.
- `group_row_insertion` reports these at stage `finalization_authority` with operation ID and original cause, never payload/report contents. Failure leaves target at pre-hash, performs no replace/finalizer and does not claim success.
- Ordering remains validation → candidate fsync → backup/hash → snapshot-builder → atomic snapshot+post-hash → target recheck → atomic replace → target/parent fsync → hash verify → `published`.

## Compact acceptance

- v3→v4 migration/backup/schema and deterministic seed/manifest; legacy rows remain value-identical with no invented authority.
- Reserve requires contract; exact replay is no-write; changed contract/action/payload/hash conflicts. SQLite failure proves both post hash and snapshot absent.
- Sanitizer compatibility plus strict JSON/type/size/privacy tests. Published without snapshot or with corrupted digest is blocked.
- Group ordering/failure tests prove no replace or finalizer before durable authority. Restart reuses the exact snapshot; a terminal repair anomaly preserves snapshot and all timestamps.
- Native Excel, finalizer execution, server/UI and full user journey are explicitly not claimed.

## Implementation evidence

- Schema v4 adds nullable legacy `workbook_contract_id` and `workbook_finalization_snapshots`; v3→v4 takes the verified pre-migration backup and leaves legacy contracts `NULL`.
- New v2 new-row operations require a nonblank immutable contract and `consumer_id == action_id`. Explicit `intent-v1` rows remain legacy-compatible only; they cannot satisfy v2 publication authority.
- `record_finalization_authority` inserts/verifies the canonical sanitized snapshot and records `post_hash` in one `BEGIN IMMEDIATE` transaction. `published` verifies the snapshot digest and fails closed when it is absent/corrupt.
- Focused: `117 passed, 2 skipped` (snapshot, journal, storage, group insertion, report observability, native-contract compatibility); seed build/check and validator green; compileall/diff green.
- Full: `1675 passed, 2 skipped`, with 12 pre-existing environment-only failures from the documented stale absolute XLSX path `/Users/x/Автоматизация РнС и ГРО/Реестр РНС Иркутск.xlsx`, plus one known OpenPyXL x14 warning. No source XLSX was copied, linked, or mutated.

## P6 remediation evidence

- `published` now revalidates the full stored payload against the current journal authority: exact action/consumer identity, required immutable workbook contract, target-row schema and `report_payload.final_state.workbook_sha256 == journal.post_hash`. A forged canonical payload with a recomputed digest is blocked.
- Legacy v1/null-contract data is readable only through an exact replay of an already persisted row. Every fresh `create`/`reserve`, including an intent-v1 shaped request, requires a contract and action/consumer identity.
- Finalization input validation runs before report projection, accepting only exact JSON primitives/containers with string keys and finite numbers. The 16 MiB ceiling applies exactly to canonical payload, not the digest envelope. Allowlisted typed authority codes reach `finalization_authority` without report/payload text.
- Remediation-owned focused: `105 passed`; seed build/check and validator, compileall/diff green. Full: `1680 passed, 2 skipped`, 12 known stale absolute-XLSX failures plus one intentionally stale forbidden test fixture `tests/test_excel_native_contract.py::test_verified_lease_commits_real_sqlite_journal_before_ack_and_open` (fresh null-contract/consumer-mismatch new-row input now correctly raises `workbook_contract_id_required`); one known OpenPyXL x14 warning.
