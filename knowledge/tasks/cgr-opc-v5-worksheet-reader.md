---
card_id: cgr-opc-v5-worksheet-reader
status: frozen
version: 1
work_id: cgr-opc-semantic-reader-v5-20260818
task_id: worksheet-semantic-reader-v1
purpose: Read complete typed workbook and worksheet semantics from injected canonical parts and relationships.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: b41a73b4f823ac41c9996142a9ef37745ea3d7fb
dependency_shas: [b41a73b4f823ac41c9996142a9ef37745ea3d7fb]
branch: codex/cgr-worksheet-semantic-reader-v1
card_path: knowledge/tasks/cgr-opc-v5-worksheet-reader.md
write_scope: [rns_import_server/ooxml_worksheet_reader.py, tests/test_ooxml_worksheet_reader.py, knowledge/tasks/cgr-opc-v5-worksheet-reader.md]
forbidden_paths: [rns_import_server/opc_workbook_reader.py, rns_import_server/opc_package_resolver.py, rns_import_server/ooxml_style_reader.py, README.md]
contract_versions: {input: injected-opc-parts-rels-v1, output: worksheet-semantic-model-v1}
acceptance_commands:
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m pytest -q tests/test_ooxml_worksheet_reader.py"
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m compileall -q rns_import_server tests"
  - git diff --check
---

# Worksheet semantic reader v1

Consume injected canonical parts/relationships. Model sheets, rows/columns, cells, shared/inline/rich strings, cached/error values, normal/shared/array formulas and attributes, merges, dimensions, filters, hyperlinks and scoped/workbook names. Enforce coordinate/grid bounds; unsigned/index fields including shared-formula `si` and `localSheetId`; dangling/duplicate relations/names/shared formulas; hyperlink type/mode/ref invariants. Unsupported features are deterministic typed findings. No package discovery, style parsing, mutation, or rejected V4 reuse.

Tests use direct typed injected fixtures and exact models/errors for every semantic family, negative/out-of-range indices, dangling/duplicate/unsupported cases. Set card review, test, normal human-authored commit/push; no merge/amend/rebase/force-push.
