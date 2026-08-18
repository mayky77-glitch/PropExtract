---
card_id: construction-group-routing-v1-excel-native-remediation
status: review
version: 1
work_id: construction-group-routing-v1-row-remediation
task_id: excel-native-remediation
purpose: Завершить безопасный Excel COM lease/ACK и audited row construction для native middle insertion.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
launch_status: completed
actual_model: gpt-5.6-terra
actual_reasoning_effort: high
fallback_reason: null
card_path: knowledge/tasks/construction-group-routing-v1-excel-native-remediation.md
card_commit_sha: runtime-envelope
planning_parent_sha: 2ff1f0df4cf5cbc379e2455a39ec75de53f55504
base_sha: runtime-envelope
dependency_shas:
  - 2ff1f0df4cf5cbc379e2455a39ec75de53f55504
branch: codex/cgr-excel-native-remediation
branch_base_sha: runtime-envelope
write_scope:
  - rns_import_server/excel_native.py
  - scripts/windows_excel_insert.ps1
  - tests/test_excel_native_contract.py
  - knowledge/tasks/construction-group-routing-v1-excel-native-remediation.md
forbidden_paths:
  - rns_import_server/group_row_insertion.py
  - rns_import_server/workbook_structure.py
  - rns_import_server/workbook_mutation_manifest.py
  - rns_import_server/workbook.py
  - README.md
contract_versions:
  input: native-group-row-insertion-v1
  output: excel-native-lease-row-v2
acceptance_commands:
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m pytest -q tests/test_excel_native_contract.py"
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m compileall -q rns_import_server tests"
  - git diff --check
---

# Remediation A — Excel native lease and COM row

## Required behavior

- PowerShell creates a hidden dedicated `Excel.Application`, obtains `Application.Hwnd`, resolves HWND→actual Excel PID, reads process creation time/image/build, and atomically flushes a nonce-bound lease with truthful adapter PID/start and Excel PID/HWND/start/build before any `Workbooks.Open`.
- Python validates operation/owner/pair nonce, adapter identity, image=`EXCEL.EXE`, creation time and HWND→PID; a caller-provided durable lease recorder must succeed before Python writes nonce-matched ACK. Helper may open workbooks only after that ACK.
- Timeout/cleanup revalidates nonce, image, creation time and HWND→PID, then terminates only the still-matching leased Excel instance. Never treat PowerShell PID or a pre-start snapshot as Excel ownership; never kill user Excel or a reused PID.
- Helper is exclusive to `insert_before_header`. It accepts and validates explicit sheet identity, insertion row, fields and template/same-group contract; inserts exactly one row and performs allowlisted A:X/AA writes, Y/Z `FormulaR1C1`, deterministic A ordinal rebasing, validated format/DV transfer and exactly one hyperlink/display contract inside Excel.
- Do not add a blank-fill structural insert path. Preserve stage, HRESULT/WinError and primary/cleanup causes in typed helper results. No OpenPyXL/raw-OOXML mutation fallback.

## Tests and handoff

- Mock lease lifecycle: truthful PID/HWND/start/build, durable-recorder-before-ACK ordering, ACK refusal, PID reuse/image/HWND mismatch, bounded cleanup, timeout, and user Excel preservation.
- Mock successful explicit-sheet insert at rows 6, 10 and 104; reject wrong sheet, non-allowlisted fields, invalid template/formula/hyperlink contract; assert exactly one insert.
- Real Windows Excel remains a blocking external gate and must be reported unavailable on non-Windows. Set card `review`, record immutable SHA/evidence/risks, commit/push normally; no merge/amend/rebase/force-push.

## Handoff evidence

- Actual route: P4 developer, `gpt-5.6-terra` / high; no fallback.
- Changed only the four card-owned implementation/test paths plus this card.
- Passed: `pytest -q tests/test_excel_native_contract.py` (7 passed); `compileall -q rns_import_server tests`; `git diff --check`.
- Hosted macOS has no desktop Excel; real COM insert/recalculate/save/reopen is intentionally unexecuted and remains the blocking Windows gate.
- Risk: process/HWND ownership checks are unit-mocked here and need real Windows API evidence before enabling production middle insertion.
- Recovery cycle: recorder and concrete process probe are required before spawn; ACK/lease use atomic BOM-free UTF-8 writes and the parser accepts/strips accidental BOM. Timeout retains primary plus cleanup cause.
