---
card_id: cgr-wave3-workbook-authority-wa2b
status: frozen
version: 2
work_id: cgr-wave3-workbook-authority-wa2b
task_id: workbook-authority-wa2b
purpose: "Require the accepted WA2a authority refresh as the first v3 finalizer stage while preserving exact legacy v1/v2 behavior."
role: default
card_path: knowledge/tasks/cgr-wave3-workbook-authority-wa2b.md
dependency_shas:
  - a2fff925f05def1e7ba55ce0ec50f6c55dc13531
branch: codex/cgr-wave3-workbook-authority-wa2b
write_scope:
  - knowledge/tasks/cgr-wave3-workbook-authority-wa2b.md
  - rns_import_server/workbook_finalization.py
  - tests/test_workbook_authority_finalization.py
forbidden_paths:
  - README.md
  - rns_import_server/registry_storage.py
  - rns_import_server/data/construction_registry.seed.sqlite3
  - rns_import_server/data/construction_registry.seed.manifest.json
  - rns_import_server/workbook_authority.py
  - rns_import_server/workbook_authority_refresh.py
  - rns_import_server/workbook_projection.py
  - rns_import_server/workbook_operation_journal.py
  - rns_import_server/workbook_finalization_snapshot.py
  - rns_import_server/group_row_insertion.py
  - rns_import_server/new_row_action_store.py
  - rns_import_server/server.py
  - rns_import_server/static
  - rns_import_server/app.py
  - rns_import_server/operation_log.py
  - rns_import_server/excel_native.py
contract_versions:
  input: durable-workbook-authority-refresh-transaction-v1
  output: workbook-finalization-authority-order-v1
acceptance_commands:
  - PYTHONPATH=. python3 -m pytest -q tests/test_workbook_finalization.py tests/test_workbook_finalization_report.py tests/test_workbook_authority_refresh.py tests/test_workbook_authority_finalization.py
  - python3 -m compileall -q rns_import_server/workbook_finalization.py tests/test_workbook_authority_finalization.py
  - git diff --check
knowledge_paths:
  - knowledge/INDEX.md
  - knowledge/tasks/cgr-wave3-workbook-authority-wa2b.md
  - knowledge/components/workbook-publication.md
  - knowledge/tasks/implement-construction-group-routing-20260820.md
---

# Workbook authority WA2b

## Frozen boundary

- Start only from accepted common `a2fff925f05def1e7ba55ce0ec50f6c55dc13531`; rejected WA2 `d500b3dfb9a72ed1fc144b7704ade9273c7d6498` is forbidden ancestry/source input.
- Preserve accepted WA2a refresh module/API byte-for-byte at Git blob `904ffe2b3905d0255bdb256cae6bf332e0bc0860`. Preserve schema/seed, WA1 authority blob `093e6c02b624be4f8138ec7c6b3a74aecc6e3f8f`, projection, journal/snapshot/group/native/server/UI/log implementations.
- Own only coordinator ordering in `workbook_finalization.py` and one new focused test module. No schema migration, workbook mutation, native call, second insertion, bridge or public API expansion.

## Ordering contract

- `manifest_version == group-row-manifest-v3` requires accepted `refresh_published_authority(storage, operation_id)` as the first finalizer stage, before binding, history, report, capability consumption or terminal `finalized`.
- Only `refreshed` or exact verified `replayed` may proceed. The coordinator must verify the immutable receipt before any downstream first write; missing/corrupt/contradictory receipt or refresh manual-repair result becomes typed manual repair. A transient refresh target/SQLite failure remains `published_pending_finalization` with refresh as the next stage.
- Exact accepted legacy `manifest-v1` and `manifest-v2` behavior remains byte/logically unchanged and bypasses WA2a refresh. Every other manifest value/type fails closed to manual repair before downstream writes.
- After verified v3 refresh, retain accepted order `binding -> history -> report -> capability -> finalized`. Existing target-post-hash preflights remain immediately before every first downstream write.
- Restart after a committed refresh replays/verifies the receipt without authority/generation/receipt writes, then continues later stages. Contradiction never attempts later stages. Concurrency produces at most one refresh/receipt and one existing downstream side-effect chain.

## Essential compact tests

- v3 success proves refresh/receipt precedes binding, history, report, capability and finalized.
- Crash/restart after refresh proves exact receipt replay is zero-write before later stages; transient refresh remains pending; contradiction and missing/corrupt receipt become manual repair with no downstream writes.
- Unknown manifest fails closed before refresh/downstream writes; exact `manifest-v1` and `manifest-v2` preserve accepted legacy finalization without refresh.
- Concurrency and spies prove no native/workbook mutation or second insertion, and target-hash checks still precede every first downstream write.

## Gate

- One P4 implementation attempt, at most one localized remediation, then independent P6. Reject after that blocks WA2b. No integration before P6 acceptance.
