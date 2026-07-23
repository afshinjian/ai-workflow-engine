# AUTO-006 — GitHub Pull Request, Automatic Squash Merge, and Closeout Integration

| Field | Value |
|---|---|
| **Stage** | AUTO-006 · Role: Engine implementation session |
| **Branch** | `feature/auto-006-pr-merge-closeout` |
| **Commit message** | `feat(workflow): add GitHub PR, automatic squash merge, and closeout integration (AUTO-006)` |
| **Report** | `docs/reports/workflow-automation/AUTO-006-completion-report.md` |
| **Status/Version** | Draft · 1.0 |

Apply the Standard Stage Protocol in `README.md` in full.

## Canonical Prompt

You are the **Engine implementation session** executing **AUTO-006 — GitHub pull request,
automatic squash merge, and closeout integration**. Preconditions: AUTO-003 and AUTO-005
`COMPLETE`; recorded authorization "I authorize AUTO-006"; branch
`feature/auto-006-pr-merge-closeout` from clean `main`.

**Allowed**: extend `agentos_workflow/skills/git_github.py` (new file, not previously created —
AUTO-003 scoped local-Git-only skills; this stage adds the GitHub-CLI-facing skills from
`../SKILL_CONTRACTS.md` §5), `agentos_workflow/tests/**`, plus SSP-required
documentation/report updates.

**Build**: `create_commit`, `push_stage_branch`, `create_pull_request`,
`read_pull_request_state`, `read_required_checks`, `verify_head_sha`,
`enable_automatic_squash_merge`, `verify_merge_completion` exactly per
`../SKILL_CONTRACTS.md` §5, as fixed-argv `gh` CLI invocations — resolves `../OPEN_QUESTIONS.md`
OD-1 (native `gh pr merge --auto --squash` vs. engine-side polling, recorded in
`../DECISIONS.md`). Wire the Merge Safety Gate and Checks-Wait Gate
(`../MACHINE_GATES.md` §5-6) into the Orchestrator. Verify by inspection and by test that no
code path can construct `gh pr merge --admin` or any other admin-bypass invocation
(`../SECURITY_MODEL.md` §4).

**Tests**: `gh` invocations mocked at the process boundary for the default suite (no real
GitHub repository required); expected-head-SHA mismatch blocks `AUTO_MERGE_ENABLED`; a required
check reported as failed blocks `MERGED` and produces `FAILED`, never a retried merge;
`verify_merge_completion` is the only path that can trigger `CloseoutAgent`; idempotent
`create_pull_request` reuses an existing open PR for the branch instead of duplicating.

**Out of scope**: end-to-end run against a real GitHub repository (opt-in only) — AUTO-007.

Write the report, recommend the commit message above, then STOP per SSP.

## Stage-Specific Notes

Reference: `../MACHINE_GATES.md` §5-6, `../SECURITY_MODEL.md` §2 and §4,
`../SKILL_CONTRACTS.md` §5. This stage is the highest-risk implementation stage in the program
(it is the only one that can reach GitHub write state) and should receive independent review
attention proportional to that risk even though `../STAGE_REGISTRY.md` does not mandate a
dedicated security-review round until AUTO-007.
