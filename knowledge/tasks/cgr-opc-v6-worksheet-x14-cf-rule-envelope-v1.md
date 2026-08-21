---
type: task
status: implemented
work_id: cgr-opc-v6-worksheet-x14-cf-rule-envelope-v1
tags: [task/implementation, feature/x14-cf-rule-envelope, status/implemented]
last_verified: 2026-08-21
updated: 2026-08-21
---

# X2a worksheet X14 CF rule envelope — frozen Gate card

Exact accepted dependency/base is `ea280eeb2101c87213bc538d3b697fc0ea6a982e`. Blocked envelope V1/V2 tips, including `65a57b7`, `5391f7c`, `eb054b5`, and old X14/native-CF lines are reference only and must be absent from ancestry; do not copy/cherry-pick their source or tests.

## Exclusive scope and API

Owned paths are only this card, `rns_import_server/opc_worksheet_x14_cf_owner_topology.py`, new `tests/opc_worksheet_x14_cf_rule_envelope_fixture_factory.py`, and new `tests/test_opc_worksheet_x14_cf_rule_envelope.py`. Preserve accepted X1 APIs/errors/projections and all existing tests.

Add frozen records with exact field order: `X14CfRuleEnvelope(owner_path, document_order, type, priority, stop_if_true, rule_id, formula, has_inline_dxf)`; `X14CfOwnerRuleEnvelope(owner: X14CfContainerOwner, rules: tuple[X14CfRuleEnvelope, ...])`; `WorksheetX14CfRuleEnvelope(worksheet: WorksheetDescriptor, containers: tuple[X14CfOwnerRuleEnvelope, ...])`; `WorkbookX14CfRuleEnvelope(worksheets: tuple[WorksheetX14CfRuleEnvelope, ...])`. Add `read_worksheet_x14_cf_rule_envelope(package_path)`. Reuse `OPCWorksheetX14CfOwnerTopologyError` exact four-tuple only.

Container owner equality/path/order must exactly match accepted X1. Rule owner path is `{owner.owner_path}/cfRule[i]`; rule document order is worksheet-global in XML order. Empty owner/rule/worksheet tuples are valid exact projections.

## Shared pipeline and narrow semantics

Each public call performs one PathLike coercion, one accepted topology call, one canonical member read and one `ET.fromstring(bytes)` per worksheet, then the complete accepted X1 ownership validation before X2a. No public chaining, reopen/reparse, alternate resolver/parser, fallback, partial output or warning-only success. Topology exception identity and X1 error precedence are unchanged. Exact sibling DV remains unowned.

X2a owns only direct X14 `cfRule` nodes beneath already accepted X14 CF container owners. It processes them immediately in XML document order. Direct XM `sqref` is completely outside X2a semantics: do not project or validate its attributes, text, cardinality, position, duplication, or relationship to rules. X2b owns sqref later. A rule before or after any sqref is still processed by X2a in its actual XML position.

Rule attrs are exactly required `type`, `priority`, `id` plus optional `stopIfTrue`; first sorted unknown attr and first sorted missing required attr fail exact tuples. Only `type="expression"` is supported. Priority collapses only XML whitespace, accepts signed positive Int32 lexical `1..2147483647` with plus/leading zeros, bounds significant digits before `int`, rejects NBSP/zero/negative/overflow, and is unique worksheet-wide by numeric value. `stopIfTrue` accepts `0/1/false/true`, absence is `None`. `id` is an exact braced ASCII-hex GUID `{8-4-4-4-12}`, preserved lexically.

Each rule has exactly direct XM `f` then direct X14 `dxf`. Formula has no attrs/children, nonblank exact text, and no nonwhite tail. Dxf is presence-only: exactly one direct X14 dxf, no attributes, and no nonwhite rule/dxf text or tail; its descendants are opaque and absent from the model for the later dxf Gate. Wrong/missing/duplicate/reversed children fail at their own XML event/cardinality without scanning unrelated later siblings first. `has_inline_dxf` is always true on success.

Freeze exact semantic codes using the shared error family: `unknown-x14-cf-attribute`, `invalid-x14-cf-content`, `invalid-x14-cf-order`, `invalid-x14-cf-cardinality`, `unsupported-x14-cf-rule-type`, `invalid-x14-cf-priority`, `duplicate-x14-cf-priority`, `invalid-x14-cf-boolean`, `invalid-x14-cf-id`, `invalid-x14-cf-formula`, `invalid-x14-cf-dxf`. Subject is canonical worksheet part; every negative asserts `(code, subject, field, detail)` exactly. X1 faults precede X2a; within X2a use document order and publish only after workbook-wide success.

## Corpus and acceptance

Synthetic two-sheet corpus has accepted owners at rows 6/10/104, expression rules across owners, unsorted unique priorities, optional/false/true stop, exact GUIDs/formulas, and inline dxf font or font+fill payloads kept opaque. Assert exact recursive `asdict`, field order, descriptor and accepted owner equality, tuple order, and `FrozenInstanceError` for every record.

Exact negative matrix covers required/unknown attrs; every unsupported type; priority whitespace/sign/zeros/NBSP/bounds/overlong/global numeric duplicate; boolean; GUID; formula/dxf missing/duplicate/reversed/attrs/blank/nested/text/tails/foreign-X14-XM child; both directions of combined semantic faults. Prove sqref is not interpreted with malformed/duplicate/reordered sqref variants producing the same rule projection when X1 ownership remains valid. Retain counted PathLike, topology sentinel identity, member/XML/root/one-parse, X1 tag/depth/DV precedence and two-sheet atomicity through focused accepted suites.

Acceptance:

`python3 -m pytest -q tests/test_opc_worksheet_x14_cf_rule_envelope.py tests/test_opc_worksheet_x14_cf_owner_topology.py tests/test_opc_worksheet_x14_cf_owner_topology_io_matrix.py tests/test_opc_worksheet_x14_cf_owner_topology_tag_matrix_v2.py tests/test_opc_workbook_topology.py tests/test_opc_worksheet_cell_reader.py tests/test_opc_worksheet_structure_reader.py tests/test_opc_worksheet_native_cf_reader.py`

`python3 -m pytest -q`

`python3 -m compileall -q rns_import_server/opc_worksheet_x14_cf_owner_topology.py tests/opc_worksheet_x14_cf_rule_envelope_fixture_factory.py tests/test_opc_worksheet_x14_cf_rule_envelope.py`

`git diff --check`

Independent P6 must inspect XML-event precedence, X1 compatibility, exact anti-shallow corpus and absence of blocked ancestry. X2a makes no sqref, dxf-child, formula-meaning, X14-DV, range mapping, insertion, publication, UI/CrossOver or native-Excel claim.

## Implementation evidence

- Implemented on `codex/cgr-opc-x14-cf-rule-envelope-v1` from planning base `c942adefcac50c41596e566a69a54308ab2143e1`; accepted dependency `ea280eeb2101c87213bc538d3b697fc0ea6a982e` is an ancestor.
- The reader and X2a projection use `_accepted`: one package-path coercion, workbook topology read, canonical member read and XML parse per worksheet, followed by complete X1 validation before any envelope work. X2a does not invoke the public X1 reader.
- Added direct-rule projection, worksheet-global numeric priority uniqueness, immutable records, and a synthetic two-sheet test corpus. `xm:sqref` remains neither read into the projection nor validated by X2a.
- Validation: focused X2a suite (33 passed); frozen acceptance command (552 passed); full suite (1304 passed, one pre-existing openpyxl extension warning); compileall and `git diff --check` passed.

## P6 remediation evidence

- Priority stripping now accepts only XML whitespace (`SP`, `TAB`, `CR`, `LF`); NBSP, U+0085, U+2003 and all other non-XML whitespace remain lexical failures. It bounds significant digits before `int`, so a positive priority with 5,000 leading zeros is accepted safely.
- Rule child validation is a single XML-order state machine. It checks each `f`/`dxf` as encountered and defers only missing-child cardinality to rule exit; combined order/attribute repros retain their earliest event.
- Expanded X2a evidence includes exact recursive projection, accepted-owner equality, record immutability, opaque inline font/fill dxf descendants, XML/non-XML whitespace, event precedence, PathLike/topology-sentinel/one-worksheet-parse checks, and two-sheet atomicity.
- Post-remediation validation: focused acceptance (568 passed); full suite (1320 passed, one known openpyxl extension warning); compileall and `git diff --check` passed.
