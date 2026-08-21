---
type: task
status: in_progress
work_id: cgr-publication-authority-k1-v1
tags: [task/implementation, feature/construction-routing, status/in_progress]
last_verified: 2026-08-21
updated: 2026-08-21
---

# Publication authority K1 — frozen Gate

Exact accepted dependency/base is `897efa9ad6d8c65d5ef9aba95096c15a4a73c771`. Source XLSX/PDF and native Excel scripts are immutable in this Gate.

## Scope

- modify `rns_import_server/group_row_insertion.py`
- modify `rns_import_server/workbook_operation_journal.py`
- modify `tests/test_group_row_insertion.py`
- modify `tests/test_workbook_operation_journal.py`
- this card

Do not modify Excel/PowerShell lease or process ownership, blank-fill cell semantics, recovery/finalizers, registry/server/UI, source workbooks or fallback policy. K2 and K3 own those later.

## Authority contract

- `PublicationContext` carries integration-owned `operation_id`, `idempotency_key`, `consumer_id` and `operation_kind`; callers cannot cause a fresh random operation identity on retry.
- Identifiers are nonempty stable strings and `operation_id` is a canonical UUID. `publish_group_row` accepts only exact `operation_kind="new_row"`; `group_provision` requires its future separate publisher and must fail before files/native work.
- Operation directory is exact `<operation_directory>/<operation_id>`. Exact replay does not create another directory, owner/pair nonce or journal operation.
- First call creates owner/pair nonces once and writes immutable journal authority. Existing `operation_id` is loaded and compared; exact replay enters existing recovery classification and never performs a second native mutation. Any identity/intent conflict fails closed.

## Canonical evidence

- `intent_version="group-row-intent-v2"`; `intent_digest` is strict canonical JSON over operation kind, consumer ID, construction ID, canonical RNS, sorted trusted fields with JSON types preserved, and hyperlink.
- `manifest_version="group-row-manifest-v2"`; `manifest_digest` is separate strict canonical JSON over mutation mode, target/sheet/template identities, workbook identity/pre-hash/generation, target row and `format_source_row=target_row-1`.
- Neither digest may equal or alias the workbook pre-hash. Unknown/non-JSON values, nonfinite floats and noncanonical field keys fail before journal/file/native work; never stringify them as fallback.
- Existing journal immutable collision semantics remain fail-closed and generation is checked only after exact replay detection.
- Legacy/v1 or conflicting journal records return a stable recovery error and are never silently upgraded or replayed.

Stable public errors are typed `GroupRowInsertionError`: `publication_authority_required@authorize`, `publication_identity_invalid@authorize`, `publication_operation_kind_mismatch@preflight`, `publication_intent_value_invalid@authorize`, `publication_intent_conflict@recovery`, `legacy_publication_authority_invalid@recovery`.

## Acceptance

Keep tests compact: exact IDs/kind reach journal; intent/manifest digests are stable/distinct and change for field/link/row/pre-hash changes; NaN/non-JSON fail before files; exact replay performs no second native/filesystem mutation; conflicting replay and `group_provision` block with exact stage/code. Preserve existing journal restart/CAS privacy tests. Run direct group+journal tests, relevant publication validators, full pytest once, compile/diff/scope/ancestry/identity/clean, then independent P6.

This Gate does not claim native Excel ownership, blank-fill correctness, post-hash recovery, real finalization side effects, server/UI or full user-path success.

## P4 implementation evidence

- `PublicationContext` now requires integration-owned canonical operation UUID, idempotency key, consumer ID and exact `new_row` kind before publication work.
- V2 intent and manifest SHA-256 evidence are separately canonicalized; non-JSON values, NaN and invalid field keys stop at `authorize`.
- An exact existing operation is classified through recovery without a new journal record, operation directory, nonce pair or native mutation. Legacy/v1 and immutable conflicts fail closed.
- Focused group/journal/storage suite: `37 passed` (2026-08-21). Full suite: `1549 passed`; 10 unrelated HTTP tests are blocked by sandbox `PermissionError` on `bind(127.0.0.1, 0)`.
