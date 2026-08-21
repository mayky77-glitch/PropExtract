---
card_id: cgr-wave3-operation-log-v2b
status: frozen
version: 2
supersedes: cgr-wave3-operation-log-v2
work_id: cgr-wave3-operation-log-v2b
task_id: operation-log-v2b
purpose: "Implement a bounded private operation log from accepted projection authority without rejected or blocked log ancestry."
role: default
card_path: knowledge/tasks/cgr-wave3-operation-log-v2b.md
dependency_shas:
  - 72273832b67b8c09cd0011e49f55d4377af96bd2
branch: codex/cgr-wave3-operation-log-v2b
write_scope:
  - knowledge/tasks/cgr-wave3-operation-log-v2b.md
  - rns_import_server/operation_log.py
  - tests/test_operation_log.py
forbidden_paths:
  - README.md
  - rns_import_server/server.py
  - rns_import_server/static
  - rns_import_server/app.py
  - rns_import_server/job_report.py
  - rns_import_server/workbook_projection.py
  - rns_import_server/workbook_operation_journal.py
  - rns_import_server/new_row.py
  - rns_import_server/group_provisioning.py
contract_versions:
  input: workbook-projection-authority-v1
  output: operation-private-log-v2b
acceptance_commands:
  - PYTHONPATH=. python3 -m pytest -q tests/test_operation_log.py
  - python3 -m compileall -q rns_import_server/operation_log.py tests/test_operation_log.py
  - git diff --check
knowledge_paths:
  - knowledge/INDEX.md
  - knowledge/tasks/cgr-wave3-operation-log-v2b.md
  - knowledge/components/workbook-publication.md
  - knowledge/tasks/implement-construction-group-routing-20260820.md
---

# Operation-scoped private JSONL log V2b

## Frozen contract

- Implement new `rns_import_server/operation_log.py` and `tests/test_operation_log.py` from accepted base `72273832b67b8c09cd0011e49f55d4377af96bd2`. Rejected V1 common/log and blocked clean V2 planning ancestry are forbidden; no cherry-pick, merge, or source copying from them.
- Preserve public contract: injected trusted `%LOCALAPPDATA%/PropExtract` data root; exact output `logs/operations/<operation_id>.jsonl`; exact built-in canonical UUID; public receipt only `operation_id`, `log_saved`, and stable error code.
- Use finite typed event enums, canonical timestamp grammar, strict JSON without duplicate keys/non-finite values/default coercion, and exact normal/truncation history schemas. Never log capability, private path, raw OCR/PDF text, report/workbook payload, environment, credential, or secret values.
- Traverse injected-root ancestors and children descriptor-relatively with no-follow checks. Bind visible final path to opened inode. Missing `O_DIRECTORY`, `O_NOFOLLOW`, `fcntl`, secure permissions, locking, fsync, or replace capability returns `technical_log_unavailable`; no alternate-root, Temp, repo, operation-dir, or weaker fallback.
- Fsync every created directory entry, including injected-root parent. Preserve complete old-or-new canonical JSONL under write, cleanup, fsync, and replacement failures.
- Use one fixed per-operation temporary name under the same stable lock and capped operation directory. Never create UUID/attempt temp names. Stale temp must be verified/recovered deterministically or fail closed. Repeated cleanup failures must keep auxiliary file count and total operation bytes bounded.
- Enforce record and total per-operation caps across canonical JSONL plus all auxiliary artifacts. Deterministic truncation metadata must have exact coherent schema and physically possible strictly positive `dropped_bytes` and `dropped_records`; reject `0/0`, zero components, and contradictory tuples such as one byte for two records.
- Compact tests cover fixed-temp repeated cleanup failure, impossible truncation metadata, and preserved boundaries: finite enums, timestamp/history schema, exact UUID, ancestor/final symlink and inode races, missing platform capabilities, root-parent fsync, atomic framing/double failure, privacy and no fallback. POSIX proof never claims Windows DACL.

## Boundary

- No server/API/UI/publication/OCR/registry/journal/native Excel wiring.
- One implementation launch, zero retries. Independent P6 is terminal: reject means hard block.

