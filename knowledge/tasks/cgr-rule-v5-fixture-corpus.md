---
card_id: cgr-rule-v5-fixture-corpus
status: frozen
version: 1
work_id: cgr-ooxml-rule-semantics-v5-20260818
task_id: rule-fixture-corpus-v1
purpose: Build an implementation-independent schema-sequenced CF/DV fixture and mutation corpus.
role: tester
route: P3
assigned_model: gpt-5.6-terra
reasoning_effort: medium
planning_parent_sha: b41a73b4f823ac41c9996142a9ef37745ea3d7fb
dependency_shas: [b41a73b4f823ac41c9996142a9ef37745ea3d7fb]
branch: codex/cgr-rule-fixture-corpus-v1
card_path: knowledge/tasks/cgr-rule-v5-fixture-corpus.md
write_scope: [tests/ooxml_rule_v5_fixture_corpus.py, tests/ooxml_rule_v5_schema_contract.py, tests/test_ooxml_rule_v5_fixture_corpus.py, tests/fixtures/ooxml-rule-v5, knowledge/tasks/cgr-rule-v5-fixture-corpus.md]
forbidden_paths: [rns_import_server, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_ooxml_rule_v5_fixture_corpus.py", "git diff --check"]
---

# Rule fixture corpus v1

No production imports. Build direct namespace-correct XML/OPC for Sheet1 and Dashboard at 6/10/104 with positive and one-field mutations for every native/x14 CF/DV field, zero groups, tri-state flags, xm:f 0..3 and embedded DXF ownership. Independent child-order schema tables cover worksheet/extLst/x14/formula/sqref; positive corpus must pass and intentionally reordered negative must fail. Verify ZIP/XML/namespaces/relationship ownership; well-formedness alone is insufficient. Card review, tests, human commit/push; no merge/rebase/amend/force.
