# Remaining Work

Mirror of `docs/TASK_QUEUE.md`'s not-yet-`Done` entries (`Current` and `Planned`). Statuses here
must agree with the task queue — `workflowctl check-task-state` fails otherwise.

The approved 1.0.0 roadmap (`docs/MASTER_ROADMAP.md`) is complete. DASH-001 and AUTO-001 were
previously closed to `Done`. AUTO-002 was accepted and closed to `Done` by the Human Owner on
2026-07-27. There is no `Current` task. Remaining work belongs to the DASH program
(DASH-002..010, all `Planned`), the rest of the AUTO program (AUTO-003..007, all `Planned`), and
the ordinary governance/tooling task GOV-2. Each requires its own fresh written authorization
before it may become `Current`; closing AUTO-002 authorizes none of them.

| Task | Title | Status |
|---|---|---|
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

Future hardening recorded at AUTO-002 closure—including infrastructure-retry accounting when a
future stage first introduces such operations, remote/GitHub reconciliation in the integration
stages, and any later portability work beyond the existing POSIX runtime boundary—is future
work, not an AUTO-002 blocker.
