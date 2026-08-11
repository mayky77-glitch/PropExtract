---
type: orchestration-manifest
status: frozen
work_id: windows-native-executable-resolution-20260811
objective: Preserve an absolute Windows native executable path while keeping OCR data and model arguments ASCII-relative.
project_root: /Users/x/.codex/worktrees/40b0/Отдел организации работ с недвижимым имуществом
planning_parent_sha: a97c74749a3ca222de70d197979e8c48c7c866bd
wave: 1
max_parallel: 1
max_spawns: 1
max_retries: 0
merge_method: merge-no-ff
shared_paths_owner: integration
data_classification: restricted
created_at: 2026-08-11T17:00:00+08:00
---

# Gate 0 — Windows native executable resolution

## Baseline

- Local integration: `python3 -m pytest -q` passed 76 tests; compileall and diff checks passed.
- Windows run `31472528336`: source-archive install under a Cyrillic/metacharacter path passed, including runtime verification and repair.
- The Tesseract stdout probe then failed in `subprocess.run` with `FileNotFoundError: [WinError 2]` before native execution.

## Proven contract

- Python `CreateProcessW` receives the verified absolute executable path unchanged.
- Only file, model, output, cache, and scratch arguments consumed by legacy native tools are ASCII-relative to the contained OCR job workspace.
- Windows staging, cleanup, source preservation, runtime integrity, and Linux behavior stay unchanged.

## Ownership

- One P4 implementation stream owns `rns_import_server/ocr.py` and its focused resource-limit test.
- Integration owns workflow, packages, lock, docs, release, and knowledge consolidation.
- No private files or raw logs enter Git or orchestration state.

Exact card/base SHA is supplied after this frozen manifest and card are committed.
