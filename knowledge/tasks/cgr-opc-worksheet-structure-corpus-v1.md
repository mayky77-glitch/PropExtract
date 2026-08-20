---
card_id: cgr-opc-worksheet-structure-corpus-v1
status: frozen
version: 1
work_id: cgr-opc-worksheet-structure-corpus-v1-20260820
task_id: cgr-opc-worksheet-structure-corpus-v1
purpose: Complete the exact adversarial corpus for the P6-accepted worksheet structure runtime without changing production.
role: tester
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: 4bd72e8bd7d261786e3fc19802a85837f6685085
dependency_shas: [4bd72e8bd7d261786e3fc19802a85837f6685085]
branch: codex/cgr-opc-worksheet-structure-corpus-v1
card_path: knowledge/tasks/cgr-opc-worksheet-structure-corpus-v1.md
write_scope: [tests/opc_worksheet_structure_fixture_factory.py, tests/test_opc_worksheet_structure_reader.py, knowledge/tasks/cgr-opc-worksheet-structure-corpus-v1.md]
forbidden_paths: [rns_import_server/opc_worksheet_structure_reader.py, rns_import_server/opc_worksheet_cell_reader.py, rns_import_server/opc_workbook_topology.py, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_opc_worksheet_structure_reader.py tests/test_opc_worksheet_cell_reader.py tests/test_opc_workbook_topology.py tests/test_opc_style_semantic_reader.py", "python3 -m pytest -q", "python3 -m compileall -q tests/opc_worksheet_structure_fixture_factory.py tests/test_opc_worksheet_structure_reader.py", "git diff --check"]
---

# OPC worksheet structure adversarial corpus v1

- Test-only completion from P6-accepted runtime `4bd72e8bd7d261786e3fc19802a85837f6685085`. Production blobs and public API must remain byte-identical.
- Freeze exact successful values/immutability/order for both worksheets: dimension, every row property with absence/false/zero distinctions, rows 6/10/104, ordered merges, optional filter, A1 and XFD1048576 boundaries.
- Freeze exact error tuples for all one-shot PathLike variants (raising `__fspath__`, non-string, bytes, NUL); missing/raw percent alias/canonical collision worksheet members; malformed XML with declaration, UTF-8 BOM, incompatible/unknown encoding, wrong root and wrong/empty namespace.
- Cover non-whitespace text and tails plus unknown attributes/children at worksheet, dimension, sheetData, row, autoFilter, mergeCells, and mergeCell owners. Cover foreign/empty namespace local-name collisions and invalid legal-parent depth for every owned tag.
- Cover complete A1 matrix: single/range, lowercase/absolute normalization, A1 and XFD1048576; empty, whole-row/whole-column, sheet/3D-qualified, reversed, zero/overflow row, beyond-XFD, malformed separators and normalized duplicates.
- Cover missing/malformed/mismatched merge count, reverse row-major order, duplicate merges, duplicate/out-of-order rows, every row numeric/boolean legal boundary and exact failure, second-sheet projections, and accepted topology/cell typed-error forwarding precedence.
- Every named row is an executable semantic assertion with exact tuple/value; no observational tests, timing gates, silent skips, or fallback behavior. Do not alter production, card API, README, PDF, or XLSX.
- Run every acceptance command; human identity commit/push only; no merge, rebase, amend, or force-push.
