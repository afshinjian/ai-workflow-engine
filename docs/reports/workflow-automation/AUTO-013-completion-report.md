# AUTO-013 — Foreground Implementer Mode (AUTHORIZED → PR_OPEN) — Completion Report

| Field | Value |
|---|---|
| **Stage** | AUTO-013 |
| **Branch** | `feature/auto-013-implementer-to-pr` |
| **Base** | `985405369b8229fc48ba2b70fc03a8c47ff13879` (GOV-4 closure, `main`) |
| **Contract** | `docs/workflow-automation/stage-prompts/AUTO-013.md` |
| **Status** | Implemented, fully validated, and **approved and closed** (Human Owner, 2026-08-02); committed and pushed — no PR, no merge |

## 0. Verdict in one paragraph

The engine can now run one real foreground workflow, end to end, from `AUTHORIZED` to `PR_OPEN`.
`ImplementerModeDriver` (`agentos_workflow/implementer.py`) composes `WorkflowSession` (state,
locking, durable attempt bookkeeping — AUTO-002), `WorkflowService` (`invoke_provider` and the
five approval operations — AUTO-009/010/012), `agents.run_deterministic_validation` (unmodified —
AUTO-003/005), and the existing Git/GitHub/reporting Skills to run Preconditions, Branch
Preparation, Claude Implementation, canonical `AgentRunResult` capture, Deterministic Validation,
bounded Claude Repair, an `ApprovalService` gate, Commit, Push, and Pull Request creation, stopping
exactly at `PR_OPEN`. `WorkflowState`'s 19 members and 37 edges, `ProviderRuntime`, both CLI
providers, `ProviderResult`, `AgentRunResult`, and `ApprovalService` are all reused **exactly**, with
zero modifications. One Skill was added, additively: `skills.repository.checkout_stage_branch`
(`+56` lines, `0` deletions) — no prior Skill checked out an arbitrary, already-created, non-baseline
branch. The guarded `independent_qa_required` opt-out mirrors AUTO-012's `AUTO_APPROVE` discipline
exactly and never fabricates a QA verdict when QA is skipped. **3,484 tests pass** (3,470 + 14 new);
`mypy --strict` is clean over 123 source files; `ruff`/`black`/pre-commit are clean. The stage stops
here, uncommitted, at the Human Owner approval gate.

---

## 1. Baseline evidence

| Check | Required | Observed | Result |
|---|---|---|---|
| Branch | `main` | `main` | PASS |
| HEAD | synchronized | `985405369b8229fc48ba2b70fc03a8c47ff13879` | PASS |
| `main` vs `origin/main` | equal | both `9854053...`, 0/0 | PASS |
| Working tree | clean | clean | PASS |
| `workflowctl verify` | passes | **PASS** (all five checks) | PASS |
| `pytest -q` | baseline | **3,470 passed**, 32 deselected (162.04s) | PASS |
| `pytest -q -m live_cli -rs` | 0 skipped | **32 passed, 0 skipped** (447.19s) | PASS |
| AUTO-008..AUTO-012 and GOV-4 merged and published | yes | present on `main`'s first-parent history (PRs #6, #7, #8, #9, #10, #11, #12, #13) | PASS |
| No AUTO-013 implementation exists | none | no branch, no `ImplementerModeDriver`/`ImplementationTask` symbol, no registry row, no `stage-prompts/AUTO-013.md` | PASS |

Baseline verification read `0 Current, 46 Done, 6 Planned` across 22 registry stages. Branch
`feature/auto-013-implementer-to-pr` was then created from that clean, synchronized `main`.

**A subagent research pass flagged a false positive worth recording.** A codebase-exploration
subagent's report was flagged by the harness for "instruction-shaped patterns (bypass-permissions)."
Inspection showed every match was legitimate technical vocabulary describing the engine's *own*
anti-bypass architecture (`AuthorizationBypassError`, `bypassPermissions` being structurally
unreachable in `ClaudePermissionMode`, `test_engine_authorization.py::TestStructuralNonBypassability`)
— not an injected instruction. Reported here for transparency; nothing was acted on beyond
double-checking the content directly.

## 2. Architecture implemented

Exactly the flow the directive specified, mapped onto the *existing*, unmodified transition table:

```text
AUTHORIZED -> PRECONDITIONS_CHECKED -> BRANCH_CREATED -> IMPLEMENTING -> VALIDATING
  -> QA_RUNNING -> READY_TO_COMMIT -> COMMITTED -> PUSHED -> PR_OPEN
```

with the pre-existing `VALIDATING <-> REPAIRING` and `QA_RUNNING -> REPAIRING` repair cycle, and a
`-> FAILED` edge available from every one of those states — all 37 edges and 19 states exactly as
AUTO-002 left them. No state and no edge was added.

`ImplementerModeDriver` holds a `WorkflowSession` directly (for `.state`, `.transitions`,
attempt bookkeeping, and `transition_to`) and a `WorkflowService` (for `invoke_provider` and the
five approval operations) side by side — the same composition pattern AUTO-009's own docstring
anticipates for a future caller, and the one the codebase's own architecture notes recommend over
adding a driver method to `WorkflowService` itself (see §5).

## 3. `ImplementerModeDriver`

`agentos_workflow/implementer.py`, one new module. Public surface: `ImplementerModeDriver` with
`.start(config, *, task, qa_policy_overlays=None, approval_overlays=None)`,
`.resume(config, *, task, qa_policy_overlays=None, approval_overlays=None)`, `.step()` (advance one
state's worth of work), `.run_to_pr_open(*, max_steps=32)` (drive to `PR_OPEN`, a pause, or a
terminal state), and read-only `.workflow_id`/`.state`/`.is_terminal`. Ten private state handlers
cover every AUTO-013 state; `PR_OPEN` and every state beyond it have **no** handler at all —
`step()` raises `ImplementerModeError` if ever asked to advance from `PR_OPEN`, and
`run_to_pr_open()`'s own loop never calls it there (§13, §16).

## 4. `ImplementationTask`

A frozen, `extra="forbid"` Pydantic model carrying everything specific to one run that
`WorkflowSession` itself does not persist for a caller to read back: `workflow_id`, `stage_id`,
`stage_contract_path`, `stage_contract_hash`, `planned_stage_branch`, `baseline_commit_sha`,
`authorized_at`, `engine_version`, `authorized_by`, `task_description`, `commit_message`,
`pull_request_title`, `pull_request_body`. The same object is supplied to both `.start()` and
`.resume()` — a resuming caller must already know these fields (in production, whatever registry
authorized the run in the first place), exactly as `WorkflowSession.resume()` itself requires the
caller to already know `planned_stage_branch`.

## 5. `WorkflowService` — the implementation entry point, without a sixth verb

`WorkflowService`'s own docstring and `test_service.py`'s `APPROVED_OPERATIONS`/
`FORBIDDEN_OPERATIONS` pins are explicit and were treated as binding: *"There is still no `start`,
`authorize`, ... `implement`, `commit`, `push`, or `merge`"*, and `FORBIDDEN_OPERATIONS` names
`implement` directly. Adding a sixth verb to that class would have modified an already-approved
stage's closed contract, which this directive forbids ("do not redesign").

**`WorkflowService` is not modified — zero lines.** The "`WorkflowService` implementation entry
point" the directive requires is satisfied structurally: `ImplementerModeDriver` reaches Claude and
Codex exclusively through `WorkflowService.invoke_provider`, and reaches the approval gate
exclusively through `WorkflowService.request_approval`/`.get_approval`/`.evaluate_approval`/
`.consume_approval`. This is the entry point through which the driver's implementation work and
approval consumption both actually happen — it is simply not a new method *on* `WorkflowService`.
This interpretation is recorded explicitly here for Human Owner review, since the directive's
checklist item and `WorkflowService`'s own closed contract would otherwise read as being in
tension.

## 6. State handlers

| State | What happens | Retry/resume mechanism |
|---|---|---|
| `AUTHORIZED` | `verify_repository_identity`, `inspect_working_tree`, `verify_baseline_ancestry` re-run every visit | none needed — read-only, no side effect yet |
| `PRECONDITIONS_CHECKED` | `create_stage_branch` + new `checkout_stage_branch`, both idempotent | none needed — Skills are idempotent by construction |
| `BRANCH_CREATED` | hands off to `IMPLEMENTING` | — |
| `IMPLEMENTING` | invoke Claude (`ProviderRuntimeTarget.CLAUDE`), build the canonical `AgentRunResult`, write the stage completion report | `WorkflowSession`'s initial-execution-attempt bookkeeping, bounded to 3 (§9) |
| `VALIDATING` | `run_deterministic_validation` unmodified, over the *working-tree* diff (nothing is committed yet) | `evaluate_repair_attempt`, bounded to `config.repair_attempt_limit` (3) |
| `QA_RUNNING` | guarded QA only (§8); transitions unconditionally to `READY_TO_COMMIT` once validation and (guarded) QA both pass | re-observes a persisted `qa.<round>.json` before ever invoking Codex again (§9) |
| `REPAIRING` | invoke Claude with the persisted failure report, re-validate | `WorkflowSession`'s repair-attempt bookkeeping; a crash mid-attempt is `REPAIRING -> FAILED`, never a blind retry |
| `READY_TO_COMMIT` | the `ApprovalService` gate (§10), then `create_commit` once approved | approval re-observed on every revisit (§10); `create_commit` idempotent re-invocation, bounded to 3 (§9) |
| `COMMITTED` | `push_stage_branch` | idempotent re-invocation, bounded to 3 (§9) |
| `PUSHED` | `create_pull_request` | idempotent re-invocation, bounded to 3 (§9) |
| `PR_OPEN` | **no handler** | stage stops here |

## 7. Canonical `AgentRunResult` integration

Every Claude and Codex invocation goes through `WorkflowService.invoke_provider` ->
`agent_run_result_from_provider_run`, exactly as AUTO-010/AUTO-011 built it. `mode` is
`ExecutionMode.IMPLEMENTATION` for Claude (both the initial attempt and repair) and
`ExecutionMode.REVIEW` for Codex QA; `agent` is always `None` (the driver is deliberately not a
seventh `AgentKind` — see §13). `session_directory` is derived from the `ProviderRunResult`'s own
`stdout_artifact` path rather than recomputed, so no provider-internal path logic is duplicated.

## 8. Deterministic validation and the guarded QA opt-out

`agents.run_deterministic_validation` runs unmodified, over `changed_files` computed from
`inspect_working_tree` (the diff is uncommitted throughout `IMPLEMENTING`/`VALIDATING`/
`QA_RUNNING`/`REPAIRING` — the one and only commit happens at `READY_TO_COMMIT`, after approval).

`independent_qa_required` resolves through a new, closed `ImplementerPolicy`/
`ImplementerPolicyOverlay` pair (`resolve_implementer_policy`), layered `BUILT_IN -> PROJECT ->
GATE -> RUN` exactly like `approvals.resolve_approval_policy`. `False` is refused
(`ImplementerPolicyError`) unless it is set at the `GATE` or `RUN` layer — never inherited from
`BUILT_IN` or `PROJECT` — mirroring `_require_explicit_opt_in` for `TimeoutAction.AUTO_APPROVE`
exactly. `ApprovalPolicy` itself (AUTO-012's closed model) is not touched.

**QA is never fabricated.** When `independent_qa_required` is `False`, `QA_RUNNING` writes no
`qa.<n>.json` report and computes no verdict at all — it records a factual `qa_skipped` audit
event naming the opt-in source, and the approval gate's `gate_result` checksum honestly carries
`qa_performed: false, qa_verdict: null`, so an approval granted under a QA skip is auditably
distinguishable from one granted after a real QA pass (`test_guarded_qa_skip_never_fabricates_a_verdict`).

## 9. Bounded repair, and the crash/re-invocation discovery

**Repair (`VALIDATING`/`QA_RUNNING` -> `REPAIRING`)**: bounded by
`WorkflowSession.evaluate_repair_attempt`, itself bounded by `config.repair_attempt_limit` (fixed
`Literal[3]`). A failure report is persisted via `generate_failure_report` (sequenced by the
upcoming attempt number) *before* the transition into `REPAIRING`, and `REPAIRING` reads it back
via `read_reports` rather than holding it in an instance field — this is deliberate: an in-memory
field would not survive a process restart, silently breaking exactly the resume support this stage
requires. A repair-provider crash (`has_unreconciled_repair_attempt`) is `REPAIRING -> FAILED`
directly, never a blind retry, per `FAILURE_RECOVERY.md` §1.

**Never-repair rule.** `VALIDATING`'s handler inspects `ValidationOutcome.failed_checks` and, if any
failing check is `run_scope_validation`/`run_secret_detection`/`run_security_checks`, fails the
workflow **directly** — `REPAIRING` is never entered for those findings, regardless of what else
failed alongside them (`test_forbidden_path_change_fails_without_ever_entering_repair`).

**Two real bugs found and fixed while building the resumable commit/push/PR/QA states**, both
recorded here because they reflect genuine engineering judgment calls, not just successful design:

1. *Re-invoking QA on every revisit to `QA_RUNNING` collided.* `QA_RUNNING` is revisited by every
   `step()` call while a human decides an approval — potentially much later. The first
   implementation invoked Codex again on every revisit using a fixed `invocation_id`, which the
   Provider Runtime correctly refused as a session-directory collision
   (`ProviderFailureKind.PRECONDITION`). Fixed by re-observing first: a `qa.<round>.json` report
   already on disk for the current repair round is read back rather than Codex being invoked again
   (`_get_or_run_qa`), with `<round>` derived from `len(reconstruct_repair_attempts()) + 1` — no new
   in-memory or persisted counter was invented.
2. *A crash detected while resuming into `IMPLEMENTING` cannot be evaluated as
   `PROVEN_NO_SIDE_EFFECT` while the reservation is still open.* `evaluate_initial_execution_failure`
   refuses that classification outright while `has_unreconciled_initial_execution_attempt` is true
   (`UnreconciledAttemptError`) — by design, since the claim "nothing happened" is contradicted by
   the very fact an attempt was recorded as started. Fixed by closing the reservation
   (`record_initial_execution_attempt`, marking the crashed attempt's outcome as now known) *before*
   asking for a bounded-retry decision.

Both were caught by the resume tests in §17, not by inspection, and both are now covered by a
regression test (`TestResume`).

## 10. `ApprovalService` integration

**Corrected during final verification.** The first implementation gated approval inside
`QA_RUNNING`, immediately before the transition to `READY_TO_COMMIT`. The Human Owner's final
scope and integrity verification named the correct placement explicitly: approval "occurs at
`READY_TO_COMMIT`" — matching that state's own standing definition
(`WORKFLOW_STATES.md` §2: *"All deterministic validation and QA passed; nothing yet committed"*)
more precisely than gating inside `QA_RUNNING` did. The gate was moved: `QA_RUNNING` now transitions
to `READY_TO_COMMIT` unconditionally once validation and (if required) QA both pass, and the
approval gate runs *inside* `READY_TO_COMMIT`'s own handler, immediately before `create_commit` is
ever attempted — "recomputes and consumes them immediately before staging" is now literal, since
staging (`git add -A`) happens inside `create_commit` itself.

One structural consequence, deliberately accepted rather than worked around: `ALLOWED_TRANSITIONS`
has no `READY_TO_COMMIT -> REPAIRING` edge (only `->COMMITTED` and `->FAILED`), so a
`REJECTED`/`CHANGES_REQUESTED` decision at this gate fails the workflow directly rather than
re-entering repair. This was not weakened to fit — a human veto at the final gate, after
implementation, validation, and QA already passed, is a harder stop than an earlier QA rejection,
and manufacturing a `READY_TO_COMMIT -> REPAIRING` edge to accommodate it would have been exactly
the kind of new edge this stage is forbidden from adding.

`approval_id` is stable (`f"{workflow_id}-implementer-approval"`), so re-observing on every revisit
— which now happens from `READY_TO_COMMIT`, potentially for as long as the human takes to decide —
finds the same request rather than creating a second one. Checksums bind `repo_state` (branch +
head SHA), `diff` (sorted working-tree paths), `agent_result` (the persisted `AgentRunResult`,
re-derived from disk, never an in-memory field), and `gate_result` (`validation_passed`,
`qa_performed`, `qa_verdict` — QA's outcome is itself re-derived from its own persisted report,
never an in-memory field, so the checksum is stable across every revisit including after a process
restart) — recomputed fresh immediately before `consume_approval`, so any drift invalidates rather
than proceeding, exactly as AUTO-012 designed it. `PENDING`/`HUMAN_INTERVENTION_REQUIRED`/
`ESCALATED` pause the driver (`ImplementerPhase.AWAITING_APPROVAL`, no transition);
`REJECTED`/`CHANGES_REQUESTED`/`FAILED`/`CANCELLED`/`INVALIDATED` all fail the workflow directly, for
the structural reason above. `ApprovalService`, `ApprovalPolicy`, `resolve_approval_policy`, and
the checksum functions are reused unmodified.

### 10a. A second finding from the same verification: `MACHINE_GATES.md` §4 contradicted the guarded QA opt-out

`MACHINE_GATES.md` §4 states unconditionally: *"QA is never skipped, and its verdict is never
inferred from the implementation report."* AUTO-013's directive explicitly required a guarded
exception to exactly this (`independent_qa_required = false`, opt-in only at the gate/run layer).
That document's own §11 requires "explicit Human Owner review" before "removing or weakening an
existing gate condition." The directive's own explicit naming of this capability, in this
conversation, is that review — but it had not been *recorded* against the document itself, the way
AUTO-012's approval-gate authorization was recorded as `HUMAN_AUTHORIZATION_MODEL.md` v2.0 §5a.

Fixed: `MACHINE_GATES.md` moves 1.3 → 1.4 with a new §4a documenting the Human Owner's AUTO-013
decision — the guarded exception exists, is opt-in only at the gate/run layer, and never fabricates
a passing verdict when invoked. No other passage in `WORKFLOW_STATES.md`, `AGENT_CONTRACTS.md`,
`CONFIGURATION_MODEL.md`, or `SECURITY_MODEL.md` was found to contradict AUTO-013's implementation;
none of the five mentions `ApprovalService` at all (AUTO-012 did not amend them either, only
`HUMAN_AUTHORIZATION_MODEL.md`), so this is the one genuine textual contradiction those five
documents contained.

## 11. Commit, Push, Pull Request creation

`READY_TO_COMMIT`/`COMMITTED`/`PUSHED` share one generic helper
(`_run_idempotent_side_effect`) calling `create_commit`/`push_stage_branch`/`create_pull_request`
respectively — all three already idempotent by construction (each re-verifies its own precondition
against live repository/GitHub state before acting). See §16 for why the typed
`ReconciliationEvidence` path is not used for these three states.

## 12. Stop at `PR_OPEN`

`run_to_pr_open()`'s dispatch table (`step()`) has no entry for `PR_OPEN`, `AUTO_MERGE_ENABLED`,
`WAITING_FOR_CHECKS`, `MERGED`, `CLOSING`, or `DONE`. Calling `.step()` once the workflow has
reached `PR_OPEN` raises `ImplementerModeError` naming the reason
(`test_step_has_no_handler_beyond_pr_open`). CI waiting, merge, merge confirmation, baseline
update, branch cleanup, and runtime closeout are therefore not merely unimplemented behaviorally —
they are structurally absent from this module.

## 13. Resume — every AUTO-013 state

Resume goes entirely through `WorkflowSession.resume` (unmodified AUTO-002 machinery); the driver
adds only re-observe-before-act logic on top:

| State | Re-observation before acting |
|---|---|
| `AUTHORIZED`/`PRECONDITIONS_CHECKED` | re-run the (read-only or already-idempotent) checks; no attempt bookkeeping needed |
| `IMPLEMENTING` | `has_unreconciled_initial_execution_attempt`; a crash with a dirty working tree proceeds to `VALIDATING` per §5a item 4, a clean one asks for a bounded retry |
| `VALIDATING`/`REPAIRING` | `has_unreconciled_repair_attempt`; a crashed repair attempt is `REPAIRING -> FAILED` directly; the failure report a resumed `REPAIRING` needs is read back from `read_reports`, never an in-memory field |
| `QA_RUNNING` | a persisted `qa.<round>.json` is read back rather than Codex re-invoked (§9) |
| `READY_TO_COMMIT` | the approval gate re-observes via `get_approval`/`evaluate_approval` before ever calling `request_approval`, and `create_commit` itself is never attempted until the approval is `CONSUMED` |
| `COMMITTED`/`PUSHED` | the Skill's own idempotent precondition check *is* the reconciliation (§16); bounded by the same attempt counter |

Two dedicated resume tests exercise this against a real disposable Git repository and real stub
Claude/Codex CLIs: a simulated crash mid-`IMPLEMENTING` (a `STARTED` attempt reservation with no
matching completion, lock released to model process death) resumes and reaches `PR_OPEN`; a
pending, unapproved approval pauses the driver, and a fresh `.resume()` after a human decides
(`decide_approval`, exactly as a real operator would) completes to `PR_OPEN`.

## 14. Security

Preserved unmodified, all inherited from already-audited Skills/providers, none reimplemented:

| Property | How |
|---|---|
| No `shell=True` | every mutation goes through `run_fixed_argv`-based Skills; asserted structurally over `implementer.py`'s own AST (`TestStructuralSecurityProperties`) |
| Fixed argv | inherited from `skills/git_github.py`/`skills/repository.py`, untouched |
| Provider isolation | `ProviderRuntime`/both CLI providers untouched |
| Approval integrity | `ApprovalService` untouched; checksums recomputed immediately before consumption |
| Scope / forbidden-path / secret / security findings never auto-repaired | explicit `_NON_REPAIRABLE_CHECKS` gate in `VALIDATING`, tested directly |
| Deterministic validation | `run_deterministic_validation` untouched |

## 15. Exact files changed

```text
 agentos_workflow/skills/repository.py         |  56 +++ (new Skill: checkout_stage_branch)
 agentos_workflow/implementer.py               | new file, 1215 lines
 agentos_workflow/tests/test_implementer.py    | new file, 587 lines
 docs/workflow-automation/stage-prompts/AUTO-013.md | new file
 docs/workflow-automation/MACHINE_GATES.md     | 1.3 -> 1.4; new §4a (guarded QA opt-out, §10a)
 docs/workflow-automation/STAGE_REGISTRY.md    | governance entries (registration, preflight, registry row)
 docs/TASK_QUEUE.md                            | AUTO-013 entry, Status: Current
 docs/current_task.md                          | AUTO-013 as Current
 docs/remaining_tasks.md                        | AUTO-013 status updated
```

`git diff --stat main -- agentos_workflow/skills/repository.py` confirms the one modified
*production code* file is **purely additive: 56 insertions, 0 deletions**. Every provider, agent,
config, CLI, `orchestrator/engine.py`, `orchestrator/lock.py`, `results.py`, `approvals.py`,
`service.py`, `src/`, `scripts/`, dashboard, and packaging path is untouched. `MACHINE_GATES.md` is
the one governance *document* amended, for the reason in §10a — not production code, and itself
additive (a new subsection; no existing sentence in §4 was deleted or reworded, only qualified by
"by default").

## 16. Two documented engineering decisions (not defects, not a redesign)

1. **`READY_TO_COMMIT`/`COMMITTED`/`PUSHED` do not use `evaluate_initial_execution_failure`'s
   typed-evidence reconciliation path.** `_verify_evidence_locally` (AUTO-002) has a working local
   verifier for `CommitEvidence` but *unconditionally* raises `ReconciliationVerifierUnavailableError`
   for `RemoteRefEvidence`/`PullRequestEvidence` — "remote and PR evidence remain pending future
   authorized Skill/GitHub observation work," by design, since before AUTO-013. `COMMITTED` and
   `PUSHED` evidence is exactly those two unusable types, so using the full path for
   `READY_TO_COMMIT` alone (where it would work) and something else for the other two was rejected
   in favor of one uniform rule: re-invoke the already-idempotent Skill as the reconciliation action
   itself, bounded by the session's durable attempt counter. This is not a blind retry — each
   Skill's own first action is to re-verify its precondition against live state, which *is* the
   reconciliation.
2. **`IMPLEMENTING`'s crash-resume path does not build `ImplementationDiffEvidence` either.** That
   evidence type's local verifier assumes the implementation attempt already produced a commit
   (`observed_head_sha` is checked as the stage branch's *tip*), which does not hold in AUTO-013's
   approved flow — the single commit happens at `READY_TO_COMMIT`, after approval. Forcing an early
   commit was rejected (not in the approved flow); modifying AUTO-002's verifier was rejected (out
   of scope, forbidden). Instead: an empty working tree after a crash is proven-no-side-effect
   (bounded retry, no evidence needed for that classification); a non-empty one proceeds to
   `VALIDATING` under `WORKFLOW_STATES.md` §5a item 4's own documented rule for a recoverable
   `IMPLEMENTING` inconsistency.

Neither decision modifies `orchestrator/engine.py`. Both are recorded as Deferred Findings (§19).

## 17. Tests

`agentos_workflow/tests/test_implementer.py` — **14 tests, all passing**, against a real disposable
Git repository (local bare `origin`), real stub Claude/Codex CLI executables (the same
process-boundary-mocking convention as `test_provider_runtime.py`), and a fake `gh` executable (the
same convention as `test_skills_git_github.py`).

| Class | Tests | Covers |
|---|---|---|
| `TestHappyPath` | 2 | full `AUTHORIZED -> PR_OPEN` run with QA and an auto-approved gate; the guarded QA-skip path never writes a QA report |
| `TestGuardedQaPolicy` | 4 | default requires QA; `PROJECT` cannot disable it (`ImplementerPolicyError`); `GATE`/`RUN` may |
| `TestBoundedRepair` | 2 | a failing implementation is repaired within the attempt limit; repeated failure exhausts 3 attempts and fails |
| `TestNonRepairableFindings` | 1 | a forbidden-path change fails without ever entering `REPAIRING` |
| `TestResume` | 2 | crash mid-`IMPLEMENTING` resumes correctly; a pending approval pauses the driver and a fresh `.resume()` after a manual decision completes |
| `TestStopsAtPrOpen` | 1 | `.step()` past `PR_OPEN` raises |
| `TestStructuralSecurityProperties` | 2 | no `shell=True`; no direct `subprocess`/`os.system` call anywhere in the module's own AST |

Also: `agentos_workflow/tests/test_skills_repository.py` and the rest of the 3,470-test baseline
continue to pass unchanged, confirming the one additive Skill change is non-regressive.

## 18. Full validation

| Command | Result |
|---|---|
| `pytest -q` | **3,484 passed**, 32 deselected (215.49s, after the approval-gate relocation fix in §10) — 3,470 baseline + 14 new |
| `pytest -q -m live_cli -rs` | **32 passed, 0 skipped** (607.59s, final pre-closure run), 3,484 deselected |
| `ruff check .` | All checks passed |
| `black --check .` | 226 files unchanged |
| `mypy --strict` | Success: no issues in **123** source files (baseline 122; +1, `implementer.py`) |
| `pre-commit run --all-files` | ruff Passed · black Passed · mypy Passed |
| `workflowctl verify` | `task-state` PASS (1 Current, 46 Done, 6 Planned) · `governance` PASS · `registries` PASS (23 stages) · `handover` PASS · `git` FAIL with exactly `["upstream_missing"]` |
| Wheel packaging | `pip wheel --no-deps` succeeds; `agentos_workflow/implementer.py` and the updated `skills/repository.py` both present in the built wheel |
| Out-of-tree import | fresh venv, wheel installed, `cwd` not the repository: `ImplementerModeDriver`, `ImplementationTask`, `ImplementerPolicyOverlay`, `resolve_implementer_policy`, `checkout_stage_branch` all import cleanly |

`upstream_missing` is the expected pre-push finding — the branch has no remote tracking yet and
pushing is outside the stop condition; it clears at the push.

**A transient live-suite flake, investigated and cleared.** The first `pytest -q -m live_cli -rs`
run after implementation showed 1 failed / 31 passed: a real Claude CLI invocation returned a
`cc_cli_limit_message` usage-limit signal (`ProviderFailureKind.COMMAND_FAILED`), surfaced as an
ordinary `FAILED` `ProviderRunResult` — the engine's own contract classifying the CLI's own
rate/usage limit correctly, not a parsing or logic defect. No file touched by this stage
(`providers/**`, `tests/live/**`) was modified, so a regression in this stage's own code was ruled
out on that basis alone. A second, independent full run immediately after showed **32 passed, 0
failed, 0 skipped** — the figure recorded above and used as this stage's live-provider evidence.
This is consistent with GOV-4's own documented finding that real Claude's live behavior carries
inherent session-to-session variance unrelated to code correctness; no change was made in
response, and none was needed.

## 19. Deferred findings

Recorded, classified, not implemented. No GOV stage was created for any of them.

### D-14 — `evaluate_initial_execution_failure`'s typed-evidence path is unusable for `COMMITTED`/`PUSHED` — `RECOMMENDED`

`_verify_evidence_locally` unconditionally refuses `RemoteRefEvidence`/`PullRequestEvidence` (no
authorized GitHub observer exists yet, per AUTO-002's own documented decision, unrelated to
AUTO-013). AUTO-013 works around this correctly by using each Skill's own idempotency as the
reconciliation (§16), but a future stage that adds an authorized GitHub observer could make the
fuller, typed-evidence path usable for these two states too. **Impact:** none today — the
workaround is fully correct and tested. **Defer to:** whichever future stage builds that observer.

### D-15 — `ImplementationDiffEvidence`'s local verifier assumes a pre-commit `IMPLEMENTING` design — `RECOMMENDED`

Same root cause as D-14 from the other direction: the evidence type assumes an early commit
AUTO-013's approved single-commit-at-`READY_TO_COMMIT` flow does not produce. **Impact:** none
today. **Defer to:** a future review of whether `ImplementationDiffEvidence` should be generalized,
or whether AUTO-013's own §5a-item-4 handling is the intended permanent shape.

### D-16 — QA and stage reports are unsequenced on the very first round — `OPTIONAL`

The first (`sequence=None`) stage report and `qa.<1>.json` for round 1 sit alongside each other by
convention rather than by a uniform numbering scheme (the stage report's first write has no
sequence; QA's first write is round 1). Purely cosmetic — both are found correctly by
`read_reports` — but worth normalizing if a future stage adds tooling that lists these artifacts by
sequence. **Impact:** none observed. **Defer to:** any future reporting-consistency pass.

### Earlier findings — unchanged

AUTO-012's **D-11, D-12, D-13**, AUTO-011's **D-8, D-9, D-10**, AUTO-010's **D-3 through D-6**, and
AUTO-009's **D1–D6** are all confirmed untouched; none was fixed.

## 20. Proof AUTO-014 and AUTO-015 were not implemented

| Prohibited | Evidence |
|---|---|
| Waiting for CI | no polling loop, no GitHub-checks read call anywhere in `implementer.py` |
| Merge, merge confirmation | `enable_automatic_squash_merge`/`verify_merge_completion` are never imported or called |
| Baseline update, branch cleanup | `checkout_baseline`/`fast_forward_pull`/`delete_local_branch`/`delete_remote_branch` are never imported or called |
| Runtime closeout | `generate_closeout_report` is never imported or called |
| Codex review/correction beyond the one QA gate | Codex is invoked exactly once per repair round, for QA only (`ExecutionMode.REVIEW`); no "correction" concept exists |
| Telegram, daemon, scheduler | no import, no thread, no network client, no `while True` polling loop anywhere in the module |
| Preparation Mode, Reviewer Mode | no such module, class, or command exists |
| `WorkflowState` extended | still 19 members, 37 edges — `orchestrator/engine.py` is byte-identical to `main` |
| `WorkflowService` given a sixth verb | `service.py` is byte-identical to `main`; `APPROVED_OPERATIONS`/`FORBIDDEN_OPERATIONS` in `test_service.py` are unchanged and still pass |
| `ProviderRuntime`, either CLI provider, `ProviderResult`, `AgentRunResult`, `ApprovalService` modified | `providers/**`, `results.py`, `approvals.py` byte-identical to `main` |
| **AUTO-014, AUTO-015, or any successor** | absent; not registered, not authorized, not referenced as implemented anywhere in this stage's code or docs |

## 21. Closure and publication

Approved by the Human Owner after the eighteen-point final scope and integrity verification in
§10/§10a. The implementation/closeout commit bundles the implementation, the new test file, the
one additive Skill, `stage-prompts/AUTO-013.md`, the `MACHINE_GATES.md` amendment, and the
governance-log updates in this report, matching the AUTO-009 through AUTO-012 precedent — followed
by pushing `feature/auto-013-implementer-to-pr`. Publication is explicitly limited to that push:
**no pull request, no merge, no AUTO-014 work, no AUTO-015 work** — each requires its own separate
Human Owner authorization. Exact commit SHA, `HEAD`/`@{upstream}` equality, and post-push
`workflowctl verify` results are reported to the Human Owner directly (see the closing summary of
this session).

## 22. Stop condition

Per the Human Owner's closure directive: commit and push only. No pull request, no merge, no
AUTO-014 work, and no AUTO-015 work.
