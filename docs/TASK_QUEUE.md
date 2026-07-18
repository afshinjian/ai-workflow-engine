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
