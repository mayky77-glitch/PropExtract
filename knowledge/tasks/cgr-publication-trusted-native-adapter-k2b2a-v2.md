---
card_id: cgr-publication-trusted-native-adapter-k2b2a-v2
status: frozen
version: 1
supersedes: cgr-publication-runner-capability-k2b2a-v1
work_id: cgr-publication-trusted-native-adapter-k2b2a-v2
task_id: trusted-native-adapter
purpose: Remove the injectable in-process native runner and harden lease scalars before live Excel handshake work.
role: developer
card_path: knowledge/tasks/cgr-publication-trusted-native-adapter-k2b2a-v2.md
dependency_shas:
  - 3cbbb1d6bbdf3dc90a7e4f01e44e11f3daad46d4
branch: codex/cgr-publication-trusted-native-adapter-k2b2a-v2
write_scope:
  - rns_import_server/excel_process_authority.py
  - rns_import_server/group_row_insertion.py
  - tests/test_excel_process_authority.py
  - tests/test_group_row_insertion.py
  - knowledge/tasks/cgr-publication-trusted-native-adapter-k2b2a-v2.md
forbidden_paths:
  - rns_import_server/excel_native.py
  - rns_import_server/excel_process_cleanup.py
  - rns_import_server/workbook_operation_journal.py
  - rns_import_server/registry_storage.py
  - rns_import_server/windows_excel_insert.ps1
  - rns_import_server/server.py
  - rns_import_server/static
contract_versions:
  input: publication-kernel-k2b1
  output: trusted-native-adapter-k2b2a-v2
acceptance_commands:
  - PYTHONPATH=. python3 -m pytest -q tests/test_excel_process_authority.py tests/test_group_row_insertion.py
  - PYTHONPATH=. python3 -m pytest -q
  - python3 -m compileall -q rns_import_server/excel_process_authority.py rns_import_server/group_row_insertion.py tests/test_excel_process_authority.py tests/test_group_row_insertion.py
  - git diff --check
---

# Trusted native adapter K2B2a-v2

## Contract

- `PublicationContext` exposes no native runner, callback, capability, request factory, or other caller-controlled execution seam.
- Production `publish_group_row` calls the imported trusted `run_native_insert` adapter directly. Tests may monkeypatch that module symbol only as harness machinery; monkeypatching is arbitrary code execution and is not represented as a product security boundary.
- No object available through `PublicationContext` before native launch contains or can return `NativeInsertRequest`, workbook paths, row fields, or hyperlink values.
- Every `ExcelProcessLease` string scalar must be an exact built-in `str`, nonempty where required, before any equality or timestamp parsing. `str` subclasses, mappings, proxy values, re-entrant equality, booleans as integers, and malformed process identities fail with existing typed authority codes.
- Existing accepted K2B1 lease, journal, schema and migration behavior remains unchanged. This Gate does not implement stdin permission/cancel, process cleanup, bounded logs, K3 recovery/finalizers, UI, or server wiring.
- No OpenPyXL, LibreOffice, raw-OOXML, silent skip, or partial publication fallback. No native Excel success claim.

## Minimal evidence

- Public dataclass field order proves `native_runner` is absent.
- A caller-supplied callable cannot be passed through the context or invoked by publication; the sole native call is the trusted module function and receives the exact request only after normal pre-open checks.
- Exact built-in scalar matrix rejects `str` subclasses without invoking attacker-defined comparison; repeated/concurrent tests prove a single native call and unchanged journal behavior.
- Existing K2B1 authority, replay, mode, manifest and validation tests stay green. Full suite has zero product failures.
