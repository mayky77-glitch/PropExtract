---
type: task
status: frozen
work_id: cgr-opc-v6-worksheet-x14-cf-sqref-envelope-v1
tags: [task/implementation, feature/x14-cf-sqref, status/frozen]
last_verified: 2026-08-21
updated: 2026-08-21
---

# X2b worksheet X14 CF sqref envelope — frozen Gate card

Exact base and accepted dependency are `f546fa552ad78954e7c9295cf76cf3b12a73be6f`. Rejected envelope V2 tips `65a57b7`, `5391f7c`, `eb054b5` must be absent from ancestry. Branch is `codex/cgr-opc-x14-cf-sqref-envelope-v1`. Role is P4 developer. Merge method is exact `--no-ff` after independent P6.

## Exclusive scope

Owned paths:

- `rns_import_server/opc_worksheet_x14_cf_owner_topology.py`
- `tests/opc_worksheet_x14_cf_sqref_fixture_factory.py`
- `tests/test_opc_worksheet_x14_cf_sqref_envelope.py`
- this card

All X1/X2a fixture, test, card and public records remain frozen. Native CF/DV readers, mutation, workbook publication, UI and Windows adapters are forbidden.

## Frozen API

Add immutable records without changing X1/X2a APIs:

- `X14CfSqrefRange(source_token, start_coordinate, end_coordinate, min_row, min_column, max_row, max_column)`
- `X14CfOwnerSqrefEnvelope(owner, rules, sqref_text, ranges)`
- `WorksheetX14CfSqrefEnvelope(worksheet, containers)`
- `WorkbookX14CfSqrefEnvelope(worksheets)`
- `read_worksheet_x14_cf_sqref_envelope(package_path)`

`owner` and `rules` equal accepted X1/X2a projection exactly. `sqref_text` is ElementTree-normalized text, never raw ZIP bytes. `source_token` preserves token lexical text; coordinates are uppercase and remove `$`. The reader is an oracle only and must not serialize source XML.

## Owner grammar and event precedence

Each accepted owner contains `x14:cfRule+` followed by exactly one direct `xm:sqref`. Rules after sqref or sqref before the first rule fail order immediately. A second sqref fails cardinality when encountered. Missing rule/sqref cardinality is checked only at owner exit. For legal first sqref, validate attributes, children, nonblank text and each token immediately before inspecting later siblings. Earlier X2a rule errors win over later sqref faults; legal-position invalid first sqref wins over any later duplicate/order/rule fault. X1 workbook-wide faults, including a later worksheet, precede all X2 work. Publish only after every worksheet succeeds.

Exact shared four-tuple errors:

- `invalid-x14-cf-cardinality`, field `conditionalFormatting`, detail `cfRule|sqref`
- `invalid-x14-cf-order`, field `conditionalFormatting`, detail `cfRule,sqref`
- `invalid-x14-cf-sqref`, field `sqref`, detail `attribute|child|text|<token>`
- `duplicate-x14-cf-sqref`, field `sqref`, detail second source token
- `overlapping-x14-cf-sqref`, field `sqref`, detail second source token

Do not scan all tree sqref values. Exact sibling X14 DV stays unowned; its formula/sqref content is not validated by X2b.

## A1 contract

Separators are XML whitespace only: SP/TAB/CR/LF. Each token is one ASCII A1 cell or rectangular range with optional `$`, within `A1:XFD1048576`. Reject qualified/3D/external, whole row/column, zero-padded row, extra colon, reversed, out-of-bounds and overlong forms. Exact/canonical repeated rectangles are duplicates. Different rectangles sharing any cell are overlaps, including containment, crossing and shared-cell edges; merely adjacent rectangles pass. Keep token order.

Use a local X14 grammar in the owned reader and parity tests against accepted native-CF geometry. Do not import private native helpers and do not create a generic-parser refactor in this Gate.

## Frozen evidence

Synthetic two-sheet projection covers owners/rules/ranges around rows 6, 10 and 104 with raw and typed fingerprints. It proves data needed for later mapping but performs no transform. Future mutation rules are separate: range above insertion unchanged; range at/below shifts; spanning range expands.

Exact corpus covers public field order/asdict/immutability; order/cardinality; A1 min/max, `$`, case, multi-range, invalid/overlong/reversed/bounds; lexical/canonical duplicates; containment/crossing/edge overlap; NBSP and non-XML whitespace; invalid first sqref plus later duplicate/rule fault; earlier rule fault plus later invalid sqref; X1 later-sheet precedence; DV before/after; counted PathLike, topology sentinel, one parse per sheet and atomic failure.

Real source qualification is read-only and must record exact container/range counts, 1,558 expression-rule consistency, rows 6/10/104 coverage and unchanged source SHA. If real target contains duplicate/overlapping ranges or grammar outside this contract, stop with evidence; do not weaken parser or silently skip.

## Acceptance

Run exactly:

`python3 -m pytest -q tests/test_opc_worksheet_x14_cf_sqref_envelope.py`

`python3 -m pytest -q tests/test_opc_worksheet_x14_cf_sqref_envelope.py tests/test_opc_worksheet_x14_cf_rule_envelope.py tests/test_opc_worksheet_x14_cf_rule_envelope_corpus.py tests/test_opc_worksheet_x14_cf_owner_topology.py tests/test_opc_worksheet_x14_cf_owner_topology_io_matrix.py tests/test_opc_worksheet_x14_cf_owner_topology_tag_matrix_v2.py tests/test_opc_worksheet_native_cf_reader.py tests/test_opc_workbook_topology.py tests/test_opc_worksheet_cell_reader.py tests/test_opc_worksheet_structure_reader.py`

`python3 -m pytest -q`

`python3 -m compileall -q rns_import_server/opc_worksheet_x14_cf_owner_topology.py tests/opc_worksheet_x14_cf_sqref_fixture_factory.py tests/test_opc_worksheet_x14_cf_sqref_envelope.py`

`git diff --check`

Verify exact ancestry, four-path scope, frozen blobs, human identity and clean tree. Independent P6 must reproduce first-event precedence and anti-shallow A1 corpus. No fallback, partial success, DXF/formula interpretation, mutation, publication, UI/CrossOver or native Excel claim.
