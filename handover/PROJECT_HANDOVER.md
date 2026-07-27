# Project Handover

Narrative context transfer between sessions. This file is checksum-verified by
`handover/PROJECT_CHECKSUM.md`; cross-check its claims against Git and the configured validation
commands.

## Where things stand (2026-07-27)

The released `ai-workflow-engine` 1.0.0 roadmap is complete. In the post-1.0 programs:

- DASH-001 is `Done`; DASH-002..DASH-010 remain `Planned`.
- AUTO-001 and AUTO-002 are `Done`. AUTO-002 was published and merged into `main` via PR #5
  (merge commit `87a5062`, parents `163bcee` + `20c9890`), so `agentos_workflow/` is on the
  baseline.
- **AUTO-003 is `Done`** and registry `COMPLETE`. It delivered the deterministic Repository,
  Contract, Validation, and Reporting Skill families in `agentos_workflow/skills/`, resolved OD-2
  (DD-33), and recorded DD-34/DD-35. The Human Owner approved it on 2026-07-27 and authorized
  exactly one local commit, created as **`908be94`**. Push and merge were explicitly withheld —
  **`908be94` is still unpushed and unmerged.**
- **GOV-AUTO-01 — Local Human-Gated Task Runner is `Current`**, implemented and validated,
  **uncommitted**, awaiting Human Owner approval.
- AUTO-004..AUTO-007 remain `Planned`/`NOT_STARTED`. **AUTO-004 is explicitly not authorized.**
- GOV-2 remains `Planned`.

## Current Git state

| Fact | Value |
|---|---|
| Branch | `feature/auto-003-repository-validation-skills` |
| HEAD | `908be94` (the AUTO-003 commit) |
| Upstream | **none** — this branch has never been pushed |
| Worktree | dirty by design: the complete GOV-AUTO-01 diff awaits inspection |
| Stashes | `stash@{0}`, `stash@{1}` — both untouched since before AUTO-002 |

`main` is at `87a5062` and matches `origin/main`. The AUTO-003 commit exists only on the local
feature branch.

## GOV-AUTO-01 — current state

Authorized 2026-07-27 as a governance/developer-experience task **outside the AUTO family** — it
has no stage-registry lifecycle and no stage contract; its authoritative record is
`docs/TASK_QUEUE.md` and `docs/current_task.md`.

Delivered a local, Human-gated automation layer for the standard task cycle:

- `scripts/workflow-next.sh <claude|codex>` — read-only preflight, then exactly one agent session
  seeded with the canonical prompt. Refuses a dirty worktree; fails closed on any unknown agent;
  no `eval`; propagates the agent's exit status.
- `scripts/prompts/implement-next-task.md` — the canonical implementation prompt, including the
  four terminal tokens and the explicit statement that independent review is **not** mandatory for
  every ordinary task.
- `scripts/workflow-approve.sh` — the Human approval gate and the only path that commits. Two
  exact-`APPROVE` confirmations, Conventional-Commit validation, staging restricted to the
  displayed file list (never `git add -A`), and an `EXIT` trap that unstages without discarding
  working-tree content if anything fails after staging.
- `docs/automation-workflow.md` — operator documentation.

Validation: 59 script tests (`tests/test_workflow_runner_scripts.py`), 2,263 combined tests,
ruff/black/mypy clean, `bash -n` and `shellcheck` clean, plus manual smoke tests in disposable
repositories. Full detail: `docs/reports/GOV-AUTO-01-completion-report.md`.

**Nothing is committed.** Approval and commit are the Human Owner's next act.

## One governance decision needing confirmation

AUTO-003 was closed `Current` → `Done` (registry `IN_PROGRESS` → `COMPLETE`) because the Human
Owner's GOV-AUTO-01 authorization named it "the single active and Human-Owner-authorized task",
which AUTO-003 could not remain `Current` alongside under `maximum_current_tasks: 1`. That reading
rests on the Human Owner having approved AUTO-003 and authorized its commit. **If AUTO-003 was
meant to stay open, revert that closure** in `docs/TASK_QUEUE.md`, the two mirrors, and
`STAGE_REGISTRY.md` §4.

## Next session

1. Verify `git status`, recent history, and this handover checksum.
2. Confirm GOV-AUTO-01 is the only `Current` task.
3. GOV-AUTO-01 awaits **Human Owner approval**. Do not commit it without a fresh instruction.
4. Two publication decisions remain open and unauthorized: pushing/merging the AUTO-003 commit
   `908be94`, and anything to do with AUTO-004.

Completing a task never authorizes its successor. AUTO-004 requires its own fresh written
authorization naming it.
