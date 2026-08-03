# AUTO-014 — CI, Merge, Repository Finalization, and Runtime Closeout

| Field | Value |
|---|---|
| **Stage** | AUTO-014 |
| **Title** | CI, Merge, Repository Finalization, and Runtime Closeout |
| **Role** | Engine implementation session |
| **Branch** | `feature/auto-014-merge-closeout` |
| **Predecessor** | AUTO-013 (`COMPLETE`, merged, published) |
| **Report** | `docs/reports/workflow-automation/AUTO-014-completion-report.md` |

## 1. Mission

Implement the second half of the foreground runtime workflow. AUTO-014 resumes an existing
workflow whose persisted runtime state is `PR_OPEN` and continues the same workflow ID and
authorization until `DONE`:

```text
PR_OPEN -> read/verify PR state -> enable merge per target-repository policy
        -> AUTO_MERGE_ENABLED -> bounded required-check polling -> WAITING_FOR_CHECKS
        -> verify required checks passed -> verify merge eligibility -> merge
        -> verify merge completion -> MERGED -> update local baseline
        -> apply configured branch-retention policy -> runtime closeout
        -> CLOSING -> DONE
```

## 2. Architectural constraints

The architecture and stage boundaries are finalized. This stage does not redesign the workflow,
does not split AUTO-014, does not move AUTO-014 responsibilities back into AUTO-013, and does not
begin AUTO-015.

## 3. Newly discovered defect policy

A defect not directly blocking `PR_OPEN -> DONE` is recorded, classified, added to Deferred
Findings, and left unimplemented — no GOV stage is created for it. A defect may be fixed only when
it directly prevents safe continuation, no scope-preserving workaround exists, the fix is minimal,
and it is documented as an AUTO-014 blocker.

## 4. Strict scope

Resume from persisted `PR_OPEN`; pull-request reconciliation; merge-policy evaluation;
required-check observation; bounded CI polling; merge eligibility; merge execution; merge
confirmation; baseline checkout and fast-forward update; configured branch retention or deletion;
runtime closeout; transition to `DONE`; restart and reconciliation for AUTO-014-owned states.

Excludes: Claude implementation, initial deterministic validation, Claude repair, initial
approval, commit, push, PR creation, Codex review/correction, Preparation Mode, Reviewer Mode,
daemon, Telegram, scheduler, multi-task orchestration, AUTO-015 or successor behaviour.

## 5. Required architecture

```text
WorkflowService -> AUTO-014 continuation operation -> MergeCloseoutModeDriver
        -> WorkflowSession.resume() -> { MergeAgent, Git/GitHub skills, CloseoutAgent, StateStore }
```

The driver owns sequencing and transition selection only. It must not write transition JSONL
directly, acquire `RepositoryLock` directly, execute raw Git/GitHub commands, duplicate skill or
merge-policy or closeout logic, or invoke providers.

## 6. WorkflowService

Add the smallest public continuation operation required to resume a persisted implementation
workflow from `PR_OPEN` (`continue_implementation_to_done(workflow_id: str)` or an evidence-based
equivalent). Delegates to the driver; contains no lifecycle business logic. Does not redesign
existing AUTO-013 operations.

## 7. Start condition

AUTO-014 may start only when the workflow exists; state is `PR_OPEN`, `AUTO_MERGE_ENABLED`,
`WAITING_FOR_CHECKS`, `MERGED`, or `CLOSING`; the same authorization remains valid; repository
identity matches; branch and PR evidence match the persisted expected head SHA; no contradictory
side effect is observed. Starting from an AUTO-013-owned earlier state is rejected. No new runtime
authorization or workflow ID is created.

## 8. Pull-request reconciliation

Before any action at `PR_OPEN`: read the persisted PR identity, query the actual PR, verify
repository/base branch/head branch/expected head SHA/PR state/mergeability, persist the
observation, and refuse continuation on contradictory evidence. AUTO-014 never creates a PR.

## 9. QA and merge eligibility

Use the persisted AUTO-013 evidence (`independent_qa_required`, `qa_passed`,
`deterministic_validation_passed`). When `independent_qa_required=true`, a real QA result must
exist and pass. When `false`, QA evidence must be explicitly `not_applicable`. Missing QA evidence
never becomes `qa_passed=true`. Deterministic validation must always have passed. Merge eligibility
fails closed on incomplete or contradictory evidence. Uses the `MergeAgent.enable_auto_merge`
contract.

## 10. Target-repository merge policy

Uses only target-repository configuration; does not encode this engine repository's own
development policy. If the runtime supports only squash merge, that restriction is preserved.

## 11. Required checks and bounded polling

Bounded attempts per foreground invocation, configurable interval and maximum observations, no
unbounded loop, no background shell polling, persists each observation, returns a resumable
result when checks remain pending after budget, never classifies pending checks as failure, fails
if a required check completes unsuccessfully, re-observes on resume.

## 12. Merge and reconciliation

Before merge: verify expected PR head SHA, required checks, deterministic gate evidence, QA
requirement evidence, PR mergeability, repository identity. Merge only through `MergeAgent` and
the GitHub skill — never admin bypass, never disabled required checks, never fabricated evidence.
After any ambiguous result: re-read the PR, inspect merge status, read the merge commit SHA,
verify expected head ancestry, persist `MergeConfirmation`, never blindly retry the merge.

## 13. Baseline update and branch policy

After merge confirmation: verify target repository identity, checkout the configured baseline,
fetch, update fast-forward only, verify local baseline equals the expected remote merge result,
refuse divergence, never force-reset. `delete_branch_after_merge: bool` (safe default `false`):
when `false`, retain local and remote stage branches and record retention; when `true`, require a
valid `MergeConfirmation`, delete remote then local branch through existing skills, re-observe
both refs, fail closed on identity/evidence mismatch.

## 14. Runtime closeout

Uses the existing `CloseoutAgent`, never the meta `scripts/workflow-approve.sh` or its deferred
Python equivalent. Persists workflow ID, task ID, final runtime state, PR identity, merge
confirmation, merge SHA, final baseline SHA, branch-retention result, validation evidence, QA
requirement and result, approval evidence, provider/agent-result references, failure/warning
findings, and final repository evidence.

## 15. State-machine ownership

AUTO-014 owns only `PR_OPEN`, `AUTO_MERGE_ENABLED`, `WAITING_FOR_CHECKS`, `MERGED`, `CLOSING`,
`DONE`, using only existing legal transitions. No new workflow state is added unless a direct
blocker is proven. Only the AUTO-014 driver selects these runtime transitions.

## 16. Resume and reconciliation

Re-observe before any possible repeated side effect at every AUTO-014-owned state. Never blindly
repeat enabling merge, merging, baseline update, branch deletion, or closeout mutation.

## 17. Failure model

Minimum typed AUTO-014 failures: `invalid_start_state`, `pr_not_found`, `pr_identity_mismatch`,
`pr_head_mismatch`, `required_checks_failed`, `required_checks_unavailable`, `merge_not_eligible`,
`merge_ambiguous`, `merge_failed`, `merge_confirmation_mismatch`, `baseline_diverged`,
`baseline_update_failed`, `branch_cleanup_failed`, `closeout_failed`, `repository_drift`,
`state_corruption`. Pending checks are never a failure.

## 18. CLI

`workflowctl auto continue` (or an evidence-based equivalent), delegating only to
`WorkflowService`, with no business logic and none of `implement`/`review`/`correct`/`prepare`/
`cancel`/`daemon`/`telegram` unless already delivered.

## 19. Security invariants

No provider is invoked by AUTO-014; no implementation agent is invoked; only the AUTO-014 driver
transitions AUTO-014 states; required checks cannot be bypassed; admin merge is unreachable;
missing QA evidence cannot become a pass; no merge against an unexpected head SHA; ambiguous merge
is re-observed, never blindly retried; baseline update is fast-forward only; branch deletion
requires merge confirmation; runtime closeout cannot run before merge confirmation; CLI contains
no business logic; credentials remain environment-selected and redacted.

## 20. Stop condition

After complete implementation and validation: no commit, no push, no PR, no merge, no AUTO-015.
Stop at the Human Owner approval gate with the complete report.
