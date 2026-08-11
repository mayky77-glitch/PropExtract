---
card_id: windows-unicode-native-bridge-20260811-implementation
status: frozen
version: 1
supersedes: null
work_id: windows-unicode-native-bridge-20260811
task_id: implementation
purpose: Give legacy Windows OCR/Poppler processes ASCII-only relative data/model arguments from a project-local temporary workspace.
role: worker
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
launch_status: planned
card_path: knowledge/tasks/windows-unicode-native-bridge-20260811-implementation.md
planning_parent_sha: cf741ff1046c2d84e50301668c658c2ff3588e8b
dependency_shas: []
branch: codex/windows-unicode-native-bridge
write_scope:
  - install_windows.ps1
  - rns_import_server/ocr.py
  - rns_import_server/runtime.py
  - scripts/windows_ocr_stdio_probe.py
  - tests/test_ocr_resource_limits.py
  - tests/test_admin_server.py
forbidden_paths:
  - .github/workflows/windows-smoke.yml
  - windows-runtime.lock.json
  - packages
  - README.md
contract_versions:
  input: windows-native-path-v1
  output: windows-native-relative-bridge-v1
acceptance_commands:
  - python3 -m pytest -q tests/test_ocr_resource_limits.py tests/test_admin_server.py tests/test_windows_installer_contract.py
  - python3 -m compileall -q rns_import_server scripts tests
  - git diff --check
---

# Windows Unicode native bridge implementation

Preserve public Python signatures unless an optional keyword is required internally. On Windows, copy one source PDF into a unique project-local temporary directory using a fixed ASCII filename; pass PDF/image/output/model paths to native tools only as ASCII relative values with that directory as `cwd`. Keep two-page OCR batching and cleanup on every exit. Use relative `TESSDATA_PREFIX` for install/runtime probes. Linux must retain direct source access and current behavior.

Add synthetic tests proving that a Cyrillic project/source path never appears in native argv or `TESSDATA_PREFIX`, source bytes remain unchanged, staged data is cleaned, and ordering/error behavior remains intact. Do not alter artifact packaging, CI workflow, workbook/parser/server behavior, or private fixtures.
