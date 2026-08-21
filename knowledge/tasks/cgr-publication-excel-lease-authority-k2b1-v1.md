---
type: task
status: completed
work_id: cgr-publication-excel-lease-authority-k2b1-v1
tags: [task/implementation, feature/construction-routing, status/in_progress]
last_verified: 2026-08-21
updated: 2026-08-21
---

# Excel lease authority K2B1 — frozen Gate

Exact accepted dependency/base is K2A integration
`041e66758a432295d84c0d942bf267738a90c73c`. Blocked K2B v1 tips
`071ea7d`/`ae8d0e6` are not ancestry and must not be cherry-picked.

## Scope

- add `rns_import_server/excel_process_authority.py`
- modify `rns_import_server/workbook_operation_journal.py`
- modify `rns_import_server/registry_storage.py`
- modify deterministic generated registry seed SQLite and manifest
- add `tests/test_excel_process_authority.py`
- modify `tests/test_workbook_operation_journal.py`
- modify `tests/test_registry_storage.py`
- this card

Do not modify `excel_native.py`, PowerShell, group publication, workbook
mutation semantics, K2B2 handshake/cleanup, K3, services/server/UI or source
XLSX/PDF. No subprocess launch, workbook Open or native Excel claim.

## Contract

- Introduce an immutable full lease authority record: operation/owner/pair,
  adapter image/PID/strict UTC start, adapter type `com`, Excel image/PID/HWND/
  strict UTC process start/build.
- A small injected inspector returns a prelaunch Excel PID snapshot, exact
  process identity and HWND→PID. Snapshot/probe/decode failure is typed and
  fail-closed; it never becomes an empty snapshot.
- Validation requires adapter PID/image/start to match the launched process,
  Excel image exact `EXCEL.EXE`, HWND→reported PID, Excel PID absent prelaunch,
  and Excel start not earlier than adapter. Reject naïve/non-UTC/malformed
  timestamps without raw exceptions. No broad process kill API exists here.
- Journal `staged -> native` accepts the full lease only after matching
  operation/owner/pair to its row; it persists exactly the process fields
  atomically. Any missing/extra/mismatched/invalid field blocks.
- Registry schema v3 adds adapter identity fields. Deterministic seed/manifest
  are versioned coherently. v2→v3 migration quarantines every nonterminal
  native-mode row at `staged`, `native`, `validated` or `backup_verified` that
  lacks complete ownership as `manual_repair` with exact failure code;
  published/finalized history remains preserved. Migration backup remains exact.

## Acceptance

Keep tests compact: one success projection; one parametrized identity/timestamp/
snapshot failure matrix; one journal full/missing/extra/nonces matrix; one v2
phase migration matrix plus backup/hash/schema proof. Run direct authority/
journal/storage tests, deterministic seed check, full pytest once, compile/diff/
scope/ancestry/identity/clean, then independent P6.

K2B1 is a pure authority foundation. K2B2 later wires it to a live parent-child
permission/cancel channel and exact COM cleanup. Passing K2B1 alone never means
that Microsoft Excel publication was executed or accepted.

## Evidence

- Added immutable `ExcelProcessLease` plus injected fail-closed inspector:
  prelaunch snapshot, exact adapter/Excel identities, HWND ownership and UTC
  chronology are required before durability.
- `staged -> native` now accepts only that full record and atomically projects
  all seven durable process fields after operation/owner/pair matching.
- Schema v3 and deterministic seed are current. v2 native in-flight records
  without adapter PID/start are durable `manual_repair` with
  `legacy_excel_lease_ownership_missing`; published/finalized history remains.
- Focused: `38 passed`; deterministic build/check and seed validator passed.
  Full suite: `1585 passed`, 10 known sandbox loopback-bind denials; no product
  test failure. No Excel process was launched or claimed.
