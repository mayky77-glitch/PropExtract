---
card_id: cgr-opc-v6-corpus
status: review
version: 1
work_id: cgr-opc-package-resolver-v6-20260818
task_id: package-v6-corpus-v1
purpose: Build an independent OPC URI and relationship mutation corpus.
role: tester
route: P3
assigned_model: gpt-5.6-terra
reasoning_effort: medium
planning_parent_sha: b41a73b4f823ac41c9996142a9ef37745ea3d7fb
dependency_shas: [b41a73b4f823ac41c9996142a9ef37745ea3d7fb]
branch: codex/cgr-opc-package-v6-corpus-v1
card_path: knowledge/tasks/cgr-opc-v6-corpus.md
write_scope: [tests/opc_package_v6_corpus.py, tests/test_opc_package_v6_corpus.py, tests/fixtures/opc-package-v6, knowledge/tasks/cgr-opc-v6-corpus.md]
forbidden_paths: [rns_import_server, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_opc_package_v6_corpus.py", "git diff --check"]
---

# OPC package V6 corpus v1

No production imports. Direct ZIP/XML fixtures enumerate valid and one-field-invalid part/target/Type/ID/source/mode/namespace cases, percent aliases, Unicode, controls, traversal and ordered multiple errors. Assert exact ordered mutation tuples and independently validate package structure. No V5 fixture reuse. Human commit/push; no merge/rebase/amend/force.

## Review evidence

- Added an implementation-independent, standard-library ZIP/XML corpus: 13 direct package cases and exact ordered mutation tuples (including the two-relationship ordered-error boundary).
- `tests/test_opc_package_v6_corpus.py` independently opens each ZIP, checks archive integrity/member uniqueness/XML roots and validates static V6-only XML fixture roots. It imports no `rns_import_server` module.
- Passed `python3 -m pytest -q tests/test_opc_package_v6_corpus.py`: `27 passed in 0.03s`.
- Passed `python3 -m pytest -q`: `313 passed, 1 warning in 8.41s`; existing OpenPyXL warning: unknown extension is not supported and will be removed.
- Passed `git diff --check`.
