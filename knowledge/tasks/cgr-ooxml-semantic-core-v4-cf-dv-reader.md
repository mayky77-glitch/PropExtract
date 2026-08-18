---
card_id: cgr-ooxml-semantic-core-v4-cf-dv-reader
status: review
version: 1
work_id: cgr-ooxml-semantic-core-v4-20260818
task_id: cf-dv-reader-v1
purpose: Parse native and x14 conditional-formatting and data-validation rules into typed semantics.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: b41a73b4f823ac41c9996142a9ef37745ea3d7fb
dependency_shas:
  - b41a73b4f823ac41c9996142a9ef37745ea3d7fb
branch: codex/cgr-cf-dv-reader-v1
card_path: knowledge/tasks/cgr-ooxml-semantic-core-v4-cf-dv-reader.md
write_scope:
  - rns_import_server/ooxml_rule_reader.py
  - tests/ooxml_rule_fixture_factory.py
  - tests/test_ooxml_rule_reader.py
  - knowledge/tasks/cgr-ooxml-semantic-core-v4-cf-dv-reader.md
forbidden_paths:
  - rns_import_server/ooxml_semantics.py
  - rns_import_server/opc_workbook_reader.py
  - rns_import_server/a1_reference_parser.py
  - rns_import_server/group_row_insertion.py
  - README.md
contract_versions:
  input: explicit-worksheet-part-map-v1
  output: ooxml-rule-model-v1
acceptance_commands:
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m pytest -q tests/test_ooxml_rule_reader.py"
  - "'/Users/x/Documents/ChatGPT/Отдел организации работ с недвижимым имуществом/.venv/bin/python' -m compileall -q rns_import_server tests"
  - git diff --check
---

# Wave 1B — CF/DV reader v1

- Consume an explicit worksheet-part map; never rediscover sheets by filenames.
- Model native CF sqref/type/priority/stopIfTrue/operator/formulas/dxfId/all attributes; model x14 IDs/priorities/formulas/dxf linkage and `xm:sqref`.
- Model native and x14 DV sqref/type/operator/allowBlank/error/input flags/formula1/formula2 and x14/xm range/formula forms.
- Split multiple disjoint sqref tokens while retaining rule order/priority. Preserve canonical dxf XML/reference and unknown attributes/children as typed unsupported findings; never replace full semantics with a hash.
- Use namespace-valid fixtures with distinct 6/10/104 ranges, native+x14 CF/DV, multiple disjoint ranges/formulas/priorities. Positive tests assert complete typed models; each semantic mutation asserts its exact field/finding.
- Do not copy or merge `9d9ef680`, `725d3c28`, or their implementation.

Set card `review`, record immutable feature SHA/evidence/risk; normal commit/push only. No merge/amend/rebase/force-push.

## Implementation evidence

- Immutable feature SHA: `791d537acab3631e590f430593a3ecad1aaabc9f`; direct descendant of exact base `3541fedb93058664a52a7c064822afcb70451083`.
- Reader consumes only the explicit caller-provided worksheet part map. It preserves supplied map order and does not infer part paths.
- Native and x14 CF/DV rules flatten each disjoint `sqref` token while retaining source, original range, rule order, priority, formulas, DXF references and complete attributes. Unknown attributes/children produce typed ordered findings with canonical XML for child evidence.
- Namespace-valid two-sheet fixture maps differ semantically at `6`, `10`, and `104`. Acceptance: focused `7 passed`; full `293 passed, 1 existing synthetic-x14 warning`; compileall and diff check pass.
- Risk: DXF references are semantic IDs from worksheet rules; resolving them against a styles part remains a later explicit-input contract.
