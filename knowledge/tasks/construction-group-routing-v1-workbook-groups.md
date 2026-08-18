---
card_id: construction-group-routing-v1-workbook-groups
status: review
version: 1
supersedes: null
work_id: construction-group-routing-v1
task_id: workbook-groups
purpose: Семантически разрешить один Excel-блок стройки, group-first РНС и безопасный blank/insertion plan без мутации книги.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
launch_status: resumed
actual_model: inherited
actual_reasoning_effort: inherited
fallback_reason: runtime did not expose an agent-model override; requested P4 route retained as task requirement
card_path: knowledge/tasks/construction-group-routing-v1-workbook-groups.md
card_commit_sha: runtime-envelope
planning_parent_sha: 9c1d6ffeeb640cc8c72f72e502ae39ae158cc746
base_sha: runtime-envelope
dependency_shas:
  - runtime-envelope
branch: codex/cgr-workbook-groups
branch_base_sha: runtime-envelope
write_scope:
  - rns_import_server/workbook_groups.py
  - tests/test_workbook_group_routing.py
  - knowledge/tasks/construction-group-routing-v1-workbook-groups.md
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
  output: workbook-group-resolution-v1
acceptance_commands:
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m pytest -q tests/test_workbook_group_routing.py tests/test_construction_registry.py"
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m compileall -q rns_import_server tests"
  - git diff --check
---

# Wave 2 — workbook group resolver

## Required behavior

- Read an injected workbook/sheet projection only. Do not save, stage, insert rows, call Excel, mutate DB, or expose HTTP/UI.
- A valid header has D equal to official name and A/B/C/E/F blank. Resolve exactly one header; group ends immediately before next valid header. Repeated header is `block_duplicate`, missing header is `block_missing`; neither is continuation.
- Validate structured child C values against construction code prefix. Blank and legacy `-` remain allowed; a recognized foreign prefix makes block structurally conflicting.
- Canonical RNS search is group-first: exactly one inside match wins even when same RNS exists elsewhere; multiple inside gives `rns_block_conflict`; none inside plus any outside gives `rns_wrong_block`; only global absence may request a new row.
- Existing-row result keeps stable semantic identity and raw values, never treats C or physical row as unique identity, and never moves a row.
- Produce read-only mutation planning data: proven existing blank/preformatted row inside group when eligible, otherwise insertion point directly before next header; last-group free business row is eligible only when template/boundary evidence proves group ownership.
- Enforce C/name consistency: repeated full C with equivalent D may be allowed; repeated full C with different D yields `object_code_name_conflict`.
- Include workbook identity/hash and registry generation in plan for later stale revalidation. No silent fallback.

## Tests

- adjacent groups and exact single header; missing/repeated header;
- same RNS inside and outside, outside-only, duplicate inside and globally absent;
- foreign/blank/legacy C values and recognized code-prefix conflict;
- validated blank slot vs insertion before next headers 6, 10 and 104; no arbitrary blank C;
- repeated C with equivalent/different D, leading-zero code values, stale identity fields;
- resolver is side-effect free and fixtures contain no private workbook/PDF data.

## Handoff

Set card to `review`. Record requested vs actual route, feature SHA, changed paths, exact commands/results, remaining risk and proposed knowledge delta. Commit and push feature branch. Do not merge, amend, rebase or force-push after handoff.

## Review handoff — 2026-08-18

- Route: requested `P4`, `gpt-5.6-terra`/`high`; actual runtime route inherited (override not exposed).
- Feature SHA: pending human commit; worker did not commit or push.
- Changed paths: `rns_import_server/workbook_groups.py`, `tests/test_workbook_group_routing.py`, this card.
- Checks: `'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m pytest -q tests/test_workbook_group_routing.py tests/test_construction_registry.py` — `18 passed`; `'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m compileall -q rns_import_server tests` — passed; `git diff --check` — passed.
- Remaining risk: caller must project authoritative construction-header names and revalidate plan identity/hash/generation under publication lock; native mutation remains Wave 2B scope.
- Proposed knowledge delta: record `workbook_groups.py` as pure A:F semantic block resolver; no `knowledge/INDEX.md` exists in this frozen worktree, so no shared vault index changed.

## Review remediation — 2026-08-18

- Full C recognition is now exact `^[0-9]{3}-[0-9]{7}\.[0-9]{4}$`; foreign `999-1234567.0001` is a structural conflict and leading-zero suffixes remain raw strings.
- An immutable official-header catalogue is required. Missing/empty/incomplete catalogues return `header_catalogue_required`; a complete catalogue keeps adjacent-group RNS as `rns_wrong_block`.
- Checks: focused registry acceptance — `19 passed`; compileall and whitespace checks — passed.
