---
card_id: cgr-structural-oracle-core-v3-raw-ooxml-semantics
status: frozen
version: 1
work_id: cgr-structural-oracle-core-v3-20260818
task_id: raw-ooxml-semantics-v1
purpose: Build a lossless read-only OPC/OOXML semantic inventory and insertion-aware mapping core independent of publication.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: b41a73b4f823ac41c9996142a9ef37745ea3d7fb
dependency_shas:
  - b41a73b4f823ac41c9996142a9ef37745ea3d7fb
branch: codex/cgr-raw-ooxml-semantics-v1
card_path: knowledge/tasks/cgr-structural-oracle-core-v3-raw-ooxml-semantics.md
write_scope:
  - rns_import_server/ooxml_semantics.py
  - tests/ooxml_fixture_factory.py
  - tests/test_ooxml_semantics.py
  - knowledge/tasks/cgr-structural-oracle-core-v3-raw-ooxml-semantics.md
forbidden_paths:
  - rns_import_server/workbook_mutation_manifest.py
  - rns_import_server/group_row_insertion.py
  - rns_import_server/workbook.py
  - rns_import_server/excel_native.py
  - README.md
contract_versions:
  input: opc-ooxml-package-v1
  output: raw-ooxml-semantics-v1
acceptance_commands:
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m pytest -q tests/test_ooxml_semantics.py"
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m compileall -q rns_import_server tests"
  - git diff --check
---

# Work1 — raw OOXML semantics v1

- Inventory every OPC part and relationship with deterministic digests; resolve workbook sheets and their relationships without OpenPyXL saves.
- Parse all sheet cells with raw type/value/formula/cache/error evidence, semantic style and number-format definitions, hyperlinks/relationships, merges, dimensions and filters.
- Parse defined names with exact definitions/ranges, native and x14 conditional formatting/data validation including rules, formulas, priorities, dxf and sqref.
- Provide deterministic insertion-aware cell/range mapping across every sheet and related workbook references. Preserve quoted sheet names and absolute/relative coordinates.
- Fail closed on external references, 3D references and structured/table references until an explicit later contract supports them.
- Fixtures are generated sanitized OPC packages. Tests cover all parts/sheets/relationships, rule/name/style/error corruption, x14, legitimate mapped shifts and fail-closed unsupported references at real boundaries 6, 10 and 104.
- This task exports semantics only. It must not change current manifest/publication behavior or touch user PDF/XLSX files.

Set card `review`, record immutable SHA/evidence/limitations; normal commit/push only. No merge/amend/rebase/force-push.
