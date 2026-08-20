---
card_id: cgr-opc-v6-package-graph-v2
status: review
version: 2
work_id: cgr-opc-package-graph-v2-20260820
task_id: package-graph-v2
purpose: Build a deterministic ZIP package graph from accepted strict Unicode URI/XML primitives.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
launch_status: inherited
actual_model: unknown
actual_reasoning_effort: unknown
fallback_reason: collaboration runtime did not expose launch override confirmation
planning_parent_sha: 332ad6076ed6135bb53f592377a99ac18767a586
dependency_shas: [d31d974551c44e9ae6b91b4e629362ffcb50a5b4, 4ce7f5b296721ebdc0b188d138b7c380602ffb03, bfb0065ce4c8915dc5163b74e3b841bd72bab5c9]
branch: codex/cgr-opc-package-graph-v2
card_path: knowledge/tasks/cgr-opc-v6-package-graph-v2.md
write_scope: [rns_import_server/opc_package_graph.py, tests/test_opc_package_graph.py, knowledge/tasks/cgr-opc-v6-package-graph-v2.md]
forbidden_paths: [rns_import_server/opc_part_uri.py, rns_import_server/opc_relationship_xml.py, tests/opc_package_v6_corpus.py, tests/test_opc_package_v6_corpus.py, tests/fixtures/opc-package-v6, knowledge/tasks/cgr-opc-v6-package-graph.md, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_opc_package_graph.py tests/test_opc_part_uri.py tests/test_opc_relationship_xml.py tests/test_opc_package_v6_corpus.py", "python3 -m pytest -q", "git diff --check"]
---

# OPC package graph v2

Implement fresh from accepted integration `332ad60`; do not merge, cherry-pick, import, or copy rejected graph v1/V5 code.

## Public contract

- Export frozen records `PackagePart`, `PackageRelationship`, `OPCPackageGraph`, typed `OPCPackageGraphError`, and `build_opc_package_graph(package_path)`.
- Error tuple is exactly `(code, subject, field, detail)`. No native exception leak, generic catch, silent skip, partial graph, warning-only result, or false success.
- Preserve ZIP member order and relationship XML order. Records retain relationship-part, source (`None` for package root), Id, Type, raw Target, TargetMode, and resolved Internal target; External has no resolved package part.

## Package rules

1. Read a path as ZIP without extraction. Narrowly map unreadable path (including embedded NUL), non-ZIP, encrypted member, unsupported XML encoding, CRC/bad member, and XML failures to stable typed graph errors.
2. Require exactly one canonical `[Content_Types].xml` with well-formed exact OPC content-types root. Put the raw control member into the same canonical collision ledger as every other member before excluding it from returned parts: exact duplicates and aliases such as `[Content_Types].%78ml` must fail.
3. Canonicalize all members with accepted `opc_part_uri`; reject directory entries, exact duplicates, and normalized aliases before graph construction.
4. Recognize `_rels/.rels`, root-source `_rels/<filename>.rels` → `<filename>`, and nested `<directory>/_rels/<filename>.rels` → `<directory>/<filename>`. Any other `.rels` location fails; every non-root source must exist.
5. Parse relationships only with accepted `parse_relationship_xml`; convert typed errors without losing code/context/detail. Resolve Internal targets with `resolve_relative_part_uri`; require target presence. External URI-references remain external.
6. Internal relationships may not target `[Content_Types].xml` or a relationship part. Recognize canonical percent aliases of the content-types control name and classify them `forbidden-internal-target`, not missing.

## Required verification

- Valid root/nested/root-level-source relationships; missing source/target; external relative/rooted/network/absolute; Unicode source/target; exact duplicate/percent alias including content-types alias; root escape; misplaced `.rels`; invalid content-types root; corrupt/non-ZIP/encrypted/unsupported-encoding/NUL path; deterministic order; immutable records.
- Replay every accepted independent V6 corpus fixture by its `expected_mutations`, without fixture-name branches: all empty-mutation cases including Unicode succeed; every invalid case fails with stable first category and context derived from bytes.
- Regression commands pass. Human commit/push; no merge, rebase, amend, force-push, or unrelated edits.

## Implementation evidence

- Fresh v2 graph implementation and focused regression suite added in the reserved paths only.
- `python3 -m pytest -q tests/test_opc_package_graph.py tests/test_opc_part_uri.py tests/test_opc_relationship_xml.py tests/test_opc_package_v6_corpus.py` → 132 passed.
- `python3 -m pytest -q` → 418 passed, 1 existing openpyxl warning; `git diff --check` passed.
