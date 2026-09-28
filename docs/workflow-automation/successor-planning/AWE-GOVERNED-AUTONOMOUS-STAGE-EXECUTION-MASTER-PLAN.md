# AWE Governed Autonomous Stage Execution — Master Architecture / Implementation Plan

> **PLANNING ARTIFACT — NOT AN AUTHORIZATION.**
> This document is the governing architecture artifact for ten future governed stages, AUTO-017 …
> AUTO-026.
> - The stages are **registered** in `docs/workflow-automation/STAGE_REGISTRY.md` §4 as `NOT_STARTED`
>   and in `docs/TASK_QUEUE.md` as `Planned` (OWNER decision OD-GSE-07, 2026-09-28).
> - Registration is not authorization. **No stage is authorized**, and this document authorizes nothing
>   and changes no code.
> - Each stage still requires its own stage contract, one bounded review, and its own separate written
>   OWNER authorization under `STAGE_REGISTRY.md` §3 and the Standard Stage Protocol, in the execution
>   order of §5.

| Field | Value |
|---|---|
| Baseline | `main` @ `e7dbb31a1469a8b371a7571a6d85424f20f0226a`, clean, empty index |
| Canonical subsystem | `src/ai_workflow_engine/milestone_runner/` |
| Sole transition authority | `MilestoneRunnerApplication` (`milestone_runner/application.py`) |
| Out of bounds for this lifecycle | `agentos_workflow/orchestrator`, legacy `src/ai_workflow_engine/workflow`, Hermes |
| Plan date | 2026-09-28 |
| Status | FINAL CANDIDATE, Revision 2 — governing architecture artifact for AUTO-017 … AUTO-026 (all `NOT_STARTED` / `Planned`, none authorized). Revision 2 remediates the frozen discovery findings AWE-GSE-R01 … R11 (§9). |
| Accepted OWNER decisions | OD-GSE-01, -02, -03, -06, -07, -12 (2026-09-28; §6.1; `docs/DECISION_LOG.md`) |
| Open OWNER decisions | OD-GSE-04, -05, -08, -09, -10, -11 (§6.2; each blocks only the stage named) |

### Registered stage mapping (OD-GSE-07)

Canonical IDs are the Registry IDs. The `AWE-AUTO-ST-NN` aliases are preserved for traceability only;
no governance tool parses them.

| Registry ID | Alias | Title | Execution predecessor (OD-GSE-12) |
|---|---|---|---|
| AUTO-017 | AWE-AUTO-ST-01 | Schema v2 + Stage Execution Policy | AUTO-016 (`COMPLETE`) |
| AUTO-018 | AWE-AUTO-ST-02 | Durable Lifecycle / Event Foundation | AUTO-017 |
| AUTO-019 | AWE-AUTO-ST-03 | Resume / Crash Recovery | AUTO-018 |
| AUTO-021 | AWE-AUTO-ST-05 | OWNER Decision API | AUTO-019 |
| AUTO-020 | AWE-AUTO-ST-04 | 1..3 Bounded Remediation Cycles | **AUTO-021** |
| AUTO-022 | AWE-AUTO-ST-06 | Per-role AI / Provider / Model Selection | AUTO-020 |
| AUTO-023 | AWE-AUTO-ST-07 | Hermes Execution Adapter | AUTO-022 |
| AUTO-024 | AWE-AUTO-ST-08 | Authenticated OWNER Decision Contracts | AUTO-023 |
| AUTO-025 | AWE-AUTO-ST-09 | Hermes Telegram Decision Transport | AUTO-024 |
| AUTO-026 | AWE-AUTO-ST-10 | Controlled Git Automation (last) | AUTO-025 |

The rows are listed in execution order. The numbering is preserved (OD-GSE-12), so AUTO-021 executes
before AUTO-020.

**Execution-predecessor semantics (R03).** These are canonical in `STAGE_REGISTRY.md` v7.0, §3 rules 1 and
10, and the SSP v1.4, "Stage Ordering".

- A stage's *execution predecessor* is the numerically preceding stage, unless an OWNER decision recorded
  in `docs/DECISION_LOG.md` and `STAGE_REGISTRY.md` §5 defines it otherwise.
- For AUTO-017..AUTO-026, OD-GSE-12 defines it through the table above. In particular, the execution
  predecessor of AUTO-021 is AUTO-019, and that of AUTO-020 is AUTO-021.
- A stage is never authorized until its execution predecessor is `COMPLETE`.
- The registry, the SSP, `docs/TASK_QUEUE.md` and this plan state one and the same rule.

---

## 0. Reading Guide

- §1 records what exists today, found by reading the code. Every design choice later refers back to it.
- §2 is the target architecture: components, state machine, durable model, and invariants.
- §3 separates what may be *built* early from what may only be *enabled* after full autonomy.
- §4 defines the ten stages, each in the same fixed template.
- §5 gives the dependency chain.
- §6 records the six OWNER decisions accepted on 2026-09-28 (§6.1). It also lists the six that remain OPEN (§6.2), each with the stage it blocks; none of those is decided here.
- §7 covers the governance-registration mechanics that all ten stages share.

Terminology. **Stage** means a project stage whose implementation AWE governs; today the runner calls this
`stage.stage_id`. **Run** means one execution of one Stage under one frozen policy. **OWNER** means the
Human Owner, whose authority is defined in `HUMAN_AUTHORIZATION_MODEL.md`. The four roles in this program
correspond to the existing `ProviderRole` members like this:

| Program role | Existing `ProviderRole` | Existing invoking `RunStatus` |
|---|---|---|
| `IMPLEMENTER` | `IMPLEMENTATION` | `IMPLEMENTING` |
| `DISCOVERY_REVIEWER` | `REVIEW` | `REVIEWING` |
| `REMEDIATOR` | `CORRECTION` | `CORRECTING` |
| `CLOSURE_VERIFIER` | `CLOSURE` | `CLOSURE_VERIFYING` |

The plan keeps the existing enum values as the persisted wire vocabulary and adds the program names as a
documented alias mapping, not as a rename. A rename would invalidate every persisted v1 record and every
existing test for no gain in safety.

---

## 1. Current-State Evidence (read directly from `main` @ `e7dbb31`)

| # | Fact | Where | Consequence for this program |
|---|---|---|---|
| E1 | The runner has an 18-member runner-local `RunStatus`. `ALLOWED_RUN_TRANSITIONS` is a closed frozenset that tests assert member by member. `DONE` and `ABORTED` are terminal. `HUMAN_INTERVENTION_REQUIRED` exits only through four recovery commands or through `abort`. | `models.py` (RunStatus, ALLOWED_RUN_TRANSITIONS) | Every new state and edge is a contract amendment plus a test-table change. There is no `OWNER_DECISION_REQUIRED` state and no edge from `CLOSURE_VERIFYING` back to `NEEDS_CORRECTION`. |
| E2 | The review budgets have hard ceilings: `MAX_FULL_REVIEWS_CEILING = 1`, `MAX_CORRECTION_ROUNDS_CEILING = 1`, `MAX_CLOSURE_REVIEWS_CEILING = 1`, `MAX_BLOCKERS_CEILING = 3`. | `config.py:90-93` | A remediation budget of 1..3 cycles is impossible today. Because ST-05 executes first (OD-GSE-12), the ceilings move in two contract amendments. ST-05 admits up to 2 OWNER-authorized extension rounds beyond the automatic budget, which stays fixed at 1 in ST-05. ST-04 then raises the automatic correction and closure ceilings to 3. The full-review ceiling stays at 1 throughout. |
| E3 | Blocking severities must include CRITICAL and HIGH. A configuration may promote MEDIUM or LOW to blocking and may never demote. Deferred findings go to `deferred_findings` and never block. | `config.py` ReviewPolicySettings validator; `models.py` BLOCKING/DEFERRED_SEVERITIES | Severity promotion already exists. What is not defined is how non-blocking findings are handled beyond recording them (OD-GSE-01). |
| E4 | A review result with more than `max_blockers` blockers is rejected as **malformed**. It routes to `_provider_failure` and then to `HUMAN_INTERVENTION_REQUIRED`. | `models.py` §18 note; `application.py::_review` | An overflowing discovery review ends up in the same state as a crashed provider. The finding set is lost as evidence (OD-GSE-02). |
| E5 | The provider binding is fixed: Claude handles IMPLEMENTATION and CORRECTION, and Codex handles REVIEW and CLOSURE with a fixed read-only sandbox. `ProviderBinding.from_config` holds one adapter per role family. | `application.py::ProviderBinding`, `providers/` | Per-role model selection (ST-06) needs a generalized role→adapter binding and model provenance. |
| E6 | Durable state is a single `state.json` projection, published atomically (temp file, fsync, `os.replace`, fsync of the directory). **No separate append-only event log exists**, although contract §11 describes one ("the event log and the audit ledgers are separate append-only streams"). | `state.py::publish_atomically`, `RunStateStore.publish` | ST-02 builds the event stream that §11 anticipated. |
| E7 | The only durable pre-dispatch evidence is `ProviderInvocationIntent` (a fingerprint and a sequence). Resume reinvokes a provider only when the fingerprint shows the repository content is byte-identical. | `state.py::ProviderInvocationIntent`, `_reconcile` | This is a sound base for the in-flight window, and ST-03 generalizes it. |
| E8 | **Crash gap A (found by inspection, not yet reproduced by a test).** `_invoke_provider` publishes the *completed* provider run in the origin state, and only after that does `_review`, `_correct` or `_verify_closure` parse and accept the result. If the process crashes between those two publications, resume sees `completed_at` set, returns `ResumeAction.CONTINUE`, and `_resume_from` calls the step again, which **re-invokes the provider**. For `CORRECTING` that repeats an effectful remediation. For `REVIEWING` it produces a **second discovery review**. | `application.py::_invoke_provider`, `_review`, `_correct`, `_resume_from`; `state.py::_reconcile` | This is direct evidence for the required phases "result received → validated → persisted → transition applied". ST-02 and ST-03 must close the gap, and ST-03 must include a regression test that reproduces it first. |
| E9 | **Crash gap B (found by inspection).** `_review` increments `review_attempts` on every entry, including a re-entry on resume. Nothing durable records that a received-but-unaccepted review result exists. | `application.py::_review` | "Exactly one discovery review" is enforced only on *accepted* rounds (`successful_review_rounds`). Nothing prevents a second provider call when the first call's result was received but never accepted. |
| E10 | The stage ID grammar is `AUTO-[0-9]{3}` and the milestone grammar is `AUTO-[0-9]{3}-M[0-9]{2}`. | `config.py:69`, `models.py` | Project Stage IDs such as `ST-07` and program IDs such as `AWE-AUTO-ST-01` are both rejected today (OD-GSE-07; ST-01 generalizes the grammar). |
| E11 | Stage authorization is checked by reading `STAGE_REGISTRY.md` for `AUTHORIZED` or `IN_PROGRESS`. No AWE-native, durable "OWNER start decision" record exists. | `application.py::_registry_authorizes`, `run_preflight` | "Each Stage starts only after an explicit OWNER start decision" needs a durable `StageStartAuthorization` (OD-GSE-06). |
| E12 | The commit and push gates are double-gated (a config flag defaulting to false plus a typed interactive confirmation), bound, single-use, and invalidated on drift. `self-governance.yaml` sets `allow_automatic_commit: false` and `allow_automatic_push: false`. `HUMAN_AUTHORIZATION_MODEL.md` §5a constraint 6 says automatic approval is opt-in only at the point of use. | `approval_git.py`, `application.py::_approve`, `self-governance.yaml` | Automatic commit in ST-10 conflicts with the established mandatory human gate (OD-GSE-04). |
| E13 | `agentos_workflow/approvals.py` has `ApprovalChannel.TELEGRAM` "as a policy value only". `ARCHITECTURE.md` §4 forbids `src/` from importing `agentos_workflow` internals, and DEC-016-002 forbids reuse of the `agentos_workflow` provider runtime. | `agentos_workflow/approvals.py:158-165` | The decision API (ST-05) and the Telegram transport (ST-09) must be built inside `milestone_runner/`. Neither may import `agentos_workflow.ApprovalService`. |
| E14 | A `RunLock` built on `fcntl.flock` is held by every state-mutating command. It allows one runner per canonical repository. | `lock.py` | Decision application (ST-05/08) and Hermes result ingestion (ST-07) must acquire the same lock. The lock already covers concurrency within a repository. |
| E15 | Redaction happens at the single write boundary (`write_redacted_artifact`), reusing `successor_planning.redaction.redact_text`. | `state.py`, contract §17a | Every new durable artifact must pass through that boundary: envelopes, results, decision messages, and Telegram payload copies. |
| E16 | T-307 introduced `CanonicalEngineProvenance`, which records the engine version, HEAD, install mode and worktree cleanliness, and fails closed on a dirty editable engine. | `src/ai_workflow_engine/provenance.py` | Model provenance (ST-06) and envelope provenance (ST-07) should include the engine provenance rather than invent a parallel one. |
| E17 | Several documents still said the T-307 closeout was "uncommitted pending … final-commit authorization", but HEAD `e7dbb31` *is* the T-307 commit: `docs/current_task.md`, `docs/PROJECT_STATE.md`, `docs/TASK_QUEUE.md`, `docs/remaining_tasks.md` and `docs/CHANGELOG.md`. `workflowctl verify` passed regardless, because the drift was in prose, not in any parsed status. | those files | **Reconciled (EP-3, 2026-09-28).** The live mirror statement in `docs/current_task.md` was corrected. Dated, append-only reconciliation notes were added elsewhere. No historical record was rewritten. |

---

## 2. Target Architecture

### 2.1 Authority model (unchanged principle, extended surface)

```text
OWNER ──(StageStartAuthorization, DecisionResponse)──►  AWE  ◄──(StructuredResult)── Hermes ◄── selected AI/model
                                                       │
                                     MilestoneRunnerApplication  (sole transition authority)
                                                       │
     ┌──────────────┬──────────────┬───────────────┬───┴───────────┬──────────────┬───────────────┐
  PolicyResolver  EventStore   OperationJournal  RecoveryReconciler  CycleCoordinator  DecisionService
  (ST-01/06)      (ST-02)      (ST-02)           (ST-03)             (ST-04)           (ST-05/08)
                                                       │
                          ExecutionPort (ST-07)  ─ LocalCliAdapter (existing) / HermesExecutionAdapter
                          DecisionTransportPort (ST-09) ─ LocalCliTransport / HermesTelegramTransport
                          GitAutomation (ST-10)  ─ evolves approval_git.py, still the only mutating-Git module
```

Rules that every stage inherits:

1. **AWE decides; everything else is evidence.** Hermes, Telegram, providers, and the transports never
   transition a run, never mint a decision ID, never choose an option, and never write to the state root.
   They deliver bytes, and AWE validates them.
2. **No Hermes workflow state machine.** Hermes receives one `RunEnvelope`, executes one role invocation,
   and returns one `StructuredResult`. It has no knowledge of the next step.
3. **No automatic next Stage (R11).** Nothing in AWE constructs a `StageStartAuthorization` on its own
   initiative. It is created only by ingesting an OWNER-initiated `START_STAGE <stage-id>` command, which
   names the Stage ID explicitly under OWNER authority. The terminal states `DONE`, `ABORTED` and
   `SUPERSEDED` have no outbound edge. No code path selects, reads, derives, recommends or solicits a
   successor Stage. A post-completion message may state generically that another Stage *can* be started by
   an explicit OWNER `START_STAGE <stage-id>`, but it names no Stage, carries no pre-filled Stage ID, and
   creates no pending decision.
4. **One discovery review per run.** The discovery-review ceiling stays fixed at 1 and cannot be
   configured.
5. **Bounded remediation.** Automatic cycles are capped by the frozen `max_remediation_cycles` (1..3) plus
   OWNER-granted extensions, each of which is exactly one cycle.

### 2.2 Run state machine additions (runner-local `RunStatus`; never a `WorkflowState`)

New members:

| State | Meaning | Exits |
|---|---|---|
| `OWNER_DECISION_REQUIRED` | The run is frozen, and exactly one durable `PendingDecision` exists. No automatic step executes. | Only by applying a validated `DecisionResponse`: → `NEEDS_CORRECTION` (EXTEND_REMEDIATION +1, or the RETRY_* options in §2.6); → `ABORTED` (ABORT_STAGE); → `SUPERSEDED` (AMEND_STAGE_CONTRACT). `KEEP_FROZEN` applies **no transition**: it records the response and stays in this state. |
| `SUPERSEDED` | Terminal. The run was left for an amended contract. | None. |

New edges (the full set is frozen in the ST-04 and ST-05 contracts and asserted member by member):

- `CLOSURE_VERIFYING → NEEDS_CORRECTION`. Allowed only when OPEN blockers remain **and**
  `completed_remediation_cycles < authorized_remediation_cycles`.
- `CLOSURE_VERIFYING → OWNER_DECISION_REQUIRED`. Taken on retry exhaustion (`on_retry_exhausted = ask_owner_and_freeze`).
- `<every live state> → OWNER_DECISION_REQUIRED`. Taken on ambiguous or unsafe recovery (ST-03).
- `REVIEWING → OWNER_DECISION_REQUIRED`. Taken on discovery overflow (accepted OD-GSE-02) and on a
  malformed discovery result.
- `OWNER_DECISION_REQUIRED → NEEDS_CORRECTION | ABORTED | SUPERSEDED`.
- There is **no** edge from `OWNER_DECISION_REQUIRED` back to `REVIEWING` (R02). A malformed or ambiguous
  discovery can never cause a second discovery invocation within the same run, which is the same
  review-cycle identity. A fresh discovery happens only in a new run, which requires
  `AMEND_STAGE_CONTRACT` and a fresh `START_STAGE`.
- There is **no** edge from `OWNER_DECISION_REQUIRED` to `READY_FOR_COMMIT_APPROVAL` and no edge to any Git
  state. The frozen-run invariant is therefore structural, as §13 already made it for
  `HUMAN_INTERVENTION_REQUIRED`.

`HUMAN_INTERVENTION_REQUIRED` stays as it is. It remains the *safety stop*, entered on a failed gate or on
drift and cleared by the existing recovery commands. `OWNER_DECISION_REQUIRED` is the *policy stop*,
cleared only by a typed decision. They are kept separate because their exits have different authority
semantics: a recovery command is an operator repair, while a decision response is an OWNER policy choice
carrying the authentication that ST-08 adds.

### 2.3 Durable model (run directory, v2)

```text
~/.ai-workflow-engine/milestone-runs/<repository-id>/
    project-defaults.json                 (ST-01; optional; OWNER-maintained, schema v2)
    stage-starts/<stage-start-id>.json    (ST-01/05; StageStartAuthorization, immutable)
    <run-id>/
        state.json            projection, schema_version 2 (rebuildable from events/)
        policy.json           EffectiveStageExecutionPolicy (immutable, digest-pinned)
        events/NNNNNNNN-<type>.json       append-only, one atomic file per event, hash-chained
        operations/<operation-id>/        request.json, dispatch.json, result.raw (redacted),
                                          result.validated.json, applied.json
        decisions/<decision-id>/          request.json (immutable), deliveries/, responses/, applied.json
        transcripts/ plan.json run.lock provider-intent.json     (existing)
```

**Why one file per event and not a JSONL append.** An appended line can be torn by a crash. A file per
event, published with the existing `publish_atomically` discipline and named by a gap-free sequence
number, is either fully present or absent. A gap or a hash-chain break is detected on load and treated
as corruption, which forces `HUMAN_INTERVENTION_REQUIRED`. The system never guesses.

**Projection rule.** `events/` is the source of truth, and `state.json` is a cache. On load the store folds
the events and compares the result with `state.json`. If they disagree, the projection is rebuilt only
when the event chain verifies. If the chain does not verify, the run stops.

### 2.4 Operation phase ladder (closes E8/E9)

Every role invocation, and every other effectful step (verification set, Git action), is an
**Operation**. Its `operation_id` is derived deterministically as
`sha256(run_id | step_kind | cycle_no | role | slot)`, so restarting cannot mint a different identity for
the same logical step.

| Phase | Durable artifact | Recovery when this is the highest phase present |
|---|---|---|
| `REQUEST_CREATED` | `request.json`: envelope digest, policy digest, role binding, pre-fingerprint | No process has been created and no dispatch was attempted. Proceed to `DISPATCH_INTENT`, after re-checking pins. (For Git operations this phase carries no such guarantee; see the R09 note below.) |
| `DISPATCH_INTENT` (**pre-spawn**, R02) | `dispatch-intent.json`: operation ID, attempt number, adapter, argv/envelope digest and pre-fingerprint. It is written and fsynced **before** process creation or remote submission. | Dispatch may or may not have happened. **Adapter that is not idempotently queryable (local CLI):** no automatic redispatch. Go to `OWNER_DECISION_REQUIRED` (`AMBIGUOUS_RECOVERY`), with the fingerprint comparison attached as *evidence only*. The one exception is an attempt whose durable outcome `PRE_SPAWN_FAILED` was recorded, which may retry within the existing bounded retry. **Idempotently queryable adapter (Hermes, per EP-1):** query by `request_id`, and adopt or recover the original execution; never submit blindly. |
| `DISPATCH_RECEIPT` (**post-spawn acknowledgment**) | `dispatch-receipt.json`: local process start (pid and start time) or Hermes acceptance ID | The execution started. The same rules as `DISPATCH_INTENT` apply: a local adapter goes to `OWNER_DECISION_REQUIRED`, and a queryable adapter queries and recovers. A receipt never licenses redispatch. |
| `RESULT_RECEIVED` | `result.raw` (redacted) plus its digest | **Never re-dispatch.** Re-validate the stored bytes. Validation is deterministic. |
| `RESULT_VALIDATED` | `result.validated.json`: typed result and validation verdict | Apply from the stored validated result. |
| `RESULT_PERSISTED` | Event `OPERATION_RESULT_ACCEPTED` appended (findings, counters) | Apply the pending transition. |
| `TRANSITION_APPLIED` | Event `STATE_TRANSITIONED` with `state_version+1`; `applied.json` | Complete. Continue with the next step. |

An invalid result, whether malformed or out of scope, is also a terminal validation verdict. It is
persisted and never re-requested silently. The existing routing to a stop still applies, now expressed
as `OWNER_DECISION_REQUIRED` with the §2.6 options. No option re-dispatches a discovery operation.

**Supersession of AUTO-016 `REINVOKE_PROVIDER` for policy-governed runs (R02).** The AUTO-016 resume rule
re-invokes a local provider when the pre-invocation fingerprint is unchanged (E7). That rule is **not**
carried into v2 policy-governed runs. An unchanged fingerprint proves nothing about a read-only role, such
as discovery or closure, that may already have executed. It also proves nothing about effects outside
the fingerprinted paths. Ambiguous post-intent recovery therefore freezes for the OWNER. AUTO-016 v1
supervised runs keep their authorized behavior unchanged. The AUTO-019 contract amends AUTO-016 §13 for
v2 runs only.

**Git operations (R09).** For a Git operation, "no process was created" does **not** mean "nothing
happened", because index preparation mutates `.git/index`. Git operations use the dedicated ladder in
AUTO-026 (§4). There, durable intent is persisted before any index mutation, and each phase's recovery is
stated separately.

### 2.5 Cycle model (ST-04)

- **Discovery.** Exactly one accepted `DISCOVERY_REVIEWER` operation per run. If it accepts zero blocking
  findings, the run takes the success path. If it accepts one or more, AWE appends the event
  `FINDING_SET_FROZEN {finding_ids, digest, review_operation_id}`. From then on no event may add, remove
  or rename a blocking finding ID.
- **Severity policy (accepted OD-GSE-01).** CRITICAL and HIGH are blocking. MEDIUM and LOW stay
  deferred and non-blocking. They are recorded in `deferred_findings`, surfaced in every decision
  message and completion report, **never** passed to the `REMEDIATOR`, and never verified by the
  `CLOSURE_VERIFIER`. Only frozen blocking findings enter remediation. The frozen policy fixes
  `blocking_severities = {CRITICAL, HIGH}` and `defer_severities = {MEDIUM, LOW}`. A runner
  configuration that promotes MEDIUM or LOW to blocking, which the AUTO-016 validator allows (E3), is
  refused for a policy-governed run (`INVALID_CONFIGURATION`), because it would contradict OD-GSE-01.
- **Blocker ceiling (accepted OD-GSE-02).** `max_blockers` stays configurable, with the unchanged range
  `1..3` and a **default of 3**, and it is frozen in the policy. A discovery result carrying more
  blocking findings than the frozen ceiling is **not** malformed and does **not** invalidate the one
  discovery review. AWE persists it in full as evidence and counts it as the run's one discovery
  review, then moves to `OWNER_DECISION_REQUIRED` with decision kind `DISCOVERY_OVERFLOW`. No finding
  set is frozen and no remediation starts.
- **Cycle *k*.** A `REMEDIATOR` operation (effectful) runs, then the post-remediation verification set,
  then a `CLOSURE_VERIFIER` operation (read-only). The closure result may only map frozen IDs to
  `OPEN` or `CLOSED`. A result that names an unknown ID, or that carries a new finding, is rejected as
  malformed. This is today's `parse_closure_result(open_finding_ids=…)` rule, generalized.
- **Completed cycle.** A cycle is complete exactly when both `REMEDIATION_RESULT_ACCEPTED(k)` and
  `CLOSURE_RESULT_ACCEPTED(k)` are durable. `completed_remediation_cycles` is *derived* from the events
  and never stored as an independent counter, so it cannot drift from them.
- **Decision after closure *k*.** If all frozen blockers are CLOSED, take the success path. If some are
  OPEN and `k < authorized_remediation_cycles`, emit `CYCLE_SCHEDULED(k+1)` and move to
  `NEEDS_CORRECTION`. If some are OPEN and `k == authorized_remediation_cycles`, emit
  `RETRY_EXHAUSTED` and `DECISION_REQUESTED`, then move to `OWNER_DECISION_REQUIRED`.
- `authorized_remediation_cycles = policy.max_remediation_cycles + Σ(applied EXTEND_REMEDIATION)`. It is
  derived from events and never edited.

### 2.6 Decision model (ST-05, authenticated in ST-08, transported in ST-09)

`DecisionRequest` is immutable and persisted before any delivery. Its fields are `decision_id`, `run_id`,
`project`, `repository_identity`, `stage_id`, `decision_kind`, `reason_code`, `reason_text`,
`workflow_state`, `state_version`, `evidence` (typed, bounded, redacted), `allowed_options[]` (each with
option code, exact reply syntax, and effect), `recommended_option`, `recommendation_rationale`,
`created_at`, `request_digest`.

- **Decision ID.** `D-<StageId>-<NNN>`, where `NNN` is the per-Stage decision sequence allocated *inside*
  the `DECISION_REQUESTED` event. Because the ID is persisted as part of the event that entered the
  state, a restart re-reads it and never re-derives it.
- **Allowed options are frozen at request time** and covered by `request_digest`. After a restart the
  rendered message is re-derived deterministically from the persisted request, which makes it
  byte-identical.
- **Decision kinds and their option sets:**

| Decision kind | Allowed options |
|---|---|
| `RETRY_EXHAUSTED` | `EXTEND_REMEDIATION +1` (offered only while `extensions_applied < 2`, per accepted OD-GSE-03), `KEEP_FROZEN`, `ABORT_STAGE`, `AMEND_STAGE_CONTRACT` |
| `AMBIGUOUS_RECOVERY` (ST-03) | `KEEP_FROZEN`, `ABORT_STAGE`, `AMEND_STAGE_CONTRACT`, plus `ADOPT_OBSERVED_STATE` only where ST-03 defines it safe |
| `DISCOVERY_OVERFLOW` (accepted OD-GSE-02) | `KEEP_FROZEN`, `ABORT_STAGE`, `AMEND_STAGE_CONTRACT`. There is no retry: the overflowing review *is* the run's one discovery review. |
| `DISCOVERY_MALFORMED` (the result is unparseable or invalid; it is persisted as evidence) | `KEEP_FROZEN`, `ABORT_STAGE`, `AMEND_STAGE_CONTRACT`. There is **no** retry: the dispatched discovery operation *is* the run's one discovery (R02). |
| `POST_REMEDIATION_VERIFICATION_FAILED` | **OPEN, per OD-GSE-09.** The option set is fixed by the ruling, before AUTO-020 (ST-04). |

- **`START_STAGE` is not a decision kind (R11).** It is an OWNER-initiated command,
  `START_STAGE <stage-id> [overrides]`, with an explicit Stage ID. AWE never issues a `DecisionRequest`
  for it and never proposes which Stage to start.
- **Single-option rule.** If exactly one option is valid, the message states it as the exact required
  response.
- **`KEEP_FROZEN`** is recorded as a response, but the decision stays pending: the same decision ID stays
  open and the same options stay valid. The OWNER can answer again later with another option. This
  meets "remain frozen; execute nothing" without minting new IDs.
- **`AMEND_STAGE_CONTRACT`** moves the run to terminal `SUPERSEDED`. The run cannot be resumed, and the
  worktree is not touched. Worktree disposition is **OPEN, per OD-GSE-10**, and blocks AUTO-021 (ST-05). A new run requires a new contract revision, with a new
  `contract_sha256`, and a fresh `START_STAGE` decision.

**Canonical message rendering.** The renderer is pure and transport-neutral. Hermes and Telegram receive
the rendered text and the structured request, and neither may reword the options.

```text
OWNER DECISION REQUIRED
Project: <project> (<repository_identity>)
Stage: <stage_id>        Run: <run_id>        Decision ID: <decision_id>
State: OWNER_DECISION_REQUIRED (state_version <n>)
Reason: <reason_text>
Completed cycles: <k> / <authorized>
Open findings: <id — severity — title> …
Closed findings: …
Evidence: <digest-referenced summaries>
Allowed responses:
  1. EXTEND_REMEDIATION +1   Effect: …
  …
Recommended response: <option>
Reason: <rationale>
Reply exactly with one of:
  <decision_id> EXTEND_REMEDIATION +1
  <decision_id> KEEP_FROZEN
  …
(ST-08 onward: a reply must also carry the attestation token described in the request.)
```

### 2.7 Invariants (program-wide; each needs a named negative test in the stage that introduces it)

- **INV-01.** Only `MilestoneRunnerApplication` appends `STATE_TRANSITIONED` events. An AST test shows no
  other module calls the event-append API with a transition type.
- **INV-02 (R02).** Discovery cardinality is counted by **dispatched discovery operations**, not by
  accepted results. At most one `DISCOVERY_REVIEWER` operation per run may ever reach `DISPATCH_INTENT`.
  Inside that one operation, a second attempt is permitted only when the prior attempt's durable outcome
  is `PRE_SPAWN_FAILED`: the OS refused process creation, so no provider ever executed. That outcome is
  recorded synchronously before any retry. A malformed, overflowing, lost or ambiguous discovery never
  produces another discovery dispatch in the same run.
- **INV-03.** Every blocking-finding ID in any event after `FINDING_SET_FROZEN` belongs to the frozen set.
- **INV-04.** `completed_remediation_cycles ≤ authorized_remediation_cycles ≤ max_remediation_cycles + extensions_applied`,
  and `extensions_applied ≤ 2`. Each applied `EXTEND_REMEDIATION +1` adds exactly one
  remediation/closure cycle (accepted OD-GSE-03). The absolute maximum is
  `max_remediation_cycles + 2 ≤ 5`.
- **INV-05.** No automatic step and no Git action runs while the state is `OWNER_DECISION_REQUIRED` or
  `HUMAN_INTERVENTION_REQUIRED`, or while a `PendingDecision` exists.
- **INV-06.** An operation holding a `RESULT_RECEIVED` artifact is never re-dispatched.
- **INV-07.** `EffectiveStageExecutionPolicy` is immutable for the life of the run. Its digest is bound
  into every envelope, event, decision, and approval.
- **INV-08.** A decision ID, together with its allowed-option set, is stable across restarts, with byte
  equality of `request.json`.
- **INV-09.** A response is applied at most once. Its nonce (ST-08) is consumed at most once. A response
  whose `state_version` differs from the pending decision's is refused.
- **INV-10.** No code path creates a `StageStartAuthorization` except the ingestion of a validated
  OWNER `START_STAGE` response.
- **INV-11.** Hermes and transport adapters have no write capability on the state root. This is
  structural in AWE and becomes an OS-level confinement requirement before enablement.
- **INV-12.** All existing AUTO-016 §22 invariants (1–20) continue to hold, including redaction at the
  single write boundary and the two-surface Git authority.

---

## 3. Build-Early vs. Enable-After-Full-Autonomy

**Full-autonomy enablement predicates (FA-1..FA-6).** Each one must be evidenced, not asserted:

| ID | Predicate | Delivered by |
|---|---|---|
| FA-1 | Authenticated OWNER decisions with authenticated attribution, integrity, replay protection, single use, state/version binding, and the expiry/revocation policy ruled under OD-GSE-05 | ST-08 |
| FA-2 | Approval isolation: no provider or Hermes process can read OWNER attestation verification material or write decision or state artifacts | ST-07 (process confinement) + ST-08 (verification material outside every provider's reach, in whatever form OD-GSE-05 rules) |
| FA-3 | Crash-safe governance transactions (event log plus phase ladder, with fault injection at every phase boundary) | ST-02 + ST-03 |
| FA-4 | Durable, idempotent Hermes execution | ST-07 |
| FA-5a | **Provider execution isolation** (R01). Every provider process, local CLI or Hermes-executed, runs under OS/runtime-enforced confinement that denies writes to the AWE state root (`~/.ai-workflow-engine/milestone-runs/**`, which holds state, events, operations, decisions and locks) and to any path outside the operation's allowed worktree paths. The evidence is a **negative isolation test at the OS/runtime level**: a hostile probe process, which is *not* a live provider, is launched through the production confinement wrapper and attempts each forbidden write; every attempt must fail. | **ST-07** (AUTO-023) |
| FA-5b | Git confinement: provider processes cannot run mutating Git against the worktree, and only `approval_git.py` can construct a mutating Git argv | **ST-10** (AUTO-026) itself (R08) |
| FA-6 | Restart, recovery, and concurrency verification suite (kill -9 at every phase boundary, duplicate delivery, two ingesters racing for the lock) | ST-03 (local) + ST-07/ST-09 (remote) |

The runner gains a derived `AutonomyReadiness` report. Each capability flag below is refused at load
unless the predicates it depends on are evidenced by the named stage's completion marker **and** the
OWNER opts in at Stage start. Opt-in at the point of use follows §5a constraint 6.

**Live-provider isolation gate (R01; explicit and non-circular).**

1. **Scope.** The gate applies to every v2 policy-governed run, from AUTO-017 onward, that would execute
   a **live** provider, local or Hermes. Examples are automatic resume, bounded or OWNER-extended
   remediation cycles, and per-role model execution. Before the gate opens, v2 runs accept only
   test-double adapters (scripted fakes), and acceptance runs use those fakes.
2. **Predicate.** `LIVE_PROVIDER_ENABLED ⇔ FA-5a evidenced by the AUTO-023 completion marker ∧ the
   per-run isolation self-test passes`. The self-test is performed during `PREFLIGHT` of *each* run. It
   launches the same hostile probe through the production confinement wrapper, and it must observe a
   denied write to the state root and to a forbidden worktree path.
3. **Owner of the check.** The predicate is a pure function evaluated by `MilestoneRunnerApplication`
   during `PREFLIGHT`. It is **not** a second transition authority: it only refuses or permits, and a
   refusal is published as an ordinary preflight stop.
4. **Non-circular.** FA-5a is delivered and evidenced by AUTO-023 using a hostile probe process. No live
   provider is needed to prove the isolation that live providers depend on. No stage before AUTO-023 can
   enable live execution. Earlier stages still build their schemas, contracts and tests.
5. **Unchanged.** AUTO-016 v1 supervised runs keep their already-authorized behavior. This program
   neither enables nor extends them, and every new autonomous capability is v2-only.

| Capability | May be **built** in | May be **enabled** only after |
|---|---|---|
| Schema v2, policy freeze, stage start (test-double adapters) | ST-01 | ST-01 |
| Event log, phase ladder (test-double adapters) | ST-02 | ST-02 |
| Automatic resume from checkpoint (test-double adapters) | ST-03 | ST-03 |
| OWNER-authorized extension cycles, at most 2 (test-double adapters) | ST-05 | ST-05 |
| Automatic 1..3 remediation cycles (test-double adapters) | ST-04 | ST-04 |
| Local-CLI OWNER decisions (typed confirmation) | ST-05 | ST-05 |
| Per-role model selection (test-double adapters) | ST-06 | ST-06 |
| **Any of the rows above with a live local provider** | ST-01..ST-06 | **Live-provider isolation gate**: FA-5a (ST-07) plus the per-run self-test; the capability's own stage must also be `COMPLETE` |
| Hermes execution against a **fake** Hermes | ST-07 | ST-07 |
| Hermes execution against **live** Hermes | ST-07 | FA-2, FA-3, FA-4, FA-5a (with the per-run self-test), FA-6 |
| Authenticated decisions on the local CLI | ST-08 | ST-08 |
| Telegram decision delivery (read-only notification) | ST-09 | ST-08 |
| Telegram decision **responses applied** | ST-09 | FA-1, FA-2, FA-3, FA-6 |
| Git automation, dry-run and receipt only | ST-10 | ST-10 |
| Git automation, **executing** | ST-10 | FA-1..FA-4, FA-5a, **FA-5b (established by ST-10 itself, R08)**, FA-6, **and** OD-GSE-04 ruled to permit it |

---

## 4. Stage Definitions

The same template is used for every stage. "Contract" means that stage's own future stage contract, which
must be drafted, reviewed once, and authorized before any implementation. The file lists give *expected*
surfaces for planning only. The authoritative allowlist is fixed by each contract.

Every stage has the following common requirements. They are stated here once and apply to all ten.

- **Adapters (R01).** Every acceptance run (Tier 1) in AUTO-017..AUTO-022 uses test-double
  (scripted fake) adapters. Live providers are admitted only through the §3 live-provider isolation gate.
- **Verification set.** `pytest -q`, `ruff check .`, `black --check .` (whole tree; the memory note on
  pre-commit skipping untracked files applies), `mypy --strict`, `pre-commit run --all-files`,
  `git diff --check`, and the four `workflowctl` governance checks.
- **Tests.** No `agentos_workflow` import from `milestone_runner/`, enforced by the existing AST test. No
  live provider, Hermes, Telegram, or network in the default suite; live tests are marked and skipped by
  default. The redaction boundary covers every new persisted artifact.
- **Scope.** Changes to `ALLOWED_RUN_TRANSITIONS` or to a ceiling happen only through that stage's
  contract, and the member-by-member test table is updated in the same change.
- **Completion marker.** The Registry row `IN_PROGRESS → COMPLETE` is recorded with a completion report at
  `docs/reports/workflow-automation/<STAGE>-completion-report.md`, which carries the verification
  evidence, the review and closure evidence, and the stage's specific markers.

---

### AUTO-017 (alias AWE-AUTO-ST-01) — Schema v2 + Stage Execution Policy

**Objective.** Introduce the versioned model through which the OWNER's start-time choices become one
immutable, digest-pinned `EffectiveStageExecutionPolicy` bound to a run.

**Prerequisites.**
- Execution predecessor AUTO-016 is `COMPLETE`.
- OD-GSE-01, -02, -03, -06 and -07 are **accepted** (2026-09-28). No OWNER decision still blocks this stage.
- The task mirrors are consistent (E17, reconciled).
- The `Current` set is empty.
- A stage contract (`stage-prompts/AUTO-017.md`) has been drafted, reviewed once, and authorized by the
  OWNER.

**Authorized scope (proposed).**
- `ProjectExecutionDefaults` (project-level, optional)
- `StageExecutionOverrides` (per-Stage, supplied at start)
- `EffectiveStageExecutionPolicy` (resolved, frozen) with:
  - `max_remediation_cycles ∈ {1,2,3}`
  - `on_retry_exhausted ∈ {ask_owner_and_freeze}`, a closed single-member enum; later stages may add
    members only by contract
  - `max_blockers ∈ 1..3`, default **3** (accepted OD-GSE-02; overflow behavior is delivered by AUTO-020)
  - `blocking_severities = {CRITICAL, HIGH}` and `defer_severities = {MEDIUM, LOW}`. These are fixed,
    not overridable per Stage (accepted OD-GSE-01).
  - `max_owner_extensions = 2`, a fixed constant recorded in the policy for auditability and not an
    OWNER-tunable knob (accepted OD-GSE-03)
  - `roles: {IMPLEMENTER, DISCOVERY_REVIEWER, REMEDIATOR, CLOSURE_VERIFIER} → RoleSelection` (structure
    only; binding happens in ST-06)
- `RoleSelection {provider_id, model_id, capability_mode, timeout_seconds}` (structure and validation only)
- `StageStartAuthorization` record: local, unauthenticated form, created by a local CLI command with typed
  confirmation
- Stage-start source of truth (accepted OD-GSE-06):
  - A matching AWE-native `StageStartAuthorization` is **required and authoritative**.
  - Where the project has a governed stage registry, its authorization or status is an **additional
    precondition**. The existing `_registry_authorizes` check is retained as that precondition.
  - Any disagreement between the two refuses execution with `STAGE_START_AUTHORIZATION_CONFLICT`,
    whatever the direction: a record without registry authorization, a registry authorization without
    a record, or a mismatch in stage ID or contract digest.
- Stage ID grammar generalized to a project-scoped grammar
- `RunRecord` schema v2 plus a v1→v2 **read-only** upgrade path. v1 records stay readable; publication is
  always v2.
- Resolution function `resolve_policy(defaults, overrides, contract) → EffectiveStageExecutionPolicy`,
  deterministic and pure

**Explicit exclusions.**
- No cycle execution: ceilings stay at 1/1/1 in behavior until ST-04 raises them.
- No event log.
- No decisions other than local start.
- No Hermes, no provider binding changes, and no Git changes.

**Files and components expected to change.**
- `milestone_runner/`: new `policy.py`; changes to `models.py`, `config.py` and `application.py`
  (the start path only); `state.py` for schema v2 load and publish.
- `cli.py`: one new verb, `milestone-runner stage-start`.
- `tests/test_milestone_runner_policy.py` (new), plus updates to the state, config and application tests.

**State/schema additions.**
- `STATE_SCHEMA_VERSION = 2`
- `policy.json`
- `stage-starts/*.json`
- `RunRecord.policy_digest`
- `RunRecord.stage_start_id`

**Invariants.** INV-07 and INV-10 (local form). Resolution precedence is contract ceiling, then Stage
override, then project default, then built-in default. An override can never exceed a contract ceiling,
and a capability-granting field defaults to least capability.

**Machine-verifiable acceptance.**
1. For all 3×N combinations of defaults and overrides, `resolve_policy` is deterministic: the same inputs
   give the same digest, and a property test covers it.
2. `max_remediation_cycles` values 0, 4, "2" and 2.0 are rejected, and 1, 2 and 3 are accepted.
3. After publication, any mutation of `policy.json` makes load fail with `POLICY_DIGEST_MISMATCH`.
4. Every v1 fixture under `tests/` loads, and publication produces v2.
5. `start` without a matching `StageStartAuthorization` is refused with `STAGE_START_NOT_AUTHORIZED`,
   even when the registry shows the stage `AUTHORIZED`.
   5a. A matching record whose stage the project registry does not authorize is refused with
   `STAGE_START_AUTHORIZATION_CONFLICT`, as is a record whose contract digest differs from the
   registry's. A repository without a governed registry relies on the record alone.
   5b. A config that promotes MEDIUM or LOW to blocking, or sets `max_blockers` outside `1..3`, is
   refused for a policy-governed run.
6. The AST test confirms that nothing outside the start-ingestion function constructs
   `StageStartAuthorization`.

**Tests.** Resolution precedence and ceilings, digest stability, the schema migration fixtures, the start
refusal, and the Stage ID grammar, both positive and negative.

**Restart/idempotency.** Re-running `stage-start` with identical inputs yields the same
`stage_start_id`, because the ID is content-addressed. A differing input yields a refusal and never
overwrites.

**Evidence required.** Digest vectors, the migration fixture list, and the verification set.

**Completion marker.** Registry `COMPLETE`, with `policy.json` produced end-to-end by a Tier-1 acceptance
run in a disposable repository.

**Dependencies on later stages.** None: this stage is self-contained. The ST-06 binding consumes
`RoleSelection`.

**Must NOT be implemented early.**
- Automatic cycles or raised ceilings.
- Decision responses other than local start.
- Telegram or Hermes fields that carry executable meaning. Structural placeholders are not allowed
  either, because `extra="forbid"` makes a later field addition a schema bump and that is intended.

---

### AUTO-018 (alias AWE-AUTO-ST-02) — Durable Lifecycle / Event Foundation

**Objective.** Make every state change a durable, hash-chained, idempotent event, and make every role
invocation an Operation with the §2.4 phase ladder.

**Prerequisites.** Execution predecessor AUTO-017 (ST-01) is `COMPLETE`, and this stage's own contract is authorized.

**Authorized scope (proposed).**
- `events.py`: `LifecycleEvent {run_id, sequence, state_version, event_type, payload, payload_digest, prev_event_digest, event_id}`.
  The event types are a closed enum.
- `EventStore`: atomic per-event publication, gap and chain verification, fold to projection.
- `operations.py`: `OperationRecord` and the phase artifacts. The deterministic `operation_id` is defined
  here.
- `RunStateStore` becomes a projection writer over events.
- `state_version` is monotonic and bound into the projection.
- Existing ledgers (`reconciliations`, `reopenings`, …) are also emitted as events.
- Execution request and result evidence are content-addressed.

**Explicit exclusions.**
- No new recovery behavior: the phase ladder is *recorded* here but not yet *consulted* on resume
  (ST-03).
- No cycle changes and no decisions.

**Files and components expected to change.** New `events.py` and `operations.py`; changes to `state.py`,
`application.py` (`_publish`, `_invoke_provider`, `transition_to` now emit events) and `models.py`;
tests.

**State/schema additions.** `events/`, `operations/`, `RunRecord.state_version`, `RunRecord.last_event_id`.

**Invariants.**
- INV-01.
- The hash chain holds: `prev_event_digest` equals the digest of event n−1.
- Events are never rewritten; a rewrite test mirrors `reject_ledger_rewrite`.
- The projection equals the fold of the events.

**Machine-verifiable acceptance.**
1. For every recorded AUTO-016 Tier-1 acceptance scenario, `fold(events) == state.json` after each step.
2. Deleting, reordering or editing any event is detected on load with `EVENT_CHAIN_BROKEN` and gives
   `HUMAN_INTERVENTION_REQUIRED`.
3. Appending the same `event_id` twice is a no-op, while the same sequence with a different digest is
   refused.
4. Every provider invocation produces its artifacts in this order, or stops at a defined phase with a
   recorded verdict: `REQUEST_CREATED`, `DISPATCH_INTENT` (published **before** process creation),
   `DISPATCH_RECEIPT`, `RESULT_RECEIVED`, `RESULT_VALIDATED`, `RESULT_PERSISTED`, `TRANSITION_APPLIED`
   (R02).
5. An AST test confirms that only `application.py` appends transition-type events.

**Tests.** Chain integrity, the projection fold, per-event atomic publish under simulated `os.replace`
failure, and redaction of the operation artifacts.

**Restart/idempotency.** The event append is idempotent by `event_id`. A crash between event publication
and projection publication is repaired on the next load, because the projection is rebuilt from the
chain.

**Evidence required.** Chain-verification output for the acceptance runs, plus the fault-injection
results for the append path.

**Completion marker.** Registry `COMPLETE`, with an acceptance run whose `events/` folds to its
`state.json` byte-identically.

**Dependencies on later stages.** ST-03 consumes the phase ladder.

**Must NOT be implemented early.**
- Resume logic that *acts* on the phases. Doing that before the ladder is proven would be recovery built
  on unproven evidence.

---

### AUTO-019 (alias AWE-AUTO-ST-03) — Resume / Crash Recovery

**Objective.** Resume every run from its latest durable checkpoint and never repeat completed work. Any
unsafe or ambiguous recovery must escalate to the OWNER.

**Prerequisites.** Execution predecessor AUTO-018 (ST-02) is `COMPLETE`, and this stage's own contract
is authorized. For its escalation target, this stage introduces the minimal `OWNER_DECISION_REQUIRED`
state, a `PendingDecision` record, the `AMBIGUOUS_RECOVERY` decision kind, and a local read-only
rendering. AUTO-021 (ST-05) later generalizes all of them. The only response ST-03 can apply is
`KEEP_FROZEN`, plus the existing `abort` command.

**Authorized scope (proposed).**
- `RecoveryReconciler` implementing the §2.4 table.
- Resume re-validation of repository identity, `run_id` and `stage_id`, `contract_sha256`,
  `policy_digest`, branch, HEAD (or the recorded post-commit HEAD from an approval receipt), the
  candidate path set and digests, and unauthorized drift (paths outside the cumulative allowlist).
- Duplicate request and result handling.
- **Regression tests reproducing crash gaps A and B (E8, E9) first**, followed by the fix.
- The minimal `OWNER_DECISION_REQUIRED` and `AMBIGUOUS_RECOVERY`, per the recommended sequencing above.

**Explicit exclusions.**
- No multi-cycle remediation and no EXTEND/ABORT/AMEND application. Only `KEEP_FROZEN` is recorded, plus
  the existing `abort` command.
- No Hermes.

**Files and components expected to change.** `recovery.py` (reconciler), `state.py` (the `_reconcile`
generalization), `application.py` (`_resume_from` becomes phase-driven), `models.py` (the new state and
edges), and tests. A new `tests/test_milestone_runner_crash_windows.py` injects faults at every phase
boundary of every role.

**State/schema additions.**
- `PendingDecision`, minimal form.
- `RecoveryVerdict` events.
- `ResumeAction` gains `APPLY_STORED_RESULT`, `REVALIDATE_STORED_RESULT` and `ESCALATE_TO_OWNER`.

**Invariants.**
- INV-06.
- Resume twice with no intervening change is a byte-identical no-op. This existing §13 property is
  preserved.
- Recovery never widens scope, never raises a budget, and never marks a finding closed.

**Machine-verifiable acceptance.** The following crash-window matrix is executed. Each cell is a test
that kills the run at the boundary, then resumes and asserts the stated outcome and the provider call
count.

| Crash after | Implementer | Discovery | Remediator (cycle k) | Closure (cycle k) |
|---|---|---|---|---|
| REQUEST_CREATED (no intent) | dispatch once | dispatch once | dispatch once | dispatch once |
| DISPATCH_INTENT, recorded `PRE_SPAWN_FAILED` | bounded retry within the same operation | bounded retry within the same operation (still one discovery operation) | bounded retry | bounded retry |
| DISPATCH_INTENT, no outcome (fingerprint unchanged **or** changed) | ODR (`AMBIGUOUS_RECOVERY`); 0 extra calls | ODR; **0 extra discovery calls** | ODR; 0 extra calls | ODR; 0 extra calls |
| DISPATCH_RECEIPT, no result | ODR; 0 extra calls | ODR; **0 extra discovery calls** | ODR; 0 extra calls | ODR; 0 extra calls |
| RESULT_RECEIVED | 0 calls; revalidate | 0 calls (**closes E9**) | 0 calls | 0 calls |
| RESULT_VALIDATED / PERSISTED | 0 calls; apply (**closes E8**) | 0 calls; apply | 0 calls; apply | 0 calls; apply |
| TRANSITION_APPLIED | continue to the next step | continue | continue at closure k (**brief example 2**) | continue |

Further acceptance criteria:

- A result delivered twice with the same digest is a no-op. The same `operation_id` with a different
  digest gives `OWNER_DECISION_REQUIRED` (`DUPLICATE_RESULT_CONFLICT`).
- HEAD, branch, contract hash or policy-digest drift on resume is refused. The existing stop reasons
  apply, plus `POLICY_DIGEST_MISMATCH`.
- A pending decision survives a restart with byte-identical `request.json`.
- **Discovery cardinality (R02).** For every row and every crash point, the number of discovery operations
  that reached `DISPATCH_INTENT` is ≤ 1. A malformed discovery result yields `DISCOVERY_MALFORMED` with
  zero further discovery dispatches. A test asserts that `RETRY_DISCOVERY` does not exist in the option
  vocabulary.
- **Intent ordering (R02).** A test with an instrumented spawn hook asserts that `dispatch-intent.json` is
  durably published before the process-creation call is entered.

**Tests.** The matrix above, plus the resume no-op property, drift refusals, and the two regression
tests for E8 and E9.

**Restart/idempotency.** This stage *is* the restart and idempotency requirement.

**Evidence required.**
- The matrix results table, with provider-call counts from a counting fake adapter.
- Proof that the E8 and E9 regressions failed before the fix and pass after it.

**Completion marker.** Registry `COMPLETE`, with the matrix 100% green and recorded in the report.

**Dependencies on later stages.** ST-04 reuses the reconciler at the cycle level. ST-07 adds the
remote-dispatch status query.

**Must NOT be implemented early.**
- Any "best-effort" auto-adoption of observed repository state. `ADOPT_OBSERVED_STATE` exists only as an
  OWNER option, never as an automatic path.

---

### AUTO-020 (alias AWE-AUTO-ST-04) — 1..3 Bounded Remediation Cycles

**Objective.** Implement the brief's lifecycle: one discovery, a frozen finding set, paired
remediation and closure cycles bounded by the frozen policy, early success, and `ask_owner_and_freeze` on
exhaustion.

**Prerequisites.**
- Execution predecessor **AUTO-021 (ST-05)** is `COMPLETE` (accepted OD-GSE-12). Retry-exhaustion OWNER
  actions (`EXTEND_REMEDIATION +1`, `KEEP_FROZEN`, `ABORT_STAGE`, `AMEND_STAGE_CONTRACT`) must exist
  before bounded multi-cycle remediation is enabled. AUTO-019 (ST-03) is therefore also `COMPLETE`.
- **OD-GSE-09 and OD-GSE-11 must be ruled.** Both are OPEN and both block this stage.
- This stage's own contract is authorized.

**Authorized scope (proposed).**
- `cycles.py`: `CycleCoordinator`, pure.
- Raise the **automatic** `MAX_CORRECTION_ROUNDS_CEILING` and `MAX_CLOSURE_REVIEWS_CEILING` to 3, driven by
  the frozen `max_remediation_cycles ∈ {1,2,3}`. The OWNER-extension budget from AUTO-021 (≤ 2) is
  unchanged and stays separate. `MAX_FULL_REVIEWS_CEILING` stays at 1 and becomes non-configurable.
- A new `CLOSURE_VERIFYING → NEEDS_CORRECTION` edge for *automatic* continuation. The exhaustion edge and
  `FINDING_SET_FROZEN` already exist from AUTO-021.
- Discovery overflow handling (accepted OD-GSE-02): `REVIEWING → OWNER_DECISION_REQUIRED` with
  `DISCOVERY_OVERFLOW`. The overflowing review is persisted and counted as the one discovery review.
- Per-cycle operation IDs.
- Prompts carrying the cycle number and the prior closure evidence as data-scoped sections.
- Post-remediation verification handling per OD-GSE-09.
- Closure scope per OD-GSE-11.

**Explicit exclusions.**
- No change to the OWNER decision API or its option semantics, which AUTO-021 (ST-05) owns. This stage
  only emits requests through it.
- No change to discovery count.
- No new finding creation by closure.
- No change to severity policy. Accepted OD-GSE-01 fixes it: only blocking findings enter remediation.

**Files and components expected to change.** `cycles.py` (new), `review.py` (ledger generalization),
`results.py` (the closure grammar keeps its frozen-ID restriction, generalized to per-cycle), `prompts.py`,
`application.py`, `config.py`, `models.py`, and tests.

**State/schema additions.**
- `RemediationCycleRecord {cycle_no, remediation_operation_id, verification_digest, closure_operation_id, open_after[], closed_after[]}`,
  derived from events.
- `authorized_remediation_cycles`, derived.

**Invariants.** INV-02, INV-03, INV-04, INV-05. Cycle k+1 cannot be scheduled unless cycle k is complete.

**Machine-verifiable acceptance.** A table-driven test runs for max = 1, 2 and 3 against a scripted fake
provider:

- If there are zero blockers, the run reaches the success path with 0 cycles.
- If everything is closed at cycle j ≤ max, the run takes the success path and exactly j cycles are
  recorded, with no further provider calls.
- If findings are still open after cycle max, the run is in `OWNER_DECISION_REQUIRED`, exactly max
  cycles are recorded, and a `RETRY_EXHAUSTED` request lists all four options.
- A discovery result with `max_blockers + 1` blockers leaves the run in `OWNER_DECISION_REQUIRED`
  (`DISCOVERY_OVERFLOW`). The review is counted once, no remediation provider call occurs, and the
  options are exactly `KEEP_FROZEN`, `ABORT_STAGE` and `AMEND_STAGE_CONTRACT`.
- MEDIUM and LOW findings never appear in a remediation prompt's actionable section.
- A closure result naming an unknown ID, or carrying a new finding, is rejected as malformed and does not
  complete the cycle.
- The discovery provider is called exactly once in every scenario, and at most one discovery operation
  ever reaches `DISPATCH_INTENT` (INV-02).
- A kill -9 at every phase boundary of cycle 2 followed by resume yields the same final state and the
  same provider-call counts as an uninterrupted run.

**Tests.** The lifecycle table, frozen-set immutability, the unknown-ID rejection, and the cycle-level
crash matrix (the ST-03 harness reused).

**Restart/idempotency.** A cycle is complete only when both acceptance events are durable. Resume
continues at the lowest incomplete phase of the lowest incomplete cycle.

**Evidence required.** The lifecycle table results for max ∈ {1,2,3}, and the provider-call count
assertions.

**Completion marker.** Registry `COMPLETE`, with a Tier-1 acceptance run in a disposable repository that
demonstrates exhaustion at max=1 and early success at max=3.

**Dependencies on later stages.** None. EXTEND, ABORT and AMEND are already applied by AUTO-021 (ST-05),
which precedes this stage.

**Must NOT be implemented early.**
- Automatic `EXTEND`.
- Any path from exhaustion to `READY_FOR_COMMIT_APPROVAL`.

---

### AUTO-021 (alias AWE-AUTO-ST-05) — OWNER Decision API

**Objective.** Provide a transport-neutral, durable decision request and response service with
restart-stable IDs and options, and apply the four exhaustion responses plus `START_STAGE`.

**Prerequisites.**
- Execution predecessor AUTO-019 (ST-03) is `COMPLETE`.
- OD-GSE-03 is **accepted**: `+1` per response, at most 2 extensions per run.
- **OD-GSE-10 must be ruled.** It is OPEN and blocks this stage.
- This stage's own contract is authorized.

**Authorized scope (proposed).**
- `decisions.py`: `DecisionRequest`, `DecisionResponse`, `PendingDecision`, `DecisionService`, the pure
  renderer (§2.6), the option catalog per decision kind, and the recommendation function.
- Application semantics:
  - `EXTEND_REMEDIATION +1` emits `REMEDIATION_EXTENDED`, adds exactly 1 to the authorized cycles, and
    moves to `NEEDS_CORRECTION`.
  - `KEEP_FROZEN` records the response and stays pending.
  - `ABORT_STAGE` moves to `ABORTED`.
  - `AMEND_STAGE_CONTRACT` moves to `SUPERSEDED`, and the next run requires a new contract digest and a
    new start.
- **Retry exhaustion at the existing single-round boundary.** Until AUTO-020 (ST-04) exists, the automatic
  remediation budget stays exactly 1, which is AUTO-016's one correction round plus one closure
  verification. The existing stop after a closure that leaves blockers OPEN (today
  `HUMAN_INTERVENTION_REQUIRED`) is re-routed to `OWNER_DECISION_REQUIRED` with a `RETRY_EXHAUSTED` request.
  This stage adds:
  - the `CLOSURE_VERIFYING → OWNER_DECISION_REQUIRED` and `OWNER_DECISION_REQUIRED → NEEDS_CORRECTION`
    edges;
  - the `FINDING_SET_FROZEN` event;
  - an `owner_extension_rounds` budget, separate from the automatic ceiling and bounded by
    `max_owner_extensions = 2` (accepted OD-GSE-03).

  Each extension round is exactly one remediation plus one closure verification, limited to the frozen
  finding IDs. **This stage delivers no automatic multi-cycle continuation**; that is AUTO-020's scope.
- `START_STAGE` ingestion creates the `StageStartAuthorization`, extending ST-01's local form.
- CLI verbs: `decision show`, `decision respond --decision-id <id> --response <text>` with typed
  confirmation.
- **The local CLI principal is the only principal in this stage.**

**Explicit exclusions.** No OWNER authentication mechanism, nonces or expiry (ST-08). No Telegram or Hermes. No automatic
selection of the recommended option under any timeout; this is deliberate.

**Files and components expected to change.** `decisions.py` (new), `application.py`, `models.py` (edges
out of `OWNER_DECISION_REQUIRED`, and `SUPERSEDED`), `cli.py`, and tests.

**State/schema additions.** `decisions/<id>/request.json`, `responses/`, `applied.json`; the
`DECISION_REQUESTED`, `DECISION_RESPONSE_RECORDED` and `DECISION_APPLIED` events.

**Invariants.**
- INV-05, INV-08, INV-09 (local form: the response is bound to `decision_id`, `request_digest` and
  `state_version`), INV-10.
- The recommendation is advisory and never applied automatically.
- Exactly one pending decision per run exists at a time.

**Machine-verifiable acceptance.**
1. The decision ID and `request.json` bytes are identical before and after a kill -9 and resume.
2. Each of the four responses produces exactly its specified effect and event sequence.
3. `EXTEND_REMEDIATION +1` adds exactly one cycle. A second response to the same decision is refused
   (`DECISION_ALREADY_APPLIED`). After the extra cycle exhausts, a *new* decision ID is issued. After the
   second applied extension exhausts, the new request offers only `KEEP_FROZEN`, `ABORT_STAGE` and
   `AMEND_STAGE_CONTRACT`; `EXTEND_REMEDIATION +1` is absent and refused if sent (OD-GSE-03).
4. A response naming an option not in `allowed_options` is refused, as is one with a stale
   `state_version` or a mismatched `request_digest`.
5. When only one option is valid, the rendered message contains the literal "exact required response".
6. A snapshot test shows the rendered message contains every field the brief requires: project, stage,
   run ID, decision ID, reason, state, evidence, all options with effects, the recommendation and its
   rationale, and the exact reply syntax.
7. A test shows `DONE` never produces a `START_STAGE` for any other Stage without an OWNER response.

**Tests.** The above, plus a crash between `RESPONSE_RECORDED` and `DECISION_APPLIED`, which must be
applied exactly once on resume.

**Restart/idempotency.** A response is recorded with its content digest, and re-ingestion is a no-op.
Application is idempotent by `decision_id`.

**Evidence required.** The rendered-message snapshots for every decision kind, and the application event
traces.

**Completion marker.** Registry `COMPLETE`, with a Tier-1 run showing exhaustion, `EXTEND_REMEDIATION +1`,
success, `DONE`, and no automatic next Stage.

**Dependencies on later stages.** ST-08 adds authentication. ST-09 adds the transport.

**Must NOT be implemented early.**
- Remote responses of any kind.
- Timeout-driven automatic responses.

---

### AUTO-022 (alias AWE-AUTO-ST-06) — Per-role AI / Provider / Model Selection

**Objective.** Bind each of the four roles to an OWNER-selected provider and model, frozen per run and
recorded with full model provenance.

**Prerequisites.**
- Execution predecessor AUTO-020 (ST-04) is `COMPLETE`. The hard technical dependencies are ST-01 and
  ST-02, because provenance lives in the operation artifacts.
- **OD-GSE-08 must be ruled.** It is OPEN and blocks this stage.
- This stage's own contract is authorized.

**Authorized scope (proposed).**
- Generalize `ProviderBinding` from the fixed Claude/Codex split to `role → (adapter, model, capability_mode)`
  resolved from the frozen policy.
- A provider catalog: a closed registry of adapter IDs, each with the model IDs it accepts and the
  capability modes it can express. Unknown adapter or model IDs are refused at resolution, not at
  invocation.
- Reviewer roles (`DISCOVERY_REVIEWER`, `CLOSURE_VERIFIER`) are constrained to read-only capability
  modes. The type system cannot express a writable reviewer.
- Independence rule per OD-GSE-08.
- `ModelProvenance {role, adapter_id, requested_model, reported_model (if the provider reports one), cli_version, engine_provenance (T-307), policy_digest}`,
  recorded per operation.

**Explicit exclusions.**
- No Hermes: local CLI adapters only.
- No runtime model fallback or substitution. A model that is unavailable produces an operation failure,
  never a silent downgrade.

**Files and components expected to change.** `providers/base.py` and possibly a new
`providers/catalog.py`, `claude_cli.py` and `codex_cli.py` (model argument slot), `config.py`, `policy.py`,
`application.py`, and tests.

**State/schema additions.** Role selections inside the `EffectiveStageExecutionPolicy` become binding;
`ModelProvenance` in `operations/*/request.json` and `result.validated.json`.

**Invariants.**
- INV-07.
- The binding cannot change after freeze.
- A reviewer's capability mode is always read-only.
- A mismatch between requested and reported model is recorded, and whether it stops the run is
  specified per the OD-GSE-08 ruling.

**Machine-verifiable acceptance.**
1. For each role, an override at Stage start changes only that role's binding.
2. After a restart, the bindings are identical, because they are read from `policy.json` and never
   re-resolved from current defaults. The test changes the project defaults between crash and resume
   and asserts that the bindings are unchanged.
3. A writable capability for a reviewer role is unrepresentable (a type test).
4. Provenance is present on 100% of the operations in the acceptance run.

**Tests.** Resolution, freezing across a defaults change, catalog refusal, reviewer read-only, and the
independence rule.

**Restart/idempotency.** Resolution happens once, at start. Resume reads, and never resolves.

**Evidence required.** The provenance table from the acceptance run.

**Completion marker.** Registry `COMPLETE`.

**Dependencies on later stages.** ST-07 maps the bindings into the `RunEnvelope`.

**Must NOT be implemented early.** Hermes model routing.

---

### AUTO-023 (alias AWE-AUTO-ST-07) — Hermes Execution Adapter

**Objective.** Implement `AWE RunEnvelope → Hermes → selected AI/model → StructuredResult → AWE` as one
more execution adapter behind an `ExecutionPort`, with AWE remaining the sole transition authority.

**Prerequisites.**
- Execution predecessor AUTO-022 (ST-06) is `COMPLETE`. The hard technical dependencies are ST-02, ST-03
  and ST-06.
- **External prerequisite EP-1 (deferred until this stage):** a written Hermes interface specification covering the submission
  mechanism, status query by request ID, result retrieval, idempotent resubmission semantics, and the
  confinement Hermes can enforce. This plan does not invent Hermes APIs. ST-07's contract cannot be
  finalized until EP-1 exists.

**Authorized scope (proposed).**
- `envelope.py`: the `RunEnvelope` fields are:
  - `envelope_version`, `request_id` (= `operation_id`), `attempt`, `run_id`, `stage_id`, `role`
  - `adapter_id`, `model_id`, `capability_mode`
  - `repository_identity`, `branch`, `head_sha`, `contract_sha256`, `policy_digest`
  - `allowed_paths[]`, `forbidden_paths[]`, `timeout_seconds`
  - `prompt_digest`, the prompt (delivered as a referenced blob)
  - `expected_result_grammar`, `issued_at`, `envelope_digest`
- `StructuredResult`: `request_id`, `envelope_digest` echo, `adapter_id`, `reported_model`,
  `started_at`/`completed_at`, `exit_status`, `result_block` (the existing §18 grammar), `changed_paths`
  claimed, `transcript_refs`, and `hermes_receipt`.
- Validation:
  - The envelope digest must echo, and the request ID must match an operation at `DISPATCH_INTENT` or `DISPATCH_RECEIPT`.
  - Claimed changed paths are *re-observed* by AWE's `GitReadOnlyInspector`, never trusted.
  - Paths are checked by the scope guard.
  - The result grammar is parsed by the existing strict parsers.
- `HermesExecutionAdapter`, a status-query recovery path (ST-03 phases `DISPATCH_INTENT` and
  `DISPATCH_RECEIPT`), and `FakeHermes`, an in-process deterministic fake that supports scripted
  duplicates, delays, loss and crash.
- **Provider execution isolation, FA-5a (R01).** The `ExecutionPort` gains one production confinement
  wrapper, used by **every** execution adapter, local CLI and Hermes alike. It denies each provider
  process write access to the AWE state root and to paths outside the operation's allowed worktree paths.
  The mechanism (for example a separate UID, a mount namespace, or an LSM such as Landlock) is fixed by
  this stage's contract. For Hermes it is fixed together with EP-1. The live-provider isolation gate (§3)
  is also implemented here.

**Explicit exclusions.**
- No live Hermes in the default test suite.
- No Hermes-side orchestration: Hermes never receives "the next step".
- No Telegram.
- No Git.

**Files and components expected to change.** `envelope.py` (new), `providers/hermes.py` (new, per
DEC-016-002's subpackage ownership), `providers/base.py` (`ExecutionPort`), `application.py`,
`recovery.py`, `config.py` (Hermes endpoint config; no credentials stored, per §17), tests, and
`tests/fakes/fake_hermes.py`.

**State/schema additions.** `operations/*/dispatch.json` gains `hermes_receipt`, and the operation
artifacts gain `structured_result.json`.

**Invariants.**
- INV-11.
- Hermes output is evidence. AWE re-derives the repository effects.
- The envelope is bound to HEAD and the contract, so a result produced under a different HEAD is
  rejected.

**Machine-verifiable acceptance.** Against `FakeHermes`:

1. A duplicate result delivery is a no-op, and a conflicting duplicate gives `OWNER_DECISION_REQUIRED`.
2. After a lost result, the status query recovers it without re-dispatch.
3. A result with a HEAD mismatch is rejected.
4. A result claiming no changes while the worktree changed is rejected, because re-observation wins.
5. A result for an unknown `request_id` is rejected and recorded.
6. The ST-03 crash-window matrix passes unchanged with `FakeHermes` substituted.
7. **Negative isolation test, OS/runtime level (R01).** A hostile probe process, not a live provider,
   is launched through the production confinement wrapper for each adapter class. It attempts to write,
   create, rename and delete under the state root, and in each of `events/`, `operations/`,
   `decisions/`, `state.json` and `run.lock`, and also outside its allowed worktree paths. **Every
   attempt must fail.** The stage cannot complete while any attempt succeeds; there is no "documented
   gap" completion.
8. The per-run isolation self-test (§3) refuses a live run when the wrapper is absent or misconfigured.
   The test simulates this by disabling the wrapper.

**Tests.** The above, plus redaction of the envelope and result.

**Restart/idempotency.** `request_id` is the idempotency key, and resubmission with the same key must be
a no-op in Hermes (an EP-1 requirement).

**Evidence required.** The FakeHermes matrix results, and the negative isolation test output (FA-5a).

**Completion marker.** Registry `COMPLETE` for the **fake** adapter, together with FA-5a evidence. Live
provider execution (local or Hermes) is enabled only through the live-provider isolation gate (§3). Live
Hermes also requires FA-2, FA-3, FA-4 and FA-6 and a separate recorded OWNER act.

**Dependencies on later stages.** ST-09 reuses the Hermes channel for decisions, but through a separate
port.

**Must NOT be implemented early.**
- Live-Hermes default enablement.
- Letting Hermes select a model.
- Letting Hermes retry on its own authority beyond what EP-1's idempotency allows.

---

### AUTO-024 (alias AWE-AUTO-ST-08) — Authenticated OWNER Decision Contracts

**Objective.** Make every `DecisionResponse`, and every OWNER-initiated `START_STAGE` command, attributable
to the configured OWNER principal through an authenticated mechanism. Each must be single-use,
integrity-protected, replay-protected, and bound to the exact decision and state version.

**Mechanism neutrality (R05).** OD-GSE-05 is OPEN, so this stage is specified by **security properties,
not by mechanism**. Nothing here requires asymmetric signatures, one-time codes (TOTP or otherwise), a
local-CLI fallback, a particular custody arrangement for credentials or keys, or a specific expiry
duration. The OD-GSE-05 ruling selects these, and the stage contract then fixes them.

**Prerequisites.**
- Execution predecessor AUTO-023 (ST-07) is `COMPLETE`. The hard technical dependency is ST-05.
- **OD-GSE-05 must be ruled** before this stage's *contract* can be finalized. It is OPEN and blocks
  this stage.

**Required security properties** (every OD-GSE-05 option must satisfy all of them):

| # | Property | Meaning |
|---|---|---|
| SP-1 | Authenticated OWNER attribution | A response is accepted only if an `AttestationVerifier` bound to the configured `OwnerPrincipal` authenticates it. Transport identity alone counts only if OD-GSE-05 rules that it is sufficient. |
| SP-2 | Integrity | The authenticated content covers the canonical bytes of `{decision_id, request_digest, state_version, option, nonce}`. Changing any field invalidates the response. |
| SP-3 | Replay protection | Each challenge carries an AWE-generated, single-use nonce. A response bound to a consumed nonce, or to a different decision, is refused. |
| SP-4 | Single-use application | At most one response per decision is consumed and applied (the R06 protocol below). |
| SP-5 | State/version binding | A response whose `state_version` or `request_digest` differs from the pending decision's is refused. |
| SP-6 | Expiry / revocation | **The policy is resolved by OD-GSE-05.** Whatever it rules is enforced deterministically. If the ruled policy includes expiry, an expired challenge is refused, and AWE may issue a new delivery of the *same* decision (same ID and options, new nonce), recorded as `DECISION_REISSUED`, which preserves INV-08. Principal or credential revocation, if ruled, refuses all later responses from the revoked credential. |

**Authorized scope (proposed).**
- `attestation.py`: an `OwnerPrincipal` registry, a mechanism-neutral `AttestationVerifier` port,
  `DecisionChallenge {decision_id, request_digest, state_version, nonce, issued_at, expiry_policy_ref}`,
  and `AuthenticatedDecisionResponse`.
- One production verifier implementation: the mechanism ruled under OD-GSE-05.
- Verification material is kept outside the repository, outside run state, and outside every provider
  and transport process's reach (FA-2). The custody form follows OD-GSE-05.
- **Single authoritative consumption record (R06).** There is **no separate nonce marker file**. A nonce
  is consumed if and only if the hash-chained event log (AUTO-018) contains a `DECISION_RESPONSE_CONSUMED`
  event naming it. The ordered protocol, performed under the run lock, is:
  1. **Persist.** The authenticated response is persisted durably, before any consumption, with its raw
     bytes, the transport identity, AWE's `received_at` and the verifier verdict, at
     `decisions/<id>/responses/<response-digest>.json`. This record is evidence only and consumes
     nothing.
  2. **Consume.** AWE appends `DECISION_RESPONSE_CONSUMED {decision_id, nonce, response_digest, option,
     state_version}`. This event is the sole authority for consumption.
  3. **Apply.** AWE appends `DECISION_APPLIED` and the resulting transition events.

  Restart behavior, determined solely from durable records:
  - **(1) Crash before the response is persisted.** Nothing was recorded or consumed. The response must be
    redelivered by the transport, which does not acknowledge before persistence (AUTO-025), or re-sent by
    the OWNER.
  - **(2) Crash after the response is persisted, before the consumption event.** This is the only "marker
    without event" state that can exist, because the persisted response is not a consumption marker.
    AWE re-runs the deterministic verification on the stored bytes. Expiry is evaluated against the
    persisted AWE `received_at`, never against restart time. If the result is valid, the decision is
    still pending, and `state_version` still matches, AWE appends the consumption event. Otherwise it
    appends `DECISION_RESPONSE_REJECTED` with the reason. There is no third outcome.
  - **(3) Crash after the consumption event, before application.** AWE applies exactly once from the
    consumption event. The option and state binding come from the event, not from re-parsing.
  - **(4) Crash after application.** There is nothing to do. A later duplicate of the same response, or
    any response for that nonce, is recorded as `DUPLICATE_RESPONSE_IGNORED` and never re-applied.

  No recovery step infers consumption from the presence of a file, and no step guesses.
- `START_STAGE` authentication uses the same properties and protocol, with the challenge replaced by an
  OWNER-initiated command nonce.

**Explicit exclusions.**
- No Telegram (ST-09).
- No mechanism is chosen here (R05).
- No credential or key material in the repository or in run state.
- No custody or expiry defaults invented while OD-GSE-05 is OPEN.

**Files and components expected to change.** `attestation.py` (new), `decisions.py`, `events.py`
(consumption event types), `config.py` (principal *reference* fields only), `cli.py`, and tests.

**State/schema additions.** Challenges in `decisions/<id>/deliveries/<n>.json`, the response records in
`decisions/<id>/responses/`, the events `DECISION_RESPONSE_CONSUMED`, `DECISION_RESPONSE_REJECTED`,
`DUPLICATE_RESPONSE_IGNORED` and `DECISION_REISSUED`, and `DecisionResponse.attestation`, which is an
opaque, mechanism-typed field.

**Invariants.**
- INV-09 in full.
- SP-1..SP-6 hold.
- Consumption authority exists exactly once: the event log.

**Machine-verifiable acceptance.**
- A **verifier conformance suite** is parametrized over every still-valid OD-GSE-05 option class:
  - transport-identity-only, if OD-GSE-05 keeps that option valid;
  - a per-decision one-time code;
  - an asymmetric signature.

  Each class runs with a test-double verifier, and the suite asserts SP-1..SP-5 and the ruled SP-6. The
  production verifier selected by OD-GSE-05 must pass the same suite.
- Refusal tests, each with its own error code:
  - replay of a consumed nonce
  - a valid attestation from the wrong principal
  - an attestation over a different option
  - a stale `state_version`
  - an attestation for decision D1 presented for decision D2
  - a tampered `request_digest`
  - expiry and revocation, **conditional** on the OD-GSE-05 ruling including them
- **R06 crash-boundary tests.** A kill -9 at each of boundaries (1)–(4), followed by resume, must yield
  exactly one of consume-and-apply-once, reject, or no-op, as specified. Across all boundaries there are
  zero double applications.
- Two concurrent valid responses produce exactly one consumption and one application.
- A test shows no module treats the presence of a response file as consumption.

**Tests.** The above.

**Restart/idempotency.** This is the R06 protocol: persist, then consume, then apply, all under the run
lock.

**Evidence required.**
- The conformance-suite results.
- The refusal matrix.
- The R06 crash-boundary results.
- A custody statement, in the form OD-GSE-05 rules, showing that no provider or transport process can
  read the verification material (FA-2 evidence).

**Completion marker.** Registry `COMPLETE`.

**Dependencies on later stages.** ST-09 carries the challenge and response.

**Must NOT be implemented early.**
- Accepting any remote response.
- Choosing an attestation mechanism, custody form or expiry duration before OD-GSE-05 is ruled.

---

### AUTO-025 (alias AWE-AUTO-ST-09) — Hermes Telegram Decision Transport

**Objective.** Carry `DecisionRequest` from AWE through Hermes and Telegram to the OWNER, and bring the
`DecisionResponse` back the same way. Telegram and Hermes serve only as transport.

**Prerequisites.**
- Execution predecessor AUTO-024 (ST-08) is `COMPLETE`. The hard technical dependencies are ST-05, ST-07
  and ST-08.
- **EP-2 (deferred until this stage):** the Hermes Telegram messaging interface specification. **EP-2
  must specify (R07):**
  - a stable, unique inbound message/update identity, for example the Telegram `update_id` together with
    the chat ID and the Hermes message ID;
  - a replay, polling, or equivalent redelivery capability, so that an unacknowledged inbound message is
    delivered again after either side restarts;
  - an explicit acknowledgment or cursor-advance operation that AWE controls.

  If EP-2 cannot provide these, the AUTO-025 contract cannot be finalized.
- **OD-GSE-05 must be ruled.** It is OPEN and also blocks this stage.

**Authorized scope (proposed).**
- `DecisionTransportPort` with an outbox and inbox:
  - `DecisionOutbox`: AWE writes each delivery, which is the rendered message, the structured request,
    and the challenge.
  - `DecisionInbox`: AWE ingests raw replies.
- `HermesTelegramTransport` adapter.
- Reply parser for the exact syntax `<decision_id> <OPTION> [args] <attestation>`, which is strict and
  rejects anything else with a transport-level "not understood" reply.
- OWNER identity correlation: the Telegram user and chat ID must match the principal registry entry.
  This is *necessary but not sufficient*, because the ST-08 attestation is still required.
- Restart-safe pending deliveries: the outbox is keyed by `(decision_id, delivery_n)`, and redelivery
  after a restart reuses the same payload bytes.
- Duplicate and replay handling via ST-08.
- **Durable inbound protocol (R07).** Hermes and Telegram remain transport only. For each inbound message:
  1. **External receipt.** AWE obtains the message from the transport together with its stable inbound
     identity.
  2. **AWE persistence.** Before any acknowledgment, AWE durably persists the raw inbound bytes, the
     inbound identity and AWE's `received_at` at `decisions/inbox/<transport>/<inbound-id>.json`,
     published atomically.
  3. **Acknowledgment.** Only after step 2 does AWE acknowledge the message or advance the transport
     cursor.
  4. **Validation.** AWE parses the reply strictly, correlates the identity, and verifies it against
     ST-08. It always does this from the persisted copy, never from transport memory.
  5. **Application.** Application follows ST-08's R06 protocol: persist the response, consume, apply.

  **Duplicates.** A second delivery with the same inbound identity is a no-op once step 2 has happened.
  It is re-acknowledged if needed and never re-validated into a second application. A different inbound
  identity carrying byte-identical reply content is also a duplicate, deduplicated by response digest and
  nonce under ST-08, and recorded as `DUPLICATE_RESPONSE_IGNORED`.
- A `FakeTelegramHermes` test double that supports scripted redelivery, delayed acknowledgment, cursor
  loss and restart.

**Explicit exclusions.**
- Hermes and Telegram never render or alter options. AWE's renderer is authoritative, and a digest of the
  rendered text is carried in the payload.
- No free-text interpretation or natural-language parsing of replies.
- No Telegram-initiated action other than replying to a pending decision or submitting `START_STAGE`.

**Files and components expected to change.** `decision_transport.py` (new),
`providers/hermes_telegram.py` or `transport/hermes_telegram.py` (the placement is fixed by the contract),
`decisions.py`, `application.py` (the ingest command acquires the run lock), and tests.

**State/schema additions.** `decisions/<id>/deliveries/*` (with transport receipt) and
`responses/<raw-digest>.json`.

**Invariants.**
- AWE ingests replies under the run lock.
- An unparseable reply never changes state.
- A reply from an uncorrelated identity is recorded as a security event and never applied.
- INV-05, INV-08 and INV-09 hold end to end.

**Machine-verifiable acceptance.** Against the fake:

1. A delivery is byte-identical after an AWE restart and after a Hermes restart.
2. An exact reply with a valid attestation is applied once, and the same reply delivered twice is
   applied once.
3. A reply to an expired challenge is refused and triggers reissue per ST-08.
4. A reply from the wrong chat or user is refused and logged.
5. A reply with a correct option but a missing attestation is refused.
6. When only one option is valid, the message states the exact required response.
7. Every rendered message contains the fields the brief requires (the snapshot test from ST-05, reused).
8. **Inbound crash-boundary tests (R07).** A kill -9 is injected at each boundary of
   external receipt → AWE persistence → acknowledgment → validation → application:
   - **After receipt, before persistence.** Nothing was acknowledged, the transport redelivers, and the
     message is applied exactly once.
   - **After persistence, before acknowledgment.** The redelivery is recognized by inbound identity as a
     no-op, and the message is applied exactly once.
   - **After acknowledgment, before validation.** On restart, validation runs from the persisted copy and
     the message is applied exactly once, with no dependence on redelivery.
   - **After validation, before application.** ST-08 R06 cases (2) and (3) apply, and the message is
     applied exactly once.
   - **After application.** A redelivery is a no-op.

   There are zero lost responses and zero double applications.
9. The cursor never advances before persistence. An instrumented fake asserts the ordering.

**Tests.** The above.

**Restart/idempotency.** The outbox is durable and idempotent by `(decision_id, delivery_n)`. The inbox is
durable and idempotent by inbound identity, and responses by response digest and nonce. AWE persists
before it acknowledges.

**Evidence required.** The fake transport matrix. Live Telegram acceptance is a separate recorded act
gated by FA-1, FA-2, FA-3 and FA-6.

**Completion marker.** Registry `COMPLETE` for the fake transport.

**Dependencies on later stages.** None.

**Must NOT be implemented early.**
- Response application before ST-08.
- Any Telegram-originated Stage start before ST-08.

---

### AUTO-026 (alias AWE-AUTO-ST-10) — Controlled Git Automation (LAST)

**Objective.** Let AWE perform the Git transition that concludes a Stage, and only after every governed
predicate passes. The transition is receipt-backed and recoverable, and it never starts the next Stage.

**Prerequisites (entry; R08).**
- Execution predecessor AUTO-025 (ST-09) is `COMPLETE`, which means AUTO-017..AUTO-025 are all
  `COMPLETE`.
- The **entry** predicates are only those deliverable before this stage: FA-1, FA-2, FA-3, FA-4, FA-5a
  (filesystem/runtime isolation, delivered by AUTO-023) and FA-6.
- **FA-5b, Git confinement, is not an entry prerequisite.** This stage establishes it.
- Full FA-5 (FA-5a ∧ FA-5b) is an **enablement / acceptance** requirement for *executable* Git
  automation, evidenced by this stage's own acceptance tests.
- **OD-GSE-04 must be ruled**; it is OPEN and blocks this stage. If OD-GSE-04 rules
"keep the mandatory human commit gate", ST-10 reduces to receipt, recovery and confinement hardening of the
existing gated path, with the OWNER approval flowing through the ST-05/08/09 decision API instead of the
terminal.

**Authorized scope (proposed).**
- `GitAutomationPredicate`, evaluated fresh at the point of use. It requires all of the following:
  - The state is `READY_FOR_COMMIT_APPROVAL`.
  - There is no pending decision and no `OWNER_DECISION_REQUIRED` or `HUMAN_INTERVENTION_REQUIRED`
    history left unresolved.
  - The frozen finding set is all `CLOSED`, or there were zero blockers.
  - The final verification set passed, and its digest is bound.
  - The candidate path set equals the cumulative allowlist intersected with the observed changes, and
    the digests match.
  - Branch and HEAD equal their bound values.
  - The policy allows the operation, and the OWNER opted in at Stage start.
- **Git operation ladder (R09).** Staging is its own receipt-backed operation, and durable intent precedes
  **any** index mutation:
  1. `GIT_INTENT` is persisted and fsynced **before any index mutation**. It binds:
     - `operation_id`;
     - `pre_head`;
     - `pre_index_digest`, a digest of the `git ls-files --stage` output, read-only;
     - the authorized candidate: the path set plus per-path content digests;
     - `intended_tree`, a tree ID computed against a **temporary index file outside `.git/index`**, so the
       real index is untouched while computing it;
     - `commit_message_digest`, where the message contains the trailer `AWE-Operation: <operation_id>`;
     - the author/committer identity policy;
     - `predicate_digest`.
  2. `STAGING_DISPATCHED`: the staging command is about to run against the real index.
  3. `STAGED`: the observed index tree equals `intended_tree`.
  4. `COMMIT_INTENT` is persisted immediately before `git commit`.
  5. `COMMIT_RECEIPT {resulting_head, observed parent, tree, message digest, author, committer}`.

  **"Nothing happened" is never inferred from a phase name for a Git operation.** Recovery always
  re-observes the index and HEAD. Recovery by crash point:
  - **Before `git add`** (`GIT_INTENT` present; the index digest equals `pre_index_digest`): proceed with
    staging.
  - **During staging** (the index digest is neither the pre-index nor the intended one): re-run staging
    only if *every* differing index entry is on a candidate path **and** equals either its pre-index
    entry or its intended entry. Staging the candidate paths is idempotent. Anything else, including a
    leftover `.git/index.lock`, goes to `OWNER_DECISION_REQUIRED` (`GIT_RECOVERY_AMBIGUOUS`). AWE never
    deletes a lock or resets the index.
  - **After staging** (the index tree equals `intended_tree`, with HEAD still `pre_head`): proceed to
    `COMMIT_INTENT`.
  - **Before commit** (`COMMIT_INTENT` present, HEAD still `pre_head`): `git commit` updates the ref
    atomically, so no commit landed. Commit once. If HEAD has advanced, apply the adoption rule below.
- **Adoption rule (R10).** A recovered commit at HEAD is adopted **only if every authorized semantic
  identity field matches** the durable `GIT_INTENT` / `COMMIT_INTENT`:
  - parent equals `pre_head`;
  - tree equals `intended_tree`;
  - the commit message digest equals `commit_message_digest`, which includes the `AWE-Operation`
    correlation trailer;
  - author and committer satisfy the recorded identity policy, with timestamps excluded;
  - a durable intent or receipt for this `operation_id` exists.

  If any field differs, including a commit with the **same parent and same tree but a different
  message**, the commit cannot be proven to belong to the AWE operation. The run then freezes in
  `OWNER_DECISION_REQUIRED` (`GIT_RECOVERY_AMBIGUOUS`) with the options `KEEP_FROZEN`, `ABORT_STAGE` and
  `AMEND_STAGE_CONTRACT`. There is no adopt option, and no second commit is created.
- Git capability confinement: `approval_git.py` remains the only module able to construct a mutating
  argv, and OS-level confinement is added so provider processes cannot run `git commit` or `git push`
  against the worktree, per the EP-1 or sandbox mechanism.

**Explicit exclusions.**
- Push and merge remain governed separately. Push stays behind its own gate unless a later, separate
  contract says otherwise.
- No PR creation, merge, branch deletion, reset, rebase or stash, per AUTO-016 §20 and §24.
- No change to `self-governance.yaml` for this repository without a separate OWNER act.

**Files and components expected to change.** `approval_git.py`, `application.py`, `recovery.py`,
`config.py`, tests, and `SECURITY_MODEL.md` and `HUMAN_AUTHORIZATION_MODEL.md` amendments if OD-GSE-04
permits automatic commit. Those amendments are MAJOR changes requiring explicit OWNER sign-off.

**State/schema additions.** The `GIT_INTENT`, `STAGING_DISPATCHED`, `STAGED`, `COMMIT_INTENT` and
`COMMIT_RECEIPT` artifacts in `operations/`, the corresponding `GIT_OPERATION_*` events, and the
`GIT_RECOVERY_AMBIGUOUS` decision kind.

**Invariants.**
- INV-05: no Git action is possible while retry is exhausted or a decision is pending, and this is
  structural (there is no edge).
- `DONE` never emits `START_STAGE`.
- Commit and push are separate operations, never both.

**Machine-verifiable acceptance.**
1. Each predicate, falsified alone, refuses the action.
2. A kill -9 between `git commit` and receipt persistence, followed by resume, adopts the HEAD only when
   all R10 fields match, and does not create a second commit.
3. The R09 staging crash tests:
   - a kill -9 before `git add`, then resume, stages and commits exactly once;
   - a kill -9 during staging, with a partially staged candidate subset, then resume, re-stages
     idempotently and commits once;
   - a staged foreign, non-candidate entry at resume gives `GIT_RECOVERY_AMBIGUOUS`;
   - a leftover `index.lock` gives `GIT_RECOVERY_AMBIGUOUS`, and the lock is not deleted;
   - a kill -9 after staging, then resume, commits once;
   - a kill -9 after `COMMIT_INTENT` with HEAD unchanged, then resume, commits once.
4. **Same-tree/different-message regression (R10).** A commit is planted with the same parent and same
   tree as the intent but a different message, with no `AWE-Operation` trailer. Resume must give
   `OWNER_DECISION_REQUIRED` (`GIT_RECOVERY_AMBIGUOUS`), no adoption, and no second commit. Variants of
   the same test cover a different author/committer policy and a missing intent.
5. A foreign commit with a different parent or tree at resume also gives `GIT_RECOVERY_AMBIGUOUS`.
6. After `DONE`, no new run exists for any Stage until an OWNER-initiated `START_STAGE <stage-id>` is
   applied. No message names a successor Stage (R11).
7. **FA-5b.** A provider-process confinement test shows that `git commit`, `git add` and a direct write
   to `.git/` from a provider sandbox all fail. Combined with FA-5a, this completes full FA-5 as the
   enablement evidence.

**Tests.** The above.

**Restart/idempotency.** Adoption requires the full R10 identity: parent, tree, message digest with the
correlation trailer, author/committer policy, and a durable intent or receipt. Tree and parent equality
alone are never sufficient.

**Evidence required.** The predicate matrix, the R09 and R10 crash and regression tests, and the FA-5b
confinement proof.

**Completion marker.** Registry `COMPLETE`, with FA-5b evidenced. Enabling execution on any real
repository is a separate recorded OWNER act. It requires full FA-5 (FA-5a from AUTO-023 and FA-5b from
this stage) together with FA-1..FA-4 and FA-6.

**Dependencies on later stages.** None; this is the last stage.

**Must NOT be implemented early.** All of it. No earlier stage may add any automatic Git capability.

---

## 5. Dependency Chain (accepted OD-GSE-12)

Hard technical dependencies (→ means "must be COMPLETE before"):

```text
ST-01 ─► ST-02 ─► ST-03 ─► ST-05 ─► ST-04
ST-01 + ST-02 ─► ST-06
ST-02 + ST-03 + ST-06 ─► ST-07
ST-05 ─► ST-08 ─► ST-09 ◄─ ST-07
ST-01..ST-09 + FA-1..FA-6 ─► ST-10
```

**Accepted execution order.** This is binding, it is linear, and only one task is `Current` at a time
under `maximum_current_tasks: 1`:

```text
AUTO-017 (ST-01) → AUTO-018 (ST-02) → AUTO-019 (ST-03) → AUTO-021 (ST-05) → AUTO-020 (ST-04)
→ AUTO-022 (ST-06) → AUTO-023 (ST-07) → AUTO-024 (ST-08) → AUTO-025 (ST-09) → AUTO-026 (ST-10)
```

The existing stage numbering is preserved. AUTO-021 (ST-05) must be `COMPLETE` before AUTO-020 (ST-04)
may be authorized, because retry-exhaustion OWNER actions must exist before bounded multi-cycle
remediation is enabled. Each stage's execution predecessor is the stage immediately before it in this
chain. Completing a stage never authorizes the next one; every stage needs its own fresh written OWNER
authorization.

---

## 6. OWNER Decisions

### 6.1 Accepted (OWNER, 2026-09-28)

| ID | Accepted ruling | Incorporated in |
|---|---|---|
| **OD-GSE-01** | MEDIUM and LOW findings stay deferred and non-blocking. Only blocking findings enter remediation. | §2.5 severity policy; AUTO-017 policy fields and acceptance 5b; AUTO-020 scope |
| **OD-GSE-02** | The discovery blocker ceiling stays configurable, with a default of 3. Overflow becomes `OWNER_DECISION_REQUIRED` and does not invalidate the one discovery review. | §2.2 edges; §2.5 blocker ceiling; §2.6 `DISCOVERY_OVERFLOW`; AUTO-017 `max_blockers`; AUTO-020 behavior |
| **OD-GSE-03** | `EXTEND_REMEDIATION` grants exactly +1 remediation/closure cycle, with at most 2 OWNER-authorized extensions per run. | §2.6 `RETRY_EXHAUSTED` options; INV-04; AUTO-017 `max_owner_extensions = 2`; AUTO-021 application semantics |
| **OD-GSE-06** | An AWE-native Stage Start authorization is authoritative. Project registry authorization or status is an additional precondition. Any disagreement refuses execution. | AUTO-017 scope and acceptance 5/5a |
| **OD-GSE-07** | The ten stages are registered as AUTO-017 through AUTO-026, with the aliases AWE-AUTO-ST-01..10 preserved. | Header mapping table; stage headings; `STAGE_REGISTRY.md` §4/§5; `docs/TASK_QUEUE.md` |
| **OD-GSE-12** | Existing numbering is preserved. Execution order is ST-01 → ST-02 → ST-03 → ST-05 → ST-04 → ST-06 → ST-07 → ST-08 → ST-09 → ST-10, and ST-05 completes before ST-04. | Header mapping table; §5; AUTO-020 prerequisites |

Accepted decisions are binding on every future stage contract in this program. A contract may narrow
them. It may not contradict them without a new, recorded OWNER decision.

### 6.2 Still OPEN (not decided; each blocks only the stage named)

These are listed in the order in which they become blocking.

### OD-GSE-10 — Worktree disposition on `ABORT_STAGE` / `AMEND_STAGE_CONTRACT`
**Current state:** AWE never resets, cleans or stashes. OD-6 (cancellation semantics) is still open.

**Alternatives:**

- **(a) Leave the worktree untouched.** A fresh start requires a clean tree, so the OWNER disposes of the
  changes manually.
- **(b) For AMEND, carry forward.** The new run adopts the existing changes as an inherited, fingerprinted
  baseline, which the amended contract's allowlist must cover. For ABORT, apply (a).
- **(c) AWE exports a patch to the external evidence root** using the read-only `git diff`, then applies
  (a).

**Planner recommendation (not decided): (b) for AMEND and (a)+(c) for ABORT.** No worktree mutation is ever performed by AWE.

**Status: OPEN.** **Blocks:** AUTO-021 (ST-05), which is 4th in execution order. The OWNER has not decided it, and this plan does not decide it.

### OD-GSE-09 — Post-remediation verification failure inside a cycle
**Question:** the verification set can fail after a remediation, in which case the closure verifier is
not invoked. That makes the cycle incomplete under the brief's definition.

**Alternatives:**

- **(a) Strict.** The cycle is incomplete. `OWNER_DECISION_REQUIRED` (`POST_REMEDIATION_VERIFICATION_FAILED`)
  offers `RETRY_CYCLE` (counts as a cycle), `KEEP_FROZEN`, `ABORT_STAGE` and `AMEND_STAGE_CONTRACT`.
- **(b) Auto-fold.** The cycle is marked complete with all findings OPEN plus a regression flag, and the
  next cycle runs automatically if budget remains.

**Consequences:** (b) automates more but changes the brief's cycle-completion definition. (a) preserves
it.

**Planner recommendation (not decided): (a).**

**Status: OPEN.** **Blocks:** AUTO-020 (ST-04), which is 5th in execution order. The OWNER has not decided it, and this plan does not decide it.

### OD-GSE-11 — Closure-verification scope in cycles 2..N
**Alternatives:**

- **(a) Verify only the currently OPEN frozen IDs** (today's behavior).
- **(b) Verify all frozen IDs every cycle.** A regression may move CLOSED → OPEN. Still no new IDs.

**Consequences:** under (a), a later remediation that re-breaks an earlier fix goes undetected until
human review.

**Planner recommendation (not decided): (b).**

**Status: OPEN.** **Blocks:** AUTO-020 (ST-04), which is 5th in execution order. The OWNER has not decided it, and this plan does not decide it.

### OD-GSE-08 — Reviewer independence in per-role model selection
**Current state:** independence holds only because Claude implements and Codex reviews (E5).

**Alternatives:**

- **(a) No constraint.**
- **(b) The `(adapter, model)` pair must differ between IMPLEMENTER/REMEDIATOR and DISCOVERY_REVIEWER/CLOSURE_VERIFIER.**
- **(c) The provider family must differ.**

A separate question is whether a mismatch between reported and requested model stops the run.

**Planner recommendation (not decided):**

- **(b) as a hard floor. A different family by default, and same-family selection requires an explicit
  acknowledgement recorded in the start decision.**
- A mismatch between reported and requested model gives `OWNER_DECISION_REQUIRED`.

**Status: OPEN.** **Blocks:** AUTO-022 (ST-06), which is 6th in execution order. The OWNER has not decided it, and this plan does not decide it.

### OD-GSE-05 — Telegram OWNER principal, attestation, key custody, and expiry
**Alternatives for attestation:**

- **(a) Telegram identity only** (user ID plus chat ID). A compromised Telegram account or Hermes
  instance becomes OWNER authority.
- **(b) Per-decision one-time code.** The OWNER replies with a TOTP (RFC 6238) code from a separate
  authenticator. AWE verifies it with a secret held outside every provider's and Hermes's reach, and the
  code is bound to the challenge by including the nonce in the reply.
- **(c) An asymmetric signature** (e.g., Ed25519) produced on an OWNER device, which is strongest but
  needs signing tooling on the phone.

**Expiry alternatives:** fixed (e.g., 24 h) or per-kind (e.g., 24 h for exhaustion, 1 h for Git).

**Planner recommendation (not decided):**

- Use **(b)** now, with an upgrade path to (c) behind the same `AttestationVerifier` port.
- Principal = Telegram user ID + chat ID + TOTP secret reference.
- Default expiry is 24 h for policy decisions. Expiry leads to a reissue with the same decision ID and a
  new nonce.
- The local CLI principal stays available as a fallback that requires physical terminal presence.

**Status: OPEN.** **Blocks:** AUTO-024 (ST-08) and AUTO-025 (ST-09), which are 8th and 9th in execution order. The OWNER has not decided it, and this plan does not decide it.

### OD-GSE-04 — Automatic commit vs. the mandatory human commit gate
**Current state:** there is a double gate (config flag plus typed confirmation), print-only by default.
`self-governance.yaml` sets `allow_automatic_commit: false`, and §5a.6 requires automatic approval to be
opt-in at the point of use (E12).

**Alternatives:**

- **(a) Keep the mandatory human commit gate.** ST-10 then only moves the approval onto the authenticated
  decision API and adds receipts and recovery.
- **(b) Per-Stage opt-in automatic *local commit*.** It is chosen at `START_STAGE` and frozen in the
  policy, executed only when every ST-10 predicate and FA-1..6 hold. Push stays gated and merge stays
  forbidden.
- **(c) Automatic commit and push.**

**Consequences:** (b) and (c) require MAJOR amendments to `HUMAN_AUTHORIZATION_MODEL.md`,
`SECURITY_MODEL.md` and AUTO-016 §20. (c) also removes the last human checkpoint before a remote-visible
effect.

**Planner recommendation (not decided): (b)**, with the start-time opt-in treated as the point-of-use approval required by
§5a.6. This repository's own `self-governance.yaml` stays `false` unless changed by a separate act.

**Status: OPEN.** **Blocks:** AUTO-026 (ST-10), which is last. The OWNER has not decided it, and this plan does not decide it.

### 6.3 External prerequisites

- **EP-1. Deferred until AUTO-023 (ST-07).** A Hermes execution interface specification covering submit,
  status by ID, result retrieval, idempotent resubmit, and confinement capabilities. It blocks
  finalizing the AUTO-023 contract.
- **EP-2. Deferred until AUTO-025 (ST-09).** A Hermes Telegram messaging interface specification. It must
  provide:
  - a stable inbound message/update identity;
  - replay, polling or equivalent redelivery;
  - an acknowledgment or cursor operation controlled by AWE, so that AWE can persist before
    acknowledging (R07).

  It blocks finalizing the AUTO-025 contract.
- **EP-3. Reconciled 2026-09-28.** The T-307 task-mirror drift (E17) was corrected. The live
  `docs/current_task.md` statement was updated, and dated append-only reconciliation notes were added to
  `docs/TASK_QUEUE.md`, `docs/remaining_tasks.md`, `docs/PROJECT_STATE.md` and `docs/CHANGELOG.md`. The
  correction record is in `docs/DECISION_LOG.md`, 2026-09-28. No historical record was altered.

---

## 7. Shared Governance Mechanics

1. **Order of acts (R04).** Each stage follows AUTO-016's precedent, in this order:
   1. **Contract preparation.** The contract `stage-prompts/AUTO-0XX.md` is drafted, reviewed once by a
      bounded independent contract review, and corrected. This is documentation-only governance work,
      and it happens **before** implementation authorization.
   2. **OWNER implementation authorization**, recorded in `STAGE_REGISTRY.md` §5 and in the task record.
   3. Branch creation, from a synchronized `main`.
   4. Implementation prompt execution and production implementation.

   **Contract preparation is not Stage implementation authorization.** It creates no branch, executes no
   implementation prompt, changes no production code, and promotes no lifecycle state. OWNER
   authorization is required before branch creation, implementation prompt execution, production
   implementation, and any lifecycle promotion (`NOT_STARTED → AUTHORIZED`, `Planned → Current`).
2. Each contract lists the AUTO-016 contract sections it amends: §10, §11, §13, §17, §19, §20, §21 or §22
   as applicable. An amendment narrows or extends explicitly. It never re-interprets silently.
3. Only one stage is `Current` at a time (`maximum_current_tasks: 1`).
4. No stage authorizes its successor. Completion of a stage authorizes nothing.
6. All ten stages are **registered** as `NOT_STARTED` / `Planned` (2026-09-28, OD-GSE-07). Registration is
   not authorization. Each stage becomes `AUTHORIZED` only through its own written OWNER authorization
   under `STAGE_REGISTRY.md` §3 rules 1–3, after its contract exists and its execution predecessor (§5)
   is `COMPLETE`.
5. Live acceptance (real providers, Hermes or Telegram) is always a separately recorded OWNER act, never
   part of the default test suite.

---

## 8. Plan Summary

This plan is the governing architecture artifact for AUTO-017 … AUTO-026.

The existing AUTO-016 runner already provides the transition authority, the closed state table, atomic
state publication, a content-fingerprint in-flight reconciliation, strict result grammars, redaction, and
a gated two-surface Git authority. The program extends that runner in place. It adds a frozen execution
policy, then an event log with a six-phase operation ladder that closes two crash windows found by
inspection (E8, E9). It generalizes the fixed 1/1/1 review budgets into one discovery plus 1..3 paired
remediation and closure cycles, and it adds a durable, transport-neutral OWNER decision service. After
that come per-role model binding, a Hermes execution adapter that is only a port, authenticated
decisions, a Telegram transport that is only a port, and finally controlled Git automation.
Autonomy-sensitive capabilities are built early but enabled only when the evidence for FA-1..FA-6 exists.

---

## 9. Revision 2 — Remediation of the frozen discovery findings (AWE-GSE-R01 … R11)

One independent discovery review produced the frozen finding set AWE-GSE-R01 … AWE-GSE-R11. Revision 2
remediates exactly those findings. It performs no new discovery, adds no finding IDs, changes no accepted
OWNER decision, and decides no open one.

| Finding | Where it is remediated |
|---|---|
| R01 (BLOCKER) | §3: FA-5a and the live-provider isolation gate. AUTO-023 scope, acceptance 7–8 and completion marker. §4 common requirements (test doubles before the gate). |
| R02 | §2.2 (the `OWNER_DECISION_REQUIRED → REVIEWING` edge is removed). §2.4 (`DISPATCH_INTENT` before spawn, distinct from `DISPATCH_RECEIPT`; ambiguity freezes for the OWNER; AUTO-016 `REINVOKE_PROVIDER` superseded for v2). §2.6 (`DISCOVERY_MALFORMED` has no retry). INV-02. The AUTO-019 matrix and acceptance. AUTO-018 acceptance 4. AUTO-020 acceptance. |
| R03 | The header execution-predecessor semantics. `STAGE_REGISTRY.md` v7.0 (§1 scope, §3 rules 1 and 10) and SSP v1.4 (stage ordering, naming). `docs/TASK_QUEUE.md` program note. |
| R04 | §7 item 1 (order of acts). SSP v1.4, "Contract preparation". `STAGE_REGISTRY.md` rule 3a. `docs/TASK_QUEUE.md` program note. |
| R05 | AUTO-024 is rewritten to be mechanism-neutral (SP-1..SP-6 and a conformance suite over every still-valid OD-GSE-05 option). FA-1 and FA-2 wording. AUTO-021 exclusions. |
| R06 | AUTO-024: a single authoritative consumption event, persisting the response before consumption, and restart cases (1)–(4). §2.3 (the nonce marker directory is removed). |
| R07 | AUTO-025: EP-2 requirements, the durable inbound protocol (persist before acknowledgment), duplicates, and the crash-boundary acceptance 8–9. §6.3 EP-2. |
| R08 | AUTO-026 entry prerequisites (FA-5a only; FA-5b established by AUTO-026). §3 FA-5 split and the executing-Git row. |
| R09 | §2.4 Git note. AUTO-026 Git operation ladder (`GIT_INTENT` before any index mutation) with per-crash-point recovery, and acceptance 3. |
| R10 | AUTO-026 adoption rule (parent, tree, message digest with correlation trailer, author/committer policy, durable intent or receipt), the same-tree/different-message regression acceptance 4, and freeze for the OWNER. |
| R11 | §2.1 rule 3 and §2.6 (`START_STAGE` is an OWNER-initiated command with an explicit Stage ID; the solicitation wording is removed). AUTO-026 acceptance 6. |
