---
type: guide
status: ready
work_id: construction-group-routing-v1
last_verified: 2026-08-18
updated: 2026-08-18
tags:
  - task/planning
  - status/ready
  - domain/rns
  - knowledge/windows
links:
  - "[[orda-construction-group-routing-plan]]"
  - "[[orda-middle-row-insertion-plan]]"
  - "[[orda-performance-optimization-plan]]"
  - "[[../ORCHESTRATION|Orchestration]]"
---

# Волны Орды: construction-group-routing-v1

## Wave 1 — durable registry foundation

`cgr-registry-core`

- Role/route: database-engineer, P4, Terra/high.
- Scope: `rns_import_server/construction_registry.py`, `rns_import_server/registry_storage.py`, `rns_import_server/workbook_operation_journal.py`, `rns_import_server/data/construction_registry.seed.sqlite3`, `rns_import_server/data/construction_registry.seed.manifest.json`, `scripts/build_construction_registry_seed.py`, `scripts/validate_construction_registry_seed.py`, `tests/test_construction_registry.py`, `tests/test_registry_storage.py`, `tests/test_workbook_operation_journal.py`.
- Deliver: Windows data path, schema/migration, generation/CAS, CRUD/status, exact-start longest match, corruption/newer-schema behavior, migration backup, deterministic Git seed+manifest build/validation, provenance-aware seed→runtime reconciliation and generic `workbook_operation_journal` schema/API for group-provision/new-row publication.
- Acceptance: clean-copy bootstrap; untouched unbound seed update; local-only preservation; divergent edit conflict; bound seed name/code change→alignment conflict/no route change; untouched removal→archive; edited removal→conflict; crash rollback; Unicode/duplicates/status/stale/lock/corrupt/newer DB; deterministic digest and no writes into installed seed. Journal enforces unique operation/consumer identity, construction/RNS/target/generation, pair nonce, pre/staged/control/post/backup hashes, manifest/digests, legal CAS phases and independent finalization flags; candidate/post evidence is `synchronous=FULL` before replace and incomplete operations are restart-readable.

Wave 1 интегрируется и проверяется до запуска consumers.

## Wave 2 — three independent consumers

Все ветки начинаются от accepted Wave-1 SHA.

`cgr-object-routing`

- Role/route: developer, P3, Terra/medium.
- Scope: `rns_import_server/object_routing.py`, `tests/test_object_group_routing.py`.
- Deliver: raw name → construction route + tail, typed outcomes, boundary/longest matching; no app/server/workbook edits.

`cgr-workbook-groups`

- Role/route: developer, P4, Terra/high.
- Scope: `rns_import_server/workbook_groups.py`, `tests/test_workbook_group_routing.py`.
- Deliver: exact single-block resolver, group-first RNS match, global guard, blank-row/insertion-point plan and C consistency; no workbook mutation/HTTP/UI.

`cgr-registry-service`

- Role/route: developer, P3, Terra/medium.
- Scope: `rns_import_server/registry_admin.py`, `tests/test_registry_admin_service.py`.
- Deliver: validated draft/provision/status service projection, generation conflicts and active-job gate; bound name/code PATCH is rejected, draft is never routable; no server/static edits.

Integration order: object routing → workbook groups → registry service, each `merge --no-ff`; then focused + combined contracts and one accepted integration SHA.

## Wave 2B — native structural insertion engine

`cgr-row-insertion-engine`

- Role/route: developer, P4, Terra/high.
- Depends: accepted Wave-2 SHA, especially workbook-group contract.
- Scope: `rns_import_server/group_row_insertion.py`, `rns_import_server/excel_native.py`, `rns_import_server/workbook_structure.py`, `rns_import_server/workbook_mutation_manifest.py`, `rns_import_server/workbook.py`, `rns_import_server/data/construction_group_template.v1.xlsx`, `scripts/windows_excel_insert.ps1`, `tests/test_group_row_insertion.py`, `tests/test_excel_native_contract.py`, `tests/test_workbook_mutation_manifest.py`, `tests/test_workbook_group_publication.py`.
- Deliver: consume the accepted Wave-1 journal API; staged PowerShell/Excel COM insertion before next header, existing-blank fill, same-group template/formula transfer, ordinal A rebase, paired same-build no-insert control, formula/dashboard/CF/x14/DV/filter/name semantic validator, early durable PID/HWND lease+ACK, typed failure/recovery envelope and operation-specific recovery hooks. This card does not alter DB schema or history/report files.
- Acceptance: no direct `openpyxl.insert_rows`; original→control admits only proven Excel normalization/cache changes and candidate→control proves the insertion manifest; no-Excel/unsupported/timeout is byte-exact pre-publication fail; before-open/open/insert/calc/save hang injection closes only leased Excel; every injected branch returns verified `recovered` or typed failure with stage/cause evidence, never silent success/no-op; mocked contracts pass cross-platform; actual Windows Excel gate proves native insertion/recalc/no repair.

Wave 2B интегрируется отдельно; Wave 3 начинается только от its accepted SHA.

## Wave 3 — user action and presentation

`cgr-new-row-action`

- Role/route: developer, P4, Terra/high.
- Depends: accepted Wave 2B.
- Scope: `rns_import_server/new_row.py`, `tests/test_new_row_action.py`, `tests/test_new_row_concurrency.py`.
- Deliver: pending IDs, suffix validation, full-C/name consistency, one-shot blank-fill/native-insert reservation, group/RNS re-resolution under publication lock and one generic-journal operation request/result. Pre-hash restart requires re-resolution/re-authorization; post-hash resumes finalization and never inserts twice. Ни одна engine failure не преобразуется в empty/success result.

`cgr-group-provisioning`

- Role/route: developer, P4, Terra/high.
- Depends: accepted Wave 2B + registry service.
- Scope: `rns_import_server/group_provisioning.py`, `tests/test_group_provisioning.py`, `tests/test_group_provisioning_recovery.py`.
- Deliver: validate name/code/XLSX form and orchestrate accepted Wave-2B engine with draft/binding state through the same accepted generic journal, first-free-row header + one bootstrap, publication and hash-driven recovery; propagate typed failure/recovery without catch-and-continue; no schema/native engine/server/static edits.
- Acceptance: current fixture starts new header at first free business row 606, not 1002; no capacity/continuation; later object in an older block is physically inserted before its next header; recovery/backup/formula oracle pass.

`cgr-ui`

- Role/route: designer, P4, Terra/high.
- Depends: frozen public API contract + accepted Wave 2B outcomes.
- Scope: `rns_import_server/static/index.html`, `rns_import_server/static/app.js`, `rns_import_server/static/app.css`, new `rns_import_server/static/registry.html`, `rns_import_server/static/registry.js`, `tests/browser_registry_smoke.py`, `tests/browser_smoke.py`.
- Deliver: registry page, capacity-free group-provision form/preview/recovery and pending-new-row card; Russian Excel-required/structural-failure states; every failure shows what failed, next step, error code, operation ID and whether/where a technical log was saved; post-hash recovery is not shown as a retryable insert. Verify 1440/768/480, keyboard/focus, light/dark, leading-zero proof; no backend edits.

Три задачи параллельны и не делят paths.

## Wave 4 — shared wiring

`cgr-server-integration`

- Role/route: developer, P4, Terra/high.
- Depends: accepted Wave 3 SHA including group provisioning.
- Scope: `rns_import_server/server.py`, `rns_import_server/app.py`, `rns_import_server/ocr.py`, `rns_import_server/job_report.py`, `rns_import_server/action_history.py`, `tests/test_admin_server.py`, `tests/test_admin_edit_integration.py`, `tests/test_critical_fallback_contract.py`.
- Deliver: load registry snapshot, route each logical RNS, preserve current comparison/proposals, serve registry assets/API, wire provision/recovery and pending action, serialize publication/report/history, safe Russian public states. Startup dispatches incomplete generic-journal operations; capability/binding/history/report finalize independently and idempotently by operation ID. Central failure boundary preserves exception chain/HRESULT/WinError/stage/hashes in LocalAppData technical log, falls back boundedly to operation-dir/Temp, and never converts failure into success/no-op. It also logs report-write/per-PDF/edit-setup/history/retry-exhaustion failures and records the exact causal reason for text-layer→raster recovery without logging PDF text.
- Must incorporate accepted pre-feature UI closeout from Gate 0 and never overwrite it.

## Wave 5 — functional Windows acceptance

`cgr-windows-acceptance`

- Role/route: tester, P3, Terra/medium.
- Scope: `scripts/windows_end_to_end_smoke.py`, `tests/test_windows_remediation_integration.py`, `tests/test_windows_installer_contract.py`; workflow only if existing triggers cannot execute the new smoke.
- Deliver: source archive contains seed/template/COM adapter; registry/block routing, bootstrap fill and native middle insert, formula/dashboard oracle, new suffix action, backup/no-op/stale/locked/no-Excel paths, reinstall/repair preserving DB. Fault matrix proves each fallback either restores the full oracle or returns a clear Russian error plus correlated technical record; no swallowed failure or false success.

Final functional reviewer: read-only reviewer, P6 Sol/high. Проверяет requirements, ancestry/scopes, DB migration, group/RNS semantics, mutation manifest, concurrency, Windows behavior and rollback. После ACCEPT фиксируется immutable functional SHA. Substantive finding получает одну bounded remediation card; cosmetic/security expansion без product defect пропускается.

## После functional work ID

Только после immutable functional SHA создаётся отдельный benchmark work ID по [[orda-performance-optimization-plan]]. Если profiling докажет bottleneck, отдельный optimization work ID получает собственный planning commit и exact cards. После accept/skip создаётся final Windows qualification work ID от точного candidate SHA. Так ни одна карточка не зависит от ещё неизвестного SHA.

## Acceptance matrix

### Registry/routing

- exact official prefix; punctuation/space boundary; longest nested name;
- unknown, duplicate normalized name/code, archived construction;
- DB restart, migration rollback, corrupt/newer schema, bounded lock;
- tracked seed digest/revision, first-run bootstrap, deterministic promotion and update merge preserving local entries;
- seed provenance cases: untouched unbound update, divergent edit conflict, bound name/code alignment conflict, local-only preservation, removal/archive and crash rollback;
- no fuzzy fallback and no private content in diagnostics.

### Existing row

- same RNS in two groups: selected group wins when it contains exactly one row;
- missing or repeated target header is review/no mutation; DB stores no row coordinates and restart rescans semantic block boundaries;
- needed-code row under another construction header is structural conflict/no mutation;
- no inside match + outside match: review/no duplicate;
- multiple inside: review/no mutation;
- tail equal: byte-level no-op;
- tail different: current admin name comparison and approval, no automatic overwrite/move;
- directive-only absent row remains review-only.
- pending/action history never trusts an old physical row after structural insertion: construction + canonical RNS + field/action are re-resolved; missing/ambiguous identity is visible stale failure with technical event.

### New row

- no row exists before suffix submit;
- `0001` preserves leading zeros and writes full C;
- invalid suffix/replay/stale hash/stale registry/no-Excel/structural failure leave workbook byte-exact;
- repeated C + equal D allowed; repeated C + different D blocked;
- validated blank row is filled in place; otherwise exactly one row is inserted before next header and filled, so it remains inside original group;
- old rows below insertion map to `+1`; values/styles/links persist, A ordinals deterministically rebase, Y/Z retain equivalent R1C1 formulas, dashboard ranges/totals expand correctly;
- paired no-insert native control isolates full-rebuild/cache/package normalization; a fixture with deliberately stale unrelated cached formulas cannot hide an insertion-specific formula/total error;
- sequential/concurrent pending actions and existing proposal/manual edit cannot overwrite each other;
- backup hash equals pre-action workbook; source PDFs remain unchanged.

### New group

- required name/code/workbook validation with no capacity field; plain PATCH cannot create/activate draft route or rename/recode bound entry; reactivation revalidates binding; no provisioned active record before valid XLSX segment;
- header + one bootstrap row begin at first validated free business row (606 in current fixture); after bootstrap fill no automatic reserve/continuation is created;
- later growth of any non-last group uses native insertion before its next header; concurrent boundary changes are replanned under lock;
- formulas/styles/hyperlinks, native CF/x14, validation, autoFilter, defined ranges, merges/tables/print settings pass exact manifest checks;
- logical old formulas remain equivalent under row mapping; new-row relative refs target itself, absolute/named refs remain fixed; dashboard ranges include insertion; native Excel full rebuild has no new errors/repair;
- stale hash/generation, duplicate name/code, unavailable Excel, unsupported structure and injected DB/XLSX/COM failures are idempotent; recovery uses exact phase-aware pre/post/third-hash matrix. Crash after COM save, durable post-hash, replace or any history/report flag yields one row and one logical action;
- approved registry seed promotion is deterministic and shipped in a clean source archive; runtime admin DB remains writable only in LocalAppData.

### UI/Windows

- registry add/edit/archive/restart;
- pending card at 1440/768/480, light/dark, keyboard and error recovery;
- missing Excel, COM timeout, formula mismatch, stale workbook, DB/report/log failure and exhausted retry each have stable error code, useful Russian next step, operation ID and local technical evidence; recovered state is distinguishable from failure and from ordinary success;
- injected exceptions cannot yield empty success/no-op. If primary and fallback log sinks both fail, UI explicitly reports `technical_log_unavailable` while preserving target state;
- pdftotext unavailable/timeout/nonzero/empty → raster carries a typed causal trace; successful raster is recovered, while raster/whole-document failure has a visible document card plus correlated log and does not hide successful independent PDFs;
- report-write, manual-edit setup, stale/corrupt history and exhausted file-lock retry preserve their existing user warning/error and add causal technical evidence including attempt/last OS error where applicable;
- portable runtime imports sqlite without network/system Python/PATH/UAC;
- LocalAppData path supports Cyrillic; app update/repair does not erase DB;
- installed Excel 365 x64 native run inserts before each group header and closes only the PID proven by early nonce/HWND/PID/creation-time lease+ACK; hang injection at each COM phase and a pre-opened user Excel prove safe cleanup. Hosted runner without Office proves byte-exact safe refusal;
- functional Windows hosted smoke passes before immutable functional SHA; final exact-main release smoke occurs in the later qualification work ID. macOS tests alone do not release.

## Integration and rollback

- Every block branch starts at exact wave base, returns feature SHA/evidence and becomes immutable after handoff.
- Integration owner verifies scope/ancestry and merges only `--no-ff`; no cherry-pick/rebase/force-push after handoff.
- Each accepted merge records feature SHA + integration SHA. Next-wave cards exist in its exact base.
- Failed task/wave does not open dependents. One retry maximum; recurring no-progress follows Orda circuit.
- Code rollback is merge revert. No destructive Git reset.
- Workbook rollback uses existing verified pre-action backup; report failure does not undo an already verified XLSX publication.
- DB migration is transactional with verified pre-migration backup. Older code must ignore, not downgrade/delete, a newer DB.
- Seed rollback reverts the code/seed merge commit; it never replaces operator runtime DB. Generic workbook-operation journal reconciles partial XLSX/DB/history/report completion without destructive reset or repeated insertion.
- После accepted release: update vault, mark Orda completed/validate, then run scoped dead-soul-harvest. Cleanup failure не отменяет принятый release.
