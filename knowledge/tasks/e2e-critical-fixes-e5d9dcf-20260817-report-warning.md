---
card_id: e2e-critical-fixes-e5d9dcf-20260817-report-warning
status: frozen
version: 1
supersedes: null
work_id: e2e-critical-fixes-e5d9dcf-20260817
task_id: report-warning
purpose: Исправить PE-E2E-002: полностью очищать только stale report-write warning с Причина после успешной записи.
role: developer
route: P3
assigned_model: gpt-5.6-terra
reasoning_effort: medium
launch_status: planned
card_path: knowledge/tasks/e2e-critical-fixes-e5d9dcf-20260817-report-warning.md
card_commit_sha: runtime-envelope
planning_parent_sha: e5d9dcf4ede1d43b7c32976df5d0b542d5e384cc
base_sha: runtime-envelope
dependency_shas: []
branch: codex/e2e-e5d9dcf-report-warning
branch_base_sha: runtime-envelope
write_scope:
  - rns_import_server/server.py
  - rns_import_server/job_report.py
  - tests/test_admin_server.py
  - tests/test_admin_row_edit_regressions.py
  - knowledge/tasks/e2e-critical-fixes-e5d9dcf-20260817-report-warning.md
forbidden_paths:
  - rns_import_server/static/app.css
  - rns_import_server/static/app.js
  - tests/browser_document_cards_responsive.py
  - README.md
contract_versions:
  input: report-warning-final-state-e5d9dcf
  output: report-warning-final-state-cleanup-v1
acceptance_commands:
  - exact-base regression must fail before production edit for one writer OSError followed by successful later action-report write
  - python3 -m pytest -q tests/test_admin_server.py tests/test_admin_row_edit_regressions.py
  - python3 -m compileall -q rns_import_server tests
  - git diff --check
---

# PE-E2E-002 stale report warning

Reproduce one temporary report writer failure, then a later successful report
write through production `JobManager`. After success, response, public job, and
persisted `final_state.warning` must omit the full generated warning including
`Причина: ...`. Preserve every unrelated warning byte-for-byte. Do not change
installer, runtime, OCR, workbook behavior, or PE-E2E-003.
