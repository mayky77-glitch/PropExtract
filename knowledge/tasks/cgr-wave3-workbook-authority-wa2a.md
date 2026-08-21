---
card_id: cgr-wave3-workbook-authority-wa2a
status: frozen
version: 2
supersedes: cgr-wave3-workbook-authority-wa2
work_id: cgr-wave3-workbook-authority-wa2a
task_id: workbook-authority-wa2a
purpose: "Atomically replace one published workbook authority and record a reconstructable immutable receipt without changing finalizers or WA1 APIs."
role: default
card_path: knowledge/tasks/cgr-wave3-workbook-authority-wa2a.md
dependency_shas:
  - b161abd3b723af89aa1512892725f5072c76fe35
branch: codex/cgr-wave3-workbook-authority-wa2a
write_scope:
  - knowledge/tasks/cgr-wave3-workbook-authority-wa2a.md
  - rns_import_server/registry_storage.py
  - rns_import_server/workbook_authority_refresh.py
  - rns_import_server/data/construction_registry.seed.sqlite3
  - rns_import_server/data/construction_registry.seed.manifest.json
  - tests/test_registry_storage.py
  - tests/test_workbook_authority_refresh.py
forbidden_paths:
  - README.md
  - rns_import_server/workbook_authority.py
  - rns_import_server/workbook_projection.py
  - rns_import_server/workbook_finalization.py
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
  input: durable-workbook-authority-v1
  output: durable-workbook-authority-refresh-transaction-v1
acceptance_commands:
  - PYTHONPATH=. python3 -m pytest -q tests/test_registry_storage.py tests/test_workbook_authority.py tests/test_workbook_authority_refresh.py
  - python3 scripts/build_construction_registry_seed.py --check
  - python3 scripts/validate_construction_registry_seed.py
  - python3 -m compileall -q rns_import_server/registry_storage.py rns_import_server/workbook_authority_refresh.py tests/test_registry_storage.py tests/test_workbook_authority_refresh.py
  - git diff --check
knowledge_paths:
  - knowledge/INDEX.md
  - knowledge/tasks/cgr-wave3-workbook-authority-wa2a.md
  - knowledge/components/workbook-publication.md
  - knowledge/tasks/implement-construction-group-routing-20260820.md
---

# Workbook authority WA2a

## Frozen source and boundary

- Start fresh from accepted `b161abd3b723af89aa1512892725f5072c76fe35`. Rejected WA2 tips `6cf73de98a1c0932844911a7e8ba2e6c68ae1681` and `d500b3dfb9a72ed1fc144b7704ade9273c7d6498` are forbidden ancestry and source-copy inputs.
- Preserve `rns_import_server/workbook_authority.py` byte-for-byte at Git blob `093e6c02b624be4f8138ec7c6b3a74aecc6e3f8f`; pending WA1 enrollment/producer continues to require exact row-3 A:X template evidence. Preserve projection blob `ded36da32cbeb445197b573f7727790fc89594b1` and finalizer blob `7bafb17b9d13e293fd25ab7958fec95d9db73486`.
- WA2a owns no finalizer ordering, binding/history/report/capability/finalized transition, publisher/bridge, server/UI, native Excel or operation log. WA2b is the only future owner of finalizer ordering.

## Schema v7

- Advance accepted schema v6 to v7 with an empty migration and deterministic `construction-registry-v7` seed/manifest. Seed and migration create no authority, action, operation, refresh receipt, ownership or real-corpus enrollment.
- Add `workbook_authority_refresh_receipts`, keyed by `operation_id`, with exact action ID, receipt version 1, manifest version `group-row-manifest-v3`, mutation mode, target row, pre/post SHA-256, prior/successor generation, canonical predecessor/successor authority payloads and their domain-separated SHA-256 digests, an envelope receipt digest and canonical creation timestamp.
- Foreign keys bind journal operation and pending action. Checks enforce built-in scalar ranges where SQLite can express them. Update/delete triggers make receipts immutable.

## Public API and transaction

- New `rns_import_server/workbook_authority_refresh.py` exposes only:
  - `refresh_published_authority(storage, operation_id) -> AuthorityRefreshResult`;
  - `verify_authority_refresh_receipt(storage, operation_id) -> AuthorityRefreshReceipt`.
- Public result is payload-free: operation ID, typed `refreshed|replayed|published_pending_finalization|manual_repair` status, stable error code and optional prior/successor generation. Receipt projection contains only typed receipt metadata/digests, never target path, template/ownership payload or workbook contents.
- First execution derives all state from one immediate transaction: published journal, matching pending action, verified finalization snapshot, current WA1 authority, exact registry generation and a descriptor-bound read-only target. Caller supplies only `operation_id`.
- Require exact `operation_id == consumer_id == action_id`, `operation_kind=new_row`, `manifest_version=group-row-manifest-v3`, mutation mode `blank_fill|middle_insert`, canonical target and exact construction/contract/target/sheet/template identities. Journal `pre_hash` equals current authority source hash; descriptor-bound target SHA equals journal `post_hash`; snapshot digest/action/hash and target row are exact.
- The predecessor must be a valid unrefreshed WA1 authority with exact row-3 A:X template evidence and exhaustive ownership. Canonical authority state includes every stable stored field needed to reproduce the row, including identities, target, evidence/counts/digests, max row, source hash, registry generation and preserved creation timestamp.
- `blank_fill` preserves template/max-row/all ownership except target becomes explicitly owned. `middle_insert` shifts ownership rows `>= target`, inserts owned target, increments max row and shifts template-evidence rows `>= target`; values, A:X column order and all identities remain exact. Valid target row is bounded by the mode and snapshot.
- In the same transaction: compute canonical predecessor/successor states and domain-separated digests; increment generation exactly once; replace the authority with the exact successor; insert the immutable receipt. Any write failure rolls both back and returns published pending.
- Replay validates receipt schema/digests/envelope, reconstructs the successor from the stored predecessor plus receipt mode/row, verifies current authority equals that successor and target still equals post-hash, then returns `replayed` with zero database writes or generation/timestamp changes.
- Missing/corrupt/contradictory durable evidence, an already-advanced authority without its exact receipt, forged predecessor/successor, target hash mismatch or concurrent conflicting successor enters a typed manual-repair result without replacing the first durable receipt/successor. A transient SQLite or unreadable/unstable target remains published pending. No native call or workbook write exists in this module.

## Essential compact tests

- Explicit v6→v7 empty migration preserves legacy rows and creates immutable empty receipts; deterministic seed is v7 with zero actions/authorities/receipts.
- Blank-fill boundaries: row 2 and max row. Middle-insert boundaries: row 2 and append boundary. Assert exact ownership/template mapping, max row, identities, values and target bytes.
- Exact replay is zero-write; concurrent exact refresh yields one generation/successor/receipt; concurrent contradiction preserves the first and returns repair.
- Compact parameterized missing/corrupt journal, action, snapshot, authority and receipt cases; forged predecessor/successor and impossible mapping fail closed.
- Canonical path/symlink/non-regular/descriptor-race/unreadable/hash mismatch cases prove pending-versus-repair semantics and source immutability.
- Injected SQLite failure proves authority, receipt and generation rollback.
- Regression: a canonically re-digested row-4 pending WA1 authority is still rejected by the unchanged `RegistryWorkbookProjectionAuthority`; forbidden blob hashes remain exact.

## Gate

- One P4 implementation attempt, at most one localized remediation, then independent P6. Reject after that blocks WA2a. No integration before P6 acceptance.
