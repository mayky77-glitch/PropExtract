---
card_id: construction-group-routing-v1-registry-core
status: done
version: 1
supersedes: null
work_id: construction-group-routing-v1
task_id: registry-core
purpose: Создать поставляемый SQLite seed, LocalAppData runtime registry и generic workbook-operation journal без Excel/server/UI wiring.
role: database-engineer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
launch_status: inherited
actual_model: inherited
actual_reasoning_effort: inherited
fallback_reason: Runtime did not expose a per-child route confirmation; executed by the assigned database-engineer P4 scope.
accepted_feature_sha: 9c1d6ffeeb640cc8c72f72e502ae39ae158cc746
card_path: knowledge/tasks/construction-group-routing-v1-registry-core.md
card_commit_sha: runtime-envelope
planning_parent_sha: f0f2f6f990dbae3711b4ab8b63af0356b03f2c18
base_sha: runtime-envelope
dependency_shas: []
branch: codex/cgr-registry-core
branch_base_sha: runtime-envelope
write_scope:
  - rns_import_server/construction_registry.py
  - rns_import_server/registry_storage.py
  - rns_import_server/workbook_operation_journal.py
  - rns_import_server/data/construction_registry.seed.sqlite3
  - rns_import_server/data/construction_registry.seed.manifest.json
  - scripts/build_construction_registry_seed.py
  - scripts/validate_construction_registry_seed.py
  - tests/test_construction_registry.py
  - tests/test_registry_storage.py
  - tests/test_workbook_operation_journal.py
  - knowledge/tasks/construction-group-routing-v1-registry-core.md
forbidden_paths:
  - rns_import_server/server.py
  - rns_import_server/app.py
  - rns_import_server/workbook.py
  - rns_import_server/static
  - README.md
contract_versions:
  input: construction-registry-plan-v1
  output: construction-registry-storage-v1
acceptance_commands:
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' scripts/build_construction_registry_seed.py --check"
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' scripts/validate_construction_registry_seed.py"
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m pytest -q tests/test_construction_registry.py tests/test_registry_storage.py tests/test_workbook_operation_journal.py"
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m compileall -q rns_import_server scripts tests"
  - git diff --check
---

# Wave 1 — registry core

## Required behavior

- Git/source archive ships deterministic read-only `construction_registry.seed.sqlite3` plus manifest containing schema version, seed revision, entry count and SHA-256.
- First Windows start creates writable runtime DB at `%LOCALAPPDATA%\PropExtract\construction-registry\registry.sqlite3`. Tests inject the data root; installed seed is never modified. Non-Windows path logic remains importable and testable.
- Runtime SQLite uses short transactions, busy timeout, foreign keys, integrity check, schema versioning, migration backup and `synchronous=FULL` for workbook-operation transitions that precede external publication.
- Construction fields: internal ID, stable optional seed ID, origin, code prefix, official name, normalized name, `draft|active|archived`, row revision and timestamps. Unique normalized name/code conflicts fail explicitly.
- Match only an official normalized prefix at start of PDF object with punctuation/whitespace boundary. Longest valid nested name wins. No fuzzy fallback.
- Bindings store stable construction/workbook-contract/target/sheet/template identity and verified state. Never persist physical row/header coordinates.
- Seed reconciliation keeps stable provenance/base values: untouched seed updates, local-only entries survive, divergent local/seed edits become conflicts, bound name/code changes become alignment conflicts, removal archives only untouched entries. Crash rolls back atomically.

## Approved initial seed

Only these official group names and prefixes enter Git:

- `051-2006437` — `Реконструкция УПГ-102 Ковыктинского ГКМ`
- `051-2006735` — `Газопровод подключения Тас-Юряхского и Верхневилючанского месторождений к МГ "Сила Сибири"`
- `051-2004430` — `Магистральный газопровод "Сила Сибири". Участок "Ковыкта - Чаянда"`
- `051-2000714` — `Обустройство Ковыктинского газоконденсатного месторождения`

No object names, RNS values, row numbers, paths or workbook content enter seed/manifest/tests.

## Generic workbook operation journal

Support `group_provision|new_row` with mutation mode `bootstrap_fill|blank_fill|middle_insert`.

Durable record includes:

- unique operation/idempotency/consumer ID, owner/pair nonce;
- construction ID, canonical RNS when applicable, stable target/sheet/template identity and expected registry generation;
- intent/manifest version+digest, operation directory;
- pre/staged/control/post/backup hashes and validation digest;
- Excel lease metadata: adapter/Excel PID, HWND, process start, build;
- legal phase, failure code, capability/binding/history/report finalization flags and timestamps.

API uses CAS transitions and rejects illegal/repeated moves. Required lifecycle covers planned, staged/native phases, validated, backup verified, published, finalized and manual repair. Incomplete operations are listable after restart. Post-hash evidence is durable before caller may replace target.

## Tests

- deterministic seed bytes/manifest and clean bootstrap;
- Unicode normalization, longest boundary prefix, duplicate name/code, status and stale generation;
- seed update/local edit/removal/bound-alignment conflict and crash rollback;
- corrupt/newer schema, bounded lock, migration backup, no write into installed seed;
- journal required fields, CAS/phase validation, idempotency, `synchronous=FULL`, restart read and finalization flags;
- no secrets, PDF text, cell content or local source paths in seed/journal diagnostics.

## Handoff

Set card to `review`. Record requested vs actual route, feature SHA, changed paths, exact commands/results, remaining risk and proposed knowledge delta. Commit and push feature branch. Do not merge, amend, rebase or force-push after handoff.

## Review handoff — 2026-08-18

- Requested route: P4 database-engineer / Terra high. Actual route: inherited database-engineer runtime; per-child model/effort confirmation was unavailable.
- Feature SHA: pending commit (reported separately after commit; card is not amended after handoff).
- Changed paths: `rns_import_server/construction_registry.py`, `rns_import_server/registry_storage.py`, `rns_import_server/workbook_operation_journal.py`, `rns_import_server/data/construction_registry.seed.sqlite3`, `rns_import_server/data/construction_registry.seed.manifest.json`, `scripts/build_construction_registry_seed.py`, `scripts/validate_construction_registry_seed.py`, and the three scoped registry/journal test files.
- Evidence: `/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python -m pytest -q tests/test_construction_registry.py tests/test_registry_storage.py tests/test_workbook_operation_journal.py` → `10 passed`; `scripts/build_construction_registry_seed.py --check` and `scripts/validate_construction_registry_seed.py` → passed; `compileall` and `git diff --check` → passed.
- Risk: schema v1 migration supports only legacy version marker `0`; future schema versions require explicit tested migration steps. Runtime SQLite is local-only; concurrent writers receive bounded SQLite lock failure instead of a server-mediated retry.
- Proposed knowledge delta: record the seed/runtime split, v1 registry schema, three-way seed reconciliation conflict behavior, and generic journal phase/CAS contract after integration accepts this feature.

## Remediation handoff — 2026-08-18

- Review findings addressed: seed/runtime schema is now v2 with a verified backup migration from v0/v1; schema-less interrupted runtime databases fail closed. Drafts never route, ordinary draft activation is rejected, and unbound-local updates use generation plus row-revision CAS while bound identity is immutable.
- Journal now persists phase-specific evidence: `pre_hash`/`staged_hash`, native lease and control evidence, an independently durable `post_hash` before published CAS, phase-gated per-flag timestamps, finalization gate, and visible manual-repair operations. Exact idempotent retries compare every immutable intent field.
- Reconciliation deduplicates unresolved conflicts/removals, preserving generation and row revision on repeated identical reconcile.
- Feature SHA: pending remediation commit (reported separately; no amend after handoff).
- Evidence: `/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python -m pytest -q tests/test_construction_registry.py tests/test_registry_storage.py tests/test_workbook_operation_journal.py` → `14 passed`; deterministic seed check, seed validator, compileall, and diff check passed.
- Remaining risk: v2 stores the foundation only; actual Excel publication and recovery dispatcher consumers remain later-wave responsibilities. Future schema versions require explicit reversible migration steps.

## Integration acceptance — 2026-08-18

- Accepted immutable feature tip: `9c1d6ffeeb640cc8c72f72e502ae39ae158cc746`; exact Wave-1 base: `3e2ff332454669b912825ba9428287cc7444c2a7`.
- Recovery closed draft routing/activation, journal evidence/idempotency/finalization, stable seed reconciliation, typed incomplete-schema rejection, safe v1 conflict migration, and legacy journal-state quarantine.
- Final focused evidence: registry-core suite `24 passed`; deterministic seed check passed; validator reported `schema=2`, revision `construction-registry-v2`, four approved entries; compileall and diff check passed.
- Independent P6 review: ACCEPT. Exact v1 migration repros, restart visibility, ancestry and all eleven reserved paths verified; no substantive residual or frozen-card test gap.
- Remaining risk: impossible legacy journal states migrate to visible `manual_repair` with `legacy_journal_state_invalid`; operator recovery is intentionally required instead of unsafe automatic completion.
