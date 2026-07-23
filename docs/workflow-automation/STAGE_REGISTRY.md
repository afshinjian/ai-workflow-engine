# AgentOS Workflow Automation — Stage Registry

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Stage Registry |
| **Purpose** | Live status of AUTO-001..007, the stage-lifecycle state model (distinct from the runtime `WORKFLOW_STATES.md` machine the finished engine will use), master stage-control rules, and the append-only authorization log. A *view* of `docs/TASK_QUEUE.md`, never a competing workflow. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Documentation & Governance session · Human Owner (approval and stage authorization) |
| **Dependencies** | `README.md` §5; `MVP_SCOPE.md`; `TEST_STRATEGY.md` |
| **Related Documents** | `stage-prompts/README.md`, `docs/AGENT_PROTOCOL.md`, `self-governance.yaml`, `docs/TASK_QUEUE.md` |

## Table of Contents
1. Naming Note · 2. State Model · 3. Control Rules · 4. Registry · 5. Authorization Log ·
6. Decision References · 7. Open Questions · 8. Future Revisions

## 1. Naming Note

This is the **stage lifecycle** for developing the AUTO engine itself (AUTO-001..AUTO-007),
following exactly the state model this repository already established in
`docs/agentos-dashboard/STAGE_REGISTRY.md` for DASH. It is a different state machine from the
**runtime workflow states** (`WORKFLOW_STATES.md`) the finished engine will use to automate a
target repository's stage. Do not conflate `AUTHORIZED` here with `AUTHORIZED` in
`WORKFLOW_STATES.md` — see that document's §1.

## 2. State Model

Per-stage states: `NOT_STARTED → PROPOSED → AUTHORIZED → IN_PROGRESS → SELF_REVIEW → REVIEW →
APPROVAL → COMPLETE`, plus `BLOCKED` and `SUPERSEDED`. Mapping to the stage's task in
`docs/TASK_QUEUE.md` (three statuses): `AUTHORIZED`/`IN_PROGRESS`/`SELF_REVIEW`/`REVIEW`/
`APPROVAL` ≈ `Current`; `NOT_STARTED`/`PROPOSED` ≈ `Planned`; `COMPLETE` ≈ `Done`. At most one
AUTO task is `Current` at a time (`self-governance.yaml` `maximum_current_tasks: 1`), enforced
repository-wide, not just within the AUTO family (`docs/DECISION_LOG.md`, 2026-07-23 AUTO-001
entry).

## 3. Control Rules

1. **Authorization preconditions:** predecessor `COMPLETE`; registry and `docs/TASK_QUEUE.md`
   agree; no other AUTO stage active; no other `Current` task anywhere in the queue; clean
   tree; blocking OD-# resolved.
2. **Authorizer:** only the Human Owner.
3. **Required language:** a written record — "I authorize AUTO-0XX" (or an equivalent explicit
   directive) — captured in the stage's task record and §5 before work.
4. **Starting:** task `Planned → Current` (requires owner authorization per
   `self-governance.yaml` `require_designer_approval_for_promotion`); registry
   `AUTHORIZED → IN_PROGRESS`.
5. **Retry after failure:** stage stays `IN_PROGRESS`; fixes within scope only; all gates rerun.
6. **Review return:** `REVIEW → IN_PROGRESS`, findings preserved; each review round after the
   first uses a fresh reviewer with no memory of prior rounds.
7. **Approval return:** `APPROVAL → IN_PROGRESS`; findings recorded.
8. **Amending a completed stage:** never in place — corrective work is a new linked task.
9. **Superseding:** Human Owner directive + registry entry `SUPERSEDED` with successor
   reference; history append-only.
10. **Early-start prevention:** stage N+1 is never authorized until N is `COMPLETE` and fresh
    authorization is recorded.
11. **Documentation reconciliation:** a stage closes only after `docs/PROJECT_STATE.md`, the
    task queue and mirrors (`workflowctl check-task-state` green), this registry, and the stage
    report agree.
12. **Evidence before completion:** report complete per template; every acceptance criterion
    individually PASS.
13. **Closing:** commit and merge per rules 15-16; post-merge closeout updates mirrors; registry
    `COMPLETE`; task `Done`; then STOP.
14. **Branches:** one stage = one branch, created from current `main`.
15. **Merges:** one merge per stage into `main`, performed by the Human Owner; commit/push
    remain human-gated per `docs/AGENT_PROTOCOL.md`.
16. **Closeout:** task flips to `Done` only after post-merge consistency checks
    (`workflowctl verify --config self-governance.yaml`); no successor selected in the same
    session.

## 4. Registry

Report paths: `docs/reports/workflow-automation/AUTO-0XX-completion-report.md`.

| Stage | Title | Role | State | Branch | Prompt |
|---|---|---|---|---|---|
| AUTO-001 | Architecture and governance contracts | Documentation & Governance session | IN_PROGRESS | `governance/auto-001-workflow-automation-planning` | `stage-prompts/AUTO-001.md` |
| AUTO-002 | Orchestrator, state machine, locking, and persistence | Engine implementation session | NOT_STARTED | `feature/auto-002-orchestrator-state-machine` | `stage-prompts/AUTO-002.md` |
| AUTO-003 | Deterministic repository and validation skills | Engine implementation session | NOT_STARTED | `feature/auto-003-repository-validation-skills` | `stage-prompts/AUTO-003.md` |
| AUTO-004 | Claude Code CLI and Codex CLI providers | Engine implementation session | NOT_STARTED | `feature/auto-004-model-providers` | `stage-prompts/AUTO-004.md` |
| AUTO-005 | PMO, implementation, QA, Git, merge, and closeout agents | Engine implementation session | NOT_STARTED | `feature/auto-005-agents` | `stage-prompts/AUTO-005.md` |
| AUTO-006 | GitHub pull request, automatic squash merge, and closeout integration | Engine implementation session | NOT_STARTED | `feature/auto-006-pr-merge-closeout` | `stage-prompts/AUTO-006.md` |
| AUTO-007 | End-to-end dry run, recovery tests, and DASH integration | Engine implementation session (+ independent security review) | NOT_STARTED | `fix/auto-007-e2e-dry-run-recovery` | `stage-prompts/AUTO-007.md` |

## 5. Authorization Log (append-only)

| Date | Stage | Authorization record | Recorded by |
|---|---|---|---|
| 2026-07-23 | AUTO-001 | Human Owner: "I authorize AUTO-001." Preconditions verified: repository/branch/clean-tree confirmed; DASH-001 (prior `Current` task) closed out to `Done` first, per Human Owner directive, to satisfy the no-conflicting-task precondition (`docs/DECISION_LOG.md`, 2026-07-23 AUTO-001 entry). | Documentation & Governance session |

## 6. Decision References
DD-01 through DD-06.

## 7. Open Questions
OD-1 through OD-7 (`OPEN_QUESTIONS.md`); none block AUTO-001 closure. AUTO-002 authorization
requires AUTO-001 `COMPLETE` plus a fresh Human Owner record.

## 8. Future Revisions
Registry table and log grow append-only; control-rule changes are MAJOR.
