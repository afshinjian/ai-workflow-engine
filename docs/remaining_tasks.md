# Remaining Work

Mirror of `docs/TASK_QUEUE.md`'s not-yet-`Done` entries (`Current` and `Planned`). Statuses here
must agree with the task queue — `workflowctl check-task-state` fails otherwise.

The approved 1.0.0 roadmap (`docs/MASTER_ROADMAP.md`) is complete. DASH-001 (post-1.0
**AgentOS Dashboard program**, entry point: `docs/agentos-dashboard/MASTER_PLAN.md`) closed out
to `Done` on 2026-07-23 as an AUTO-001 precondition. Remaining work belongs to the DASH program
(DASH-002..010, still `Planned`) and the newly authorized post-1.0 **AgentOS Workflow
Automation program** (entry point: `docs/workflow-automation/README.md`), authorized by the
Human Owner on 2026-07-23. Each stage below requires its own fresh written authorization before
it may become `Current`.

| Task | Title | Status |
|---|---|---|
| AUTO-001 | Architecture and governance contracts | Current |
| AUTO-002 | Orchestrator, state machine, locking, and persistence | Planned |
| AUTO-003 | Deterministic repository and validation skills | Planned |
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
