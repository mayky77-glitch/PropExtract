---
card_id: cgr-wave3-operation-log-v2
status: frozen
version: 2
supersedes: cgr-wave3-authority-observability-foundation-v1-operation-log
work_id: cgr-wave3-operation-log-v2
task_id: operation-log-v2
purpose: "Implement a bounded private operation log without rejected V1 ancestry or unbounded auxiliary artifacts."
role: worker
card_path: knowledge/tasks/cgr-wave3-operation-log-v2.md
dependency_shas:
  - 72273832b67b8c09cd0011e49f55d4377af96bd2
branch: codex/cgr-wave3-operation-log-v2
write_scope:
  - knowledge/tasks/cgr-wave3-operation-log-v2.md
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
  output: operation-private-log-v2
acceptance_commands:
  - PYTHONPATH=. python3 -m pytest -q tests/test_operation_log.py
  - python3 -m compileall -q rns_import_server/operation_log.py tests/test_operation_log.py
  - git diff --check
knowledge_paths:
  - knowledge/INDEX.md
  - knowledge/tasks/cgr-wave3-operation-log-v2.md
  - knowledge/components/workbook-publication.md
  - knowledge/tasks/implement-construction-group-routing-20260820.md
---

# Operation-scoped private JSONL log V2

## Frozen contract

- Reimplement `rns_import_server/operation_log.py` from accepted base `72273832b67b8c09cd0011e49f55d4377af96bd2`. Do not copy, cherry-pick, merge, or depend on rejected V1 log/common ancestry.
- Preserve public contract: injected trusted `%LOCALAPPDATA%/PropExtract` data root; exact output `logs/operations/<operation_id>.jsonl`; exact built-in canonical UUID; public receipt contains only `operation_id`, `log_saved`, and stable error code.
- Use finite typed event enums, canonical timestamp grammar, strict JSON without duplicate keys/non-finite values/default coercion, and exact normal/truncation history schemas. Never log capability, private path, raw OCR/PDF text, report/workbook payload, environment, credential, or secret values.
- Traverse injected-root ancestors and all children descriptor-relatively with no-follow checks. Bind visible final path to the opened inode. Missing `O_DIRECTORY`, `O_NOFOLLOW`, `fcntl`, secure permissions, fsync, or locking capability returns typed `technical_log_unavailable`; no alternate-root, Temp, repo, operation-dir, or weaker fallback.
- Fsync every newly created directory entry, including injected-root parent. Preserve complete old-or-new canonical JSONL under write/cleanup/fsync/replacement failure.
- Use one fixed per-operation temporary name inside the same locked and capped operation directory. Never create UUID or attempt-specific temp names. A stale temp is within the same operation cap and must be verified/recovered deterministically or fail closed; repeated cleanup failure must keep auxiliary file count and total operation bytes bounded.
- Enforce fixed record and total per-operation caps across canonical JSONL plus every auxiliary artifact. Deterministic truncation marker must have a coherent exact schema and physically possible strictly positive `dropped_bytes` and `dropped_records`; reject impossible `0/0`, zero component, or contradictory count/byte history.
- Tests stay compact and cover the prior nine closed boundaries plus fixed-temp repeated cleanup failures and impossible truncation metadata. POSIX evidence is local proof only and never a Windows DACL claim.

## Boundary

- No server/API/UI/publication/OCR/registry/journal/native Excel wiring.
- One implementation attempt. Independent P6 is terminal: reject means hard block with no remediation loop.

