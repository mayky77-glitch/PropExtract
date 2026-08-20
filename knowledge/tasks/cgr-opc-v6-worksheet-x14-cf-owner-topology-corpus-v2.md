---
type: task
status: in_review
work_id: cgr-opc-v6-worksheet-x14-cf-owner-topology-corpus-v2
tags: [task/test-corpus, feature/x14-cf-owner-topology, status/in-review]
last_verified: 2026-08-20
updated: 2026-08-20
---

# X1 owner-topology corpus v2 — frozen test-only card

Exact accepted base: `e40bdefab96a453d316b073c24d4ef723214faf6`. Exclusive scope is only `tests/test_opc_worksheet_x14_cf_owner_topology.py` plus this card. Production reader blob `6eea77cdda6f08bc9902810f54cff332123bad87` and fixture `83a56ee4f6f7a00a92cc577eb279377f50aba912` are frozen; X1, mixed-content, and corpus-v1 cards are frozen. No edits outside the two owned paths; a validated non-force human-attributed corpus commit/push is required.

## Exact corpus

Add only tests, with no code-set values or skipped cases. Cover counted PathLike success, `__fspath__` TypeError/ValueError/OSError, nonstr, NUL, each once; member missing/case/dot/percent aliases, two aliases, canonical+alias, read failure, decompression failure; XML UTF8/UTF16 BOM and declarations, unsupported encoding, undeclared prefix, duplicate expanded attributes, one ET parse; every six X14/XM owned local at worksheet, wrappers, every other owner depth, wrong URI/case, and foreign/empty variants; ext tail, container text/all tails, and accepted cfRule text/child-tail regressions.

Combined two-sheet rows 6/10/104 must assert full recursive `asdict`, exact field order, and `FrozenInstanceError` for workbook, worksheet, and container records. Every negative must assert the exact four-tuple. Preserve all legal and precedence regressions. If another production defect appears, hard block and make no production edit.

## Acceptance and handoff

Run direct, focused, and full pytest; compile the test file; run `git diff --check`; verify production/fixture hashes, exact test-only scope, authorship/identity, remote, and clean state. P6 reviews the combined tip: ACCEPT permits integration; REJECT is a hard block. No UI, bottle, native Excel, or semantic claim. A non-force human-attributed commit/push is required; AI attribution and force push are forbidden.

## Evidence

2026-08-20 corpus v2 added exact test-only boundary coverage for path coercion, ZIP member aliases/read failures, XML encodings/parser boundaries, owned-local placement and namespace collisions, mixed content, and the two-sheet immutable projection. Observed: `PYTHONPATH=. pytest -q tests/test_opc_worksheet_x14_cf_owner_topology.py` — 102 passed; `PYTHONPATH=. pytest -q tests/test_opc_worksheet_x14_cf_owner_topology.py -k 'path or member or xml or owned or mixed or projection'` — 88 passed, 14 deselected; `PYTHONPATH=. pytest -q` — 1237 passed, 1 existing openpyxl warning; `python3 -m py_compile tests/test_opc_worksheet_x14_cf_owner_topology.py` — passed; `git diff --check` — passed. Frozen production/fixture hashes observed: `6eea77cdda6f08bc9902810f54cff332123bad87`, `83a56ee4f6f7a00a92cc577eb279377f50aba912`.
