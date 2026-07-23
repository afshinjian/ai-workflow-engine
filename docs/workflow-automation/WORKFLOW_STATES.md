# AgentOS Workflow Automation — Workflow States

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Workflow States |
| **Purpose** | Normative runtime state machine for one workflow execution against one target-repository stage: exact allowed/forbidden transitions, retry behavior, interruption recovery, and idempotency. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Documentation & Governance session (AUTO-001) · Human Owner (approval) |
| **Dependencies** | `ARCHITECTURE.md` §3; `HUMAN_AUTHORIZATION_MODEL.md`; `MACHINE_GATES.md` |
| **Related Documents** | `AGENT_CONTRACTS.md`, `FAILURE_RECOVERY.md`, `AUDIT_MODEL.md` |

## Table of Contents
1. Scope and Naming Note · 2. States · 3. Allowed Transitions · 4. Forbidden Transitions ·
5. Retry Behavior · 6. Interruption Recovery · 7. Idempotency · 8. Terminal States ·
9. Decision References · 10. Open Questions · 11. Future Revisions

## 1. Scope and Naming Note

This document defines the **runtime workflow state machine** — the lifecycle of one execution
of the workflow engine against one authorized target-repository stage. It is a distinct state
machine from the **AUTO-00x stage lifecycle** used to track development of this engine itself
(`STAGE_REGISTRY.md`), which reuses this repository's `docs/agentos-dashboard/STAGE_REGISTRY.md`
state model (`NOT_STARTED`/`PROPOSED`/`AUTHORIZED`/`IN_PROGRESS`/... /`COMPLETE`). The word
`AUTHORIZED` appears in both machines with an analogous but not identical meaning; every
reference to workflow state in this document means the runtime machine defined below unless
explicitly qualified as "stage lifecycle."

## 2. States

| State | Meaning |
|---|---|
| `CREATED` | Workflow record exists; not yet authorized. |
| `AUTHORIZED` | Human gate passed; authorization bound (`HUMAN_AUTHORIZATION_MODEL.md`). |
| `PRECONDITIONS_CHECKED` | `PMOAgent` verified repository/stage preconditions. |
| `BRANCH_CREATED` | Stage branch created from the verified baseline. |
| `IMPLEMENTING` | `ImplementationAgent` / `ClaudeCLIProvider` implementing the stage contract. |
| `VALIDATING` | Deterministic validation Skills running (tests, lint, format, scope, security, secret detection). |
| `QA_RUNNING` | `QAAgent` / `CodexCLIProvider` running independent QA. |
| `REPAIRING` | `ImplementationAgent` / `ClaudeCLIProvider` attempting an automatic repair. |
| `READY_TO_COMMIT` | All deterministic validation and QA passed; nothing yet committed. |
| `COMMITTED` | `GitAgent` created the stage commit. |
| `PUSHED` | `GitAgent` pushed the stage branch. |
| `PR_OPEN` | `GitAgent` opened the pull request. |
| `AUTO_MERGE_ENABLED` | `MergeAgent` verified expected head SHA and enabled automatic squash merge. |
| `WAITING_FOR_CHECKS` | Waiting for all required GitHub checks to complete. |
| `MERGED` | GitHub confirmed the pull request merged. |
| `CLOSING` | `CloseoutAgent` performing cleanup, baseline update, final verification. |
| `DONE` | Workflow complete; closeout report and audit finalized. |
| `FAILED` | Workflow terminated without completing; see `FAILURE_RECOVERY.md`. |
| `CANCELLED` | Workflow explicitly aborted by an operator before completion. |

## 3. Allowed Transitions

```
CREATED            → AUTHORIZED             (human action — the only human gate)
AUTHORIZED         → PRECONDITIONS_CHECKED  (machine gate: PMOAgent preconditions pass)
PRECONDITIONS_CHECKED → BRANCH_CREATED       (machine gate: stage branch created)
BRANCH_CREATED     → IMPLEMENTING           (machine: ImplementationAgent starts)
IMPLEMENTING       → VALIDATING             (machine: implementation attempt complete)
VALIDATING         → QA_RUNNING             (machine gate: deterministic validation passes)
VALIDATING         → REPAIRING              (machine gate: deterministic validation fails, attempts remain)
VALIDATING         → FAILED                 (machine gate: deterministic validation fails, no attempts remain)
QA_RUNNING         → READY_TO_COMMIT        (machine gate: independent QA passes)
QA_RUNNING         → REPAIRING              (machine gate: independent QA fails, attempts remain)
QA_RUNNING         → FAILED                 (machine gate: independent QA fails, no attempts remain)
REPAIRING          → VALIDATING             (machine: repair attempt complete, re-validate)
READY_TO_COMMIT    → COMMITTED              (machine: GitAgent commits)
COMMITTED          → PUSHED                 (machine: GitAgent pushes)
PUSHED             → PR_OPEN                (machine: GitAgent opens PR)
PR_OPEN            → AUTO_MERGE_ENABLED     (machine gate: expected head SHA verified)
AUTO_MERGE_ENABLED → WAITING_FOR_CHECKS     (machine: automatic merge enabled, checks pending)
WAITING_FOR_CHECKS → MERGED                 (machine gate: all required checks pass and GitHub confirms merge)
WAITING_FOR_CHECKS → FAILED                 (machine gate: a required check fails)
MERGED             → CLOSING                (machine: merge independently verified)
CLOSING            → DONE                   (machine gate: final verification passes)
CLOSING            → FAILED                 (machine gate: final verification fails — see §5, cleanup already-safe)
{CREATED, AUTHORIZED, PRECONDITIONS_CHECKED, BRANCH_CREATED} → CANCELLED (operator abort, before any destructive/shared-state action)
```

`CANCELLED` from `IMPLEMENTING` onward is not a modeled transition in the MVP: once a stage
branch carries agent-authored work, an operator abort is handled as a `FAILED` workflow
(preserving evidence) rather than a silent `CANCELLED`, per the failure policy in
`FAILURE_RECOVERY.md`. Revisiting this is `OPEN_QUESTIONS.md` OD-6.

Cancellation is **not** a human gate: it only withdraws permission to continue, it never grants
permission to proceed further, so it does not create a second point where a human authorizes
forward progress (`HUMAN_AUTHORIZATION_MODEL.md` §1).

## 4. Forbidden Transitions

- Any transition that skips an intermediate state (e.g. `BRANCH_CREATED → COMMITTED` directly).
- Any transition back to `CREATED` or `AUTHORIZED` from any later state — authorization is
  single-use per workflow; a new workflow requires a new authorization
  (`HUMAN_AUTHORIZATION_MODEL.md`).
- Any transition out of a terminal state (`DONE`, `FAILED`, `CANCELLED` — §8).
- `AUTO_MERGE_ENABLED` reached without `READY_TO_COMMIT` having been reached first in this
  workflow (i.e., without both deterministic validation and QA having passed).
- `MERGED` reached without `WAITING_FOR_CHECKS` having confirmed all required checks passed.
- `CLOSING` started before `MERGED` is independently confirmed by GitHub (never inferred from
  local Git state alone).
- Any transition triggered by a Model Provider report alone without the corresponding machine
  gate re-verifying it against real repository/GitHub state (`MACHINE_GATES.md`).

## 5. Retry Behavior

- The `VALIDATING`/`QA_RUNNING` ⇄ `REPAIRING` cycle is bounded to a maximum of 3 repair attempts
  (`FAILURE_RECOVERY.md`). Exceeding the limit transitions to `FAILED`, never silently retries
  further.
- Transient infrastructure failures inside a single Skill invocation (e.g. a network error
  calling the GitHub API in `WAITING_FOR_CHECKS`) may be retried a small, fixed number of times
  by that Skill with backoff, entirely separate from the repair-attempt counter. This is an
  infrastructure retry, not a repair attempt, and it never changes workflow state by itself
  (`OPEN_QUESTIONS.md` OD-4 tracks confirming this separation before AUTO-002 implementation).
- No transition is retried an unbounded number of times; every retry path has a fixed ceiling
  recorded in the corresponding Skill contract (`SKILL_CONTRACTS.md`).

## 6. Interruption Recovery

State is persisted after every transition (`AUDIT_MODEL.md`). On process restart:

1. The Orchestrator loads the persisted state for the target repository's active workflow.
2. It re-verifies the preconditions relevant to the *current* state (repository identity,
   branch existence, working-tree cleanliness where expected, authorization binding fields
   still matching live repository state) before resuming any further transition.
3. If any bound authorization value has drifted (e.g. the baseline commit SHA no longer
   matches), the workflow moves to `FAILED` and requires new authorization to restart — it is
   never silently continued (`HUMAN_AUTHORIZATION_MODEL.md` §4).
4. If preconditions still hold, the Orchestrator resumes from the current state's outgoing
   transition as if no interruption occurred; no state is ever skipped or replayed twice in a
   way that would repeat a non-idempotent side effect (§7).
5. Resume is only ever attempted for the single active workflow permitted by the repository
   lock (MVP); the lock itself is what makes "safe resume" well-defined instead of racing a
   second invocation.

## 7. Idempotency Expectations

Every Skill invoked by a state transition is idempotent with respect to the intended end
state, not just safe-to-retry:

- `create_stage_branch` — if the branch already exists at the expected base, this is a pass,
  not a re-creation.
- `create_commit` — if the working tree already matches the expected committed diff, this is a
  pass, not a duplicate commit.
- `push_stage_branch` — a push whose remote ref already matches the local ref is a pass.
- `create_pull_request` — if an open PR already exists for the stage branch, it is reused, not
  duplicated.
- `enable_automatic_squash_merge` — if automatic merge is already enabled with the expected
  configuration, this is a pass.
- `delete_local_branch` / `delete_remote_branch` — deleting an already-absent branch is a pass,
  never an error, provided the precondition that it is safe to delete was already verified.

Idempotency is what makes §6 (resume) and §5 (bounded retry) safe: re-entering a transition
after an interruption never produces a duplicate side effect.

## 8. Terminal States

`DONE`, `FAILED`, `CANCELLED` have no outgoing transitions. Reaching any of them releases the
repository lock. Restarting work on the same stage after `FAILED` or `CANCELLED` always begins
a brand-new workflow at `CREATED`, requiring fresh human authorization
(`HUMAN_AUTHORIZATION_MODEL.md` §4, `FAILURE_RECOVERY.md` §5).

## 9. Decision References
DD-04, DD-05.

## 10. Open Questions
OD-4, OD-6.

## 11. Future Revisions
Any new state or transition is a MAJOR change to this document and requires Human Owner
review, since it changes the machine-gate surface that stands in for human approval after
authorization.
