---
card_id: construction-group-routing-v1-object-routing
status: done
version: 1
supersedes: null
work_id: construction-group-routing-v1
task_id: object-routing
purpose: Преобразовать raw object name в однозначный construction route и object tail с fail-closed typed outcomes.
role: developer
route: P3
assigned_model: gpt-5.6-terra
reasoning_effort: medium
launch_status: inherited
actual_model: inherited
actual_reasoning_effort: inherited
fallback_reason: Runtime did not expose per-child model/effort confirmation; executed within the assigned P3 developer scope.
accepted_feature_sha: b043d169651bda5959dc0dddfe298b0ec02fb92b
card_path: knowledge/tasks/construction-group-routing-v1-object-routing.md
card_commit_sha: runtime-envelope
planning_parent_sha: 9c1d6ffeeb640cc8c72f72e502ae39ae158cc746
base_sha: runtime-envelope
dependency_shas:
  - runtime-envelope
branch: codex/cgr-object-routing
branch_base_sha: runtime-envelope
write_scope:
  - rns_import_server/object_routing.py
  - tests/test_object_group_routing.py
  - knowledge/tasks/construction-group-routing-v1-object-routing.md
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
  output: construction-object-route-v1
acceptance_commands:
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m pytest -q tests/test_object_group_routing.py tests/test_construction_registry.py"
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m compileall -q rns_import_server tests"
  - git diff --check
---

# Wave 2 — object routing

## Required behavior

- Consume accepted immutable registry snapshot/API; do not reopen or mutate SQLite in this layer.
- Preserve original `raw_object`. Normalize only for matching.
- Match official normalized construction name only at start, with punctuation/whitespace boundary. Longest valid nested name wins; no fuzzy/LLM fallback.
- Return stable typed projection containing construction identity, code prefix, status, registry generation, original raw value and exact `object_tail` after removing only matched prefix plus its boundary.
- Unknown, ambiguous/conflicting, archived-for-new-row and stale input fail closed with explicit codes. Draft is never routable.
- Archived construction may remain identifiable for an already-existing-row comparison, but route must carry a flag that forbids new-row creation until reactivation.
- Never infer workbook block, row coordinates, RNS placement or mutation plan.

## Tests

- exact/boundary/punctuation/Unicode normalization and longest nested prefix;
- prefix-like text without valid boundary, empty tail, unknown and conflicting snapshot entries;
- draft exclusion and archived existing-only semantics;
- raw input preserved while tail removes only the exact matched construction prefix;
- deterministic typed outcome and generation propagation; no private PDF text or workbook content in fixtures/diagnostics.

## Handoff

Set card to `review`. Record requested vs actual route, feature SHA, changed paths, exact commands/results, remaining risk and proposed knowledge delta. Commit and push feature branch. Do not merge, amend, rebase or force-push after handoff.

## Review handoff — 2026-08-18

- Requested route: P3 developer / Terra medium. Actual route: inherited developer runtime; per-child model/effort confirmation was unavailable.
- Feature SHA: pending commit (reported separately after commit; this card is not amended after handoff).
- Changed paths: `rns_import_server/object_routing.py`, `tests/test_object_group_routing.py`, and this scoped card.
- Evidence: `'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m pytest -q tests/test_object_group_routing.py tests/test_construction_registry.py` → `11 passed`; `'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m compileall -q rns_import_server tests` → passed; `git diff --check` → passed.
- Risk: this deliberately pure router requires a future consumer to obtain and pass a coherent immutable registry snapshot; it does not read SQLite or decide workbook placement. Archived existing-row context is identity-only and always keeps new-row creation disabled.
- Proposed knowledge delta: document the `construction-object-route-v1` snapshot-only contract, stable outcome codes, raw-tail preservation, and archived/draft fail-closed semantics after integration acceptance.

## Review remediation — 2026-08-18

- Fixed whole-string NFKC-equivalent prefix mapping. Decomposed `И\u0306од` now matches official `Йод` while retaining raw input and exact tail.
- Tail removal now consumes one accepted punctuation separator plus adjacent separator whitespace. It accepts `!` and fullwidth `：`; it preserves meaningful leading punctuation such as `-Объект` in `Йод: -Объект`.
- Duplicate code prefixes now have explicit distinct-name deterministic `CONFLICTING_SNAPSHOT` coverage.
- Evidence: card acceptance rerun after remediation: `13 passed`; compileall and `git diff --check` passed. Focused repros covered decomposed `Йод`, `：`, `!`, `-Объект`, and same-code conflict.
- Remaining risk: prefix-offset construction normalizes complete raw prefixes to preserve NFKC composition mapping; runtime cost grows with raw-object length, but router inputs are single object labels.

## Integration acceptance — 2026-08-18

- Accepted immutable feature tip: `b043d169651bda5959dc0dddfe298b0ec02fb92b`; exact Wave-2 base: `9e25b6982b3dec1f3ccc51fcf1a52436d5f0d22e`.
- Final focused evidence: `13 passed`; compileall and diff checks passed.
- Independent P6 review: ACCEPT. Decomposed Cyrillic, ASCII/fullwidth/multi-character-NFKC boundaries, exact raw-tail preservation, duplicate-code conflict, ancestry and three-path scope verified.
- Remaining risk: raw-prefix span mapping is quadratic in object-label length; inputs are bounded labels and performance changes require later measurement, not semantic shortcuts.
