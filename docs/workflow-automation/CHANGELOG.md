# AgentOS Workflow Automation — Changelog

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Changelog |
| **Purpose** | Program-level changelog, newest first. |
| **Status** | Draft |
| **Version** | 2.1 |
| **Owner** | Documentation & Governance session |
| **Dependencies** | None |
| **Related Documents** | `docs/CHANGELOG.md` (repository-level; cross-posted there) |

## [Unreleased]

### Changed
- Governance recovery (2026-07-24): fixed an OD-9 retry-classification defect —
  `SKILL_CONTRACTS.md`/`MODEL_PROVIDER_CONTRACTS.md` classified retryability by error type
  instead of by timing (whether the operation had actually been invoked); corrected to classify
  strictly by timing, per the already-approved policy (`SKILL_CONTRACTS.md` → 1.2,
  `MODEL_PROVIDER_CONTRACTS.md` → 1.2, `WORKFLOW_STATES.md` §5a → 4.1). Appended
  `docs/agentos-dashboard/CHANGELOG.md` `CL-20260724-06` for its own 4.0 → 5.0 transition, which
  had no entry. Rewrote every live AUTO-002 branch-blocker description to state the settled
  release procedure rather than an open choice. Full record: `docs/DECISION_LOG.md`.
- Human Owner policy decisions applied (2026-07-24): OD-8 — `SUPERSEDED` ≈ task status `Done`
  (administratively closed, never successful completion); legal source states `AUTHORIZED`/
  `BLOCKED`/`IN_PROGRESS`/`SELF_REVIEW`/`REVIEW`/`APPROVAL`; never a fourth task status; never an
  automatic successor authorization (`STAGE_REGISTRY.md` §2/rule 9 → 6.0; Dashboard registry →
  5.0; `DECISIONS.md` DD-08). OD-9 — bounded same-state retry → idempotency/reconciliation →
  advance/`REPAIRING`(`IMPLEMENTING` only)/`FAILED` for the implementation-provider invocation
  and `create_commit`/`push_stage_branch`/`create_pull_request`, with an explicit deterministic
  retry classification; no new state or transition, only new reasons on existing edges
  (`WORKFLOW_STATES.md` new §5a → 4.0; `MACHINE_GATES.md` → 1.2; `FAILURE_RECOVERY.md` new §1a →
  1.2; `AGENT_CONTRACTS.md` → 1.2; `SKILL_CONTRACTS.md` → 1.1; `MODEL_PROVIDER_CONTRACTS.md` →
  1.1; `TEST_STRATEGY.md` new §4b → 1.2; `DECISIONS.md` DD-09). Both approvals recorded verbatim;
  both `OPEN_QUESTIONS.md` entries moved Open → Resolved (→ 1.3). Full record:
  `docs/DECISION_LOG.md`.
- Governance recovery (2026-07-24, twelfth pass): corrected `WORKFLOW_STATES.md`'s gate-count
  wording (→ 3.2) to describe the existing six named gates accurately — the Precondition gate
  spans two transition-source states; no transition or failure trigger changed. Added two
  unresolved Human Owner design questions to `OPEN_QUESTIONS.md` (→ 1.2) without choosing policy:
  OD-8 (`SUPERSEDED` task-status semantics across the development-stage registries) and OD-9
  (ordinary initial-execution provider/commit/push/PR failure handling). Full record:
  `docs/CHANGELOG.md`, `docs/DECISION_LOG.md`.
- Governance recovery (2026-07-24): `STAGE_REGISTRY.md` (→ 2.1), `HUMAN_AUTHORIZATION_MODEL.md`
  (→ 1.1), `WORKFLOW_STATES.md` (→ 1.1), `stage-prompts/README.md` (→ 1.1),
  `stage-prompts/AUTO-002.md` (→ 1.1), and `OPEN_QUESTIONS.md` (→ 1.1) revised to state
  explicitly, rather than leave implied, that: `STAGE_REGISTRY.md` + the SSP exclusively govern
  the AUTO-00x development-stage lifecycle while `WORKFLOW_STATES.md`/
  `HUMAN_AUTHORIZATION_MODEL.md` govern only the future runtime engine against target
  repositories; authorization preconditions and execution preconditions are separate concepts
  (new `STAGE_REGISTRY.md` §3 rule 17); a failed execution precondition moves a stage to the
  canonical `BLOCKED` state (≈ task status `Current`) without invalidating a recorded
  authorization, with `BLOCKED → AUTHORIZED → IN_PROGRESS` (precondition resolved; routed back
  through `AUTHORIZED` so the SSP's own gate keeps working, refined in a later pass — see below)
  or `BLOCKED → SUPERSEDED` (Human Owner directive) as its only legal exits; `STAGE_REGISTRY.md`
  rule 16 (closeout) now states which `workflowctl verify` findings are tolerated at closeout; and
  OD-3/OD-4 in `OPEN_QUESTIONS.md` are reworded to distinguish an authorization-gating "blocks
  stage X" from an implementation-time "affects stage X." A citation error in `STAGE_REGISTRY.md`
  §5's AUTO-002 authorization-log row and in `docs/DECISION_LOG.md`'s AUTO-002 entry (both
  incorrectly grounded a branch-precondition failure in `HUMAN_AUTHORIZATION_MODEL.md`) was
  corrected in place. No lifecycle transition changed; no AUTO-002 implementation performed. Full
  record: `docs/CHANGELOG.md`, `docs/DECISION_LOG.md`.
- AUTO-001 (2026-07-24): closed out to `Done`, merged into `main` via PR #3 (`191f600`).
  AUTO-002 enrolled as the sole `Current` task (authorized "I authorize AUTO-002."), registry
  state `BLOCKED` on an execution-precondition branch mismatch (working branch
  `feature/auto-002-orchestrator-foundation` vs. canonical
  `feature/auto-002-orchestrator-state-machine`); the authorization itself stands. Full record:
  `docs/CHANGELOG.md`, `docs/DECISION_LOG.md`.
- Governance recovery (2026-07-24, third pass): disambiguated OD-3/OD-4 (authorization-gating
  "blocks" vs. implementation-time "affects"); clarified rule 16's `workflowctl verify` tolerance
  at closeout; synchronized this changelog and `docs/remaining_tasks.md`/`docs/PROJECT_STATE.md`/
  `handover/PROJECT_HANDOVER.md` (+ regenerated `handover/PROJECT_CHECKSUM.md`) with current
  reality. Full record: `docs/CHANGELOG.md`, `docs/DECISION_LOG.md`.
- Governance recovery (2026-07-24, fourth pass): redefined rule 1's "clean tree" so it no longer
  describes an impossible condition; fixed a `BLOCKED`/SSP deadlock the third pass's rule 17 had
  introduced, by routing `BLOCKED → AUTHORIZED → IN_PROGRESS` rather than straight to
  `IN_PROGRESS`; rewrote rule 8 to distinguish frozen completion records (corrected only via new
  rule 18, a Governance Correction Record) from versioned living reference documents (amendable
  in place with a version bump); restored §5's two AUTO-002 authorization-log rows to their
  original wording (a prior pass had improperly merged them in place) and appended a proper
  correction row instead; and declared `docs/DECISION_LOG.md` explicitly append-only, disclosing
  that entries had been edited in place before that rule was explicit (`STAGE_REGISTRY.md` →
  3.0; `stage-prompts/README.md` → 1.2). Full record: `docs/CHANGELOG.md`, `docs/DECISION_LOG.md`.
- Governance recovery (2026-07-24, fifth pass): revised rule 16 to state that no successor is
  *automatically* selected at closeout, resolving a real contradiction with the Decision Log
  (both DASH-001→AUTO-001 and AUTO-001→AUTO-002 closed out a predecessor and authorized a
  successor in one session) without invalidating either historical, Human-Owner-directed
  authorization; completed rule 1's artifact list (it omitted this registry's own §4/§5 and the
  program-level changelog); added three failure transitions to `WORKFLOW_STATES.md` §3
  (`AUTHORIZED`/`PRECONDITIONS_CHECKED`/`PR_OPEN` → `FAILED`) that `MACHINE_GATES.md` required
  but which were missing; and mirrored all of the above, plus a stale `DASH-001: IN_PROGRESS`
  fix (it has been `Done` since 2026-07-23), into `docs/agentos-dashboard/STAGE_REGISTRY.md` (→
  2.0) and appended a correction entry to its changelog. `STAGE_REGISTRY.md` → 4.0;
  `WORKFLOW_STATES.md` → 1.2. Full record: `docs/CHANGELOG.md`, `docs/DECISION_LOG.md`.
- Governance recovery (2026-07-24, seventh pass): fixed §7's stale "AUTO-002 authorization
  requires..." wording (already satisfied and recorded) to state the fact plainly instead;
  audited the Dashboard/AUTO rule-equivalence claim rule-by-rule and fixed a real gap in DASH's
  closeout rule (missing `git`-check tolerance) rather than merely re-asserting equivalence;
  eliminated a formatter non-determinism release blocker at its root (`ruff-format` removed from
  `.pre-commit-config.yaml` as a redundant, disagreeing second formatter; all three hooks
  re-pinned to installed versions; idempotence verified over two consecutive runs). Full record:
  `docs/CHANGELOG.md`, `docs/DECISION_LOG.md`.
- `WORKFLOW_STATES.md` (2026-07-24): Human Owner explicitly reviewed and approved the three
  `FAILED` transitions added in the fifth pass as a MAJOR change under §11; version 1.2 → **2.0**.
  Full record: `docs/DECISION_LOG.md`.
- Governance recovery (2026-07-24, eighth pass): fixed `tests/test_migration_plan_apply.py` so
  `ruff format --check .` and `black --check .` fully agree; audited validator-coverage claims
  and found none overclaiming. Full record: `docs/DECISION_LOG.md`.
- `WORKFLOW_STATES.md` (2026-07-24): Human Owner explicitly reviewed and approved eight further
  `FAILED` transitions, completing the failure-transition model so every state
  `TEST_STRATEGY.md` §4a requires drift-testing at now has one; version 2.0 → **3.0**.
  `MACHINE_GATES.md`, `FAILURE_RECOVERY.md`, `TEST_STRATEGY.md`, and `AGENT_CONTRACTS.md` each
  → 1.1 for consistency. Full record: `docs/DECISION_LOG.md`.
- Governance recovery (2026-07-24, eleventh pass): added `STAGE_REGISTRY.md` rule 19 (Resume
  Preflight, → 5.0) so resuming an already-`IN_PROGRESS` stage no longer requires the impossible
  return to `AUTHORIZED` — zero new transitions, both resume outcomes leave registry state
  unchanged; restructured the SSP into explicit initial-start/resume sections (→ 1.3);
  `stage-prompts/AUTO-002.md` → 1.2; `WORKFLOW_STATES.md` → 3.1 (labeling only, no new
  transition); rewrote every live AUTO-002 branch-blocker assertion as a durable,
  branch-name-independent rule without touching the append-only §5 authorization log. Full
  record: `docs/DECISION_LOG.md`.

### Added
- AUTO-001 (2026-07-23): Complete architecture and governance documentation set for the
  AgentOS Workflow Automation program — 21 documents plus `stage-prompts/AUTO-001..AUTO-007.md`.
  Program enrolled in `docs/TASK_QUEUE.md` (AUTO-001 `Current`, AUTO-002..007 `Planned`);
  DASH-001 closed to `Done` first as a precondition. Documentation-and-architecture-only; no
  engine, test, or dependency change. Full record: `docs/CHANGELOG.md`,
  `docs/DECISION_LOG.md`.
