---
type: task
status: completed
work_id: cgr-opc-v6-worksheet-x14-cf-owner-io-matrix-v1
tags: [task/test-corpus, feature/x14-cf-owner-topology, status/planned]
last_verified: 2026-08-20
updated: 2026-08-20
---

# X14 CF owner I/O matrix — frozen A card

Exact base is `e40bdefab96a453d316b073c24d4ef723214faf6`. This card owns only the future new test file `tests/test_opc_worksheet_x14_cf_owner_topology_io_matrix.py` and this card. Production reader blob `6eea77cdda6f08bc9902810f54cff332123bad87`, fixture factory blob `83a56ee4f6f7a00a92cc577eb279377f50aba912`, the original focused test, and all other cards are frozen. No production, fixture, deployment/runtime configuration, API, or unrelated documentation edits; no UI, bottle, native Excel, or semantic work.

## Exact A corpus

Exercise the frozen reader's package-path and worksheet-part I/O matrix. A counted PathLike success, `__fspath__` TypeError, ValueError, and OSError, non-string input, and embedded NUL must each assert the exact four-tuple (where applicable) and exactly one `__fspath__` call. Cover missing member; case and dot aliases without a canonical member; percent aliases; canonical plus alias; two aliases; and read/decompression failure, with exact tuples and no code sets or skips.

Cover the exact empty `b''` helper case and prove it distinguishes `None` from empty bytes. Cover UTF-8 and UTF-16 BOMs and declarations, unsupported encoding, and an undeclared prefix. Include a genuine duplicate expanded QName produced by two prefixes bound to the same namespace. Instrument parsing to prove exactly one `ET.fromstring` per worksheet.

Every negative assertion uses the exact four-tuple contract. Preserve topology identity, descriptor equality, canonical member selection, and all frozen projections. Do not add or alter application behavior to make a case pass.

## Frozen boundaries and handoff

Use only the frozen reader and fixture blobs above; the original focused test and compatibility readers remain unchanged. Do not claim UI, bottle, native Excel, or rule/priority/formula/sqref/dxf semantics. If a runtime defect or contract mismatch is found, stop immediately and report the evidence to the owner; do not edit production code. Any behavior not determined by the frozen implementation (especially empty-byte helper classification or alias/decompression precedence) is an owner decision, not an inferred test expectation.

## Acceptance

Run direct A, combined original-plus-A, focused compatibility, full suite, and compile checks:

`python3 -m pytest -q tests/test_opc_worksheet_x14_cf_owner_topology_io_matrix.py`

`python3 -m pytest -q tests/test_opc_worksheet_x14_cf_owner_topology.py tests/test_opc_worksheet_x14_cf_owner_topology_io_matrix.py`

`python3 -m pytest -q tests/test_opc_worksheet_x14_cf_owner_topology.py tests/test_opc_workbook_topology.py tests/test_opc_worksheet_cell_reader.py tests/test_opc_worksheet_structure_reader.py tests/test_opc_worksheet_native_cf_reader.py tests/test_opc_worksheet_x14_cf_owner_topology_io_matrix.py`

`python3 -m pytest -q`

`python3 -m compileall -q tests/test_opc_worksheet_x14_cf_owner_topology_io_matrix.py`

Also run `git diff --check`; verify the reader and fixture hashes, exact one-file scope, identity/remote/clean state, and P6. Human-authored non-force commit/push is required after acceptance; do not prohibit that scoped commit in this card.

## P4 evidence — 2026-08-20

- Added only `tests/test_opc_worksheet_x14_cf_owner_topology_io_matrix.py` (17 tests): PathLike coercion/error matrix, raw-member aliases and ambiguity, read/decompression failure, byte-preserving helper (`None` distinct from `b''`), UTF-8/UTF-16 XML boundaries, unsupported encoding, undeclared prefix, duplicate expanded QName through two namespace prefixes, descriptor identity/equality, and exactly one XML parse per worksheet.
- Frozen hashes verified: reader `6eea77cdda6f08bc9902810f54cff332123bad87`; fixture `83a56ee4f6f7a00a92cc577eb279377f50aba912`.
- Passed: direct A `17 passed`; original-plus-A `59 passed`; focused compatibility `442 passed`; full suite `1194 passed, 1 warning` (existing openpyxl unknown-extension warning); compile and `git diff --check` passed.
