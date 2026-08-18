---
card_id: construction-group-routing-v1-row-insertion-engine
status: frozen
version: 1
supersedes: null
work_id: construction-group-routing-v1
task_id: row-insertion-engine
purpose: Выполнить Windows-first native Excel insertion внутри принятого блока стройки с paired control, structural oracle, durable lease и hash-driven recovery.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
launch_status: planned
actual_model: pending
actual_reasoning_effort: pending
fallback_reason: null
card_path: knowledge/tasks/construction-group-routing-v1-row-insertion-engine.md
card_commit_sha: runtime-envelope
planning_parent_sha: 9a9201099ddf9dfffcc0e649af2200a8dd901299
base_sha: runtime-envelope
dependency_shas:
  - runtime-envelope
branch: codex/cgr-row-insertion-engine
branch_base_sha: runtime-envelope
write_scope:
  - rns_import_server/group_row_insertion.py
  - rns_import_server/excel_native.py
  - rns_import_server/workbook_structure.py
  - rns_import_server/workbook_mutation_manifest.py
  - rns_import_server/workbook.py
  - rns_import_server/data/construction_group_template.v1.xlsx
  - scripts/windows_excel_insert.ps1
  - tests/test_group_row_insertion.py
  - tests/test_excel_native_contract.py
  - tests/test_workbook_mutation_manifest.py
  - tests/test_workbook_group_publication.py
  - knowledge/tasks/construction-group-routing-v1-row-insertion-engine.md
forbidden_paths:
  - rns_import_server/construction_registry.py
  - rns_import_server/registry_storage.py
  - rns_import_server/workbook_operation_journal.py
  - rns_import_server/server.py
  - rns_import_server/app.py
  - rns_import_server/static
  - README.md
contract_versions:
  input: workbook-group-resolution-v1
  journal: workbook-operation-journal-v1
  output: native-group-row-insertion-v1
acceptance_commands:
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m pytest -q tests/test_group_row_insertion.py tests/test_excel_native_contract.py tests/test_workbook_mutation_manifest.py tests/test_workbook_group_publication.py tests/test_workbook_group_routing.py tests/test_workbook_operation_journal.py"
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m compileall -q rns_import_server scripts tests"
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' scripts/windows_end_to_end_smoke.py --self-test"
  - git diff --check
---

# Wave 2B — native structural insertion engine

## Required behavior

- Consume the accepted workbook-group plan and Wave-1 generic journal. Re-resolve target hash, registry generation, group/header identity and canonical RNS under the shared publication lock before any mutation.
- Fill a proven existing blank/preformatted row without structural shift. Otherwise insert exactly one physical row immediately before the next group header; never call `openpyxl.insert_rows()` and never create a continuation header.
- Windows v1 middle insertion requires installed desktop Microsoft Excel. Use a separate hidden COM instance on staged copies through `scripts/windows_excel_insert.ps1`; no-Excel/unsupported/timeout is a typed pre-publication failure and never switches to OpenPyXL/raw OOXML.
- Create paired control and candidate from the same verified pre-hash, pair nonce, adapter build/settings and one-workbook-at-a-time flow. Control receives no mutation; candidate uses native `Rows(k).Insert`, full recalculation and save.
- Before `Workbooks.Open`, durably prove exact Excel ownership with operation/owner nonce, adapter PID/start, Excel PID/HWND/start/build and nonce-matched lease ACK. Cleanup or termination may affect only the still-matching leased instance; a user Excel process or reused PID is never killed.
- Transfer only validated same-group format/validation/template data; write allowlisted A:X/AA fields; produce Y/Z from validated `FormulaR1C1`; add exactly one requested hyperlink; deterministically rebase visible A ordinals while preserving semantic identity.
- Validate original→control normalization separately from candidate→control insertion manifest. Prove mapped rows, formulas/dashboard totals, CF/x14/DV, merges, filter/defined names, hyperlinks and formula errors. Python opens staged outputs read-only and never saves them with OpenPyXL.
- Durable phases and hashes must support exact pre-hash re-resolution, exact post-hash finalization without reinsertion, and third-hash/manual-repair behavior. Backup, replace and independent capability/binding/history/report flags are idempotent by operation ID.
- Every COM/open/save/recalc/oracle/journal/backup/replace/cleanup failure preserves stage and cause/HRESULT/WinError in a typed recovery envelope. Never return empty/success/no-op after failure and never publish a candidate that failed the oracle.
- Do not change registry schema/journal implementation, server/static wiring, reports/history modules, user README, or any user source PDF/XLSX. The tracked template must be generated/sanitized project data only.

## Acceptance

- Cross-platform mocked contracts cover proven blank fill and native insertion before next headers 6, 10 and 104; source remains byte-exact on every pre-publication failure.
- No direct `openpyxl.insert_rows`; control accepts only proven Excel normalization/cache changes; candidate manifest proves exactly one insertion and expected allowlisted edits.
- Formula/dashboard, CF/x14/DV/filter/name/merge/hyperlink oracles pass, including stale unrelated cache normalization and no new formula errors.
- Hang/crash injection at before-open/open/insert/calc/save/post-hash/replace/finalization proves bounded cleanup, no user-Excel termination, no double insertion and typed manual repair for a third hash.
- Real Windows Excel gate remains blocking for native insertion: insert/recalculate/save/reopen without repair or compatibility dialog. Hosted no-Office validation proves the safe negative path.

## Handoff

Set card to `review`. Record requested vs actual route, immutable feature SHA, exact changed paths/commands/results, Windows evidence, remaining risk and proposed knowledge delta. Commit and push the feature branch. Do not merge, amend, rebase or force-push after handoff.
