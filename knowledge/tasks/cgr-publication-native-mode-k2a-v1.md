---
type: task
status: in_progress
work_id: cgr-publication-native-mode-k2a-v1
tags: [task/implementation, feature/construction-routing, status/in_progress]
last_verified: 2026-08-21
updated: 2026-08-21
---

# Native mutation mode K2A — frozen Gate

Exact accepted dependency/base is K1 integration `e61ad0541b9428594c0d563a2684622c6054a212`. Source XLSX/PDF are immutable.

## Scope

- modify `rns_import_server/excel_native.py`
- modify `scripts/windows_excel_insert.ps1`
- modify `rns_import_server/group_row_insertion.py`
- modify `rns_import_server/workbook_mutation_manifest.py`
- modify `tests/test_excel_native_contract.py`
- modify `tests/test_group_row_insertion.py`
- modify `tests/test_workbook_mutation_manifest.py`
- this card

Do not redesign Excel PID/HWND ownership, lease persistence/ACK/cleanup (K2B), journal recovery/finalizers (K3), registry/server/UI or source files.

## Contract

- `NativeInsertRequest` carries exact `mutation_mode` and emits it in request JSON.
- Only `middle_insert` and `blank_fill` are accepted before helper launch/Open. Any other value returns typed `native_mutation_mode_invalid@pre_open`; no files/native process.
- PowerShell validates mode before creating Excel:
  - `middle_insert`: exactly one `Rows.Item(k).Insert(-4121, 0)` and then trusted writes;
  - `blank_fill`: zero row insertion and only trusted field/hyperlink writes at the existing row.
- Existing control open/recalc/save and candidate open/recalc/save behavior is unchanged. No OpenPyXL/LibreOffice/custom-OOXML publication fallback.

Add read-only `validate_blank_fill` to the mutation manifest and call it for `blank_fill` after control validation and before candidate fsync/backup/replace:

- sheet identity and max row unchanged;
- all values/formulas/hyperlinks outside target row are exact;
- candidate target row may change only request-owned field columns, each to its exact trusted value;
- Y/Z and every non-request formula remain exact;
- W display value follows trusted field 23 and W hyperlink is exact request; no other target-row hyperlink is admitted;
- missing/unexpected value/formula/link or row-count change blocks with typed manifest error wrapped as `GroupRowInsertionError@validate`, no output/backup/replace.

`middle_insert` retains the accepted generic→inserted-row/dependent→X14→FilterDatabase→structure order. K2A adds no native Excel ownership claim.

## Acceptance

Keep tests compact: request mode serialization and invalid-mode pre-open; static PowerShell proof of exclusive mode branches and one insert call; blank-fill success proves unchanged row count/coordinates/formulas and exact trusted values/W link; one parametrized outside/target/formula/link/count failure matrix; publication failure stops before final fsync/backup/replace. Run direct native/manifest/group tests, relevant publication validators, full pytest once, compile/diff/scope/ancestry/identity/clean, then independent P6.

Native Excel 365 remains required later to qualify actual COM behavior. CrossOver/LibreOffice cannot convert this Gate into a native Excel success claim.

## Implementation evidence

- Request JSON carries `mutation_mode`; Python rejects a non-string or unknown
  mode as `native_mutation_mode_invalid@pre_open`, before request-file write or
  helper launch.
- PowerShell validates mode before `New-Object -ComObject Excel.Application`.
  `middle_insert` contains the sole row `Insert`; `blank_fill` performs no row
  insertion.
- `validate_blank_fill` compares read-only semantic manifests, including XLSX
  hyperlink relationships. It permits only exact request field values and W
  link, and blocks target or outside value/formula/link/count drift at
  `GroupRowInsertionError@validate` before final fsync, backup, or replace.
