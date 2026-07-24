# Project Handover

Narrative context transfer between sessions. This file's integrity is checksum-verified by
`handover/PROJECT_CHECKSUM.md` via `workflowctl check-handover` — if the two disagree, trust
neither until you've reconciled why (a stale checksum after a legitimate edit is the most likely
cause; verify with `git diff` before assuming tampering). A checksum match only proves this file
is byte-identical to what the manifest recorded — it says nothing about whether the *content* is
still factually true; cross-check against `git log`, `docs/TASK_QUEUE.md`, and
`docs/DECISION_LOG.md` before trusting a narrative here.

## Where things stand (2026-07-24)

**The approved 1.0.0 roadmap (`docs/milestones.md`, `docs/MASTER_ROADMAP.md`) is 100% complete**
and has been merged and pushed — see "Git and release history" below; this is no longer pending.
Two post-1.0 programs have since been authorized by the Human Owner:

- **AgentOS Dashboard (DASH-001..010):** DASH-001 (planning foundation, `docs/agentos-dashboard/`)
  is `Done`, merged into `main` via PR #1 (`5f82996`). DASH-002..010 are `Planned`, each requiring
  its own fresh authorization; DASH-004 onward is additionally gated on OD-D9.
- **AgentOS Workflow Automation (AUTO-001..007):** AUTO-001 (architecture and governance
  contracts, `docs/workflow-automation/`) is `Done`, merged into `main` via PR #3 (`191f600`).
  **AUTO-002 (orchestrator, state machine, locking, and persistence) is the sole `Current` task**,
  authorized by the Human Owner on 2026-07-24 ("I authorize AUTO-002."), but its registry state is
  `BLOCKED` (`docs/workflow-automation/STAGE_REGISTRY.md` §2/§4) on a durable execution
  precondition: AUTO-002 stays `BLOCKED` until this governance recovery is merged into `main`, and
  even then an AUTO-002 session must begin from updated, clean `main` and create or check out the
  canonical branch `feature/auto-002-orchestrator-state-machine` — that branch must independently
  pass the SSP's initial-start branch-binding and clean-tree checks before the registry
  transitions `AUTHORIZED → IN_PROGRESS`. This does **not** invalidate the Human Owner's
  authorization (`STAGE_REGISTRY.md` §3 rule 17). **No AUTO-002 implementation has been written.**
  See "What's next" below for the current session's own (temporary, not-canonical) branch and the
  full durable rule. Full detail: `docs/current_task.md`, `docs/DECISION_LOG.md` (2026-07-24
  entries).

A multi-pass governance-recovery effort on 2026-07-24 audited the AUTO-001 post-merge state
across seven independent-review rounds and corrected, in turn: a citation of the wrong governing
document for the AUTO-002 branch block; a non-canonical `STAGE_REGISTRY.md` state value; the
AUTO-00x lifecycle's authorization-vs-execution-precondition rules and the `BLOCKED` state's
legal transitions (made explicit across `STAGE_REGISTRY.md`, `HUMAN_AUTHORIZATION_MODEL.md`,
`WORKFLOW_STATES.md`, the SSP, `stage-prompts/AUTO-002.md`, and `OPEN_QUESTIONS.md`); an
impossible "clean tree" rule definition and a self-introduced `BLOCKED`/SSP deadlock; a stale
Dashboard registry (`DASH-001` shown `IN_PROGRESS` though `Done` since 2026-07-23) and its drift
from the AUTO registry's rules; three failure transitions missing from `WORKFLOW_STATES.md` §3
that `MACHINE_GATES.md` already required (`AUTHORIZED`/`PRECONDITIONS_CHECKED`/`PR_OPEN` →
`FAILED` — added, then explicitly reviewed and approved by the Human Owner as the MAJOR change
`WORKFLOW_STATES.md` §11 requires, version 1.2 → **2.0**); an overstated Dashboard/AUTO
rule-equivalence claim, narrowed to what a rule-by-rule audit actually supports; and a
non-deterministic pre-commit configuration (two disagreeing formatters, `ruff-format` and
`black`, running over the same files) fixed at its root by removing the redundant formatter and
re-pinning all hooks to the installed tool versions, with idempotence verified over two
consecutive runs. None of this changed any AUTO-002 lifecycle state or started its
implementation. A documented, deliberately unimplemented gap (`GOV-2`, `Planned`): extending
`workflowctl check-governance` to machine-verify registry/lifecycle consistency needs new
validator code, out of scope for this recovery.

Two further rounds (eighth and ninth) then: fixed `tests/test_migration_plan_apply.py` so
`ruff format --check .` fully agrees with `black --check .` (no residual formatter disagreement
anywhere in the repository); audited every mention of `check-governance` for overclaiming and
found none; and — with a second, separate, explicit Human Owner MAJOR-change approval, quoted
verbatim in `docs/DECISION_LOG.md` — completed `WORKFLOW_STATES.md`'s failure-transition model
with eight further `→ FAILED` transitions (`BRANCH_CREATED`, `IMPLEMENTING`, `REPAIRING`,
`READY_TO_COMMIT`, `COMMITTED`, `PUSHED`, `AUTO_MERGE_ENABLED`, `MERGED`), required by
`TEST_STRATEGY.md` §4a's "at each state" interruption-testing mandate but previously absent from
the table; version 2.0 → **3.0** (a separate MAJOR bump, not reusing the prior one), with
consistency updates to `MACHINE_GATES.md`, `FAILURE_RECOVERY.md`, `TEST_STRATEGY.md`, and
`AGENT_CONTRACTS.md` (each → 1.1) so no document contradicts the now-complete table. None of this
changed any AUTO-002 lifecycle state or started its implementation.

A tenth round then closed two Dashboard-scoped gaps: `docs/agentos-dashboard/
stage-prompts/README.md` still named the removed `ruff-format` hook (fixed to name the actual
current pre-commit hooks in actual order — `ruff-check --fix`, `black`, `mypy` — and to include
`ruff format --check .` in its recorded validation commands, → 1.2); and
`docs/agentos-dashboard/CHANGELOG.md` was missing entries for two already-approved revisions
(`STAGE_REGISTRY.md` 2.0 → 3.0 and `stage-prompts/README.md` 1.0 → 1.1), closed by appending
three new entries without touching the existing ones (its own append-only convention).

An eleventh round added `STAGE_REGISTRY.md` rule 19 (Resume Preflight, zero new transitions) so
resuming an already-`IN_PROGRESS` AUTO-00x stage no longer requires the impossible return to
`AUTHORIZED`; mirrored `GOV-2` into `docs/PROJECT_STATE.md` and this file, which had omitted it;
and rewrote every live description of AUTO-002's branch blocker as a durable, branch-name-
independent rule. A twelfth round mirrored the resume-preflight fix into the Dashboard registry,
corrected a machine-gate-count wording nit, and recorded (without resolving) two Human Owner
design questions: `SUPERSEDED` task-status semantics (OD-8) and initial-execution provider/
commit/push/PR failure policy (OD-9). The Human Owner then supplied both policies explicitly:
OD-8 — `SUPERSEDED` ≈ task status `Done`, administratively closed and never confused with
successful completion, with explicit legal source states and no automatic successor
authorization; OD-9 — a bounded same-state retry, then idempotency/reconciliation, then advance/
`REPAIRING`(`IMPLEMENTING` only)/`FAILED`, for the implementation-provider invocation and
`create_commit`/`push_stage_branch`/`create_pull_request`, adding no new state or transition
(new `WORKFLOW_STATES.md` §5a). Both applied fully across every named document
(`STAGE_REGISTRY.md` both programs, `WORKFLOW_STATES.md`, `MACHINE_GATES.md`,
`FAILURE_RECOVERY.md`, `AGENT_CONTRACTS.md`, `SKILL_CONTRACTS.md`,
`MODEL_PROVIDER_CONTRACTS.md`, `TEST_STRATEGY.md`, `DECISIONS.md`, `OPEN_QUESTIONS.md`), with
both approvals quoted verbatim in `docs/DECISION_LOG.md`. None of this changed any AUTO-002
lifecycle state, started its implementation, or performed any release action.

A further round fixed a real defect in how OD-9 was implemented: `SKILL_CONTRACTS.md`/
`MODEL_PROVIDER_CONTRACTS.md` had classified retryable failures by error *type* (timeout,
connection reset, DNS failure), when the approved policy requires classifying by *timing* —
absence of confirmation is never proof no side effect occurred. Corrected to classify strictly by
whether the underlying operation was ever actually invoked. Also appended a missing
`docs/agentos-dashboard/CHANGELOG.md` entry for its own 4.0 → 5.0 version transition, and rewrote
every live AUTO-002 branch-blocker description (this file included, below) to state the settled
release procedure — this recovery branch is reviewed, committed, pushed, merged, and deleted
through the ordinary process, never renamed into the AUTO-002 branch — rather than presenting it
as an open choice. Full detail: `docs/DECISION_LOG.md` (2026-07-24 entries).

## Git and release history

`main` and `origin/main` are **identical** (both at `191f600`, 0 ahead / 0 behind) — DASH-001 and
AUTO-001 were each merged via a real GitHub PR (#1 and #3) and are pushed. There is no
uncommitted or unpushed work sitting on `main`. The only local branch without an upstream is this
session's own working branch, `feature/auto-002-orchestrator-foundation` (`workflowctl check-git`
reports `upstream_missing`, expected for a local, not-yet-pushed feature branch and not a
governance blocker by itself). The repository also contains two local stash entries retained as
recovery snapshots; they are not branches or upstreams and this recovery leaves them untouched.

The approved 1.0.0 engine work (Milestones 1–4) reached its `1.0.0` release; see "What the
released engine does" below for what it consists of. It shipped as part of the history now on
`main`/`origin/main` described above.

## What the released engine (v1.0.0) does

`ai_workflow_engine` (`src/`) is a local orchestration foundation for governed AI-assisted
software development, delivered across four milestones (`docs/milestones.md`):

- **Milestone 1** (v0.1.0): deterministic read-only Git inspection (`GitClient`,
  `READ_ONLY_FORMS`), governance/task-state mirror checks, checksum-verified handover integrity,
  protected-path enforcement, structured CLI/JSON output.
- **Milestone 2**: governed prompt generation — deterministic, canonically-hashed
  rendering/validation/atomic storage for all seven workflow stages, plus
  `workflowctl prompt <stage>`.
- **Milestone 3** (v0.2.0): non-interactive agent execution — a persisted, hash-chained workflow
  state machine (`workflowctl state`), a configurable `agents` surface with a strict report
  contract, a snapshot-sandbox runner with hard timeouts/isolation, and independent claim
  verification with tamper-evident run artifacts (`workflowctl agent run`). Agent output is
  always verified against sandbox reality, never trusted at face value.
- **Milestone 4** (v0.3.0, released as v1.0.0): controlled commit and push — a separate typed
  writable-Git surface (`GitWriter`; force-push, branch deletion, `reset`, `--amend`, `add -A`
  are structurally unreachable, not just denylisted), per-invocation human approval artifacts, and
  the `workflowctl commit` / `push` / `apply-patch` gates. No commit or push happens without a
  matching approval artifact.

Full spec/demonstration docs: `docs/milestone-2-plan.md`, `docs/milestone-3-plan.md` +
`docs/MILESTONE_3_VALIDATION.md`, `docs/milestone-4-plan.md` + `docs/MILESTONE_4_VALIDATION.md`,
`docs/FINAL_COMPLETION_REPORT.md`.

## What's next

No task-tracked engine work is queued under `src/`/`tests/` right now — the released engine's
roadmap is complete and stable. All remaining work is one of two kinds: stage-authorization-gated
AUTO/DASH program work — AUTO-002 (`Current`, `BLOCKED`, see below) and the `Planned`
AUTO-003..007 / DASH-002..010 stages, each requiring its own fresh Human Owner authorization — or
one ordinary (non-AUTO/DASH-family) governance/tooling task, **GOV-2**: extending
`workflowctl check-governance` to machine-verify stage-registry/lifecycle consistency, assessed
but deliberately not implemented during this recovery (real validator code, out of scope for a
documentation-only session), also `Planned` and also requiring its own fresh authorization
(`docs/TASK_QUEUE.md`, `docs/remaining_tasks.md`).

**AUTO-002's `BLOCKED` state is a durable execution-precondition rule, not a fact tied to any
particular branch name, and the release path is settled, not an open choice.** This
governance-recovery branch is reviewed, committed, pushed, merged, and deleted through the
ordinary recovery release process — it is **not** renamed into the AUTO-002 implementation
branch. Whichever branch this governance-recovery work happens to be on is temporary; this
document's own name for it will go stale the moment it is deleted post-merge, which is expected
and does not need a fresh handover edit to remain accurate, because the rule below does not
depend on it. After that merge and cleanup, an AUTO-002 execution session begins from updated,
clean `main`, creates or checks out the canonical branch
`feature/auto-002-orchestrator-state-machine`, and that branch must independently satisfy the
SSP's initial-start branch-binding and clean-tree checks (`docs/workflow-automation/
STAGE_REGISTRY.md` §3 rules 1/14/4) before the registry transitions `AUTHORIZED → IN_PROGRESS`.
This is not a new AUTO-002 authorization — the Human Owner's `"I authorize AUTO-002."`
authorization already stands, unaffected by any of this (`STAGE_REGISTRY.md` §3 rule 17) — and
AUTO-002 implementation does not begin during governance recovery. The original branch-mismatch
discovery (2026-07-24) remains in `docs/DECISION_LOG.md` unchanged, as a historical record, not a
live, ongoing assertion.

The immediate next action is the **Human Owner review and release of this governance-recovery
branch** (commit, push, merge, and cleanup — each still individually human-gated per
`docs/AGENT_PROTOCOL.md`, every time). No further branch-naming decision is outstanding: the
canonical AUTO-002 branch is created fresh from `main` by a later AUTO-002 session, never by
renaming this one.
