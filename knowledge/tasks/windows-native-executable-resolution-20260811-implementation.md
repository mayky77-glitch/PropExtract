---
card_id: windows-native-executable-resolution-20260811-implementation
status: frozen
version: 1
supersedes: null
work_id: windows-native-executable-resolution-20260811
task_id: implementation
purpose: Keep the verified Windows executable absolute and make only native data/model arguments ASCII-relative.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
launch_status: planned
card_path: knowledge/tasks/windows-native-executable-resolution-20260811-implementation.md
planning_parent_sha: a97c74749a3ca222de70d197979e8c48c7c866bd
dependency_shas:
  - a97c74749a3ca222de70d197979e8c48c7c866bd
branch: codex/windows-native-executable-resolution
write_scope:
  - rns_import_server/ocr.py
  - tests/test_ocr_resource_limits.py
forbidden_paths:
  - .github/workflows/windows-smoke.yml
  - scripts/windows_ocr_stdio_probe.py
  - install_windows.ps1
  - windows-runtime.lock.json
  - packages
  - README.md
contract_versions:
  input: windows-native-relative-bridge-v1
  output: windows-native-executable-resolution-v1
acceptance_commands:
  - python3 -m pytest -q tests/test_ocr_resource_limits.py tests/test_admin_server.py tests/test_windows_installer_contract.py
  - python3 -m pytest -q
  - python3 -m compileall -q rns_import_server scripts tests
  - git diff --check
---

# Windows native executable resolution

Change `_native_argv` so `argv[0]` preserves the exact verified command path. Continue converting only `argv[1:]` to ASCII-relative paths under the native workspace. Add a regression with an absolute Unicode command path proving it remains unchanged while every consumed data/model path remains ASCII-relative. Preserve all public signatures, source files, staging/cleanup, Linux behavior, and Russian operator errors.
