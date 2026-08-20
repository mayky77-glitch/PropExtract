---
type: task
status: planned
work_id: cgr-opc-v6-worksheet-x14-cf-rule-envelope-corpus-v1
tags: [task/test-corpus, feature/x14-cf-rule-envelope, status/planned]
last_verified: 2026-08-21
updated: 2026-08-21
---

# X2a worksheet X14 CF rule-envelope corpus — frozen test-only card

Base/runtime candidate is `b6926ace325dc4a13d24b32f6ac21c2a0d677734`; accepted dependency is `ea280eeb2101c87213bc538d3b697fc0ea6a982e`. Worktree and branch are exact: `/Users/x/.codex/worktrees/cgr-opc-x14-cf-rule-envelope-corpus-v1` on `codex/cgr-opc-x14-cf-rule-envelope-corpus-v1`. Role: tester. This card is planned and owns exactly one additive test module, `tests/test_opc_worksheet_x14_cf_rule_envelope_corpus.py`, plus this card. Commit only the card as the planning commit; later implementation must be a separate test-only commit and feature-branch push under the verified human identity.

## Frozen boundaries and forbidden paths

Exclusive write scope is the new test module and this card. Do not edit production `rns_import_server/opc_worksheet_x14_cf_owner_topology.py`, the original fixture factory, the original X2a card, or frozen original fixture/test/card blobs. Preserve all accepted X1 APIs, errors, projections, tests, and ancestry. If a test proves a production defect, STOP and report it; make no production edit. No sqref semantics, dxf-child semantics, formula meaning, X14-DV, range mapping, insertion, publication, UI/CrossOver, native Excel, or runtime/deployment claim.

## Corpus contract

Additive corpus coverage must assert every public record field order, including `WorkbookX14CfRuleEnvelope`, exact recursive `asdict`, exact four-tuples, full projection, accepted owner equality, tuple ordering, and `FrozenInstanceError` immutability for every record. Use the synthetic two-sheet corpus with accepted owners at rows 6/10/104, expression rules, unsorted unique priorities, optional/false/true `stopIfTrue`, exact GUIDs/formulas, and opaque inline dxf font or font+fill payloads.

Cover missing `type`, `priority`, and `id`, including sorted multi-missing and sorted unknown attributes; missing/empty formula; `stopIfTrue="1"`; all required priority, boolean, GUID, formula, and dxf semantic negatives from the original card. Cover both directions of combined semantic faults and preserve XML-event/document-order precedence. Direct XM `sqref` is ignored and unprojected: malformed, duplicate, reordered, empty, or misplaced sqref before/between rules must leave the same rule projection while rule order and errors remain preserved. Cover foreign X14/XM direct children and exact owner/rule paths/order. Assert rule owner paths `{owner.owner_path}/cfRule[i]`, worksheet-global document order, and atomic two-sheet publication.

Retain original X1 compatibility evidence: counted PathLike coercion, topology sentinel identity, canonical member/XML/root reads, one XML parse per worksheet, X1 tag/depth/DV precedence, and no shallow or fallback corpus. Keep all errors exact as `(code, subject, field, detail)` and do not broaden production behavior.

## Acceptance and handoff

Run exactly:

`python3 -m pytest -q tests/test_opc_worksheet_x14_cf_rule_envelope.py tests/test_opc_worksheet_x14_cf_owner_topology.py tests/test_opc_worksheet_x14_cf_owner_topology_io_matrix.py tests/test_opc_worksheet_x14_cf_owner_topology_tag_matrix_v2.py tests/test_opc_workbook_topology.py tests/test_opc_worksheet_cell_reader.py tests/test_opc_worksheet_structure_reader.py tests/test_opc_worksheet_native_cf_reader.py`

`python3 -m pytest -q tests/test_opc_worksheet_x14_cf_rule_envelope_corpus.py`

`python3 -m pytest -q`

`python3 -m compileall -q rns_import_server/opc_worksheet_x14_cf_owner_topology.py tests/opc_worksheet_x14_cf_rule_envelope_fixture_factory.py tests/test_opc_worksheet_x14_cf_rule_envelope.py tests/test_opc_worksheet_x14_cf_rule_envelope_corpus.py`

`git diff --check`

Verify exact base/dependency ancestry, frozen blob hashes, exact scope, human Git identity `mayky77-glitch <274605240+mayky77-glitch@users.noreply.github.com>`, remote sync, and clean tree. Require one non-force test-only commit and push of the feature branch; no amend, rebase, or force-push. Independent P6 review must inspect XML-event precedence, X1 compatibility, exact anti-shallow corpus, and absence of blocked production ancestry. Any unclear behavior or production defect remains an owner decision.
