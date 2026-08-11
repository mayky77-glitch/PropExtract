---
card_id: risk-lifecycle-20260811-windows-e2e-smoke
status: frozen
version: 1
supersedes: null
work_id: risk-lifecycle-20260811
task_id: windows-e2e-smoke
purpose: Проверить на Windows точный offline runtime, жизненный цикл и реальный синтетический PDF-to-XLSX/no-op.
role: devops
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
launch_status: planned
card_path: knowledge/tasks/risk-lifecycle-20260811-windows-e2e-smoke.md
card_commit_sha: runtime-envelope
planning_parent_sha: ba9e9036e11d5f97be748ab93975d0697a080010
base_sha: runtime-envelope
dependency_shas:
  - instance-lifecycle-accepted-integration
branch: codex/risk-windows-e2e-smoke
branch_base_sha: runtime-envelope
write_scope:
  - .github/workflows/windows-smoke.yml
  - scripts/windows_end_to_end_smoke.py
  - README.md
forbidden_paths:
  - rns_import_server
  - install_windows.ps1
  - start_windows.ps1
  - stop_windows.ps1
contract_versions:
  input: instance-lifecycle-v1
  output: windows-smoke-v2
acceptance_commands:
  - python3 scripts/windows_end_to_end_smoke.py --self-test
  - ruby -e 'require "yaml"; YAML.load_file(".github/workflows/windows-smoke.yml")'
  - node --check rns_import_server/static/app.js
  - git diff --check
---

# Windows end-to-end smoke

Keep installer fully offline. Add a portable-Python synthetic run that creates
its own non-private PDF/XLSX fixtures, verifies a real publication, verifies a
second identical run leaves XLSX bytes and mtime unchanged with no new Excel
backup, and checks source fixture hashes. Exercise same-instance health,
double-start behavior, stop completion, immediate restart, Unicode paths, and
installer preflight contracts on Windows 2022.

No private fixture, network download, system Python, pytest installation, or
unbounded workflow wait. README must describe no-op, OCR batching, installer
preflight, instance lifecycle, and residual Windows 10/ARM/manual limits.
