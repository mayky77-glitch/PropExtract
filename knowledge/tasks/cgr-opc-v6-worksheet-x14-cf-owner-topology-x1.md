---
type: task
status: completed
work_id: cgr-opc-v6-worksheet-x14-cf-owner-topology-x1
tags: [task/implementation, feature/x14-cf-owner-topology, status/planned]
last_verified: 2026-08-20
updated: 2026-08-20
---

# X1 worksheet X14 CF owner topology — frozen Gate card

Base is direct ancestry only: `d6d007528ceed65ed6c6597015c187ea536ee544`. Do not reuse `bdee129`, `0cb500b`, `06bbdc3` or descendants; old X14/native rejected refs are reference only.

## Exclusive scope

Exactly four owned paths: this card; `rns_import_server/opc_worksheet_x14_cf_owner_topology.py`; `tests/opc_worksheet_x14_cf_owner_fixture_factory.py`; `tests/test_opc_worksheet_x14_cf_owner_topology.py`. No other code/config/tests/docs, source files, publication, or history rewrite; ordinary human-authored non-force feature commit/push is required after validation.

## Frozen API

Frozen records, exact field order: `X14CfContainerOwner(owner_path: str, document_order: int)`; `WorksheetX14CfOwnerTopology(worksheet: WorksheetDescriptor, containers: tuple[X14CfContainerOwner, ...])`; `WorkbookX14CfOwnerTopology(worksheets: tuple[WorksheetX14CfOwnerTopology, ...])`. `OPCWorksheetX14CfOwnerTopologyError(ValueError)` fields are `code, subject, field, detail`, with `as_tuple()`; reader is `read_worksheet_x14_cf_owner_topology(package_path)`. Empty `containers` is the sole presence signal. Owner path is `{part}/worksheet/extLst[i]/ext[j]/conditionalFormattings[1]/conditionalFormatting[k]`, order 1-based worksheet-local.

## XML ownership and legal chain

Namespaces: SML `http://schemas.openxmlformats.org/spreadsheetml/2006/main`; X14 `http://schemas.microsoft.com/office/spreadsheetml/2009/9/main`; XM `http://schemas.microsoft.com/office/excel/2006/main`. CF URI is exact case-sensitive `{78C0D931-6437-407d-A8EE-F0AAD7539E65}`; DV URI `{CCE6A557-97BC-4b89-ADB6-D9C93CAAB3DF}`.

Legal CF chain is worksheet → direct SML `extLst` → SML `ext` sole CF URI → exactly one X14 `conditionalFormattings` → one or more X14 `conditionalFormatting`. Below a container only direct X14 `cfRule*`, direct XM `sqref*`; each direct X14 `cfRule` may contain only direct XM `f*` and direct X14 `dxf*`. X1 validates no attrs/type/priority/bool/id/order/cardinality/text/payload below rule/value nodes. At most one matching CF extension exists across direct `extLst`; matching ext has exactly one formattings and no other direct child; formattings contain only containers; containers only `cfRule`/XM `sqref`. `extLst` has no attrs, `ext` exactly `uri`, formattings/container no attrs. Non-white text/tails are rejected at extLst/matching ext/formattings/container; lower content is opaque.

Classify every element by expanded QName+local. Owned locals are X14 `conditionalFormattings`, `conditionalFormatting`, `cfRule`, `dxf`, and XM `f`, `sqref`. An owned tag outside its legal direct parent is `invalid-x14-cf-parent`; foreign/empty same-local tags are `x14-cf-namespace-collision` at worksheet, every CF candidate, and owner depth.

Native SML conditionalFormatting/cfRule and SML cell f remain intact. DV is not skipped wholesale: carve only exact XM f/sqref inside exact legal worksheet/direct extLst/direct SML ext whose URI is DV/direct X14 `dataValidations`; continue traversal. CF-owned tags and foreign/empty impostors still fail. Wrong URI/case, extra ext attrs, wrong placement/namespace disable the carve.

## Pipeline and errors

Call `os.fspath` once; pass `str` to accepted `read_workbook_topology`, preserving exact exception identity; resolve exact canonical worksheet member; one `ET.fromstring(bytes)` per worksheet; validate all roots; one complete-tree preorder DFS; publish only after workbook-wide validation. No public chaining, decode/regex/expat/pull/second parse/fallback/partial success. DFS events are start, text, descendants, tails, end-cardinality. Global precedence: path → topology → all members/XML → all roots → tier 1 → tier 2 → success. Within tiers, earliest fault by document order; tier 1 is parent/ns/URI/required-chain/cardinality, tier 2 attrs/unknown child/mixed content; after traversal choose highest tier then first document-order fault.

Retain accepted errors: `invalid-package-path`, `unreadable-package`, topology identity, `missing-worksheet-member`, `ambiguous-worksheet-member`, `noncanonical-worksheet-member`, `unreadable-worksheet-part`, `unsupported-xml-encoding`, `malformed-worksheet-xml`, `invalid-worksheet-root`. X1 exact tuples: `invalid-x14-cf-parent(part,'tag',expanded)`, `x14-cf-namespace-collision(part,'tag',expanded)`, `unsupported-x14-cf-extension-uri(part,'uri',actual_or_empty)`, `duplicate-x14-cf-extension(part,'uri',CF_URI)`, `invalid-x14-cf-cardinality(part,'ext','conditionalFormattings')` or `(part,'conditionalFormattings','conditionalFormatting')`, `unknown-x14-cf-attribute(part,'attribute',expanded_attr)`, `unknown-x14-cf-child(part,'tag',expanded_tag)`, `invalid-x14-cf-content(part,owner_local,'text'|'tail')`. First exact tuple only.

## Corpus, X2 handoff, exclusions

Use full recursive two-sheet projection: sheet 1 opaque row 6/10 containers, sheet 2 row 104; verify asdict, paths, orders, descriptor equality, field order, and `FrozenInstanceError` for all three records. Prove malformed priorities/blank formulas/sqrefs/arbitrary dxf are opaque and absent. Cover counted PathLike success, raising `__fspath__` TypeError/ValueError/OSError, nonstr/NUL, topology sentinel identity, exactly-once calls; missing/case/dot/percent aliases, two aliases, canonical+alias, decompression; empty/truncated/undeclared-prefix/duplicate-expanded-attr/UTF8+UTF16 BOM/declarations/unsupported XML and one parse count. Cover every owned local at legal/direct worksheet/arbitrary wrapper/every owner depth/wrong URI+case, foreign/empty variants, native SML CF/cell f, realistic DV carve/coexistence, malformed DV no carve, all chain cardinality/order/unknown child/attr/text/tail faults and precedence. Every negative asserts exact four-tuple; native CF/topology/cell/structure/native blobs remain identical.

X2 is separate: reuse this private pipeline within one call, never public-call/reparse X1; preserve API/errors/projections and no partial success; semantics only on validated internal nodes. Exclude all rule/priority/formula/sqref/dxf semantics, mapping/insertion, UI/CrossOver/native Excel.

Acceptance commands:

`python3 -m pytest -q tests/test_opc_worksheet_x14_cf_owner_topology.py`

`python3 -m pytest -q tests/test_opc_worksheet_x14_cf_owner_topology.py tests/test_opc_workbook_topology.py tests/test_opc_worksheet_cell_reader.py tests/test_opc_worksheet_structure_reader.py tests/test_opc_worksheet_native_cf_reader.py`

`python3 -m pytest -q`

`python3 -m compileall -q rns_import_server/opc_worksheet_x14_cf_owner_topology.py tests/opc_worksheet_x14_cf_owner_fixture_factory.py tests/test_opc_worksheet_x14_cf_owner_topology.py`

`git diff --check`

## Implementation evidence

Implemented from direct parent `d6d007528ceed65ed6c6597015c187ea536ee544` without rejected X14-envelope ancestry. 2026-08-20 validation passed: focused `15`, compatibility `398`, full `1150` tests (one existing openpyxl extension warning), `compileall`, and `git diff --check`.
