---
card_id: cgr-opc-graph-v2-path-encoding-remediation
status: ready
version: 1
work_id: cgr-opc-graph-v2-path-encoding-remediation-20260820
task_id: graph-v2-path-encoding-remediation
purpose: Restore deterministic path evidence and parser-compatible XML encodings in graph v2.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: 13637a156148b40df2899f21b727b999cf9f2ce1
dependency_shas: [13637a156148b40df2899f21b727b999cf9f2ce1]
branch: codex/cgr-opc-graph-v2-path-encoding-remediation
card_path: knowledge/tasks/cgr-opc-graph-v2-path-encoding-remediation.md
write_scope: [rns_import_server/opc_package_graph.py, tests/test_opc_package_graph.py, knowledge/tasks/cgr-opc-graph-v2-path-encoding-remediation.md]
forbidden_paths: [rns_import_server/opc_part_uri.py, rns_import_server/opc_relationship_xml.py, tests/opc_package_v6_corpus.py, tests/test_opc_package_v6_corpus.py, tests/fixtures/opc-package-v6, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_opc_package_graph.py tests/test_opc_part_uri.py tests/test_opc_relationship_xml.py tests/test_opc_package_v6_corpus.py", "python3 -m pytest -q", "git diff --check"]
---

# Graph v2 path/encoding remediation

P6 after `13637a1` confirmed all prior graph findings closed, then found two regressions.

1. Before successful path coercion, error subject must be deterministic and type-based; never use object `repr` or memory addresses. Coerce once. Catch only the frozen conversion/access boundaries (`TypeError` → `invalid-package-path`; `ValueError`/`OSError` → `unreadable-package`). Assert identical full tuples across fresh equivalent failing `PathLike` instances.
2. Remove the UTF-only encoding allowlist. Preserve any well-formed encoding accepted by the underlying XML parser, including `us-ascii`, `iso-8859-1`, `cp1251`, `windows-1252`, and `iso-2022-jp`. Narrowly classify unknown or parser-unsupported declarations such as `utf-7`, `shift_jis`, and `gbk` as `unsupported-xml-encoding` at both content-types and relationship boundaries. No permissive decoding/replacement/fallback and no accepted-parser change.

Keep every prior v2 fix and corpus behavior. Independent P6 required. Human commit/push; no merge, rebase, amend, force-push, or unrelated edits.
