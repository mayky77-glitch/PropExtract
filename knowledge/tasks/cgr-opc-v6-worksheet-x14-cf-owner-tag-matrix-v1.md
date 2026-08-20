---
type: task
status: planned
work_id: cgr-opc-v6-worksheet-x14-cf-owner-tag-matrix-v1
tags: [task/test-corpus, feature/x14-cf-owner-topology, status/planned]
last_verified: 2026-08-20
updated: 2026-08-20
---

# X14/XM owner-tag matrix — frozen B-card

Exact base is `e40bdefab96a453d316b073c24d4ef723214faf6`. This card owns only the new `tests/test_opc_worksheet_x14_cf_owner_topology_tag_matrix.py` and this card. The reader blob `6eea77cdda6f08bc9902810f54cff332123bad87`, fixture factory `83a56ee4f6f7a00a92cc577eb279377f50aba912`, original test, and prior cards are frozen. Do not edit production, fixtures, APIs, deployment/runtime configuration, or any other path. No UI, bottle, native Excel, or semantic-insertion claim.

## Exact B corpus

Complete the six owned locals `conditionalFormattings`, `conditionalFormatting`, `cfRule`, `dxf`, `f`, and `sqref` across X14 and XM, each at worksheet-direct, arbitrary-wrapper, and every other frozen conditional-formatting owner depth. Include legal parent positives; wrong conditional-formatting URI and case; namespace wrong-case using `X14.upper` for X14 and `XM.upper` for XM; and foreign-namespace and empty-namespace variants for all six locals.

Cover the complete extension/formattings/container/cfRule text boundary and every child tail, including `conditionalFormatting` child-tail. Preserve the realistic legal direct-DV carve. Malformed or nested DV remains disabled; CF tags and CF siblings fail. Assert exact tier/document precedence and exact four-tuples. Do not use sets, skips, or unordered assertions.

The matrix must retain the frozen single-parse and ownership contract, exact field/descriptor behavior, and no-fallback/partial-success behavior. Do not infer semantics for payloads, formulas, dxfs, or ranges beyond the frozen reader contract.

## Acceptance and handoff

Run exactly:

`python3 -m pytest -q tests/test_opc_worksheet_x14_cf_owner_topology_tag_matrix.py`

`python3 -m pytest -q tests/test_opc_worksheet_x14_cf_owner_topology_tag_matrix.py tests/test_opc_worksheet_x14_cf_owner_topology.py tests/test_opc_workbook_topology.py tests/test_opc_worksheet_cell_reader.py tests/test_opc_worksheet_structure_reader.py tests/test_opc_worksheet_native_cf_reader.py`

`python3 -m pytest -q`

`python3 -m compileall -q tests/test_opc_worksheet_x14_cf_owner_topology_tag_matrix.py`

`git diff --check`

Verify the reader/fixture/original-test/card hashes, exact one-file scope, line count, identity, remote, and clean state. P6 reviews the combined tip. A non-force commit/push is required under the verified human identity `mayky77-glitch <274605240+mayky77-glitch@users.noreply.github.com>`; no AI attribution or force push. Stop and report a runtime defect; do not edit production. Any unclear precedence or namespace behavior requires an owner decision.
