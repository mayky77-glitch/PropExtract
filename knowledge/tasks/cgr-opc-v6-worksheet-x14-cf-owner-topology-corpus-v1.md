---
type: task
status: planned
work_id: cgr-opc-v6-worksheet-x14-cf-owner-topology-corpus-v1
tags: [task/test-corpus, feature/x14-cf-owner-topology, status/planned]
last_verified: 2026-08-20
updated: 2026-08-20
---

# X1 owner-topology corpus completion — frozen test-only card

Exact base is `9a40ac27eee9d52bd96ecfc48c0f587341b258fa`. Exclusive implementation scope is only existing `tests/test_opc_worksheet_x14_cf_owner_topology.py` plus this card. Production and fixture blobs are frozen: reader `e388311af9b7c319a6295765e240668e76c4952b`; fixture factory `83a56ee4f6f7a00a92cc577eb279377f50aba912`. No production, fixture, API, X1-card, or other file edits; no UI/bottle/native Excel/semantic claim.

## Exact corpus

Complete only the missing corpus, with no code sets: counted PathLike success and `__fspath__` TypeError/ValueError/OSError, nonstr, NUL, each exactly one call; member missing/case/dot/percent aliases, two aliases, canonical+alias, read failure, decompression failure, exact tuples; XML UTF8/UTF16 BOM, declarations, unsupported encoding, undeclared prefix, duplicate expanded attrs, and one ET parse per worksheet. Cover every exact X14/XM owned local at worksheet, arbitrary wrapper, every other owner depth, wrong CF URI/case, plus foreign/empty variants; ext tail, container text, and all tails.

Combined two-sheet rows 6/10/104 must assert exact recursive `asdict`, field order, descriptor equality, and `FrozenInstanceError` for workbook/worksheet/container. Every negative asserts the exact four-tuple. Retain direct legal DV and precedence regressions. Do not change code/API or set values outside the frozen reader contract.

## Acceptance and handoff

Run exactly:

`python3 -m pytest -q tests/test_opc_worksheet_x14_cf_owner_topology.py`

`python3 -m pytest -q tests/test_opc_worksheet_x14_cf_owner_topology.py tests/test_opc_workbook_topology.py tests/test_opc_worksheet_cell_reader.py tests/test_opc_worksheet_structure_reader.py tests/test_opc_worksheet_native_cf_reader.py`

`python3 -m pytest -q`

`python3 -m compileall -q tests/test_opc_worksheet_x14_cf_owner_topology.py`

`git diff --check`

Also verify frozen blob hashes, exact scope/authorship/remote/clean state. P6 reviews the combined tip: ACCEPT may permit feature integration; REJECT is a hard block. A non-force commit/push is required under the verified human identity mayky77-glitch <274605240+mayky77-glitch@users.noreply.github.com>; AI attribution and force push are forbidden.
