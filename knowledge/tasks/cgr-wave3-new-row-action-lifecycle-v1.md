---
card_id: cgr-wave3-new-row-action-lifecycle-v1
status: frozen
version: 2
supersedes: null
work_id: cgr-wave3-new-row-action-lifecycle-v1
task_id: new-row-action-lifecycle
purpose: "Close EXISTING_ROW as a durable non-publication outcome and distinguish live from abandoned planned operations by authoritative pre-hash evidence."
role: developer
card_path: knowledge/tasks/cgr-wave3-new-row-action-lifecycle-v1.md
dependency_shas:
  - a2fff925f05def1e7ba55ce0ec50f6c55dc13531
branch: codex/cgr-wave3-new-row-action-lifecycle-v1
write_scope:
  - knowledge/tasks/cgr-wave3-new-row-action-lifecycle-v1.md
  - rns_import_server/new_row.py
  - rns_import_server/new_row_action_store.py
  - rns_import_server/workbook_operation_journal.py
  - rns_import_server/registry_storage.py
  - rns_import_server/data/construction_registry.seed.sqlite3
  - rns_import_server/data/construction_registry.seed.manifest.json
  - tests/test_new_row_action.py
  - tests/test_new_row_action_store.py
  - tests/test_new_row_concurrency.py
  - tests/test_workbook_operation_journal.py
  - tests/test_registry_storage.py
forbidden_paths:
  - README.md
  - rns_import_server/workbook_authority.py
  - rns_import_server/workbook_authority_refresh.py
  - rns_import_server/workbook_projection.py
  - rns_import_server/workbook_finalization.py
  - rns_import_server/workbook_finalization_snapshot.py
  - rns_import_server/group_row_insertion.py
  - rns_import_server/workbook_groups.py
  - rns_import_server/server.py
  - rns_import_server/static
  - rns_import_server/app.py
  - rns_import_server/operation_log.py
  - rns_import_server/excel_native.py
  - rns_import_server/powershell
contract_versions:
  input: new-row-action-lifecycle-architecture-v1
  output: durable-new-row-action-lifecycle-v1
acceptance_commands:
  - PYTHONPATH=. python3 -m pytest -q tests/test_new_row_action.py tests/test_new_row_action_store.py tests/test_new_row_concurrency.py tests/test_workbook_operation_journal.py tests/test_registry_storage.py
  - python3 scripts/build_construction_registry_seed.py --check
  - PYTHONPATH=. python3 scripts/validate_construction_registry_seed.py
  - python3 -m compileall -q rns_import_server/new_row.py rns_import_server/new_row_action_store.py rns_import_server/workbook_operation_journal.py rns_import_server/registry_storage.py tests/test_new_row_action.py tests/test_new_row_action_store.py tests/test_new_row_concurrency.py tests/test_workbook_operation_journal.py tests/test_registry_storage.py
  - git diff --check
knowledge_paths:
  - knowledge/INDEX.md
  - knowledge/tasks/cgr-wave3-new-row-action-lifecycle-v1.md
  - knowledge/components/workbook-publication.md
  - knowledge/tasks/implement-construction-group-routing-20260820.md
  - knowledge/DECISIONS.md
---

# NewRow action lifecycle

## Frozen boundary

- Start only from accepted common `a2fff925f05def1e7ba55ce0ec50f6c55dc13531`. Rejected WA2/WA2b tips are evidence only and forbidden ancestry/source input.
- Preserve accepted authority, refresh, projection, finalizer, group, native, server/UI and logging implementations byte-for-byte. No bridge and no real workbook enrollment.
- Own only the four named lifecycle/storage modules, deterministic seed artifacts, the five focused existing test modules, and this card.

## Durable schema v8

- Add nullable `predecessor_action_id` to `new_row_pending_actions`, a self foreign key, and a partial unique index for non-null predecessors. Do not rebuild or infer pending actions.
- Add immutable `new_row_action_lifecycle_receipts`: `action_id` primary/foreign key, exact receipt version 1, terminal state `resolved_existing|existing_review|abandoned`, nullable operation ID, nullable observed row, nullable expected pre-hash, required observed workbook hash, required domain-separated digest and canonical timestamp.
- Exact checks: existing outcomes have no operation ID or expected hash and require `observed_row >= 2`; abandoned has `operation_id == action_id`, no observed row, and two valid unequal hashes. Reject update/delete with immutable triggers.
- v7 to v8 migration is additive and empty: no backfill, inferred lifecycle, fabricated authority or receipt. Regenerated deterministic seed remains empty for operational tables.

## Lifecycle API and semantics

- Add public outcome codes `resolved_existing` and `existing_review`. Exact existing requires observed C exactly equal to the requested object code, observed D equal by accepted `field_comparison_equal`, and the resolver's already-proven canonical F/RNS. Make no claim about A/B/E. Same-RNS rows not meeting exact C/D become `existing_review`.
- `close_existing(action_id, *, job_authorization, terminal_state, observed_row, observed_workbook_hash)` verifies the action capability and `publishing` reservation, requires no journal, and atomically inserts the immutable receipt. Exact replay is zero-write; contradiction is typed and preserves the first receipt.
- Existing outcomes terminate without publisher, consumed/published state, operation journal/directory, snapshot, native mutation, history, binding, report, capability consumption or finalization. Effective public state comes from the joined lifecycle receipt; raw reservation state may remain `publishing` for compatibility.
- `classify_planned_pre_hash(action_id, *, job_authorization, observed_pre_hash)` returns typed `live|abandoned`, deriving the expected hash from durable workbook authority and verifying the exact action/authority/journal tuple under the accepted exclusive publication lock. Equality is live and zero-write. Inequality plus a pristine planned journal atomically records an abandoned receipt and journal phase `abandoned` with `failure_code=planned_pre_hash_abandoned`.
- Never infer abandonment from time or age. Staged/later/corrupt/contradictory journal state fails typed with no abandonment. `incomplete()` excludes abandoned while manual-repair evidence stays visible.
- A successor may register with optional `predecessor_action_id` only when that predecessor is durably abandoned. Require a new action ID and a fresh action-bound capability; the supplied raw capability must not authenticate the predecessor. Allow one successor per predecessor and reject reuse/conflicts.
- Typed boundaries include `new_row_action_outcome_invalid`, `new_row_action_outcome_conflict`, `new_row_action_outcome_terminal`, `new_row_action_pre_hash_observation_invalid`, `new_row_action_abandonment_invalid`, and `new_row_action_capability_reused`; preserve accepted storage-fault classification.

## Essential compact tests

- Exact existing closes `resolved_existing`; same RNS with blank, legacy or different C closes `existing_review`; neither invokes publisher/journal/history/finalizer/directory.
- Exact replay is zero-write; concurrent identical closure converges once; conflicting closure preserves the first receipt.
- v7 to v8 migration and deterministic seed create no authority/action/lifecycle rows.
- Equal authoritative pre-hash is live/zero-write. A differing hash with pristine planned state atomically becomes abandoned; injected storage failure rolls back both receipt and journal.
- Stage versus abandon serializes to one winner; staged/later/corrupt states reject abandonment.
- Reusing the old operation ID or raw capability is rejected. A new action ID, fresh capability and predecessor link succeeds once.
- Accepted finalization/history behavior remains unchanged; spies prove no native call or second insertion.

## Gate

- One P4 implementation attempt, at most one localized remediation, then one independent P6. Reject after that blocks this Gate. No integration before terminal P6 acceptance.
