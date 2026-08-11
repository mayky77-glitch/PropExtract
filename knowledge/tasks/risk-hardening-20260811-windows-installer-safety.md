---
card_id: risk-hardening-20260811-windows-installer-safety
status: frozen
version: 1
supersedes: null
work_id: risk-hardening-20260811
task_id: windows-installer-safety
purpose: Защитить офлайн-установку Windows от двойного запуска, нехватки места и опасной длины пути.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
launch_status: planned
card_path: knowledge/tasks/risk-hardening-20260811-windows-installer-safety.md
card_commit_sha: runtime-envelope
planning_parent_sha: e4deefb447067fa739ad6fa5c224ec7928b1bf43
base_sha: runtime-envelope
dependency_shas: []
branch: codex/risk-windows-installer-safety
branch_base_sha: runtime-envelope
write_scope:
  - install_windows.ps1
  - windows_runtime_helpers.ps1
  - install_windows.cmd
  - tests/test_windows_installer_contract.py
forbidden_paths:
  - rns_import_server/server.py
  - rns_import_server/ocr.py
  - .github/workflows/windows-smoke.yml
contract_versions:
  input: windows-runtime-lock-v1
  output: windows-installer-safety-v1
acceptance_commands:
  - python3 -m pytest -q tests/test_windows_installer_contract.py tests/test_admin_server.py
  - git diff --check
---

# Windows installer safety

Preserve exact SHA-256 and full tree-digest verification and the fully offline
installation. Add one installer mutex per project root, writable/free-space and
projected-path preflight, Russian user-facing failures, and safe cleanup of
installer-created stale runtime trees only after the replacement is verified.
Release the mutex in `finally`.

Never remove PDFs, XLSX files, Excel backups, reports, or error logs. Existing
tamper-recovery and repeated-install behavior must remain valid in Windows CI.
