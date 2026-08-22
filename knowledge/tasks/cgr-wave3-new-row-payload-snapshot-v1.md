---
card_id: cgr-wave3-new-row-payload-snapshot-v1
status: frozen
version: 2
supersedes: null
work_id: cgr-wave3-new-row-payload-snapshot-v1
task_id: new-row-payload-snapshot
purpose: "Define a strict immutable NewRow mutation payload and memory-only sanitized final report snapshot without wiring publication or lifecycle."
role: developer
card_path: knowledge/tasks/cgr-wave3-new-row-payload-snapshot-v1.md
dependency_shas:
  - a2fff925f05def1e7ba55ce0ec50f6c55dc13531
branch: codex/cgr-wave3-new-row-payload-snapshot-v1
write_scope:
  - knowledge/tasks/cgr-wave3-new-row-payload-snapshot-v1.md
  - rns_import_server/new_row_payload.py
  - rns_import_server/group_row_insertion.py
  - rns_import_server/workbook_mutation_manifest.py
  - rns_import_server/job_report.py
  - tests/test_new_row_payload.py
  - tests/test_group_row_insertion.py
  - tests/test_workbook_mutation_manifest.py
  - tests/test_new_row_job_report.py
forbidden_paths:
  - README.md
  - rns_import_server/server.py
  - rns_import_server/app.py
  - rns_import_server/static
  - rns_import_server/registry_storage.py
  - rns_import_server/new_row.py
  - rns_import_server/new_row_action_store.py
  - rns_import_server/workbook_operation_journal.py
  - rns_import_server/workbook_authority.py
  - rns_import_server/workbook_authority_refresh.py
  - rns_import_server/workbook_projection.py
  - rns_import_server/workbook_finalization.py
  - rns_import_server/workbook_finalization_snapshot.py
  - rns_import_server/workbook_groups.py
  - rns_import_server/excel_native.py
  - rns_import_server/operation_log.py
  - rns_import_server/data
contract_versions:
  input: imported-new-row-state-v1
  output: strict-new-row-payload-snapshot-v1
acceptance_commands:
  - PYTHONPATH=. python3 -m pytest -q tests/test_new_row_payload.py tests/test_group_row_insertion.py tests/test_workbook_mutation_manifest.py tests/test_new_row_job_report.py tests/test_report_observability.py
  - python3 -m compileall -q rns_import_server/new_row_payload.py rns_import_server/group_row_insertion.py rns_import_server/workbook_mutation_manifest.py rns_import_server/job_report.py tests/test_new_row_payload.py tests/test_group_row_insertion.py tests/test_workbook_mutation_manifest.py tests/test_new_row_job_report.py
  - git diff --check
knowledge_paths:
  - knowledge/INDEX.md
  - knowledge/tasks/cgr-wave3-new-row-payload-snapshot-v1.md
  - knowledge/components/workbook-publication.md
---

# NewRow payload and snapshot contract

## Frozen boundary

- Start only from accepted `a2fff925f05def1e7ba55ce0ec50f6c55dc13531`. Rejected lifecycle/WA2/WA2b/log tips are evidence only and forbidden ancestry or source input.
- Own only the four production modules, four writable focused test modules and this card. `new_row_payload.py` and its focused tests are new. Existing report-observability tests may run but must not be edited.
- No server/app, DB/schema/seed, action lifecycle, authority/refresh/finalizer, native/PowerShell, UI, logging, journal orchestration or publication wiring.

## Immutable payload

- Introduce an immutable injected `ImportedNewRowState`; construction must deep-copy/freeze caller-owned imported state so later source mutation cannot change a produced payload or report.
- Build the mutation payload from the exact action identity, construction identity, canonical RNS and object tail. Overlay only resolution-authoritative C, D and F. W must carry the exact display value and exact target value as separate bound evidence.
- Payload cell keys accept exact built-in integers for columns `1..24` and `27` only. Reject `25`, `26`, values above `27`, booleans masquerading as integers, duplicate/coercible keys and non-integer keys.
- Values must be strict JSON data without implicit conversion: reject non-finite numbers, unsupported objects, non-string mapping keys, and any string whose first non-whitespace character is `=`, `+`, `-` or `@`. Never use `default=str` or normalize forbidden content.
- Payload construction is pure and pre-journal: no directory, file, snapshot, native process, capability, report publication or workbook mutation.

## Group evidence and manifest

- Tighten group-row evidence and workbook mutation manifest validation to the identical exact column/value allowlist. No weaker legacy path may admit Y/Z, columns above AA, boolean keys, formula-looking text or non-strict JSON values.
- Canonical serialization/digest replay must be stable and bind the exact accepted payload/evidence; contradictory replay fails typed rather than rewriting or coercing.

## Memory-only final report snapshot

- Add a memory-only producer in `job_report.py` that returns a deep-copied sanitized final report derived only from the injected imported state and strict payload result.
- The snapshot must contain no `Path`, file/directory authority, raw report bytes, capability, OCR payload or other private/raw source object. It performs no disk read/write and preserves the caller source byte-for-byte/object-for-object.
- Canonical exact replay yields the same detached data without aliasing. Invalid/non-JSON/private values fail typed; no persistence or restart claim.

## Explicit blockers

- Do not decide the A-column ordinal, date transport/format, JobManager/server wiring, report UI semantics or restart persistence. Keep each as an explicit typed downstream blocker; do not infer or silently default it.

## Essential compact tests

- Exact payload binds action/construction/RNS/object tail, overlays C/D/F, and binds W display plus target; source mutations after construction do not affect it.
- Parametrized hostile keys/values reject Y/Z, >AA, booleans, nonfinite/non-JSON values and formula-looking strings before any side effect.
- Group evidence and manifest enforce the same allowlist and stable canonical digest/replay; contradictory evidence fails typed.
- Memory-only report is detached, sanitized and canonical; spies prove no Path/disk/native/journal/report/capability/OCR access and input remains unchanged.
- Explicit unresolved A/date/wiring/UI/restart concerns return typed blockers rather than inferred content.

## Gate

- One P4 implementation attempt, at most one localized remediation, then independent P6. No integration before terminal acceptance; rejection blocks this Gate.
