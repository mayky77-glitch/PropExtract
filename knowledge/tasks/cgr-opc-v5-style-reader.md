---
card_id: cgr-opc-v5-style-reader
status: frozen
version: 1
work_id: cgr-opc-semantic-reader-v5-20260818
task_id: style-table-semantic-reader-v1
purpose: Read complete used and unused OOXML style tables with recursive semantic fingerprints and strict indices.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: b41a73b4f823ac41c9996142a9ef37745ea3d7fb
dependency_shas: [b41a73b4f823ac41c9996142a9ef37745ea3d7fb]
branch: codex/cgr-style-table-semantic-reader-v1
card_path: knowledge/tasks/cgr-opc-v5-style-reader.md
write_scope: [rns_import_server/ooxml_style_reader.py, tests/test_ooxml_style_reader.py, knowledge/tasks/cgr-opc-v5-style-reader.md]
forbidden_paths: [rns_import_server/opc_workbook_reader.py, rns_import_server/opc_package_resolver.py, rns_import_server/ooxml_worksheet_reader.py, README.md]
contract_versions: {output: ooxml-style-table-model-v1}
acceptance_commands:
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m pytest -q tests/test_ooxml_style_reader.py"
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m compileall -q rns_import_server tests"
  - git diff --check
---

# Style table semantic reader v1

Expose all used and unused numFmt/font/fill/border/cellStyleXF/cellXF/dxf tables. Recursively canonicalize complete nested semantics including gradients, stops, colors, themes, tints, alignment and protection. Validate every unsigned/index/cross-table reference, duplicate and negative numFmt, component bounds and xf inheritance. Preserve deterministic unsupported findings; no one-level hashes, worksheet parsing, mutation, or rejected V4 reuse.

Tests mutate deep gradient stops/colors and unused entries, every cross-index, duplicates/negative ids, inheritance and namespace prefixes; positive assertions cover full tables. Set card review, test, normal human-authored commit/push; no merge/amend/rebase/force-push.
