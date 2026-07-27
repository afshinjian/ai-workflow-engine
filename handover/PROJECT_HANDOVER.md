# Project Handover

Narrative context transfer between sessions. This file is checksum-verified by
`handover/PROJECT_CHECKSUM.md`; cross-check its claims against Git and the configured validation
commands.

## Where things stand (2026-07-27)

The released `ai-workflow-engine` 1.0.0 roadmap is complete. In the post-1.0 programs:

- DASH-001 is `Done`; DASH-002..DASH-010 remain `Planned`.
- AUTO-001 is `Done`.
- AUTO-002 is `Done` and registry `COMPLETE`. It delivered the `agentos_workflow/` orchestrator,
  19-state workflow state machine, authorization capture and replay, append-only state/audit
  persistence, repository locking, retry/attempt accounting, configuration, and narrowly scoped
  local resume/evidence observation, plus the Human-Owner-approved remediation in
  `docs/workflow-automation/DECISIONS.md` DD-15..DD-31. **It has since been published and merged
  into `main`** (see below), so `agentos_workflow/` now exists on the baseline.
- **AUTO-003 is `Current` and registry `IN_PROGRESS`**, implemented and validated on
  `feature/auto-003-repository-validation-skills`, stopped and awaiting Human Owner approval.
- AUTO-004..AUTO-007 remain `Planned`/`NOT_STARTED`. None is authorized by AUTO-003's work.
- GOV-2 remains `Planned`.

## AUTO-002 publication and merge (2026-07-27)

Under a Human Owner authorization separate from AUTO-002's closure, the stage branch was pushed
and merged into `main`:

- PR **#5**, merged by merge commit **`87a5062`** (parents `163bcee` + `20c9890`) — a merge
  commit, matching the two-parent shape of PRs #1–#4, not a squash or fast-forward.
- Both CI runs passed **before** the merge was performed.
- Local `main` == `origin/main` == `87a5062`; `agentos_workflow/` is present on `main`.
- The AUTO-002 feature branch was **retained** (no governance rule required its deletion), and
  both pre-existing recovery stashes were left untouched.

This resolved the precondition that previously made AUTO-003 unstartable: its contract requires a
branch cut from clean `main`, and `main` had not contained `agentos_workflow/`.

## AUTO-003 — current state

Authorized 2026-07-27 ("I authorize AUTO-003."), with commit, push, merge, and AUTO-004 all
explicitly prohibited. Branch `feature/auto-003-repository-validation-skills`, cut from clean
`main` at `87a5062`.

Delivered `agentos_workflow/skills/` — 31 Skills across the Repository (§2), Contract (§3),
Validation (§4), and Reporting (§6) families of `SKILL_CONTRACTS.md`. Every Skill is a named
function over fixed argv returning a typed `SkillResult`, never raising to the Orchestrator. The
forbidden Git operations of `SECURITY_MODEL.md` §2 are unreachable by construction and
machine-checked by an AST assertion over the module's own source. OD-2 is resolved (DD-33);
DD-34 and DD-35 record the other two implementation decisions.

Validation, all recorded in `docs/reports/workflow-automation/AUTO-003-completion-report.md`:

- Focused suite 222 passed; `agentos_workflow/tests` 1,226 passed; `tests` 978 passed; combined
  2,204 passed.
- Engine default collection unchanged: 978 on the branch and on a clean `main` worktree.
- Ruff, Black, mypy (`agentos_workflow` and `src`), `pre-commit run --all-files` (mutated
  nothing), and `git diff --check`: all clean.
- `workflowctl verify` — `task-state`, `governance`, `handover` PASS; `git` FAIL with
  **`upstream_missing` only**, the expected condition for an unpushed local stage branch given
  `require_upstream: true`. AUTO-002 recorded the identical condition.

**Nothing is committed.** The stage's work is uncommitted working-tree state, deliberately, per
the authorization.

## Next session

1. Verify `git status`, recent history, and this handover checksum.
2. Confirm AUTO-003 is the only `Current` task and the registry shows `IN_PROGRESS`.
3. AUTO-003 is awaiting **Human Owner approval**. Do not advance its registry state, commit its
   work, or begin AUTO-004 without a fresh explicit instruction.
4. Should the Human Owner approve, closure and any commit/push/merge each require their own
   explicit authorization — approval of the implementation is not by itself authorization to
   commit or publish it.

Completing a stage never authorizes its successor. AUTO-004 requires its own fresh written
authorization naming it.
