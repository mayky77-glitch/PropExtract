---
card_id: cgr-opc-v6-unicode-relationship-uri
status: review
version: 1
work_id: cgr-opc-unicode-relationship-uri-v1-20260820
task_id: unicode-relationship-uri-v1
purpose: Admit canonical NFC Unicode in relationship URI-reference path data without weakening accepted URI boundaries.
role: developer
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: b6ebf9914167a872895631ab7deffcdd17fa86f4
dependency_shas: [cbe0a7c3510454c1a98d1da05b0a3cfbda532b7d, bfb0065ce4c8915dc5163b74e3b841bd72bab5c9]
branch: codex/cgr-opc-unicode-relationship-uri-v1
card_path: knowledge/tasks/cgr-opc-v6-unicode-relationship-uri.md
write_scope: [rns_import_server/opc_relationship_xml.py, tests/test_opc_relationship_xml.py, knowledge/tasks/cgr-opc-v6-unicode-relationship-uri.md]
forbidden_paths: [rns_import_server/opc_part_uri.py, rns_import_server/opc_package_graph.py, tests/opc_package_v6_corpus.py, tests/test_opc_package_v6_corpus.py, tests/fixtures/opc-package-v6, README.md]
acceptance_commands: ["python3 -m pytest -q tests/test_opc_relationship_xml.py tests/test_opc_part_uri.py tests/test_opc_package_v6_corpus.py", "python3 -m pytest -q", "git diff --check"]
---

# Unicode relationship URI-reference v1

Owner decision: preserve the accepted corpus case `worksheets/лист.xml` as valid. Extend only the accepted relationship XML URI grammar; do not special-case the graph and do not reuse rejected V5 code.

Implemented NFC-only Unicode acceptance in relationship URI path/query/fragment
components. Scheme and authority remain ASCII-only; controls, format/surrogate
code points, raw backslashes, and non-NFC forms fail closed with existing typed
errors.

P6 evidence: relationship suite `64 passed`; required composite URI/corpus suite
`117 passed`; full suite `403 passed` (one existing openpyxl extension warning);
`python3 -m compileall -q rns_import_server/opc_relationship_xml.py` and
`git diff --check` passed. No V5 code reused.

## Frozen contract

- Raw Unicode is allowed only as canonical NFC scalar text in URI path, query, and fragment character positions. This applies consistently to Internal and External `Target` and to the path/query portion of absolute relationship `Type` URIs.
- Scheme and authority parsing stay on the accepted ASCII/RFC boundary. Unicode host/userinfo is not admitted by this card; callers may use punycode or percent encoding.
- Keep every accepted restriction: nonblank values; Internal remains non-rooted relative; External accepts valid relative, rooted, network-path, or absolute URI-references; Type is absolute and fragment-free; percent escapes must be complete; existing IPv4/IPv6/IPvFuture, port, bracket, userinfo, and first-segment-colon rules remain.
- Reject non-NFC text, C0/C1/DEL controls including NUL, Unicode categories `Cf` and `Cs`, raw backslash, malformed percent escapes, forbidden ASCII delimiters, and all existing malformed authority/escape cases. No replacement, normalization-on-behalf-of-caller, silent fallback, or broad exception catch.
- Preserve current public API, dataclasses, error codes/tuples, ordering, and XML/DOCTYPE behavior.

## Required verification

- Accept NFC Cyrillic internal target `worksheets/лист.xml`; an XML package using it must pass the accepted independent Unicode corpus case when composed with the part resolver.
- Add Internal/External/Type cases covering Unicode path plus query/fragment where the existing mode/type contract permits them.
- Reject decomposed equivalents, zero-width/bidi formatting characters, surrogate input where representable, C0/C1/DEL, raw backslash, Unicode authority, malformed percent escapes, and percent-encoded separator/traversal at the existing downstream boundary.
- Re-run all acceptance commands. Human commit/push; no merge, rebase, amend, force-push, or unrelated edits.
