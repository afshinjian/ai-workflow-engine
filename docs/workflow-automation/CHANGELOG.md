# AgentOS Workflow Automation — Changelog

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Changelog |
| **Purpose** | Program-level changelog, newest first. |
| **Status** | Draft |
| **Version** | 2.17 |
| **Owner** | Documentation & Governance session |
| **Dependencies** | None |
| **Related Documents** | `docs/CHANGELOG.md` (repository-level; cross-posted there) |

## [Unreleased]

### Added
- AUTO-009 (2026-07-31, implementation): `agentos_workflow/service.py` and
  `agentos_workflow/cli_auto.py` deliver the boundary
  `workflowctl auto -> WorkflowService -> agentos_workflow read-only APIs`. `WorkflowService`
  exposes exactly `status`, `list`, `audit`, `report`, each returning a frozen `extra="forbid"`
  model; `AuditResult` carries the store's own `StateTransitionRecord`/`CommandExecutionRecord`
  models so every `AUDIT_MODEL.md` section 2-3 field, including `gate_evidence_ref`, `stdout_ref`,
  and `stderr_ref`, survives the boundary intact. Two new errors, `WorkflowNotFoundError` and
  `ReportNotFoundError`, express read-only lookup absence without inheriting resume semantics;
  every pre-existing configuration, corruption, and confinement error passes through unchanged.
  `StateStore.list_workflow_ids()` and `skills.reporting.read_reports()` were added to their
  owning modules; `_open_confined_directory` gained a `missing_ok` keyword whose default preserves
  behaviour for all four existing call sites. `src/ai_workflow_engine/cli.py` changed by +14/-0.
  Registry state `IN_PROGRESS -> COMPLETE`; 146 new tests (3,005 -> 3,151).
- AUTO-009 (2026-07-31, registration and authorization): registered and authorized by the Human
  Owner as the first public application-service boundary for the engine. `WorkflowService`
  (`agentos_workflow/service.py`) exposes exactly four read-only operations — `status`, `list`,
  `audit`, `report` — over the existing state, audit, report, and configuration components, and
  `agentos_workflow/cli_auto.py` surfaces the same four as an additive `workflowctl auto` Typer
  sub-application. Registry state `NOT_STARTED -> AUTHORIZED -> IN_PROGRESS`; registry stage count
  rises 18 -> 19. No stage contract file was issued; the written directive is the contract.

### Fixed
- GOV-AUTO-07 (2026-07-31, implementation): resolved AUTO-008's F-1 finding. Every raise site of
  `AuthorizationBindingDriftError` in `orchestrator/engine.py` now follows one convention —
  `expected` is the authorization-bound value where the comparison has one, otherwise the invariant
  the check requires; `actual` is the current runtime, repository, live-observation, or
  caller/disk-supplied value judged against it. Three clusters were normalized:
  `_detect_authorization_binding_drift` (all ten `_BINDING_DRIFT_FIELDS`, which passed the current
  value as `expected`), two `_live_drift` calls in `_validate_live_resume_observation` that put the
  bound value in `actual` (including two adjacent `repository_identity` raises that contradicted
  each other), and the four cross-record checks in `_validate_persisted_authorization_evidence`
  that reported the persisted `AuthorizationRecord` as `actual`. Comparisons are symmetric, so
  which drifts are detected, in what order, and with what durable `-> FAILED` consequence is
  unchanged; only the reported sides moved. Public attributes and the rendered message are
  byte-unchanged.

### Added
- AUTO-007 (2026-07-28, implementation): built the stage's own test-authoring deliverables under
  `agentos_workflow/tests/e2e/**` and `agentos_workflow/tests/recovery/**` — no production code
  changed. `test_interruption_resume_matrix.py` (16 tests) proves `TEST_STRATEGY.md` §4a's
  authorization-bound-drift check "at each state" across all eight states
  `WORKFLOW_STATES.md` §3 names (`BRANCH_CREATED`, `IMPLEMENTING`, `REPAIRING`,
  `READY_TO_COMMIT`, `COMMITTED`, `PUSHED`, `AUTO_MERGE_ENABLED`, `MERGED`), plus a negative
  control proving a non-drifted resume still succeeds. `test_retry_reconciliation_matrix.py`
  (25 tests) builds §4b's (state × outcome) matrix across `IMPLEMENTING`, `READY_TO_COMMIT`,
  `COMMITTED`, `PUSHED`. `test_security_model.py` (17 tests) gives every numbered
  `SECURITY_MODEL.md` rule (§1-§7) at least one dedicated test, and records — without fixing — a
  defense-in-depth observation that `create_commit`/`push_stage_branch` have no independent
  baseline-branch check of their own (safe today only because `create_stage_branch` never lets
  the stage branch equal baseline). `test_dry_run.py` (1 test) drives one real `WorkflowSession`
  through every real Agent and Skill, `CREATED → DONE`, against a real disposable Git repository
  and a faked `gh`, exercising one repair cycle, one interruption/resume cycle, and the full
  commit → push → PR → auto-merge → checks-wait → merge → closeout path — `TEST_STRATEGY.md` §5's
  and `MVP_SCOPE.md` §4's acceptance demonstration. Building that dry run surfaced two genuine,
  previously undetected production defects, neither fixed here (outside this stage's allowed
  files): a `stage_contract_hash` format disagreement between `PMOAgent` and the live resume
  observer (new OD-11, `DECISIONS.md` DD-39), and empirical confirmation of the existing OD-10
  `allowed_environment_variables` gap. 59 new tests; `agentos_workflow` suite 1,557-green (up
  from 1,498); engine `tests` collection unchanged at 1,092. This stage's own contract requires a
  mandatory independent, fresh-session security review before it may reach `COMPLETE`; that
  review has not been performed, so registry state remains `IN_PROGRESS`, stopped for Human Owner
  approval; no commit, push, merge, or further work was performed.
- AUTO-006 (2026-07-28, implementation): implemented the eight Git/GitHub Skills of
  `SKILL_CONTRACTS.md` §5 in the new file `agentos_workflow/skills/git_github.py` —
  `create_commit`, `push_stage_branch`, `create_pull_request`, `read_pull_request_state`,
  `verify_head_sha`, `read_required_checks`, `enable_automatic_squash_merge`,
  `verify_merge_completion` — binding the eight Skill names `GitAgent`/`MergeAgent` (AUTO-005)
  already called against fakes; no Agent code changed. `enable_automatic_squash_merge` has
  exactly one `gh pr merge` call site, always `--auto --squash`, never `--admin` (asserted by an
  AST test over the module's own source); every `gh` invocation is `cwd`-scoped to the target
  repository with no `--repo` flag, so no argv can redirect a Skill at an arbitrary GitHub
  repository. OD-1 resolved in favor of native GitHub auto-merge (`DECISIONS.md` DD-37).
  Retry classification follows `SKILL_CONTRACTS.md` §5's asymmetric policy: `create_commit`,
  `push_stage_branch`, and `create_pull_request` classify `POSSIBLE_SIDE_EFFECT` once their
  subprocess has run, even for `create_commit`'s purely local case, since a hook or partial write
  could already have applied. 33 new tests: real temporary Git repositories for the local Skills
  (the same technique `test_skills_repository.py` uses), and `gh` mocked at the process boundary
  — a fake executable placed first on `PATH`, with call recording, never internals patched —
  for the five GitHub-facing Skills. `agentos_workflow` suite 1,498-green (up from 1,465); engine
  `tests` collection unchanged at 1,066 (no `tests/`/`src/` file touched). Self-review discovered
  and recorded, but did not fix (outside this stage's allowed files), that five of the eight
  Skill calls in `agents/git.py`/`agents/merge.py` never forward
  `allowed_environment_variables`, so `gh` cannot authenticate in a real deployment until a
  future stage adds it (`DECISIONS.md` DD-38, `OPEN_QUESTIONS.md` OD-10). Stage remains
  `IN_PROGRESS`, stopped for Human Owner approval; no commit, push, merge, or AUTO-007 work was
  performed.
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
- AUTO-006 (2026-07-28): approved, closed, and published. The Human Owner approved the
  implementation, recorded commit `d8d356d`, moved the stage `IN_PROGRESS → COMPLETE` (task
  `Current → Done`), and authorized publication: `feature/auto-006-pr-merge-closeout` pushed to
  `origin`, local `main` updated from `origin/main`, the stage branch merged into `main` by the
  established safe merge policy, and `main` pushed. `main` now carries
  `agentos_workflow/skills/git_github.py`. The stage branch was retained (no deletion) and both
  pre-existing stashes untouched. The two documented limitations — Orchestrator wiring of the
  Merge Safety Gate / Checks-Wait Gate, and the `allowed_environment_variables` gap on five
  `gh`-based Skill calls (OD-10, DD-38) — were explicitly accepted rather than fixed in scope. Per
  `STAGE_REGISTRY.md` §3 rule 8 the completion report was **not** rewritten — the commit
  post-dates it — and the commit, approval, and merge are recorded in a new append-only addendum,
  a new §5 row, and `docs/DECISION_LOG.md`. No successor is authorized: AUTO-007 remains
  `NOT_STARTED`.
- AUTO-005 (2026-07-28): approved, closed, and published. The Human Owner approved the
  implementation, explicitly accepted all five documented limitations, recorded commit `430cbb4`,
  moved the stage `IN_PROGRESS → COMPLETE` (task `Current → Done`), and authorized publication:
  `feature/auto-005-agents` pushed to `origin`, local `main` fast-forwarded from `origin/main`, the
  stage branch merged into `main` by the established safe merge policy, and `main` pushed. `main`
  now carries `agentos_workflow/agents/`. The stage branch was retained (no deletion) and both
  pre-existing stashes untouched. The QA report artifact collision was recorded as **GOV-3**
  (`docs/TASK_QUEUE.md`, `Planned`, unauthorized) rather than fixed in scope, so
  `agentos_workflow/skills/**` is byte-unchanged. Per `STAGE_REGISTRY.md` §3 rule 8 the completion
  report was **not** rewritten — it was finished before the commit existed and names no hash — and
  the hash, closure, and merge are recorded in a new append-only addendum, a new §5 row, and
  `docs/DECISION_LOG.md`. No successor is authorized: AUTO-006 remains `NOT_STARTED`.
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

## 2026-07-28 — AUTO-006 authorized

The Human Owner authorized AUTO-006 through the two-confirmation local gate. The stage is
`AUTHORIZED`; implementation, approval, push, and merge remain separate.

## 2026-07-28 — AUTO-007 authorized

The Human Owner authorized AUTO-007 through the two-confirmation local gate. The stage is
`AUTHORIZED`; implementation, approval, push, and merge remain separate.

## 2026-07-29 — AUTO-007 closed

The Human Owner approved and closed AUTO-007 through the automatic task-closeout gate
(`scripts/workflow-approve.sh`, GOV-AUTO-03). Registry state `COMPLETE`; task status `Done`.

## 2026-07-29 — GOV-3 implemented (attempt-aware report artifact names)

Implemented under the ordinary engine task GOV-3 (`docs/TASK_QUEUE.md`), not an AUTO stage, so no
stage-registry lifecycle state changes. The four report generators in
`agentos_workflow/skills/reporting.py` take an optional validated `sequence`, naming an artifact
`<kind>.<sequence>.json` inside the workflow's own audit directory; content-hash idempotency and
the differing-content refusal are unchanged per artifact. `QAAgent._report_scope`'s AUTO-005
per-attempt derived-identifier workaround is removed, so each QA round's report now lives beside
that workflow's own audit log instead of in a sibling directory. `SKILL_CONTRACTS.md` §6 records
the contract change (Version 1.3); rationale in `DECISIONS.md` DD-40; the remaining caller-side
round-numbering question is `OPEN_QUESTIONS.md` OD-12. Implemented and validated; stopped for
Human Owner approval before any commit.

## 2026-07-30 — AUTO-008 registered and authorized

The Human Owner registered and authorized AUTO-008 — Engine CI baseline — in one act, following an
architectural audit which found the AUTO-001..007 engine substantially complete but verified by no
automated gate and unable to run as a program. Registry state `AUTHORIZED`; implementation,
approval, push, and merge remain separate.

## 2026-07-30 — AUTO-008 approved and closed

The Human Owner approved AUTO-008 after a required scope-and-cleanliness verification (which caught
two self-inflicted defects, both corrected before commit) and authorized closure. The engine is now
verified by CI: all three suites run under one `pytest` invocation (1,160 -> 2,967 tests, all
passing), `mypy --strict` covers all three packages, the wheel ships all three, and the
`MVP_SCOPE.md` §4 end-to-end dry run passes with no test-only production workarounds. OD-10 and
OD-11 resolved; `agentos_workflow` carries its own version. Registry state `COMPLETE`; task status
`Done`. F-1 and F-2 recorded as follow-up work.

## 2026-07-30 — GOV-AUTO-06 approved and closed

The eight Git/GitHub Skills delivered by AUTO-006 are bound in `default_skill_registry()`; they had
remained classified as undelivered after that stage shipped, leaving `GitAgent` and `MergeAgent`
unable to invoke their own contracted Skills through the production registry. Capability contracts
are unchanged and a negative test proves no Agent gained reach. Resolves AUTO-008's F-2 finding.
F-1 remains open.
