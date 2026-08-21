---
type: task
status: frozen
work_id: cgr-opc-v6-x14-cf-priority-compat-v1
tags: [task/implementation, feature/x14-rule, status/frozen]
last_verified: 2026-08-21
updated: 2026-08-21
---

# X14 CF repeated-priority compatibility — frozen Gate card

Base/dependency are exact `6220dbf47fbe31291ab6c827057538ede00332c7`. Branch `codex/cgr-opc-x14-cf-priority-compat-v1`; P4 developer; exact `--no-ff` only after P6.

## Scope

- `rns_import_server/opc_worksheet_x14_cf_owner_topology.py`
- `tests/test_opc_worksheet_x14_cf_rule_envelope.py`
- `tests/test_opc_worksheet_x14_cf_rule_envelope_corpus.py`
- this card

No public API, fixture, X1/X2b test, relationship, mutation, publication or UI changes.

## Contract

Keep strict priority lexical/XML-whitespace/Int32 validation. Remove only worksheet-global duplicate-priority rejection from both rule and sqref readers. Preserve every rule's priority, GUID, owner path and XML document order exactly; never deduplicate, sort or renumber. Do not invent owner-local uniqueness. `duplicate-x14-cf-priority` is retired because the reader cannot claim worksheet-wide conformance without native-rule comparison and the real register systematically repeats priorities.

This is read-only compatibility, not a claim that the source priorities meet the standard. Future insertion must preserve the ordered priority/GUID fingerprint; any removal, renumbering or deduplication is blocking. All rule-event, X1 and X2b precedence/atomicity stay unchanged.

## Acceptance

Replace only the obsolete global-uniqueness assertions. Keep the test set small:

1. canonical-equal priorities in different owners are preserved in order;
2. repeats inside one owner are also preserved;
3. repeats across sheets are preserved and document order resets per sheet;
4. a repeat never masks a later invalid ID/formula;
5. all old invalid lexical/bound/overlong cases still fail typed;
6. real read-only candidate with X2b records 1,558 owners/rules, 2,473 ranges, 214 unique priority values, exact main multiplicities, 1,558 unique GUIDs, document order `1..1558`, row coverage 6/10/104=`8/8/13`, and unchanged SHA `2a1786d5836e4c3144107704f281bc9513fcd8de97937499268dc806c1106dd1`.

Run direct rule tests, focused X1/X2a, full pytest, compile production, diff check, exact scope/ancestry/identity/clean. No generalized matrix, fallback, mutation or native Excel claim.
