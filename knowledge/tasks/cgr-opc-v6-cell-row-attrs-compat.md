---
card_id: cgr-opc-v6-cell-row-attrs-compat
status: frozen
version: 1
work_id: cgr-opc-cell-row-attrs-compat-v1-20260820
task_id: cgr-opc-cell-row-attrs-compat-v1
purpose: Accept and validate native worksheet row formatting attributes at the cell-reader boundary without changing its projection API.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: f1e82690564bb0104b9069c9bf0a5d9b8d7d692d
dependency_shas: [ce864f484fd8e89cbcaa9aa805dbc336e7f94b25]
branch: codex/cgr-opc-cell-row-attrs-compat-v1
card_path: knowledge/tasks/cgr-opc-v6-cell-row-attrs-compat.md
write_scope: [rns_import_server/opc_worksheet_cell_reader.py, tests/test_opc_worksheet_cell_reader.py, knowledge/tasks/cgr-opc-v6-cell-row-attrs-compat.md]
forbidden_paths: [rns_import_server/opc_worksheet_structure_reader.py, tests/opc_worksheet_structure_fixture_factory.py, tests/test_opc_worksheet_structure_reader.py, rns_import_server/opc_style_semantic_reader.py, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_opc_worksheet_cell_reader.py tests/test_opc_style_semantic_reader.py tests/test_opc_workbook_topology.py", "python3 -m pytest -q", "python3 -m compileall -q rns_import_server/opc_worksheet_cell_reader.py tests/test_opc_worksheet_cell_reader.py", "git diff --check"]
---

# OPC cell-reader native row-attribute compatibility

- Preserve the accepted immutable cell/formula/hyperlink public API and every existing exact error. This Gate only expands strict validation of standard native `<row>` attributes needed by the downstream structure reader.
- Continue owning `r` and `spans`. Additionally accept and validate: `ht` as finite non-negative native row height; `s` as bounded UInt32; `customHeight`, `customFormat`, `hidden`, and `collapsed` as exact XML booleans; `outlineLevel` as bounded UInt8 with Excel domain 0..7.
- These added fields are validate-and-ignore at this boundary: do not expose, normalize, default, invert, or silently coerce them. The separate structure reader owns their immutable semantic records.
- Apply XML-whitespace and integer/boolean lexical rules consistently with accepted readers. Bound lexical length before numeric conversion; reject NaN/infinity, negative/out-of-range values, malformed booleans, duplicates, namespace-confused attributes, and every still-unknown row attribute with stable exact `OPCWorksheetCellReaderError` tuples.
- Positive tests combine all fields on native rows 6, 10, and 104 and prove cell/formula/hyperlink output is byte-for-value unchanged. Negative tests cover every field's malformed/range/long lexical boundary and exact error precedence before cell projection.
- No structure-reader implementation, styles, package graph/topology, mutation, CF/DV/X14, README, PDF, or XLSX edits. Run every acceptance command; human identity commit/push only; no merge, rebase, amend, or force-push.

## Implementation evidence

- Native row `ht`, `s`, `customHeight`, `customFormat`, `hidden`, `outlineLevel`, and `collapsed` are accepted only after bounded strict validation and remain absent from immutable cell-reader output.
- The cell/formula/hyperlink projection is equal with or without valid native row properties at rows 6, 10, and 104.
- Negative coverage freezes malformed, range, long-lexical, namespace-confused, and duplicate-attribute failures before cell projection.
