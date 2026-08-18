---
card_id: cgr-excel-native-v3-lease-journal
status: review
version: 1
work_id: cgr-excel-native-v3-20260818
task_id: lease-journal-v3
purpose: Persist durable Excel/adapter ownership, structured failures and ACK-authorizing journal phase before native workbook open.
role: database-engineer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: b41a73b4f823ac41c9996142a9ef37745ea3d7fb
dependency_shas:
  - b41a73b4f823ac41c9996142a9ef37745ea3d7fb
branch: codex/cgr-lease-journal-v3
card_path: knowledge/tasks/cgr-excel-native-v3-lease-journal.md
write_scope:
  - rns_import_server/registry_storage.py
  - rns_import_server/workbook_operation_journal.py
  - tests/test_registry_storage.py
  - tests/test_workbook_operation_journal.py
  - knowledge/tasks/cgr-excel-native-v3-lease-journal.md
forbidden_paths:
  - rns_import_server/excel_native.py
  - rns_import_server/group_row_insertion.py
  - scripts/windows_excel_insert.ps1
  - README.md
contract_versions:
  input: workbook-operation-journal-v1
  output: excel-lease-journal-v3
acceptance_commands:
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m pytest -q tests/test_registry_storage.py tests/test_workbook_operation_journal.py"
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m compileall -q rns_import_server tests"
  - git diff --check
---

# Wave 1A — lease journal v3

- Persist adapter PID/image/start and Excel PID/HWND/image/start/build with operation/owner/pair nonce.
- Enforce durable `excel_launching → excel_owned` transition before ACK may be issued; lease update is exact-CAS/idempotent and invalid identities never become owned.
- Persist structured primary and cleanup failure stage/code/message/HRESULT/WinError without losing the original cause.
- Add transactional migration with verified backup/rollback, typed corrupt/newer behavior and restart-readable owned/failed state. Preserve existing journal consumers and schema history.
- Tests cover complete/partial lease, nonce mismatch, phase races, crash/rollback/reopen and structured diagnostic round trip.

## Implementation evidence

- Feature SHA: `b953f556553b7fdaa17c7615000eae3f43936c33`.
- Exact focused acceptance: `22 passed` — `tests/test_registry_storage.py tests/test_workbook_operation_journal.py`.
- Wider regression: `289 passed, 1 warning` (pre-existing OpenPyXL x14-extension warning); `compileall` and `git diff --check` pass.
- Verified immutable v2 seed rebuild remains byte-identical. Runtime copies migrate transactionally to schema v3 after copy; the verified `.pre-migration.bak` is the direct rollback artifact.

## Residual risk

- The journal only authorizes a nonce-bound ACK after `excel_owned`; the adapter/PowerShell consumers must call the new lease methods before opening a workbook. Their integration is intentionally outside this card's write scope.

## Recovery evidence

- Recovery SHA: `5bfc32c36f0d76a8503b9ea9e47107526bdd792a`.
- `excel_owned` now compares and predicates the previously durable adapter PID/image/start, updates Excel fields only, and treats raced exact replays as success while differing identity is a typed conflict.
- Cleanup failure diagnostics are write-once CAS evidence; exact races replay, differing races conflict. Failure envelopes require the exact complete typed stage/code/message/HRESULT/WinError shape.
- Seed manifests remain exact v2 release artifacts; runtime v3 is accepted only after copy-and-migrate.
- Recovery validation: focused `26 passed`; full `293 passed, 1 warning`; deterministic seed check, compileall, and diff check pass.
