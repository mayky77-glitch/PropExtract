---
card_id: cgr-wave3-authority-observability-foundation-v1-operation-log
status: frozen
version: 2
supersedes: null
work_id: cgr-wave3-authority-observability-foundation-v1
task_id: operation-log
purpose: "Write private, operation-scoped, capped LocalAppData JSONL logs with fail-closed typed unavailability."
role: developer
card_path: knowledge/tasks/cgr-wave3-authority-observability-foundation-v1-operation-log.md
dependency_shas:
  - 50bc3f7ebc2e307e253eb45f6145b7d2343338cf
branch: codex/cgr-wave3-operation-log-v1
write_scope:
  - knowledge/tasks/cgr-wave3-authority-observability-foundation-v1-operation-log.md
  - rns_import_server/operation_log.py
  - tests/test_operation_log.py
forbidden_paths:
  - README.md
  - rns_import_server/server.py
  - rns_import_server/static
  - rns_import_server/new_row.py
  - rns_import_server/group_provisioning.py
  - rns_import_server/workbook_projection.py
  - tests/test_workbook_projection.py
  - rns_import_server/workbook_operation_journal.py
  - rns_import_server/job_report.py
  - rns_import_server/app.py
contract_versions:
  input: publication-finalized-k3b2b2-v1
  output: operation-private-log-v1
acceptance_commands:
  - PYTHONPATH=. python3 -m pytest -q tests/test_operation_log.py
  - python3 -m compileall -q rns_import_server/operation_log.py tests/test_operation_log.py
  - git diff --check
knowledge_paths:
  - knowledge/INDEX.md
  - knowledge/tasks/cgr-wave3-authority-observability-foundation-v1-operation-log.md
  - knowledge/components/workbook-publication.md
  - knowledge/tasks/implement-construction-group-routing-20260820.md
---

# Operation-scoped private JSONL log

## Frozen contract

- Add a standalone port in `rns_import_server/operation_log.py`. Caller injects the trusted data root corresponding to `%LOCALAPPDATA%/PropExtract`; exact output is `<data-root>/logs/operations/<operation_id>.jsonl`.
- Accept only an exact built-in canonical UUID string for `operation_id`. Never derive a path from another identifier and never fall back to operation directories, repository paths, `%TEMP%`, or any alternate root.
- Create/traverse only private regular non-symlink directories and file. Reject symlink components, replacement races, non-regular targets, insecure existing objects, permission/DACL failures, parent-fsync failures, and secure-write failures with typed `technical_log_unavailable`.
- JSONL input is an explicit allowlisted event DTO. Strict JSON only: no `default=str`, NaN, arbitrary mappings/objects, raw exceptions, or silent coercion. Never record capability values/digests, raw OCR/PDF text, report payloads, workbook rows/cells, private paths, environment, credentials, or secrets.
- Enforce fixed per-record and per-operation byte caps. Preserve valid JSONL framing. When content or history is truncated, emit deterministic allowlisted truncation metadata with exact dropped counts/bytes; never leak truncated source bytes. Repeated equivalent input must produce deterministic serialized bytes apart from explicitly injected time/sequence authority.
- Public receipt exposes only exact `operation_id`, `log_saved`, and stable error code. It never exposes path, payload, exception text, permissions, or truncation source.
- Tests cover UUID subclasses/noncanonical spellings, strict JSON failures, caps and deterministic truncation, concurrent/replay-safe append behavior, symlink traversal/races, non-regular/insecure targets, and injected secure-write/fsync failures. POSIX mode assertions are local proof only; do not claim Windows DACL qualification.

## Stable boundary

- No server, UI, publication, report, OCR, registry, or journal wiring in this Gate.
- Any Windows DACL implementation/qualification beyond the portable strict port is an explicit downstream Gate, never inferred from POSIX tests.

