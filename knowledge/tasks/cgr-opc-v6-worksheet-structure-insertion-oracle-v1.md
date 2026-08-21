---
type: task
status: in_progress
work_id: cgr-opc-v6-worksheet-structure-insertion-oracle-v1
tags: [task/implementation, feature/construction-routing, status/in_progress]
last_verified: 2026-08-21
updated: 2026-08-21
---

# Worksheet structure middle-insert oracle — frozen Gate

Accepted dependency is exact `c28fad7fcecf902051996fa9fc29035b90ed1df3`. It includes the accepted worksheet compatibility reader. Rejected structural-reader lines and unrelated Wave3 request branches are forbidden ancestry.

## Scope

- add `rns_import_server/opc_worksheet_structure_insertion_oracle.py`
- add `tests/test_opc_worksheet_structure_insertion_oracle.py`
- modify `rns_import_server/group_row_insertion.py`
- modify `tests/test_group_row_insertion.py`
- this card

Do not modify readers, X14/FilterDatabase oracles, native PowerShell, manifests, registry, server/UI, source XLSX/PDF or fallback policy.

## Contract

Add a read-only, typed, immutable structural validator for paired control/candidate XLSX files. It must reuse accepted topology/worksheet-structure semantics, select the exact worksheet by name, and never save, normalize or rewrite either package.

For a middle insertion at row `k`:

- dimension and native `autoFilter` ranges map geometrically: rows below `k` stay; rows at/after `k` shift by one; a range crossing `k` expands by one;
- every merge range follows the same mapping, preserving document order and exact count;
- unrelated sheets and worksheet identity/order stay exact;
- missing/extra/changed structures, malformed packages, ambiguous sheet names, invalid row bounds and dependency reader errors fail as exact `OPCWorksheetStructureInsertionOracleError(code, subject, field, detail)`; no empty-success/fallback.

Wire it only for `middle_insert` after generic, X14 and `_FilterDatabase` validators, but before fsync, backup, post-hash and replace. Preserve the original typed cause at publication stage `validate`; failure must leave source hash unchanged and create no output/backup.

Real read-only expectations for `Реестр РНС Иркутск.xlsx`, source SHA-256 `2a1786d5836e4c3144107704f281bc9513fcd8de97937499268dc806c1106dd1`:

- `Реестр РНС`: dimension `A1:AQ1001`, autoFilter `A3:AQ605`, 12 merges;
- candidate expectation at rows 6/10/104: dimension `A1:AQ1002`, autoFilter `A3:AQ606`;
- at row 6 exactly five row-6 merges shift to row 7 and seven remain unchanged; at rows 10/104 all 12 remain unchanged;
- source SHA stays byte-identical.

## Acceptance

Keep tests compact: one parametrized 6/10/104 mapping proof, mismatch/error precedence, immutable/PathLike/source-hash proof, and one publication-order/no-side-effect regression. Run direct oracle tests, structure/topology/cell/group-row focused tests, full pytest once, compile changed modules, diff check, exact scope/ancestry/identity/clean, then independent P6.

No native Excel mutation, LibreOffice publication, UI or end-to-end success claim in this Gate.
