# Project State

Overall condition of `ai-workflow-engine`. This document is a governance mirror
(`governance.project_state` in `self-governance.yaml`) and a `governance.facts` source for the
`version` fact — it is cross-checked against `pyproject.toml` by `workflowctl check-governance`,
so keep the version line's wording exact if you edit it.

Current Version: 1.0.0

## Summary

`ai-workflow-engine` is a local orchestration foundation for governed AI-assisted software
development: deterministic read-only inspection, governed prompt generation, non-interactive
agent execution with independent claim verification and a persisted workflow state machine, and
approval-gated controlled commit and push. All four milestones are implemented. See
`docs/milestones.md` for the four-milestone roadmap, `docs/MASTER_ROADMAP.md` for the task-level
plan to 1.0, and `docs/architecture.md` for the pipeline shapes.

## Completed

- AUTO-001 (closed 2026-07-24): AgentOS Workflow Automation architecture and governance
  contracts — the complete documentation set under `docs/workflow-automation/`, merged into
  `main` via PR #3 (`191f600`). Formally flipped to `Done` per Human Owner review (see
  `docs/DECISION_LOG.md`, 2026-07-24 entry).
- DASH-001 (closed 2026-07-23): AgentOS Dashboard planning foundation and contracts — the
  complete documentation set under `docs/agentos-dashboard/`, merged into `main` via PR #1
  (`5f82996`). Formally flipped to `Done` as an AUTO-001 precondition (see
  `docs/DECISION_LOG.md`, 2026-07-23 AUTO-001 entry).
- Milestone 1 (v0.1.0, released 2026-07-16): deterministic read-only Git inspection, governance
  and task-state mirror checks, source-aware handover checksum verification, protected paths,
  structured CLI/JSON results.
- Milestone 2 (approved; committed locally 2026-07-17): governed prompt generation — deterministic,
  canonically-hashed rendering/validation/atomic storage for all seven workflow stages, plus the
  `workflowctl prompt <stage>` CLI surface. Passed three independent fresh implementation
  reviews; two real defects found and fixed along the way (see `docs/DECISION_LOG.md`).
- GOV-1 (closed 2026-07-17): the self-governance layer — this document and its siblings —
  validated end-to-end in `docs/VALIDATION_REPORT.md` and formally closed via task T-101.
- Milestone 3 (v0.2.0, 2026-07-18): non-interactive agent execution — a persisted, hash-chained
  workflow state machine (`workflowctl state`), the `agents` config section + strict report
  contract, a snapshot-sandbox runner with hard timeouts and isolation, and independent claim
  verification with tamper-evident run artifacts (`workflowctl agent run`). Each task (T-301..
  T-306) passed independent review; the normative plan is `docs/milestone-3-plan.md` and the
  demonstration is `docs/MILESTONE_3_VALIDATION.md`.
- Milestone 4 (released in v1.0.0, 2026-07-18): controlled commit and push — a separate typed
  writable-Git surface (`GitWriter`, read-only `GitClient` untouched), per-invocation human
  approval artifacts, and the `workflowctl commit` / `push` / `apply-patch` gates. Each task
  (T-401..T-404) passed independent review (the plan review took two rounds); normative plan
  `docs/milestone-4-plan.md`, demonstration `docs/MILESTONE_4_VALIDATION.md`. This completes all
  four milestones of `docs/milestones.md`.
- Version 1.0.0 (T-501, 2026-07-18): the approved roadmap is 100% complete. The `version`-fact
  regex was widened so `check-governance` extracts a `1.x` version; full summary in
  `docs/FINAL_COMPLETION_REPORT.md`.

## In progress

The entire approved 1.0.0 roadmap (`docs/MASTER_ROADMAP.md`) is complete, DASH-001 is closed,
and AUTO-001 is closed. The active task is AUTO-002 (orchestrator, state machine, locking, and
persistence), the second stage of the post-1.0 **AgentOS Workflow Automation program**,
authorized by the Human Owner on 2026-07-24 ("I authorize AUTO-002."). AUTO-002's registry state
is `BLOCKED` on a durable execution precondition, not on a fact tied to any particular branch
name. The settled procedure: this governance-recovery branch is reviewed, committed, pushed,
merged, and deleted through the ordinary recovery release process — it is never renamed into the
AUTO-002 implementation branch. After that merge and cleanup, an AUTO-002 execution session
begins from updated, clean `main` and creates or checks out the canonical branch
(`feature/auto-002-orchestrator-state-machine`, `docs/workflow-automation/STAGE_REGISTRY.md`
§4), which must independently satisfy the SSP's initial-start branch-binding and clean-tree
checks (`STAGE_REGISTRY.md` §3 rules 1/14/4) before the registry transitions
`AUTHORIZED → IN_PROGRESS`. Per rule 17, a failed execution precondition never invalidates a
recorded authorization (`HUMAN_AUTHORIZATION_MODEL.md` is not authority here — it governs only
the future runtime engine's authorization of workflows against *target* repositories, never this
repository's own AUTO-00x development stages, `STAGE_REGISTRY.md` §1); this is not a new
AUTO-002 authorization, and AUTO-002 implementation does not begin during governance recovery.
No AUTO-002 runtime implementation has started; the task remains `Current` (registry state
`BLOCKED`) until the canonical branch exists and passes its checks. The original branch-mismatch
discovery (2026-07-24, on this session's own working branch, not the canonical one) remains in
`docs/DECISION_LOG.md` as a historical record. Details: `docs/current_task.md`,
`docs/DECISION_LOG.md` (2026-07-24 entries).

## Planned

AUTO-003..AUTO-007 (`docs/TASK_QUEUE.md`; program plan `docs/workflow-automation/README.md`)
and Dashboard stages DASH-002..DASH-010 (program plan
`docs/agentos-dashboard/MASTER_PLAN.md`), each requiring its own fresh Human Owner
authorization; DASH-004 onward additionally gated on the OD-D9 dependency decision. Separately,
one ordinary (non-AUTO/DASH-family) governance/tooling task, **GOV-2** (`docs/TASK_QUEUE.md`):
extending `workflowctl check-governance` to machine-verify stage-registry/lifecycle consistency,
assessed but deliberately not implemented during the 2026-07-24 governance recovery (real
validator code needing its own authorization, out of scope for a documentation-only recovery
session) — requires its own fresh authorization like any other Planned task. Candidate future
engine work (explicitly out of the delivered 1.0.0 scope) remains listed in
`docs/FINAL_COMPLETION_REPORT.md` under "Future improvements".

## Blockers

**AUTO-002 is `BLOCKED`** (`docs/workflow-automation/STAGE_REGISTRY.md` §2/§4) on a durable
execution precondition — the sole current blocker: it stays `BLOCKED` until this governance
recovery is merged into `main`. The recovery release procedure is settled and durable, not a fact
about this specific branch's name: this session's own working branch is reviewed, committed,
pushed, merged, and deleted through the ordinary recovery release process — it is **not** renamed
into the AUTO-002 implementation branch. After that merge and cleanup, an AUTO-002 execution
session begins from updated, clean `main` and creates or checks out the canonical branch
(`feature/auto-002-orchestrator-state-machine`); that branch must pass its own execution-
precondition and branch-binding checks before the registry can transition to `IN_PROGRESS`. This
is not a new AUTO-002 authorization, and no AUTO-002 implementation begins during governance
recovery. This does not affect the Human Owner's "I authorize AUTO-002." authorization, which
stands (`STAGE_REGISTRY.md` §3 rule 17).

`main` and `origin/main` are identical (both at `191f600`, 0 ahead/0 behind) — DASH-001 (PR #1,
`5f82996`) and AUTO-001 (PR #3, `191f600`) have both been merged and pushed to `origin/main`.
The 1.0.0-release working tree (Stage 0's T-104 and all of Milestones 3 and 4) was folded into
that same history via those merges; no work is sitting uncommitted on `main` waiting for a
push decision. The only unpushed branch is the current session's own working branch,
`feature/auto-002-orchestrator-foundation`, which has no upstream configured
(`workflowctl check-git` reports `upstream_missing`) — expected for a local, not-yet-pushed
feature branch, and not itself a governance blocker. Committing and pushing any future work
still require explicit human approval per `docs/AGENT_PROTOCOL.md` — the gates Milestone 4
provides.
