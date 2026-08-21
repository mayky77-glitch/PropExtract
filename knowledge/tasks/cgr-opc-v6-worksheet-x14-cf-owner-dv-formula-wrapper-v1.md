---
type: task
status: implementation-complete
work_id: cgr-opc-v6-worksheet-x14-cf-owner-dv-formula-wrapper-v1
tags: [task/implementation, feature/x14-owner, status/frozen]
last_verified: 2026-08-21
updated: 2026-08-21
---

# X14 CF owner: DV formula-wrapper carve — frozen Gate card

Base and accepted dependency are exact `ec9363b18f6ef8da6594f96fcb61a36615154e49`. Branch is `codex/cgr-opc-x14-cf-owner-dv-formula-wrapper-v1`; role P4 developer; merge exact `--no-ff` only after independent P6.

## Exclusive scope

- `rns_import_server/opc_worksheet_x14_cf_owner_topology.py`
- `tests/test_opc_worksheet_x14_cf_owner_dv_formula_wrappers.py`
- this card

All relationship, package graph, X2a/X2b test/fixture/card, native CF/DV, mutation, publication and UI files are frozen.

## Contract

Public API and errors do not change. Extend only the X1 DFS ownership classifier with exact QName wrappers `x14:formula1` and `x14:formula2`. Direct `xm:f` is unowned by CF only in this exact immediate chain:

`worksheet / direct extLst / direct ext[@uri=DV_URI and no extra attrs] / direct x14:dataValidations / direct x14:dataValidation / direct x14:formula1|formula2 / direct xm:f`.

The wrapper state is edge-local, never inherited through deeper descendants. Do not skip a subtree. Preserve the prior direct DV `xm:f/xm:sqref` carve. Do not permit wrapper `xm:sqref`. Wrong URI/case/namespace/depth, extra ext attribute, foreign/empty wrapper or an intervening element must keep exact `invalid-x14-cf-parent`, field `tag`, detail `{XM}f` (or `{XM}sqref`). Do not validate DV attributes, content, formula meaning or cardinality.

X1 workbook-wide tier/document order, X2a/X2b projection, atomicity and one worksheet parse remain unchanged. CF owners before/after DV keep identical paths/order/results.

## Evidence and acceptance

Synthetic exact matrix covers formula1 and formula2 separately and together, direct sqref, adjacent valid CF, every wrong URI/case/namespace/depth/attribute/foreign/empty/intervening-node case, wrapper sqref rejection, earlier/later CF fault precedence, tier priority and second-sheet atomic failure. Existing owner/rule/sqref suites must remain byte-frozen and pass.

Real read-only target `Автоматизация РнС и ГРО/Реестр РНС Иркутск.xlsx`, SHA-256 `2a1786d5836e4c3144107704f281bc9513fcd8de97937499268dc806c1106dd1`, has one X14 DV container with seven dataValidation records, each containing formula1/f, formula2/f and direct sqref. After the Gate the combined relationship+X1+X2b candidate must either project exactly 1,558 CF rules/ranges with unchanged SHA or stop on the next exact typed blocker; never skip it.

Run direct wrapper tests; existing X1/X2a/X2b focused suites; full pytest; compile the production module; `git diff --check`. Verify exact three-path scope, ancestry, frozen blobs, human identity and clean tree. No fallback, DV semantic claim, mutation or native Excel claim.

## P4 evidence — 2026-08-21

- Added only the edge-local exact `x14:formula1|formula2 -> xm:f` carve in the X1 DFS. Direct X14 DV `xm:f/xm:sqref` behavior remains unchanged; wrapper `xm:sqref` remains an exact typed parent fault.
- New direct matrix: `22 passed` (`tests/test_opc_worksheet_x14_cf_owner_dv_formula_wrappers.py`). Existing X1 and X2a focused suites: `231 passed`.
- Real read-only corpus SHA is checked before and after topology read; it accepts its seven DV formula-wrapper records without mutation.
- Full suite: `1424 passed`, exactly 10 expected managed-sandbox `socket.bind` `PermissionError` infrastructure failures, and one existing OpenPyXL extension warning; no product-test failure observed.
- `python3 -m py_compile rns_import_server/opc_worksheet_x14_cf_owner_topology.py` and `git diff --check` pass. X2b sqref suite is not present at this exact base; its combined real-corpus qualification remains for the integration gate.
