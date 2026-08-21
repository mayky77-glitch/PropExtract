---
type: task
status: frozen
work_id: cgr-x14-oracle-publication-gate-v1
tags: [task/implementation, feature/x14-insertion, status/frozen]
last_verified: 2026-08-21
updated: 2026-08-21
---

# X14 oracle publication gate — frozen card

Accepted dependency is exact `711e4cfc2a36a69390abd786b434b98f9a4816f1`. Branch `codex/cgr-x14-oracle-publication-gate-v1`; P4 developer; independent P6 before integration.

## Scope

- `rns_import_server/group_row_insertion.py`
- `tests/test_group_row_insertion.py`
- this card

No parser/oracle, PowerShell, UI, DB, journal schema, manifest or workbook mutation changes.

## Contract

For `middle_insert`, call accepted `validate_x14_cf_middle_insert(control, candidate, sheet_name=request.sheet, insertion_row=plan.target_row, format_source_row=plan.target_row-1)` after the generic manifest check and before fsync, backup, post-hash or replace. `blank_fill` must not call it.

Map `OPCWorksheetX14CfInsertionOracleError` to `GroupRowInsertionError` with the same stable code, stage `validate`, original cause retained. Existing journal/manual-repair handling then records the failure. Never skip, downgrade or publish after an oracle failure; source stays hash-identical and output absent.

## Acceptance

Keep two focused scenarios: exact invocation on successful middle insert; injected oracle failure proves same code/stage/cause, no output, unchanged source and no backup/published transition. Existing blank-fill and no-Excel tests must remain green. Run focused group-row/oracle tests, full pytest once, compile/diff, exact scope/identity/clean. Native Excel execution remains a later Windows/CrossOver Gate.

## Implementation evidence

- `middle_insert` runs X14 oracle after `validate_insertion` and before candidate `fsync`, backup, post-hash, or replace.
- Oracle error retains stable code and original cause in `GroupRowInsertionError` at `validate`; manual repair has no output, backup, or `published` transition.
- Focused: `PYTHONPATH=. pytest -q tests/test_group_row_insertion.py tests/test_opc_worksheet_x14_cf_insertion_oracle.py` — 18 passed.
- Full: 1489 passed; 10 loopback HTTP tests blocked only by sandbox `PermissionError: [Errno 1] Operation not permitted`; one existing OpenPyXL extension warning.
