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

Status: Current

Authorized by the Human Owner on 2026-07-27 as a governance and developer-experience task
(non-AUTO-family, so it carries no stage-registry entry). Adds a local Bash automation layer for
the repository's standard task cycle — `scripts/workflow-next.sh` (read-only preflight plus one
agent session), `scripts/prompts/implement-next-task.md` (the canonical implementation prompt),
`scripts/workflow-approve.sh` (the Human approval and single-commit gate), and
`docs/automation-workflow.md`. It automates the mechanical steps **without replacing the Human
Owner approval gate**: neither script pushes, merges, changes branches, alters upstream, or
touches stashes, and no commit occurs without two explicit `APPROVE` confirmations. No
dependencies were added. Implemented and validated 2026-07-27, pending Human Owner approval;
not committed.

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

Status: Planned

Requires its own fresh authorization. Contract:
`docs/workflow-automation/stage-prompts/AUTO-004.md`.

## AUTO-005 — PMO, implementation, QA, Git, merge, and closeout agents

Status: Planned

Requires its own fresh authorization. Contract:
`docs/workflow-automation/stage-prompts/AUTO-005.md`.

## AUTO-006 — GitHub pull request, automatic squash merge, and closeout integration

Status: Planned

Requires its own fresh authorization. Contract:
`docs/workflow-automation/stage-prompts/AUTO-006.md`.

## AUTO-007 — End-to-end dry run, recovery tests, and DASH integration

Status: Planned

Requires its own fresh authorization. Contract:
`docs/workflow-automation/stage-prompts/AUTO-007.md`.

## GOV-2 — Extend `check-governance` to validate stage-registry/lifecycle consistency

Status: Planned

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

## DASH-002 — Repository adapter and read-only snapshot

Status: Planned

Root-confined read-only file adapter, fixed-argv Git read adapter, snapshot builder with
staleness fingerprint. Contract: `docs/agentos-dashboard/stage-prompts/DASH-002.md`.

## DASH-003 — Governance and Markdown parsing

Status: Planned

Tolerant parsers for the governance mirrors, decision log, orchestration implementation state,
and handover manifest; consistency engine v1. Contract:
`docs/agentos-dashboard/stage-prompts/DASH-003.md`.

## DASH-004 — Local backend and dashboard shell

Status: Planned

Loopback-only web shell with security baseline and Overview page. Blocked on OD-D9 (serving
stack dependency decision, `docs/agentos-dashboard/OPEN_QUESTIONS.md`). Contract:
`docs/agentos-dashboard/stage-prompts/DASH-004.md`.

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
