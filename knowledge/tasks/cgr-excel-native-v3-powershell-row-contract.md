---
card_id: cgr-excel-native-v3-powershell-row-contract
status: frozen
version: 1
work_id: cgr-excel-native-v3-20260818
task_id: powershell-row-contract-v3
purpose: Implement independently testable PowerShell COM handshake and exact audited row mutation contract.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: b41a73b4f823ac41c9996142a9ef37745ea3d7fb
dependency_shas:
  - b41a73b4f823ac41c9996142a9ef37745ea3d7fb
branch: codex/cgr-powershell-row-contract-v3
card_path: knowledge/tasks/cgr-excel-native-v3-powershell-row-contract.md
write_scope:
  - scripts/windows_excel_insert.ps1
  - scripts/WindowsExcelInsert.Contract.psm1
  - tests/test_windows_excel_insert_contract.py
  - tests/windows_excel_insert_contract.Tests.ps1
  - knowledge/tasks/cgr-excel-native-v3-powershell-row-contract.md
forbidden_paths:
  - rns_import_server/excel_native.py
  - rns_import_server/group_row_insertion.py
  - rns_import_server/registry_storage.py
  - rns_import_server/workbook_mutation_manifest.py
  - README.md
contract_versions:
  input: excel-native-row-request-v3
  output: powershell-row-contract-v3
acceptance_commands:
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m pytest -q tests/test_windows_excel_insert_contract.py"
  - "pwsh -NoProfile -File tests/windows_excel_insert_contract.Tests.ps1"
  - git diff --check
---

# Wave 1C — PowerShell row contract v3

- Emit atomic BOM-free structured progress/result/error JSON with stage, HRESULT/WinError, primary and cleanup cause. Lease contains truthful adapter/Excel identity and is durably flushed before waiting for ACK; no workbook opens before exact nonce ACK.
- Independently validate workbook/sheet/group bounds, expected next header, source/template/insertion row, allowed A:X/AA fields and exact Y/Z/W contract.
- Perform exactly one native insertion; copy row height, formats and DV only from validated source/template; set exact `FormulaR1C1`; add one W hyperlink with exact address/display; rebase A ordinals only within group using explicit mapping.
- Always close workbooks and COM proxies; `Quit()` only owned Excel. Cleanup failure is secondary and never hides the primary stage failure.
- Python tests statically/model-check contract and JSON protocol; Pester tests execute mocked COM success at 6/10/104 plus open/insert/calc/save/cleanup faults. Non-Windows absence is explicit, not a pass for real Excel.

Set card `review`, record immutable feature SHA/evidence/Windows risk; normal commit/push only. No merge/amend/rebase/force-push.
