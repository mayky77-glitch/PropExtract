---
card_id: construction-group-routing-v1-registry-service
status: review
version: 1
supersedes: null
work_id: construction-group-routing-v1
task_id: registry-service
purpose: Дать validated admin-service projection для draft/provision/status операций с generation и active-job gate без HTTP/UI wiring.
role: developer
route: P3
assigned_model: gpt-5.6-terra
reasoning_effort: medium
launch_status: resumed
actual_model: inherited
actual_reasoning_effort: inherited
fallback_reason: runtime did not expose an agent-model override; requested P3 route retained as task requirement
card_path: knowledge/tasks/construction-group-routing-v1-registry-service.md
card_commit_sha: runtime-envelope
planning_parent_sha: 9c1d6ffeeb640cc8c72f72e502ae39ae158cc746
base_sha: runtime-envelope
dependency_shas:
  - runtime-envelope
branch: codex/cgr-registry-service
branch_base_sha: runtime-envelope
write_scope:
  - rns_import_server/registry_admin.py
  - tests/test_registry_admin_service.py
  - knowledge/tasks/construction-group-routing-v1-registry-service.md
forbidden_paths:
  - rns_import_server/construction_registry.py
  - rns_import_server/registry_storage.py
  - rns_import_server/workbook_operation_journal.py
  - rns_import_server/workbook.py
  - rns_import_server/server.py
  - rns_import_server/app.py
  - rns_import_server/static
  - README.md
contract_versions:
  input: construction-registry-storage-v1
  output: construction-registry-admin-service-v1
acceptance_commands:
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m pytest -q tests/test_registry_admin_service.py tests/test_construction_registry.py tests/test_registry_storage.py"
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m compileall -q rns_import_server tests"
  - git diff --check
---

# Wave 2 — registry admin service

## Required behavior

- Consume accepted registry storage APIs and return transport-neutral validated service results; do not edit server/app/static/workbook paths.
- List projection returns constructions plus exact registry generation and stable status/binding/conflict data needed by future API/UI.
- Validate official name, fixed v1 code prefix grammar `^[0-9]{3}-[0-9]{7}$`, uniqueness and expected generation before creating a draft/provision request.
- Admin create is provision-only: create/represent non-routable `draft` intent; this service must not activate it or claim a workbook block exists. Actual XLSX provisioning remains a later wave.
- Draft correction is allowed before provision. Plain PATCH cannot activate a draft, create a construction, hard-delete, or rename/recode a bound active/archived construction.
- Bound name/code change returns `binding_alignment_required` without DB/XLSX change. Bound active/archived PATCH may change only status with expected generation.
- Reactivation requires injected binding revalidation; failed/ambiguous/missing binding remains non-active with typed outcome.
- Enforce injected active-job/publication gate: conflicting mutation rejects or waits only according to explicit caller policy; no unbounded retry or catch-and-continue.
- Duplicate, invalid, stale generation, active-job and binding failures are deterministic typed results suitable for Russian API/UI mapping. Draft never appears in routable snapshot.

## Tests

- list/generation projection; duplicate normalized name/code and invalid grammar;
- provision creates only draft intent, never active route;
- draft correction; forbidden ordinary activation/hard delete;
- bound rename/recode rejection and status-only archive/reactivate;
- reactivation binding validation, stale generation/CAS and active-job gate;
- no server/static/workbook mutation and no silent success/no-op on failure.

## Handoff

Set card to `review`. Record requested vs actual route, feature SHA, changed paths, exact commands/results, remaining risk and proposed knowledge delta. Commit and push feature branch. Do not merge, amend, rebase or force-push after handoff.

## Review handoff — 2026-08-18

- Route: requested `P3`, `gpt-5.6-terra`/`medium`; actual runtime route inherited (override not exposed).
- Feature SHA: pending commit at card update; commit/push follows this review record.
- Changed paths: `rns_import_server/registry_admin.py`, `tests/test_registry_admin_service.py`, this card.
- Checks: `'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m pytest -q tests/test_registry_admin_service.py tests/test_construction_registry.py tests/test_registry_storage.py` — `23 passed`; `'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m compileall -q rns_import_server tests` — passed; `git diff --check` — passed.
- Remaining risk: storage has no public binding projection method, so this transport-neutral read projection uses its accepted local SQLite connection; server/UI wiring and actual XLSX provisioning remain later-wave scopes.
- Proposed knowledge delta: record `registry_admin.py` as draft-only admin service with generation, active-job, and binding-revalidation gates; no `knowledge/INDEX.md` exists in this frozen worktree, so no shared vault index changed.
