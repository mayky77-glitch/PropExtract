---
card_id: cgr-opc-v6-part-uri
status: review
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

## Implementation evidence

- Added typed raw, canonical and relative URI forms plus stable `OPCPartURIError` and collision tuples.
- Unreserved escapes normalize before lookup (`%77` equals `w`); encoded separators, controls, malformed escapes, non-NFC/format Unicode and unsafe path topology fail closed.
- P6 validation: focused URI suite `22 passed`; full suite `308 passed` with one existing OpenPyXL synthetic-x14 warning; `python3 -m compileall -q rns_import_server/opc_part_uri.py` and `git diff --check` passed.
- P6 remediation: raw `..` resolves even when another valid escape is present; only percent-decoded dot segments are rejected. Percent bytes reject only raw ASCII C0/DEL before UTF-8 decode, then decoded C1 remains a typed control failure (`%C2%80`); valid UTF-8 continuation bytes are accepted. Exact duplicate raw names now collide. Terminal directory targets (`.`, `..`, `a/.`, `a/..`) fail `invalid-part-uri` rather than resolving to a part.
