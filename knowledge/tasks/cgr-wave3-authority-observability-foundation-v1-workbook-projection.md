---
card_id: cgr-wave3-authority-observability-foundation-v1-workbook-projection
status: frozen
version: 2
supersedes: null
work_id: cgr-wave3-authority-observability-foundation-v1
task_id: workbook-projection
purpose: "Expose one immutable, read-only workbook snapshot for row routing and group provisioning without inventing workbook authority."
role: developer
card_path: knowledge/tasks/cgr-wave3-authority-observability-foundation-v1-workbook-projection.md
dependency_shas:
  - 50bc3f7ebc2e307e253eb45f6145b7d2343338cf
branch: codex/cgr-wave3-workbook-projection-v1
write_scope:
  - knowledge/tasks/cgr-wave3-authority-observability-foundation-v1-workbook-projection.md
  - rns_import_server/workbook_projection.py
  - tests/test_workbook_projection.py
forbidden_paths:
  - README.md
  - rns_import_server/server.py
  - rns_import_server/static
  - rns_import_server/new_row.py
  - rns_import_server/group_provisioning.py
  - rns_import_server/workbook_groups.py
  - rns_import_server/registry_storage.py
  - rns_import_server/workbook_operation_journal.py
  - rns_import_server/new_row_action_store.py
  - rns_import_server/operation_log.py
  - tests/test_operation_log.py
contract_versions:
  input: publication-finalized-k3b2b2-v1
  output: workbook-projection-authority-v1
acceptance_commands:
  - PYTHONPATH=. python3 -m pytest -q tests/test_workbook_projection.py tests/test_new_row_action.py tests/test_group_provisioning.py tests/test_workbook_group_publication.py
  - python3 -m compileall -q rns_import_server/workbook_projection.py tests/test_workbook_projection.py
  - git diff --check
knowledge_paths:
  - knowledge/INDEX.md
  - knowledge/tasks/cgr-wave3-authority-observability-foundation-v1-workbook-projection.md
  - knowledge/components/workbook-publication.md
  - knowledge/tasks/implement-construction-group-routing-20260820.md
---

# Workbook projection and authority boundary

## Frozen contract

- Add an authoritative read-only adapter in `rns_import_server/workbook_projection.py`. One immutable snapshot and one pre-hash must yield both existing `SheetProjection` and `GroupProvisioningProjection`; no save, rewrite, mutation, fallback, or second workbook read.
- Inspect accepted construction/binding storage and readers before choosing authority. Resolve target and workbook contract only from existing durable verified data when its source semantics are exact. Never normalize a path, infer identity from a filename/hash, or invent `target_path`/`workbook_contract_id`.
- If no existing durable producer exactly proves all required authority, define a strict immutable injected authority DTO/port. Keep the concrete producer absent and return a typed next-Gate blocker in handoff and knowledge delta. Do not broaden scope to implement it.
- Require exact built-in scalar types where authority depends on them. Validate canonical absolute target, regular file, no symlink in target or path components, exact target/workbook-contract/sheet/template evidence, and registry generation needed by both projections.
- Use read-only workbook loading and a before/read/after identity check that proves one stable source. Hash/read instability, replacement, symlink, malformed authority, sheet mismatch, template mismatch, unsupported cells, or I/O failure must return stable typed failure; no partial projection.
- Keep returned rows immutable and sufficient for existing `SheetRow` A:F ownership/template semantics and `ProvisioningRow` A:X+AA business/template semantics. Both projections must carry the same authority identity, pre-hash, generation, and source observation.
- Tests use synthetic workbooks plus a disposable copy of the real corpus only when available. Prove source and copy hashes/mtime/bytes stay unchanged. Never add private XLSX or its path/content to Git.

## Stable boundary

- Public API exposes only immutable authority/projection objects and typed codes/errors; paths remain private implementation authority.
- No bridge, server/API/UI/native Excel wiring. No workbook lock or publication claim.
- Handoff must state the exact unresolved authority producer decision, or prove the exact accepted durable producer and fields used.

