# Remaining Work

Mirror of `docs/TASK_QUEUE.md`'s not-yet-`Done` entries (`Current` and `Planned`). Statuses here
must agree with the task queue — `workflowctl check-task-state` fails otherwise.

The approved 1.0.0 roadmap (`docs/MASTER_ROADMAP.md`) is complete. DASH-001 and AUTO-001 were
previously closed to `Done`. AUTO-002 was accepted and closed to `Done` by the Human Owner on
2026-07-27, then published and merged into `main` (PR #5, merge commit `87a5062`) under a separate
Human Owner authorization the same day. AUTO-003 was implemented, approved, committed locally as
`908be94`, and closed to `Done` on 2026-07-27. GOV-AUTO-01 was closed to `Done` on 2026-07-28 —
implemented, validated, approved, committed as `a302c95`, and merged into `main` via `a3b5b0a`.
**AUTO-004 was closed to `Done` on 2026-07-28** — implemented, validated, approved, committed as
`84616d5`, and published to `main` under the same Human Owner decision. **AUTO-005 was closed to
`Done` on 2026-07-28** — implemented, validated, approved, committed as `430cbb4`, and published
to `main` under the same decision. **GOV-AUTO-02 was closed to `Done` on 2026-07-28** —
implemented, validated, approved, and committed as
`d212e4d2dae2cd0a3510c54d7cd098fdfd5da548`. **AUTO-006 was closed to `Done` on 2026-07-28** —
implemented, validated, approved, committed locally as
`d8d356d060076be4ad78afb4d20891004a946204`, and published to `main` under the same Human Owner
decision. **GOV-AUTO-03 was authorized by the Human Owner on 2026-07-28** as the single `Current`
task — implemented and validated the same day, stopped for Human Owner approval before any commit;
report: `docs/reports/GOV-AUTO-03-completion-report.md`. Remaining work otherwise belongs
to the DASH program (DASH-002..010, all `Planned`), AUTO-007, and the ordinary governance/tooling
tasks GOV-2 and GOV-3 — the latter recorded on 2026-07-28 by Human Owner decision as explicit
future work for the QA report artifact collision AUTO-005 documented and worked around. Each of
those requires its own fresh written authorization before it may become `Current`; authorizing
GOV-AUTO-03 authorized none of them. Since then: **AUTO-007 was closed to `Done` on 2026-07-29**,
**GOV-2 was closed to `Done` on 2026-07-29**, and **GOV-3 was authorized by the Human Owner on
2026-07-29** as the single `Current` task — implemented and validated the same day, stopped for
Human Owner approval before any commit; report: `docs/reports/GOV-3-completion-report.md`.

| Task | Title | Status |
|---|---|---|
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
