---
card_id: cgr-opc-v6-corpus
status: frozen
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
