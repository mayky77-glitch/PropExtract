---
type: task
status: completed
work_id: cgr-opc-v6-worksheet-x14-cf-envelope-projection-v2
tags: [task/implementation, feature/x14-cf-envelope, status/planned]
last_verified: 2026-08-21
updated: 2026-08-21
---

# X2 worksheet X14 CF envelope projection v2 — frozen Gate card

Exact accepted dependency/base is `ea280eeb2101c87213bc538d3b697fc0ea6a982e` on `codex/cgr-opc-x14-cf-owner-dv-precedence-v1-integration`. Accepted X1 owner topology, DV precedence, I/O matrix A and tag/depth matrix B-v2 are mandatory dependencies. Blocked envelope tips `bdee129`, `21e1446`, `0cb500b`, `848641b`, `06bbdc3`, blocked corpus tips, and old X14/native-CF lines are reference only: do not merge, cherry-pick, copy, or inherit them.

## Exclusive scope

Exactly four paths may change: this card; `rns_import_server/opc_worksheet_x14_cf_owner_topology.py`; new `tests/opc_worksheet_x14_cf_envelope_fixture_factory.py`; new `tests/test_opc_worksheet_x14_cf_envelope_projection.py`. Do not edit accepted X1 fixture/tests, other readers, mutation/publication/UI, source PDF/XLSX, README, configuration, or history. Preserve all existing X1 public APIs, exact errors and projections byte-for-behavior.

## Frozen public API

Add immutable records with exact field order:

- `X14CfRuleEnvelope(owner_path: str, document_order: int, type: str, priority: int, stop_if_true: bool | None, rule_id: str, formula: str, has_inline_dxf: bool)`;
- `X14CfContainerEnvelope(owner: X14CfContainerOwner, sqref_text: str, rules: tuple[X14CfRuleEnvelope, ...])`;
- `WorksheetX14CfEnvelope(worksheet: WorksheetDescriptor, containers: tuple[X14CfContainerEnvelope, ...])`;
- `WorkbookX14CfEnvelope(worksheets: tuple[WorksheetX14CfEnvelope, ...])`.

Add `read_worksheet_x14_cf_envelope(package_path) -> WorkbookX14CfEnvelope`. Reuse `OPCWorksheetX14CfOwnerTopologyError` and its exact `(code, subject, field, detail)` tuple; do not add an alternate error family. Container owner identity/path/order must equal the accepted X1 projection. Rule `owner_path` is `{container.owner_path}/cfRule[i]`; `document_order` is worksheet-local across containers in XML order. Empty worksheets return empty container tuples.

## One accepted pipeline and semantic boundary

Refactor only as needed so each public call performs exactly one `os.fspath`, one accepted topology call, one canonical member read and one `ET.fromstring(bytes)` per worksheet, followed by the accepted complete X1 owner validation before envelope semantics. Do not public-chain X1, reopen ZIP, reparse XML, decode/regex/expat/pull-parse, or implement an alternate ownership path. Topology exceptions retain object identity. Workbook publication is atomic after every worksheet validates. Existing X1 API/error/projection tests must remain green.

The exact CF chain remains accepted X1. The exact sibling DV URI/subtree remains unowned; CF-owned siblings/descendants inside it retain accepted X1 errors. X2 consumes only already validated legal X14 `conditionalFormatting` owners. It does not weaken, skip, reinterpret, or duplicate X1 parent/namespace/URI/tail precedence.

## Envelope semantics

Each legal X14 `conditionalFormatting` has direct children in exact order: one or more X14 `cfRule`, then exactly one XM `sqref`. Container/formattings attrs remain forbidden by X1. XM `sqref` has no attrs or children, nonblank text, and no nonwhite tail; preserve its text exactly without A1 parsing or normalization.

Each direct X14 `cfRule` has exactly attributes `type`, `priority`, `id`, with optional `stopIfTrue`; unknown or missing required attrs fail closed. Only `type="expression"` is supported. `priority` collapses only XML whitespace and is a signed lexical positive Int32 `1..2147483647`; bound the raw/significant lexical before `int`; priorities are unique worksheet-wide but need not be numerically sorted. `stopIfTrue` accepts only `0/1/false/true`, absence maps to `None`. `id` is one exact braced GUID `{8-4-4-4-12}` with ASCII hex; preserve original spelling.

Rule children are exactly one XM `f`, then one X14 `dxf`. XM `f` has no attrs/children and nonblank exact text. X14 `dxf` has no attrs/nonwhite mixed content and is represented only by `has_inline_dxf=True`; its SML children are opaque in X2 and must not be interpreted, but foreign/X14/XM children fail `unknown-x14-cf-child`. Allow only direct SML `font` and optional following SML `fill`, matching observed target order; duplicates or reverse order fail. Do not validate font/fill descendants in this Gate.

Freeze deterministic semantic errors after accepted X1 validation: `unknown-x14-cf-attribute`, `unknown-x14-cf-child`, `invalid-x14-cf-content`, `invalid-x14-cf-order`, `invalid-x14-cf-cardinality`, `unsupported-x14-cf-rule-type`, `invalid-x14-cf-priority`, `duplicate-x14-cf-priority`, `invalid-x14-cf-boolean`, `invalid-x14-cf-id`, `invalid-x14-cf-formula`, `invalid-x14-cf-sqref`, `invalid-x14-cf-dxf`. Subject is canonical worksheet part; fields/details are exact in tests. First accepted X1 fault always precedes X2 semantic faults; within X2 use XML document order and return one exact tuple only. No fallback, partial output, warning-only success, skip, xfail, or empty-success substitution.

## Corpus and acceptance

Synthetic two-sheet corpus mirrors only aggregate target shape: two ordered containers tied by raw formula/sqref text to rows 6 and 10 on sheet 1; one row 104 container on sheet 2; expression rules, unsorted unique priorities, stopIfTrue absent/false/true, braced IDs, inline dxf font and font+fill. Assert exact recursive `asdict`, field order, accepted `WorksheetDescriptor` and `X14CfContainerOwner` equality, owner/rule order and `FrozenInstanceError` for every record.

Exact negative matrix covers required/unknown attrs; priority whitespace/sign/zeros/bounds/overlong/duplicates across containers; boolean; GUID; formula/sqref missing/duplicate/blank/attrs/nested/tails/order; dxf missing/duplicate/attrs/text/tails/foreign-X14-XM child/font-fill duplicate/reverse; unsupported rule types; owner-level fault precedence; valid sibling DV unowned and CF-owned tags inside DV still rejected by X1. Retain counted PathLike, topology sentinel identity, canonical member/XML/UTF/BOM/root, one parse per worksheet, six-local placement/collision and two-sheet atomicity through the accepted X1 suites.

Acceptance commands:

`python3 -m pytest -q tests/test_opc_worksheet_x14_cf_envelope_projection.py tests/test_opc_worksheet_x14_cf_owner_topology.py tests/test_opc_worksheet_x14_cf_owner_topology_io_matrix.py tests/test_opc_worksheet_x14_cf_owner_topology_tag_matrix_v2.py tests/test_opc_workbook_topology.py tests/test_opc_worksheet_cell_reader.py tests/test_opc_worksheet_structure_reader.py tests/test_opc_worksheet_native_cf_reader.py`

`python3 -m pytest -q`

`python3 -m compileall -q rns_import_server/opc_worksheet_x14_cf_owner_topology.py tests/opc_worksheet_x14_cf_envelope_fixture_factory.py tests/test_opc_worksheet_x14_cf_envelope_projection.py`

`git diff --check`

Independent P6 must verify exact accepted-base ancestry, absence of blocked X14 tips, one shared parse/ownership pipeline, X1 behavioral compatibility, anti-shallow exact tuples and immutable full projections. X2 qualifies only envelope values and inline-dxf presence. Sqref geometry/mapping, formula interpretation, dxf/font/fill/color semantics, X14 DV semantics, mutation/insertion/publication safety, UI/CrossOver/native Excel remain explicitly unqualified.

## Completion evidence

Implemented from frozen base `c5ea7cab467288d15b3ec0075d6a87a424633ca0` with accepted X1 dependency `ea280eeb2101c87213bc538d3b697fc0ea6a982e`. The envelope reader uses the shared accepted X1 parse/ownership pipeline and publishes only after all worksheets pass X1 and X2 validation. Exact acceptance subset: 533 passed. Full suite: 1285 passed, with one existing openpyxl unknown-extension warning. Required `compileall` and `git diff --check` passed.
