---
card_id: cgr-excel-native-v3-process-authority
status: review
version: 1
work_id: cgr-excel-native-v3-20260818
task_id: windows-process-authority-v1
purpose: Provide injectable Win32 authority for exact adapter and leased Excel process identity, revalidation and bounded cleanup.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: b41a73b4f823ac41c9996142a9ef37745ea3d7fb
dependency_shas:
  - b41a73b4f823ac41c9996142a9ef37745ea3d7fb
branch: codex/cgr-windows-process-authority-v1
card_path: knowledge/tasks/cgr-excel-native-v3-process-authority.md
write_scope:
  - rns_import_server/windows_process_authority.py
  - tests/test_windows_process_authority.py
  - knowledge/tasks/cgr-excel-native-v3-process-authority.md
forbidden_paths:
  - rns_import_server/excel_native.py
  - rns_import_server/group_row_insertion.py
  - rns_import_server/registry_storage.py
  - scripts/windows_excel_insert.ps1
  - README.md
contract_versions:
  input: win32-process-identity-v1
  output: windows-process-authority-v1
acceptance_commands:
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m pytest -q tests/test_windows_process_authority.py"
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m compileall -q rns_import_server tests"
  - git diff --check
---

# Wave 1B — Windows process authority

- Implement an injectable ctypes Win32 facade: process image/start, HWND→PID, open/query/terminate/wait/close handles and typed Win32/access errors. Module remains importable on non-Windows with explicit unsupported outcome.
- Verify adapter identity exactly against `Popen.pid`, expected PowerShell image and creation time.
- Verify Excel lease exactly against PID/HWND/image=`EXCEL.EXE`/creation time; reject mismatch, access denied and PID reuse.
- Terminator is mandatory. Revalidate immediately before bounded `TerminateProcess` + wait; never terminate on incomplete/mismatched authority and never touch user Excel.
- Tests inject facade outcomes for success, mismatch, reused PID, access denied, vanished process, timeout and handle cleanup.

## Handoff evidence

- P4 developer route completed with injectable facade only; no adapter/publisher edits.
- Passed: `pytest -q tests/test_windows_process_authority.py` (6 passed), compileall and diff check.
- Windows API calls are simulated by the facade on this non-Windows host; real Windows validation remains a later gate.

Set card `review`, record immutable feature SHA/evidence/risks; normal commit/push only. No merge/amend/rebase/force-push.
