---
type: task
status: frozen
work_id: cgr-opc-v6-x14-cf-middle-insert-oracle-v1
tags: [task/implementation, feature/x14-insertion, status/frozen]
last_verified: 2026-08-21
updated: 2026-08-21
---

# X14 CF middle-insert oracle — frozen Gate card

Accepted dependency is exact `2d28d2ee2b7e9c317474546afc9f77c6b0c078c0`. Branch `codex/cgr-opc-x14-cf-middle-insert-oracle-v1`; P4 developer; independent P6 before integration.

## Scope

- `rns_import_server/opc_worksheet_x14_cf_owner_topology.py`
- `rns_import_server/opc_worksheet_x14_cf_insertion_oracle.py`
- `tests/test_opc_worksheet_x14_cf_insertion_oracle.py`
- this card

No workbook mutation, PowerShell, UI, DB, publication, existing X2b API/test or generic parser framework changes.

## Contract

Add read-only `validate_x14_cf_middle_insert(control, candidate, *, sheet_name, insertion_row, format_source_row)`. Require `format_source_row == insertion_row - 1`. Reuse accepted X2b projection and compare rules by unique GUID, never repeated priority. Preserve GUID order, type, priority, stop flag, translated formula, semantic inline-DXF fingerprint and normalized sqref geometry.

Expected geometry maps old rows `< k` unchanged, rows `>= k` to `+1`, expands crossing ranges, and gives inserted row `k` exactly the column coverage of source row `k-1`. Formula comparison uses the existing formula translator from old to new first-range anchor. Any ambiguity, unsupported formula, malformed candidate, rule/DXF/formula/range mismatch or X2b error must raise one typed four-field error and block publication. No skip, raw-copy, LibreOffice/OpenPyXL save or empty-success fallback.

## Acceptance

Keep evidence bounded to five behaviors:

1. parametrized rows 6/10/104 geometry and formula shift, including source coverage 8/30/18;
2. GUID/order/type/priority mismatch fails typed;
3. semantic DXF change fails while prefix/attribute-order-only rewrite passes;
4. unsupported formula and malformed candidate fail typed with input hashes unchanged;
5. real read-only source proves 1,558 rules, 2,473 ranges, 94 formula texts, seven DXF fingerprints, target coverage 8/8/13, source coverage 8/30/18, and unchanged SHA `2a1786d5836e4c3144107704f281bc9513fcd8de97937499268dc806c1106dd1`.

Run direct oracle tests, compact X2b/rule regression, full pytest once, compile both production modules, diff check, exact scope/ancestry/identity/clean. Native Excel mutation and full UI E2E are later Gates.
