---
card_id: cgr-publication-excel-handshake-cleanup-k2b2b-v1
status: frozen
version: 1
supersedes: cgr-publication-excel-handshake-k2b2-v1
work_id: cgr-publication-excel-handshake-cleanup-k2b2b-v1
task_id: excel-handshake-cleanup
purpose: Implement the process-isolated live Excel permission handshake, exact cleanup, and private bounded native logs.
role: developer
card_path: knowledge/tasks/cgr-publication-excel-handshake-cleanup-k2b2b-v1.md
dependency_shas:
  - 86e9585dc8dd95fed21e07802323ba64bb22e52e
branch: codex/cgr-publication-excel-handshake-cleanup-k2b2b-v1
write_scope:
  - rns_import_server/excel_native.py
  - rns_import_server/excel_process_cleanup.py
  - rns_import_server/group_row_insertion.py
  - scripts/windows_excel_insert.ps1
  - tests/test_excel_native_contract.py
  - tests/test_excel_process_cleanup.py
  - tests/test_group_row_insertion.py
  - knowledge/tasks/cgr-publication-excel-handshake-cleanup-k2b2b-v1.md
forbidden_paths:
  - rns_import_server/excel_process_authority.py
  - rns_import_server/workbook_operation_journal.py
  - rns_import_server/registry_storage.py
  - rns_import_server/server.py
  - rns_import_server/static
contract_versions:
  input: trusted-native-adapter-k2b2a-v2
  output: excel-handshake-cleanup-k2b2b-v1
acceptance_commands:
  - PYTHONPATH=. python3 -m pytest -q tests/test_excel_native_contract.py tests/test_excel_process_cleanup.py tests/test_group_row_insertion.py tests/test_excel_process_authority.py tests/test_workbook_operation_journal.py
  - PYTHONPATH=. python3 -m pytest -q
  - python3 -m compileall -q rns_import_server/excel_native.py rns_import_server/excel_process_cleanup.py rns_import_server/group_row_insertion.py tests/test_excel_native_contract.py tests/test_excel_process_cleanup.py tests/test_group_row_insertion.py
  - git diff --check
---

# Excel handshake and cleanup K2B2b

## Fixed runtime contract

- Production owns one process-isolated `run_native_insert(request, script, journal, timeout)` path. No injectable runner, callback, acceptor, capability, alternate publisher, OpenPyXL/LibreOffice save, raw-OOXML write, silent skip, or partial-success fallback.
- Before launch, parent validates request/mode/native availability and takes a fail-closed frozen Excel PID snapshot. Helper writes a complete BOM-free exact-key `ExcelProcessLease` atomically and durably before any `Workbooks.Open`.
- Parent reads and K2B1-verifies the lease, commits durable journal `staged -> native`, writes/fsyncs audit ACK, then and only then sends one stdin JSON line granting `open`. Helper never reads ACK as permission.
- Stdin stays live for `cancel`; timeout sends and flushes cancel, waits bounded grace, then exact cleanup may act only on the leased process that was not pre-existing and still matches HWND -> PID, image and start time.
- Cleanup mismatch, PID reuse, pre-existing PID, inaccessible evidence, or process still alive is typed failure. Zero kill on mismatch/pre-existing/reuse. Success cannot be emitted or returned before complete COM release/Quit and proof the leased process is gone.
- Stdout/stderr are drained concurrently from launch to EOF without PIPE deadlock. Each retained stream and owner-private durable log is hard-capped at 64 KiB with explicit truncation evidence. Failure to establish private bounded logging before launch fails closed.
- Primary error code/stage is preserved when cleanup also fails; cleanup evidence is attached separately. Public errors never expose workbook paths, payload, streams or traceback.
- `group_row_insertion` passes its journal to the trusted adapter, performs no second `staged -> native`, advances `native -> validated` without a lease rewrite, and uses the durable phase reported by native failure for manual-repair transition.
- Windows helper remains Windows PowerShell 5.1 compatible. No `Task.Run` scriptblock, ACK polling, `taskkill /T`, success-before-cleanup, or native Excel success claim.

## Stable precedence

1. request/mode/row/unavailable before files or process launch;
2. snapshot, launch, lease timeout/shape/identity;
3. journal CAS, ACK durability, stdin permission;
4. helper/protocol/timeout;
5. cleanup alone or attached to preserved primary failure.

## Minimal acceptance evidence

- Call order: verify lease, journal CAS, durable ACK, stdin open; CAS/ACK failure sends no open.
- Timeout sends cancel; helper success waits for confirmed cleanup.
- Exact cleanup terminates only a matching non-preexisting lease and proves disappearance. HWND/image/start mismatch, PID reuse and preexisting PID perform no kill and cannot succeed.
- Oversized simultaneous stdout/stderr complete without deadlock; retained/logged bytes are each at most 64 KiB and private-mode creation is fail-closed.
- Group flow uses only trusted adapter, respects durable native phase, preserves primary+cleanup envelope and all prior K2A/K2B1/K2B2a contracts.
- Static PowerShell checks prove lease-before-open, stdin permission, no ACK polling/Task.Run, exact cleanup tuple and success after cleanup. Native Excel 365 execution remains a separate external Gate.
