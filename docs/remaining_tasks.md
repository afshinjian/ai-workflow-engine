# Remaining Work

Mirror of `docs/TASK_QUEUE.md`'s not-yet-`Done` entries (`Current` and `Planned`). Statuses here
must agree with the task queue — `workflowctl check-task-state` fails otherwise.

The approved 1.0.0 roadmap (`docs/MASTER_ROADMAP.md`) is complete. DASH-001 (post-1.0
**AgentOS Dashboard program**, entry point: `docs/agentos-dashboard/MASTER_PLAN.md`) closed out
to `Done` on 2026-07-23 as an AUTO-001 precondition. AUTO-001 (post-1.0 **AgentOS Workflow
Automation program**, entry point: `docs/workflow-automation/README.md`) closed out to `Done` on
2026-07-24, merged into `main` via PR #3 (`191f600`). AUTO-002 is `Current`, authorized
2026-07-24, but registry state `BLOCKED` (`docs/workflow-automation/STAGE_REGISTRY.md` §2) on a
durable execution precondition — AUTO-002 stays `BLOCKED` until this governance recovery is
reviewed, committed, pushed, merged, and deleted through the ordinary recovery release process
(this session's branch is never renamed into the AUTO-002 branch), after which an AUTO-002
session begins from clean `main` and creates or checks out the canonical branch — not on any
fact tied to a specific branch's name; the authorization itself stands (`STAGE_REGISTRY.md` §3
rule 17). This is not a new AUTO-002 authorization, and implementation does not begin during
governance recovery. See `docs/current_task.md` and `docs/DECISION_LOG.md` (2026-07-24 entries).
Remaining work belongs to the DASH program (DASH-002..010, still `Planned`), the rest of the AUTO
program (AUTO-003..007, still `Planned`), and one ordinary (non-AUTO/DASH-family) engine task,
GOV-2, assessed but not implemented during the 2026-07-24 governance recovery (see
`docs/TASK_QUEUE.md` for the full scope note). Each stage below requires its own fresh written
authorization before it may become `Current`.

| Task | Title | Status |
|---|---|---|
| AUTO-002 | Orchestrator, state machine, locking, and persistence | Current |
| AUTO-003 | Deterministic repository and validation skills | Planned |
| GOV-2 | Extend `check-governance` to validate stage-registry/lifecycle consistency | Planned |
| AUTO-004 | Claude Code CLI and Codex CLI providers | Planned |
| AUTO-005 | PMO, implementation, QA, Git, merge, and closeout agents | Planned |
| AUTO-006 | GitHub pull request, automatic squash merge, and closeout integration | Planned |
| AUTO-007 | End-to-end dry run, recovery tests, and DASH integration | Planned |
| DASH-002 | Repository adapter and read-only snapshot | Planned |
| DASH-003 | Governance and Markdown parsing | Planned |
| DASH-004 | Local backend and dashboard shell (blocked on OD-D9) | Planned |
| DASH-005 | Workflow board and task detail | Planned |
| DASH-006 | Git, upstream, handover, and consistency views | Planned |
| DASH-007 | Stage registry and prompt generation | Planned |
| DASH-008 | Run records, evidence, and audit timeline | Planned |
| DASH-009 | Security hardening and failure handling | Planned |
| DASH-010 | Integration testing, documentation, and release readiness | Planned |

Outside the task-tracked scope, the pending human decision recorded since 1.0.0 still stands: a
commit/push decision on completed work requires explicit human approval per
`docs/AGENT_PROTOCOL.md`.
