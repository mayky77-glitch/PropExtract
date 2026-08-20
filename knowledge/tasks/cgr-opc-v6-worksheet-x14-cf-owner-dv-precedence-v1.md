---
type: task
status: planned
work_id: cgr-opc-v6-worksheet-x14-cf-owner-dv-precedence-v1
tags: [task/implementation, feature/x14-cf-owner-topology, status/planned]
last_verified: 2026-08-20
updated: 2026-08-20
---

# X14 CF owner topology — DV extension precedence remediation

Exact accepted runtime base is `e40bdefab96a453d316b073c24d4ef723214faf6`. Rejected envelope/X1/corpus branches and the suspended tag-matrix branch are evidence only and must not enter ancestry. Exclusive scope is exactly this card, `rns_import_server/opc_worksheet_x14_cf_owner_topology.py`, and `tests/test_opc_worksheet_x14_cf_owner_topology.py`. Fixture and all other tests/cards are frozen. No history rewrite; human-attributed non-force commit/push only.

## Single runtime contract

The exact direct SML `ext` URI `{CCE6A557-97BC-4b89-ADB6-D9C93CAAB3DF}` is a known valid X14 data-validation extension, not an unsupported CF extension. Its exact legal X14 `dataValidations` subtree carves out only the already frozen XM `f`/`sqref` descendants. This carve never hides CF ownership.

Any X14/XM CF-owned unique tag (`conditionalFormattings`, `conditionalFormatting`, `cfRule`, `dxf`, `f`, `sqref`) placed as a direct child or descendant inside that exact DV extension outside the proved legal DV value positions remains traversed in document order and fails at its own element with exact `invalid-x14-cf-parent(part, 'tag', expanded_qname)`. A CF-looking sibling beside `dataValidations` therefore fails by its tag, not by `unsupported-x14-cf-extension-uri` for the otherwise valid DV URI.

Wrong-case, unknown, blank, or malformed extension URI does not activate the DV carve and preserves the existing URI/parent precedence and exact tuples. Malformed or wrong-parent DV structures do not activate a broad skip. Valid sibling CF and DV extensions remain accepted: only the CF extension contributes owner topology; the DV subtree remains unclaimed. Preserve one `ET.fromstring` per worksheet, one complete event-ordered traversal, tier/document precedence, all public records and errors, opaque lower rule/formula/dxf semantics, topology identity, canonical-member behavior, workbook-wide atomic publication, and no fallback/partial success.

## Focused evidence

Add exact regressions for: valid adjacent CF and DV extensions returning only CF owners; exact DV extension with legal `dataValidations` plus direct CF-owned sibling; CF-owned descendants at representative nested DV depths; CF-owned tag before and after legal DV descendants to prove document order; exact legal XM carve still accepted; wrong-case/unknown/blank URI retaining existing URI/parent precedence; malformed/wrong-parent DV structure not broad-skipped; valid first worksheet plus invalid second worksheet returning only the exact second-part error and no partial result. Every negative asserts the full four-field tuple.

Acceptance commands:

`python3 -m pytest -q tests/test_opc_worksheet_x14_cf_owner_topology.py`

`python3 -m pytest -q tests/test_opc_worksheet_x14_cf_owner_topology.py tests/test_opc_workbook_topology.py tests/test_opc_worksheet_cell_reader.py tests/test_opc_worksheet_structure_reader.py tests/test_opc_worksheet_native_cf_reader.py`

`python3 -m pytest -q`

`python3 -m compileall -q rns_import_server/opc_worksheet_x14_cf_owner_topology.py tests/test_opc_worksheet_x14_cf_owner_topology.py`

`git diff --check`

Independent P6 review must reproduce the exact DV-sibling precedence and confirm all old APIs/errors/frozen blobs. This Gate makes no X14 envelope, formula, sqref, dxf, insertion, publication, UI, CrossOver, or native Excel claim.
