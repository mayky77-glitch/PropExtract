---
type: orchestration-manifest
status: frozen
work_id: windows-unicode-native-bridge-20260811
objective: Eliminate Cyrillic paths from legacy native-tool arguments while preserving source PDF files and offline runtime integrity.
project_root: /Users/x/.codex/worktrees/40b0/Отдел организации работ с недвижимым имуществом
planning_parent_sha: cf741ff1046c2d84e50301668c658c2ff3588e8b
wave: 1
max_parallel: 1
max_spawns: 2
max_retries: 1
merge_method: merge-no-ff
shared_paths_owner: integration
data_classification: restricted
created_at: 2026-08-11T16:05:00+08:00
---

# Gate 0 — Windows Unicode native bridge

## Baseline

- `python3 -m pytest -q`: 74 passed, one known synthetic OpenPyXL warning.
- `compileall`, JavaScript check, YAML parse and `git diff --check`: passed.
- Windows run `31471224762`: VC ZIP extraction under a Cyrillic source-archive path passed; Tesseract `--list-langs` failed because absolute `TESSDATA_PREFIX` became `?????` at the PowerShell 5.1/native boundary.

## Shared contracts

- `ocr.read(pdf, dpi, max_pages) -> (text, total)` remains unchanged.
- Source PDF bytes/path remain unchanged; any bridge copy is temporary, ASCII-named, bounded to one document, and cleaned on success/failure.
- Native executable trees and artifact SHA/full-tree verification remain unchanged.
- Windows behavior changes only at native arguments/environment/cwd; Linux remains direct and system-tool compatible.

## Ownership

- One P4 implementation stream owns the OCR/native bridge and its focused tests.
- Integration owns workflow, package lock, README, release/history cleanup, acceptance, and knowledge consolidation.
- No private PDF/XLSX/log/image contents may enter task state, prompts, tests, or Git.

Exact planning/card/base SHAs are supplied to the Orda runtime envelope after this frozen manifest/card commit; they are intentionally not self-referential YAML fields.
