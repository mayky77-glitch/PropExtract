---
card_id: cgr-opc-v6-relationship-xml
status: review
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

Implemented strict parser API: `Relationship` immutable record,
`OPCRelationshipXMLError` with `as_tuple() -> (code, part, detail)`, and
`parse_relationship_xml(part, payload)`. Parser preserves XML child order,
uses XML 1.0 Fifth Edition Unicode NCName rules, defaults omitted `TargetMode`
to `Internal`, validates RFC 3986 URI syntax and mode-aware targets (External
accepts valid URI references), blocks only lexical DOCTYPE declarations before
parsing, and fails closed on malformed/schema/URI violations including owned
element tails.

Residual evidence: focused suite `51 passed`; full suite `337 passed` (one
existing openpyxl extension warning); `python3 -m compileall -q
rns_import_server/opc_relationship_xml.py` and `git diff --check` passed. No
V5 code reused.
