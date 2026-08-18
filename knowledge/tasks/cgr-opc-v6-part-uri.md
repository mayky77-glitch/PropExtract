---
card_id: cgr-opc-v6-part-uri
status: frozen
version: 1
work_id: cgr-opc-package-resolver-v6-20260818
task_id: part-uri-canonicalizer-v1
purpose: Canonicalize OPC part and relative target URIs with typed collision evidence.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: b41a73b4f823ac41c9996142a9ef37745ea3d7fb
dependency_shas: [b41a73b4f823ac41c9996142a9ef37745ea3d7fb]
branch: codex/cgr-opc-part-uri-v1
card_path: knowledge/tasks/cgr-opc-v6-part-uri.md
write_scope: [rns_import_server/opc_part_uri.py, tests/test_opc_part_uri.py, knowledge/tasks/cgr-opc-v6-part-uri.md]
forbidden_paths: [rns_import_server/opc_package_resolver.py, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_opc_part_uri.py", "python3 -m compileall -q rns_import_server/opc_part_uri.py", "git diff --check"]
---

# OPC part URI canonicalizer v1

Return typed raw/canonical/relative forms. Normalize percent-encoded unreserved aliases before collision/lookup; reject encoded separators/traversal, package-root escape, raw/decoded C0/DEL/C1, slash/backslash misuse, malformed percent and ambiguous Unicode. Resolution is idempotent and source-relative. Tests assert exact collision/error tuples, Unicode, case behavior and all V5 residuals. No V5 ancestry/copy. Human commit/push; no merge/rebase/amend/force.
