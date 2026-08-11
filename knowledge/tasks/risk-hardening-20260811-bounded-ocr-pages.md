---
card_id: risk-hardening-20260811-bounded-ocr-pages
status: frozen
version: 1
supersedes: null
work_id: risk-hardening-20260811
task_id: bounded-ocr-pages
purpose: Ограничить одновременные OCR PNG без пропуска страниц и изменения публичного контракта.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
launch_status: planned
card_path: knowledge/tasks/risk-hardening-20260811-bounded-ocr-pages.md
card_commit_sha: runtime-envelope
planning_parent_sha: e4deefb447067fa739ad6fa5c224ec7928b1bf43
base_sha: runtime-envelope
dependency_shas: []
branch: codex/risk-bounded-ocr-pages
branch_base_sha: runtime-envelope
write_scope:
  - rns_import_server/ocr.py
  - tests/test_ocr_resource_limits.py
forbidden_paths:
  - rns_import_server/server.py
  - rns_import_server/workbook.py
  - install_windows.ps1
contract_versions:
  input: ocr-read-v1
  output: ocr-read-v1-bounded-resources
acceptance_commands:
  - python3 -m pytest -q tests/test_ocr_resource_limits.py tests/test_admin_server.py
  - python3 -m compileall -q rns_import_server
  - git diff --check
---

# Bounded OCR pages

Keep `read(pdf, dpi, max_pages) -> (text, total)` unchanged. Render a bounded
page batch, OCR in deterministic page order, delete batch PNG files before the
next batch, and fail the document on render/OCR error. Do not add an arbitrary
page limit or silently return partial text.

Tests must cover bounded live PNG count, order, Unicode paths, empty stdout,
and cleanup after timeout or failure.
