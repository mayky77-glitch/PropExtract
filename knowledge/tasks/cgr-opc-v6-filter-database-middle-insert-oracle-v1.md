---
type: task
status: frozen
work_id: cgr-opc-v6-filter-database-middle-insert-oracle-v1
tags: [task/implementation, feature/filter-database-insertion, status/frozen]
last_verified: 2026-08-21
updated: 2026-08-21
---

# FilterDatabase middle-insert oracle — frozen Gate card

Accepted dependency is exact `20676a7c6ea0bfa706e8e75799e1850b8c57b255`. Branch `codex/cgr-opc-filter-database-middle-insert-oracle-v1`; P4 developer; independent P6 before integration.

## Scope

- add `rns_import_server/opc_workbook_filter_database_insertion_oracle.py`
- add `tests/test_opc_workbook_filter_database_insertion_oracle.py`
- modify `rns_import_server/group_row_insertion.py`
- modify `tests/test_group_row_insertion.py`
- this card

No XLSX mutation logic, PowerShell, UI, database, registry, X14, generic parser, existing defined-name reader, fixture factory, README, PDF or source XLSX changes.

## Contract

Add read-only `validate_filter_database_middle_insert(control, candidate, *, sheet_name, insertion_row)` with one immutable evidence record and one typed four-field error. Reuse the accepted workbook-defined-name reader; do not parse raw OOXML or save through OpenPyXL/LibreOffice.

Require exactly one `_xlnm._FilterDatabase` owner for the target worksheet before and after. The insertion row must be strictly below the first row and no later than the last row of the control range. Preserve worksheet identity, columns, first row, name order, scope, hidden flag and every unrelated opaque defined-name expression. Candidate last row must be control last row plus exactly one. Compare the target range semantically, not by raw Excel spelling. Missing, duplicate, ambiguous, malformed, unchanged, over-expanded or otherwise mismatched candidates fail closed with a stable typed error; no skip or empty-success fallback.

Wire this validator only for `middle_insert`, after accepted generic-manifest and X14 validation and before fsync/backup/replace. Map its typed error to `GroupRowInsertionError` at stage `validate`, preserve the causal exception, record journal `manual_repair`, and create neither output nor backup. `blank_fill` remains unchanged.

## Acceptance

Keep tests bounded to six behaviors:

1. rows 6/10/104 accept semantic `A3:AQ605 -> A3:AQ606`;
2. unchanged, over-expanded or out-of-range candidates fail typed;
3. changed columns or worksheet owner fail typed;
4. changed unrelated defined name/order/scope/hidden/expression fails typed;
5. missing or duplicate target owner fails with exact four-field tuple;
6. publication failure preserves source hash, produces no output/backup, and journals `manual_repair` after X14 validation.

Run direct oracle tests, focused defined-name/publication tests, one full pytest run, compile touched modules, `git diff --check`, exact scope/ancestry/identity/clean. Qualify the real source read-only: target `Реестр РНС`, control `_FilterDatabase` `A3:AQ605`, insertion rows 6/10/104, unchanged SHA `2a1786d5836e4c3144107704f281bc9513fcd8de97937499268dc806c1106dd1`. Native Excel insertion and UI E2E remain later Gates.
