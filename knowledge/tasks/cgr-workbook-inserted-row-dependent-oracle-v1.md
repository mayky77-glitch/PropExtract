---
type: task
status: awaiting_review
work_id: cgr-workbook-inserted-row-dependent-oracle-v1
tags: [task/implementation, feature/construction-routing, status/in_progress]
last_verified: 2026-08-21
updated: 2026-08-21
---

# Inserted-row and dependent-formula oracle — frozen Gate

Exact accepted dependency/base before this card is `56f54409110a193d2bec3f53b41316083c031086`. It combines accepted structure publication guards and Wave3 request services. Source XLSX/PDF are immutable.

## Scope

- modify `rns_import_server/workbook_mutation_manifest.py`
- modify `rns_import_server/group_row_insertion.py`
- modify `tests/test_workbook_mutation_manifest.py`
- modify `tests/test_group_row_insertion.py`
- this card

Do not modify native PowerShell/lease, OPC readers/oracles, registry/storage, server/UI, source workbooks or fallback policy.

## Contract

Preserve current `validate_insertion`, then add two read-only validators before X14/FilterDatabase/structure and before fsync/backup/replace.

1. Inserted row:
   - exact `format_source_row = insertion_row - 1`;
   - candidate row height and complete A:AQ style semantics equal format-source row;
   - candidate Y/Z formulas equal Excel-Translator results from source Y/Z;
   - only request-owned field columns may contain values, each exactly equals trusted `request.fields`;
   - no unexpected formula/value from the predecessor may be copied;
   - W display value comes from trusted field 23, W hyperlink exactly equals requested hyperlink, and no other inserted-row hyperlink is admitted.

2. Dependent formulas outside `Реестр РНС`:
   - preserve formula cell set/order;
   - known whole-column references to exact quoted sheet token stay byte-identical;
   - known bounded ranges whose last endpoint is row 1001 expand only to 1002 for insertion rows 6/10/104;
   - any other change or unsupported changed reference fails closed; no formula evaluator, regex rewrite, OpenPyXL save or fallback.

Errors are typed/stable and wrapped as `GroupRowInsertionError` at stage `validate` with original cause. Failure leaves source hash unchanged, no output/backup and manual-repair journal state.

Real immutable evidence, SHA-256 `2a1786d5836e4c3144107704f281bc9513fcd8de97937499268dc806c1106dd1`:

- source rows 5/9/103 feed inserts 6/10/104 and have distinct heights/styles plus W links;
- Y/Z formulas exist at all six rows;
- Dashboard has 615 registry formulas: 108 bounded row-4..1001 references and 550 whole-column display formulas; bounded last endpoints become 1002, whole-column formulas remain exact;
- SHA must remain unchanged.

## Acceptance

Keep tests compact: one parametrized 6/10/104 inserted-row success, exact value/formula/style/height/hyperlink negatives, one dashboard bounded/whole-column success plus one changed-token failure, and one publication-order/no-side-effect regression. Run direct manifest/group tests, relevant structural/X14/filter focused tests, full pytest once, compile/diff/scope/ancestry/identity/clean, then independent P6.

This Gate compares persisted semantics only. It does not perform insertion, calculate formulas, save with OpenPyXL/LibreOffice, or qualify charts/pivots/queries/native Excel/UI.

## Implementation evidence

- Added read-only `validate_inserted_row` and `validate_dependent_registry_references`; both fail through a stable `MutationManifestError`, wrapped by publication as `GroupRowInsertionError(stage="validate")` before X14/FilterDatabase/structure, fsync, backup or replace.
- Direct gate tests cover all real insertion rows 6/10/104, exact Y:Z translation/style/height/request field/W-link semantics, Dashboard bounded `1001→1002` plus unchanged whole-column references, and a changed-token rejection.
- 2026-08-21: focused 62 passed; compile/diff green. Full suite result is recorded with the work handoff: 1,540 passed and exactly 10 sandbox loopback-bind failures; no product failure. Immutable source SHA remained `2a1786d5836e4c3144107704f281bc9513fcd8de97937499268dc806c1106dd1`.
