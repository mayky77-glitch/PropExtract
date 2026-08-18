---
card_id: cgr-opc-v6-relationship-xml
status: frozen
version: 1
work_id: cgr-opc-package-resolver-v6-20260818
task_id: relationship-record-parser-v1
purpose: Parse relationship XML records with exact namespace, XML ID and URI invariants.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: b41a73b4f823ac41c9996142a9ef37745ea3d7fb
dependency_shas: [b41a73b4f823ac41c9996142a9ef37745ea3d7fb]
branch: codex/cgr-opc-relationship-xml-v1
card_path: knowledge/tasks/cgr-opc-v6-relationship-xml.md
write_scope: [rns_import_server/opc_relationship_xml.py, tests/test_opc_relationship_xml.py, knowledge/tasks/cgr-opc-v6-relationship-xml.md]
forbidden_paths: [rns_import_server/opc_package_resolver.py, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_opc_relationship_xml.py", "python3 -m compileall -q rns_import_server/opc_relationship_xml.py", "git diff --check"]
---

# Relationship XML parser v1

Require exact namespace/children and deterministic order; validate Unicode XML 1.0 NCName IDs, unique IDs, absolute valid Type URI with no fragment, exact TargetMode and required attrs. Return typed records/errors with exact `(code,part,detail)`; reject malformed/wrong namespace/unknown attrs/children. Tests cover Unicode IDs, URI parser edges, fragments, modes and stable order. No V5 reuse. Human commit/push; no merge/rebase/amend/force.
