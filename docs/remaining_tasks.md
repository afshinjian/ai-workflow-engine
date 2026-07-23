# Remaining Work

Mirror of `docs/TASK_QUEUE.md`'s not-yet-`Done` entries (`Current` and `Planned`). Statuses here
must agree with the task queue — `workflowctl check-task-state` fails otherwise.

The approved 1.0.0 roadmap (`docs/MASTER_ROADMAP.md`) is complete. Remaining work belongs to
the post-1.0 **AgentOS Dashboard program** (entry point:
`docs/agentos-dashboard/MASTER_PLAN.md`), authorized by the Human Owner on 2026-07-23. Each
stage below requires its own fresh written authorization before it may become `Current`.

| Task | Title | Status |
|---|---|---|
| DASH-001 | Dashboard planning foundation and contracts | Current |
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
