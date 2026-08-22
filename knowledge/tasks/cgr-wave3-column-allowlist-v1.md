---
card_id: cgr-wave3-column-allowlist-v1
status: frozen
version: 2
supersedes: null
work_id: cgr-wave3-column-allowlist-v1
task_id: column-allowlist
purpose: "Enforce the exact writable-column allowlist at group insertion and workbook mutation manifest boundaries before any side effect."
role: developer
card_path: knowledge/tasks/cgr-wave3-column-allowlist-v1.md
dependency_shas:
  - a2fff925f05def1e7ba55ce0ec50f6c55dc13531
branch: codex/cgr-wave3-column-allowlist-v1
write_scope:
  - knowledge/tasks/cgr-wave3-column-allowlist-v1.md
  - rns_import_server/group_row_insertion.py
  - rns_import_server/workbook_mutation_manifest.py
  - tests/test_group_row_insertion.py
  - tests/test_workbook_mutation_manifest.py
forbidden_paths:
  - README.md
  - rns_import_server/new_row_payload.py
  - rns_import_server/job_report.py
  - rns_import_server/server.py
  - rns_import_server/app.py
  - rns_import_server/static
  - rns_import_server/registry_storage.py
  - rns_import_server/new_row.py
  - rns_import_server/new_row_action_store.py
  - rns_import_server/workbook_operation_journal.py
  - rns_import_server/workbook_authority.py
  - rns_import_server/workbook_authority_refresh.py
  - rns_import_server/workbook_projection.py
  - rns_import_server/workbook_finalization.py
  - rns_import_server/workbook_groups.py
  - rns_import_server/excel_native.py
  - rns_import_server/operation_log.py
  - rns_import_server/data
contract_versions:
  input: accepted-mutation-boundaries-a2fff925
  output: exact-column-allowlist-v1
acceptance_commands:
  - PYTHONPATH=. python3 -m pytest -q tests/test_group_row_insertion.py tests/test_workbook_mutation_manifest.py
  - python3 -m compileall -q rns_import_server/group_row_insertion.py rns_import_server/workbook_mutation_manifest.py tests/test_group_row_insertion.py tests/test_workbook_mutation_manifest.py
  - git diff --check
knowledge_paths:
  - knowledge/INDEX.md
  - knowledge/tasks/cgr-wave3-column-allowlist-v1.md
  - knowledge/components/workbook-publication.md
---

# Exact mutation column allowlist

## Frozen boundary

- Start only from accepted `a2fff925f05def1e7ba55ce0ec50f6c55dc13531`; rejected payload `30a7075`, lifecycle `f99b3d4`, WA2/WA2b and log tips are forbidden ancestry/input.
- Change exactly the two mutation-boundary modules and their existing focused tests. Do not create/import the rejected payload or report implementation.
- No server/app, DB/schema/seed, lifecycle, authority/refresh/finalizer, native/PowerShell, UI, logging or public report changes.

## Contract

- Both group-row insertion evidence and workbook mutation manifest accept column keys only when `type(key) is int` and the value is in `{1..24, 27}`.
- Reject `bool`, columns `25` and `26`, every value above `27`, zero/negative integers, and every non-integer key. Do not coerce strings, floats, enums or integer-like objects.
- Validation must complete before journal creation/transition, operation-directory creation, native invocation, fsync, backup or replace. Failure is typed and produces no side effect.
- Existing accepted formulas, hyperlinks and all value semantics inside allowed columns remain unchanged. Do not add payload-wide JSON/formula/privacy policy in this Gate.
- Canonical manifest/evidence replay for already-valid allowed columns remains stable; no compatibility fallback may reopen forbidden columns.

## Essential compact tests

- Parametrized acceptance covers exact built-in integers `1`, `24` and `27` at both boundaries.
- Parametrized rejection covers `True`, `False`, `25`, `26`, `28`, larger, zero, negative, string/float/integer-like keys at both boundaries.
- Spies prove every rejected key fails before journal, directory, native, fsync, backup and replace.
- Existing formula/link behavior and canonical replay for allowed columns remain unchanged.

## Gate

- One P4 implementation attempt, at most one localized remediation, then independent P6. No integration before terminal acceptance; rejection blocks this Gate.
