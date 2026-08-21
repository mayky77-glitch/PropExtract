---
card_id: cgr-wave3-workbook-authority-wa2
status: frozen
version: 2
supersedes: null
work_id: cgr-wave3-workbook-authority-wa2
task_id: workbook-authority-wa2
purpose: "Refresh durable workbook authority exactly once after verified publication and before downstream finalizers."
role: default
card_path: knowledge/tasks/cgr-wave3-workbook-authority-wa2.md
dependency_shas:
  - b161abd3b723af89aa1512892725f5072c76fe35
branch: codex/cgr-wave3-workbook-authority-wa2
write_scope:
  - knowledge/tasks/cgr-wave3-workbook-authority-wa2.md
  - rns_import_server/registry_storage.py
  - rns_import_server/workbook_authority.py
  - rns_import_server/workbook_authority_refresh.py
  - rns_import_server/workbook_finalization.py
  - rns_import_server/data/construction_registry.seed.sqlite3
  - rns_import_server/data/construction_registry.seed.manifest.json
  - tests/test_registry_storage.py
  - tests/test_workbook_authority.py
  - tests/test_workbook_authority_refresh.py
  - tests/test_workbook_finalization.py
forbidden_paths:
  - README.md
  - rns_import_server/server.py
  - rns_import_server/static
  - rns_import_server/app.py
  - rns_import_server/operation_log.py
  - rns_import_server/group_row_insertion.py
  - rns_import_server/excel_native.py
  - rns_import_server/workbook_projection.py
  - rns_import_server/workbook_operation_journal.py
  - rns_import_server/workbook_finalization_snapshot.py
contract_versions:
  input: durable-workbook-authority-v1
  output: durable-workbook-authority-refresh-v1
acceptance_commands:
  - PYTHONPATH=. python3 -m pytest -q tests/test_registry_storage.py tests/test_workbook_authority.py tests/test_workbook_authority_refresh.py tests/test_workbook_finalization.py
  - python3 scripts/build_construction_registry_seed.py --check
  - python3 scripts/validate_construction_registry_seed.py
  - python3 -m compileall -q rns_import_server/registry_storage.py rns_import_server/workbook_authority.py rns_import_server/workbook_authority_refresh.py rns_import_server/workbook_finalization.py tests/test_registry_storage.py tests/test_workbook_authority.py tests/test_workbook_authority_refresh.py tests/test_workbook_finalization.py
  - git diff --check
knowledge_paths:
  - knowledge/INDEX.md
  - knowledge/tasks/cgr-wave3-workbook-authority-wa2.md
  - knowledge/components/workbook-publication.md
  - knowledge/tasks/implement-construction-group-routing-20260820.md
---

# Workbook authority WA2

## Frozen contract

- Start only from accepted WA1 common `b161abd3b723af89aa1512892725f5072c76fe35`; preserve its enrollment, producer, projection, schema-v6 and typed-error contracts. Rejected/blocked operation-log ancestry is forbidden.
- Advance the registry with an empty migration and deterministic seed/manifest for one immutable authority-refresh receipt table. Migration/seed fabricate no authority, refresh receipt, enrollment, ownership or corpus claim.
- A refresh is derived only from one transactionally consistent read of the published journal operation, matching pending action, verified finalization snapshot, current durable authority and verified current target. No caller may supply identities, path, row evidence, pre/post hashes or mutation mode.
- Exact tuple requirements: `operation_id == consumer_id == action_id`; operation kind `new_row`; manifest version exactly `group-row-manifest-v3`; canonical target and all construction/contract/target/sheet/template identities match; operation `pre_hash` equals current authority `source_sha256`; target descriptor-bound SHA-256 equals operation `post_hash`; finalization snapshot is valid and supplies the exact target row.
- `blank_fill`: preserve `max_row`, template evidence and all ownership except the target row becomes explicitly owned. `middle_insert`: shift every ownership row at or after target row by one, insert the target row as owned, increment `max_row`, and shift every template-evidence row at or after the target row by one. Preserve exact A:X column order and scalar values. No inference from workbook contents.
- In one SQLite transaction, verify current authority, write its exact successor with `source_sha256=post_hash` and the updated evidence/generation, and insert one immutable canonical refresh receipt binding operation/action, mutation mode, target row, old/new authority digests, pre/post hashes and generation transition. Exact replay verifies everything and performs zero writes/generation changes. Conflict, missing/corrupt evidence, impossible mapping, receipt mismatch, target contradiction or already-advanced authority without the exact receipt enters typed manual repair. Transient SQLite/storage failure leaves the published operation pending and authority/receipt unchanged.
- `finalize_published_operation` must run/verify the refresh before binding, history, report, capability consumption or terminal `finalized` for `group-row-manifest-v3`. Binding must refuse v3 without a valid refresh receipt. Accepted legacy manifest versions keep their existing finalizer order and behavior.
- Crash-after-replace replay must refresh/finalize from durable authority without a native call or second insertion. WA2 itself never invokes workbook mutation/native Excel.

## Essential acceptance

- Empty prior-schema migration and deterministic seed contain zero authorities/receipts.
- Exact blank-fill and middle-insert ownership/template mappings, including boundary rows and unchanged identities.
- Exact replay is zero-write; concurrent exact refresh yields one update/receipt; concurrent contradiction preserves the first durable successor.
- Missing/corrupt journal, action, snapshot, authority, target hash, mapping or receipt fails closed with the required pending/manual-repair distinction.
- Injected SQLite failure rolls back authority plus receipt and returns published pending finalization.
- V3 binding/history/report/capability/finalized cannot advance without the valid refresh receipt; legacy accepted operations preserve existing behavior.
- Focused disposable workbook tests verify current target read-only and never enroll or commit a private workbook.

## Boundary

- No WA1 enrollment rewrite, WA3/bridge, server/API/UI, operation log, native Excel invocation, report-shape expansion, real enrollment or source workbook mutation.
- One P4 implementation worker. Independent P6 may authorize at most one localized remediation inside this frozen scope; otherwise WA2 blocks.
