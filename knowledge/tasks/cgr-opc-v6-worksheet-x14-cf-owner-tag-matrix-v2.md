---
type: task
status: planned
work_id: cgr-opc-v6-worksheet-x14-cf-owner-tag-matrix-v2
tags: [task/test, feature/x14-cf-owner-topology, status/planned]
last_verified: 2026-08-21
updated: 2026-08-21
---

# X14 CF owner tag/depth matrix v2 — frozen test-only Gate

Exact accepted base is `b3486ab8feb99137f2f8d24efa68771c6fadccc2`, containing accepted DV-precedence runtime `b6f8c0a81f0787f946cfc3126c35dd89892b1a0f` / no-ff `c30b76106232c198422657c180b46abeff472af4` and accepted I/O matrix A `b540012e0d75acc472928cca827ff0a97075813f`. Old tag matrix `ae599ac`, envelope/corpus/X1 blocked tips and their test bytes are evidence only; do not merge, cherry-pick, copy, or inherit them beyond the exact accepted base.

## Exclusive test scope and frozen blobs

Owned paths are only this card and new `tests/test_opc_worksheet_x14_cf_owner_topology_tag_matrix_v2.py`. Production, fixture, existing focused tests, and accepted A are frozen byte-for-byte:

- reader `008490111ac3f6b3212f4a775157e440c89d2a00`;
- fixture `83a56ee4f6f7a00a92cc577eb279377f50aba912`;
- focused runtime test `e1ebf495676c764397ec021a0b23c2bcae29e2b2`;
- accepted A test `38195a0e15b86d235d5bffc55e8292e58b6c953f`.

Any new runtime discrepancy stops this Gate without changing production or weakening an expected tuple. No fallback, skip, xfail, alternate code, observational-only assertion, empty success, partial projection, or semantic expansion is allowed.

## Complete exact matrix

Generate direct owner-specific trees, never a wrapper that masks the target. For all six unique owned locals — X14 `conditionalFormattings`, `conditionalFormatting`, `cfRule`, `dxf` and XM `f`, `sqref` — assert the legal parent where applicable and exact failure at every other worksheet/CF-owner depth: direct worksheet, arbitrary foreign wrapper, direct SML `extLst`, direct CF/DV/unknown-URI SML `ext`, direct X14 `conditionalFormattings`, direct X14 `conditionalFormatting`, and direct X14 `cfRule`. Include direct-under-legal-`conditionalFormattings` cases for the five previously masked locals. Every negative asserts the complete `(code, subject, field, detail)` tuple for the target tag, not a wrapper side effect.

For every six locals cover exact namespace, wrong-case namespace URI (`X14.upper()` or `XM.upper()`), one foreign namespace, and empty namespace; cover wrong local-name case separately without treating it as the owned tag. Freeze first document/tier fault precedence with an earlier and later defect around each representative owner.

Prove the exact known DV carve with realistic topology: adjacent legal CF extension plus legal DV extension succeeds and publishes only CF owners; legal DV-only workbook returns no owners; CF-owned sibling beside direct `x14:dataValidations` fails its own tag; CF-owned descendants before and after legal DV XM values fail in document order; wrong-case/unknown/blank/malformed URI never activates the carve. Native SML CF and native cell formula remain unowned.

Freeze nonwhite text and every direct-child tail for SML `extLst`, matching SML `ext`, X14 `conditionalFormattings`, X14 `conditionalFormatting` (including `cfRule` and `xm:sqref` tails), and X14 `cfRule` (including `xm:f` and `x14:dxf` tails). XML whitespace remains valid. Add a two-sheet atomicity case: valid first sheet plus invalid second sheet raises only the exact second-part tuple and returns no partial workbook result.

Add complete immutable exact projection for two worksheets with synthetic row-linked owner evidence at 6, 10 and 104: assert record field order, exact recursive `asdict`, worksheet descriptor equality, container order/paths/document order, tuple order, and `FrozenInstanceError` for every public record. Lower priority/formula/sqref/dxf values remain opaque and absent from topology.

## Acceptance

`python3 -m pytest -q tests/test_opc_worksheet_x14_cf_owner_topology_tag_matrix_v2.py`

`python3 -m pytest -q tests/test_opc_worksheet_x14_cf_owner_topology.py tests/test_opc_worksheet_x14_cf_owner_topology_io_matrix.py tests/test_opc_worksheet_x14_cf_owner_topology_tag_matrix_v2.py tests/test_opc_workbook_topology.py tests/test_opc_worksheet_cell_reader.py tests/test_opc_worksheet_structure_reader.py tests/test_opc_worksheet_native_cf_reader.py`

`python3 -m pytest -q`

`python3 -m compileall -q tests/test_opc_worksheet_x14_cf_owner_topology_tag_matrix_v2.py`

`git diff --check`

Verify the four frozen hashes, exact two-path scope, base ancestry, human identity, clean worktree, and exact remote tip. Independent P6 must adversarially inspect direct tree construction and anti-shallow coverage. This Gate makes no envelope/rule/formula/sqref/dxf interpretation, insertion/publication, UI, CrossOver, or native Excel claim.
