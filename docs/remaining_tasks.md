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
| T-307 | Target-bound governed verification evidence and engine execution provenance | Current |

**DASH-006 implementation update (2026-08-09):** implemented and validated on branch
`feature/dash-006-git-handover-views`, uncommitted, awaiting Human Owner approval. Report:
`docs/reports/agentos-dashboard/STAGE-06-completion.md`.

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

## AUTO-016 closure — 2026-08-08

AUTO-016 — Integrated Milestone Automation Runner — was registered and authorized by the Human
Owner on 2026-08-05, started on 2026-08-06 on branch `feature/auto-016-milestone-runner` (cut from
`main` at `4cbd714dd6a83de1b390feac39223e0b8f5d4cbf`), implemented under the finalized Revision 4
contract and its exact nineteen-file implementation allowlist, and published via pull request #19,
merged into `main` as `b4534c7` with CI green. It is closed `Current → Done`; the Current set is
empty. Completion report:
`docs/reports/workflow-automation/AUTO-016-completion-report.md`. Human Owner–confirmed external
runner evidence (runner run ID `auto016-20260805T213855Z-7fea75fc`, produced outside this
repository): 9/9 milestones complete, one bounded Codex review, one correction round, one closure
verification, one out-of-band closure of the last blocker, final verification 11/11, final runner
state `READY_FOR_COMMIT_APPROVAL`, no blocking findings. The deferred finding
`AUTO-016-M08-BLOCKER-001` is retained as explicitly non-blocking. This closure authorizes no
successor — AUTO-017 and every later roadmap phase remain unauthorized and `Planned`.

## DASH-005 implementation update — 2026-08-08

**DASH-005 — Workflow board and task detail — was authorized by the Human Owner on 2026-08-08**
as the single `Current` task — implemented and validated the same day on its registered branch
`feature/dash-005-board-task-detail` (the queue-lane board, the coded workflow-stage strip, the
ORCH program lane, the unclassified lane, and the task detail page), stopped, uncommitted, for
Human Owner approval; report: `docs/reports/agentos-dashboard/STAGE-05-completion.md`.

## PLAN-001 closure — 2026-08-10

**PLAN-001 — Close dashboard requirement-to-stage coverage gaps** was registered and authorized
by the Human Owner on 2026-08-10 as a governance/documentation-only correction: "PLAN-001 is
authorized as a governance/documentation-only correction to close Dashboard MVP
requirement-to-stage ownership gaps." It does **not** authorize DASH-007 implementation. It
corrected `docs/agentos-dashboard/STAGE_REGISTRY.md` §5 and the DASH-007/DASH-008/DASH-010 stage
contracts so DR-090, DR-091, EP-07, EP-08, and PG-08 are explicit DASH-007 responsibilities
(a bounded read-only Governance browser/search surface), EP-18 is an explicit DASH-008
Build/Acceptance/evidence responsibility rather than a bare allowlist mention, and DR-121, DR-122,
and PG-12 are explicit DASH-010 responsibilities (final cross-page verification and a bounded
read-only Settings/About surface). No code was written for any of it. Carrying no
`STAGE_REGISTRY.md` §3 registry row (the same non-AUTO/DASH-family governance-task shape as
GOV-2/GOV-3/GOV-4/GOV-AUTO-0x), it was closed `Current -> Done` in the same session, following the
GOV-AUTO-08/GOV-AUTO-10 precedent, leaving the diff uncommitted for a separate Human Owner review.
The `Current` set is empty both before and after. Rationale: `docs/agentos-dashboard/DECISIONS.md`
DD-16; `docs/DECISION_LOG.md`, 2026-08-10 entry. DASH-007..DASH-010 all remain `Planned` and
unauthorized in the table above — this closure authorizes no successor and does not begin,
authorize, or start DASH-007.

## T-307 registration — 2026-09-02

This section is a dated historical record of the registration event. It deliberately carries no
`Status:` line and asserts no live lifecycle state: the canonical, parseable status for T-307 is
the row in the table above, which `scripts/workflow-authorize.sh` updates on authorization. This
follows the convention already used by the `AUTO-015 closure`, `DASH-005 implementation update`,
and `PLAN-001 closure` sections in this file.

**T-307 — Target-bound governed verification evidence and engine execution provenance — was
registered on 2026-09-02** at `main` / `f632ebe458f21a1ccccb988b57c103237be4774e` with a clean
worktree, `workflowctl verify` PASS, and an empty `Current` set that the registration left empty.
Registration alone authorized nothing: no planning, implementation, branch, commit, or push
followed from it.

It restores target-bound governed review evidence and execution provenance: configurable named
verification bundles, engine-side execution of the selected commands inside a disposable clone of
the exact clean target HEAD, capture of exact argv and observed exit codes as engine evidence, a
rendered `## Verification evidence` section, and fail-closed engine version/HEAD/worktree/install
provenance in both the prompt payload/metadata and the agent-run artifact — all while review agents
stay `read-only`. It is the next unused canonical ID in Milestone 3, the family that owns the
sandbox executor (T-304) and the agent-run artifact (T-305) this task extends.

**Contract amended 2026-09-02 (Revision 2).** The Human Owner resolved both decisions the contract
had left open. OD-1 is now stricter than originally frozen: a dirty **editable** engine worktree
fails closed on every governed prompt/review/provenance execution, regardless of bundle selection.
OD-2 confirms the frozen bundle design — optional configuration, only explicitly configured
bundles selectable, unknown or duplicate selection a deterministic pre-execution error, selection
order fixing execution order, no-selection preserving backward-compatible behaviour, and no
consumer-specific names, paths, commands, or defaults. No open decision remains.

**Contract amended 2026-09-03 (Revision 3) — bounded Human Owner scope amendment; one test path.**
The Human Owner explicitly approved adding exactly one path to the frozen §7.2 test allowlist:
`tests/test_prompt_store.py`. The rationale is schema-version test coupling: T-307's frozen design
bumps the prompt payload/metadata schema `1.1` → `1.2`, and that file carries current-schema `"1.1"`
literals coupled directly to the bump — a `PromptSuccess(schema_version="1.1", …)` construction that
would fail during model construction after the bump rather than test its intended invariant, a
legacy-sidecar test that must express the new current-to-previous relationship `"1.2"` → `"1.1"`,
and a duplicate-key literal representing the current Prompt schema. **No production path was added
and no production scope expanded**: `src/ai_workflow_engine/prompt/store.py` pins no schema version
and remains excluded by §7.4. The objective, OD-1, OD-2, §7.1, every other §7.2 entry, §7.3, §7.5,
and §8 in its entirety are unchanged — §8 is byte-identical to the pre-amendment contract. This is
a Human-Owner amendment recorded while
the task is already `Current` — not a re-authorization; `scripts/workflow-authorize.sh` structurally
refuses a `Current` task, and the 2026-08-09 DASH-006 scope-amendment entry in
`docs/DECISION_LOG.md` is the governing precedent. T-307 remains `Current`, **implementation has not
started** under the amended scope, and `tests/test_prompt_store.py` is itself untouched. Rationale:
`docs/DECISION_LOG.md`, 2026-09-03 entry.

Contract, with the exact frozen allowed-path set, the fifteen acceptance criteria, the forbidden
surface, and the two resolved Human Owner decisions:
`docs/t-307-governed-verification-evidence-and-engine-provenance.md`. Authorization is a separate
Human Owner act through `scripts/workflow-authorize.sh T-307`, which additionally requires the
local governance baseline to be published to `origin/main` first.
