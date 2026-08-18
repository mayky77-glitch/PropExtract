---
card_id: cgr-opc-v5-fixture-corpus
status: frozen
version: 1
work_id: cgr-opc-semantic-reader-v5-20260818
task_id: ooxml-v5-fixture-corpus-v1
purpose: Build an implementation-independent direct-OPC semantic fixture corpus for boundaries 6, 10 and 104.
role: tester
route: P3
assigned_model: gpt-5.6-terra
reasoning_effort: medium
planning_parent_sha: b41a73b4f823ac41c9996142a9ef37745ea3d7fb
dependency_shas: [b41a73b4f823ac41c9996142a9ef37745ea3d7fb]
branch: codex/cgr-ooxml-v5-fixture-corpus-v1
card_path: knowledge/tasks/cgr-opc-v5-fixture-corpus.md
write_scope: [tests/ooxml_v5_fixture_corpus.py, tests/test_ooxml_v5_fixture_corpus.py, tests/fixtures/ooxml_v5, knowledge/tasks/cgr-opc-v5-fixture-corpus.md]
forbidden_paths: [rns_import_server, README.md]
contract_versions: {output: ooxml-v5-fixture-corpus-v1}
acceptance_commands:
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m pytest -q tests/test_ooxml_v5_fixture_corpus.py"
  - git diff --check
---

# OOXML V5 fixture corpus v1

Create namespace-valid direct OPC packages without production imports. For each boundary 6/10/104, original/control/candidate packages must be byte- and semantic-distinct and coherently shift rows, cells, formulas/caches/errors, merges, filters, hyperlinks, names, row/column dimensions, styles, native+x14 CF/DV and dashboard cross-sheet formulas. Include valid and one-dimension-invalid mutations for every semantic family. Tests assert package validity, distinctness and exact expected manifest, never truthiness/count-only. No product code or rejected fixture reuse.

Set card review, test, normal human-authored commit/push; no merge/amend/rebase/force-push.
