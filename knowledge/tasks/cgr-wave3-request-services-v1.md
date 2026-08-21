---
type: task
status: implemented
work_id: cgr-wave3-request-services-v1
tags: [task/implementation, feature/construction-routing, status/implemented]
last_verified: 2026-08-21
updated: 2026-08-21
---

# Wave3 request services — frozen Gate card

Accepted dependency/base is exact `576272ae6b92c68874b0858cc796592c548a79b0`. Branch `codex/cgr-wave3-request-services-v1`; P4 developer; independent P6 before integration.

## Scope

- add `rns_import_server/new_row.py`
- add `rns_import_server/group_provisioning.py`
- add `tests/test_new_row_action.py`
- add `tests/test_new_row_concurrency.py`
- add `tests/test_group_provisioning.py`
- this card

No server/UI/HTTP, native Excel/PowerShell, journal/storage schema, existing group-row engine, registry implementation, PDF/XLSX/source data or fallback changes.

## Contract

Implement planning/validation/reservation services only through injected pending/projection/publisher ports. Suffix is exact ASCII `^[0-9]{4}$`; server forms `code_prefix + "." + suffix` and preserves leading zeros. Under reservation, re-run accepted `resolve_workbook_group`; equal-D duplicate C is allowed, different-D returns existing `object_code_name_conflict`. Pending state is CAS `pending -> publishing`; concurrent submit calls publisher exactly once, loser returns `pending_already_reserved`. Reopen pending only after proven pre-hash failure; unknown/post-hash state stays closed.

Group provisioning must call existing `RegistryAdminService` to create a draft; draft never becomes routable/active in this Gate. Plan two consecutive validated blank/preformatted rows. First-free is one plus last nonempty business value in A:X/AA, never worksheet max-row; with business data through 605 and formula tail through 1001 choose header 606/bootstrap 607. No mutation or success claim: injected publisher may return a typed planning/publication result, but native `group_provision` bridge is a later Gate. No silent fallback, fake success, generic suffix normalization or append-to-end shortcut.

## Acceptance

1. `0001` yields exact full C; Unicode/width/sign/whitespace digits fail before publisher;
2. equal-D duplicate C accepted, different-D exact conflict;
3. two concurrent submits: one publisher call, one typed reservation conflict;
4. draft+plan chooses 606/607 and draft stays non-routable; stale generation creates no second draft;
5. restart before journal replans a draft from fresh hash/generation; pending action requires new job authorization.

Keep tests compact and interface-driven. Run three direct tests, relevant registry/group/journal regressions, full pytest once, compile new modules, diff check, exact scope/ancestry/identity/clean. This Gate does not qualify XLSX mutation, native Excel, recovery, HTTP/UI or operator success.

## Implementation evidence

- Added port-only `new_row` and `group_provisioning` services. Both require
  injected projections and CAS pending ports; neither opens or mutates XLSX.
- `NewRowService` admits only ASCII four-digit suffixes, forms C on the server,
  resolves after its reservation, and reopens solely after typed pre-hash proof.
- `GroupProvisioningService` creates a RegistryAdminService draft, plans two
  validated rows from A:X/AA business occupancy, and leaves the draft unroutable.
- Focused coverage: 5 new tests and 35 related registry/group/journal
  regressions passed. Full pytest ran 1,509 passing; 10 existing loopback HTTP
  tests are sandbox-blocked at socket bind (`PermissionError`).
