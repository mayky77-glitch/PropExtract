---
card_id: cgr-real-corpus-locator-v1
status: frozen
version: 2
supersedes: null
work_id: cgr-real-corpus-locator-v1
task_id: real-corpus-locator
purpose: "Replace stale absolute real-XLSX test paths with one explicit hash-bound read-only corpus locator."
role: tester
card_path: knowledge/tasks/cgr-real-corpus-locator-v1.md
dependency_shas:
  - e5f8dec41c0c00f8ce8c6e717a8db4163b8a7154
branch: codex/cgr-real-corpus-locator-v1
write_scope:
  - knowledge/tasks/cgr-real-corpus-locator-v1.md
  - tests/real_rns_corpus.py
  - tests/test_opc_workbook_filter_database_insertion_oracle.py
  - tests/test_opc_worksheet_structure_insertion_oracle.py
  - tests/test_opc_worksheet_structure_reader.py
  - tests/test_opc_package_graph.py
  - tests/test_opc_worksheet_x14_cf_insertion_oracle.py
  - tests/test_opc_worksheet_x14_cf_owner_dv_formula_wrappers.py
forbidden_paths:
  - rns_import_server
  - scripts
  - README.md
contract_versions:
  input: publication-cutover-recovery-k3a-v1
  output: real-rns-corpus-locator-v1
acceptance_commands:
  - RNS_REAL_CORPUS_PATH='/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/Автоматизация РнС и ГРО/Реестр РНС Иркутск.xlsx' PYTHONPATH=. python3 -m pytest -q tests/test_opc_workbook_filter_database_insertion_oracle.py tests/test_opc_worksheet_structure_insertion_oracle.py tests/test_opc_worksheet_structure_reader.py tests/test_opc_package_graph.py tests/test_opc_worksheet_x14_cf_insertion_oracle.py tests/test_opc_worksheet_x14_cf_owner_dv_formula_wrappers.py
  - RNS_REAL_CORPUS_PATH='/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/Автоматизация РнС и ГРО/Реестр РНС Иркутск.xlsx' PYTHONPATH=. python3 -m pytest -q
  - python3 -m compileall -q tests/real_rns_corpus.py tests/test_opc_workbook_filter_database_insertion_oracle.py tests/test_opc_worksheet_structure_insertion_oracle.py tests/test_opc_worksheet_structure_reader.py tests/test_opc_package_graph.py tests/test_opc_worksheet_x14_cf_insertion_oracle.py tests/test_opc_worksheet_x14_cf_owner_dv_formula_wrappers.py
  - git diff --check
knowledge_paths:
  - knowledge/INDEX.md
  - knowledge/tasks/cgr-real-corpus-locator-v1.md
  - knowledge/tasks/implement-construction-group-routing-20260820.md
---

# Real RNS corpus locator v1

## Frozen contract

- Add one test-only `real_rns_corpus_path()` locator. It accepts only the explicit environment variable `RNS_REAL_CORPUS_PATH` containing an absolute regular-file path whose SHA-256 is exactly `2a1786d5836e4c3144107704f281bc9513fcd8de97937499268dc806c1106dd1`.
- Unset, relative, missing, non-file, symlink or hash-mismatched input fails explicitly. There is no repository traversal, default path, copy, symlink creation, skip or fallback.
- Replace only the six stale inline `parents[4]`/`SOURCE` locators. Existing read-only before/after source-hash assertions and test semantics remain unchanged.
- Production code, XLSX bytes, UI, publication behavior and test breadth are frozen. This Gate only repairs deterministic access to the existing private read-only corpus.

## Minimal evidence

- Without the environment variable, the helper fails with one stable diagnostic; it never searches the filesystem.
- The focused six-file suite changes from exactly 12 stale-path failures to green with the exact corpus path.
- The full suite runs with the same explicit variable and has no corpus-path failures. Source SHA remains exact before and after.
