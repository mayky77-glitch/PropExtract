---
card_id: cgr-opc-v6-style-numfmt-oracle
status: frozen
version: 1
work_id: cgr-opc-style-numfmt-oracle-v1-20260820
task_id: opc-style-numfmt-oracle-v1
purpose: Add the missing exact NumberFormat value oracle to the accepted style-reader corpus.
role: tester
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: 227ffd49b61e11f7634e0c51777e3af50870b886
dependency_shas: [227ffd49b61e11f7634e0c51777e3af50870b886]
branch: codex/cgr-opc-style-numfmt-oracle-v1
card_path: knowledge/tasks/cgr-opc-v6-style-numfmt-oracle.md
write_scope: [tests/opc_style_fixture_factory.py, tests/test_opc_style_semantic_reader.py, knowledge/tasks/cgr-opc-v6-style-numfmt-oracle.md]
forbidden_paths: [rns_import_server/opc_style_semantic_reader.py, rns_import_server/opc_worksheet_cell_reader.py, rns_import_server/opc_workbook_topology.py, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_opc_style_semantic_reader.py tests/test_opc_worksheet_cell_reader.py tests/test_opc_workbook_topology.py", "python3 -m pytest -q", "python3 -m compileall -q tests/opc_style_fixture_factory.py tests/test_opc_style_semantic_reader.py", "git diff --check"]
---

# OPC style NumberFormat value oracle

- Test-only completion from exact style-reader recovery tip `227ffd49b61e11f7634e0c51777e3af50870b886`.
- Add one real native custom `<numFmt>` to the typed styles fixture. Its `numFmtId` and `formatCode` must be legal, non-empty, and referenced consistently where the fixture already models the style table.
- Replace the empty `number_formats` expectation with an exact recursive `asdict` value oracle for `NumberFormat(num_fmt_id, format_code)`. Assert both values, record ordering, immutability, and integration inside the complete public style-table oracle.
- Do not modify production code, public APIs, package relationship behavior, style parsing semantics, unrelated fixture cases, accepted OPC modules, README, PDFs, or XLSX files.
- Run every acceptance command. Human identity commit/push only; no merge, rebase, amend, or force-push.
