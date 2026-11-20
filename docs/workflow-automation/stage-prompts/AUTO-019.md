# AUTO-019 / AWE-AUTO-ST-03 — Resume / Crash Recovery

**Private draft. NOT_STARTED / Planned. Implementation unauthorized.** The objective is to resume a policy-governed run from its last provable durable fact without repeating completed work. If the evidence cannot distinguish two executions that require different actions, do not choose one by inspecting the worktree.

## Authority and gates

Planning baseline: `14ca2459f20a9459eaf91cf55b8df320a82d8614`. Governing artifact: [frozen master plan](../successor-planning/AWE-GOVERNED-AUTONOMOUS-STAGE-EXECUTION-MASTER-PLAN.md), SHA-256 `8ab499c0240cc542e735eb5d1953dcd93994ebd87f1ef7413e9346805d613077`. Its §4 AUTO-019 defines scope and acceptance; §§2.2, 2.4 and 2.6 govern the local stop, operation evidence and decision respectively. `docs/TASK_QUEUE.md` (AUTO-019, OD-GSE-07/12) registers **no blocking OWNER decision or external prerequisite**. The execution predecessor AUTO-018 is COMPLETE / Done, CLOSED and FROZEN at `e964cea54ffe8a67721c964a682c1adf2db92eee` (`docs/DECISION_LOG.md`, 2026-10-02); its completion does not select a successor.

1. Under [registry §3](../STAGE_REGISTRY.md) and master plan §7, submit only this private document for one bounded independent technical review. Judge AUTHORITY, SURFACE, PHASES, PINS, OWNER_STOP, DISCOVERY, MATRIX and FRAGMENT separately against the exact candidate; identify the revision, verdict and supporting passage or defect for each. One round total: a linked correction is limited to that review's in-scope findings in this file; bind any corrected verdict to the corrected candidate. Stop for the OWNER. Technical PASS has no governance effect.
2. Contract acceptance/freeze is a separate OWNER act. Implementation requires explicit written OWNER authorization for AUTO-019 recorded in registry §5 **and** its task. This card does not edit the product checkout, promote a task, record acceptance, freeze, publish or invoke Stage Start.
3. After the OWNER authorizes the stage, create the registered stage branch from synchronized clean `main`. Require the matching OWNER-initiated AWE-native Stage Start for this stage and frozen contract before execution. Follow the [SSP](README.md): read its required context and use exactly the applicable preflight (initial §3 rule 4, later session rule 19). Stop on failed prerequisites; neither contract review nor runner `resume` substitutes for authorization or Stage Start.

The remaining choices here are whether the OWNER accepts this contract and whether to authorize execution, not a new policy ruling. Master plan §6.2 reserves OD-GSE-04/-05/-08/-09/-10/-11 for their owning stages. In particular §2.6 leaves post-remediation verification failure options to OD-GSE-09 before AUTO-020 and amended-run worktree disposition to OD-GSE-10 before AUTO-021. Do not choose those options or dispose of a worktree here.

## Future implementation boundary

Production paths below are relative to `src/ai_workflow_engine/milestone_runner/`:

- New `recovery.py::RecoveryReconciler`: a deterministic selector over verified run pins, ordered operation facts and repository evidence. Return a typed `RecoveryVerdict` (run, operation/attempt, phase, evidence digests, action, reason, expected state version); no provider, filesystem mutation or Git command in the selector.
- Existing `state.py::RunStateStore._reconcile` currently considers in-flight state, `completed_at` and fingerprint. For v2 delegate to the selector. Extend existing `state.py::ResumeAction` with `APPLY_STORED_RESULT`, `REVALIDATE_STORED_RESULT`, `ESCALATE_TO_OWNER`. The store owns persistence, not the renderer or adapter. Use the frozen ST-02 run lock, append-only ordered events, atomic artifact publication (file fsync, replace, parent fsync) and replay-derived projection. Persist typed `RecoveryVerdict` events for new recovery decisions, causally bound to the evidence and version; re-reading a verdict must not append it again. Use the existing event writer, not a parallel journal.
- Existing `models.py`: extend runner-local `RunStatus`, transition guards and run record with `OWNER_DECISION_REQUIRED` and optional typed `PendingDecision`; no shared `WorkflowState` change. Existing `operations.py::operation_id`, `OperationPhase` and AUTO-018 §8 evidence formats remain authoritative inputs, not new protocols.
- Existing `application.py::resume_run` and `_resume_from`: guard frozen runs before step dispatch. Split validation and application from `_invoke_provider` and the ordinary `_implement_milestone`, `_review`, `_correct`, `_verify_closure` entry paths so stored results use the same role parser, policy and transition logic **without** starting an attempt. Expose deterministic local read-only decision rendering from the stored request here. Keep all existing verification and approval gates.
- New `tests/test_milestone_runner_crash_windows.py`: phase-boundary fault hooks at store publication, adapter process creation and application transition; no live providers. Future evidence file: `docs/reports/workflow-automation/AUTO-019-completion-report.md`.

**Amendments to AUTO-016 (v2 policy-governed only).** §13: replace fingerprint-based `REINVOKE_PROVIDER` for ambiguous local dispatch with the rules below; retain entry checks, no-op resume and guarded recovery commands. §11: record verdict/decision evidence in the ST-02 stream, not merely in `state.json`. §19: re-entry to review is not a new discovery attempt; count dispatch identity, not just successful rounds. Extend the runner state/edge and stop rules only by the local freeze below. No relaxation of budgets, correction, closure or approval rules; v1 supervised resume and recovery commands retain their authorized behavior. Multiple cycles/overflow policy belong to AUTO-020; general decision API and worktree disposition to AUTO-021; catalog, remote/Hermes queries, authentication, transport and Git automation to AUTO-022 through AUTO-026 respectively. No legacy orchestrator edits. Git has index effects even before spawn: this provider ladder does not recover a Git operation.

## Evidence before action

Under the store lock, replay the ST-02 stream in sequence. Verify event identity, version continuity, causation, policy binding, artifact references and content digests before consulting the projection. Recover a stale projection from committed facts, never the reverse. Match repository identity, requested `run_id`, `stage_id`, `contract_sha256`, branch and pinned HEAD. Accept a different HEAD only if it is exactly the recorded post-commit HEAD in a verified matching approval receipt. Revalidate the stored `EffectiveStageExecutionPolicy` and canonical `policy_digest` against the run and all bound evidence (AUTO-017 §10.3, DO-019-1); never re-resolve from current defaults. Compare the full recorded candidate path set and per-path content digests, including additions, deletions and changes on already-known paths; separately reject drift outside the cumulative authorized allowlist. An allowed path is not permission to adopt new bytes.

Refuse continuation on mismatch, with the existing applicable drift/identity/gate stop reason or `POLICY_DIGEST_MISMATCH`. Record bounded redacted expected/observed identity, digest or path delta and source checkpoint; no dispatch, transition into work, pin rewrite or repair of the repository. Preserve the existing `HUMAN_INTERVENTION_REQUIRED` safety stop for drift/failed gates. For unresolved intent record both fingerprint observations as evidence of ambiguity, never as spawn evidence; independent pin failures still bar work. Recovery cannot widen scope, raise a budget, close a finding or automatically adopt observed state.

Bind every fact to `sha256(run_id|step_kind|cycle_no|role|slot)` using AUTO-018 §8.1 encoding and slots. A duplicate request with identical bound digest reuses the original operation and its highest phase, not a new attempt. A conflicting request cannot replace it: retain evidence and freeze as ambiguous. For one `operation_id`, identical result digest is a delivery no-op; different result digest preserves the original and conflict evidence and freezes with `DUPLICATE_RESULT_CONFLICT`. Check duplication before parsing, counting or applying. A repeated conflict must not mint a second decision.

Use the highest **consistent** phase, not the newest filename. Verify the contiguous artifact/event chain, ordered attempts, matching envelope/role and expected pre-state. Where ST-02 replay proves a publication is pending, finish only that publication from committed evidence (e.g. recreate a missing applied marker from its transition event). Never interpret a torn chain, orphan intent, corrupt digest or conflicting phase as a lower, retryable phase. If unprovable, refuse/freeze with diagnostic evidence and zero calls; never append into an unverifiable stream. Hold the lock across selection and conditional publication; stale version requires reread. Two resumes at an unchanged checkpoint after reconciliation are a byte-identical no-op, including events, counters, request, projection and rendering; no fresh timestamps on inspection.

## Local provider phase rules (master plan §2.4)

1. **REQUEST_CREATED:** immutable operation `request.json` plus `OPERATION_REQUEST_CREATED` proves the envelope, policy, role and pre-fingerprint. Only with intact pins and no attempt evidence may the runner allocate the first attempt, publish and fsync `dispatch-intent.json` and its event, then enter the process-creation call once.
2. **DISPATCH_INTENT:** verify operation, gap-free attempt number, adapter, argv/envelope digest and pre-fingerprint. Only durable `PRE_SPAWN_FAILED` proving positive OS refusal before creation, with no receipt/result, permits the next attempt of the *same* operation. Retain prior artifacts; 3 attempts total, no fourth; at exhaustion stop. Timeout, unknown outcome, cancellation, nonzero exit and failure to publish a receipt are not this exception. With no outcome, freeze `AMBIGUOUS_RECOVERY` regardless of unchanged **or** changed fingerprint. Do not probe or call again.
3. **DISPATCH_RECEIPT:** `dispatch-receipt.json` with local PID/start time (typed acknowledgment for fake) and `OPERATION_DISPATCH_RECEIVED` proves start, not completion. Without result freeze as ambiguous; no redispatch.
4. **RESULT_RECEIVED:** verify redacted `result.raw`, digest, outcome/transcript references and receipt event. `REVALIDATE_STORED_RESULT` invokes only the deterministic role validator on these bytes and frozen limits; persist typed verdict and validation event. Never redispatch (INV-06).
5. **RESULT_VALIDATED:** `result.validated.json` and validation event bind typed result, diagnostics and VALID/INVALID/EXECUTION_FAILED verdict to the received digest. `APPLY_STORED_RESULT`: for valid evidence append `OPERATION_RESULT_ACCEPTED` once with the original operation's effects (findings/counters); otherwise record `OPERATION_RESULT_REJECTED` once and honor its stop route, no success accounting. Malformed discovery takes the policy stop below.
6. **RESULT_PERSISTED:** acceptance/rejection event already owns the effects. Apply only the pending causative transition from its expected version; never consume another attempt, finding or round.
7. **TRANSITION_APPLIED:** verify `STATE_TRANSITIONED` with `state_version+1` and `applied.json` referencing its ID/version/digest. A return from `PROVIDER_WAIT` is not this transition. Continue from the destination, not the origin: focused verification after implementation, the recorded review disposition after discovery, closure k after successful remediation k and its required verification, the existing gated disposition after closure. Respect a rejection stop. No repeat of the interrupted operation.

## Policy stop (master plan §§2.2, 2.6; INV-05/08)

`ESCALATE_TO_OWNER` freezes a live run in `OWNER_DECISION_REQUIRED`, distinct from the safety stop. Commit exactly one pending request with the freeze under the lock; allocate `D-<StageId>-<NNN>` in `DECISION_REQUESTED`. Persist the immutable decision `request.json` before exposing it. Bind run/project/repository/stage, policy, reason, origin state/version, redacted operation evidence, options with exact reply/effect, recommendation, fixed creation time and canonical request digest. Rehydrate the same `PendingDecision` and render locally from these bytes, never from current time or a newly generated option list.

Route ambiguous local execution to `AMBIGUOUS_RECOVERY`, incompatible result deliveries to `DUPLICATE_RESULT_CONFLICT`, and persisted unparseable/invalid discovery to `DISCOVERY_MALFORMED`. The latter is a dispatched discovery, not a successful round. Per run at most **one distinct discovery operation** may ever reach intent, including across all restarts and pre-spawn retries. No subsequent discovery after malformed receipt. `RETRY_DISCOVERY` must not exist in the vocabulary.

For this stage offer the applicable local response `KEEP_FROZEN`: validate decision ID and request digest, record the response once, leave the same decision/options pending, no transition. Retain the separately guarded existing `abort` command. Do not advertise unimplemented responses as executable. Master plan §2.6's wider `ABORT_STAGE`, `AMEND_STAGE_CONTRACT`, conditional `ADOPT_OBSERVED_STATE` and later `EXTEND_REMEDIATION +1` vocabulary confers no such response authority here. No safe adoption path is specified. While frozen or pending: read-only inspection, no automatic step, Git, approval or edge back to `REVIEWING`; an ordinary safety recovery command cannot clear this policy stop.

## Acceptance: kill, reopen, observe

Each cell is an independent kill/restart test. Digits count *additional local provider calls for the interrupted operation*, measured before dispatch for later work. Retry cells allow at most 2 remaining creation attempts after the first refusal, never beyond 3 total; only one may successfully start a provider. Freeze below means `OWNER_DECISION_REQUIRED / AMBIGUOUS_RECOVERY`.

| Crash after | Implementer | Discovery | Remediator | Closure |
|---|---|---|---|---|
| REQUEST_CREATED | dispatch 1 | dispatch 1 | dispatch 1 | dispatch 1 |
| DISPATCH_INTENT + PRE_SPAWN_FAILED | retry ≤2 | same discovery retry ≤2 | retry ≤2 | retry ≤2 |
| DISPATCH_INTENT without outcome | freeze 0 | freeze 0 | freeze 0 | freeze 0 |
| DISPATCH_RECEIPT | freeze 0 | freeze 0 | freeze 0 | freeze 0 |
| RESULT_RECEIVED | revalidate 0 | revalidate 0 | revalidate 0 | revalidate 0 |
| RESULT_VALIDATED | apply verdict 0 | apply verdict 0 | apply verdict 0 | apply verdict 0 |
| RESULT_PERSISTED | transition only 0 | transition only 0 | transition only 0 | transition only 0 |
| TRANSITION_APPLIED | next step 0 | next step 0 | continue to closure k 0 | next step 0 |

After separate authorization, run `python -m pytest -q tests/test_milestone_runner_crash_windows.py`. First add the E8/E9 tests **without** the implementation; require a red assertion demonstrating the specific repeated call or incorrect accounting, not a setup failure. E8: completed implementer still in `IMPLEMENTING`, validated success before acceptance; require one original acceptance, one edge to `FOCUSED_VERIFYING`, one total call. E9: original `REVIEWING` request, one attempt/intent, received raw bytes, no verdict; parse via `parse_review_result` at the pinned blocker limit, accept the recognizable finding once, successful rounds 0→1, attempts/intents/calls still one each. A round count alone is insufficient. Both historical appendix oracles are normative tests.

Use a counting fake adapter with a ledger surviving process death, keyed by role/operation/attempt. Kill immediately after the named durable boundary; reopen disk state in a fresh session with identical pins. Instrument file and directory fsync and intent event commit; at **entry** to process creation assert they already completed and that reopened intent bytes match the attempt. Record creation attempts separately from provider starts. Exercise ambiguity on either side of actual creation before receipt, with both fingerprint outcomes. Assert IDs, ordered events, digests, counters, state and restart call delta in each cell. For every run count distinct discovery IDs with intent ≤1. Include exhausted refusal retries, invalid verdicts and kill during acceptance/transition publication.

Focused negative/property tests: duplicate equal/conflicting request and result before/after acceptance; malformed discovery with zero further dispatch and no retry option; independently vary every pin, candidate membership/content and outside-allowlist drift (including valid versus unrelated post-commit receipt). Corrupt/truncate evidence and race two resumes: neither may cause duplicate effects. Snapshot all durable bytes across repeated unchanged resumes. Restart before and after `KEEP_FROZEN`; compare ID, digest, options, request bytes, rendered bytes and zero work/Git calls. Exercise existing abort, safety gates and unmodified v1 behavior; replay the frozen ST-02 compatibility corpus without rewriting it.

**Future closure evidence only:** report exact revisions, commands, fixtures, E8/E9 red-before and green-after assertions, spawn ordering trace, per-cell expected/observed verdicts and provider counts, pin/duplicate/freeze/no-op and compatibility results. Require the matrix **100% green** in the completion report for proposed closeout, plus applicable SSP checks and separate OWNER disposition. No live acceptance implied.

## Historical appendix — accepted private E8/E9 fragment

Source: commit `5d4b8bced7d9190a5938d36948129768d4e30240`, blob `181629865c087a385ca8bb1e4d54e72bdab8e945`, path `docs/workflow-automation/stage-prompts/AUTO-019.md`, SHA-256 `f6bcb71f13826ae5cb0915f1f539f4e20b45bfd35e1216c7c87d135bf844b2b9`. Only the fragment below is the accepted private source; the surrounding full contract is a new draft.

~~~~markdown
# Draft — AUTO-019 resume / crash recovery: E8 and E9

AUTO-019 is **NOT_STARTED / Planned**. Implementation is unauthorized. AUTO-018, its execution predecessor, is complete and frozen. This documentation-only fragment is for Owner review as input to the future contract and its bounded contract review. It neither freezes the contract nor authorizes Stage Start.

## Regression vectors

The [master plan](../successor-planning/AWE-GOVERNED-AUTONOMOUS-STAGE-EXECUTION-MASTER-PLAN.md) identifies E8 and E9 by inspection. The oracles below follow its §2.4 operation phase ladder and AUTO-019 crash-window matrix for v2 policy-governed runs. They are proposed tests, not reproduction results.

```json
[
  {"gap":"E8","checkpoint":"RESULT_VALIDATED","action":"apply","extra_provider_calls":0},
  {"gap":"E9","checkpoint":"RESULT_RECEIVED","action":"revalidate","extra_provider_calls":0}
]
```

In `tests/test_milestone_runner_crash_windows.py`, each row will drive one run with a counting fake provider. The fixture will keep the run and operation IDs fixed, leave repository and policy pins unchanged, and reopen the durable store in a fresh session. `checkpoint` will be the highest durable `operations.py::OperationPhase`. The harness will count provider calls across both sessions and measure the restart delta through the recovered transition, before dispatch of any later step. Code references below are relative to `src/ai_workflow_engine/milestone_runner/`.

### E8 — apply a validated result

The fake implementer will complete one milestone invocation. The fixture will retain its completed provider record in `IMPLEMENTING` and its `result.validated.json` with a typed successful result and validation verdict. The test will interrupt after that artifact is durable but before `OPERATION_RESULT_ACCEPTED` or the transition to `FOCUSED_VERIFYING`.

Restart will exercise `state.py::_reconcile` and the `IMPLEMENTING` branch of `application.py::_resume_from`. A set `completed_at` currently takes reconciliation to `ResumeAction.CONTINUE`; the test will distinguish applying the stored result from re-entering `_implement_milestone` and calling `_invoke_provider` again. It will assert one acceptance for the original operation, one transition to `FOCUSED_VERIFYING`, and a fake call count unchanged at one.

### E9 — revalidate a received discovery result

The fake reviewer will return a valid discovery response containing a recognizable in-budget finding. The fixture will retain the original `REVIEWING` operation, one dispatch intent, one review attempt, and the redacted `result.raw` with its digest. The test will interrupt after receipt is durable but before validation or acceptance: no typed verdict, accepted finding, or successful review round will yet exist.

Restart will exercise `application.py::_resume_from` at the `_review` boundary. Instead of recording another attempt and calling `_invoke_provider`, recovery will verify the digest and pass the stored response to `parse_review_result` with the pinned blocker limit. The test will assert that the stored response yields the expected finding, that it is accepted once, and that `successful_review_rounds` moves from zero to one. The counting fake will still report one discovery call in total; the dispatch-intent count and `review_attempts` will each remain one. A successful-round count alone would not detect a duplicate call before acceptance.
~~~~
