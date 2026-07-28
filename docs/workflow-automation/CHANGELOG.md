# AgentOS Workflow Automation — Changelog

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Changelog |
| **Purpose** | Program-level changelog, newest first. |
| **Status** | Draft |
| **Version** | 2.12 |
| **Owner** | Documentation & Governance session |
| **Dependencies** | None |
| **Related Documents** | `docs/CHANGELOG.md` (repository-level; cross-posted there) |

## [Unreleased]

### Added
- AUTO-005 (2026-07-28): implemented the six Agents of `AGENT_CONTRACTS.md` §2-7 in
  `agentos_workflow/agents/`, together with the two Orchestrator-owned sequences §8 says are not
  Agents. The capability boundary of §1 is enforced three independent ways: a broker that refuses
  every out-of-contract Skill name and Provider role, a comparison of the capability tables against
  `AGENT_CONTRACTS.md`'s own Skill lists so the two cannot drift, and an AST assertion that no
  Agent module imports a Skill family, names `select_live_provider`/`MockProvider`, or reaches a
  subprocess. `AgentResult` has no state field, so an Agent deciding its own transition is
  unrepresentable. The `VALIDATING` gate (`MACHINE_GATES.md` §3) runs all seven checks even after
  one fails, so a repair attempt sees every problem at once instead of one per round; an unbound or
  unspawnable check fails the gate rather than being skipped (§1's "no third outcome"). The repair
  loop (`FAILURE_RECOVERY.md` §1-2) rebuilds the failure report from the round that just ran,
  re-runs deterministic validation *and* QA in full after every attempt, stops at
  `repair_attempt_limit` (pinned to 3 by the configuration schema), and ends without re-validating
  when an attempt produced nothing usable. `QAAgent` cannot read the implementation report — the
  Skill is absent from its capability set — and reports a QA pass on a failed deterministic gate as
  contradictory evidence rather than a pass. `MergeAgent` never reaches
  `enable_automatic_squash_merge` on a head-SHA mismatch, and `CloseoutAgent` refuses every
  destructive step, before touching anything, without a `MergeConfirmation` bound to its own stage
  branch. AUTO-006's eight GitHub-facing Skills are named and unbound, failing as
  `SKILL_UNAVAILABLE`. One integration limitation is recorded rather than worked around silently:
  `generate_qa_report` allows one report per workflow identifier, so each QA round is written under
  a per-attempt audit scope; the Human Owner accepted this for AUTO-005 and directed it be tracked
  as future work, now recorded as GOV-3 in `docs/TASK_QUEUE.md`. 133 new tests (1,465 in
  `agentos_workflow`, up from 1,332); engine collection unchanged at 1,037. Approved by the Human
  Owner on 2026-07-28, who accepted every documented limitation and authorized exactly one local
  commit; no push, merge, or AUTO-006 work was performed.
- AUTO-004 (2026-07-28): implemented the Model Provider layer in `agentos_workflow/providers/`
  (`MODEL_PROVIDER_CONTRACTS.md`) — the common `Provider` interface (§1), `ClaudeCLIProvider` (§2,
  implementation and repair) and `CodexCLIProvider` (§3, independent QA) as subprocess adapters
  over the target repository's own configured executable and timeout, and `MockProvider` (§4). The
  package raises nothing to the Orchestrator: every failure, including spawn failure, timeout, and
  malformed CLI output, is a typed `ProviderFailure`. Retry classification follows §2's "*when*,
  not *what*" rule — a spawn failure is the single `PROVEN_PRE_SIDE_EFFECT` case; a timeout, an
  abnormal exit, and a clean exit with unreadable output are all `POSSIBLE_SIDE_EFFECT` and never
  eligible for a blind retry. Session isolation (§5) is enforced by a per-invocation `0o700`
  directory keyed by workflow/provider/invocation with `TMPDIR` redirected into it, stateless
  provider instances, and a fresh instance per selection. `MockProvider`'s exclusion from real
  workflows (`MVP_SCOPE.md` §3) is structural on four independent counts: it is not a
  `CLIProvider` and live selection is typed to return one, it is absent from the live registry, it
  has no `from_config`, and no live module imports or names it (asserted by AST). Prompts travel
  on stdin, never argv; only allowlisted environment variables reach a provider process, `HOME`
  never implicitly among them. 106 new tests with the process boundary mocked by executable
  substitution, so the default suite needs no Claude or Codex CLI; engine collection provably
  unchanged at 1,037. No dependencies added; no existing runtime module modified. Stage remains
  `IN_PROGRESS`, stopped for Human Owner approval; no commit, push, merge, or AUTO-005 work was
  performed.
- AUTO-003 (2026-07-27): implemented the deterministic Repository, Contract, Validation, and
  Reporting Skill families in `agentos_workflow/skills/` (`SKILL_CONTRACTS.md` §2, §3, §4, §6) —
  31 named Skills over fixed argv, each returning a typed `SkillResult`/`SkillFailure` rather than
  raising to the Orchestrator (§7), with retry classification following §5 exactly. The forbidden
  Git operations of `SECURITY_MODEL.md` §2 are unreachable by construction (no caller-supplied
  verb, no `--force`/`-D`/`reset`/`rebase`/`--amend` literal anywhere), machine-checked by an
  AST assertion over the module's own source; baseline mutation is refused by a required
  baseline parameter, and branch deletion requires a `MergeConfirmation` token with no default.
  Report and audit writes are confined to the audit root by descriptor-relative `O_NOFOLLOW`
  walks, are content-hash idempotent, and refuse to overwrite differing content. 222 new tests
  against temporary real Git repositories and fixture contracts (`TEST_STRATEGY.md` §3); the
  engine's own `GitClient` is neither imported nor modified, and `src/`, `tests/`, and the default
  `pytest` collection are provably unchanged (978 collected before and after). Decisions:
  DD-33 (OD-2), DD-34, DD-35. Stage remains `IN_PROGRESS`, stopped for Human Owner approval;
  no commit, push, merge, or AUTO-004 work was performed.

### Changed
- AUTO-004 (2026-07-28): approved, closed, and published. The Human Owner approved the
  implementation, recorded commit `84616d5`, moved the stage `IN_PROGRESS → COMPLETE` (task
  `Current → Done`), and authorized publication: `feature/auto-004-model-providers` pushed to
  `origin`, local `main` fast-forwarded from `origin/main`, the stage branch merged into `main` by
  the established safe merge policy, and `main` pushed. `main` now carries
  `agentos_workflow/providers/`, so AUTO-005's Agents have real Providers to be restricted to. The
  stage branch was retained (no deletion) and both pre-existing stashes untouched. Per
  `STAGE_REGISTRY.md` §3 rule 8 the stage completion report was **not** rewritten — the commit
  post-dates it — and the commit, approval, and merge are recorded in a new append-only addendum
  to that report, a new §5 Authorization Log row, and `docs/DECISION_LOG.md`.
- AUTO-003 (2026-07-27): **OD-2 resolved** — secret handling is an environment allowlist as the
  primary control plus named, linear-time regex output redaction as defense-in-depth, applied to
  every string leaving a Skill. Entropy-based detection was considered and rejected (DD-33).
- AUTO-002 (2026-07-27): published and merged into `main` under a separate Human Owner
  authorization — branch pushed, PR #5 merged by merge commit `87a5062` (parents `163bcee` +
  `20c9890`) after CI passed, `main` synchronized. The stage branch was retained and both
  pre-existing stashes left untouched. No registry state changed; AUTO-002 was already `COMPLETE`.
- AUTO-002 (2026-07-27): Human Owner reviewed the implementation/remediation report and
  validation results, accepted the stage as sufficient, explicitly waived another independent
  review, and authorized closure plus one local commit. AUTO-002 is now `COMPLETE`/`Done`; no
  successor, push, or merge is authorized. Remaining portability, infrastructure-retry, and
  remote-reconciliation items are future work, not AUTO-002 blockers (DD-32).
- AUTO-002 (2026-07-27): Human Owner authorized all five tasks from a third independent review.
  Implementation reconciliation now binds evidence to the authorization record, exact branch tip,
  latest persisted attempt, independently-derived baseline diff, path policy, and a strict
  workflow/stage/attempt/branch/head/path completion report. Mutable persistence rejects hardlink
  aliases; authorization and attempt sidecars use literal workflow-directory descriptor
  confinement; authorization, attempt, and completion-report JSON reject duplicate keys; and
  `AUDIT_MODEL.md` now documents repository identity and canonical path as separate fields.
  Governance reconciled in DD-27 through DD-31. AUTO-002 remains `IN_PROGRESS`, pending fresh
  independent review; no commit, push, merge, network access, or later-stage work was performed.
- AUTO-002 (2026-07-27): a **second independent review reproduced five defects (IR-01..IR-05)**,
  two of them in code the pass below reported as hardened — invalidating that pass's completion
  claims for F04, F05, F08, and F09 as overstated. All five remediated: IR-01 repository-lock
  confinement via descriptor-relative `O_NOFOLLOW` walk (`orchestrator/lock.py`, new
  `LockPathConfinementError`); IR-02 state/audit record confinement via one shared confined-open
  primitive covering both histories and both reads and writes (`orchestrator/state_store.py`, new
  `StateStorePathConfinementError`); IR-03 strict rejection of every noncanonical changed-path
  pattern plus canonicalisation of observed Git paths (`config/schema.py`, `orchestrator/engine.py`);
  IR-04 chronological ordering enforced at append time under the append lock (`state_store.py`, new
  `StateStoreOrderingError`); IR-05 duplicate JSON object keys rejected at every nesting level
  (`state_store.py`). F11 reclassified `INSUFFICIENT_DURABLE_EVIDENCE` — its historical definition
  and regression mapping could not be reconstructed from durable repository evidence; no definition
  was invented. Governance reconciled (`DECISIONS.md` DD-21 → DD-26, version 1.6 → 1.7). Validation:
  1967 passed (`pytest tests agentos_workflow/tests`; +95 regression tests over the prior 1872),
  Ruff/Black/mypy(`src`)/mypy(`agentos_workflow`)/`git diff --check` clean, `workflowctl verify`
  clean apart from the pre-existing `upstream_missing` finding. AUTO-002 remains `IN_PROGRESS` and
  is now **pending fresh independent review** — no independent approval has been obtained for this
  remediation. AUTO-003/AUTO-005 remain unauthorized and `NOT_STARTED`. Full ledger:
  `docs/DECISION_LOG.md`, `docs/reports/workflow-automation/AUTO-002-completion-report.md`.
- AUTO-002 (2026-07-27): sequential remediation pass F04/F05/F06 (locking, JSONL durability,
  attempt accounting; implemented earlier this session), F08 (audit-record identity/timestamp/
  path-confinement/ordering invariants hardened, `state_store.py`), F09 (changed-path config
  patterns confined to repository-relative form, `config/schema.py`), F10 (`ResumedWorkflow.
  transition_to` now rejects `AUTHORIZED` before any persistence, closing a lower-level
  authorization-bypass write), and F12 (regression-test-adequacy audit, no code change) completed
  and governance-reconciled (`DECISIONS.md` DD-16 → DD-20, version 1.5 → 1.6). Full ledger:
  `docs/DECISION_LOG.md`, `docs/reports/workflow-automation/AUTO-002-completion-report.md`.
  AUTO-002 remains `IN_PROGRESS`; AUTO-003/AUTO-005 remain unauthorized and `NOT_STARTED`.
- AUTO-002 (2026-07-27): Human Owner decision AUTO002-F07 — reconciliation evidence must never
  be accepted merely on a caller's success claim, self-consistency, or a nonblank reference
  string. Narrowly extended DD-14's local-observation boundary (evidence-verification-only) with
  `LocalEvidenceObserver`/`resolve_evidence_artifact` (`agentos_workflow/observation/evidence.py`,
  new); `ImplementationDiffEvidence`/`CommitEvidence` are now independently re-verified from real
  local Git/filesystem state before being trusted, wired transparently into the existing
  `evaluate_initial_execution_failure` (no public signature changed).
  `RemoteRefEvidence`/`PullRequestEvidence` now unconditionally fail closed
  (`ReconciliationVerifierUnavailableError`) — remote/GitHub verification remains unauthorized and
  pending future work; this does not authorize AUTO-003 or AUTO-005 (`DECISIONS.md` DD-15 → 1.5).
  Full record: `docs/DECISION_LOG.md`.
- Governance Correction Record (2026-07-27): a fresh-session reconciliation, performed before
  AUTO002-F04, found `DECISIONS.md`'s DD-14 entry had been appended out of physical sequence
  (between DD-01 and DD-02 instead of after DD-13) and `STAGE_REGISTRY.md` §6 left reading "DD-01
  through DD-13." Human Owner authorized a Governance Correction Record (`STAGE_REGISTRY.md` §3
  rule 18): DD-14 remains valid and binding, unmoved and unrewritten; the effective decision
  sequence is DD-01 through DD-14; `STAGE_REGISTRY.md` §6 corrected accordingly (`DECISIONS.md` →
  1.4, `STAGE_REGISTRY.md` → 6.2). No workflow state, transition, implementation, or test changed.
  Full record: `docs/DECISION_LOG.md`.
- AUTO-002 (2026-07-27): Human Owner resolved AUTO002-F03's live-observation and
  state-specific-resume ambiguity. Added the strictly local, fixed-argv, read-only AUTO-002
  observation exception and the authoritative branch/HEAD/worktree/evidence matrix
  (`ARCHITECTURE.md` → 1.1, `WORKFLOW_STATES.md` §6a → 4.3, `MACHINE_GATES.md` §2a → 1.3,
  `DECISIONS.md` DD-14 → 1.3, and `stage-prompts/AUTO-002.md` → 1.3). No state or transition
  changed; AUTO-003 remains unauthorized and `NOT_STARTED`.
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
