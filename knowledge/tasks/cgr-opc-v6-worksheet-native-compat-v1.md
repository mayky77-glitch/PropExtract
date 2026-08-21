---
type: task
status: frozen
work_id: cgr-opc-v6-worksheet-native-compat-v1
tags: [task/implementation, feature/worksheet-reader, status/frozen]
last_verified: 2026-08-21
updated: 2026-08-21
---

# Worksheet native compatibility — frozen Gate card

Accepted dependency/base is exact `576272ae6b92c68874b0858cc796592c548a79b0`. Branch `codex/cgr-opc-worksheet-native-compat-v1`; P4 developer; independent P6 before integration.

## Scope

- `rns_import_server/opc_worksheet_cell_reader.py`
- `tests/test_opc_worksheet_cell_reader.py`
- `rns_import_server/opc_worksheet_structure_reader.py`
- `tests/test_opc_worksheet_structure_reader.py`
- this card

No insertion oracle, mutation, publication, PowerShell, UI, DB, X14/CF/DV semantics, source XLSX or unrelated tests.

## Contract

Keep public records and four-field error shapes. Accept explicit native numeric `t="n"`; valued cells retain type `n`, and numeric/default cells without `<v>`/`<f>` are immutable empty semantic cells with `value=None`. Accept exact native hyperlink `tooltip=""` while other blank anchor/id requirements remain fail-closed. Merge ranges remain bounded, unique, counted and source-ordered, but native serialization need not be row-major sorted. Duplicate/count/A1/namespace/content defects remain typed failures. Use the existing single read pipeline; no alternate parser or OpenPyXL/raw-XML/LibreOffice fallback.

## Acceptance

1. valued/empty `t=n`, default empty cell and `tooltip=""` exact immutable projections;
2. unordered unique merges accepted in source order; duplicate/count/A1 failures unchanged;
3. real source read-only passes cell+structure readers for all four sheets and proves target dimension `A1:AQ1001`, autoFilter `A3:AQ605`, 12 merges;
4. previous strict negative boundaries stay green; no new permissive generic blank handling;
5. source SHA remains `2a1786d5836e4c3144107704f281bc9513fcd8de97937499268dc806c1106dd1`.

Run direct cell/structure tests, compact topology/style/formula regression, full pytest once, compile touched modules, diff check, scope/ancestry/identity/clean. This Gate proves read compatibility only, not insertion safety or Excel publication.
