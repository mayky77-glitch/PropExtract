---
type: task
status: implementation-complete-pending-p6
work_id: cgr-opc-v6-openpyxl-relationship-interop-v1
tags: [task/implementation, feature/opc-relationships, status/frozen]
last_verified: 2026-08-21
updated: 2026-08-21
---

# Openpyxl relationship interoperability — frozen Gate card

Base and accepted dependency are exact `f546fa552ad78954e7c9295cf76cf3b12a73be6f`. Branch is `codex/cgr-opc-openpyxl-relationship-interop-v1`; role is P4 developer; integration is exact `--no-ff` only after independent P6.

## Exclusive scope

- `rns_import_server/opc_relationship_xml.py`
- `rns_import_server/opc_package_graph.py`
- `tests/test_opc_relationship_xml.py`
- `tests/test_opc_package_graph.py`
- this card

No workbook/X14 reader, fixture, mutation, hyperlink dereference, UI, publication or Windows adapter changes.

## External hyperlink compatibility

Keep the strict URI parser as the default. A raw U+0020 compatibility path is allowed only when `Type` is the exact existing Transitional hyperlink relationship and `TargetMode="External"`. Build a validation-only view by replacing U+0020 with `%20`, then apply all existing URI, NFC, percent, authority, control/Cf/Cs and backslash checks. Admit only scheme-less path references or case-insensitive `file:` URIs. Spaces are path-only and may not be leading/trailing; raw-space `http`, `https`, `urn`, query, fragment, authority, wrong type/mode and Internal targets remain invalid.

Preserve and return the original decoded XML `Target`. Never return the validation view, rewrite XML, resolve the external path, access the file/network, or report success after a failed check. `resolved_target` remains `None`.

## Package-root Internal targets

Accept exactly one leading `/` for Internal URI references and resolve the remainder from package root. Preserve raw `Target`; expose only the existing canonical resolved member. Continue rejecting `//authority`, absolute schemes, empty root, encoded/raw traversal, separators, controls, query and fragment. Existing forbidden-control/relationship-part checks and missing-target checks keep their precedence.

Errors remain the existing typed contracts: invalid compatibility syntax is `invalid-relationship-target`; a valid rooted but absent part is `missing-internal-target`; forbidden destinations are `forbidden-internal-target`. No partial graph or fallback.

## Frozen evidence

Real read-only target is `Автоматизация РнС и ГРО/Реестр РНС Иркутск.xlsx`, SHA-256 `2a1786d5836e4c3144107704f281bc9513fcd8de97937499268dc806c1106dd1`. It has 218 relationships: 209 External hyperlinks, of which 208 are `file:` and one is relative; 205 contain raw spaces and NFC Cyrillic. Four Internal worksheet targets are rooted `/xl/worksheets/sheet1.xml` through `sheet4.xml`. After this Gate the graph must contain 9 parts, 218 relationships, 209 unresolved External relationships and four exact rooted mappings; source SHA must remain unchanged.

The next X14 read may still stop on another typed error. Record it exactly; do not weaken or skip it and do not claim X2b real qualification.

## Acceptance

Tests must cover raw-space `file:` and relative Cyrillic hyperlink targets with raw preservation; already escaped `%20`; all wrong type/mode/scheme/authority/query/fragment/edge-space/backslash/control/non-NFC/bad-percent negatives; rooted Internal success/missing/forbidden/traversal; no external dereference; exact real-corpus counts/hash.

Run focused relationship/graph/part-URI/corpus tests, full `python3 -m pytest -q`, compile the two production modules, and `git diff --check`. Verify exact five-path scope, ancestry, human identity and clean tree. Independent P6 must reproduce the real target read-only. No fallback or standards-wide relaxation.

## Recovery implementation evidence

P6 Recovery closes the literal-control precedence gap without changing the
frozen graph scope. `ElementTree` now establishes XML well-formedness, root,
and exact child identity before the lexical `Relationship@Target` verdict; the
verdict runs only after the existing attribute, Id, Type, and TargetMode
boundaries and immediately before Target URI validation. Thus duplicate
`Target` remains `malformed-xml`, a wrong root remains
`invalid-relationships-root`, and a wrong-namespace child remains
`invalid-relationships-child` even when its source Target contains literal
TAB/LF/CR. BOM-less UTF-16LE/BE documents with an explicit `utf-16`
declaration use their unambiguous byte signatures for the same lexical check;
valid documents in both forms remain accepted.

Focused relationship/graph/part-URI/corpus tests: 197 passed. Full suite:
1402 passed, exactly 10 managed-sandbox loopback `socket.bind` denials, and
one known Openpyxl warning; no product-test failure. The real source workbook
remained read-only at SHA-256
`2a1786d5836e4c3144107704f281bc9513fcd8de97937499268dc806c1106dd1`.

## P4 implementation evidence

Implemented on the frozen base: raw U+0020 is accepted only in the specified Transitional External hyperlink form, while output preserves the decoded XML target and leaves `resolved_target` as `None`. Exactly one Internal leading slash is resolved from package root; all other target checks keep their existing typed boundary. P6 remediation adds encoding-aware lexical rejection of literal TAB/LF/CR in quoted `Relationship@Target` before ElementTree normalizes them; character references retain the established parser path. Focused relationship/graph/part-URI tests: 163 passed. Full suite: 1397 passed, 10 sandbox-only loopback `socket.bind` denials, 1 known Openpyxl warning; zero product-test failures. Compile and diff checks passed. Pending independent P6.
