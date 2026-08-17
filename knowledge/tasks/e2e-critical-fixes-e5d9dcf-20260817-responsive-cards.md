---
card_id: e2e-critical-fixes-e5d9dcf-20260817-responsive-cards
status: review
version: 2
supersedes: null
work_id: e2e-critical-fixes-e5d9dcf-20260817
task_id: responsive-cards
purpose: Исправить PE-E2E-001 для document cards при 541-850 px и доказать 768 px без регрессий 480/1440.
role: developer
route: P3
assigned_model: gpt-5.6-terra
reasoning_effort: medium
launch_status: inherited
actual_model: inherited
actual_reasoning_effort: inherited
route_note: Runtime did not expose a model/effort override confirmation; inherited execution remains at the P3-safe route.
card_path: knowledge/tasks/e2e-critical-fixes-e5d9dcf-20260817-responsive-cards.md
card_commit_sha: runtime-envelope
planning_parent_sha: e5d9dcf4ede1d43b7c32976df5d0b542d5e384cc
base_sha: runtime-envelope
dependency_shas: []
branch: codex/e2e-e5d9dcf-responsive-cards
branch_base_sha: runtime-envelope
write_scope:
  - rns_import_server/static/app.css
  - tests/browser_document_cards_responsive.py
  - knowledge/tasks/e2e-critical-fixes-e5d9dcf-20260817-responsive-cards.md
forbidden_paths:
  - rns_import_server/server.py
  - rns_import_server/job_report.py
  - tests/test_admin_server.py
  - tests/test_admin_row_edit_regressions.py
  - README.md
contract_versions:
  input: document-card-layout-e5d9dcf
  output: document-card-layout-responsive-v1
acceptance_commands:
  - exact-base regression script must fail before production edit at viewport 768 and record passing 480/1440 controls
  - python3 tests/browser_document_cards_responsive.py
  - node --check rns_import_server/static/app.js
  - git diff --check
---

# PE-E2E-001 responsive document cards

Use only synthetic public mock job data. Add dedicated browser regression proof
for computed document-card layout at 1440, 768, and 480 px. At 768 px main
content must remain readable and effectively full-width; 480 and 1440 must keep
their existing valid layouts. Capture concise command evidence, not screenshots
or private document names, in handoff. Do not address PE-E2E-003.

## Handoff evidence

- Baseline card bytes matched `5de1fe27f9109de24795e3f12e31f88080692ff4`; worktree was clean at that exact base before edits.
- Before CSS edit: `.venv/bin/python tests/browser_document_cards_responsive.py` failed as intended. Controls passed at 1440 (`1076px` single grid column; main `1076` of card `1078`) and 480 (`396px`; main `396` of `398`); 768 failed with `72px 564px`, main width `72` of card `638`.
- After CSS edit: `.venv/bin/python tests/browser_document_cards_responsive.py` passed. Computed layouts: 1440 `1076px` / main `1076` of `1078`; 768 `636px` / main `636` of `638`; 480 `396px` / main `396` of `398`. Every viewport had `scrollWidth <= clientWidth`.
- Passed: `node --check rns_import_server/static/app.js`; `git diff --check`.

## Changed paths

- `rns_import_server/static/app.css`
- `tests/browser_document_cards_responsive.py`
- `knowledge/tasks/e2e-critical-fixes-e5d9dcf-20260817-responsive-cards.md`

## Risks and proposed knowledge delta

- Risk: the focused browser test requires the local ignored `.venv` with Playwright and Chromium; CI must install `requirements-dev.txt` and browser assets before running it.
- Proposed knowledge delta: document that the 850px generic `.record-card` grid rule must preserve the document-card single-column override, with browser evidence at 1440/768/480.
