---
card_id: risk-lifecycle-20260811-instance-lifecycle
status: frozen
version: 1
supersedes: null
work_id: risk-lifecycle-20260811
task_id: instance-lifecycle
purpose: Не путать разные копии PropExtract на порту 8775 и подтверждать реальную готовность/остановку.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
launch_status: planned
card_path: knowledge/tasks/risk-lifecycle-20260811-instance-lifecycle.md
card_commit_sha: runtime-envelope
planning_parent_sha: ba9e9036e11d5f97be748ab93975d0697a080010
base_sha: runtime-envelope
dependency_shas: []
branch: codex/risk-instance-lifecycle
branch_base_sha: runtime-envelope
write_scope:
  - rns_import_server/app.py
  - rns_import_server/server.py
  - start_windows.ps1
  - stop_windows.ps1
  - start_linux.sh
  - tests/test_lifecycle_contract.py
forbidden_paths:
  - install_windows.ps1
  - windows_runtime_helpers.ps1
  - .github/workflows/windows-smoke.yml
  - README.md
contract_versions:
  input: loopback-server-v1
  output: instance-lifecycle-v1
acceptance_commands:
  - python3 -m pytest -q tests/test_lifecycle_contract.py tests/test_admin_server.py
  - python3 -m compileall -q rns_import_server
  - sh -n start_linux.sh
  - git diff --check
---

# Instance lifecycle

Expose an opaque project-instance identifier from `/health` without leaking a
path. Windows start/stop must act only on the same instance. Browser opening
must happen after successful bind. Stop must wait until the original instance
is gone. A port collision, wrong instance, bind failure, or timeout must return
a specific Russian message and preserve the underlying diagnostic.

Extend transient Excel/share lock retries with a bounded deadline/backoff while
re-raising the original last `OSError`. Preserve loopback-only binding, one-job
semantics, existing API paths, and Linux startup.
