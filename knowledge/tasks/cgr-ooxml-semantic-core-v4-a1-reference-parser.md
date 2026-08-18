---
card_id: cgr-ooxml-semantic-core-v4-a1-reference-parser
status: review
version: 1
work_id: cgr-ooxml-semantic-core-v4-20260818
task_id: a1-reference-parser-v1
purpose: Parse and map A1 references structurally across insertion boundaries without partial rewrites.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: b41a73b4f823ac41c9996142a9ef37745ea3d7fb
dependency_shas:
  - b41a73b4f823ac41c9996142a9ef37745ea3d7fb
branch: codex/cgr-a1-reference-parser-v1
card_path: knowledge/tasks/cgr-ooxml-semantic-core-v4-a1-reference-parser.md
write_scope:
  - rns_import_server/a1_reference_parser.py
  - tests/a1_reference_cases.py
  - tests/test_a1_reference_parser.py
  - knowledge/tasks/cgr-ooxml-semantic-core-v4-a1-reference-parser.md
forbidden_paths:
  - rns_import_server/ooxml_semantics.py
  - rns_import_server/opc_workbook_reader.py
  - rns_import_server/ooxml_rule_reader.py
  - rns_import_server/group_row_insertion.py
  - README.md
contract_versions:
  output: a1-insertion-mapping-v1
acceptance_commands:
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m pytest -q tests/test_a1_reference_parser.py"
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m compileall -q rns_import_server tests"
  - git diff --check
---

# Wave 1C — A1 reference parser v1

- Implement a lexer/parser and immutable tokens/AST, not global regex substitution. Support cells, ranges and whole-row/whole-column ranges.
- Preserve `$` exactly. Support unquoted and quoted sheet names with escaped apostrophes. Local references use the host sheet; qualified references map only for the insertion target.
- Do not alter string literals, function names or ordinary defined names. Exact round-trip when no mapping applies.
- Mapping at insertion row `k`: above unchanged; cells/rows at or below shift +1; spanning ranges expand; wholly below ranges shift.
- Reject external workbook, 3D and structured/table references with typed `UnsupportedReference` before any partial rewrite.
- Cases cover materially distinct 6/10/104 boundaries, local/quoted cross-sheet references, relative/absolute/mixed anchors, whole rows/columns, strings/functions/names and exact unsupported cases.
- Do not copy or merge `9d9ef680`, `725d3c28`, or their implementation.

## Implementation evidence

- Feature SHA: `3f586c22f29fc55792c19b38f2b8063e095c5bee`.
- Immutable lexer/AST tokens preserve exact source bytes when no map applies. Mapping covers cell/range/whole-row/whole-column boundaries at 6, 10 and 104, anchors, host sheet and quoted/unquoted target sheet semantics.
- External workbook, 3D and structured/table forms raise typed `UnsupportedReference` during parsing before any mapped formula is rendered; strings are opaque.
- Validation: focused `13 passed`; full `299 passed, 1 warning` (existing OpenPyXL x14 warning); compileall and `git diff --check` pass.

## Residual risk

- This v1 contract intentionally rejects reference dialects outside A1. Later OOXML integration must surface that typed unsupported state rather than attempting a text fallback.
