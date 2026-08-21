---
card_id: cgr-wave3-workbook-authority-wa1
status: frozen
version: 1
work_id: cgr-wave3-workbook-authority-wa1
task_id: workbook-authority-wa1
purpose: "Add explicit durable workbook authority enrollment and a projection authority producer without inference or runtime wiring."
role: default
card_path: knowledge/tasks/cgr-wave3-workbook-authority-wa1.md
dependency_shas:
  - 72273832b67b8c09cd0011e49f55d4377af96bd2
branch: codex/cgr-wave3-workbook-authority-wa1
write_scope:
  - knowledge/tasks/cgr-wave3-workbook-authority-wa1.md
  - rns_import_server/registry_storage.py
  - rns_import_server/workbook_authority.py
  - rns_import_server/workbook_projection.py
  - rns_import_server/data/construction_registry.seed.sqlite3
  - rns_import_server/data/construction_registry.seed.manifest.json
  - tests/test_registry_storage.py
  - tests/test_workbook_authority.py
  - tests/test_workbook_projection.py
forbidden_paths:
  - README.md
  - rns_import_server/server.py
  - rns_import_server/static
  - rns_import_server/app.py
  - rns_import_server/operation_log.py
  - rns_import_server/workbook_operation_journal.py
  - rns_import_server/new_row.py
  - rns_import_server/group_provisioning.py
  - rns_import_server/workbook_groups.py
contract_versions:
  input: workbook-projection-authority-v1
  output: durable-workbook-authority-v1
acceptance_commands:
  - PYTHONPATH=. python3 -m pytest -q tests/test_registry_storage.py tests/test_workbook_authority.py tests/test_workbook_projection.py
  - python3 -m compileall -q rns_import_server/registry_storage.py rns_import_server/workbook_authority.py rns_import_server/workbook_projection.py tests/test_registry_storage.py tests/test_workbook_authority.py tests/test_workbook_projection.py
  - git diff --check
knowledge_paths:
  - knowledge/INDEX.md
  - knowledge/tasks/cgr-wave3-workbook-authority-wa1.md
  - knowledge/components/workbook-publication.md
  - knowledge/tasks/implement-construction-group-routing-20260820.md
---

# Workbook authority WA1

## Frozen contract

- Start only from accepted projection common `72273832b67b8c09cd0011e49f55d4377af96bd2`. Rejected operation-log branches and commons are forbidden ancestry; do not cherry-pick or copy from them.
- Advance registry schema v5 to v6 with an empty migration and deterministic v6 seed/manifest. Add durable `workbook_authorities` enrollment. Migration and seed contain no fabricated authority, inferred identity, inferred path, ownership backfill, or real-corpus claim.
- Enrollment is strict insert-or-exact-replay. Persist canonical absolute regular non-symlink target path plus exact workbook contract ID, target identity, sheet identity, template version, lowercase source SHA-256, exact row-3 A:X template evidence, and exhaustive explicit row ownership for `1..max_row`. Ownership is trusted caller evidence only; even all-false evidence must be explicitly supplied.
- Validate strict JSON structure, finite field sets/types, evidence digest/count/range, canonical path and source identities. Corrupt stored JSON/digest/count and conflicting/concurrent enrollment fail closed without replacing the first authority.
- Implement a concrete read-only producer for `WorkbookProjectionAuthorityPort`. In one consistent registry snapshot, join the pending new-row action, its exact authority, optional exact construction binding, and registry generation. Require tuple identity/generation consistency; never infer from filename, path, hash, sheet contents, or optional binding absence.
- Extend the projection read boundary so the enrolled expected source SHA-256 must equal the digest of the exact descriptor-bound bytes parsed by OpenPyXL. Mismatch returns a typed failure with no projection.
- Preserve workbook bytes and metadata. Any disposable real-copy test reads only a private copy and must not enroll or commit private XLSX data.

## Essential acceptance

- v5→v6 migration is empty and fabricates no authority; deterministic seed/manifest are v6.
- Exact enrollment replay is no-write; conflict and concurrent conflicting enrollment preserve the first tuple.
- Reject relative/non-canonical/missing/symlink/non-regular paths, malformed identity/hash/template evidence, and missing/partial/duplicate/out-of-range ownership.
- Producer proves the exact pending-action/authority/optional-binding/generation tuple and rejects mismatch/missing/corrupt state.
- Corrupt JSON, digest/count/range mismatches fail closed; projection rejects source hash mismatch.
- Focused tests prove descriptor-bound read-only behavior and disposable-copy immutability without claiming real-corpus enrollment.

## Boundary

- No WA2 refresh/re-enrollment policy, bridge, server/API/UI, operation log, native Excel, OCR/report payload, fallback path, or automatic authority discovery.
- One P4 implementation worker. Independent P6 review may authorize at most one localized remediation in the same frozen scope; otherwise WA1 blocks.
