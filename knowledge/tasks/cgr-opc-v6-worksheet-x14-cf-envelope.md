---
type: task
status: planned
work_id: cgr-opc-worksheet-x14-cf-envelope-v1
tags:
  - task/implementation
  - domain/propextract
  - feature/opc-worksheet-x14-cf-envelope
  - status/planned
last_verified: 2026-08-20
updated: 2026-08-20
---

# OPC v6 worksheet X14 CF envelope — frozen Gate card

Frozen future implementation card. Dependency/planning base is exact `d6d007528ceed65ed6c6597015c187ea536ee544` on `codex/cgr-opc-package-resolver-v6-integration`. Old X14 `8ad867a`/`b02351b`/`387a8d2`, old CF `786fe`/`123e7b8`, rejected V1 `e72b4e5`/`8a387dd`, and rejected structure `5fb526a7`/`2478fabd` are reference/excluded ancestry only.

## Exclusive scope

Only these future paths may change: `rns_import_server/opc_worksheet_x14_cf_reader.py`, `tests/opc_worksheet_x14_cf_fixture_factory.py`, `tests/test_opc_worksheet_x14_cf_reader.py`, and this card. No code/config/source workbook/UI/CrossOver/native Excel changes.

## Contract

Namespaces are exact: SML `http://schemas.openxmlformats.org/spreadsheetml/2006/main`, X14 `http://schemas.microsoft.com/office/spreadsheetml/2009/9/main`, XM `http://schemas.microsoft.com/office/excel/2006/main`. Read the direct SML worksheet `extLst`, then its direct SML `ext` with the required sole `uri` attribute `{78C0D931-6437-407d-A8EE-F0AAD7539E65}`, then direct X14 `conditionalFormattings`/`conditionalFormatting` children exactly `X14 cfRule` then `XM sqref`; each rule is exactly `XM f` then `X14 dxf`. Legal chain is SML worksheet → direct SML `extLst` → direct SML `ext` → direct X14 `conditionalFormattings` → direct X14 `conditionalFormatting` → direct X14 `cfRule`/`XM sqref`; rule chain is `XM f`/`X14 dxf`. URI matching is case-sensitive. Ignore sibling X14 data validations under `{CCE6A557-97BC-4b89-ADB6-D9C93CAAB3DF}` as unowned; do not globally reject X14.

Immutable API/field order: `X14CfRuleEnvelope(owner_path, document_order, type, priority, stop_if_true, rule_id, formula, has_inline_dxf)`, `X14CfContainerEnvelope(owner_path, sqref_text, rules)`, `WorksheetX14CfEnvelope(worksheet, containers)`, `WorkbookX14CfEnvelope(worksheets)`, `OPCWorksheetX14CfReaderError(code, subject, field, detail).as_tuple()`, and `read_worksheet_x14_cf_envelope(path)`. Wrappers and envelopes are immutable; tests must verify identity, ancestry, full records/asdict, and `FrozenInstanceError`.

Preserve exact parsed Unicode text for nonblank formula and sqref, including leading/trailing non-whitespace-preserving content; no normalization; whitespace-only is invalid. Expression only; priorities collapse XML whitespace, are signed positive Int32 `1..2147483647`, worksheet-global unique, and need not follow numeric order in XML. Booleans accept `0/1/false/true`; id is nonblank; exactly one inline dxf marker. Inline dxf is opaque only after one dxf with no attrs/mixed content; SML font/fill children are accepted but unmodeled; any X14/XM unexpected child is typed. `extLst` attrs are none; `ext` attrs are exactly `uri`; `conditionalFormattings`/`conditionalFormatting` attrs are none; container/formattings/dxf/f/sqref attrs are none; cfRule attrs are exactly `type/priority/stopIfTrue/id`. Use accepted topology/canonical member, one-shot PathLike, topology error identity, exact canonical member matching, and one `ET.fromstring` per worksheet. Never relax the native-CF X14 hard-stop; no alternate parser, fallback, or partial success.

Error precedence is first document-order fault only: path/topology/member/XML wellformedness → worksheet root → complete legal CF parent chain + exact URI → envelope semantics. XML wellformedness precedes all semantics; parent/URI precedes envelope. Freeze codes/subjects/fields/details for `path-invalid`, package/member/XML/root errors compatible with accepted OPC readers; `invalid-x14-cf-parent`, `unsupported-x14-cf-extension-uri`, X14 namespace/local collisions, `unknown-x14-cf-attribute/child`, `invalid-x14-cf-content/order/cardinality`, `unsupported-x14-cf-rule-type`, `invalid-x14-cf-priority`, `duplicate-x14-cf-priority`, `invalid-x14-cf-boolean`, and `invalid-x14-cf-id/formula/sqref/dxf`. Reject wrong parent/URI/namespace collision, owned unknown attrs/children/order, duplicates, mixed content, and unsupported type with exact four-tuple.

## Corpus and acceptance

Corpus has two sheets with rows 6/10/104 synthetic raw sqref/formula, unsorted unique priorities, boolean tri-state, and full immutable projections. Matrix covers path/topology/member/XML, parent/URI/namespace, formula/sqref/dxf/rule attribute/cardinality/order, and sibling-DV coexistence.

Owned paths are exactly this card plus `rns_import_server/opc_worksheet_x14_cf_reader.py`, `tests/opc_worksheet_x14_cf_fixture_factory.py`, and `tests/test_opc_worksheet_x14_cf_reader.py`; fixture tests contain no source-derived values. Acceptance commands are exactly: `python3 -m pytest -q tests/test_opc_worksheet_x14_cf_reader.py tests/test_opc_worksheet_structure_reader.py tests/test_opc_worksheet_cell_reader.py tests/test_opc_workbook_topology.py`, `python3 -m pytest -q`, `python3 -m compileall -q rns_import_server tests`, and `git diff --check`. Require topology/cell/structure coverage, full records/asdict/identity/ancestry/FrozenInstanceError, and full matrix coverage. No semantic safety claim beyond ownership/envelope: sqref geometry/mapping, formula interpretation, dxf/font/fill/color semantics, X14 DV parsing, native CF changes, mutation/insertion safety, UI/CrossOver/native Excel are excluded. Preserve no-silent-fallback invariant.
