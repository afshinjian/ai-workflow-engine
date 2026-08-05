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
Human Owner approval before any commit; report: `docs/reports/GOV-3-completion-report.md`. **DASH-002 was
authorized by the Human Owner on 2026-07-29** as the single `Current` task — implemented and
validated the same day (the `agentos_dashboard/core/` adapters and snapshot builder, 115 tests),
stopped for Human Owner approval before any commit; report:
`docs/reports/agentos-dashboard/STAGE-02-completion.md`. Its registered branch was not created
and the work sits on `main`; that conflict, and the approval gate's report-name expectation, are
recorded as OD-D10 and OD-D11 in `docs/agentos-dashboard/OPEN_QUESTIONS.md`. **DASH-002 was
approved and closed to `Done` on 2026-07-29**, and **DASH-003 was authorized by the Human Owner
on 2026-07-29** as the single `Current` task — implemented and validated the same day (tolerant
parsers for the governance mirrors, decision log, orchestration implementation state, and
handover manifest, plus a consistency engine v1, 157 tests), recurring the same OD-D10 conflict
on `main`, stopped for Human Owner approval before any commit; report:
`docs/reports/agentos-dashboard/STAGE-03-completion.md`. **DASH-003 was approved and closed to
`Done` on 2026-07-29**, and **GOV-AUTO-04 — Automatic registered-branch preparation and canonical
completion-report naming** was proposed by Human Owner directive on 2026-07-29, registered as
`Planned`, and then **authorized by the Human Owner on 2026-07-29** as the single `Current`
task — implemented and validated the same day: `scripts/lib/branch_prepare.sh` gives
`workflow-authorize.sh`/`workflow-next.sh` one shared branch-preparation/verification routine
(resolves OD-D10), and `workflow-approve.sh`'s report discovery now accepts the Dashboard
program's canonical `STAGE-XX-completion.md` name, resolved from registry data (resolves OD-D11);
stopped, uncommitted, for Human Owner approval; report:
`docs/reports/GOV-AUTO-04-completion-report.md`. **GOV-AUTO-04 was approved and closed to `Done`
on 2026-07-29** (commit `0ffa591`). **OD-D9 — the serving-stack dependency decision — was
resolved by the Human Owner on 2026-07-29**: FastAPI (HTTP application framework), Uvicorn (ASGI
server), and Jinja2 (templates), declared in a new optional `dashboard` dependency group in
`pyproject.toml`, with the default install left free of them
(`docs/agentos-dashboard/OPEN_QUESTIONS.md` OD-D9; `DECISIONS.md` DD-09). **DASH-004 was
authorized by the Human Owner on 2026-07-30** as the single `Current` task — implemented and
validated the same day on its registered branch `feature/dash-004-dashboard-shell` (the local
backend, security middleware, and Overview page shell), stopped, uncommitted, for Human Owner
approval; report: `docs/reports/agentos-dashboard/STAGE-04-completion.md`. **AUTO-008 was closed to
`Done` on 2026-07-30**, **GOV-AUTO-06 and GOV-AUTO-07 were closed to `Done` on 2026-07-30 and
2026-07-31** — each resolving one of the two findings AUTO-008 deferred — and **AUTO-009 was closed
to `Done` on 2026-07-31**, delivering the engine's first public application-service boundary and
the read-only `workflowctl auto` command group; its six non-blocking defects (D1-D6) remain
deferred and unauthorized to fix. **AUTO-010 — Real Non-Interactive Provider Runtime — was
registered and authorized by the Human Owner on 2026-07-31** as the single `Current` task, on its
registered branch `feature/auto-010-provider-runtime`; contract:
`docs/workflow-automation/stage-prompts/AUTO-010.md`; report:
`docs/reports/workflow-automation/AUTO-010-completion-report.md`. **AUTO-010 was approved and
closed to `Done` on 2026-07-31** after a fourteen-point scope, runtime, and safety verification —
both providers live-validated against the real installed CLIs on all ten acceptance criteria each
(25 live tests, zero skipped), 3,241 tests green, three blockers fixed inside the shared provider
process runner, four non-blocking defects deferred. **AUTO-010 was published on 2026-08-01** via
PR #10, merged as `fd0b34f`. **AUTO-011 — Unified Provider and Agent Result Contract — was
registered and authorized by the Human Owner on 2026-08-01** as the single `Current` task, on its
registered branch `feature/auto-011-agent-result-contract`; it introduces the canonical
`AgentRunResult` for provider and agent execution without implementing any workflow mode or
lifecycle; contract: `docs/workflow-automation/stage-prompts/AUTO-011.md`; report:
`docs/reports/workflow-automation/AUTO-011-completion-report.md`. **AUTO-011 was approved and
closed to `Done` on 2026-08-01** after a fourteen-point scope, contract, and compatibility
verification — 3,352 tests green, 25 live tests with zero skips, `mypy --strict` clean over 121
source files, no production file outside the new module modified, no blocker fixed because none
existed, and three non-blocking defects (D-8, D-9, D-10) recorded and deferred. **AUTO-011 was
published on 2026-08-01** via PR #11, merged as `e2b069c`. **AUTO-012 — Configurable Approval
Policy, Persistence, and Invalidation — was registered and authorized by the Human Owner on
2026-08-01** as the single `Current` task, on its registered branch
`feature/auto-012-approval-policy`; it builds the reusable `ApprovalService` subsystem — typed
policy with four-layer resolution, immutable snapshots, durable append-only records, manual and
timeout decisions, checksum binding, and invalidation — without implementing any workflow mode. The
same directive required the separate governance act recorded as `HUMAN_AUTHORIZATION_MODEL.md` v2.0
§5a, authorizing the subsystem only. Contract:
`docs/workflow-automation/stage-prompts/AUTO-012.md`; report:
`docs/reports/workflow-automation/AUTO-012-completion-report.md`. **AUTO-012 was approved and closed
to `Done` on 2026-08-01** — 3,469 tests green, 25 live tests with zero skips, `mypy --strict` clean
over 122 source files, both modified production files purely additive, no workflow mode or state
implemented, no blocker fixed because none existed, and three non-blocking defects (D-11, D-12,
D-13) recorded and deferred. AUTO-013 remains unauthorized. **GOV-4 — Isolate Claude live-test
configuration per attempt and add bounded test-only format retries — was registered and authorized
by the Human Owner on 2026-08-02** as the single `Current` task, as an ordinary (non-AUTO/GOV-AUTO)
engine task record following the GOV-2/GOV-3 precedent — a pre-AUTO-013 baseline-verification
correction to the live acceptance test harness, discovered while verifying the AUTO-013 baseline.
Scope was test-only (`agentos_workflow/tests/live/test_live_providers.py` and
`agentos_workflow/tests/test_provider_runtime.py`); no production code was touched. **GOV-4 was
approved and closed to `Done` on 2026-08-02** — two full live-suite runs at 32 passed/0 failed/0
skipped each, authentication template byte- and mtime-identical across every live run, zero
`.claude-A` contamination, 3,470 tests green, `mypy` clean over 122 source files. **AUTO-013 —
Foreground Implementer Mode (AUTHORIZED → PR_OPEN) — was registered and authorized by the Human
Owner in one written directive on 2026-08-02** as the single `Current` task, on its registered
branch `feature/auto-013-implementer-to-pr`; it builds `ImplementerModeDriver`/`ImplementationTask`
(`agentos_workflow/implementer.py`), composing the already-delivered `WorkflowSession`,
`WorkflowService`, deterministic validation, and Git/GitHub/reporting Skills to drive one workflow
from `AUTHORIZED` to `PR_OPEN`, with a guarded `independent_qa_required` opt-out and no new
workflow state. Contract: `docs/workflow-automation/stage-prompts/AUTO-013.md`; report:
`docs/reports/workflow-automation/AUTO-013-completion-report.md`. **AUTO-013 was approved and closed to `Done` on 2026-08-02** after an eighteen-point final
scope and integrity verification, with two corrections recorded (the `ApprovalService` gate moved
to `READY_TO_COMMIT`; `MACHINE_GATES.md` amended to 1.4 with a new §4a) — 3,484 tests passing, 32
live-CLI tests passing with zero skips, `mypy --strict` clean over 123 source files,
`ruff`/`black`/pre-commit clean, wheel packaging and out-of-tree imports verified. Publication was
subsequently completed via PR #14 (merge commit `4659335`); no governance entry recorded that
merge at the time, which AUTO-014's registration records as a deferred documentation finding.
**AUTO-014 — CI, Merge, Repository Finalization, and Runtime Closeout (`PR_OPEN → DONE`) — was
registered, implemented, fully validated, and closed to `Done` on 2026-08-03** on its registered branch
`feature/auto-014-merge-closeout`; it resumes an
existing workflow's persisted `PR_OPEN` state through `MergeCloseoutModeDriver`
(`agentos_workflow/merge_closeout.py`), composing the already-delivered `WorkflowSession`,
`MergeAgent`, `CloseoutAgent`, and Git/GitHub/reporting Skills to reach `DONE`, with no new
workflow state. Contract: `docs/workflow-automation/stage-prompts/AUTO-014.md`. AUTO-015 and
every later roadmap phase remain unauthorized. Completion report:
`docs/reports/workflow-automation/AUTO-014-completion-report.md`.

| Task | Title | Status |
|---|---|---|
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

## GOV-AUTO-08 — AUTO-015 Successor Scope and Contract Definition

Status: Done

Documentation-only governance task registered on 2026-08-04 as the sole Current task after
AUTO-014 `COMPLETE`. It inventories the successor options and records no selection on behalf of
the Human Owner. Branch: `governance/gov-auto-08-successor-scope`.

The Human Owner selected **Automatic Next-Stage Computation and Prompt Generation** as the
proposed basis for AUTO-015. GOV-AUTO-08 is closed `Current → Done`; this selection does not
authorize implementation. AUTO-015 is not registered, authorized, or implemented, and the
Current task set is empty.

## AUTO-015 closure — 2026-08-05

AUTO-015 — Deterministic Next-Stage Proposal and Governed Prompt Generation — was implemented on
branch `feature/auto-015-successor-planning`, committed as `05b819e`, and published via pull
request #17, merged into `main` as `e325f95`. It is closed `Current → Done`; the Current set is
empty. Completion report:
`docs/reports/workflow-automation/AUTO-015-completion-report.md`. This closure authorizes no
successor — AUTO-016 and every later roadmap phase remain unauthorized and `Planned`.

## GOV-AUTO-10 — AUTO-016 Integrated Runner Contract Definition

Status: Done

Documentation-only governance task registered on 2026-08-05 as the sole Current task after
AUTO-015 `COMPLETE`. It converts the Human Owner's selected successor capability —
**Integrated Milestone Automation Runner** — into a finalized, implementation-ready stage contract
and obtains one bounded independent review of it. No branch was registered; the work was performed
on `main` as an uncommitted documentation change set.

GOV-AUTO-10 is closed `Current -> Done`; the contract does not authorize implementation. AUTO-016
is not registered, authorized, or implemented, and the Current task set is empty. The three
decisions this task recorded as open — DEC-016-002, DEC-016-005, DEC-016-006 — were ruled by the
Human Owner on 2026-08-05 and propagated into contract Revision 4 (`docs/DECISION_LOG.md`). No
contract decision remains open; allowlist sign-off, acceptance-plan approval, a fresh authorization
preflight, and an explicit authorization statement still block implementation. Contract:
`docs/workflow-automation/stage-prompts/AUTO-016.md`. Review:
`docs/reports/workflow-automation/AUTO-016-contract-review.md`.

## Authorization update — 2026-08-05

## AUTO-016

Status: Current

The Human Owner explicitly authorized this single task, registering it for the first time in the
same act: "I authorize AUTO-016 implementation under the finalized AUTO-016 contract and its exact
implementation allowlist." Authorization is bounded to the finalized Revision 4 contract
(`docs/workflow-automation/stage-prompts/AUTO-016.md`) and its exact nineteen-file implementation
allowlist (§23), with the forbidden surface (§24) unchanged; the independent review's verdict is
"CONTRACT READY FOR HUMAN OWNER AUTHORIZATION". Registry state `NOT_STARTED → AUTHORIZED`.

Registration only — implementation has not begun and progress is 0%. The registered branch
`feature/auto-016-milestone-runner` was not created, because rule 14 requires it to be cut from a
`main` baseline that already carries the authorization record; this session was bounded to preparing,
validating, and committing that record locally, with push withheld for Human Owner review. A separate
initial-start session will create the branch from the synchronized authorized baseline and record
`AUTHORIZED → IN_PROGRESS`; a separate implementation session will then execute AUTO-016. Live
acceptance is authorized only during that later implementation/verification phase.
