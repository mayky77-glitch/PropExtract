---
card_id: cgr-publication-excel-handshake-cleanup-k2b2b-v2
status: frozen
version: 2
supersedes: cgr-publication-excel-handshake-cleanup-k2b2b-v1
work_id: cgr-publication-excel-handshake-cleanup-k2b2b-v2
task_id: excel-handshake-cleanup
purpose: Implement a process-isolated Excel permission handshake with a proven live cancel channel, exact cleanup, and bounded private logs.
role: developer
card_path: knowledge/tasks/cgr-publication-excel-handshake-cleanup-k2b2b-v2.md
dependency_shas:
  - 86e9585dc8dd95fed21e07802323ba64bb22e52e
branch: codex/cgr-publication-excel-handshake-cleanup-k2b2b-v2
write_scope:
  - rns_import_server/excel_native.py
  - rns_import_server/excel_process_cleanup.py
  - rns_import_server/group_row_insertion.py
  - scripts/windows_excel_insert.ps1
  - tests/test_excel_native_contract.py
  - tests/test_excel_process_cleanup.py
  - tests/test_group_row_insertion.py
  - knowledge/tasks/cgr-publication-excel-handshake-cleanup-k2b2b-v2.md
forbidden_paths:
  - rns_import_server/excel_process_authority.py
  - rns_import_server/workbook_operation_journal.py
  - rns_import_server/registry_storage.py
  - rns_import_server/server.py
  - rns_import_server/static
contract_versions:
  input: trusted-native-adapter-k2b2a-v2
  output: excel-handshake-cleanup-k2b2b-v2
acceptance_commands:
  - PYTHONPATH=. python3 -m pytest -q tests/test_excel_native_contract.py tests/test_excel_process_cleanup.py tests/test_group_row_insertion.py tests/test_excel_process_authority.py tests/test_workbook_operation_journal.py
  - PYTHONPATH=. python3 -m pytest -q
  - python3 -m compileall -q rns_import_server/excel_native.py rns_import_server/excel_process_cleanup.py rns_import_server/group_row_insertion.py tests/test_excel_native_contract.py tests/test_excel_process_cleanup.py tests/test_group_row_insertion.py
  - git diff --check
knowledge_paths:
  - knowledge/INDEX.md
  - knowledge/tasks/cgr-publication-excel-handshake-cleanup-k2b2b-v2.md
---

# Excel handshake and cleanup K2B2b v2

## Fixed boundary

- Start only from accepted K2B2a-v2 `86e9585`; rejected K2B2/K2B2b-v1 commits are contract references only and must not be merged, cherry-picked, or enter ancestry.
- Production has one trusted `run_native_insert(request, script, journal, timeout)` path. No injected runner, callback, fallback publisher, OpenPyXL/LibreOffice save, raw OOXML write, silent skip, or partial success.
- Validate exact built-in request values before files or launch. Freeze the prelaunch Excel PID snapshot fail closed.
- Helper durably writes the complete exact K2B1 lease before any `Workbooks.Open`. Parent verifies it, commits `staged -> native`, fsyncs audit ACK, then grants `open` only through live stdin. ACK is never permission.
- Stdin is owned by one dedicated C# background reader thread using `Console.OpenStandardInput`; it parses sequential exact JSON lines `open` then optional `cancel`. Main/COM thread only reads thread-safe flags. No `Peek`, pending `ReadLineAsync` that keeps process alive, `Task.Run`, PowerShell background job, or competing stdin reader.
- Normal checkpoints must never block while parent stdin remains open. A cancel written after `open` must be consumed within bounded grace. The background reader must not keep the helper alive after normal completion.
- Timeout sends/flushed `cancel`, waits bounded grace, then exact cleanup may terminate only the non-preexisting leased Excel process still matching HWND-to-PID, canonical image and start time. Mismatch, PID reuse, preexisting PID, inaccessible evidence, or still-alive process is typed failure and never kill success.
- Parent drains stdout/stderr concurrently and persists at most 64 KiB per stream under verified current-user-only Windows DACL. Logging failure blocks launch. Primary code/stage is preserved; cleanup and journal causes stay separate.
- Every error after durable `staged -> native` reports durable phase `native`; group recovery moves that exact phase to manual repair. Process-missing detection is locale-neutral structured data; runtime image observations canonicalize to exact `EXCEL.EXE`.
- Success is impossible before COM release/Quit and proof the leased process disappeared. Native Microsoft Excel execution remains a later external Gate.

## Exact acceptance evidence

- verify lease -> journal CAS -> durable ACK -> stdin `open`; CAS/ACK/open failures preserve exact durable phase and send no false permission.
- Native Windows PowerShell 5.1 redirected-pipe proof from the exact embedded C# source: no-cancel exits while parent stdin is still open; post-open cancel exits within grace. CrossOver/Wine may be supplementary but cannot qualify the native pipe contract.
- Exact cleanup success/mismatch/PID-reuse/preexisting matrix, locale-neutral missing process, canonical image, DACL-before-Popen, strict request/row/timeout/Path, capped dual-stream drain, primary+cleanup preservation.
- Group flow calls only trusted adapter, performs no second lease CAS, advances native -> validated, and leaves no publication output on failure.
