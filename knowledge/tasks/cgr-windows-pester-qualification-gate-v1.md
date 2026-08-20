---
card_id: cgr-windows-pester-qualification-gate-v1
status: ready
version: 1
work_id: cgr-windows-pester-qualification-gate-v1-20260820
task_id: windows-pester-gate-v1
purpose: Run the three suspended Excel contracts on a real pinned Windows Pester runner at an exact candidate SHA.
role: devops
route: P4
assigned_model: gpt-5.6-terra
reasoning_effort: high
planning_parent_sha: 949b1c338b3761cd6343dbf0a965603197779874
dependency_shas: [c38198251e30e9d17aeb85cae5d20954ca861224, 20eb66a2328ac201803e16c30de8f08ca9541b85, 6f689ae27163eff18a4472727d94407d5f9334fb]
branch: codex/cgr-windows-pester-qualification-gate-v1
card_path: knowledge/tasks/cgr-windows-pester-qualification-gate-v1.md
write_scope: [.github/workflows/windows-excel-qualification.yml, knowledge/tasks/cgr-windows-pester-qualification-gate-v1.md]
forbidden_paths: [rns_import_server, scripts, tests, README.md, .github/workflows/windows-smoke.yml]
acceptance_commands: ["git diff --check", "git diff --name-only 949b1c338b3761cd6343dbf0a965603197779874..HEAD"]
---

# Windows Pester qualification gate v1

Add one isolated GitHub Actions workflow; do not alter production, tests, or the existing offline smoke workflow.

## Frozen contract

- Trigger on `pull_request` when this workflow or the three exact PowerShell modules/tests change; allow `workflow_dispatch`. Use `windows-2022`, pinned `actions/checkout` SHA, least `contents: read`, bounded timeout.
- Install exactly Pester `5.6.1` for `CurrentUser` from PSGallery and prove the imported version is exactly `5.6.1` before tests. Installation/import failure is terminal; no preinstalled fallback.
- Run exactly these three files as three separately reported suites: `tests/WindowsExcelRequestSchema.Tests.ps1`, `tests/WindowsExcelAtomicProtocol.Tests.ps1`, `tests/WindowsExcelFakeCom.Tests.ps1`.
- Set only the two existing discovery guards needed to prevent nested self-invocation. For each suite call `Invoke-Pester` directly with `-PassThru`, require a non-null result, `Result = Passed`, `FailedCount = 0`, `TotalCount > 0`, and `PassedCount = TotalCount`. For fake-COM additionally require `TotalCount = 9`. Any incomplete/discovery-zero/skipped/failed suite exits nonzero.
- Emit suite name, exact `GITHUB_SHA`, Pester version, total/passed/failed/skipped counts. Upload a small always-produced JSON summary artifact pinned to an action SHA; artifact creation must not turn failure into success.
- No secrets, caches, marketplace actions beyond pinned checkout/upload-artifact, production access, workflow chaining, or permissive `continue-on-error`.

## Qualification protocol

1. Independent P6 reviews the exact workflow SHA before trigger.
2. Push same-repository feature branch and open a temporary draft PR to trigger `pull_request`; do not merge it.
3. Accept evidence only when the run `head_sha` equals the reviewed feature SHA and the qualification job is green. Download/inspect summary artifact; all three suites must be present and satisfy the contract.
4. Until exact Windows green, request-schema `c3819825`, atomic `20eb66a`, and fake-COM `6f689ae` remain suspended and unmerged.

Human commit/push; no merge, rebase, amend, force-push, or unrelated edits.
