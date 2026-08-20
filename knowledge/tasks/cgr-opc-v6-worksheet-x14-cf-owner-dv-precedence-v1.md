---
type: task
status: completed
work_id: cgr-opc-v6-worksheet-x14-cf-owner-dv-precedence-v1
tags: [task/implementation, feature/x14-cf-owner-topology, status/planned]
last_verified: 2026-08-20
updated: 2026-08-20
---

# X14 CF owner topology — DV extension precedence remediation

Exact accepted runtime base is `e40bdefab96a453d316b073c24d4ef723214faf6`. Rejected envelope/X1/corpus branches and the suspended tag-matrix branch are evidence only and must not enter ancestry. The accepted dependency's historical feature ancestry includes X1 commits; this exclusion prohibits no additional merge, cherry-pick, or reuse of rejected branch tips beyond that exact accepted dependency. Exclusive scope is exactly this card, `rns_import_server/opc_worksheet_x14_cf_owner_topology.py`, and `tests/test_opc_worksheet_x14_cf_owner_topology.py`. Fixture and all other tests/cards are frozen. No history rewrite; human-attributed non-force commit/push only.

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

## Completion evidence

Implemented 2026-08-21. The traversal now distinguishes the direct legal `x14:dataValidations` container and its direct `x14:dataValidation` member from arbitrary nested descendants. Only direct `xm:f` and `xm:sqref` value positions are carved; every other CF-owned unique tag remains validated at its entry event. Focused regressions cover adjacent CF/DV extensions, direct and nested illegal CF-owned tags, URI/parent precedence for nonexact DV URIs, before/after document order, and second-sheet atomic failure.

Validation completed before commit: focused topology suite (61 passed), specified related suite (444 passed), full suite (1196 passed; one existing OpenPyXL unknown-extension warning), compileall, and `git diff --check`.

P6 remediation: direct plural `x14:conditionalFormattings` siblings before and after legal direct `x14:dataValidations` now reach their existing parent validator under the exact DV URI, rather than being preempted by unsupported-URI registration. Both cases assert `invalid-x14-cf-parent` at the plural Clark tag.

Independent P6 review must reproduce the exact DV-sibling precedence and confirm all old APIs/errors/frozen blobs. This Gate makes no X14 envelope, formula, sqref, dxf, insertion, publication, UI, CrossOver, or native Excel claim.
