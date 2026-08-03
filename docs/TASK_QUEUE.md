# Task Queue

Authoritative record of every tracked workstream for `ai-workflow-engine`. This document is the
`governance.task_queue` source in `self-governance.yaml`; `docs/current_task.md` and
`docs/remaining_tasks.md` mirror it and must not contradict it — `workflowctl check-task-state`
and `workflowctl check-governance` verify that automatically.

## M-1 — Deterministic inspection and validation

Status: Done

Milestone 1 (v0.1.0, released 2026-07-16): read-only Git inspection, governance/task-state
mirror checks, source-aware handover checksum verification, protected-path enforcement,
structured CLI/JSON results.

## M-2 — Governed prompt generation

Status: Done

Deterministic, canonically-hashed prompt rendering, structural validation, and atomic
no-clobber storage for all seven workflow stages. Approved after three independent fresh
implementation reviews (two real defects found and fixed; several test-coverage gaps closed).
Committed locally 2026-07-17 with human approval.

## GOV-1 — Bootstrap self-governance documentation

Status: Done

Pointed this project's own governance tooling at its own repository: the five governance
documents, `self-governance.yaml`, and the pure-documentation files (`DECISION_LOG.md`,
`CHANGELOG.md`, `AGENT_PROTOCOL.md`) that had no existing counterpart. All acceptance criteria
demonstrated in `docs/VALIDATION_REPORT.md`; closed 2026-07-17 per the approved
`docs/MASTER_ROADMAP.md` (task T-101). Decision record: `docs/GOVERNANCE_AUDIT.md`.

## T-101 — Close out GOV-1

Status: Done

Formal GOV-1 closeout per the approved master roadmap: status flip, mirror synchronization,
changelog/decision-log entries, handover refresh. Completed 2026-07-17.

## T-102 — Documentation synchronization

Status: Done

Fixed the prose drift recorded in `docs/IMPLEMENTATION_GAP_ANALYSIS.md`: marked
`docs/milestone-2-plan.md` implemented/approved, extended `README.md` and
`docs/architecture.md` to cover the prompt subsystem, refreshed stale counts (the
point-in-time figures in `docs/GOVERNANCE_AUDIT.md` were deliberately left as accurate
historical records). Completed 2026-07-17.

## T-103 — Lightweight CI

Status: Done

Human-approved Stage 0 addition (2026-07-17): `.github/workflows/ci.yml` runs the test suite,
lint, format check, strict typing, and the three repository-content governance checks against a
CI-generated config copy (`check-git` is excluded in CI because a detached-HEAD checkout has no
upstream — an environment artifact, not a defect). Every step verified locally. Completed
2026-07-17.

## T-301 — Milestone 3 normative architecture plan

Status: Done

Wrote `docs/milestone-3-plan.md` at `docs/milestone-2-plan.md` rigor. Round-1 independent plan
review REJECTED (three blocking findings, all verified against source and remediated); round-2
independent review (fresh, no memory of round 1) APPROVED with only non-blocking notes.
Completed 2026-07-17.

## T-104 — Robust machine-readable CLI output (FORCE_COLOR bug)

Status: Done

Fixed a real defect surfaced during T-301 review: `workflowctl <cmd> --output json` and
`version` routed through Rich, which injects ANSI color codes when `FORCE_COLOR` is set,
corrupting the documented stable 1.0 JSON contract into unparseable output. Machine output now
bypasses Rich via a `_write_stdout` helper (as the Milestone 2 prompt path and `_protected`
already do). Subprocess regression test reproduces the exact `FORCE_COLOR=3` condition; suite
450-green with and without it. Independent implementation review APPROVED. Completed 2026-07-18.

## T-302 — Persisted workflow state machine

Status: Done

Event-sourced per-task state machine (append-only hash-chained events, verdict recording,
transition enforcement, next-stage computation) with collision-free tamper-evident storage and
the `workflowctl state show|next|record` CLI. 83 new tests; suite 533-green with and without
`FORCE_COLOR`. Independent implementation review APPROVED (two non-blocking findings addressed:
a canonical-form tamper-test gap closed, and the deterministic bespoke CLI payload documented in
`docs/DECISION_LOG.md`). Completed 2026-07-18.

## T-303 — Agent configuration schema and strict report models

Status: Done

`EngineConfig.agents` section (mode/stage compatibility, `push` forbidden for any agent,
absolute executable, timeout bounds, unique names); strict `AgentReport`/`AgentFinding` models;
and the prompt-payload migration (schema_version 1.0 → 1.1, `agents` in `CanonicalEngineConfig`,
1.0 sidecar rejected). `WorkflowStage` moved to `models.py` (re-exported) to avoid a circular
import. Template byte-pins unchanged. 39 new tests; suite 572-green both color modes.
Independent implementation review APPROVED (two non-blocking items deferred to T-304/T-305 per
plan). Completed 2026-07-18.

## T-304 — Non-interactive agent runner (sandbox, timeouts, isolation)

Status: Done

`SandboxGit` (writable Git bound only to managed sandbox clones; target repo untouched) + sandbox
lifecycle, the clean-tree/HEAD precondition gate, the subprocess runner (hard timeout with
process-group kill, scrubbed env, before/after `repository_mutated` fingerprint), the failure
taxonomy, and the `verification_argv` observation path. 26 stub-agent tests. Independent
implementation review APPROVED; two actionable non-blocking findings fixed in-task (process-group
kill on verification timeout; negative binding-mismatch tests for task/stage/verdict). Suite
598-green both color modes. Completed 2026-07-18.

## T-305 — Independent claim verification, agent-run artifacts, and the `agent run` CLI

Status: Done

Judged `RunObservation`s into a verified `CheckResult` (claim equality, scope/protected
containment, verification-command exit codes); the tamper-evident `AgentRunRecord` artifact
(content-addressed `run_id`, base64 stdout/stderr, `.patch` sidecar); the `workflowctl agent run`
CLI; and the `state record --agent-run` evidence binding. Independent implementation review
APPROVED; the two coverage-gap findings (protected-path / read-only-write / malformed-path
verification tests; FAIL-still-stores CLI test) were closed and the one spec deviation recorded
in `docs/DECISION_LOG.md`. Suite 623-green both color modes. Completed 2026-07-18. Closes
Milestone 3 implementation.

## T-306 — Milestone 3 closeout (release 0.2.0)

Status: Done

Full-cycle demonstration (`docs/MILESTONE_3_VALIDATION.md`, including the lying-agent detection),
version bump to 0.2.0 (`pyproject.toml`, `src/.../__init__.py`, `docs/PROJECT_STATE.md`; version
fact consistent), and architecture/README doc updates for the state + agent surfaces. Completed
2026-07-18.

## M-3 — Non-interactive agent execution

Status: Done

Released as v0.2.0 on 2026-07-18: scoped agent execution with strict report schemas, sandbox
isolation, hard timeouts, independent claim verification, and the persisted hash-chained workflow
state machine Milestone 2 deferred here. Delivered across T-301..T-306 (each independently
reviewed); normative plan `docs/milestone-3-plan.md`, demonstration
`docs/MILESTONE_3_VALIDATION.md`.

## T-401 — Milestone 4 normative architecture plan

Status: Done

`docs/milestone-4-plan.md` written at milestone-2/3 rigor. Round-1 independent plan review
REJECTED (five blocking findings, all remediated — typed-methods-only `GitWriter`, live-read push
gate, `GitClient` read-only extension using unchanged `READ_ONLY_FORMS`, complete file list);
round-2 independent review (fresh, no memory of round 1) APPROVED, confirming every safety
property and that residual ambiguities fail safe. Completed 2026-07-18.

## T-402 — Milestone 4: writable surface, approvals, and the commit gate

Status: Done

The typed-methods-only `GitWriter` (+ `GitWriteError`), the `GitClient` read-only extension
(`READ_ONLY_FORMS` byte-unchanged), the `CommitApproval`/`PushApproval` models + loader, and the
`workflowctl commit` gate (clean-index precondition, subset+existence checks, staged-set
assertion with rollback, post-hoc parent/path-set/message verification). 36 tests. Independent
implementation review APPROVED — three non-blocking findings closed (CLI-boundary tests,
defensive-branch tests, and a plan/impl placement note reconciled in `docs/milestone-4-plan.md`).
Suite 665-green both color modes. Completed 2026-07-18.

## T-403 — Milestone 4: push gate and the apply-patch bridge

Status: Done

The `workflowctl push` gate (branch/HEAD/upstream equality, strict `rev-list` behind==0, clean
tree → one `git push`) and the optional `workflowctl apply-patch` bridge (apply a verified M-3
patch to the working tree, gated by run artifact + HEAD match + clean-tree + dry-run + digest
re-check). Push tests run against a `file://` remote. Independent implementation review APPROVED;
five non-blocking findings closed (TOCTOU digest re-check, task_id normalization,
independently-proven apply_check branch, redundant-status cleanup, no-push assertions). Suite
684-green both color modes. Completed 2026-07-18.

## T-404 — Milestone 4 closeout (release 0.3.0)

Status: Done

Full-cycle commit→push demonstration (`docs/MILESTONE_4_VALIDATION.md`, incl. the un-approved-
change refusal), version bump to 0.3.0 (version fact consistent), and README/architecture doc
updates for the commit/push/apply-patch surfaces. Completed 2026-07-18.

## M-4 — Controlled commit and push

Status: Done

Released as v0.3.0 on 2026-07-18: a separate typed writable-Git surface, per-invocation human
approval artifacts, and the `workflowctl commit` / `push` / `apply-patch` gates with
protected-path enforcement and remote/upstream checks. Delivered across T-401..T-404 (each
independently reviewed; the plan review took two rounds). Normative plan
`docs/milestone-4-plan.md`, demonstration `docs/MILESTONE_4_VALIDATION.md`. Completes the
four-milestone roadmap in `docs/milestones.md`.

## T-501 — Version 1.0.0 release

Status: Done

Fixed the `version`-fact regex (`0\.\d+\.\d+` → `\d+\.\d+\.\d+`) in `self-governance.yaml` and
`examples/amozesh_konkur.yaml`, bumped to 1.0.0 (`pyproject.toml`, `__init__.py`,
`docs/PROJECT_STATE.md`, version tests), reworded the stale auto-flag validator message, finalized
the changelog, and wrote `docs/FINAL_COMPLETION_REPORT.md`. `check-governance` PASSes at 1.0.0
(proving the regex fix). Completed 2026-07-18 — the approved roadmap is now 100% complete.

## AgentOS Dashboard program

Post-1.0 program authorized by the Human Owner on 2026-07-23 (authorization and its recovery
record: `docs/agentos-dashboard/STAGE_REGISTRY.md` §4; enrollment decision:
`docs/DECISION_LOG.md`, 2026-07-23 entry). Ten independently authorized documentation and
implementation stages deliver a local, read-only-first governance dashboard as a separate
top-level package (`agentos_dashboard/`), leaving `src/`, `tests/`, and the audited engine
suite untouched. Program entry point: `docs/agentos-dashboard/MASTER_PLAN.md`; per-stage
contracts: `docs/agentos-dashboard/stage-prompts/`; live stage view:
`docs/agentos-dashboard/STAGE_REGISTRY.md`. Exactly one DASH task may be `Current` at a time,
and each stage requires its own fresh written authorization — completing a stage never
authorizes its successor.

## DASH-001 — Dashboard planning foundation and contracts

Status: Done

Documentation-only stage on branch `governance/dash-001-documentation`: created the complete
planning set under `docs/agentos-dashboard/` (16 documents + `stage-prompts/` with README and
ten canonical prompts), enrolled the DASH family here, mirrored it in `docs/current_task.md` and
`docs/remaining_tasks.md`, and recorded the enrollment decision in `docs/DECISION_LOG.md` — with
zero changes to `src/`, `tests/`, `scripts/`, dependencies, `handover/**`, or
`docs/implementation/orchestration/**`. Recovered and re-executed correctly for this repository
on 2026-07-23 after a mis-targeted first execution (see `docs/agentos-dashboard/DECISIONS.md`
DD-03); full contract: `docs/agentos-dashboard/stage-prompts/DASH-001.md`; report:
`docs/reports/agentos-dashboard/STAGE-01-completion.md`. Merged into `main` via PR #1
(`5f82996`); closed out 2026-07-23 as an AUTO-001 precondition (Human Owner directive: "Close
out DASH-001 first" — `docs/DECISION_LOG.md`, 2026-07-23 AUTO-001 entry). DASH-002..010 remain
`Planned`, each requiring its own fresh authorization; no successor was promoted by this
closeout.

## AgentOS Workflow Automation program

Post-1.0 program authorized by the Human Owner on 2026-07-23 ("I authorize AUTO-001."). Builds
a local orchestration layer that automates a target repository's stage lifecycle (precondition
verification, branching, implementation via Claude Code CLI, deterministic validation,
independent QA via Codex CLI, automatic repair, commit, push, PR, squash merge, and closeout)
behind a single human gate — explicit per-stage authorization — with every later transition
controlled by machine gates. Program entry point: `docs/workflow-automation/README.md`;
architecture: `docs/workflow-automation/ARCHITECTURE.md`; per-stage contracts:
`docs/workflow-automation/stage-prompts/`. This program automates *other* repositories' stages
(e.g. `DASH-002` in a separate target repository) — it does not itself replace this repository's
own `docs/TASK_QUEUE.md` discipline, which continues to govern `ai-workflow-engine`'s own work
including AUTO-00x. Exactly one AUTO task may be `Current` at a time, and each stage requires
its own fresh written authorization — completing a stage never authorizes its successor.

## AUTO-001 — Architecture and governance contracts

Status: Done

Documentation-and-architecture-only stage on branch
`governance/auto-001-workflow-automation-planning`: defined the complete governance and
architecture foundation for the AgentOS Workflow Automation engine under
`docs/workflow-automation/` (21 documents + `stage-prompts/` covering AUTO-001..AUTO-007) and
recorded the enrollment decision in `docs/DECISION_LOG.md` — with zero runtime code, zero
dependency changes, and zero changes to `src/`, `tests/`, `scripts/`, `handover/**`, or
`docs/implementation/orchestration/**`. Full contract:
`docs/workflow-automation/stage-prompts/AUTO-001.md`; report:
`docs/reports/workflow-automation/AUTO-001-completion-report.md`. Merged into `main` via PR #3
(`191f600`); formally closed out to `Done` 2026-07-24 per Human Owner review — see
`docs/DECISION_LOG.md`, 2026-07-24 entry.

## AUTO-002 — Orchestrator, state machine, locking, and persistence

Status: Done

Engine implementation completed and accepted for closure by the Human Owner on 2026-07-27
without an additional independent review. Authorized originally on 2026-07-24 ("I authorize
AUTO-002."). Full contract:
`docs/workflow-automation/stage-prompts/AUTO-002.md`; canonical branch per
`docs/workflow-automation/STAGE_REGISTRY.md` §4: `feature/auto-002-orchestrator-state-machine`.
**Execution precondition resolved 2026-07-24: the governance recovery merged into `main` via
PR #4 (`163bcee`) and the prior non-canonical branch was deleted both locally and remotely. A
fresh AUTO-002 session verified `main` == `origin/main`, a clean working tree, and both retained
stashes untouched, then created the canonical branch above from clean `main`, satisfying the
SSP's initial-start branch-binding and clean-tree checks
(`docs/workflow-automation/stage-prompts/README.md`; `STAGE_REGISTRY.md` §3 rules 1/14/4). Per
rule 17(a), registry state moved `BLOCKED → AUTHORIZED → IN_PROGRESS` with no new Human Owner
authorization act; the Human Owner's "I authorize AUTO-002." record stands unchanged. Full
record: `docs/workflow-automation/STAGE_REGISTRY.md` §5 ("execution precondition resolved"
entry).** The delivered state machine, authorization boundary, persistence, locking, local
observation, and remediation work passed the configured gates before the Human Owner directed
closure and one local commit. AUTO-003 remains `Planned` and requires separate authorization.

## GOV-AUTO-01 — Local Human-Gated Task Runner

Status: Done

Authorized by the Human Owner on 2026-07-27 as a governance and developer-experience task
(non-AUTO-family, so it carries no stage-registry entry). Adds a local Bash automation layer for
the repository's standard task cycle — `scripts/workflow-next.sh` (read-only preflight plus one
agent session), `scripts/prompts/implement-next-task.md` (the canonical implementation prompt),
`scripts/workflow-approve.sh` (the Human approval and single-commit gate), and
`docs/automation-workflow.md`. It automates the mechanical steps **without replacing the Human
Owner approval gate**: neither script pushes, merges, changes branches, alters upstream, or
touches stashes, and no commit occurs without two explicit `APPROVE` confirmations. No
dependencies were added. Implemented and validated 2026-07-27.

Closed `Current → Done` on 2026-07-28 by explicit Human Owner decision, which recorded that the
task was implemented, validated, approved, committed as `a302c95`, and merged into `main` via
`a3b5b0a`. The closeout bookkeeping had lagged the merge: `main` already carried the work while
this record, both mirrors, and `handover/PROJECT_HANDOVER.md` still showed the task `Current` and
uncommitted. The same decision resolved the resulting `maximum_current_tasks: 1` conflict and
authorized AUTO-004 as the single `Current` task
(`docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 16; §5, 2026-07-28 rows). Report:
`docs/reports/GOV-AUTO-01-completion-report.md`.

## GOV-AUTO-02 — Local Task Authorization and Launch Gate

Status: Done

Closed `Current → Done` on 2026-07-28 by explicit Human Owner decision, recording that the task
was implemented, validated, approved, and committed as
`d212e4d2dae2cd0a3510c54d7cd098fdfd5da548`. This is a governance-only closeout: no push, merge,
successor authorization, branch/upstream change, or stash mutation was authorized. No task is
`Current`, and AUTO-006 remains `Planned` and explicitly unauthorized. Report:
`docs/reports/GOV-AUTO-02-completion-report.md`.

Authorized by the Human Owner on 2026-07-28 as a governance and developer-experience task. Adds
`scripts/workflow-authorize.sh <TASK_ID> [claude|codex]`, a fail-closed local gate that accepts
only the task the Human Owner names, verifies readiness and the clean default-branch baseline,
requires two exact `AUTHORIZE` confirmations, reconciles the task/governance/registry/changelog/
handoff records, and creates exactly one local governance-only authorization commit. An optional
agent is launched through the existing `scripts/workflow-next.sh` only after that commit is
verified and the worktree is clean.

The gate never selects a task, closes a predecessor, implements a task, pushes, merges, changes
branch/upstream, or mutates stashes.

## AUTO-003 — Deterministic repository and validation skills

Status: Done

Authorized by the Human Owner on 2026-07-27 ("I authorize AUTO-003."), on branch
`feature/auto-003-repository-validation-skills` created from clean `main` at `87a5062` (the
AUTO-002 merge). Implemented the Repository, Contract, Validation, and Reporting skill families
(`docs/workflow-automation/SKILL_CONTRACTS.md` §2, §3, §4, §6) in `agentos_workflow/skills/`,
and resolved OD-2 (secret redaction) as an implementation decision (DD-33; also DD-34, DD-35).
Validation: 222 focused tests, 2,204 combined, engine collection unchanged at 978; ruff, black,
mypy, pre-commit, and `git diff --check` clean. The Human Owner approved the implementation on
2026-07-27 ("I approve the AUTO-003 implementation.") and authorized exactly one local commit,
created as `908be94`; push and merge were explicitly withheld. Closed to `Done` on 2026-07-27
when the Human Owner authorized GOV-AUTO-01 as **the single active task**, which requires
AUTO-003 to leave `Current` under `maximum_current_tasks: 1`. Report:
`docs/reports/workflow-automation/AUTO-003-completion-report.md`. Contract:
`docs/workflow-automation/stage-prompts/AUTO-003.md`. Future improvements carried forward from
AUTO-002—not AUTO-002 blockers—include the first authorized implementation of deterministic
infrastructure-retry audit accounting and any local repository/security observations needed by
AUTO-003. Remote/GitHub reconciliation remains assigned to the later GitHub integration stages.

## AUTO-004 — Claude Code CLI and Codex CLI providers

Status: Done

Closed `Current → Done` on 2026-07-28 by explicit Human Owner decision ("I approve the AUTO-004
implementation and authorize its formal closure and publication"), recording that the stage was
implemented, validated, approved by the Human Owner, and committed locally as `84616d5`. The same
decision authorized publication — pushing `feature/auto-004-model-providers` and merging it into
`main` — and, only after that integration and its closure checks passed, a separate explicit
authorization of AUTO-005. Registry state `IN_PROGRESS → COMPLETE`
(`docs/workflow-automation/STAGE_REGISTRY.md` §4; §5 closure row, 2026-07-28).

The commit `84616d5` was created after the stage completion report had already been written, so
that report's "no commit was performed" statement was accurate when written and is **not**
rewritten; the commit, the approval, and the merge are recorded in a new append-only addendum to
that report, per `docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 8.

Authorized by the Human Owner on 2026-07-28 ("I authorize AUTO-004 — Claude Code CLI and Codex
CLI providers"), directing branch creation from the clean, synchronized `main` (`a3b5b0a`),
implementation of AUTO-004 only, the standard implementation and validation workflow, a bounded
self-review, governance/handoff updates, and a stop for Human Owner approval; commit, push,
merge, and beginning AUTO-005 were all explicitly prohibited. The same decision closed
GOV-AUTO-01 to `Done` first, so this is the single `Current` task under
`maximum_current_tasks: 1`.

Initial-start preflight (`docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 4) passed: the
active stage is exactly AUTO-004, AUTO-002 (the contract's named precondition) and AUTO-003 are
`COMPLETE`, branch `feature/auto-004-model-providers` was created from clean `main`, and
`git status` was clean. Per rule 17(a) the registry state moves
`NOT_STARTED → AUTHORIZED → IN_PROGRESS` under this single recorded authorization act.

Delivers the Model Provider layer (`docs/workflow-automation/MODEL_PROVIDER_CONTRACTS.md`) in
`agentos_workflow/providers/`: the common `Provider` interface, `ClaudeCLIProvider` and
`CodexCLIProvider` as subprocess adapters over the configured executable and timeout, and
`MockProvider` as an offline test/dry-run substitute that is structurally excluded from any real
authorized workflow (`MVP_SCOPE.md` §3). Contract:
`docs/workflow-automation/stage-prompts/AUTO-004.md`. Report:
`docs/reports/workflow-automation/AUTO-004-completion-report.md`.

## AUTO-005 — PMO, implementation, QA, Git, merge, and closeout agents

Status: Done

Closed `Current → Done` on 2026-07-28 by explicit Human Owner decision ("I approve the formal
closure and publication of AUTO-005"), recording that the stage was implemented, validated,
approved by the Human Owner, and committed locally as `430cbb4`. The same decision authorized
publication — pushing `feature/auto-005-agents` and merging it into `main`. Registry state
`IN_PROGRESS → COMPLETE` (`docs/workflow-automation/STAGE_REGISTRY.md` §4; §5 closure row,
2026-07-28).

The commit `430cbb4` post-dates the stage completion report, which recorded the approval and the
authorized commit *before* that commit existed and is therefore **not** rewritten; the commit
hash, the closure, and the merge are recorded in a new append-only addendum to that report, per
`docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 8. This closure authorizes no successor:
AUTO-006, AUTO-007, GOV-2, and GOV-3 all remain `Planned` and unauthorized.

Authorized by the Human Owner on 2026-07-28 ("After AUTO-004 is successfully merged and all
closure checks pass, I authorize AUTO-005 — Agents"), as the single `Current` task after AUTO-004
was approved, closed, and merged into `main` under the same decision. The authorization was
explicitly conditioned on that integration succeeding first; it did, and the branch
`feature/auto-005-agents` was created from the resulting clean, synchronized `main`
(`4721f9a`). Registry state moves `NOT_STARTED → AUTHORIZED → IN_PROGRESS` per
`docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 17(a) under that single authorization act.

Delivers the six Agents of `docs/workflow-automation/AGENT_CONTRACTS.md` §2-7 in
`agentos_workflow/agents/` — `PMOAgent`, `ImplementationAgent`, `QAAgent`, `GitAgent`,
`MergeAgent`, `CloseoutAgent` — each restricted to its contract's Skills and Provider roles by a
capability broker, each returning a structured result, and none deciding its own workflow-state
transition. The `VALIDATING` step (`MACHINE_GATES.md` §3) and the bounded repair loop
(`FAILURE_RECOVERY.md` §1-2) are implemented as Orchestrator-owned sequences, not as a seventh
Agent, per `AGENT_CONTRACTS.md` §8.

Out of scope: real GitHub pull-request and merge integration (AUTO-006), which delivers the eight
GitHub-facing Skills `GitAgent` and `MergeAgent` call; those are named but deliberately unbound,
so an attempt to use one fails as `SKILL_UNAVAILABLE` naming AUTO-006 rather than returning a
fabricated success. Commit, push, merge, and beginning AUTO-006 are explicitly prohibited; the
stage stops for Human Owner approval. Contract:
`docs/workflow-automation/stage-prompts/AUTO-005.md`. Report:
`docs/reports/workflow-automation/AUTO-005-completion-report.md`.

## AUTO-006 — GitHub pull request, automatic squash merge, and closeout integration

Status: Done

Closed `Current → Done` on 2026-07-28 by explicit Human Owner decision ("I approve the formal
closure and publication of AUTO-006. The approved AUTO-006 implementation commit is
`d8d356d060076be4ad78afb4d20891004a946204`"), recording that the stage was implemented, validated,
approved by the Human Owner, and committed locally as
`d8d356d060076be4ad78afb4d20891004a946204`. The same decision authorized publication — pushing
`feature/auto-006-pr-merge-closeout` and merging it into `main`. Registry state
`IN_PROGRESS → COMPLETE` (`docs/workflow-automation/STAGE_REGISTRY.md` §4; §5 closure row,
2026-07-28).

The commit `d8d356d060076be4ad78afb4d20891004a946204` was created after the stage completion
report had already been written, so that report's "no commit … was performed" Confirmation
statement was accurate when written and is **not** rewritten; the commit, the approval, and the
merge are recorded in a new append-only addendum to that report, per
`docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 8.

Authorized by the Human Owner on 2026-07-28 through the local two-confirmation task gate
(`scripts/workflow-authorize.sh`). Branch `feature/auto-006-pr-merge-closeout` created from clean
`main`; registry state moved `AUTHORIZED → IN_PROGRESS`
(`docs/workflow-automation/STAGE_REGISTRY.md` §5).

Implemented and validated the same day: the eight Git/GitHub Skills of `SKILL_CONTRACTS.md` §5 —
`create_commit`, `push_stage_branch`, `create_pull_request`, `read_pull_request_state`,
`verify_head_sha`, `read_required_checks`, `enable_automatic_squash_merge`,
`verify_merge_completion` — in the new file `agentos_workflow/skills/git_github.py`, binding the
eight Skill names `GitAgent`/`MergeAgent` (AUTO-005) already called against fakes; no Agent code
changed. OD-1 resolved in favor of native GitHub auto-merge (`docs/workflow-automation/DECISIONS.md`
DD-37). 33 new tests, `agentos_workflow` suite 1,498-green, engine `tests` collection unchanged at
1,066. Self-review discovered, and recorded without fixing (outside this stage's allowed files),
that five of the eight Skill calls in AUTO-005's Agent code never forward
`allowed_environment_variables`, so `gh` cannot authenticate in a real deployment until a future
stage adds it (DD-38, `docs/workflow-automation/OPEN_QUESTIONS.md` OD-10). Report:
`docs/reports/workflow-automation/AUTO-006-completion-report.md`. Contract:
`docs/workflow-automation/stage-prompts/AUTO-006.md`.

This closure authorizes no successor: AUTO-007, GOV-2, and GOV-3 all remain `Planned` and
unauthorized.

## GOV-AUTO-03 — Human-Approved Commit with Automatic Task Closeout

Status: Done

Authorized by the Human Owner on 2026-07-28 as a governance and developer-experience task
(non-AUTO-family, so it carries no stage-registry lifecycle state — recorded in
`docs/workflow-automation/STAGE_REGISTRY.md` §5 for continuity only, per the GOV-AUTO-01/02
precedent). Extends `scripts/workflow-approve.sh` so that, after Human approval, it performs both
the approved implementation commit and the governance closeout of that same task (task queue
`Current → Done`, mirrors, project state, decision log, changelog, stage registry where
applicable, program changelog where applicable, completion-report addendum, handover, checksum)
as one controlled local commit — never a separate `docs(governance): close TASK_ID` commit. The
closeout transaction is gated on the same `project.id: ai-workflow-engine` marker
`scripts/workflow-authorize.sh` already uses, so any other repository (including every existing
disposable test sandbox) keeps the unchanged GOV-AUTO-01 plain approval/commit gate. Closeout
generation is fail-closed: every edit is an `awk`-guarded, precondition-checked replacement, and
any failure restores the generated governance files from a pre-closeout backup while leaving the
approved implementation diff untouched. 26 new focused tests in
`tests/test_workflow_approve_closeout.py`; the pre-existing GOV-AUTO-01/02 suites
(`tests/test_workflow_runner_scripts.py`, `tests/test_workflow_authorize_script.py`, 88 tests)
pass unmodified. Implemented and validated 2026-07-28; report:
`docs/reports/GOV-AUTO-03-completion-report.md`. Stopped for Human Owner approval before any
commit; does not begin AUTO-007.

## AUTO-007 — End-to-end dry run, recovery tests, and DASH integration

Status: Done

Requires its own fresh authorization. Contract:
`docs/workflow-automation/stage-prompts/AUTO-007.md`.

## AUTO-008 — Engine CI baseline: packaging, type-checking, and verified blocker fixes

Status: Done

Registered and authorized by the Human Owner on 2026-07-30 following an architectural audit which
established that `agentos_workflow` is substantially complete and heavily unit-tested but has never
run as a program and is verified by no automated gate: no `cli.py`, no `.agentos/workflow.yaml`,
absent from `pyproject.toml`'s wheel `packages`, not importable outside the repository root, not
type-checked, and its 1,575 tests never collected by CI. Its single end-to-end acceptance
demonstration (`docs/workflow-automation/MVP_SCOPE.md` §4) fails on `main`.

Scope: make the existing engine verifiable, adding no capability. Bring `agentos_workflow` and
`agentos_dashboard` under `testpaths`, wheel `packages`, and `mypy`; give `agentos_workflow` a
version independent of the `ai-workflow-engine` distribution version; resolve OD-10 and OD-11;
correct `AuthorizationBindingDriftError`'s inverted message; decouple the dashboard task-queue test
from mutable governance content; and remove the test-only production workarounds that OD-10/OD-11
made unnecessary. No new feature or public interface; no change to `src/ai_workflow_engine/**` or
`scripts/**`. Contract: `docs/workflow-automation/stage-prompts/AUTO-008.md`.

**Implemented, validated, approved, and closed `Current -> Done` on 2026-07-30.** All three suites
now run under one `pytest` invocation: default collection 1,160 -> 2,967, all passing, including the
previously-failing end-to-end acceptance demonstration with both test-only production workarounds
deleted. `mypy --strict` clean across all three packages (115 source files); `ruff` and `black`
clean; the wheel ships all three packages; all three importable from outside the repository root.
OD-10 and OD-11 resolved. `agentos_workflow` now carries its own version, so a legacy-engine release
can no longer invalidate its authorizations. Reported and deliberately not fixed: the eight
AUTO-006 Git/GitHub Skills are still unbound in `default_skill_registry()` (F-2, REQUIRED before
AUTO-013), and the `expected`/`actual` parameter convention still diverges between the two drift
raise sites (F-1, RECOMMENDED). Report:
`docs/reports/workflow-automation/AUTO-008-completion-report.md`.

## GOV-2 — Extend `check-governance` to validate stage-registry/lifecycle consistency

Status: Done

**Scope, assessed but not implemented during 2026-07-24 governance recovery** (this is a
documentation-only task record; no code was written). Confirmed by reading
`src/ai_workflow_engine/governance/validators.py`: `check_governance`/`check_task_state` today
validate only (a) task-status agreement across the configured Markdown mirrors and (b)
byte-equality of configured regex-extracted "facts" (currently only the `version` fact). Neither
function reads `docs/workflow-automation/STAGE_REGISTRY.md` or
`docs/agentos-dashboard/STAGE_REGISTRY.md` at all, so none of the following are machine-checked
today: a registry's per-stage `State` cell (e.g. `BLOCKED`) against its task's
`docs/TASK_QUEUE.md` status (e.g. `Current`) under the documented state-model mapping (this needs
semantic mapping, e.g. `BLOCKED`/`AUTHORIZED`/`IN_PROGRESS`/... ≈ `Current`, not the existing
fact-checker's byte-equality, which cannot express a mapping); agreement of a shared control rule
across the AUTO and DASH registries where §1 claims equivalence (as audited manually,
2026-07-24 — see `docs/DECISION_LOG.md`); or a `Future Revisions`-governed document's declared
`Version` bump actually corresponding to a MAJOR/MINOR change classification (would need either
richer document metadata than a `Version` table cell provides today, or a Human-Owner-recorded
classification per change to check against).

**Recommended shape when authorized:** a new `governance/registry.py` module parsing each
program's `STAGE_REGISTRY.md` §Registry table (tolerant Markdown-table parsing, matching this
project's existing conservative-parsing principle, `docs/DECISION_LOG.md` "Milestone 1" entry),
a documented state→task-status mapping table (not hard-coded per program, since DASH and AUTO
both already state the same mapping), a new `check-name` (e.g. `check-registries`) wired into
`workflowctl verify`, and a config surface in `self-governance.yaml` naming which registries to
check (this repository currently has two; a target repository being governed by a future engine
would have its own). Version-policy compliance (MAJOR/MINOR classification correctness) is
flagged as the hardest of the three to automate safely and may need to stay a documented,
human-reviewed judgment call rather than a machine check, unless a future revision adds a
structured changelog-per-document field the tool can parse.

**Why not implemented now:** out of scope for a governance-recovery session (documentation and
process correctness, not new engine functionality); writing new validator code is implementation
work this session's mandate excludes, and — consistent with the very rules this recovery has been
enforcing — adding new `workflowctl` capability is itself engine work requiring its own stage
authorization and independent review, not something to slip in unauthorized during a
documentation pass. Tests are correctly expected for every new validator per this repository's
existing test-coverage discipline (`docs/AGENT_PROTOCOL.md`), to be added alongside the
implementation, not before it exists. Requires its own fresh authorization, as an ordinary
(non-AUTO/DASH-family) engine task.

## GOV-3 — Attempt-aware report artifact naming in the Reporting Skills

Status: Done

**Recorded as explicit future work by Human Owner decision on 2026-07-28, when approving AUTO-005**
("Record the QA report collision as explicit future work. Do not fix it within AUTO-005 and do not
expand the current scope."). This is a task record only; no code was written for it.

**The defect.** `generate_qa_report` — and, by the same construction, `generate_stage_report`,
`generate_failure_report`, and `generate_closeout_report` in `agentos_workflow/skills/reporting.py`
— writes to a fixed path `<audit_root>/<workflow_id>/reports/<report_kind>.json`, one artifact per
workflow identifier per kind, and correctly refuses to overwrite an existing artifact whose content
differs (append-only audit semantics, `AUDIT_MODEL.md`). But a single workflow legitimately
produces **several** genuinely different reports of the same kind: the bounded repair loop
(`FAILURE_RECOVERY.md` §1) runs up to four QA rounds and up to four implementation attempts, each
with its own verdict, findings, and diff. The second round therefore fails on the *artifact* rather
than on the code under review.

**AUTO-005's in-scope workaround, and why it is not the fix.** `QAAgent` writes each round under a
per-attempt audit scope derived from the workflow identifier, because `agentos_workflow/skills/**`
was outside AUTO-005's allowed paths. Every artifact stays inside the audit root and the workflow's
own audit log keeps the real, undecorated identifier, so the rounds remain joined — but the
per-attempt reports live in sibling directories rather than inside that workflow's own audit
directory, which is not what `AUDIT_MODEL.md` intends and is not a shape to build on.

**Recommended shape when authorized:** give the four `_generate_report` callers an optional,
validated attempt/sequence component so one workflow directory can hold
`reports/qa.1.json`, `reports/qa.2.json`, … under its own `<workflow_id>`; keep the existing
content-hash idempotency and differing-content refusal per artifact unchanged; and remove
`QAAgent._report_scope`'s derived-identifier workaround in the same change, so the two cannot drift.
Tests belong alongside the implementation per `docs/AGENT_PROTOCOL.md`.

Requires its own fresh authorization, as an ordinary (non-AUTO/DASH-family) engine task. It is
**not** an AUTO-005 blocker: the Human Owner accepted the documented limitation for that stage.
Full description: `docs/reports/workflow-automation/AUTO-005-completion-report.md`, "Known
limitations" item 1.

**Authorized by the Human Owner on 2026-07-29** through the local two-confirmation task gate
(`scripts/workflow-authorize.sh`), superseding the "task record only" note above: implemented and
validated the same day on `main`, stopped for Human Owner approval before any commit. The four
`_generate_report` callers in `agentos_workflow/skills/reporting.py` now take an optional,
validated `sequence`, so one workflow's own audit directory holds `reports/qa.1.json`,
`reports/qa.2.json`, … ; the content-hash idempotency and the differing-content refusal are
unchanged per artifact; and `QAAgent._report_scope`'s derived-identifier workaround was removed in
the same change, so the two cannot drift. The distinct caller-side question — the pre-loop QA round
and the repair loop's first internal round both being numbered attempt 1 — is recorded as OD-12
(`docs/workflow-automation/OPEN_QUESTIONS.md`) rather than resolved here, because it is a decision
about who assigns round numbers, not about artifact naming. Report:
`docs/reports/GOV-3-completion-report.md`.

## DASH-002 — Repository adapter and read-only snapshot

Status: Done

Root-confined read-only file adapter, fixed-argv Git read adapter, snapshot builder with
staleness fingerprint. Contract: `docs/agentos-dashboard/stage-prompts/DASH-002.md`.

**Authorized by the Human Owner on 2026-07-29** through the local two-confirmation task gate
(`scripts/workflow-authorize.sh`); implemented and validated the same day, **uncommitted**,
stopped for Human Owner approval. Created `agentos_dashboard/` with `core/paths.py` (root
confinement, lexical traversal rejection, symlink-escape refusal, the SC-08 deny-list checked
both before and after resolution), `core/files.py` (capped, error-tolerant reads with head/tail
windows and streamed digests; no write path exists in the module), `core/gitread.py` (seven
named read-only functions over fixed argv with `LC_ALL=C`, a 5 s timeout, and typed failures),
and `core/snapshot.py` (the `SOURCE_OF_TRUTH.md` §3 watched-file fingerprint, TR-04 findings, and
the TR-05 staleness test), plus 115 tests in `agentos_dashboard/tests/`. No file under `src/`,
`tests/`, `scripts/`, `handover/`, `pyproject.toml`, or any other engine path was touched, and no
dependency was added. Report: `docs/reports/agentos-dashboard/STAGE-02-completion.md`.

**Two governance conflicts were found and recorded rather than resolved unilaterally**
(`docs/agentos-dashboard/OPEN_QUESTIONS.md`): OD-D10 — the stage's registered branch
`feature/dash-002-repo-adapter` was **not** created, because the local runner prompt forbids the
session from creating or switching branches, so the work sits on `main` and
`scripts/workflow-approve.sh` will refuse the closeout until the tree is on that branch; and
OD-D11 — the approval gate looks for `DASH-002-completion-report.md` while this program's
convention (and DASH-001's precedent) is `STAGE-02-completion.md`. Registry state stays
`AUTHORIZED` (`docs/agentos-dashboard/STAGE_REGISTRY.md` §4, 2026-07-29 preflight row).

## DASH-003 — Governance and Markdown parsing

Status: Done

Tolerant parsers for the governance mirrors, decision log, orchestration implementation state,
and handover manifest; consistency engine v1. Contract:
`docs/agentos-dashboard/stage-prompts/DASH-003.md`.

Implemented and validated 2026-07-29: `agentos_dashboard/parsing/` (five tolerant parsers) and
`agentos_dashboard/services/consistency.py`, plus 157 tests (`agentos_dashboard/tests/`)
including a malformed-document fixture corpus. No parser raises for malformed input; every
degradation becomes a `ConsistencyFinding`. Recurred the exact OD-D10 branch-vs-runner conflict
DASH-002 already recorded (`docs/agentos-dashboard/OPEN_QUESTIONS.md`): implemented on `main` in
the working tree, uncommitted, awaiting Human Owner approval. Report:
`docs/reports/agentos-dashboard/STAGE-03-completion.md`.

## DASH-004 — Local backend and dashboard shell

Status: Done

Loopback-only web shell with security baseline and Overview page. Contract:
`docs/agentos-dashboard/stage-prompts/DASH-004.md`.

**Authorized by the Human Owner on 2026-07-30** through the local two-confirmation task gate
(`scripts/workflow-authorize.sh`); implemented and validated the same day on the registered branch
`feature/dash-004-dashboard-shell` (created automatically by GOV-AUTO-04's branch-preparation
routine — the first DASH stage this repository has run without recurring OD-D10), **uncommitted**,
stopped for Human Owner approval. Task status remains `Current`.

Delivered a new top-level package surface, exactly the contract's Allowed list:
`agentos_dashboard/settings.py` (`AWED_`-prefixed environment settings parsed into a frozen
Pydantic model; no `.env` file is ever loaded; a non-loopback `AWED_HOST` is refused at
construction, SC-01/SC-10); `agentos_dashboard/main.py` (the `create_app()` factory — FastAPI app,
`SecurityMiddleware`, the `/dash/api/v1` router, the web page router, typed exception handlers;
interactive API docs disabled outright since their default assets are CDN-hosted, which SC-05
forbids); `agentos_dashboard/__main__.py` (`python -m agentos_dashboard`: refuses a non-loopback
bind, acquires a single-instance PID lockfile kept outside the repository under the platform temp
directory — SC-02/SC-24, and deliberately not under `data/agentos_dashboard/`, which stays
DASH-008's to create — prints the exact URL, and supports `--check` for a bind-free startup smoke
test); `agentos_dashboard/api/` (`envelope.py`, `errors.py` — the `{ok, data, error}` contract and
`API_SPEC.md` §5's typed error catalogue; `security.py` — one middleware enforcing the `Host`
allowlist (SC-36), CSRF double-submit cookie enforcement on every state-changing request (SC-03),
and the CSP/`X-Content-Type-Options`/`Cache-Control: no-store` response headers (SC-04/SC-05,
`API_SPEC.md` §1); `lock.py` — the PID lockfile; `snapshot_cache.py` — an in-process cached
`RepositorySnapshot` (DASH-002) with lazy staleness rebuild and a non-blocking `refresh()` that
returns `409 SNAPSHOT_BUILDING` under contention rather than queuing; `overview.py` — DR-010..013's
aggregate, composing the DASH-003 task-queue/project-state parsers and consistency engine with the
snapshot's own Git status, rendering an explicit healthy-empty state for every field nothing yet
populates (DR-013; `AuditEvent`s and gate-history do not exist until DASH-008 builds
`dashboard.db`); `routes.py` — EP-01 (health), EP-02 (snapshot metadata), EP-03 (status/Overview),
and EP-20 (snapshot refresh), the read surface this stage delivers of `API_SPEC.md`'s full
register); and `agentos_dashboard/web/` (Jinja2 `base.html`/`overview.html` — PG-01, autoescaped by
default, English operator UI with the full left-navigation register per `UI_SPEC.md`, only
Overview linked and every other page marked not-yet-available; self-hosted `static/style.css`
(dark-mode via `prefers-color-scheme`, color-blind-safe badges) and `static/app.js` (the Refresh
action's CSRF-aware fetch, with a confirmation dialog)). No repository write path exists anywhere
in the new code (asserted by a tests source scan). Dependencies: exactly the optional `dashboard`
group OD-D9 already declared (`fastapi`, `jinja2`, `uvicorn`); no new dependency was added.

71 new tests in `agentos_dashboard/tests/` (settings parsing/validation, the PID lockfile
including stale-lock reclamation, the snapshot cache including refresh contention, the Overview
aggregate against fixture and real-repository content, the security middleware's Host/CSRF/header
behavior, the API routes' envelope shape, the web page's rendering and an XSS escaping proof
against hostile repository content, and `__main__`'s startup/`--check`/port-in-use/lock-conflict
paths) plus a small dependency-free ASGI test client
(`agentos_dashboard/tests/_asgi_client.py`) written because `starlette.testclient.TestClient`
requires an HTTP client package (`httpx`/`httpx2`) this stage is not authorized to add.

**One pre-existing, environment-dependent test failure was observed and is unrelated to this
diff**: `agentos_workflow/tests/e2e/test_dry_run.py::test_full_workflow_created_to_done_...`
fails on an `engine_version` authorization-binding drift — the same class of installed-package-
version-vs-hardcoded-test-expectation mismatch GOV-2/GOV-3/GOV-AUTO-04 already recorded, now
recurring in the opposite direction (this session's `pip install -e '.[dashboard]'`, run only to
install the already-declared optional dependency group, refreshed the installed package's
reported version). `git status --porcelain -- agentos_workflow/` is empty: no byte under that
package changed, so the failure cannot be caused by this diff.

**No independent review was performed for this stage**, and none is claimed; this is an ordinary
implementation stage, and the bounded self-review below is the standard applied. DASH-009 carries
the program's mandatory independent security review, where every SC control this stage implements
(SC-01 through SC-05, SC-10, SC-24, SC-25, SC-29, SC-33, SC-34, SC-36) gets its formal
reconciliation-log entry per `SECURITY_MODEL.md` §7.

## DASH-005 — Workflow board and task detail

Status: Planned

Queue-lane board (Planned/Current/Done), workflow-stage strip, ORCH program lane, task detail
views. Contract: `docs/agentos-dashboard/stage-prompts/DASH-005.md`.

## DASH-006 — Git, upstream, handover, and consistency views

Status: Planned

Git status/history pages, upstream verification, handover checksum viewer, consistency page.
Contract: `docs/agentos-dashboard/stage-prompts/DASH-006.md`.

## DASH-007 — Stage registry and prompt generation

Status: Planned

Registry loader, precondition engine, hash-recorded gated prompt generation with refusal path.
Contract: `docs/agentos-dashboard/stage-prompts/DASH-007.md`.

## DASH-008 — Run records, evidence, and audit timeline

Status: Planned

Non-authoritative local SQLite store, append-only audit trail, run/evidence/audit pages.
Contract: `docs/agentos-dashboard/stage-prompts/DASH-008.md`.

## DASH-009 — Security hardening and failure handling

Status: Planned

Adversarial security test corpus and failure-handling hardening, with mandatory independent
fresh-session security review. Contract: `docs/agentos-dashboard/stage-prompts/DASH-009.md`.

## DASH-010 — Integration testing, documentation, and release readiness

Status: Planned

End-to-end tests, operator manual, MVP closure recommendation to the Human Owner. Contract:
`docs/agentos-dashboard/stage-prompts/DASH-010.md`.

## GOV-AUTO-04 — Automatic registered-branch preparation and canonical completion-report naming

Status: Done

**Proposed by Human Owner directive on 2026-07-29 as a governance and developer-experience task**
(non-AUTO-family, so it carries no stage-registry entry, per the GOV-AUTO-01/02/03 precedent).
This is a task record only; no code has been written or authorized.

**The defects.** Two recurring integration gaps between `scripts/workflow-authorize.sh`,
`scripts/workflow-next.sh`, and `scripts/workflow-approve.sh`, both first observed and recorded as
OD-D10 and OD-D11 in `docs/agentos-dashboard/OPEN_QUESTIONS.md` during DASH-002 and recurring
identically at DASH-003:

1. **OD-D10 — registered branch vs. no-branch runner rule.** AUTO/DASH stages are contractually
   required to run on a registered feature branch created from clean `main`
   (`docs/agentos-dashboard/STAGE_REGISTRY.md` §2 rules 4/15), but `workflow-authorize.sh` runs on
   `main` and explicitly documents the branch as "created later by the implementation session,
   never by this gate" (lines 265-266), while the canonical runner prompt
   (`scripts/prompts/implement-next-task.md` §7) flatly forbids the session from creating or
   switching branches. No session can satisfy both, so DASH-002 and DASH-003 were both
   implemented on `main`, and `workflow-approve.sh` (line 535) then refuses the closeout until the
   Human Owner manually runs `git switch -c feature/...`.
2. **OD-D11 — completion-report filename mismatch.** The Dashboard program's own naming
   convention (`docs/agentos-dashboard/STAGE_REGISTRY.md` §3) is
   `docs/reports/agentos-dashboard/STAGE-XX-completion.md`, but `workflow-approve.sh`'s
   report-discovery loop (lines 544-556) only accepts `<TASK_ID>-completion-report.md` variants,
   so it cannot find a report written under the documented convention without a manual rename or
   duplicate copy.

**Scope.** (1) Give `workflow-authorize.sh`/`workflow-next.sh` one shared, tested
branch-preparation routine that, after the authorization commit, safely creates or switches to a
registry-governed task's registered branch (refusing on divergence, unexpected commits, a dirty
worktree, or ambiguous history; GOV/main-branch tasks stay on `main`); `workflow-next.sh` verifies
the branch precondition before launching an agent. (2) Extend `workflow-approve.sh`'s
report-discovery to also accept the canonical `STAGE-XX-completion.md` name for DASH tasks (stage
number resolved from registry data, not unchecked filename construction), rejecting path
traversal and refusing on conflicting duplicate reports, while keeping existing
`<TASK_ID>-completion-report.md` support for AUTO/GOV tasks unchanged.

**Allowed paths:** `scripts/workflow-authorize.sh`, `scripts/workflow-next.sh`,
`scripts/workflow-approve.sh`, `scripts/lib/**`, `scripts/prompts/implement-next-task.md`,
`tests/**workflow**`, `docs/automation-workflow.md`, `docs/workflow-automation/**`,
`docs/agentos-dashboard/**`, `docs/TASK_QUEUE.md`, `docs/current_task.md`,
`docs/remaining_tasks.md`, `docs/PROJECT_STATE.md`, `docs/DECISION_LOG.md`, `docs/CHANGELOG.md`,
`docs/reports/**`, `handover/PROJECT_HANDOVER.md`, `handover/PROJECT_CHECKSUM.md`.

**Out of scope:** automatic push, automatic merge, pull-request creation, next-task automatic
authorization, unrelated AgentOS engine/agent/provider/GitHub code, dashboard runtime code, and
resolving any open decision other than OD-D10/OD-D11.

**Acceptance criteria:** registered AUTO/DASH branches are prepared automatically and safely with
no manual `git switch -c` step; canonical DASH `STAGE-XX-completion.md` reports are accepted
directly with no manual report copy; existing TASK-ID report and branch behavior for AUTO/GOV
tasks remains backward compatible; dirty trees, divergent branches, malformed registry data, path
traversal, and conflicting reports are all refused without mutation; regression tests cover both
success and refusal paths; no push, merge, force, reset, branch deletion, or stash operation is
introduced; OD-D10 and OD-D11 are resolved with evidence.

Requires its own fresh, explicit Human Owner authorization
(`scripts/workflow-authorize.sh GOV-AUTO-04 [claude|codex]`) before any implementation may begin.
Recommended implementation commit message:
`fix(workflow): automate registered branches and canonical report discovery (GOV-AUTO-04)`.

**Authorized by the Human Owner on 2026-07-29** through the local two-confirmation task gate
(`scripts/workflow-authorize.sh`), superseding the "requires its own fresh authorization" note
above: implemented and validated the same day on `main`, **uncommitted**, stopped for Human Owner
approval. Task status remains `Current`.

Delivered a new shared library, `scripts/lib/branch_prepare.sh`
(`workflow_registered_branch`/`workflow_prepare_branch`/`workflow_verify_branch`), sourced by both
`scripts/workflow-authorize.sh` and `scripts/workflow-next.sh`. `workflow-authorize.sh` now
creates or safely switches to a registry-governed task's registered branch immediately after its
own authorization commit — refusing on a dirty worktree, an unexpected starting branch, or an
already-existing branch that diverges from the commit it would be created from — while GOV/plain
tasks (no registry row) stay on the default branch exactly as before; a preparation failure is
reported distinctly (`EXIT_BRANCH_PREP`, exit 10) without disturbing the already-created
authorization commit. `workflow-next.sh` independently verifies, read-only, that the Current
task's registered branch matches the working branch before launching an agent
(`EXIT_BRANCH_MISMATCH`, exit 8). Resolves OD-D10.

`scripts/workflow-approve.sh`'s completion-report discovery now also accepts the Dashboard
program's canonical `docs/reports/agentos-dashboard/STAGE-XX-completion.md` name for a DASH task,
with the two-digit stage number cross-checked against the registry's own Branch cell — never
derived from unchecked filename construction on the task ID alone — so a disagreeing or malformed
registry silently disables the canonical lookup rather than guessing, and two present reports with
differing content are refused outright (`EXIT_REPORT_CONFLICT`, exit 18); byte-identical
duplicates (the shape DASH-002/DASH-003 already left behind) are accepted without preferring one
over the other. Existing `<TASK_ID>-completion-report.md` behavior for AUTO/GOV tasks is
unchanged. Resolves OD-D11. Rationale for both resolutions:
`docs/agentos-dashboard/DECISIONS.md` DD-08.

Validation: 40 new focused tests (`tests/test_workflow_branch_prepare.py`,
`tests/test_workflow_report_discovery.py`, and additions to
`tests/test_workflow_authorize_script.py`/`tests/test_workflow_runner_scripts.py`); full
repository suite 2726-green; ruff, black, and mypy (`src` and `agentos_workflow`) clean;
`git diff --check` clean; `workflowctl verify` PASS on all five checks. Report:
`docs/reports/GOV-AUTO-04-completion-report.md`.

**Not yet done:** uncommitted, awaiting a separate Human Owner approval via
`scripts/workflow-approve.sh`, which performs the implementation commit and the deterministic
governance closeout together. No push, merge, branch, upstream, or stash operation was performed.

## GOV-AUTO-05 — Fix resolved-blocker false positives in authorization

Status: Done

**Registered by Human Owner directive on 2026-07-30 as a governance task** (non-AUTO-family, so
it carries no structured stage-registry row, per the GOV-AUTO-01/02/03/04 convention). This is a
task record only; the already-prepared patch has not been applied, no implementation has been
authorized, and no task has become `Current`.

**Scope.** Fix `scripts/workflow-authorize.sh` so resolved or negated blocker text does not
falsely prevent task authorization. The defect includes broad task-section matching on the word
`blocked`; scanning the entire `OPEN_QUESTIONS.md`, including the `## Resolved` section; and
false positives from phrases such as `no longer blocked`, `not blocked`, and `formerly blocked`.

**Required behaviour:** explicit `Status: Blocked` still refuses; active unresolved open
questions still refuse; only the `## Open` section is authoritative; resolved entries do not
block; negated or historical wording does not block; predecessor, registry, branch, dirty-tree,
and Human confirmation checks remain unchanged.

**Allowed implementation paths:** `scripts/workflow-authorize.sh`,
`tests/test_workflow_authorize_script.py`, `tests/**workflow**`,
`docs/automation-workflow.md`, `docs/TASK_QUEUE.md`, `docs/current_task.md`,
`docs/remaining_tasks.md`, `docs/PROJECT_STATE.md`, `docs/DECISION_LOG.md`,
`docs/CHANGELOG.md`, `docs/reports/**`, `handover/PROJECT_HANDOVER.md`, and
`handover/PROJECT_CHECKSUM.md`.

**Out of scope:** workflow branch preparation; report discovery; push or merge automation;
dashboard runtime; AgentOS engine; and unrelated governance cleanup.

**Acceptance criteria:** `Status: Blocked` refuses; an active open question explicitly blocking a
task refuses; resolved questions never block; `no longer blocked`, `not blocked`, and historical
`formerly blocked` text do not block; DASH-004 reaches normal authorization after OD-D9
resolution; existing authorization safety checks remain unchanged; regression tests cover
positive and negative cases; and no push, merge, reset, rebase, force, branch deletion, or stash
operation is introduced.

Requires its own fresh, explicit Human Owner authorization
(`scripts/workflow-authorize.sh GOV-AUTO-05 [claude|codex]`) before any implementation may begin.
Recommended implementation commit message:
`fix(workflow): avoid resolved blocker false positives (GOV-AUTO-05)`.

**One-time Human Owner governance exception — 2026-07-30.** The Human Owner explicitly authorized
implementation of GOV-AUTO-05 despite the known false-positive defect in
`scripts/workflow-authorize.sh`: the normal gate could not authorize the task without first
applying the fix the task exists to implement. This manual `Planned → Current` record is the sole
authorization exception; it authorizes only GOV-AUTO-05's registered scope and does not authorize
another task, push, merge, branch creation or switching, rebase, reset, amend, force/history
rewrite, or stash operation. Implementation and Human Owner approval remain separate.

Implemented and validated under that exception, uncommitted and stopped for Human Owner approval.
The canonical task status parser now reads only the first non-blank, whole-line status field after
the task heading; quoted examples, Markdown emphasis, acceptance criteria, explanatory prose, and
later fenced examples cannot override `Status: Current`. Explicit canonical `Status: Blocked`
still refuses. The same canonical-field discipline now also governs approval-side Current-task
discovery and guarded `Current → Done` replacement; approval no longer scans explanatory task
prose for blocker keywords. Open-question gating reads only structured entries in `## Open`,
ignores resolved entries, and distinguishes active blocking declarations from negated or
historical wording. Existing predecessor, registry, branch, report, scope, dirty-tree, Human
confirmation, closeout, staging, checksum, commit, remote, and stash protections remain unchanged.
Report: `docs/reports/GOV-AUTO-05-completion-report.md`.

## GOV-AUTO-06 — Bind delivered Git/GitHub skills into the default AgentOS skill registry

Status: Done

Registered and authorized by the Human Owner on 2026-07-30 to resolve the finding AUTO-008 reported
and deliberately did not fix. AUTO-006 delivered all eight Git/GitHub Skills in
`agentos_workflow/skills/git_github.py`, but `agentos_workflow/agents/__init__.py` was never
updated: `PROVISIONAL_SKILL_NAMES` still classifies all eight as undelivered, and
`default_skill_registry()` still does not bind them. `GitAgent` and `MergeAgent` therefore cannot
invoke their own contracted Skills through the production registry — the broker returns a typed
"not yet implemented; it is delivered by AUTO-006" failure — and the end-to-end dry run has to
register all eight by hand. This blocks any real run.

Scope: remove the stale provisional classification for the eight genuinely-implemented Skills and
bind the existing implementations into the production registry. No new GitHub feature, no new
public interface, no change to agent capability contracts, `CapabilityBroker` enforcement, the
environment allowlist rules, or workflow state-machine behaviour. Does not address F-1 and does not
begin AUTO-009.

Recorded as a governance/engine follow-up task outside the AUTO family, per the GOV-AUTO-01
precedent (`docs/workflow-automation/STAGE_REGISTRY.md` §5): no stage-registry row, no stage
contract, no lifecycle state in that registry.

**Implemented, validated, approved, and closed `Current -> Done` on 2026-07-30.** All eight
delivered Git/GitHub Skills are bound in `default_skill_registry()` (32 -> 40 entries), each
identity-verified against `skills/git_github.py`; `PROVISIONAL_SKILL_NAMES` is now empty but
retained as a public symbol, since the mechanism it drives is general and deleting it would have
removed a name from `__all__`. `GitAgent` and `MergeAgent` resolve every contracted Skill through
the production registry — the path no test previously traversed. Capability isolation is unchanged
and proven by a negative test: `AGENT_SKILL_CONTRACTS` is AST-identical to its prior value, and all
six Agents still refuse every Git/GitHub Skill their own contract omits. `_is_unbound` was widened
rather than allowed to decay, preserving the existing `SKILL_UNAVAILABLE` classification for a
missing binding. 2,978 tests pass; `mypy --strict` clean over 115 source files; `ruff`, `black`, and
pre-commit clean. F-1 and AUTO-009 remain untouched. Report:
`docs/reports/GOV-AUTO-06-completion-report.md`.

## GOV-AUTO-07 — Normalize the `AuthorizationBindingDriftError` expected/actual convention

Status: Done

Registered and authorized by the Human Owner on 2026-07-31 to resolve F-1, the finding AUTO-008
reported and deliberately did not fix (`docs/reports/workflow-automation/AUTO-008-completion-report.md`
§2.4). The `expected`/`actual` argument convention diverges between the two authorization-drift call
paths in `agentos_workflow/orchestrator/engine.py`: `_detect_authorization_binding_drift` passes the
independently-supplied **current** value as `expected` and the persisted `AuthorizationRecord` as
`actual`, while `_validate_live_resume_observation` / `_live_drift` passes the persisted record as
`expected` and the **live observation** as `actual`. The two are mutually inverted, so no fixed
"bound value X / current value Y" wording can be correct at both — which is why AUTO-008 could only
neutralize the rendered message rather than fix it. `.expected` and `.actual` therefore carry
opposite meanings depending on which safety path raised, on the primary authorization-invalidation
path.

Scope: define and enforce one canonical convention — `expected` is the authorization-bound or
otherwise required reference value; `actual` is the current runtime, repository, or supplied value
judged against it — and normalize every raise site of `AuthorizationBindingDriftError` to it. The
public attribute names `field`, `expected`, and `actual` are preserved. Regression tests must cover
every affected drift path. No new feature, no new public interface, no change to workflow
transitions, Git/GitHub skill registration, the public CLI, or any other exception type. Does not
begin AUTO-009.

Recorded as a governance/engine follow-up task outside the AUTO family, per the GOV-AUTO-01
precedent (`docs/workflow-automation/STAGE_REGISTRY.md` §5): no stage-registry row, no stage
contract, no lifecycle state in that registry.

**Implemented, validated, approved, and closed `Current -> Done` on 2026-07-31.** One canonical
convention is now documented on `AuthorizationBindingDriftError` itself and enforced at all 43 of
its raise/helper call sites: `expected` is the authorization-bound value where the comparison has
one, otherwise the invariant the check requires; `actual` is the current runtime, repository,
live-observation, or caller/disk-supplied value judged against it. Three clusters were normalized —
`_detect_authorization_binding_drift` (all ten `_BINDING_DRIFT_FIELDS`), two `_live_drift` calls in
`_validate_live_resume_observation` (one of which contradicted the raise directly beside it on the
same field), and the four cross-record checks in `_validate_persisted_authorization_evidence`, which
reported the persisted `AuthorizationRecord` as `actual` despite it being the root of trust. Every
comparison is symmetric, so which drifts are detected, in what order, and with what durable
`-> FAILED` consequence is unchanged; only the reported orientation moved. The public attributes
`field`/`expected`/`actual` and the rendered message are byte-identical, pinned by a test. 3,005
tests pass (2,978 + 27 new, none skipped); the new suite fails 17 of 27 against the pre-fix engine,
and the only pre-existing test that broke was AUTO-008's own message pin. `mypy --strict` clean over
115 source files; `ruff`, `black`, and pre-commit clean. AUTO-009 remains untouched and
unauthorized. Report: `docs/reports/GOV-AUTO-07-completion-report.md`.

## AUTO-009 — WorkflowService boundary and read-only `workflowctl auto` surface

Status: Done

Registered and authorized by the Human Owner on 2026-07-31, in one written directive, as the
single `Current` task. This is the first stage of the AUTO family since AUTO-008 closed; the two
intervening tasks (GOV-AUTO-06, GOV-AUTO-07) were governance follow-ups outside the family that
resolved AUTO-008's two deferred findings, and both explicitly left AUTO-009 unauthorized.

Scope: create the first public application-service boundary for the automated workflow engine —

    workflowctl auto -> WorkflowService -> agentos_workflow read-only state, audit,
    report, and configuration APIs

`WorkflowService` (`agentos_workflow/service.py`) exposes exactly four read-only operations —
`status`, `list`, `audit`, `report` — returning typed results and containing no CLI formatting, no
Telegram logic, no shell interaction, no interactive prompts, no agent execution, and no Git or
GitHub mutation. A new additive Typer sub-application (`agentos_workflow/cli_auto.py`) surfaces the
same four operations as `workflowctl auto status|list|audit|report`, following the repository's
existing human/JSON output, exit-code, error-envelope, debug, and stdout/stderr conventions.
Registration into `src/ai_workflow_engine/cli.py` is the smallest possible additive change; no
existing command is moved, refactored, or changed in behaviour or output.

Explicitly out of scope and prohibited in this stage: workflow start, authorization, approval,
rejection, resume, cancellation; Preparation/Reviewer/Implementer Mode; Claude or Codex execution;
result-contract redesign; configurable approval; timeout behaviour; daemon; Telegram; Git commit,
push, or branch deletion; GitHub PR; CI polling; merge; Python governance closeout; shell-script
retirement; and AUTO-010 or any successor behaviour. No workflow state-machine change is expected
or permitted absent a proven blocker. Newly discovered defects that do not block AUTO-009 are
recorded and classified in the completion report and deferred to a future governed stage.

Report: `docs/reports/workflow-automation/AUTO-009-completion-report.md`.

**Implemented, validated, approved, and closed `Current -> Done` on 2026-07-31.** The engine's
first public application-service boundary exists. `WorkflowService` (`agentos_workflow/service.py`)
exposes exactly four read-only operations — `status`, `list`, `audit`, `report` — returning frozen,
`extra="forbid"` typed results, and `agentos_workflow/cli_auto.py` surfaces the same four as
`workflowctl auto`. `src/ai_workflow_engine/cli.py` changed by +14/-0 lines and reaches AgentOS
through exactly one name, `agentos_workflow.cli_auto.auto_app`.

Read-only-ness is demonstrated, not asserted. Every mutation channel was booby-trapped —
`RepositoryLock.acquire`/`__enter__`/`release`, `subprocess.run`/`Popen`, `os.system`/`fork`/
`posix_spawn`, both `StateStore` append methods, and all six reporting writers — and none was
reached by any of the six operation invocations, while a path+mode+mtime+bytes digest over the
state directory, the audit directory, and the target repository stayed identical across each. AST
assertions confirm the service imports no lock or session symbol and calls no write method.
Symlinked workflow directories, history files, and report files are still refused; a malformed
report is surfaced, never repaired.

Two new primitives were added to the modules that already own the corresponding storage layout,
not to the service, so the `O_NOFOLLOW` confinement discipline is not duplicated:
`StateStore.list_workflow_ids()` (+33) and `skills.reporting.read_reports()` (+180). Neither
creates missing storage.

Compatibility: thirteen of fourteen byte-compared existing command invocations are identical to
the `98acc195` baseline; the fourteenth is `workflowctl --help`, which gains the intended `auto`
group and nothing else. 3,151 tests pass (3,005 + 146 new, none skipped, none xfail);
`mypy --strict` clean over 117 source files; `ruff`, `black`, and pre-commit clean; the wheel
carries both new modules and both import from outside the repository root.

Six non-blocking defects (D1-D6) were recorded, classified, and deferred — none fixed. No workflow
state-machine change was needed. AUTO-010 and every later roadmap phase remain untouched and
unauthorized. Report: `docs/reports/workflow-automation/AUTO-009-completion-report.md`.

## AUTO-010 — Real Non-Interactive Provider Runtime

Status: Done

Registered and authorized by the Human Owner on 2026-07-31, in one written directive naming the
stage, its mission, its required architecture, its closed permission and sandbox policies, its
three-layer never-ask enforcement, its strictly prohibited behaviours, and its stop condition.
AUTO-010 had never been registered before, so this single entry records both its registration and
its authorization. It is the single `Current` task; the `Current` set was empty beforehand.

Scope: implement and validate the real non-interactive Provider Runtime for Claude Code and Codex —

    WorkflowService -> Provider Runtime -> Claude CLI / Codex CLI

The stage must prove that both installed provider CLIs run without an interactive terminal, receive
a complete prompt through stdin, never ask the user questions, execute under an explicit permission
or sandbox policy, return a structured machine-readable result, enforce timeouts and output limits,
isolate invocation artifacts, and return `BLOCKED` instead of waiting for clarification. The
existing AgentOS provider framework (`agentos_workflow/providers/`) is reused, never duplicated:
`WorkflowService` delegates through a narrow public Provider Runtime boundary and contains no
provider-specific CLI flag and no subprocess logic of its own.

Claude's permission mode is a strict enum limited to `plan`, `dontAsk`, and `acceptEdits`;
`bypassPermissions` is not permitted. Codex's sandbox mode is a strict enum limited to `read-only`
and `workspace-write`; `danger-full-access` is not permitted. Never-ask enforcement is implemented
and tested at all three layers — prompt contract, mechanical non-interactivity (no TTY, one prompt
on stdin, stdin closed, non-interactive flags, termination on timeout), and a structured terminal
result (`COMPLETED`, `COMPLETED_WITH_ASSUMPTIONS`, `BLOCKED`, `FAILED`).

Explicitly out of scope and prohibited in this stage: Preparation/Reviewer/Implementer Mode;
workflow authorization, approval, or approval timeouts; Telegram; daemon; task scheduling; workflow
start, resume, or cancel; Codex direct correction workflow; Claude-Codex orchestration; Git commit,
push, PR creation, CI polling, merge, or branch cleanup; Python governance closeout; shell-script
retirement; the AUTO-011 unified agent result; the AUTO-012 approval policy; and any successor
stage. No workflow state-machine change is expected or permitted absent a proven blocker, and
existing `workflowctl auto status|list|audit|report` behaviour and output are unchanged. Newly
discovered defects that do not block AUTO-010 are recorded, classified, and deferred in the
completion report.

Contract: `docs/workflow-automation/stage-prompts/AUTO-010.md`.
Report: `docs/reports/workflow-automation/AUTO-010-completion-report.md`.

**Implemented, validated, approved, and closed `Current -> Done` on 2026-07-31.** The engine can
now really run Claude Code and Codex non-interactively, and that claim rests on live acceptance
tests against the installed CLIs rather than on mocks. `WorkflowService.invoke_provider` delegates
to `ProviderRuntime.invoke` (`agentos_workflow/providers/runtime.py`), which selects a provider
through the existing live registry and returns a typed `ProviderRunResult`; the service names no
CLI flag, imports no provider internals, and holds no lock or store, so a provider run still cannot
transition workflow state by itself.

All three never-ask layers are enforced and tested. The prompt contract states the four required
clauses verbatim and cannot be omitted, because the public request carries a `task` and no
`prompt`. Mechanical non-interactivity is proven against real child processes: no TTY on any
standard stream, no controlling terminal at all, its own process group, exactly one prompt on
stdin, and EOF thereafter. Every execution terminates in `COMPLETED`,
`COMPLETED_WITH_ASSUMPTIONS`, `BLOCKED`, or `FAILED`, with `BLOCKED` requiring concrete blockers,
`COMPLETED_WITH_ASSUMPTIONS` requiring recorded assumptions, and a report omitting `status`
rejected rather than inferred.

Permission and sandbox policy is closed by construction: Claude is limited to `plan`/`dontAsk`/
`acceptEdits` and Codex to `read-only`/`workspace-write`, both defaulting to the least capable
value. `bypassPermissions` and `danger-full-access` are absent from the enums that configuration
is typed to, so no configuration, request, or call site can express either. Account selection uses
the real `claude`/`codex` binaries plus the allowlisted `CLAUDE_CONFIG_DIR`/`CODEX_HOME`; shell
aliases are structurally unusable under `shell=False` and fixed argv.

Three blockers were found and fixed inside the shared provider process runner, each minimal:
`subprocess.run`'s timeout killed only the direct child and left the parent's controlling terminal
attached (now `Popen(start_new_session=True)` with SIGTERM-then-SIGKILL of the whole process
group); output ceilings were unenforced during capture and stderr had none (now bounded streaming
readers that reclaim the group on breach); and AUTO-004's Codex parser took the last JSON object on
stdout, which is always a `turn.*` envelope and never the report, so it could never have worked
against the real CLI (now the `--output-last-message` answer file, with a narrow JSONL fallback
pinned to verbatim captured output).

Evidence: 3,241 tests pass (3,151 + 90 new, none skipped, none xfail) plus 25 live acceptance tests
against the real CLIs with **zero skips** — Claude 9, Codex 9, suite guards 7. `mypy --strict`
clean over 120 source files; `ruff`, `black`, and pre-commit clean; the wheel carries every new
module and all import from outside the repository root; nine existing `workflowctl` invocations are
byte-identical to the `5d1b6be` baseline. Four non-blocking defects (D-3 through D-6) remain
deferred and none was fixed; D-1 was withdrawn as misdiagnosed, and D-2 and D-7 were resolved. No
workflow state-machine change was needed. AUTO-011 and every later roadmap phase remain untouched
and unauthorized. Report: `docs/reports/workflow-automation/AUTO-010-completion-report.md`.

## AUTO-011 — Unified Provider and Agent Result Contract

Status: Done

Registered and authorized by the Human Owner on 2026-08-01, in one written directive naming the
stage, its mission, its required architecture, its canonical field set, its status contract and
invariants, its authority rule, its compatibility constraints, its strictly prohibited behaviours,
and its stop condition. AUTO-011 had never been registered before, so this single entry records
both its registration and its authorization. It is the single `Current` task; the `Current` set was
empty beforehand.

Scope: create one canonical typed result contract for provider and agent execution —

    WorkflowService -> Provider Runtime -> Canonical AgentRunResult

The stage introduces `AgentRunResult` as the canonical result contract for future Claude execution,
Codex execution, internal agents, and the Preparation/Reviewer/Implementer Modes, without
implementing any of them. It standardizes execution results only: no workflow mode and no workflow
lifecycle. The canonical result represents `workflow_id`, `mode`, `agent`, `provider`, `status`,
`summary`, `assumptions`, `blocking_issues`, `changed_files`, `artifacts`, `tests_run`,
`started_at`, `completed_at`, `duration`, `exit_code`, `failure`, `final_verdict`, and
`recommended_next_state`, reusing existing repository models — `ProviderRunStatus`,
`ProviderVerdict`, `ProviderFailure`, `ProviderKind` — rather than declaring duplicates.

Exactly four terminal statuses are supported (`COMPLETED`, `COMPLETED_WITH_ASSUMPTIONS`, `BLOCKED`,
`FAILED`), with `COMPLETED_WITH_ASSUMPTIONS` requiring at least one assumption, `BLOCKED` requiring
at least one concrete blocking issue, `FAILED` requiring a typed failure, `COMPLETED` carrying no
contradictory blocking or failure data, and unknown statuses rejected. `recommended_next_state` is
advisory only and must never mutate workflow state, authorize a transition, bypass the
Orchestrator, or substitute for deterministic validation.

AUTO-010's Provider Runtime must continue to work unchanged; adapters are introduced instead of
breaking existing interfaces. The provider process runner is not rewritten, and provider argv,
permission modes, sandbox modes, environment allowlists, timeout behaviour, output limits,
process-group cleanup, session layout, and the live CLI tests are all unaltered. No legacy result
model is deleted, and legacy `AgentReport` under `src/ai_workflow_engine` remains unchanged.

Explicitly out of scope and prohibited in this stage: Preparation/Reviewer/Implementer Mode;
workflow authorization, approval, or approval timeouts; task scheduling; workflow start, resume, or
cancellation; Claude-Codex coordination; Codex direct correction; Git commit or push automation; PR
creation; CI polling; merge; branch cleanup; Python governance closeout; daemon; Telegram; and
AUTO-012 or any successor behaviour. No workflow state-machine change is permitted, Git/GitHub
skill registration is untouched, shell scripts are neither retired nor modified, and existing
`workflowctl auto status|list|audit|report` behaviour and output are unchanged. Newly discovered
defects that do not block AUTO-011 are recorded, classified, and deferred in the completion report.

Contract: `docs/workflow-automation/stage-prompts/AUTO-011.md`.
Report: `docs/reports/workflow-automation/AUTO-011-completion-report.md`.

**Implemented, validated, approved, and closed `Current -> Done` on 2026-08-01** after a
Human-Owner-required fourteen-point scope, contract, and compatibility verification that passed in
full. `agentos_workflow/results.py` delivers the canonical `AgentRunResult`, reached from AUTO-010's
`ProviderRunResult` through `agent_run_result_from_provider_run`, so the Provider Runtime is
unchanged and compatibility is preserved by projection rather than by interface change. All
eighteen required canonical fields are present, plus `session_id` as the invocation's trace
identity. Status and verdict remain deliberately distinct — AUTO-010's deferred D-3 is narrowed,
not collapsed, because a `COMPLETED` run reporting `fail` is a QA provider finding real defects.
`recommended_next_state` is advisory only: no module outside the contract reads it, proven by scan
rather than by assertion.

3,352 tests pass (3,241 + 111 focused); 25 live CLI acceptance tests pass with zero skips;
`mypy --strict` clean over 121 source files; `ruff`, `black`, and pre-commit clean. No production
file outside the new module was modified — every provider, orchestrator, agent, skill, config, CLI,
`src/`, `scripts/`, and packaging path is byte-identical to `fd0b34f`, and six `workflowctl`
invocations match a clean baseline worktree exactly. No blocker was fixed because none existed.
Three non-blocking defects were recorded, classified, and deferred (D-8, D-9, D-10), none
implemented and no GOV stage created; AUTO-010's D-3 through D-6 and AUTO-009's D1-D6 remain
deferred and untouched. AUTO-012 and every later roadmap phase remain untouched and unauthorized.
Report: `docs/reports/workflow-automation/AUTO-011-completion-report.md`.

## AUTO-012 — Configurable Approval Policy, Persistence, and Invalidation

Status: Done

Registered and authorized by the Human Owner on 2026-08-01, in one written directive naming the
stage, its mission, its required architecture, its policy and record contracts, its timeout
semantics, its checksum-binding and invalidation rules, its persistence requirements, its
boundaries, its strictly prohibited behaviours, and its stop condition. AUTO-012 had never been
registered before, so this single entry records both its registration and its authorization. It is
the single `Current` task; the `Current` set was empty beforehand.

Scope: implement a configurable, durable approval subsystem for future workflow gates —

    WorkflowService -> ApprovalService -> policy resolution, request persistence, manual
    decisions, timeout decisions, checksum binding, invalidation

The stage delivers a strict typed approval policy (`required`, `timeout_seconds`, `timeout_action`,
`channels`, `approvers`, `escalate_to`) resolved across built-in defaults, project configuration,
per-gate configuration, and per-run override, then frozen into an immutable snapshot that later
configuration changes cannot retroactively alter. Timeout actions are `AUTO_APPROVE`, `PAUSE`,
`FAIL`, `CANCEL`, and `ESCALATE`; channels are `CLI` and `TELEGRAM`, with Telegram a policy value
only and no transport or networking implemented. `AUTO_APPROVE` requires explicit opt-in at the
specific gate or per-run override and is refused when inherited from a broad default.

Deadlines are absolute, timezone-aware UTC instants persisted to disk and evaluated lazily: no
`sleep`, no in-memory timer, no background thread, no process-local scheduler state, so a deadline
survives process and machine restart. The daemon is not implemented. Every approval binds four
checksums — repository state, diff, canonical AUTO-011 agent result, and deterministic gate result
— which are recomputed immediately before consumption; any difference invalidates the approval,
blocks the action, and records which checksum changed, with no silent recreation and no
auto-approval of an invalidated request. Persistence is `approvals.jsonl` through the existing
`StateStore` discipline: append-only, fsync'd, duplicate-key rejecting, monotonically ordered,
symlink refusing, per-workflow confined, restart-safe on replay, with no historical record ever
rewritten.

The governance prerequisite is recorded separately: `HUMAN_AUTHORIZATION_MODEL.md` moves to v2.0
with a new §5a recording the Human Owner's explicit decision that future workflow modes may use
configurable approval gates governed by `ApprovalService`. That decision authorizes the subsystem
only — never a specific Preparation, Reviewer, or Implementer workflow, never a gate placement, and
never AUTO-013.

Explicitly out of scope and prohibited in this stage: Preparation/Reviewer/Implementer Mode; Claude
or Codex execution changes; provider-runtime changes; canonical result changes; Codex direct
correction; task scheduling; workflow orchestration; Git commit or push automation; PR creation; CI
polling; merge; branch deletion; governance closeout automation; daemon; Telegram bot;
shell-script retirement; and AUTO-013 or any successor behaviour. Git/GitHub skill registration is
untouched, existing `workflowctl auto status|list|audit|report` behaviour and output are unchanged,
and no deferred finding is fixed unless it directly blocks AUTO-012. Newly discovered defects that
do not block AUTO-012 are recorded, classified, and deferred in the completion report.

Contract: `docs/workflow-automation/stage-prompts/AUTO-012.md`.
Report: `docs/reports/workflow-automation/AUTO-012-completion-report.md`.

**Implemented, validated, approved, and closed `Current -> Done` on 2026-08-01.**
`agentos_workflow/approvals.py` delivers the reusable `ApprovalService` subsystem: a strict typed
policy resolved across built-in, project, gate, and run layers into an immutable snapshot; an
append-only per-workflow `approvals.jsonl` written through the existing `StateStore` discipline,
with the current request derived by replay so no decision is ever overwritten; absolute
timezone-aware UTC deadlines evaluated lazily with no thread, timer, sleep, or scheduler anywhere,
proven to survive a restart; all five timeout actions, with `PAUSE` resumable and escalation bounded
by a no-loop fallback and at most one extension; and four-checksum binding recomputed immediately
before consumption, so any change invalidates the approval, records which checksum changed, and
blocks reuse. `AUTO_APPROVE` is refused when inherited from a broad default and accepted only from
the specific gate or a per-run override. Telegram is a policy value only — no transport, bot,
handler, or network call exists.

The governance prerequisite was met before implementation, as its own act:
`HUMAN_AUTHORIZATION_MODEL.md` moves to v2.0 with a new §5a recording the Human Owner's decision
that future workflow modes may use configurable approval gates governed by `ApprovalService` —
authorizing the subsystem only, never a mode, never a gate placement, never a successor stage.

**No workflow mode, lifecycle, or state was implemented.** `WorkflowState` remains 19 members with
37 transition edges, and `orchestrator/engine.py` is byte-identical. Both modified production files
are purely additive (146 insertions, 0 deletions); every provider, agent, skill, config, CLI,
`results.py`, `src/`, `scripts/`, live-test, and packaging path is byte-identical to `e2b069c`, and
six `workflowctl` invocations match a clean baseline worktree exactly.

3,469 tests pass (3,352 + 117 focused); 25 live CLI acceptance tests pass with zero skips;
`mypy --strict` clean over 122 source files; `ruff`, `black`, and pre-commit clean. No blocker was
fixed because none existed. Three non-blocking defects were recorded, classified, and deferred
(D-11, D-12, D-13), none implemented and no GOV stage created; AUTO-011's D-8 through D-10,
AUTO-010's D-3 through D-6, and AUTO-009's D1-D6 remain deferred and untouched. AUTO-013 and every
later roadmap phase remain untouched and unauthorized.
Report: `docs/reports/workflow-automation/AUTO-012-completion-report.md`.

## GOV-4 — Isolate Claude live-test configuration per attempt and add bounded test-only format retries

Status: Done

**Registered and authorized by the Human Owner in one act on 2026-08-02**, as an ordinary
(non-AUTO/GOV-AUTO-family) engine task record, following the same lightweight pattern GOV-2 and
GOV-3 established rather than a new AUTO or GOV-AUTO stage. This is a pre-AUTO-013
baseline-verification correction to the `agentos_workflow` live acceptance test harness
(`agentos_workflow/tests/live/test_live_providers.py` and its mocked companion
`agentos_workflow/tests/test_provider_runtime.py`), discovered while verifying the AUTO-013
baseline required by `docs/workflow-automation/stage-prompts/AUTO-013.md`.

Two distinct, independently reproduced defects motivate it: (1) the live suite forwarded the
configured Claude account's real, long-lived `CLAUDE_CONFIG_DIR` to every invocation for an entire
session, letting Claude Code's own client-side continuity state (`.claude.json`, `projects/`,
`plans/`, session history) accumulate across tests and across separate suite runs — reproduced
causing a real contract-violating failure, the model treating an injected plan-mode system
reminder as a genuine ongoing session and refusing the auto-mode JSON-only contract; and (2),
independent of (1), real Claude's compliance with that same strict bare-JSON contract is not
deterministic on a single attempt — observed as a short prose sentence plus a fenced JSON block,
under both `plan` and `acceptEdits` permission modes, on fresh ephemeral directories with no other
symptom.

Scope: test-only. No production code (`agentos_workflow/providers/`, `agentos_workflow/agents/`,
`agentos_workflow/orchestrator/`, `agentos_workflow/config/`, `results.py`, `service.py`, or any
other production path) is touched. No parser change, no permission-mode change, no provider argv
change, no new workflow state, no `workflowctl` change. AUTO-013 is not registered, authorized,
branched, or implemented by this task, and this task authorizes no successor.

Explicitly out of scope and prohibited: any GOV-AUTO or AUTO stage for this defect; any change to
`ProviderRuntime`, `unfenced`, `strict_json_loads`, or report classification; weakening the strict
JSON contract; treating model non-compliance as accepted nondeterminism; any Codex-side retry
policy absent concrete Codex evidence of the same failure mode; fixing any unrelated deferred
finding.

Contract: none — an ordinary engine task record, per the GOV-2/GOV-3 precedent.

**Implemented, validated, and closed `Current -> Done` on 2026-08-02.**
`_stage_ephemeral_claude_config_dir` makes the configured Claude account directory a read-only
authentication template: every invocation gets a fresh directory under its own `tmp_path`
containing only `.credentials.json` (confirmed sufficient by direct probe), never the template
itself. `run_live_claude_with_bounded_format_repair` retries only `FAILED`/`MALFORMED_OUTPUT` up
to 3 attempts, each with its own fresh ephemeral config, session, and disposable repository
directory, stopping immediately at the first non-format-failure result; every other failure kind
is accepted unchanged on attempt one. A new deterministic mocked test
(`test_prose_before_a_fenced_report_is_rejected_not_normalized`) pins single-attempt rejection of
the exact observed failure shape, unweakened.

Two full `pytest -q -m live_cli -rs` runs after both fixes: 32 passed, 0 failed, 0 skipped each
(32, not 25, because this task also added 7 structural guard tests proving the isolation
mechanism). The authentication template's file count, SHA-256, and mtime were identical before
and after every live run; the interactive `.claude-A` directory showed zero diffs under
`plans/`/`projects/`. 3,470 tests pass (3,469 + 1); `mypy` clean over 122 source files (test
directories excluded from that count, matching every prior stage's baseline); `ruff`/`black`/
pre-commit clean; `workflowctl verify` full PASS. Changed files: exactly
`agentos_workflow/tests/live/test_live_providers.py` and
`agentos_workflow/tests/test_provider_runtime.py` — no production code. This closure authorizes
no successor: AUTO-013 and every later roadmap phase remain unauthorized.
Report: `docs/reports/GOV-4-completion-report.md`.

## AUTO-013 — Foreground Implementer Mode (AUTHORIZED → PR_OPEN)

Status: Done

Registered and authorized by the Human Owner in one written directive naming the stage, its
mission, its final approved runtime flow, its required implementation surface
(`ImplementerModeDriver`, `ImplementationTask`, the `WorkflowService` implementation entry point,
guarded QA configuration, Claude/AgentRunResult/deterministic-validation/bounded-repair/
`ApprovalService`/commit/push/PR-creation integration, resume support for every AUTO-013 state),
its guarded `independent_qa_required` policy (default `true`; `false` reachable only through the
same explicit gate/run opt-in discipline AUTO-012 established for `AUTO_APPROVE`, never
fabricating `qa_passed = true`), its security preservation requirements (no `shell=True`, fixed
argv, provider isolation, approval integrity, checksum validation, scope/forbidden-path
validation, secret detection), its newly discovered defect policy, and its stop condition
(implementation and validation only — no commit, no push, no PR, no merge, no AUTO-014, no
AUTO-015). AUTO-013 had never been registered before, so this single entry records both its
registration and its authorization.

Preconditions verified before implementation began: predecessor AUTO-012 `COMPLETE`, merged, and
published; AUTO-001 through AUTO-012 and GOV-4 all `COMPLETE`/`Done`; no other `Current` task
anywhere in the queue; registry and task-queue agreement; clean, synchronized `main` ==
`origin/main` at `985405369b8229fc48ba2b70fc03a8c47ff13879`; `workflowctl verify --config
self-governance.yaml` full PASS; `pytest -q` at 3,470 passed / 0 skipped and `pytest -q -m
live_cli -rs` at 32 passed / 0 skipped; no blocking OD-#. Branch
`feature/auto-013-implementer-to-pr` created from that clean, synchronized `main`.

`agentos_workflow/implementer.py` delivers `ImplementerModeDriver` and `ImplementationTask`,
composing the already-delivered `WorkflowSession` (state/lock/durable attempt bookkeeping),
`WorkflowService` (`invoke_provider` and the five approval operations — the "`WorkflowService`
implementation entry point" this stage's directive named, deliberately without adding a sixth
workflow verb to that class, since its own docstring and `test_service.py`'s
`APPROVED_OPERATIONS`/`FORBIDDEN_OPERATIONS` pins explicitly forbid one), `agents.
run_deterministic_validation` (unmodified), and the existing Git/GitHub/reporting Skills, to drive
one workflow from `AUTHORIZED` to `PR_OPEN`. One deliberately additive Skill was added outside this
module, `skills.repository.checkout_stage_branch` — no prior Skill checked out a non-baseline,
already-created branch. `WorkflowState`'s 19 members and 37 edges, `ProviderRuntime`, both CLI
providers, `ProviderResult`, `AgentRunResult`, and `ApprovalService` are all reused exactly as
AUTO-002/010/011/012 left them, unmodified.

Contract: `docs/workflow-automation/stage-prompts/AUTO-013.md`.
Report: `docs/reports/workflow-automation/AUTO-013-completion-report.md`.

**Implemented, validated, approved, and closed `Current -> Done` on 2026-08-02**, after an
eighteen-point final scope and integrity verification the Human Owner required before any commit.
Two corrections were made during that verification, neither weakening any existing gate, invariant,
or transition table: the `ApprovalService` gate was relocated from `QA_RUNNING` to
`READY_TO_COMMIT` (matching that state's own standing `WORKFLOW_STATES.md` §2 definition more
precisely — a rejected/changes-requested decision there fails the workflow directly, since no
`READY_TO_COMMIT → REPAIRING` edge exists and none was added); and `MACHINE_GATES.md` was amended
(1.3 → 1.4, new §4a) to record the Human Owner's explicit authorization of the guarded
`independent_qa_required=false` exception to its previously-unconditional "QA is never skipped"
clause — the same treatment `HUMAN_AUTHORIZATION_MODEL.md` v2.0 §5a gave AUTO-012's approval-gate
authorization. See the completion report for the full evidence table (3,484 tests passing — 3,470
+ 14 new — 0 skipped; `pytest -q -m live_cli -rs` at 32 passed / 0 skipped, after one transient,
investigated, and cleared Claude usage-limit flake unrelated to this stage's code; `mypy --strict`
clean over 123 source files; `ruff`/`black`/pre-commit clean; wheel packaging and out-of-tree
imports both verified). Three new non-blocking defects (D-14, D-15, D-16) recorded and deferred,
none implemented, no GOV stage created. **Publication was subsequently completed via PR #14**
(`feature/auto-013-implementer-to-pr` merged into `main`, merge commit `4659335`) — no governance
entry recorded that merge at the time; AUTO-014's registration below notes the gap as a deferred
documentation finding rather than rewriting this closed entry. This entry authorizes no successor:
AUTO-014, AUTO-015, and every later roadmap phase remain unauthorized, and
merge/CI-wait/branch-cleanup/runtime-closeout behavior was not implemented by this stage.

## AUTO-014 — CI, Merge, Repository Finalization, and Runtime Closeout (PR_OPEN → DONE)

Status: Done

Registered and authorized by the Human Owner in one written directive naming the stage, its
mission, its approved runtime flow (`PR_OPEN → AUTO_MERGE_ENABLED → WAITING_FOR_CHECKS → MERGED →
CLOSING → DONE`), its required architecture (`WorkflowService` continuation operation ->
`MergeCloseoutModeDriver` -> `WorkflowSession.resume()` -> `MergeAgent`/Git-GitHub skills/
`CloseoutAgent`/`StateStore`), its explicit exclusions (no Claude implementation, no Codex
review/correction, no commit/push/PR creation, no Preparation/Reviewer Mode, no daemon, no
Telegram, no scheduler, no AUTO-015), its start-condition, PR-reconciliation, QA/merge-eligibility,
bounded-polling, merge-reconciliation, baseline-update, branch-retention, runtime-closeout,
resume, failure-model, CLI, and security-invariant requirements, its newly discovered defect
policy, and its stop condition. AUTO-014 had never been registered before, so this single entry
records both its registration and its authorization.

Preconditions verified before implementation began: predecessor AUTO-013 `COMPLETE`, merged, and
published (PR #14, merge commit `4659335`); AUTO-001 through AUTO-013 and GOV-4 all
`COMPLETE`/`Done`; no other `Current` task anywhere in the queue; registry and task-queue
agreement; clean, synchronized `main` == `origin/main` at
`465933551c28f65d38be6c0dceab95d95af8fa03`; `workflowctl verify --config self-governance.yaml`
full PASS; `pytest -q` at 3,484 passed / 0 skipped and `pytest -q -m live_cli -rs` at 32 passed /
0 skipped; no blocking OD-#. Branch `feature/auto-014-merge-closeout` created from that clean,
synchronized `main`.

Contract: `docs/workflow-automation/stage-prompts/AUTO-014.md`.
Report: `docs/reports/workflow-automation/AUTO-014-completion-report.md`.

AUTO-014 was implemented, fully validated, and approved for finalization on 2026-08-03 after the
corrected AUTO-013-created disposable acceptance run reached `DONE`. The completion report records
the accepted PR #2 lifecycle, repository ledger, validation evidence, and deferred findings.

## GOV-AUTO-08 — AUTO-015 Successor Scope and Contract Definition

Status: Done

Registered as the sole `Current` task by the Human Owner’s GOV-AUTO-08 directive on 2026-08-04,
after AUTO-014 was verified `COMPLETE`/`Done` and the Current set was empty. This is a
documentation-only governance task. Its predecessor is AUTO-014 `COMPLETE`; its purpose is to
compare successor capabilities and obtain an explicit Human Owner choice through
`docs/workflow-automation/successor-planning/AUTO-015-DECISION-TEMPLATE.md`.

The Human Owner selected **Automatic Next-Stage Computation and Prompt Generation** as the
proposed basis for AUTO-015, with proposed title **AUTO-015 — Deterministic Next-Stage Proposal
and Governed Prompt Generation**. The decision is capability selection only and is explicitly
**not authorized** for implementation.

GOV-AUTO-08 authorizes no AUTO-015 capability. It must not implement Preparation Mode, Reviewer
Mode, Codex Correction Mode, automatic next-stage computation, daemon/scheduler, Telegram or
another operator interface, multi-task orchestration, security hardening, provider expansion, or
any deferred-defect remediation. It must not modify production source, tests, scripts, providers,
workflow states, or runtime behavior. The registered working branch is
`governance/gov-auto-08-successor-scope`; no commit, push, PR, or merge is authorized.

The governance activity transitions `Planned → Current → Done` and is recorded as
`IN_PROGRESS → COMPLETE` in its continuity log. GOV-AUTO-08 is closed because the decision gate
was completed; AUTO-015 remains unregistered, unauthorized, and unimplemented. No AUTO-015
contract, stage row, branch, implementation, commit, push, PR, or merge was created or authorized.

Deliverables: `docs/workflow-automation/successor-planning/AUTO-015-CANDIDATES.md`,
`docs/workflow-automation/successor-planning/AUTO-015-DECISION-TEMPLATE.md`, and the GOV-AUTO-08
completion report.
