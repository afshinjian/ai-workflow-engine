# AgentOS Dashboard — Stage Registry

| Field | Value |
|---|---|
| **Title** | AgentOS Dashboard — Stage Registry |
| **Purpose** | Live status of DASH-001..010, stage-state model, master stage-control rules, and the append-only authorization log. A *view* of the `docs/TASK_QUEUE.md` lifecycle, never a competing workflow. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Documentation & Governance session · Human Owner (approval and stage authorization) |
| **Dependencies** | `MASTER_PLAN.md` §4; `MVP_SCOPE.md`; `TEST_STRATEGY.md` |
| **Related Documents** | `stage-prompts/README.md`, `docs/AGENT_PROTOCOL.md`, `self-governance.yaml` |

## Table of Contents
1. State Model · 2. Control Rules · 3. Registry · 4. Authorization Log ·
5. Stage→Requirement Map · 6. Decision References · 7. Open Questions · 8. Future Revisions

## 1. State Model

Per-stage states: `NOT_STARTED → PROPOSED → AUTHORIZED → IN_PROGRESS → SELF_REVIEW → REVIEW →
APPROVAL → COMPLETE`, plus `BLOCKED` and `SUPERSEDED`. Mapping to the stage's task in
`docs/TASK_QUEUE.md` (which knows exactly three statuses): `AUTHORIZED`/`IN_PROGRESS`/
`SELF_REVIEW`/`REVIEW`/`APPROVAL` ≈ `Current`; `NOT_STARTED`/`PROPOSED` ≈ `Planned`;
`COMPLETE` ≈ `Done`. A stage's registry state can never be more advanced than its task's status
in `docs/TASK_QUEUE.md`, and at most one DASH task is `Current` at a time
(`self-governance.yaml` `maximum_current_tasks: 1`).

## 2. Control Rules

1. **Authorization preconditions:** predecessor `COMPLETE`; registry and `docs/TASK_QUEUE.md`
   agree; no other DASH stage active; no other `Current` task in the queue; clean tree;
   blocking OD-D# resolved.
2. **Authorizer:** only the Human Owner.
3. **Required language:** a written record — "I authorize DASH-0XX" (or an equivalent explicit
   directive) — captured in the stage's task record and §4 before work.
4. **Starting:** the assigned agent verifies the SSP preamble; task `Planned → Current`
   (promotion requires the owner authorization per `self-governance.yaml`
   `require_designer_approval_for_promotion`); registry `AUTHORIZED → IN_PROGRESS`.
5. **Retry after failure:** stage stays `IN_PROGRESS`; fixes within scope only; all gates rerun;
   failed results preserved in the report.
6. **Review return:** `REVIEW → IN_PROGRESS` with findings preserved; every review round after
   the first uses a fresh reviewer with no memory of prior rounds (`docs/AGENT_PROTOCOL.md`);
   repeat review reruns all contract gates.
7. **Approval return:** `APPROVAL → IN_PROGRESS`; findings recorded; approval names the exact
   diff/commit.
8. **Amending a completed stage:** never in place — corrective work is a new linked task.
9. **Superseding:** Human Owner directive + registry entry `SUPERSEDED` with successor
   reference; history append-only.
10. **Early-start prevention:** the prompt generator refuses stage N+1 until N is `COMPLETE`
    **and** fresh authorization is recorded; the SSP orders the agent to stop; sole-active
    checks flag violations.
11. **Documentation reconciliation:** a stage closes only after `docs/PROJECT_STATE.md`, the
    task queue and its mirrors (`workflowctl check-task-state` green), this registry, and the
    stage report agree.
12. **Evidence before completion:** report complete per template; all validation results
    recorded; scope audit clean; every acceptance criterion individually PASS.
13. **Closing:** commit and merge per rules 15–16; post-merge closeout updates mirrors;
    registry `COMPLETE`; task `Done`; then STOP.
14. **Rollback:** revert the stage's exact commit(s); dashboard.db never blocks rollback.
15. **Branches:** one stage = one branch, named per the registry table, created from current
    `main` (the configured default branch), never from another stage branch.
16. **Merges:** one merge per stage into `main`, performed by the Human Owner. Commits and any
    push are human-gated per `docs/AGENT_PROTOCOL.md`; the approval-gated
    `workflowctl commit` / `push` gates may be used but a plain human-run Git command with
    explicit approval is equally valid.
17. **Closeout:** merge commit recorded in the task record; task flips to `Done` only after
    post-merge consistency checks (`workflowctl verify --config self-governance.yaml`); no
    successor selected in the same session.

## 3. Registry

Report paths: `docs/reports/agentos-dashboard/STAGE-XX-completion.md`.

| Stage | Title | Role | State | Branch | Prompt |
|---|---|---|---|---|---|
| DASH-001 | Planning foundation and dashboard contracts | Documentation & Governance session | IN_PROGRESS | `governance/dash-001-documentation` | `stage-prompts/DASH-001.md` |
| DASH-002 | Repository adapter and read-only snapshot | Dashboard implementation session | NOT_STARTED | `feature/dash-002-repo-adapter` | `stage-prompts/DASH-002.md` |
| DASH-003 | Governance and Markdown parsing | Dashboard implementation session | NOT_STARTED | `feature/dash-003-governance-parsing` | `stage-prompts/DASH-003.md` |
| DASH-004 | Local backend and dashboard shell | Dashboard implementation session | NOT_STARTED | `feature/dash-004-dashboard-shell` | `stage-prompts/DASH-004.md` |
| DASH-005 | Workflow board and task detail | Dashboard implementation session | NOT_STARTED | `feature/dash-005-board-task-detail` | `stage-prompts/DASH-005.md` |
| DASH-006 | Git, upstream, handover, consistency views | Dashboard implementation session | NOT_STARTED | `feature/dash-006-git-handover-views` | `stage-prompts/DASH-006.md` |
| DASH-007 | Stage registry and prompt generation | Dashboard implementation session | NOT_STARTED | `feature/dash-007-prompt-generation` | `stage-prompts/DASH-007.md` |
| DASH-008 | Run records, evidence, audit timeline | Dashboard implementation session | NOT_STARTED | `feature/dash-008-runs-evidence-audit` | `stage-prompts/DASH-008.md` |
| DASH-009 | Security hardening and failure handling | Dashboard implementation session (+ mandatory independent security review) | NOT_STARTED | `fix/dash-009-security-hardening` | `stage-prompts/DASH-009.md` |
| DASH-010 | Integration testing, documentation, release readiness | Dashboard implementation session | NOT_STARTED | `feature/dash-010-release-readiness` | `stage-prompts/DASH-010.md` |

## 4. Authorization Log (append-only)

| Date | Stage | Authorization record | Recorded by |
|---|---|---|---|
| 2026-07-23 | DASH-001 | Human Owner: "I authorize DASH-001." Original planning-session authorization. The resulting execution was mistakenly performed in a different repository and is void for `ai-workflow-engine`; superseded by the recovery record below. | Documentation & Governance session |
| 2026-07-23 | DASH-001 (recovery) | Human Owner: "I authorize recovery and correct execution of DASH-001 in the ai-workflow-engine repository." Preconditions verified (branch `governance/dash-001-documentation`; the copied documentation treated as candidate material only; commit/push/merge prohibited; DASH-002+ not authorized). | Documentation & Governance session |

## 5. Stage→Requirement Map

DASH-002 → adapters underpinning all DRs · DASH-003 → DR-120..122 foundations · DASH-004 →
DR-010..013, DR-123 (blocked on OD-D9) · DASH-005 → DR-020..033 · DASH-006 → DR-080..083,
DR-100..102, DR-120 · DASH-007 → DR-040..043 · DASH-008 → DR-050..071, DR-110..111 ·
DASH-009 → SC-01..36 verification · DASH-010 → MVP acceptance.

## 6. Decision References
DD-01, DD-02, DD-03.

## 7. Open Questions
OD-D1 is resolved (see `OPEN_QUESTIONS.md`); OD-D9 must be resolved before DASH-004
authorization; DASH-002 authorization requires DASH-001 `COMPLETE` plus a fresh Human Owner
record.

## 8. Future Revisions
Registry table and log grow append-only; control-rule changes are MAJOR.
