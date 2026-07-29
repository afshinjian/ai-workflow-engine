# AgentOS Workflow Automation — Decisions

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Decisions |
| **Purpose** | Append-only record of program-level decisions (DD-##). Subordinate to `docs/DECISION_LOG.md`; cross-posted there when repository governance requires. |
| **Status** | Draft |
| **Version** | 1.11 |
| **Owner** | Documentation & Governance session (append) · Human Owner (approval) |
| **Dependencies** | `README.md` |
| **Related Documents** | `docs/DECISION_LOG.md` |

## Format

Each entry: status, context, decision, consequences, reconsideration trigger. Entries are
appended, never rewritten; supersessions are explicit.

## DD-01 — Separate top-level package `agentos_workflow/`

- **Status:** Accepted.
- **Context:** The engine could live inside `src/ai_workflow_engine/` (this repository's
  audited engine package) or as a separate top-level package, mirroring the choice already made
  for `agentos_dashboard/` (DASH DD-01).
- **Decision:** A separate top-level package `agentos_workflow/`, so the audited engine
  package's strict lint/type/test gates and self-governance scope are never touched by AUTO
  work, and so AUTO-00x stages are ordinary `docs/TASK_QUEUE.md` tasks under the existing
  `check-task-state` discipline (same reasoning as DASH DD-01).
- **Consequences:** Zero risk to `src/ai_workflow_engine/`; AUTO tests live outside the engine
  suite's `testpaths`.
- **Reconsideration trigger:** none identified.

## DD-14 — AUTO-002 owns a local read-only resume observer and state/evidence policy

- **Status:** Accepted. Human Owner decisions, 2026-07-27, resolving AUTO002-F03.
- **Context:** AUTO-002 requires interruption resume to re-verify live authorization bindings,
  but its original scope excluded the repository/contract Skills planned for AUTO-003. The
  implementation instead trusted a caller-built `CurrentAuthorizationBinding`; copying fields
  from `authorization.json` could therefore resume without observing the repository. The
  contracts also said branch/worktree state must be checked "where expected" without defining
  expectations at every persisted state and crash boundary.
- **Decision:** AUTO-002 may add one typed local observation boundary used only for resume. It
  performs fixed-argv, allowlisted, read-only local Git queries plus confined contract/runtime
  observation. It has no arbitrary-command, mutation, network, GitHub, Provider, Agent, or
  general Skill surface and does not import `src/ai_workflow_engine/git/`. Production resume
  constructs it internally; test adapters return raw facts and never an authorization verdict.
  `WORKFLOW_STATES.md` §6a is the authoritative state/evidence matrix. Repository appearance
  never proves a possibly completed side effect: persisted attempt/reconciliation evidence is
  required. Workflow-owned, configuration-permitted `.agentos/**` control artifacts are
  classified separately; arbitrary content under that prefix is not ignored.
- **Allowed Git forms:** fixed equivalents of `rev-parse`, `symbolic-ref`, porcelain `status`,
  `config --get remote.<configured-name>.url`, `show-ref`, and
  `merge-base --is-ancestor`. All argv are arrays, repository location is explicit, return codes
  are validated, and no query performs network access.
- **Consequences:** `CurrentAuthorizationBinding` is retained only for lower-level compatibility;
  it is not authoritative in `WorkflowSession.resume`. AUTO-003 remains unauthorized and
  `NOT_STARTED`; no AUTO-003 Skill or mutation operation is implemented. The 19 states and 37
  legal edges are unchanged.
- **Acceptance:** live repository/path/identity, contract/path/hash, baseline/current/planned
  branch, HEAD/ancestry, classified working tree, runtime version, persisted attempts, and
  applicable reconciliation evidence must agree before resume returns. Every rejection releases
  its lock and records `FAILED` only on a legal edge.
- **Reconsideration trigger:** expansion beyond local read-only resume observation requires a
  separately authorized stage.

## DD-02 — Per-target-repository configuration at `.agentos/workflow.yaml`

- **Status:** Accepted (naming open — `OPEN_QUESTIONS.md` OD-5).
- **Context:** `self-governance.yaml` is this repository's own self-governance config, in a
  schema built for `ai-workflow-engine`'s own read-only inspection tooling; it is not a fit for
  per-target workflow-automation configuration, which needs CLI executables, timeouts, merge
  policy, and audit/state directories.
- **Decision:** A distinct configuration schema (`CONFIGURATION_MODEL.md`) at a
  target-repository-local conventional path, discovered per invocation, never assuming a
  target's shape matches this repository's own.
- **Consequences:** No coupling between AUTO's configuration and this repository's own
  governance schema; each can evolve independently.
- **Reconsideration trigger:** if a future stage needs to automate `ai-workflow-engine` itself
  as a target, this decision is revisited explicitly rather than silently reused.

## DD-03 — Claude = default implementation/repair provider; Codex = default QA provider; sessions isolated

- **Status:** Accepted.
- **Context:** The requesting Human Owner specified Claude as default implementation/repair and
  Codex as default independent QA. This repository's own Milestone 3 already established the
  principle "agent output is evidence to verify, not an authority," verified against sandbox
  reality rather than trusted.
- **Decision:** `ClaudeCLIProvider` implements and repairs; `CodexCLIProvider` independently
  verifies, with session isolation between the two (`MODEL_PROVIDER_CONTRACTS.md` §5) so QA
  never inherits the implementation session's framing.
- **Consequences:** QA has real independence; a compromised or overconfident implementation
  session cannot self-certify its own work.
- **Reconsideration trigger:** adding a third provider role requires a new decision, not a
  silent extension of this one.

## DD-04 — One workflow per target repository; local execution only; no multi-approver system (MVP)

- **Status:** Accepted.
- **Context:** MVP constraints requested explicitly: local execution, single active workflow
  per target, no distributed agents/cloud orchestration/multi-user approval.
- **Decision:** A per-target-repository lock enforces single-active-workflow; state and audit
  are local-filesystem only; authorization is single-authorizer.
- **Consequences:** Simplicity and a small, auditable trust boundary for the MVP; concurrency
  and multi-approver support are explicitly deferred (`MVP_SCOPE.md` §3), not silently
  unsupported by omission.
- **Reconsideration trigger:** any future multi-target-concurrency requirement is a new
  program decision, not an incremental change to this one.

## DD-05 — Squash-only merge, PR-only path, no admin bypass, structurally enforced

- **Status:** Accepted.
- **Context:** This repository's own Milestone 4 established the principle that dangerous Git
  operations (force-push, history rewrite, branch deletion outside policy) should be
  structurally unreachable through the writable surface, not merely policy-documented.
- **Decision:** The Git/GitHub Skill layer (`SKILL_CONTRACTS.md` §5) has no argv path that can
  reach `gh pr merge --admin`, a force-push, or a baseline commit/push — these are absent from
  the Skill surface entirely, mirroring `GitWriter`'s typed-method design.
- **Consequences:** Skill-layer code review can verify these prohibitions by inspection of the
  available methods, not by trusting every call site to remember policy.
- **Reconsideration trigger:** none identified; this is treated as permanent (`SECURITY_MODEL.md`
  §10 / `MVP_SCOPE.md` §2).

## DD-06 — Runtime workflow states named distinctly from the AUTO-00x stage lifecycle

- **Status:** Accepted.
- **Context:** Both state machines use everyday words like `AUTHORIZED`; without an explicit
  disambiguation, cross-document "state name consistency" review could wrongly read them as
  contradictory.
- **Decision:** `WORKFLOW_STATES.md` §1 and `STAGE_REGISTRY.md` §1 each carry an explicit
  cross-reference stating the two machines are distinct and naming any word shared between them
  as coincidental English overlap, not aliasing.
- **Consequences:** Reviewers and future sessions have one place each to resolve any apparent
  naming conflict.
- **Reconsideration trigger:** none identified.

## DD-07 — DASH-001 closed out as an AUTO-001 precondition

Cross-posted from `docs/DECISION_LOG.md` (2026-07-23 AUTO-001 entry) for program-local
visibility: DASH-001 was flipped from `Current` to `Done` in `docs/TASK_QUEUE.md` and its
mirrors before AUTO-001 work began, to satisfy this repository's `maximum_current_tasks: 1`
invariant. Full rationale: `docs/DECISION_LOG.md`.

## DD-08 — `SUPERSEDED` maps to task status `Done`, administratively closed, never successful completion (OD-8)

Cross-posted from `docs/DECISION_LOG.md` (2026-07-24 OD-8/OD-9 entry). Human Owner policy
decision resolving OD-8: `COMPLETE` and `SUPERSEDED` both map to task status `Done` (the
three-status model gains no fourth status), but `docs/TASK_QUEUE.md`'s prose must always
distinguish successful completion from administrative closure for a superseded stage. Legal
source states for `SUPERSEDED`: `AUTHORIZED`, `BLOCKED`, `IN_PROGRESS`, `SELF_REVIEW`, `REVIEW`,
`APPROVAL` — never `NOT_STARTED`/`PROPOSED`/`COMPLETE`. Superseding never automatically
authorizes or starts a successor. Full rationale and verbatim approval: `docs/DECISION_LOG.md`.

## DD-09 — Initial-execution failure policy: bounded retry, then reconciliation, then advance/repair/FAIL (OD-9)

Cross-posted from `docs/DECISION_LOG.md` (2026-07-24 OD-8/OD-9 entry). Human Owner policy
decision resolving OD-9 for the implementation-provider invocation and the `create_commit`/
`push_stage_branch`/`create_pull_request` Skills: a transient failure before any side effect
gets a bounded, same-state retry; a failure with a possible or unknown side effect never
retries blindly and instead performs an idempotency/reconciliation check; reconciliation success
advances normally (no duplicate side effect); a recoverable inconsistency uses the existing
`REPAIRING` path (never a second repair lifecycle); everything else — retry exhausted,
reconciliation indeterminate, an unrepairable inconsistency, or a broken invariant — reaches
`FAILED`. No new state or transition; only new reasons on existing edges plus a same-state retry
sub-procedure. Full normative text: `docs/workflow-automation/WORKFLOW_STATES.md` §5a. Full
rationale and verbatim approval: `docs/DECISION_LOG.md`.

## DD-10 — Repository lock: OS-level `flock` is the sole mutual-exclusion authority; metadata is diagnostic-only (OD-3)

- **Status:** Accepted. Engine implementation session decision, AUTO-002 (`OPEN_QUESTIONS.md`
  OD-3, whose recommendation this refines rather than adopts verbatim).
- **Context:** OD-3 asked whether the per-target-repository lock should be a PID/heartbeat file,
  an OS-level advisory lock, or both, and recommended a lock file with liveness-checked PID plus
  an underlying `flock` as the actual primitive.
- **Decision:** `agentos_workflow/orchestrator/lock.py` uses `fcntl.flock(LOCK_EX | LOCK_NB)` on
  `<canonical repository_path>/.agentos/workflow.lock` as the sole proof that a lock is held. The
  lock path is a pure function of the target repository's own symlink-resolved canonical path —
  never of the separately-configurable `state_directory` — so two configurations naming the same
  physical repository (including through a symlink alias) always contend on the same file. A JSON
  metadata payload (workflow ID, PID, hostname, repository identity/path, acquisition time) is
  written alongside the lock for diagnostics only; it is never treated as authoritative and no
  PID-liveness check is performed against it, since PIDs are reused by the OS and a stale file
  left by a crashed process is otherwise indistinguishable from a live one by inspection alone —
  only a live `flock` hold proves exclusivity. `release()` never unlinks the lock file, since
  unlinking while another process races to open the same path can let a third process acquire a
  fresh inode believing it holds the lock while the original file description is still locked;
  leaving the file in place and relying purely on `flock` avoids that race.
- **Consequences:** Simpler and race-free versus the recommended liveness-checked design;
  `agentos_workflow/tests/test_lock.py` covers acquire/release, same- and cross-process
  contention, stale-metadata tolerance, symlink-alias equivalence, and flock/fd cleanup on
  partial-failure paths (write/fsync/ftruncate/metadata-construction failures).
- **Reconsideration trigger:** none identified.

## DD-11 — Configuration file location finalized as `.agentos/workflow.yaml`, override always available (OD-5)

- **Status:** Accepted. Engine implementation session decision, AUTO-002 (`OPEN_QUESTIONS.md`
  OD-5; finalizes DD-02's "naming open" parenthetical).
- **Context:** OD-5 asked whether `.agentos/workflow.yaml` (per target repository) is the final
  convention or should be configurable/discoverable differently.
- **Decision:** `agentos_workflow/config/loader.py`'s `discover_config_path` keeps
  `.agentos/workflow.yaml`, relative to `repository_path`, as the default, with an explicit
  override path always accepted and taking precedence when supplied. A missing configuration
  file at the resolved path is a precondition failure (`ConfigurationNotFoundError`) — the loader
  never guesses or substitutes a default for `baseline_branch` or any other field.
- **Consequences:** Matches this repository's own `--config` convention for `workflowctl`, so a
  future CLI stage (AUTO-004+, `CLI_SPEC.md` §3) can wire an override flag straight through
  without a new discovery mechanism.
- **Reconsideration trigger:** none identified.

## DD-12 — `WorkflowSession` is the single, orchestrator-owned runtime facade; `WorkflowStateMachine`/`RepositoryLock`/`StateStore` are not re-exported as the package's public surface

- **Status:** Accepted. Engine implementation session decision, AUTO-002 (`ARCHITECTURE.md` §2,
  §5 — "Orchestrator... owns the state machine," "Repository Lock is acquired before any state
  transition past AUTHORIZED... released only when a workflow reaches DONE, FAILED, or
  CANCELLED").
- **Context:** Before this decision, `agentos_workflow/orchestrator/engine.py` exposed
  `WorkflowStateMachine`, `RepositoryLock`, and `StateStore` as three separately-constructed
  primitives, plus a set of free functions (`authorize`, `resume_workflow`,
  `evaluate_repair_attempt`, `record_repair_attempt_started`/`record_repair_attempt`,
  `record_initial_execution_attempt_started`/`record_initial_execution_attempt`,
  `evaluate_initial_execution_failure`, ...) each taking `state_store=`/`lock=`/`machine=`
  directly. `orchestrator/__init__.py` was empty, so nothing distinguished "the intended external
  entry point" from "a lower-level primitive" — a caller could assemble the three mutable runtime
  objects itself, in any order, and could observe or hold one without the other two correctly
  wired alongside it (e.g. calling `evaluate_repair_attempt` against a `state_store` for a
  workflow whose `RepositoryLock` a different caller already held, or never acquiring the lock at
  all before driving transitions).
- **Decision:** `WorkflowSession` (`engine.py`, at the end of the module, after every primitive it
  composes) is the sole public entry point an external caller — the not-yet-implemented
  Orchestrator/CLI layer, AUTO-003+ — is meant to hold. Constructed only via
  `WorkflowSession.start(...)` (fresh authorization) or `WorkflowSession.resume(...)`
  (re-attaching to persisted, in-flight state); both build their own `StateStore`/`RepositoryLock`
  from a `WorkflowConfig` alone, so a caller of `WorkflowSession` never constructs either. Every
  mutating operation the module already offered as a free function is available as a same-named
  instance method that supplies the session's own held `workflow_id`/`stage_id`/repository
  identity/`state_store` automatically. `WorkflowSession` never exposes the machine, lock, or
  state store it holds through any public attribute, property, or return value — only observable
  *state* (`.state`, `.is_terminal`, `.transitions` as an immutable tuple, `.lock_is_held` as a
  bare `bool`). `orchestrator/__init__.py` now declares a `__all__` that includes `WorkflowSession`
  and every error/enum/evidence type a caller needs to construct inputs or catch failures, but
  deliberately excludes `WorkflowStateMachine`, `RepositoryLock`, and `StateStore` from the
  package's declared public surface — a structural invariant `test_workflow_session.py`'s
  `TestNeverExposesMutableRuntimeObjects` class asserts directly, not merely documents.
  `WorkflowSession.start()` also fixes an ordering defect found while building it: it now acquires
  the repository lock *before* calling `authorize()`, not after — `authorize()` itself has no
  notion of a repository lock, so two concurrent `start()` calls against the same target
  repository (necessarily different `workflow_id`s) previously could have both durably persisted
  an `AuthorizationRecord` before either attempted to acquire the lock, only one of which could
  ever actually proceed. Acquiring the lock first makes `ARCHITECTURE.md` §5's "a second authorize
  call against a locked target repository is refused... before any target-repository mutation
  occurs" actually true for `WorkflowSession`, rather than true only for whichever caller happened
  to acquire the lock first while both had already written conflicting authorization evidence.
- **Consequences:** None of `WorkflowStateMachine`, `RepositoryLock`, `StateStore`, or the free
  functions they compose were removed, renamed, or deprecated — they remain independently
  importable and independently tested (this package's own whitebox test suite continues to import
  them directly) for any lower-level caller that does not want `WorkflowSession`'s composed
  lifecycle. No Agent, Skill, or Model Provider is implemented by this decision; `WorkflowSession`
  composes only primitives this stage already built.
- **Reconsideration trigger:** if a future stage needs more than one workflow instance live inside
  a single process against the same target repository (contradicting DD-04's "one workflow per
  target repository, MVP"), `WorkflowSession`'s implicit one-lock-per-instance assumption would
  need explicit revisiting.

## DD-13 — Infrastructure retries, repair attempts, and initial-execution attempts are three separate durable counters; no AUTO-002 code change (OD-4)

- **Status:** Accepted. Human Owner policy decision (`OPEN_QUESTIONS.md` OD-4; verbatim approval
  and full rationale: `docs/DECISION_LOG.md`, 2026-07-26 entry).
- **Context:** OD-4 asked the Human Owner to confirm that transient infrastructure retries (e.g. a
  flaky GitHub API call) never increment the 3-attempt repair counter, before AUTO-002 could treat
  that separation as load-bearing rather than documentation intent. `WORKFLOW_STATES.md` §5
  already described the separation; the sign-off itself was the missing piece.
- **Decision:** The Human Owner confirmed the separation and additionally made explicit that
  infrastructure retries, repair attempts, and initial-execution attempts are three separate
  durable event streams and counters — infrastructure retry permitted only on durable
  proven-no-side-effect evidence, prohibited (mandatory reconciliation instead) once invocation may
  have started. `WORKFLOW_STATES.md` §5 updated to state this explicitly, version 4.1 → 4.2.
- **Consequences:** No `agentos_workflow/` code changed. AUTO-002 already implements two of the
  three streams as independent counters (`AttemptKind.INITIAL_EXECUTION`, `AttemptKind.REPAIR`);
  the third (infrastructure retry) has no implementation anywhere in AUTO-002 because no Skill,
  Provider, or Git/GitHub call exists yet to retry — that stream's implementation is deferred to
  whichever future stage first introduces a retryable infrastructure call (most likely AUTO-003 or
  AUTO-006), which must build it as its own independent counter from the outset.
- **Reconsideration trigger:** none identified.

## Governance Correction Record (2026-07-27) — DD-14 physical placement

A fresh-session governance reconciliation, performed before AUTO002-F04, found that DD-14 above
(added by the immediately preceding session) was appended in the wrong physical location — placed
between DD-01 and DD-02 rather than after DD-13, breaking this file's ascending DD-01→DD-13
ordering with no supersession note explaining the placement. The Human Owner reviewed this finding
and directed a Governance Correction Record (`STAGE_REGISTRY.md` §3 rule 18) rather than any edit
to DD-14 itself. Per that directive: DD-14's content, status, and authority are unaffected and
remain fully valid and binding; no decision identifier is renumbered; no historical decision text
above (DD-01's or DD-14's own) is removed, moved, or rewritten. The effective decision sequence for
all purposes going forward is **DD-01 through DD-14**, regardless of DD-14's physical position in
this file. This record corrects only the implied physical ordering, not the content of any
decision. Full rationale, authorization, and the companion `STAGE_REGISTRY.md` §6 synchronization:
`docs/DECISION_LOG.md`, 2026-07-27 Governance Correction Record entry.

## DD-15 — AUTO002-F07: narrow local reconciliation-evidence verification; remote/PR evidence remains unauthorized and fails closed

- **Status:** Accepted. Human Owner decision, 2026-07-27 ("AUTO002-F07 evidence verification
  scope"; full text: `docs/DECISION_LOG.md`, 2026-07-27 entry).
- **Context:** AUTO002-F07 found that `evaluate_initial_execution_failure`'s reconciliation-
  evidence handling (WORKFLOW_STATES.md §5a) accepted confirmed `ReconciliationEvidence` on the
  strength of a caller-supplied success Boolean, internal expected/observed self-consistency, and
  a nonblank reference string alone — never independently checked against the repository. A
  caller (or a compromised/buggy future Skill) could claim any outcome for any commit, remote
  ref, or pull request and have it accepted verbatim. F07 was blocked pending a Human Owner scope
  decision on whether AUTO-002 may independently verify evidence at all, and if so, how far DD-14's
  existing local-observation boundary may be extended to do it.
- **Decision:** `ReconciliationEvidence` must never be accepted merely on the caller's claim.
  DD-14's local-observation boundary is narrowly extended, evidence-verification-only, via a new
  `LocalEvidenceObserver` (`agentos_workflow/observation/evidence.py`) exposing exactly
  `commit_exists`, `tree_sha`, and `commit_reachable_from_branch` — the same fixed-argv,
  read-only, scrubbed-environment subprocess pattern `LocalResumeObserver` already established,
  no arbitrary command surface, no mutable Git operation, no network or GitHub call.
  `ImplementationDiffEvidence` (`IMPLEMENTING`) and `CommitEvidence` (`READY_TO_COMMIT`) are
  locally verifiable and are now independently re-derived from real Git state before being
  trusted: the claimed commit must exist locally, be reachable from the claimed stage branch
  (`ImplementationDiffEvidence`) or have its tree SHA independently recomputed and compared
  (`CommitEvidence`) — a caller-supplied SHA or branch label is never itself authority.
  `ImplementationDiffEvidence`'s `completion_report_reference` is confined to a bare filename,
  resolved by the engine (never the caller) to
  `<audit_directory>/<workflow_id>/evidence/<state.value>/<artifact_name>`
  (`resolve_evidence_artifact`), with per-component validation before path construction, a
  confinement check under the audit root (catching both parent traversal and symlink escape), and
  an existing-regular-file check. `RemoteRefEvidence` (`COMMITTED`) and `PullRequestEvidence`
  (`PUSHED`) describe remote/GitHub facts AUTO-002 has no authorized network-reaching observer
  for; both now unconditionally raise a new `ReconciliationVerifierUnavailableError` regardless of
  the caller's claim — lack of an authorized verifier is never interpreted as successful evidence.
  A definite local disagreement (commit missing, outside branch ancestry, tree mismatch, artifact
  unresolvable) raises a second new error, `LocalEvidenceVerificationFailedError`. Both are wired
  into the existing `evaluate_initial_execution_failure` transparently, immediately after its
  existing internal-consistency check, using only parameters (`repository_path`,
  `state_store.audit_directory`) it already received — no public signature changed.
- **Consequences:** No dependency added; no network or GitHub access implemented; no general
  Skill or Agent interface implemented; no mutable Git operation authorized. `COMMITTED`/`PUSHED`
  reconciliation now always fails closed pending future authorized Skill/GitHub observation work
  — this decision does not authorize building that observer, nor AUTO-003 or AUTO-005. Two
  acknowledged, undocumented-until-now gaps remain, deliberately left unclosed rather than
  papered over with invented schema: (1) the evidence-artifact path convention binds
  workflow/operation but not the specific retry *attempt* — no `attempt_number` field exists on
  any evidence type to bind against; (2) `ImplementationDiffEvidence` has no `changed_paths`
  field, so "changed paths outside authorized scope" is not independently checkable from evidence
  alone today. Both are recorded here as known limitations for a future stage to close, not
  silently assumed solved.
- **Reconsideration trigger:** the first future stage that adds an authorized remote/GitHub
  observer (most likely AUTO-003 or AUTO-006) must revisit `RemoteRefEvidence`/
  `PullRequestEvidence`'s unconditional fail-closed behavior here, and the first stage that adds
  per-attempt evidence binding or changed-path scope evidence must revisit the two gaps noted
  above.

## DD-16 — AUTO002-F04/F05/F06: canonical repository locking, JSONL append durability, and durable retry/attempt accounting hardened

- **Status:** Accepted. Independent-review findings F04/F05/F06, remediated earlier in the same
  multi-session remediation pass this document's DD-15/DD-17 through DD-21 entries also record.
- **Context:** A fresh-session independent review of AUTO-002's already-implemented
  `agentos_workflow/` module found three hardening gaps, processed in order ahead of F07-F10 above
  (`docs/reports/workflow-automation/AUTO-002-completion-report.md`'s own ledger, this remediation
  pass's ninth-plus sessions, is the authoritative per-finding record; this entry exists so
  `DECISIONS.md` — not only the completion report — carries these three findings, matching the
  discipline every other AUTO-002 finding in this file already has).
- **Decision:**
  - **F04 (canonical repository locking, `agentos_workflow/orchestrator/lock.py`):**
    `canonical_lock_path` derives a target repository's lock location solely from the
    repository's own canonical (symlink-resolved, absolute) filesystem path — never from the
    separately-configurable `state_directory` — so two configurations naming the same physical
    repository (directly, or through a symlink alias, or through a differently-configured
    `state_directory`) always resolve to the identical lock file and genuinely contend, closing a
    path by which "exactly one active workflow per target repository" (`ARCHITECTURE.md` §5)
    could otherwise be defeated.
  - **F05 (state persistence and JSONL durability, `agentos_workflow/orchestrator/state_store.py`):**
    every transition/command-execution append is a single `flock`-serialized,
    open-write-fsync-close sequence (`_append_jsonl_line`), with every byte of the payload written
    in a retry loop (`_write_all`, guarding against a POSIX short write silently truncating a
    record) and the containing directory itself durably `fsync`'d on first creation
    (`_ensure_directory_durable`) — so a crash mid-append can never leave a torn, unparseable
    record silently accepted on a later read, and two concurrent writers (threads or processes)
    can never interleave their writes into a corrupted line.
  - **F06 (retry reservation and attempt accounting, `agentos_workflow/orchestrator/engine.py`):**
    every initial-execution and repair attempt is durably reserved as its own `STARTED` event
    (`record_initial_execution_attempt_started`/`record_repair_attempt_started`) under a
    per-workflow lock (`_held_attempts_lock`) before the operation itself ever runs, and completed
    separately (`record_initial_execution_attempt`/`record_repair_attempt`) — so a crash between
    "started" and "completed" is durably detectable (`has_unreconciled_initial_execution_attempt`)
    on restart rather than looking like an attempt that never happened, and attempt numbering,
    limits, and unreconciled-attempt refusal are all enforced from this same durable record, never
    from an in-memory counter.
- **Consequences:** No dependency added; no schema field removed; no public signature changed
  beyond what each fix's own accompanying regression tests (`test_lock.py`, `test_state_store.py`,
  `test_engine_retry.py`) already exercise. These three findings were implemented and fully tested
  in an earlier portion of this same remediation session, before F07-F10's own work (DD-15,
  DD-17-DD-21) began; this entry deliberately does not restate implementation-level specifics
  (exact prior defect reproduction, line-level detail) beyond what is directly verifiable against
  the current code, consistent with this program's discipline against asserting unverifiable
  historical detail.
- **Reconsideration trigger:** none identified beyond the per-file reconsideration triggers each
  fix's own code comments and tests already carry.

## DD-17 — AUTO002-F08: audit-record identity, timestamp, path-confinement, and ordering invariants hardened

- **Status:** Accepted. Independent-review finding F08, remediated in this remediation pass.
- **Context:** F08 found `agentos_workflow/orchestrator/state_store.py`'s `CommandExecutionRecord`/
  `StateTransitionRecord` schemas and their read paths accepted several classes of internally
  inconsistent or unsafe values with no validation: a naive (non-timezone-aware) timestamp; a
  command's `completion_time` before its own `start_time`; an `stdout_ref`/`stderr_ref` pointing
  outside the audit directory (absolute path or `..` parent traversal) — silently defeating
  `AUDIT_MODEL.md` §2's "reference... under the audit directory" description; a
  `StateTransitionRecord` whose own `workflow_id` field disagreed with the file it was read from;
  and a persisted sequence whose timestamps were not in non-decreasing (append) order.
- **Decision:** `_validate_iso8601` now rejects a naive timestamp (every timestamp this codebase
  actually produces is already timezone-aware, so this only ever rejects a value nothing
  legitimate would produce). `CommandExecutionRecord` gained a model validator rejecting
  `completion_time < start_time`, and a field validator (`_validate_audit_ref`) rejecting an
  absolute or parent-traversal `stdout_ref`/`stderr_ref` — a purely syntactic, structural check
  (no configured audit root is available to a bare field validator), matching the same discipline
  AUTO002-F07's `resolve_evidence_artifact` already applies to evidence-artifact references.
  `StateStore.read_transitions` now cross-checks every returned record's own `workflow_id` field
  against the requested one (`StateStoreCorruptionError` on mismatch), and both
  `read_transitions`/`read_command_executions` now reject a persisted sequence whose timestamps
  are not in non-decreasing order (`_require_monotonic_order`) — a real, `flock`-serialized
  append-only writer can never itself produce such a file, so a violation is treated as audit
  corruption, the same severity `AUDIT_MODEL.md` §8 already assigns audit-completeness failures.
- **Consequences:** No schema field added or removed (`CommandExecutionRecord` has no `workflow_id`
  field per `AUDIT_MODEL.md` §2's own schema, so its identity cannot be cross-checked the same way
  `StateTransitionRecord`'s is — recorded here as an explicit, acknowledged limitation, not
  silently worked around). Two pre-existing tests (`test_engine_resume.py`'s
  `test_record_workflow_id_disagreeing_with_file_rejected`, `test_state_store.py`'s
  `test_command_executions_persist_in_order`) were updated to reflect detection now happening one
  layer earlier (`CorruptedHistoryError` instead of `InconsistentHistoryError`) and to supply a
  consistent `completion_time`, respectively — both were adjustments to match corrected behavior,
  never a weakening of what either test verifies. 44 new regression tests added
  (`test_state_store.py`).
- **Reconsideration trigger:** the first stage that adds a `workflow_id` (or other identity) field
  to `CommandExecutionRecord` should also add the same cross-check `read_transitions` now applies
  to `StateTransitionRecord`.

## DD-18 — AUTO002-F09: changed-path configuration patterns confined to repository-relative form

- **Status:** Accepted. Independent-review finding F09, remediated in this remediation pass.
- **Context:** F09 found `agentos_workflow/config/schema.py`'s `allowed_changed_paths`/
  `forbidden_changed_paths` fields (glob patterns matched via `fnmatch.fnmatchcase` against
  repository-relative changed-file paths, `engine.py`'s `_matches_any`) accepted any string,
  including an absolute pattern or one containing a `..` segment — which can never match any real
  repository-relative changed path at all. For `forbidden_changed_paths` specifically, such a
  pattern does not merely do nothing: it gives the false appearance of an active protection that
  was never actually in effect, directly contradicting `CONFIGURATION_MODEL.md` §4's "no path may
  resolve outside the intended boundary."
- **Decision:** `WorkflowConfig` gained a field validator on both fields rejecting a blank
  pattern, a pattern starting with `/`, and a pattern containing a `..` segment (leading, embedded,
  or bare) — a purely structural check requiring nothing more than the pattern's own text, applied
  before any matching ever occurs.
- **Consequences:** No schema field added; no existing legitimate configuration (the illustrative
  example in `CONFIGURATION_MODEL.md` §5, and every configuration fixture already in this
  program's own test suite) is rejected by this tightening — confirmed by the full test suite
  passing unchanged. 8 new regression tests added (`test_config.py`).
- **Reconsideration trigger:** none identified.

## DD-19 — AUTO002-F10: `ResumedWorkflow.transition_to` rejects `AUTHORIZED` before any persistence, closing a lower-level authorization-bypass write

- **Status:** Accepted. Independent-review finding F10, remediated in this remediation pass.
- **Context:** F10 found that `ResumedWorkflow` (`agentos_workflow/orchestrator/engine.py`) — a
  plain, unguarded dataclass with no construction token (unlike `WorkflowSession`, whose own
  `__init__` requires one) — could be constructed directly by any caller holding a `StateStore`, a
  `RepositoryLock`, and an arbitrary list of `StateTransitionRecord`, entirely bypassing
  `resume_workflow()`'s replay, evidence, and reuse checks. Because `(CREATED, AUTHORIZED)` is a
  legal edge in `ALLOWED_TRANSITIONS` and `actor="human"` is legal for it, calling
  `ResumedWorkflow.transition_to(WorkflowState.AUTHORIZED, actor="human")` against such a
  fabricated instance (`.machine` a fresh, never-replayed `WorkflowStateMachine()` at `CREATED`)
  reached `self.state_store.record_transition(new_record)` and durably persisted a fabricated
  `CREATED -> AUTHORIZED` transition — with no `AuthorizationRecord` ever validated — *before* its
  own trailing `self.machine.transition_to(to_state)` call finally raised
  `AuthorizationBypassError`. The corrupting write happened first, every time; the rejection came
  too late to prevent it, defeating `WorkflowIdReuseError`'s single-use invariant at a layer no
  `WorkflowSession`-facade check ever runs at.
- **Decision:** `ResumedWorkflow.transition_to` now checks `to_state is WorkflowState.AUTHORIZED`
  and raises `AuthorizationBypassError` immediately — before `from_state` is even read, and before
  any persistence is attempted — mirroring the same rejection `WorkflowStateMachine.transition_to`
  already performs for its own in-memory mutation, now also closing the gap on the durable-write
  side. `raw authorize()` itself (independently re-verified during this investigation) was already
  airtight against every reuse scenario tried; the bypass was specific to `ResumedWorkflow`.
- **Consequences:** No change to `ResumedWorkflow`'s deliberately unguarded construction (its own
  docstring already documents `.machine.transition_to(...)` as intentionally directly reachable —
  this fix closes the specific write-before-check ordering defect, not `ResumedWorkflow`'s general
  accessibility, which remains a documented design choice). 5 new regression tests added
  (`test_engine_resume.py`), including one confirming a *legitimately* resumed workflow is covered
  by the same guard, not merely the fabricated-instance reproduction.
- **Reconsideration trigger:** none identified.

## DD-20 — AUTO002-F12: regression-test-adequacy audit found no leftover positively-encoded unsafe behavior

- **Status:** Accepted (audit only; no code change). Independent-review finding F12.
- **Context:** F12 asked whether any test in the AUTO-002 test suite still asserted, as expected/
  correct, behavior that F04-F10's fixes above made unsafe or incorrect ("positively-encoded
  unsafe behavior") — beyond the specific tests each fix's own work already found and corrected.
- **Decision:** A full-suite run after every one of F04-F10's fixes (1872 tests, `pytest tests
  agentos_workflow/tests`) passed with zero failures beyond the specific tests each fix's own work
  identified and corrected; a further targeted sweep (naive timestamps, `RemoteRefEvidence`/
  `PullRequestEvidence` success expectations, absolute-path audit refs, fabricated-SHA evidence,
  `skip`/`xfail` markers) found nothing further to rewrite or remove.
- **Consequences:** No test file changed by this finding specifically (F04-F10's own fixes already
  made every necessary test change).
- **Reconsideration trigger:** none identified.

## DD-21 — AUTO002-IR-01: repository lock confined to the canonical repository by descriptor-relative `O_NOFOLLOW` opens

- **Status:** Accepted. Independent-review finding IR-01, remediated in this remediation pass.
  Pending fresh independent review.
- **Context:** A second, independent review reproduced a lock-file escape that DD-16's F04 work
  did not close. `canonical_lock_path` resolves the *repository root* (`Path.resolve()`), but then
  appends `.agentos/workflow.lock` lexically; `acquire()` opened that joined path directly. With
  `<repo>/.agentos` a symlink to a directory outside the repository, `os.open(..., O_RDWR |
  O_CREAT)` followed the link and `os.ftruncate(fd, 0)` then destroyed the external file's
  contents. Reproduced directly: an external `workflow.lock` holding sentinel bytes was truncated
  and overwritten with lock metadata. Resolving the root alone is not confinement.
- **Decision:** Every lock open now walks the path one literal component at a time with
  `O_NOFOLLOW`, relative to a directory file descriptor (`dir_fd`), starting from the
  already-canonical root: `_open_confined_lock_fd` → `_open_directory_component` →
  `_open_lock_file_component` (`agentos_workflow/orchestrator/lock.py`). A symlinked component is
  refused by the kernel *at the open itself*, not by a separate check a racing attacker could
  invalidate between check and open, and the refusal happens before any create, truncate, or
  write. `read_metadata` uses the same confined walk rather than `Path.read_text`, so a symlinked
  control directory cannot even disclose an external file's bytes. A new
  `LockPathConfinementError(LockError)` carries the refusal; `LockContentionError`/`LockStateError`
  are unchanged.
- **Consequences:** Lock *identity* is unchanged — two spellings of the same physical repository
  (including a symlinked repository root, which `resolve()` still legitimately collapses) still
  contend for exactly one lock, and cross-process `flock` contention is unaffected. Only symlinks
  at or below `.agentos` are refused. `_refused_symlink` classifies an already-failed open via
  `lstat` purely to choose the error message; the open, not that check, is what enforces
  confinement. The module was already POSIX-only (`fcntl.flock`), so `dir_fd`/`O_NOFOLLOW` add no
  new portability constraint — this is documented in the module docstring rather than claiming
  cross-platform guarantees that do not exist. 8 new regression tests (`test_lock.py`).
- **Reconsideration trigger:** a supported non-POSIX target, which would require replacing
  `flock` and this walk together.

## DD-22 — AUTO002-IR-02: state and audit records confined to their configured roots by one shared confined-open primitive

- **Status:** Accepted. Independent-review finding IR-02, remediated in this remediation pass.
  Pending fresh independent review.
- **Context:** The same review reproduced the equivalent escape in persistence. `_safe_workflow_id`
  validates the workflow identifier as a safe path *component*, but the component was still joined
  lexically and the record file opened by path. With `<state_directory>/<workflow_id>` (or the
  audit equivalent) a symlink, `record_transition`/`record_command_execution` appended audit
  records to files outside the configured root — reproduced on both histories, with sentinel-bearing
  external files appended to. Reads were equally unconfined, so a planted external history could
  be replayed as the workflow's own and `current_state` would return attacker-chosen state.
- **Decision:** One reusable primitive, `_confined_record_fd`
  (`agentos_workflow/orchestrator/state_store.py`), performs the same descriptor-relative
  `O_NOFOLLOW` walk as DD-21, from the canonical root through `<workflow_id>` to the record file,
  and is used by *both* transition and command storage and by *both* reads and writes — so the two
  histories cannot drift apart in what they enforce. Validation precedes any `mkdir`, create,
  append, or read. A new `StateStorePathConfinementError(StateStoreError)` carries the refusal,
  deliberately *not* a `StateStoreCorruptionError`: the records may be perfectly well-formed; the
  defect is where the path points.
- **Consequences:** Append-only semantics are preserved exactly (`O_APPEND`, no `O_TRUNC`).
  Durability is preserved: the primitive yields the workflow-directory descriptor alongside the
  record descriptor and holds it open for the caller, so the post-append directory `fsync` now
  targets that already-open descriptor instead of reopening the directory by path — removing the
  very check-then-open pattern this finding is about. One existing F02 crash-atomicity test
  (`test_transition_directory_fsync_failure_leaves_completed_detectable_pair`) injected at the
  path-based `_fsync_directory` seam; it was re-targeted at the descriptor-level `fsync`,
  identified by the directory's own contents, with every assertion it makes unchanged — the
  invariant under test (a directory-fsync failure propagates and leaves a detectable pair) is
  identical. 10 new regression tests (`test_state_store.py`).
- **Reconsideration trigger:** same POSIX assumption as DD-21.

## DD-23 — AUTO002-IR-03: changed-path authorization operates on one canonical representation; noncanonical patterns are rejected outright

- **Status:** Accepted. Independent-review finding IR-03, remediated in this remediation pass.
  Pending fresh independent review.
- **Context:** DD-18 (F09) rejected absolute and `..` patterns only. The review reproduced
  *noncanonical but non-traversing* patterns still being accepted and passed raw into
  `fnmatch.fnmatchcase`: `docs/./secret/**`, `docs//secret/**`, `docs\secret\**`,
  `./docs/secret/**`, `C:\...`, `C:/...`, `\\server\share\**`, and whitespace-only strings — seven
  forms accepted, none of which match the canonical `docs/secret/x` that Git actually reports. For
  `forbidden_changed_paths` this is the precise failure DD-18 set out to prevent and did not: the
  forbidden rule stays inert, the path falls through, and a broader `allowed_changed_paths` rule
  wins. A configuration could read as forbidding a path while actually allowing it.
- **Decision:** *Strict rejection*, the preferred of the two offered designs — never partial
  normalization, and never a mix of the two. `_noncanonical_pattern_reason`
  (`agentos_workflow/config/schema.py`) accepts a pattern only if it is already in the single
  canonical repository-relative POSIX form: it rejects empty and whitespace-only strings, any
  backslash (covering Windows separators and UNC forms alike), a Windows drive-letter prefix, a
  leading `/`, and any empty, `.`, or `..` segment. It judges only separators and segments, so
  `*`, `?`, `[...]`, and `**` pass through untouched and no rewriting step can reinterpret a glob
  token. The error names the offending pattern and the specific reason. Symmetrically,
  `canonical_repository_relative_path` reduces each *observed* Git path to that same
  representation, and `_classify_worktree` (`engine.py`) matches on it — so both sides of every
  comparison are provably in one representation and forbidden rules deterministically take
  precedence over broader allowed rules.
- **Consequences:** Backslashes are rejected in patterns but deliberately *preserved* in observed
  paths: a backslash is a legal POSIX filename character, so rewriting it to `/` would silently
  reinterpret a legitimate path. Canonicalisation governs the authorization *decision* only; drift
  reporting still surfaces exactly the path Git reported. No legitimate existing pattern is
  rejected (`.github/**` and similar leading-dot filenames are canonical segments, not `.`
  segments) — confirmed by the full suite. 48 new regression tests (`test_config.py`,
  `test_engine_authorization.py`).
- **Reconsideration trigger:** a requirement to accept configuration authored on Windows, which
  would need an explicit, tested translation layer rather than silent acceptance.

## DD-24 — AUTO002-IR-04: chronological ordering enforced at append time, under the append lock

- **Status:** Accepted. Independent-review finding IR-04, remediated in this remediation pass.
  Pending fresh independent review.
- **Context:** DD-17 (F08) added `_require_monotonic_order` on the *read* path only. The review
  reproduced the resulting asymmetry: the public writer accepted a record older than the one
  already persisted, the append succeeded, and every subsequent `read_transitions` /
  `read_command_executions` then raised `StateStoreCorruptionError`. The store could be driven
  into a permanently unreadable state through its own supported API, with no tampering — reproduced
  on both histories.
- **Decision:** `_append_jsonl_line` now enforces ordering *before* writing any byte, while
  holding the same `flock` that protects the append, reading the last durable record through the
  *same* file description the append will use (`_last_persisted_timestamp`) — which is what makes
  check-and-append indivisible rather than a scan followed by a later write. The rule applied is
  exactly the reader's: **non-decreasing**, so an equal timestamp is accepted and only a strictly
  earlier one is refused; comparison is on parsed instants, so equal times in different UTC
  offsets compare equal. Transition histories order on `timestamp`; command histories order on
  `completion_time` — the same field `read_command_executions` enforces, stated explicitly so
  writer and reader can never diverge. A new `StateStoreOrderingError(StateStoreError)` carries
  the rejection, distinct from corruption: nothing on disk is wrong, the submitted record is.
- **Consequences:** Empty and missing histories are unconstrained. A malformed existing tail
  (torn append, blank final line, non-JSON, missing or unparseable timestamp) fails closed as
  `StateStoreCorruptionError` without writing — extending a history that cannot be replayed would
  only deepen the damage. Rejection leaves the file byte-for-byte intact and still replayable. The
  record file is now opened `O_RDWR` rather than `O_WRONLY` solely so the tail can be read under
  the lock; `O_APPEND` still forces every write to end-of-file, so readability grants no ability to
  overwrite or truncate. Flush/fsync durability is unchanged. 17 new regression tests
  (`test_state_store.py`).
- **Reconsideration trigger:** a requirement for clock-skew tolerance across hosts, which would
  need an explicit skew policy rather than a relaxed comparison.

## DD-25 — AUTO002-IR-05: duplicate JSON object keys rejected at every nesting level

- **Status:** Accepted. Independent-review finding IR-05, remediated in this remediation pass.
  Pending fresh independent review.
- **Context:** Persisted records were parsed with standard JSON semantics, which silently accept a
  repeated object key and apply last-key-wins. The review reproduced records that parsed cleanly
  and validated successfully while carrying two values for the same field: a duplicate `to_state`
  replayed as `MERGED` (the value `current_state` returns), and a duplicate `timestamp` drove the
  record backwards in time. An ambiguous record has no single correct reading, so choosing one
  silently is the defect.
- **Decision:** `_loads_rejecting_duplicate_keys` parses every persisted record with
  `json.loads(..., object_pairs_hook=...)`, which sees each object's raw key/value pairs before a
  dict collapses them — so duplicates are caught at *any* nesting level, not merely top level.
  Parsing is now a separate step from model validation, so an ambiguous record fails closed as
  `StateStoreCorruptionError` before any model sees one arbitrarily-chosen reading of it. The same
  strict loader is used by the writer's tail parse (DD-24), so reads and writes agree. The error
  names the file, the line, and the offending key, and deliberately does not echo the record's
  other contents.
- **Consequences:** Applies identically to transition and command records. Valid records are
  unaffected; exception chaining is preserved. This mirrors the *shape* of the packaged
  `ai_workflow_engine.workflow.event_store._parse_json_no_duplicate_keys` for consistency, but is
  re-implemented locally and raises this module's own `StateStoreCorruptionError` — `agentos_workflow`
  takes on no dependency on `ai_workflow_engine` internals, and no packaged source was modified.
  12 new regression tests (`test_state_store.py`).
- **Reconsideration trigger:** none identified.

## DD-26 — AUTO002-F11: historical definition and regression mapping could not be reconstructed from durable repository evidence

- **Status:** Accepted (traceability correction; no code change). Supersedes the claim, made in
  `docs/DECISION_LOG.md` and the AUTO-002 completion report, that "F11 was already resolved by a
  prior session and was not reopened."
- **Context:** The independent review could not locate any durable definition, implementation
  mapping, or regression-test mapping for F11. An exhaustive local search confirms this: the
  string `F11` appears in exactly two places in the entire repository — one line in
  `docs/DECISION_LOG.md` and two lines in
  `docs/reports/workflow-automation/AUTO-002-completion-report.md` — and in both cases it is only
  the assertion that F11 was already resolved, never a statement of what F11 *was*. No F11
  definition exists in any decision record, report, addendum, stage prompt, test, or
  implementation file; `git log -S "F11"` across all refs returns nothing, and neither stash
  contains it. No network was used.
- **Decision:** Outcome B. F11 is recorded as **`INSUFFICIENT_DURABLE_EVIDENCE`**:
  `F11 historical definition and regression mapping could not be reconstructed from durable
  repository evidence.` No definition is invented, and no implementation was changed to manufacture
  evidence. The prior "already resolved" claim is superseded as unverifiable rather than deleted —
  the fact that it was asserted, and by whom, remains on the record.
- **Consequences:** F11 does not block this remediation: the five reproduced findings IR-01
  through IR-05 are concrete and independently reproduced, and none of them depends on the unknown
  F11 invariant. It remains possible that F11 described a real defect that is still open; nothing
  here should be read as evidence that it was fixed. If a future session recovers the original
  wording, F11 must be re-assessed against current code from scratch.
- **Reconsideration trigger:** recovery of the original F11 statement from any durable source.

## DD-27 — AUTO002-IR3-01: implementation reconciliation evidence is bound to authorization and persisted execution

- **Status:** Accepted. Third independent-review finding IR3-01, remediated with Human Owner
  authorization. Pending fresh independent review.
- **Context:** Implementation reconciliation accepted any existing commit reachable from a
  caller-named branch plus any nonblank artifact. It did not require the authorized branch, its
  exact tip, a persisted attempt, the authorized-baseline diff, or a report bound to those facts.
- **Decision:** `ImplementationDiffEvidence` carries the implementation attempt and canonical
  changed paths. Acceptance requires the authorized planned branch, its exact current tip, the
  latest persisted `IMPLEMENTING` attempt, an independently-derived Git diff from the authorized
  baseline, authorized path-policy compliance, and an exact structured completion-report binding
  to workflow, stage, attempt, branch, head, and changed paths.
- **Consequences:** Stale ancestors, unbound branches, empty/malformed/mismatched reports,
  cross-workflow artifacts, nonexistent attempts, and out-of-policy diffs fail closed. Remote
  evidence remains unavailable and no network authority is added.
- **Reconsideration trigger:** a future approved evidence format or remote verification boundary.

## DD-28 — AUTO002-IR3-02: mutable persistence files must have exactly one filesystem name

- **Status:** Accepted. Third independent-review finding IR3-02, remediated with Human Owner
  authorization. Pending fresh independent review.
- **Context:** `O_NOFOLLOW` prevents symlink traversal but not hardlink aliasing. A planted
  hardlink at a lock, transition-history, or attempt-history path allowed an engine write to mutate
  the same inode through a name outside the configured boundary.
- **Decision:** After descriptor-relative open and before any mutation, every mutable persistence
  target must be a regular file with link count exactly one. Otherwise the existing confinement
  error is raised.
- **Consequences:** Lock, transition, command, authorization-lock, and attempt files cannot alias
  an externally named inode. This is a POSIX/local-filesystem invariant consistent with the
  existing `fcntl` and `dir_fd` implementation boundary.
- **Reconsideration trigger:** a storage backend without meaningful POSIX link counts.

## DD-29 — AUTO002-IR3-03: authorization and attempt sidecars use the same workflow confinement boundary

- **Status:** Accepted. Third independent-review finding IR3-03, remediated with Human Owner
  authorization. Pending fresh independent review.
- **Context:** Authorization and attempt sidecars resolved final paths, so a symlink could select
  another workflow directory while remaining under the configured state root.
- **Decision:** Authorization, authorization-lock, attempt, and attempt-lock access is performed
  relative to an `O_NOFOLLOW`-opened literal `<state_root>/<workflow_id>` directory descriptor.
  Atomic publication, cleanup, reading, locking, and durability operations remain descriptor
  relative throughout.
- **Consequences:** One workflow cannot consume or mutate another workflow's authorization or
  attempt artifacts through path aliases, including aliases that remain inside the state root.
- **Reconsideration trigger:** migration to a transactional database with explicit workflow keys.

## DD-30 — AUTO002-IR3-04: strict duplicate-key JSON parsing covers all security-relevant sidecars and evidence

- **Status:** Accepted. Third independent-review finding IR3-04, remediated with Human Owner
  authorization. Pending fresh independent review.
- **Context:** Authorization and attempt JSON, and completion-report JSON, still used
  last-key-wins parsing even though transition and command histories already rejected ambiguous
  objects.
- **Decision:** The existing duplicate-key-rejecting loader is used before schema validation for
  authorization, attempt, and completion-report JSON. Duplicate keys at any nesting level are
  corruption, never an alternate serialization of a valid record.
- **Consequences:** Every persisted field participating in authorization, retry accounting, or
  reconciliation has one unambiguous value.
- **Reconsideration trigger:** none identified.

## DD-31 — AUTO002-IR3-05: audit schema documents repository identity and path as distinct fields

- **Status:** Accepted. Third independent-review finding IR3-05, remediated with Human Owner
  authorization. Pending fresh independent review.
- **Context:** `StateTransitionRecord` persisted `target_repository` and `repository_path`
  separately, while `AUDIT_MODEL.md` documented only one combined identity-and-path field.
- **Decision:** The audit model now defines `target_repository` as repository identity and
  `repository_path` as its independently bound canonical path, matching the implemented schema.
- **Consequences:** Governance, validation, and persisted records describe the same two
  independently checkable authorization facts. This documents an existing field; it does not
  migrate or rewrite append-only history.
- **Reconsideration trigger:** a versioned audit-schema migration.

## DD-32 — Human Owner accepts and closes AUTO-002 without another independent review

- **Status:** Accepted. Human Owner closure decision, 2026-07-27.
- **Context:** All approved remediation tasks were implemented and the reported focused/full
  validation passed. The prior remediation record called for a fresh independent review.
- **Decision:** The Human Owner reviewed the implementation and validation report, accepted the
  result as sufficient for AUTO-002, explicitly directed that no additional independent review or
  findings search occur, and authorized lifecycle closure plus one local commit. This decision
  supersedes only the pending-review condition in DD-27 through DD-31; their technical decisions
  remain unchanged.
- **Consequences:** AUTO-002 moves to registry `COMPLETE` and task `Done`. No successor is
  authorized automatically. Out-of-scope observations remain future work. Push and merge remain
  prohibited by this closure instruction.
- **Reconsideration trigger:** none; later improvements require a separately authorized task.

## DD-33 — OD-2 resolved: secret handling is an environment allowlist plus regex output redaction

- **Status:** Accepted. AUTO-003 implementation decision, 2026-07-27. Resolves `OPEN_QUESTIONS.md`
  OD-2, which was recorded as blocking AUTO-003/AUTO-004 security hardening.
- **Context:** OD-2 asked whether secret handling should be regex-pattern-based redaction of known
  secret shapes, an allowlist-only environment capture, or both. Its recommendation was both.
  `SECURITY_MODEL.md` §1 already names both controls but left the implementation open. OD-2 is a
  question the stage contract (`stage-prompts/AUTO-003.md`) names AUTO-003 as resolving, so this
  is an implementation decision, not a Human Owner policy call — the same posture DD-10 took for
  OD-3 under AUTO-002.
- **Decision:** Implement both, with an explicit primacy ordering. The **environment allowlist is
  the primary control**: `skills/__init__.py::_build_environment` constructs each subprocess
  environment from `PATH`, pinned `LC_ALL`/`LANG`, interactive-prompt suppression, and only the
  variables a target repository's `allowed_environment_variables` names — nothing else in the
  operator's environment is forwarded. **Regex redaction is defense-in-depth**:
  `skills/__init__.py::redact_secrets` replaces known secret shapes with an opaque
  `[REDACTED:<kind>]` marker naming the pattern that matched, and is applied to every string
  leaving a Skill — failure details, command stdout/stderr, report payloads (recursively), and
  audit events.
- **Rejected alternative — entropy-based detection:** considered and deliberately not implemented.
  It would flag Git SHAs, content hashes, and base64 test fixtures, all of which this engine's own
  output is full of; a redactor that fires on ordinary output trains operators to ignore it. The
  patterns are therefore explicit and named rather than statistical.
- **Consequences:** Redaction is lossy, irreversible, and idempotent (re-redacting redacted text
  neither corrupts the marker nor leaks a fragment). It is explicitly *not* a guarantee: a secret
  with no recognizable shape and no label is not detectable by pattern alone, which is precisely
  why the allowlist — not the redactor — is the primary control. Every pattern is written to match
  in linear time, because redaction runs over untrusted target-repository output where a
  catastrophically backtracking pattern would be a reachable denial-of-service vector.
  `run_secret_detection` reuses the same shapes for the *opposite* purpose (failing the gate on a
  secret committed to the diff) and suppresses placeholder values so the gate stays trustworthy.
- **Reconsideration trigger:** a credential format in real use that the named patterns miss, or
  evidence that placeholder suppression is hiding a real finding.

## DD-34 — Skills return typed failures; destructive Git operations are structurally unreachable

- **Status:** Accepted. AUTO-003 implementation decision, 2026-07-27.
- **Context:** `SKILL_CONTRACTS.md` §7 requires every Skill to return a typed failure rather than
  raise, and `SECURITY_MODEL.md` §2 requires the forbidden Git operations to be unreachable *by
  construction* rather than refused at runtime. Both needed a concrete mechanism.
- **Decision:** (a) Every Skill returns `SkillResult[T]`, carrying either a value or a
  `SkillFailure` with a `FailureKind` and a `RetryClassification`; no Skill raises to the
  Orchestrator, and even a subprocess spawn failure becomes a record so the audit trail has no
  gaps. (b) `skills/repository.py` exposes only named functions whose mutating verb is a literal
  in that function's own argv tuple — there is no general "run a git command" entry point and no
  caller-supplied verb — so `--force`, `-D`, `reset`, `rebase`, and `commit --amend` have no
  expressible form. (c) Every ref-mutating Skill takes the baseline branch as a *required*
  parameter and refuses when its target equals it. (d) `delete_local_branch`/`delete_remote_branch`
  require a `MergeConfirmation` token with no default, so `SECURITY_MODEL.md` §5's
  "only after `verify_merge_completion`" precondition is unexpressible to violate rather than
  merely discouraged; the token's producer arrives in AUTO-006.
- **Consequences:** The prohibition is machine-checked, not review-dependent:
  `test_skills_repository.py::test_no_forbidden_argv_tokens` parses the module's own AST and fails
  if a forbidden token ever appears in a string literal. Retry classification follows
  `SKILL_CONTRACTS.md` §5 exactly — only a spawn failure is `PROVEN_PRE_SIDE_EFFECT`, and a
  timeout on a network-touching Skill is `POSSIBLE_SIDE_EFFECT`, never proven pre-effect.
- **Reconsideration trigger:** a Skill family that genuinely requires a caller-supplied Git verb,
  which would need its own security review.

## DD-35 — Branch-relative change sets use three-dot (merge-base) diff semantics

- **Status:** Accepted. AUTO-003 implementation decision, 2026-07-27.
- **Context:** `list_changed_files` and `inspect_diff` feed scope enforcement
  (`SECURITY_MODEL.md` §7). Two-dot and three-dot diff answer different questions, and the choice
  determines whether scope violations are attributed correctly.
- **Decision:** Both Skills use `base...branch` (three-dot, diff against the merge base).
- **Consequences:** The change set is what the stage branch *introduced*. Two-dot would also
  report everything that landed on the baseline after the branch was cut, so an unrelated baseline
  commit touching a forbidden path would be attributed to the stage and fail its scope gate. This
  is a deliberate divergence from `observation/evidence.py::changed_paths`, which uses two-dot
  because it answers a different question — the exact path set between two specific commits.
- **Reconsideration trigger:** a workflow that needs the absolute two-commit path set for scope.

## DD-36 — `create_commit` stages the working tree's current diff rather than a caller-supplied path list

- **Status:** Accepted. AUTO-006 implementation decision, 2026-07-28.
- **Context:** `SKILL_CONTRACTS.md` §5's table names "staged allowed paths, commit message" as
  `create_commit`'s input, implying the caller stages specific paths before invoking it. But
  `GitAgent.create_commit` (`agents/git.py`, delivered by AUTO-005) calls this Skill with only
  `repository_path`, `branch`, `message`, and `expected_head_sha` — no path list — and modifying
  `agents/git.py` is outside AUTO-006's allowed files (`stage-prompts/AUTO-006.md`: only
  `agentos_workflow/skills/git_github.py`, `agentos_workflow/tests/**`, and SSP-required
  documentation). No other Agent has a Skill capability that stages files either
  (`AGENT_SKILL_CONTRACTS`, `agents/__init__.py`), so nothing upstream of `create_commit` ever
  runs `git add`.
- **Decision:** `create_commit` treats "the input" as the working tree's current diff: it runs
  `git add -A` (after re-verifying `expected_head_sha` and the current branch), then commits
  whatever that staged. This is safe by construction at the point this Skill is ever reachable
  (`READY_TO_COMMIT`, reached only after the `VALIDATING` gate's `run_scope_validation` has
  already passed, `MACHINE_GATES.md` §3): the working tree's diff and the allowed-path diff are
  the same set of files by the time this Skill runs, so "stage everything currently changed" and
  "stage the allowed paths" coincide.
- **Consequences:** `create_commit`'s actual call shape (as `GitAgent` already exercises it in
  `test_agents_git_merge.py`) is honored without touching AUTO-005's Agent code. The idempotency
  check (`_reused_commit`) is correspondingly a bit more work than "same paths, same message":
  it confirms `HEAD`'s parent equals `expected_head_sha`, the tree is clean, and the commit
  subject matches, before treating a repeated call as a safe no-op.
- **Reconsideration trigger:** a future stage giving `ImplementationAgent` or `GitAgent` its own
  staging Skill, at which point `create_commit` should accept an explicit path list instead and
  refuse to stage anything itself.

## DD-37 — OD-1 resolved: native GitHub auto-merge, never engine-side polling merge

- **Status:** Accepted. AUTO-006 implementation decision, 2026-07-28, resolving OD-1
  (`OPEN_QUESTIONS.md`).
- **Context:** OD-1 asked whether `enable_automatic_squash_merge` should use GitHub's native
  `gh pr merge --auto --squash` (which waits server-side for required checks) or have the engine
  poll `read_required_checks` itself and issue a plain squash merge once green. The stage
  contract (`stage-prompts/AUTO-006.md`) already named the native form as the intended
  resolution.
- **Decision:** `enable_automatic_squash_merge`'s only merge-enabling call is
  `gh pr merge <number> --auto --squash`, after re-verifying the PR's current head SHA against
  GitHub itself immediately before that call (`SECURITY_MODEL.md` §5's "destructive Skills
  re-verify their precondition immediately before execution", applied here even though this
  Skill sits outside §5's originally-named list, because enabling auto-merge is an irreversible
  GitHub-side state change). `read_required_checks` remains implemented and is used for the
  engine's own `WAITING_FOR_CHECKS` visibility, exactly as OD-1's recommendation described, but
  it never gates or substitutes for GitHub's own merge decision.
- **Consequences:** No engine-side polling-then-merge loop exists; GitHub's branch protection is
  the sole authority over when the squash merge actually happens once auto-merge is enabled.
  `enable_automatic_squash_merge` has exactly one `gh pr merge` call site in the module's source,
  asserted by `test_skills_git_github.py::test_exactly_one_merge_enabling_call_site` over the
  module's own AST — the same structural-proof technique `SECURITY_MODEL.md` §4's no-admin-bypass
  claim already uses elsewhere in this program.
- **Reconsideration trigger:** a target repository whose branch protection does not support
  native GitHub auto-merge, which would need a documented fallback to engine-side polling.

## DD-38 (discovered, not resolved by this stage) — five of eight Git/GitHub Skill calls never receive `allowed_environment_variables`

- **Status:** Recorded as a discovered gap; not fixed in this stage. Requires its own Human Owner
  decision. See `OPEN_QUESTIONS.md` OD-10.
- **Context:** While self-reviewing this stage's diff against `GitAgent`/`MergeAgent`'s actual
  call sites (`agents/git.py`, `agents/merge.py`, delivered by AUTO-005), five of the eight
  Skills this stage binds are invoked without `allowed_environment_variables` at all:
  `create_pull_request`, `read_pull_request_state` (`GitAgent`), and
  `enable_automatic_squash_merge`, `read_required_checks`, `verify_merge_completion`
  (`MergeAgent`). Every one of those five is a `gh` invocation. Only `push_stage_branch`
  (`GitAgent`) forwards `self._allowed_environment_variables`; `create_commit` and
  `verify_head_sha` are local-only and do not need it.
- **Why this matters:** `_build_environment` (`skills/__init__.py`) forwards *only* `PATH` plus
  the caller-supplied allowlist to every Skill subprocess — never the operator's full
  environment, and never `HOME` unless it is itself allowlisted (`SECURITY_MODEL.md` §1). `gh`
  needs either a `GH_TOKEN`/`GITHUB_TOKEN` environment variable or a readable
  `$HOME/.config/gh/hosts.yml` to authenticate. With no `allowed_environment_variables` reaching
  the subprocess at all, none of those five Skills can authenticate to GitHub in a real
  deployment — they would fail every time, not merely under an edge case.
- **Why this stage does not fix it:** the fix is a one-line addition to each of five call sites in
  `agents/git.py`/`agents/merge.py`, which are `agentos_workflow/agents/**` — outside AUTO-006's
  allowed files (`stage-prompts/AUTO-006.md`). Per the Standard Stage Protocol, an unrelated
  problem discovered mid-stage is recorded, not fixed, when it needs a scope decision.
- **Recommended shape when authorized:** add `allowed_environment_variables=self._allowed_environment_variables`
  to the five call sites above, mirroring `push_stage_branch`'s existing call; `GitAgent` and
  `CloseoutAgent` already carry that field on `self`, so `MergeAgent` would need the same
  constructor parameter added. Small, mechanical, and testable against the existing
  `test_agents_git_merge.py` fakes by asserting the kwarg is now present in the recorded call.
- **Reconsideration trigger:** none — this is not a design choice awaiting new information, it is
  a known defect awaiting authorization to fix.

## DD-39 (discovered, not resolved by this stage) — `stage_contract_hash` format disagreement between `PMOAgent` and `LocalResumeObserver`

- **Status:** Recorded as a discovered gap; not fixed in this stage. Requires its own Human Owner
  decision. See `OPEN_QUESTIONS.md` OD-11.
- **Context:** While building AUTO-007's end-to-end dry run, `PMOAgent.check_preconditions`
  (`agentos_workflow/agents/pmo.py:201`) was found to compare `calculate_contract_hash`'s bare-hex
  `ContractHash.sha256` (`agentos_workflow/skills/contract.py`) directly against
  `authorization.stage_contract_hash`, while `LocalResumeObserver`
  (`agentos_workflow/observation/local.py:315`) — the live observer the production
  `resume_workflow`/`WorkflowSession.resume` path uses — computes and compares a
  `"sha256:<hex>"`-prefixed value for the identical semantic field.
- **Why this matters:** no single `AuthorizationRecord.stage_contract_hash` value can satisfy
  both comparisons. A bare-hex value passes `PRECONDITIONS_CHECKED` but any later real resume
  raises a false-positive `AuthorizationBindingDriftError`, durably failing the workflow and
  requiring fresh authorization (`HUMAN_AUTHORIZATION_MODEL.md` §4) even though nothing has
  actually drifted; a `"sha256:"`-prefixed value would instead fail `PRECONDITIONS_CHECKED` on the
  very first gate. Every real workflow that reaches `PRECONDITIONS_CHECKED` and is later resumed
  hits this.
- **Why neither existing test suite caught it:** `test_agents_pmo.py` hand-builds its
  `Authorization` fixture with a bare-hex hash (matching `PMOAgent`'s own convention);
  `test_engine_resume.py` hand-builds its `AuthorizationRecord` fixture with a
  `"sha256:deadbeef"`-prefixed literal (matching the resume path's convention). Each suite tests
  its own side in isolation and never checks the other's expectation, so the disagreement was
  invisible until a single session drove both `PMOAgent` and a real resume against the *same*
  authorization record — precisely what AUTO-007's dry run is for.
- **Why this stage does not fix it:** correcting either side touches
  `agentos_workflow/agents/**`, `agentos_workflow/skills/**`, or `agentos_workflow/observation/**`
  — all outside AUTO-007's allowed files (`stage-prompts/AUTO-007.md`). AUTO-007's own dry run
  test routes around the inconsistency with a test-only `calculate_contract_hash` wrapper
  (`agentos_workflow/tests/e2e/test_dry_run.py::_prefixed_contract_hash`) rather than touching
  production code.
- **Recommended shape when authorized:** standardize on the `"sha256:<hex>"`-prefixed form
  (`LocalResumeObserver`'s existing convention) and correct `PMOAgent.check_preconditions`'s
  comparison — either by updating `calculate_contract_hash` to emit the prefix, or by prefixing
  its result before comparison inside `pmo.py` — plus a new test that binds `PMOAgent` and a real
  resume to the same authorization record so the two can never again silently diverge.
- **Reconsideration trigger:** none — this is not a design choice awaiting new information, it is
  a known defect awaiting authorization to fix.

## DD-40 — Attempt-aware report artifact names, inside the workflow's own audit directory

- **Status:** Accepted. Implemented by GOV-3 (`docs/TASK_QUEUE.md`), the ordinary engine task the
  Human Owner recorded when approving AUTO-005 rather than fixing that limitation in scope.
- **Context:** The four `_generate_report` callers in `agentos_workflow/skills/reporting.py`
  (AUTO-003) wrote to a fixed `<audit_root>/<workflow_id>/reports/<kind>.json` — one artifact per
  workflow per kind — and correctly refused to overwrite an existing artifact whose content
  differed (`AUDIT_MODEL.md`'s append-only semantics). But the bounded repair loop
  (`FAILURE_RECOVERY.md` §1) runs several QA rounds and implementation attempts per workflow, each
  with its own verdict, findings, and diff, so the second round failed on the *artifact* rather
  than on the code under review. AUTO-005 could not touch `skills/**` and worked around it by
  deriving a per-attempt audit scope (`<workflow_id>.qa<N>`) inside `QAAgent`, which kept every
  artifact within the audit root but placed the rounds in sibling directories rather than in the
  workflow's own — not what `AUDIT_MODEL.md` intends, and not a shape to build on.
- **Decision:** Each of the four generators takes an optional `sequence`. When supplied, the
  artifact is named `<kind>.<sequence>.json` inside that workflow's own `reports/` directory;
  when omitted, the existing `<kind>.json` name is produced byte-identically, so every existing
  caller is unaffected. `sequence` is a validated integer (1..9999, `bool` explicitly excluded)
  rather than a caller-supplied string, so nothing a caller passes can widen what reaches a
  filename — everything `_validate_component` refuses for an identifier is unreachable here by
  construction. `QAAgent._report_scope` was deleted in the same change, so the Skill and its only
  caller cannot drift apart again.
- **Consequences:** Idempotency and the differing-content refusal stay **per artifact**: two
  different reports of the same kind *and* sequence still collide, which is the correct reading —
  that means a caller reused a round number, not that the append-only audit model needs relaxing.
  One such caller-side reuse is already known and is recorded, not resolved, as OD-12: the
  pre-loop QA round and the repair loop's own first internal round are both numbered attempt 1.
  Reports now also carry `report_sequence`, so an artifact read on its own says which round
  produced it.
- **Reconsideration trigger:** a workflow needing more than `_MAX_REPORT_SEQUENCE` (9999) reports
  of one kind, or an audit consumer needing the rounds addressable by something other than a
  monotonic integer.
