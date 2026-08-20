---
type: task
status: planned
work_id: cgr-opc-v6-worksheet-x14-cf-rule-mixed-content-v1
tags: [task/implementation, feature/x14-cf-owner-topology, status/planned]
last_verified: 2026-08-20
updated: 2026-08-20
---

# X14 CF rule mixed-content remediation — frozen card

Exact base: `11f11630491ae6d2be6dd2fe4fb9edea660b3172` (runtime `9a40ac2` plus corpus planning card; no corpus test diff). Exclusive implementation scope is exactly `rns_import_server/opc_worksheet_x14_cf_owner_topology.py`, `tests/test_opc_worksheet_x14_cf_owner_topology.py`, and this card. Fixture blob `83a56ee4f6f7a00a92cc577eb279377f50aba912` is frozen; X1 and corpus cards are frozen. No edits outside the three owned paths; a validated non-force human-attributed feature commit/push is required.

## Single contract

X14 `cfRule` is an owned mixed-content wrapper for structure only. Nonwhite direct `cfRule` text returns exact `OPCWorksheetX14CfOwnerTopologyError` tuple: `('invalid-x14-cf-content', worksheet_part, 'cfRule', 'text')`. Nonwhite tail of every direct `cfRule` child, including XM `f` and X14 `dxf`, returns the same tuple with detail `tail`. XML-whitespace-only text/tails are allowed.

Preserve event/document precedence: earlier tier-1 faults beat tier-2 faults; within tier 2, a child tail occurs after that child subtree; first document-order fault wins. Preserve all API, ownership topology, DV carve, one ET parse, and no-fallback/partial-success rules. Lower attrs/text semantics remain opaque: do not validate formula text, dxf payload, priority, or attributes.

## Required tests and acceptance

Add exact tests for direct cfRule text; XM f tail; X14 dxf tail; multiple children with first tail; whitespace-positive cases; paired earlier tier-1/later rule-tail; and earlier unknown-child/later rule-tail, all asserting exact tuples.

Acceptance commands:

`python3 -m pytest -q tests/test_opc_worksheet_x14_cf_owner_topology.py`

`python3 -m pytest -q tests/test_opc_worksheet_x14_cf_owner_topology.py tests/test_opc_workbook_topology.py tests/test_opc_worksheet_cell_reader.py tests/test_opc_worksheet_structure_reader.py tests/test_opc_worksheet_native_cf_reader.py`

`python3 -m pytest -q`

`python3 -m compileall -q rns_import_server/opc_worksheet_x14_cf_owner_topology.py tests/test_opc_worksheet_x14_cf_owner_topology.py`

`git diff --check`

Verify fixture/card hashes, exact scope/authorship/remote/clean state. P6 independent review is required; after ACCEPT, fresh corpus qualification only—do not edit the suspended corpus branch. No UI, bottle, native Excel, insertion, or publication claim. A non-force commit/push requires the verified human identity `mayky77-glitch <274605240+mayky77-glitch@users.noreply.github.com>`; AI attribution and force push are forbidden.
