# Changelog

All notable changes to `ai-workflow-engine` are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); this project does not yet follow a formal
release-versioning cadence beyond the milestone numbering in `docs/milestones.md`.

## [Unreleased]

### Added
- GOV-2 (2026-07-29): implemented, Human-Owner-approved, and closed
  `Current -> Done` in one local commit via scripts/workflow-approve.sh's automatic
  task closeout (GOV-AUTO-03).
- GOV-2 (2026-07-29): explicitly authorized by the Human Owner through the local
  two-confirmation task gate; authorization commit and implementation remain separate.
- AUTO-007 (2026-07-29): implemented, Human-Owner-approved, and closed
  `Current -> Done` in one local commit via scripts/workflow-approve.sh's automatic
  task closeout (GOV-AUTO-03).
- AUTO-007 (2026-07-28, implementation): built the stage's own test-authoring deliverables — no
  production code changed — under `agentos_workflow/tests/e2e/**` and
  `agentos_workflow/tests/recovery/**`: the interruption/resume drift matrix "at each state"
  (`TEST_STRATEGY.md` §4a, all 8 states `WORKFLOW_STATES.md` §3 names), the initial-execution
  retry/reconciliation matrix (§4b, all 4 applicable states), a dedicated test per
  `SECURITY_MODEL.md` rule (§4), and the full `CREATED → DONE` end-to-end dry run against a real
  disposable Git repository with `MockProvider` and a faked `gh` (§5, `MVP_SCOPE.md` §4's
  acceptance demonstration), exercising one repair cycle, one interruption/resume cycle, and the
  full commit → push → PR → auto-merge → checks-wait → merge → closeout path. The dry run
  surfaced two genuine, previously undetected production defects, neither fixed here (outside
  this stage's allowed files): a `stage_contract_hash` format disagreement between `PMOAgent` and
  the live resume observer (new OD-11, `docs/workflow-automation/DECISIONS.md` DD-39), and
  empirical confirmation of the existing OD-10 `allowed_environment_variables` gap. 59 new tests;
  `agentos_workflow` suite 1,557-green (up from 1,498); engine collection unchanged at 1,092. This
  stage's own contract requires a mandatory independent, fresh-session security review before it
  may reach `COMPLETE`; that review has not been performed, so registry state remains
  `IN_PROGRESS`, stopped for Human Owner approval; no commit, push, merge, or further work was
  performed. Report: `docs/reports/workflow-automation/AUTO-007-completion-report.md`.
- AUTO-007 (2026-07-28): explicitly authorized by the Human Owner through the local
  two-confirmation task gate; authorization commit and implementation remain separate.
- GOV-AUTO-03 (2026-07-28): implemented, Human-Owner-approved, and closed
  `Current -> Done` in one local commit via scripts/workflow-approve.sh's automatic
  task closeout (GOV-AUTO-03).
- GOV-AUTO-03 (2026-07-28): authorized by the Human Owner as a governance and developer-experience
  task ("I authorize one new governance and developer-experience task: GOV-AUTO-03 — Human-Approved
  Commit with Automatic Task Closeout"). Extends `scripts/workflow-approve.sh` so that, after the
  same two exact `APPROVE` confirmations, it identifies the single `Current` task, verifies the
  task-queue/mirror/registry/report/commit-message evidence corresponds to it, performs a
  fail-closed deterministic governance closeout (task queue, mirrors, project state, decision log,
  changelog, stage registry where applicable, program changelog where applicable, completion-report
  addendum, handover, checksum) using `awk`-guarded precondition-checked replacements, re-runs
  `task-state`/`governance`/`handover` validation, and creates exactly one local commit containing
  the approved implementation and the generated closeout records together — never a separate
  closure commit. Gated on the `project.id: ai-workflow-engine` marker `workflow-authorize.sh`
  already uses, so every other repository (including the pre-existing test sandboxes) keeps the
  unchanged GOV-AUTO-01 plain approval/commit gate. A pre-closeout backup restores every generated
  governance file verbatim on failure, leaving the approved implementation untouched; the script
  never pushes, merges, changes branches, alters upstream, mutates stashes, or authorizes a
  successor. 26 new tests in `tests/test_workflow_approve_closeout.py`; the pre-existing
  GOV-AUTO-01/02 suites (88 tests) pass unmodified. Implementation complete and validated; stopped
  for Human Owner approval before any commit. Report:
  `docs/reports/GOV-AUTO-03-completion-report.md`.
- AUTO-006 (2026-07-28): explicitly authorized by the Human Owner through the local
  two-confirmation task gate, then implemented — the eight Git/GitHub Skills of
  `SKILL_CONTRACTS.md` §5 (`agentos_workflow/skills/git_github.py`): `create_commit`,
  `push_stage_branch`, `create_pull_request`, `read_pull_request_state`, `verify_head_sha`,
  `read_required_checks`, `enable_automatic_squash_merge`, `verify_merge_completion`. These bind
  the eight Skill names `GitAgent`/`MergeAgent` (AUTO-005) already called against fakes with the
  identical keyword shapes; no Agent code changed. `enable_automatic_squash_merge` has exactly
  one `gh pr merge` call site (`--auto --squash`, never `--admin`), and no `gh` invocation ever
  carries a `--repo` flag, so no Skill can be redirected at an arbitrary GitHub repository. OD-1
  resolved in favor of native GitHub auto-merge. 33 new tests: real temporary Git repositories
  for the local Skills, `gh` mocked at the process boundary (a fake executable on `PATH`) for the
  GitHub-facing ones. `agentos_workflow` suite 1,498-green (up from 1,465); engine collection
  unchanged at 1,066. Self-review found, and recorded without fixing, that five of the eight
  Skill calls in AUTO-005's Agent code never forward `allowed_environment_variables`, so `gh`
  cannot authenticate in a real deployment until a future stage adds it
  (`docs/workflow-automation/DECISIONS.md` DD-38, `OPEN_QUESTIONS.md` OD-10). Implementation
  complete and validated; stopped for Human Owner approval before any commit. Report:
  `docs/reports/workflow-automation/AUTO-006-completion-report.md`.
- GOV-AUTO-02 (2026-07-28): `scripts/workflow-authorize.sh <TASK_ID> [claude|codex]`, a local
  two-confirmation Human authorization gate. It validates an explicitly named planned/ready task,
  clean default-branch baseline, single-Current invariant, structured program predecessor and
  owner-decision gates, and repository governance/handoff state; displays the exact transition;
  requires `AUTHORIZE` twice; updates the authoritative mirrors, relevant stage registry,
  changelogs, handoff, and checksum; then creates one governance-only local authorization commit.
  Optional launch delegates to `workflow-next.sh` only after that commit and a clean-tree check.
  It never selects a task, closes a predecessor, implements, pushes, merges, changes branch/
  upstream, or mutates stashes. 29 focused disposable-repository tests cover input/state/Human
  gates, mirror/checksum/commit behavior, runner modes and status propagation, remote/stash
  integrity, validation refusal, and post-staging index recovery. Implemented, validated,
  approved by the Human Owner, and committed as
  `d212e4d2dae2cd0a3510c54d7cd098fdfd5da548`. Report:
  `docs/reports/GOV-AUTO-02-completion-report.md`.
- GOV-3 (2026-07-28): recorded as `Planned` future work by Human Owner decision — the Reporting
  Skills write one artifact per workflow identifier per kind, but a bounded repair loop produces
  several genuinely different QA and stage reports per workflow. AUTO-005 works around it with a
  per-attempt audit scope; the fix is an attempt-aware artifact name, which requires its own fresh
  authorization. Not an AUTO-005 blocker.
- AUTO-005 (2026-07-28): the six AgentOS Workflow Automation Agents in `agentos_workflow/agents/`
  — `PMOAgent`, `ImplementationAgent`, `QAAgent`, `GitAgent`, `MergeAgent`, and `CloseoutAgent`
  (`AGENT_CONTRACTS.md` §2-7). Each is bounded to the Skills and Provider roles its own contract
  lists by a capability broker that refuses everything else, and no Agent module imports a Skill
  family or a Provider implementation at all, so the boundary is structural rather than a
  convention. No result type in the package carries a workflow state: Agents report, and the
  Orchestrator decides every transition. The `VALIDATING` gate and the bounded repair loop are
  Orchestrator-owned sequences, not a seventh Agent — the repair loop re-runs *all* deterministic
  validation and independent QA in full after every attempt, feeds each attempt the latest failure
  report rather than a stale one, and stops hard at the configured attempt limit. `MergeAgent`
  verifies the pull request's head SHA before, not after, enabling the merge, and has no
  admin-bypass path in its executable code; `CloseoutAgent` cannot be asked to delete a branch
  without an independently produced merge confirmation, and restores the baseline before any
  deletion. The eight GitHub-facing Skills AUTO-006 delivers are named but deliberately unbound,
  so reaching for one fails as `SKILL_UNAVAILABLE` naming AUTO-006 rather than returning a
  fabricated success. 133 new tests; engine collection provably unchanged at 1,037. No
  dependencies added and no existing runtime module modified. Approved by the Human Owner on
  2026-07-28, who accepted the documented limitations and authorized exactly one local commit;
  push and merge were explicitly withheld. Report:
  `docs/reports/workflow-automation/AUTO-005-completion-report.md`.
- AUTO-004 (2026-07-28): the AgentOS Workflow Automation Model Provider layer in
  `agentos_workflow/providers/` — the common `Provider` interface, `ClaudeCLIProvider`
  (implementation and repair) and `CodexCLIProvider` (independent QA) as subprocess adapters over
  each target repository's own configured executable and timeout, and `MockProvider` for offline
  tests and dry runs. Nothing in the package raises to the Orchestrator; every failure is typed,
  and retry classification turns on *when* a failure occurred, never what kind it was. Prompts
  travel on stdin rather than argv, only allowlisted environment variables reach a provider
  process, each invocation runs in its own `0o700` session directory, and every string leaving the
  package is redacted. `MockProvider` is structurally unable to be selected for a real authorized
  workflow. 106 new tests, with the process boundary mocked by executable substitution so no
  Claude or Codex CLI is needed; default `pytest` collection unchanged at 1,037. No dependencies
  added and no existing runtime module modified. Implemented and validated, pending Human Owner
  approval; not committed. Report:
  `docs/reports/workflow-automation/AUTO-004-completion-report.md`.
- GOV-AUTO-01 (2026-07-27): a local, Human-gated task runner for the repository's standard task
  cycle — `scripts/workflow-next.sh` (read-only preflight, then exactly one agent session with the
  canonical prompt), `scripts/prompts/implement-next-task.md`, `scripts/workflow-approve.sh` (the
  Human approval gate and the only path that creates a commit), and `docs/automation-workflow.md`.
  It automates the mechanical steps **without replacing the Human Owner approval gate**: neither
  script pushes, merges, changes branches, alters upstream, or mutates stashes; a dirty worktree
  blocks starting a task, an empty worktree blocks approval, unknown agent arguments fail closed,
  `eval` is never used, and a commit requires two separate exact-`APPROVE` confirmations plus a
  displayed-and-confirmed file list (never `git add -A`). 59 tests in
  `tests/test_workflow_runner_scripts.py` against disposable temporary repositories; `bash -n` and
  `shellcheck` clean. No dependencies added. Implemented and validated, pending Human Owner
  approval; not committed.

### Changed
- AUTO-006 (2026-07-28): approved by the Human Owner, closed `Current → Done` / registry
  `IN_PROGRESS → COMPLETE`, and published — committed locally as `d8d356d`, pushed as
  `feature/auto-006-pr-merge-closeout`, and merged into `main`, which now carries
  `agentos_workflow/skills/git_github.py`. The stage branch was retained and both pre-existing
  stashes left untouched. The two documented limitations (Orchestrator wiring of the Merge Safety
  Gate / Checks-Wait Gate not performed; the `allowed_environment_variables` gap on five `gh`-based
  Skill calls, OD-10) were explicitly accepted rather than fixed in scope. The stage completion
  report was **not** rewritten: the commit post-dates it, so the commit, approval, and merge are
  recorded in a new append-only addendum to that report, a new
  `docs/workflow-automation/STAGE_REGISTRY.md` §5 row, and `docs/DECISION_LOG.md`. This closure
  authorizes no successor — AUTO-007 and GOV-AUTO-03 remain unauthorized.
- GOV-AUTO-02 (2026-07-28): closed `Current → Done` by explicit Human Owner decision, recording
  that it was implemented, validated, approved, and committed as
  `d212e4d2dae2cd0a3510c54d7cd098fdfd5da548`. No task is now `Current`. The governance-only
  closure authorizes no push, merge, successor, or work on AUTO-006, which remains `Planned` and
  explicitly unauthorized.
- AUTO-005 (2026-07-28): approved by the Human Owner, closed `Current → Done` / registry
  `IN_PROGRESS → COMPLETE`, and published — committed locally as `430cbb4`, pushed as
  `feature/auto-005-agents`, and merged into `main`, which now carries `agentos_workflow/agents/`.
  The stage branch was retained and both pre-existing stashes left untouched. All five documented
  limitations were explicitly accepted for this stage; the QA report artifact collision was
  recorded as future work (GOV-3) rather than fixed in scope, so
  `agentos_workflow/skills/reporting.py` is byte-unchanged. The stage completion report was **not**
  rewritten: it was finished before the commit existed and names no hash, so the hash, closure, and
  merge are recorded in a new append-only addendum to it plus
  `docs/workflow-automation/STAGE_REGISTRY.md` §5 and `docs/DECISION_LOG.md`. This closure
  authorizes no successor — AUTO-006 remains explicitly unauthorized.
- AUTO-004 (2026-07-28): approved by the Human Owner, closed `Current → Done` / registry
  `IN_PROGRESS → COMPLETE`, and published — committed locally as `84616d5`, pushed as
  `feature/auto-004-model-providers`, and merged into `main`, which now carries
  `agentos_workflow/providers/`. The stage branch was retained and both pre-existing stashes left
  untouched. The stage completion report was **not** rewritten: its "no commit was performed"
  Confirmation was accurate when written, and the later commit, approval, and merge are recorded
  in a new append-only addendum to it plus `docs/workflow-automation/STAGE_REGISTRY.md` §5 and
  `docs/DECISION_LOG.md`.
- GOV-AUTO-01 (2026-07-28): closed `Current → Done` by explicit Human Owner decision, recording
  that it was implemented, validated, approved, committed as `a302c95`, and merged into `main` via
  `a3b5b0a`. The closeout bookkeeping had lagged the merge — `main` already carried the work while
  the task queue, both mirrors, and the handover still showed it `Current` and uncommitted. The
  same decision resolved the resulting `maximum_current_tasks: 1` conflict and authorized AUTO-004
  as the single `Current` task (`docs/DECISION_LOG.md`, 2026-07-28).
- AUTO-003 (2026-07-27): implemented, approved by the Human Owner, and committed locally as
  `908be94` (push and merge explicitly withheld). Delivered the deterministic Repository, Contract,
  Validation, and Reporting Skill families in `agentos_workflow/skills/`; resolved OD-2 (DD-33) and
  recorded DD-34/DD-35. Closed to `Done` when the Human Owner authorized GOV-AUTO-01 as the single
  active task.
- AUTO-002 (2026-07-27): completed the AgentOS Workflow Automation orchestrator/state-machine
  foundation and its approved security remediation. After the configured validation gates
  passed, the Human Owner accepted AUTO-002 for closure without another independent review and
  authorized one local Conventional Commit. AUTO-002 is `Done`; AUTO-003 remains `Planned` and
  separately authorization-gated. No push or merge is authorized.
- Governance recovery (2026-07-24): fixed a real OD-9 retry-classification defect —
  `SKILL_CONTRACTS.md`/`MODEL_PROVIDER_CONTRACTS.md` had classified retryability by error *type*
  (timeout/reset/DNS-failure = retryable), when the approved policy requires classifying by
  *timing* (a timeout is never, by itself, proof no side effect occurred); corrected to classify
  strictly by whether the underlying operation was ever actually invoked (`SKILL_CONTRACTS.md` →
  1.2, `MODEL_PROVIDER_CONTRACTS.md` → 1.2, `WORKFLOW_STATES.md` §5a item 1 tightened → 4.1);
  appended the missing `docs/agentos-dashboard/CHANGELOG.md` entry for its own 4.0 → 5.0
  transition (OD-8 mirror), without touching existing entries; and rewrote every live AUTO-002
  branch-blocker description to state the settled release procedure (this recovery branch is
  reviewed/committed/pushed/merged/deleted through the ordinary process, never renamed into the
  AUTO-002 branch) rather than presenting it as an open choice. No policy, lifecycle state, or
  AUTO-002 implementation changed. Full record: `docs/DECISION_LOG.md`.
- Human Owner policy decisions applied (2026-07-24): OD-8 (`SUPERSEDED` maps to task status
  `Done`, administratively closed, never successful completion; legal source states
  `AUTHORIZED`/`BLOCKED`/`IN_PROGRESS`/`SELF_REVIEW`/`REVIEW`/`APPROVAL`; never automatic
  successor authorization; no fourth task status — `STAGE_REGISTRY.md` → 6.0, Dashboard
  registry → 5.0, `DECISIONS.md` DD-08) and OD-9 (initial-execution failure policy for the
  implementation-provider invocation and `create_commit`/`push_stage_branch`/
  `create_pull_request`: bounded same-state retry, then reconciliation, then advance/`REPAIRING`
  (`IMPLEMENTING` only)/`FAILED`, per new `WORKFLOW_STATES.md` §5a — no new state or transition,
  only new reasons on existing edges — `WORKFLOW_STATES.md` → 4.0, `DECISIONS.md` DD-09, with
  consistency updates to `MACHINE_GATES.md`, `FAILURE_RECOVERY.md`, `AGENT_CONTRACTS.md`,
  `SKILL_CONTRACTS.md`, `MODEL_PROVIDER_CONTRACTS.md`, `TEST_STRATEGY.md`). Both approvals
  recorded verbatim; both `OPEN_QUESTIONS.md` entries moved Open → Resolved (→ 1.3). Full record:
  `docs/DECISION_LOG.md`.
- Governance recovery (2026-07-24, twelfth pass): synchronized the Dashboard lifecycle with its
  existing substantive-equivalence promise by adding a zero-transition Resume Preflight
  restatement (`docs/agentos-dashboard/STAGE_REGISTRY.md` → 4.0; Dashboard SSP → 1.3), corrected
  the Dashboard/AUTO rule-number crosswalk, clarified that the runtime's six named machine gates
  include one Precondition gate spanning two transition-source states
  (`WORKFLOW_STATES.md` → 3.2), and corrected the handover's "unpushed ref" wording to distinguish
  the sole no-upstream branch from two retained local stash snapshots. Recorded, without
  resolving, two Human Owner design questions: `SUPERSEDED` task-status semantics (OD-8) and
  initial-execution provider/commit/push/PR failure policy (OD-9;
  `OPEN_QUESTIONS.md` → 1.2). No lifecycle state, runtime transition, authorization, task status,
  release behavior, stash, or AUTO-002 implementation changed (`docs/DECISION_LOG.md`).
- AUTO-001 (2026-07-24): flipped from `Current` to `Done` in `docs/TASK_QUEUE.md` and its
  mirrors — its PR (#3, `191f600`) had already merged into `main`; this is the formal closeout
  step. AUTO-002 enrolled as the sole `Current` task, authorized by the Human Owner
  ("I authorize AUTO-002."), but its execution-precondition check found the working branch
  (`feature/auto-002-orchestrator-foundation`) does not match the canonical branch
  (`feature/auto-002-orchestrator-state-machine`); no AUTO-002 implementation was started
  (`docs/DECISION_LOG.md`).
- Governance recovery (2026-07-24, two passes): corrected a mis-cited authority for the AUTO-002
  branch block in every document that repeated it (`docs/current_task.md`, `docs/TASK_QUEUE.md`,
  `docs/PROJECT_STATE.md`, `docs/workflow-automation/STAGE_REGISTRY.md` §5, and the original
  `docs/DECISION_LOG.md` entry itself) and a non-canonical `STAGE_REGISTRY.md` state value
  (`AUTHORIZED (blocked — …)` → `BLOCKED`). Made the governance boundary explicit rather than
  implied: `docs/workflow-automation/STAGE_REGISTRY.md` (+ the SSP) is now stated as the
  exclusive authority for the AUTO-00x stage lifecycle, `HUMAN_AUTHORIZATION_MODEL.md`/
  `WORKFLOW_STATES.md` as scoped only to the future runtime engine, a new `STAGE_REGISTRY.md` §3
  rule 17 states that a failed execution precondition never invalidates a recorded authorization
  and moves a stage to `BLOCKED` (≈ task status `Current`, now named explicitly in §2's mapping)
  instead, and `stage-prompts/AUTO-002.md` now separates authorization preconditions from
  execution preconditions. No lifecycle transition changed; no AUTO-002 implementation performed
  (`docs/DECISION_LOG.md`).
- Governance recovery (2026-07-24, third pass): disambiguated OD-3/OD-4 in
  `docs/workflow-automation/OPEN_QUESTIONS.md` (authorization-gating "blocks" vs.
  implementation-time "affects"); clarified `STAGE_REGISTRY.md` rule 16's `workflowctl verify`
  tolerance at closeout; completed the `BLOCKED` lifecycle (later refined in the fourth pass
  below to `BLOCKED → AUTHORIZED → IN_PROGRESS`, or `BLOCKED → SUPERSEDED`, never back to
  `NOT_STARTED`/`PROPOSED`); fixed a retired
  "authorization-binding" phrase left in `docs/remaining_tasks.md`; corrected
  `docs/PROJECT_STATE.md`'s self-contradicting "Blockers" section, which claimed no blocker
  existed and described stale Git history (`main` is in fact identical to `origin/main`, both PRs
  merged and pushed); and rewrote the stale (though checksum-valid) `handover/PROJECT_HANDOVER.md`
  in full, regenerating `handover/PROJECT_CHECKSUM.md` to match. No lifecycle transition changed;
  no AUTO-002 implementation performed (`docs/DECISION_LOG.md`).
- Governance recovery (2026-07-24, fourth pass): redefined rule 1's "clean tree" (the
  predecessor-closeout/successor-enrollment edit that authorizes a stage is the sanctioned
  trigger, not a violation — verified against `git status` evidence at every point in this
  recovery); fixed a `BLOCKED`/SSP deadlock the third pass's rule 17 had introduced, by routing
  `BLOCKED → AUTHORIZED → IN_PROGRESS` instead of straight to `IN_PROGRESS`; rewrote rule 8 to
  distinguish frozen completion records (§4/§5, reports, `docs/DECISION_LOG.md` — corrected only
  via a new rule-18 Governance Correction Record, never in place) from versioned living reference
  documents (this registry, `HUMAN_AUTHORIZATION_MODEL.md`, `WORKFLOW_STATES.md`, the SSP,
  `stage-prompts/*.md`, `OPEN_QUESTIONS.md` — amendable in place with a version bump); and
  declared `docs/DECISION_LOG.md` itself explicitly append-only, disclosing that the two prior
  passes had edited entries in place before that rule was explicit
  (`STAGE_REGISTRY.md` → 3.0; `stage-prompts/README.md` → 1.2). No lifecycle transition changed;
  no AUTO-002 implementation performed (`docs/DECISION_LOG.md`).
- Governance recovery (2026-07-24, fifth pass): revised rule 16 (no successor is *automatically*
  selected at closeout, but an explicit Human Owner directive covering both a predecessor's
  closeout and a successor's authorization in one session — as happened twice, DASH-001→AUTO-001
  and AUTO-001→AUTO-002 — satisfies rather than violates it) instead of invalidating either
  historical authorization; audited every stage registry repository-wide and fixed
  `docs/agentos-dashboard/STAGE_REGISTRY.md`'s stale DASH-001 `IN_PROGRESS` (actually `Done` since
  2026-07-23) plus its drift from the AUTO registry's already-fixed rules, and appended a
  correction entry to `docs/agentos-dashboard/CHANGELOG.md`; added three failure transitions
  (`AUTHORIZED`/`PRECONDITIONS_CHECKED`/`PR_OPEN` → `FAILED`) to `WORKFLOW_STATES.md` §3 that
  `MACHINE_GATES.md` required but which were absent from the transition table; and completed
  rule 1's "clean tree" artifact list, which had itself omitted this registry's own §4/§5 and the
  program-level changelog. `docs/implementation/orchestration/migration-registry.yaml` was
  checked and confirmed out of scope (frozen ORCH-00x evidence, SSP-forbidden to modify).
  `STAGE_REGISTRY.md` → 4.0; `docs/agentos-dashboard/STAGE_REGISTRY.md` → 2.0;
  `WORKFLOW_STATES.md` → 1.2. No lifecycle transition changed; no AUTO-002 implementation
  performed (`docs/DECISION_LOG.md`).
- Governance recovery (2026-07-24, seventh pass): fixed a real gap in
  `docs/agentos-dashboard/STAGE_REGISTRY.md` rule 17 (was missing AUTO's `git`-check closeout
  tolerance) and narrowed its overstated "identical in substance" claim to a precise shared/
  program-specific rule list (→ 3.0); fixed stale "AUTO-002 authorization requires..." wording in
  `docs/workflow-automation/STAGE_REGISTRY.md` §7 to state the already-satisfied fact plainly;
  **eliminated formatter non-determinism at its root** by removing the redundant `ruff-format`
  pre-commit hook (this repository's own SSP validation commands never included it — `black` is
  the actual canonical formatter) and re-pinning `.pre-commit-config.yaml` to the exact installed
  tool versions (`ruff-pre-commit` → v0.15.21, `black-pre-commit-mirror` → 25.12.0,
  `mirrors-mypy` → v1.20.2); verified `pre-commit run --all-files` idempotent across two
  consecutive runs (zero file changes either time). Assessed extending `check-governance` to
  validate registry/lifecycle consistency and confirmed it needs new code, not config — tracked
  as `GOV-2` (`Planned`) rather than implemented in this session. Full record:
  `docs/DECISION_LOG.md`.
- `docs/workflow-automation/WORKFLOW_STATES.md` (2026-07-24): Human Owner explicitly reviewed and
  approved the three `FAILED` transitions added in the prior pass (`AUTHORIZED`,
  `PRECONDITIONS_CHECKED`, `PR_OPEN` → `FAILED`) as a MAJOR change under the document's own §11
  revision policy; version bumped 1.2 → **2.0**. This approval does not authorize AUTO-002
  implementation or any release action. Full record: `docs/DECISION_LOG.md`.
- Governance recovery (2026-07-24, eighth pass): fixed `tests/test_migration_plan_apply.py` so
  `ruff format --check .` and `black --check .` fully agree (extracted a long assert message to
  a local variable, eliminating the line-wrap disagreement); audited every mention of
  `check-governance`/`check-task-state` for overclaiming registry/lifecycle coverage and found
  none. Full record: `docs/DECISION_LOG.md`.
- `docs/workflow-automation/WORKFLOW_STATES.md` (2026-07-24): Human Owner explicitly reviewed and
  approved eight further `FAILED` transitions (`BRANCH_CREATED`, `IMPLEMENTING`, `REPAIRING`,
  `READY_TO_COMMIT`, `COMMITTED`, `PUSHED`, `AUTO_MERGE_ENABLED`, `MERGED` → `FAILED`) as a
  separate MAJOR change under §11, completing the failure-transition model so every state
  `TEST_STRATEGY.md` §4a requires interruption/drift testing at now has a legal transition;
  version bumped 2.0 → **3.0** (not reusing the prior MAJOR bump's version number, per explicit
  instruction). Consistency updates to `MACHINE_GATES.md` (→ 1.1), `FAILURE_RECOVERY.md`
  (→ 1.1), `TEST_STRATEGY.md` (→ 1.1), and `AGENT_CONTRACTS.md` (→ 1.1) so no document contradicts
  the completed table. This approval does not authorize AUTO-002 implementation or any release
  action. Full record: `docs/DECISION_LOG.md`.
- Governance recovery (2026-07-24, tenth pass): resynchronized
  `docs/agentos-dashboard/stage-prompts/README.md` with the actual current pre-commit toolchain
  (named the real hooks — `ruff-check --fix`, `black`, `mypy`, no `ruff-format` — in actual order,
  and added `ruff format --check .` to its recorded validation commands, → 1.2); closed a
  Dashboard changelog completeness gap by appending three missing entries documenting already-
  approved revisions (`STAGE_REGISTRY.md` 2.0 → 3.0, `stage-prompts/README.md` 1.0 → 1.1 and
  1.1 → 1.2) without touching the existing entries. No repository policy changed. Full record:
  `docs/DECISION_LOG.md`.
- Governance recovery (2026-07-24, eleventh pass): separated the SSP's initial-start preflight
  from a new resume preflight (`STAGE_REGISTRY.md` new rule 19, → 5.0; SSP restructured, → 1.3;
  `stage-prompts/AUTO-002.md` → 1.2) so resuming an already-`IN_PROGRESS` stage no longer requires
  impossibly returning to `AUTHORIZED` — zero new transitions, both resume outcomes leave the
  registry state unchanged; mirrored `GOV-2` into `docs/PROJECT_STATE.md` and
  `handover/PROJECT_HANDOVER.md`, which had omitted it; rewrote every live description of
  AUTO-002's branch blocker as a durable, branch-name-independent rule
  (`docs/PROJECT_STATE.md`, `docs/TASK_QUEUE.md`, `docs/current_task.md`,
  `docs/remaining_tasks.md`, `handover/PROJECT_HANDOVER.md`,
  `docs/workflow-automation/STAGE_REGISTRY.md` §7) without touching the append-only §5 log rows
  that correctly record the original, branch-specific discovery. Full record:
  `docs/DECISION_LOG.md`.

### Added
- AUTO-001 (2026-07-23): AgentOS Workflow Automation architecture and governance foundation —
  the complete documentation set under `docs/workflow-automation/` (README, architecture,
  workflow-state, agent/skill/model-provider contracts, human-authorization model, machine
  gates, security model, failure recovery, audit model, configuration model, target-repository
  model, CLI spec, MVP scope, stage registry, test strategy, decisions, open questions,
  changelog, stage report template) plus `stage-prompts/AUTO-001..AUTO-007.md`. Program
  enrollment in `docs/TASK_QUEUE.md` and its mirrors (AUTO-001 `Current`, AUTO-002..007
  `Planned`); DASH-001 formally closed to `Done` as a precondition (see `docs/DECISION_LOG.md`).
  Documentation-and-architecture-only; no engine, test, or dependency change.

- DASH-001 (2026-07-23): AgentOS Dashboard program planning foundation — the complete
  documentation set under `docs/agentos-dashboard/` (master plan, architecture, product spec,
  security model, source-of-truth rules, data model, API/UI specs, MVP scope, test strategy,
  stage registry, stage prompts, program decisions/questions/changelog) plus program enrollment
  in `docs/TASK_QUEUE.md` and its mirrors, and the enrollment decision in
  `docs/DECISION_LOG.md`. Documentation-only; no engine, test, or dependency change. Recovered
  and re-executed correctly for this repository after a mis-targeted first execution
  (`docs/agentos-dashboard/DECISIONS.md` DD-03;
  `docs/reports/agentos-dashboard/DASH-001-recovery-report.md`).

### Changed
- DASH-001 (2026-07-23): flipped from `Current` to `Done` in `docs/TASK_QUEUE.md` and its
  mirrors — its PR (#1, `5f82996`) had already merged into `main`; this is the formal closeout
  step, done as an AUTO-001 precondition (`docs/DECISION_LOG.md`).

## [1.0.0] — 2026-07-18 — Roadmap complete

Version 1.0.0: all four milestones of `docs/milestones.md` are implemented, validated, and
governance-reviewed. Completion report: `docs/FINAL_COMPLETION_REPORT.md`.

### Fixed
- T-501 (2026-07-18): the `version` governance-fact regex in `self-governance.yaml` (and
  `examples/amozesh_konkur.yaml`) widened from `0\.\d+\.\d+` to `\d+\.\d+\.\d+`, so the fact
  extracts a `1.x`+ version; without this the 1.0.0 bump would have made `check-governance` FAIL.

### Changed
- T-501 (2026-07-18): version bumped to 1.0.0 (`pyproject.toml`, `__init__.py`,
  `docs/PROJECT_STATE.md`). The `WorkflowSettings` auto-flag validator message reworded from the
  now-stale "Milestone 1 forbids…" to state the permanent invariant (config-level automatic
  commit/push are always forbidden; use the approval-gated Milestone 4 commands). Behavior
  unchanged.

## [0.3.0] — 2026-07-18 — Milestone 4

Milestone 4 (controlled commit and push), released as v0.3.0. Every task (T-401..T-404) passed an
independent review; the plan review took two rounds (five blocking findings remediated).
Demonstration: `docs/MILESTONE_4_VALIDATION.md`.

### Added
- T-401 (2026-07-18): `docs/milestone-4-plan.md` — the normative Milestone 4 plan.
- T-402 (2026-07-18): the writable-Git surface and commit gate — `git/writer.py`
  (typed-methods-only `GitWriter` + `GitWriteError`), six read-only `GitClient` gate helpers
  (`READ_ONLY_FORMS` byte-unchanged), `git/approval.py` (`CommitApproval`/`PushApproval` +
  loaders), `commit/gates.py` (`run_commit_gate`), and `workflowctl commit`.
- T-403 (2026-07-18): `run_push_gate` + `run_apply_patch_gate` and the `workflowctl push` /
  `apply-patch` commands. The push gate mechanically applies the Milestone 2 push algorithm;
  apply-patch writes a verified Milestone 3 patch to the working tree only.
- T-404 (2026-07-18): Milestone 4 closeout — version 0.3.0, `docs/MILESTONE_4_VALIDATION.md`, and
  README/architecture updates for the commit/push/apply-patch surfaces.

Refusal-by-default throughout: no commit or push without a matching per-invocation human approval
artifact, and every gate failure writes nothing. `allow_automatic_commit`/`allow_automatic_push`
remain hard-false.

## [0.2.0] — 2026-07-18 — Milestone 3

Milestone 3 (non-interactive agent execution) plus the Stage-0 work that preceded it, released
as v0.2.0. Every task (Stage 0 T-101..T-104; Milestone 3 T-301..T-306) passed an independent
fresh review. Full-cycle demonstration and the lying-agent detection evidence:
`docs/MILESTONE_3_VALIDATION.md`.

### Added
- `docs/IMPLEMENTATION_GAP_ANALYSIS.md` — full fresh-session audit of implementation vs.
  documentation (2026-07-17); repository verified healthy (448 tests, lint/type clean,
  self-governance verify PASS).
- `docs/MASTER_ROADMAP.md` — human-approved (2026-07-17) roadmap to version 1.0.0: Stage 0
  closeout/sync/CI, Milestone 3 (T-301..T-306), Milestone 4 (T-401..T-404), release (T-501).
- GOV-1 closed via T-101; Stage 0 tasks T-102 (documentation sync) and T-103 (lightweight CI,
  human-approved addition) registered in the task queue.

- T-103 (2026-07-17): `.github/workflows/ci.yml` — lightweight CI running lint, format check,
  strict typing, the test suite, and the three repository-content governance checks on every
  push and pull request.
- T-301 (2026-07-17): `docs/milestone-3-plan.md` — the normative Milestone 3 architecture plan
  (event-sourced workflow state machine, agent config/report schemas, snapshot-sandbox runner,
  independent claim verification). Approved after two independent plan-review rounds (round 1
  REJECTED, remediated; round 2 APPROVED).
- T-302 (2026-07-18): `ai_workflow_engine.workflow` event-sourced state machine —
  append-only hash-chained `WorkflowEvent`s, the fixed transition table with verdict
  enforcement, collision-free tamper-evident storage (Milestone 2 atomic no-clobber protocol),
  next-stage computation, and the `workflowctl state show|next|record` CLI. Independent
  implementation review APPROVED. (First Milestone 3 implementation task.)
- T-303 (2026-07-18): `EngineConfig.agents` configuration section (per-agent name/executable/
  args/mode/timeout/stages, with mode-stage compatibility and `push` forbidden for any agent)
  and the strict `AgentReport`/`AgentFinding` output contract (`ai_workflow_engine.agents`).
  `WorkflowStage` moved to `ai_workflow_engine.models` (re-exported from `prompt.models`).

- T-304 (2026-07-18): `ai_workflow_engine.agents.sandbox` + `.runner` — throwaway sandbox
  clones with a sandbox-only `SandboxGit` surface, and the non-interactive `run_agent` execution
  protocol (clean-tree/HEAD precondition gate, hard timeout with process-group kill, scrubbed
  environment, before/after target-repository fingerprint, and the agent-output failure
  taxonomy). Observes the raw run facts (change set, patch, verification exit codes) for T-305;
  never writes the target repository. Independent implementation review APPROVED.
- T-305 (2026-07-18): `ai_workflow_engine.agents.verification` + `.artifacts` and the
  `workflowctl agent run` CLI — independent claim verification (`RunObservation` →
  `CheckResult`: claim equality, scope/protected-path containment, verification-command exit
  codes), tamper-evident content-addressed `AgentRunRecord` artifacts (base64 stdout/stderr with
  recomputable digests, `.patch` sidecar), and `state record --agent-run` evidence binding. A
  scoped-write agent's verified patch is stored, never applied (that is Milestone 4). Independent
  implementation review APPROVED.
- T-306 (2026-07-18): Milestone 3 closeout — version 0.2.0, `docs/MILESTONE_3_VALIDATION.md`, and
  README/architecture updates for the state + agent CLI surfaces.
- T-401 (2026-07-18): `docs/milestone-4-plan.md` — the normative Milestone 4 plan (typed
  `GitWriter`, approval artifacts, commit/push/apply-patch gates). Approved after two independent
  plan-review rounds (round 1 REJECTED with five blocking findings, remediated; round 2 APPROVED).
- T-402 (2026-07-18): the writable-Git surface and commit gate — `git/writer.py` (typed-methods-
  only `GitWriter` + `GitWriteError`), six read-only `GitClient` gate helpers (`READ_ONLY_FORMS`
  byte-unchanged), `git/approval.py` (`CommitApproval`/`PushApproval` + loaders), `commit/gates.py`
  (`run_commit_gate`), and `workflowctl commit`. Refusal-by-default; every FAIL/ERROR path writes
  nothing. First real-Git-write code; independent implementation review APPROVED.

### Changed
- T-303 (2026-07-18): **prompt-artifact schema bump 1.0 → 1.1.** The `agents` config section
  now enters the canonical prompt payload, so `PromptContext`/`PromptMetadata`/`PromptSuccess`
  are `schema_version` 1.1 and `workflowctl prompt` stored artifacts from before this change no
  longer load. Prompt **templates** (the seven byte-pinned bodies) are unchanged; only
  content-derived identity (`prompt_id`) shifts. Accepted, documented break (pre-1.0, local
  ephemeral artifacts) — see `docs/milestone-3-plan.md`.

### Fixed
- T-104 (2026-07-18): `workflowctl` machine-readable output (`--output json` for every
  check/verify/inspect, and `version`) no longer emits ANSI color codes when `FORCE_COLOR` is
  set in the environment, which had corrupted the stable 1.0 JSON contract into unparseable
  output. Machine output now bypasses Rich via a `_write_stdout` helper. Independent
  implementation review APPROVED.

### Changed
- T-102 (2026-07-17): `docs/milestone-2-plan.md` status line now records implemented/approved
  reality; `README.md` and `docs/architecture.md` extended to cover the Milestone 2 prompt
  subsystem and self-governance usage.
- `ai_workflow_engine.prompt` package: deterministic, canonically-hashed rendering, structural
  validation, and race-safe atomic storage of governed workflow prompts for all seven stages
  (`plan-review`, `implementation`, `implementation-review`, `remediation`,
  `governance-closeout`, `governance-review`, `push`).
- `workflowctl prompt <stage>` CLI commands, with `--output human|json` and `--store/--no-store`.
- `project.conda_environment` required configuration field (rejects empty/whitespace-only).
- Self-governance layer: `docs/PROJECT_STATE.md`, `docs/TASK_QUEUE.md`, `docs/current_task.md`,
  `docs/remaining_tasks.md`, `docs/CONTEXT.md`, `docs/DECISION_LOG.md`, `docs/CHANGELOG.md`,
  `docs/AGENT_PROTOCOL.md`, `handover/PROJECT_HANDOVER.md` + checksum manifest, and
  `self-governance.yaml`, so `workflowctl` can be pointed at this repository itself. See
  `docs/GOVERNANCE_AUDIT.md`.

### Fixed
- `workflowctl`'s `_protected` error path (used by every command, not just `prompt`) no longer
  corrupts or soft-wraps `ERROR: <message>` stderr output. Previously routed through Rich's
  `Console`, which interpreted bracketed substrings as markup/highlighting and soft-wrapped long
  messages at the console width — both violated the exact-bytes stderr contract. Now writes
  directly to `sys.stderr`.

### Process
- Milestone 2 passed three independent fresh implementation reviews (no reviewer had memory of
  a prior round's fixes) before approval, fixing two real defects and closing several
  test-coverage gaps (per-field prompt-identity sensitivity tests, genuine thread-based
  concurrency tests for the atomic store, a `load()` mixed-pair test, an expanded validator
  mutation matrix, byte-exact CLI golden tests).

## [0.1.0] — 2026-07-16 — Milestone 1

### Added
- Deterministic, read-only Git inspection (`GitClient`, `READ_ONLY_FORMS` allowlist).
- Governance mirror checking: task-state parsing from Markdown (`Current`/`Done`/`Planned`),
  configurable cross-document fact consistency checks.
- Handover integrity verification via a checksummed manifest, sourced from the working tree,
  Git index, or a specific commit.
- Protected-path enforcement (`never_stage`/`never_commit` glob patterns).
- Structured `CheckResult`/`VerificationReport` schema (`schema_version: "1.0"`), Rich console
  and JSON output.
- `workflowctl` CLI: `version`, `inspect`, `check-git`, `check-task-state`, `check-governance`,
  `check-handover`, `verify`.

## 2026-07-15 — Project initialization

### Added
- Repository scaffolding, packaging (`pyproject.toml`, `hatchling`), lint/type/format tooling
  (`ruff`, `black`, `mypy --strict` on `src`), `pre-commit` configuration.
