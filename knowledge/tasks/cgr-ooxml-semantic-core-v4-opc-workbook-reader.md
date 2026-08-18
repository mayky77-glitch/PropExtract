---
card_id: cgr-ooxml-semantic-core-v4-opc-workbook-reader
status: review
version: 1
work_id: cgr-ooxml-semantic-core-v4-20260818
task_id: opc-workbook-reader-v1
purpose: Build a namespace-aware typed OPC workbook reader without reusing rejected raw-OOXML code.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: b41a73b4f823ac41c9996142a9ef37745ea3d7fb
dependency_shas:
  - b41a73b4f823ac41c9996142a9ef37745ea3d7fb
branch: codex/cgr-opc-workbook-reader-v1
card_path: knowledge/tasks/cgr-ooxml-semantic-core-v4-opc-workbook-reader.md
write_scope:
  - rns_import_server/opc_workbook_reader.py
  - tests/opc_workbook_fixture_factory.py
  - tests/test_opc_workbook_reader.py
  - knowledge/tasks/cgr-ooxml-semantic-core-v4-opc-workbook-reader.md
forbidden_paths:
  - rns_import_server/ooxml_semantics.py
  - rns_import_server/ooxml_rule_reader.py
  - rns_import_server/a1_reference_parser.py
  - rns_import_server/group_row_insertion.py
  - README.md
contract_versions:
  output: opc-workbook-model-v1
acceptance_commands:
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m pytest -q tests/test_opc_workbook_reader.py"
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m compileall -q rns_import_server tests"
  - git diff --check
---

# Wave 1A — OPC workbook reader v1

- Parse namespace-aware content types, package relationships, workbook, workbook relationships and every sheet name/id/state to its actual target.
- Reject duplicate normalized parts, traversal, missing targets and malformed internal/external relationships.
- Model typed cells (coordinate/type/raw/shared/inline/error/formula/cache and shared/array attributes), row/column height/width/hidden/outline/style and worksheet dimension.
- Model number formats, fonts, fills, borders, cell XFs/alignment/protection and resolved cell style fingerprints.
- Model hyperlinks, merges, autoFilter and scoped/workbook defined names. Retain per-part digest as evidence only; return unsupported features as typed findings.
- Use namespace-valid synthetic OPC fixtures with materially different boundaries 6/10/104, at least two sheets, shared/inline/numeric/date-style/formula/cache/error cells, styles/dimensions, internal and relationship hyperlinks.
- Positive tests assert the complete typed model; mutations assert exact findings. Do not copy or merge `9d9ef680`, `725d3c28`, or their implementation.

Set card `review`, record immutable feature SHA/evidence/risk; normal commit/push only. No merge/amend/rebase/force-push.

## Implementation evidence

- Immutable feature SHA: `1535efb4ddfb47eafe86b3e0f5006228760e6b76`; direct descendant of exact base `3541fedb93058664a52a7c064822afcb70451083`.
- Added namespace-aware direct OPC reader and synthetic fixtures. Sheet targets resolve from relationships to `xl/worksheets/sheet6.xml` and `sheet104.xml`; semantic boundaries cover rows `6`, `10`, and `104` with two distinct sheets.
- Acceptance: focused `5 passed`; full suite `291 passed, 1 warning` (existing OpenPyXL synthetic-x14 warning); compileall and `git diff --check` pass.
- Residual risk: reader intentionally reports, rather than interprets, unsupported worksheet features such as conditional formatting; package digests remain evidence only.
