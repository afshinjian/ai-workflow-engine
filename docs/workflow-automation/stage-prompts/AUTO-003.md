# AUTO-003 — Deterministic Repository and Validation Skills

| Field | Value |
|---|---|
| **Stage** | AUTO-003 · Role: Engine implementation session |
| **Branch** | `feature/auto-003-repository-validation-skills` |
| **Commit message** | `feat(workflow): add repository, contract, and validation skills (AUTO-003)` |
| **Report** | `docs/reports/workflow-automation/AUTO-003-completion-report.md` |
| **Status/Version** | Draft · 1.0 |

Apply the Standard Stage Protocol in `README.md` in full.

## Canonical Prompt

You are the **Engine implementation session** executing **AUTO-003 — Deterministic repository
and validation skills**. Preconditions: AUTO-002 `COMPLETE`; recorded authorization
"I authorize AUTO-003"; branch `feature/auto-003-repository-validation-skills` from clean
`main`.

**Allowed**: create `agentos_workflow/skills/{__init__.py, repository.py, contract.py,
validation.py, reporting.py}`, `agentos_workflow/tests/**`, plus SSP-required
documentation/report updates.

**Build**: every skill in `../SKILL_CONTRACTS.md` §2 (Repository), §3 (Contract), §4
(Validation), and §6 (Reporting) with the exact input/output/side-effect/idempotency contract
specified there. Git-facing skills as named functions over `subprocess.run` with fixed argv,
`LC_ALL=C`, bounded timeout, typed errors, never a mutating verb beyond what each skill's
contract names. Secret-redaction defense-in-depth for command output per
`../SECURITY_MODEL.md` §1 (resolves `../OPEN_QUESTIONS.md` OD-2).

**Tests**: root-confinement/traversal/symlink rejection for repository skills against tmpdirs;
Git skills against temporary real Git repositories covering the fixture matrix in
`../TEST_STRATEGY.md` §3; contract-hash and stage-ordering skills against fixture stage
contracts; validation skills against fixture pass/fail command outputs, including secret-shaped
output redaction; engine-suite collection unchanged.

**Out of scope**: GitHub-facing skills (`push_stage_branch` beyond local push mechanics,
`create_pull_request`, checks/merge skills) — those are AUTO-006. Model Providers — AUTO-004.
Agents wiring skills together — AUTO-005.

Write the report, recommend the commit message above, then STOP per SSP.

## Stage-Specific Notes

Reference: `../SECURITY_MODEL.md` §2, §5-7 for the structural-prohibition requirements
(force-push, history rewrite, baseline mutation must be unreachable by construction, not just
refused at runtime). The engine's own read-only `GitClient`
(`src/ai_workflow_engine/git/`) is prior art for the allowlist discipline but must not be
imported or modified.
