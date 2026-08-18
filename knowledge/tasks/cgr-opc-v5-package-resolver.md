---
card_id: cgr-opc-v5-package-resolver
status: review
version: 1
work_id: cgr-opc-semantic-reader-v5-20260818
task_id: package-relationship-resolver-v1
purpose: Resolve OPC parts and relationships with strict typed URI and package-boundary validation.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: b41a73b4f823ac41c9996142a9ef37745ea3d7fb
dependency_shas: [b41a73b4f823ac41c9996142a9ef37745ea3d7fb]
branch: codex/cgr-package-relationship-resolver-v1
card_path: knowledge/tasks/cgr-opc-v5-package-resolver.md
write_scope: [rns_import_server/opc_package_resolver.py, tests/test_opc_package_resolver.py, knowledge/tasks/cgr-opc-v5-package-resolver.md]
forbidden_paths: [rns_import_server/opc_workbook_reader.py, rns_import_server/ooxml_worksheet_reader.py, rns_import_server/ooxml_style_reader.py, README.md]
contract_versions: {output: opc-package-resolver-v1}
acceptance_commands:
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m pytest -q tests/test_opc_package_resolver.py"
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m compileall -q rns_import_server tests"
  - git diff --check
---

# Package relationship resolver v1

Parse namespace-aware ContentTypes and every `.rels`; canonicalize part names and resolve internal targets against the source directory. Reject duplicate normalized parts, package-root escape, missing targets, invalid percent/control/backslash/URI syntax and malformed internal/external relationships with typed deterministic errors. External targets require a nonempty valid absolute URI and never become package parts. Preserve relationship type, mode, id and source. Do not reuse rejected V4 implementation.

## Implementation evidence

- Immutable feature SHA: `1a1640058ce4578efd25270b56b900032183c5e1`.
- Namespace-aware Content Types and every relationship part are parsed. Internal URI targets resolve relative to their source; valid contained `..` normalizes, package escape and encoded traversal reject deterministically.
- Tests cover aliases, missing targets, malformed XML, strict external URIs, malformed percent escapes and backslashes. Focused `9 passed`; full `295 passed, 1 existing synthetic-x14 warning`; compileall/diff pass.
- Risk: resolver intentionally validates package/URI semantics only; content-type application semantics remain downstream responsibility.

## P6 recovery evidence

- Immutable recovery feature SHA: `16b1f05077771c4ad981358d82c290d50528d4ea`.
- Relationship IDs require nonblank XML-ID spelling; relationship types require valid absolute URIs. Non-root relationship parts require an existing source part, and unexpected structural children/namespaces reject deterministically.
- URI parsing is centralized: URI parser/port failures are typed, external scheme payload and authority are validated, and decoded C0/DEL/C1, encoded separators and traversal reject.
- Focused `9 passed`; full `295 passed, 1 existing synthetic-x14 warning`; compileall and diff check pass. Residual scope remains semantic use of resolved package contents.

Tests must exercise valid contained `..`, escape, encoded traversal, backslash, controls, malformed percent, duplicate aliases, missing parts and external URI edge cases. Set card review, test, normal human-authored commit/push; no merge/amend/rebase/force-push.
