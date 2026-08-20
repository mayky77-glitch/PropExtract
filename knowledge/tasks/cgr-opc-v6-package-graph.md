---
card_id: cgr-opc-v6-package-graph
status: review
version: 1
work_id: cgr-opc-package-graph-v1-20260820
task_id: package-graph-v1
purpose: Compose the accepted OPC part-URI and relationship parsers into a deterministic ZIP package graph.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
launch_status: inherited
actual_model: unknown
actual_reasoning_effort: unknown
fallback_reason: collaboration runtime did not expose launch override confirmation
planning_parent_sha: b6ebf9914167a872895631ab7deffcdd17fa86f4
dependency_shas: [d31d974551c44e9ae6b91b4e629362ffcb50a5b4, cbe0a7c3510454c1a98d1da05b0a3cfbda532b7d, bfb0065ce4c8915dc5163b74e3b841bd72bab5c9]
branch: codex/cgr-opc-package-graph-v1
card_path: knowledge/tasks/cgr-opc-v6-package-graph.md
write_scope: [rns_import_server/opc_package_graph.py, tests/test_opc_package_graph.py, knowledge/tasks/cgr-opc-v6-package-graph.md]
forbidden_paths: [rns_import_server/opc_part_uri.py, rns_import_server/opc_relationship_xml.py, tests/opc_package_v6_corpus.py, tests/test_opc_package_v6_corpus.py, tests/fixtures/opc-package-v6, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_opc_package_graph.py tests/test_opc_part_uri.py tests/test_opc_relationship_xml.py tests/test_opc_package_v6_corpus.py", "python3 -m pytest -q", "git diff --check"]
---

# OPC package graph v1

Build a read-only, immutable package graph from a filesystem path to an OPC ZIP. Reuse only the accepted V6 primitives and corpus; do not copy or import rejected V5 resolver code.

## Public contract

- Export frozen records `PackagePart`, `PackageRelationship`, `OPCPackageGraph`, typed `OPCPackageGraphError`, and `build_opc_package_graph(package_path)`.
- `OPCPackageGraphError.as_tuple()` is exactly `(code, subject, field, detail)`. No generic catch, silent skip, partial graph, warning-only result, or false success.
- Preserve ZIP member order and relationship XML order. Returned tuples and first-failure selection are deterministic.
- A relationship record retains relationship-part name, source part (`None` for package root), `Id`, `Type`, raw `Target`, `TargetMode`, and resolved internal target; external targets have no resolved package part.

## Package rules

1. Open the path as ZIP and fail with typed evidence for unreadable/non-ZIP/encrypted/bad members. Never extract files.
2. Require exactly one canonical `[Content_Types].xml`; parse it as well-formed XML with the exact OPC content-types root namespace. Full Default/Override semantics are intentionally a later card.
3. Canonicalize every member using `opc_part_uri`; reject exact duplicates and normalized aliases before graph construction. Directory entries are invalid package parts.
4. Recognize only `_rels/.rels` and `<directory>/_rels/<filename>.rels` as relationship parts. Derive the source mechanically; every non-root source must be a present canonical package part. A `.rels` member in any other location fails explicitly.
5. Parse each relationship part with `parse_relationship_xml`. Convert its typed error into graph error without losing code, relationship-part context, or detail.
6. Resolve every Internal target with `resolve_relative_part_uri(source, target)` and require the canonical target to exist. Preserve raw target plus resolved target. External URI-references stay external and are never resolved or required in the ZIP.
7. Relationships may not target `[Content_Types].xml` or a relationship part. Fail explicitly.

## Required verification

- Unit cases: valid root and nested relationships; source derivation; missing source; missing internal target; external relative/rooted/network/absolute references; exact duplicate and percent alias; root escape; misplaced `.rels`; invalid content-types root; corrupt/non-ZIP/encrypted input; deterministic member/XML order; immutable records.
- Drive the accepted independent V6 corpus by writing its package bytes and checking every valid case succeeds and every invalid case fails with the correct stable first category/context. Production must not import from `tests`.
- Regression commands in front matter pass. Human commit/push; no merge, rebase, amend, force-push, or unrelated edits.

## Implementation evidence

- Added the immutable ZIP package graph in `rns_import_server/opc_package_graph.py`, using only the accepted part-URI and relationship-XML primitives.
- Added focused package-graph cases in `tests/test_opc_package_graph.py`, including the independent V6 corpus replay.
- `python3 -m pytest -q tests/test_opc_package_graph.py tests/test_opc_part_uri.py tests/test_opc_relationship_xml.py tests/test_opc_package_v6_corpus.py` → 120 passed.
- `python3 -m pytest -q` → 406 passed, 1 existing openpyxl warning; `git diff --check` passed.
- Known contract risk: the corpus's raw-Unicode relationship target is labelled valid, but the accepted relationship parser rejects non-ASCII URI references. The graph keeps that parser as the responsible typed-error boundary.
