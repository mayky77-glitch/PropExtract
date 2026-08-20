---
type: task
status: completed
work_id: cgr-opc-v6-worksheet-x14-cf-owner-tag-matrix-v1
tags: [task/test-corpus, feature/x14-cf-owner-topology, status/completed]
last_verified: 2026-08-20
updated: 2026-08-20
---

# X14/XM owner-tag matrix — frozen B-card

Exact base is `e40bdefab96a453d316b073c24d4ef723214faf6`. This card owns only `tests/test_opc_worksheet_x14_cf_owner_topology_tag_matrix.py` and this card. The reader blob `6eea77cdda6f08bc9902810f54cff332123bad87`, fixture factory `83a56ee4f6f7a00a92cc577eb279377f50aba912`, original test, and prior cards are frozen. No production, fixture, API, deployment/runtime configuration, or other path changes are permitted.

## Completed corpus

The independent matrix covers each owned X14/XM local (`conditionalFormattings`, `conditionalFormatting`, `cfRule`, `dxf`, `f`, and `sqref`) at its legal parent and at worksheet-direct, arbitrary-wrapper, and every other conditional-formatting owner depth. It asserts the exact four-tuple for all negative cases, including wrong CF extension URI/case and X14/XM wrong-case, foreign, and empty namespace collisions.

It preserves the direct legal data-validation carve while proving a CF tag within that carve still fails. It covers nonwhite text and every direct-child tail at the CF extension, `conditionalFormattings`, `conditionalFormatting`, and `cfRule` boundaries; proves tier/document precedence; retains one XML parse per worksheet; and freezes a two-sheet rows 6/10/104 immutable projection.

## Validation

Run the exact focused, compatibility, full-suite, compile, and diff commands in the acceptance section below. Verify the frozen reader and fixture hashes, human identity, remote, exact two-file scope, and clean state before a non-force human-attributed commit/push. No AI attribution or force push is allowed.

## Acceptance and handoff

`python3 -m pytest -q tests/test_opc_worksheet_x14_cf_owner_topology_tag_matrix.py`

`python3 -m pytest -q tests/test_opc_worksheet_x14_cf_owner_topology_tag_matrix.py tests/test_opc_worksheet_x14_cf_owner_topology.py tests/test_opc_workbook_topology.py tests/test_opc_worksheet_cell_reader.py tests/test_opc_worksheet_structure_reader.py tests/test_opc_worksheet_native_cf_reader.py`

`python3 -m pytest -q`

`python3 -m compileall -q tests/test_opc_worksheet_x14_cf_owner_topology_tag_matrix.py`

`git diff --check`
