# AgentOS Workflow Automation — Machine Gates

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Machine Gates |
| **Purpose** | Every automatic checkpoint that stands in for human approval after the single human gate, with pass/fail criteria and on-fail behavior. |
| **Status** | Draft |
| **Version** | 1.3 |
| **Owner** | Documentation & Governance session (AUTO-001) · Human Owner (approval) |
| **Dependencies** | `WORKFLOW_STATES.md`, `HUMAN_AUTHORIZATION_MODEL.md` |
| **Related Documents** | `SKILL_CONTRACTS.md`, `SECURITY_MODEL.md`, `FAILURE_RECOVERY.md` |

## Table of Contents
1. Principle · 2. Precondition Gate · 3. Deterministic Validation Gate · 4. Independent QA Gate ·
5. Merge Safety Gate · 6. Checks-Wait Gate · 7. Closeout Gate · 8. Gate Summary Table ·
9. Decision References · 10. Open Questions · 11. Future Revisions

## 1. Principle

After `AUTHORIZED`, no further step requires or accepts human input. Every subsequent
transition is gated by a deterministic, machine-evaluated condition. A gate either passes (the
Orchestrator advances the workflow state) or fails (the Orchestrator moves to `REPAIRING` if
attempts remain, otherwise to `FAILED`) — there is no third outcome and no silent skip.

The six gates below (§2–§7) are the **forward-progress** checkpoints and are not the exhaustive
source of every legal `→ FAILED` transition in `WORKFLOW_STATES.md` §3: a second, general
failure path — interruption/resume detecting authorization-bound-value drift
(`WORKFLOW_STATES.md` §6 item 3) — independently reaches `FAILED` from every other non-terminal,
non-`CREATED` state, including several this document names no gate for (`BRANCH_CREATED`,
`IMPLEMENTING`, `REPAIRING`, `READY_TO_COMMIT`, `COMMITTED`, `PUSHED`, `AUTO_MERGE_ENABLED`,
`MERGED`). A **third** failure path — bounded retry then reconciliation for a side-effecting
operation's own first-time execution failure (`WORKFLOW_STATES.md` §5a; `IMPLEMENTING`,
`READY_TO_COMMIT`, `COMMITTED`, `PUSHED` only) — is likewise not a gate in this document's sense:
it never applies to a gate's own pass/fail check, only to the Skill/provider invocation that
precedes reaching a gate state. Do not read this document's gate list as defining the complete
`→ FAILED` surface — `WORKFLOW_STATES.md` §3 is that complete, closed list.

## 2. Precondition Gate (`AUTHORIZED → PRECONDITIONS_CHECKED → BRANCH_CREATED`)

Pass requires all of: repository identity verified; working tree state as expected; current
branch and baseline ancestry verified; stage contract located, parsed, and its hash matching
the authorization binding; stage ordering valid (predecessor stage complete, no future-stage
work detected); stage branch successfully created from the verified baseline commit. Any
failure moves the workflow to `FAILED` (a precondition failure is not repairable by
`ImplementationAgent` — it is a target-repository or authorization-state problem).

### 2a. Resume form of the precondition gate (Human Owner clarification, 2026-07-27)

On resume, "working tree state as expected" means the state- and evidence-specific matrix in
`WORKFLOW_STATES.md` §6a. The Orchestrator obtains repository, Git, contract, and runtime
observations independently; caller-copied authorization strings are never live evidence.
Cleanliness is mandatory at the states §6a names as clean. Intentional implementation/repair
changes are accepted only within configured allowed paths, never forbidden paths, and only when
persisted attempt/audit evidence makes those changes expected. A possible branch creation,
provider invocation, commit, push, PR, merge, or closeout effect is reconciled against its
persisted operation evidence before repetition or transition; appearance alone never advances
the workflow.

## 3. Deterministic Validation Gate (`VALIDATING`)

Pass requires all of: `run_tests`, `run_lint`, `run_formatting_checks`, `run_scope_validation`,
`run_security_checks`, `run_secret_detection` all pass, and `validate_completion_report`
confirms the implementation report is well-formed. Any failure → `REPAIRING` (if repair
attempts remain) or `FAILED`.

## 4. Independent QA Gate (`QA_RUNNING`)

Pass requires `CodexCLIProvider`'s QA report to have an explicit pass verdict, and
`validate_qa_report` to confirm the report is well-formed and internally consistent with the
deterministic validation results it was given. QA is never skipped, and its verdict is never
inferred from the implementation report — it is independently derived
(`MODEL_PROVIDER_CONTRACTS.md` §3). Any failure → `REPAIRING` (if attempts remain) or `FAILED`.

## 5. Merge Safety Gate (`PR_OPEN → AUTO_MERGE_ENABLED`)

Automatic merge may be enabled **only after all of the following independently hold**:

- Deterministic validation passed (§3).
- Independent Codex QA passed (§4).
- The pull request's current head SHA equals the SHA recorded when the PR was opened
  (`verify_head_sha`) — if it differs, the workflow moves to `FAILED`; it never merges a diff it
  did not validate.
- `enable_automatic_squash_merge` never calls `gh pr merge --admin` and never uses any
  admin-bypass path, under any condition.

## 6. Checks-Wait Gate (`WAITING_FOR_CHECKS → MERGED`)

Pass requires `read_required_checks` to confirm every check configured as required for the
target repository has completed successfully, **and** `verify_merge_completion` to confirm
GitHub itself reports the pull request as merged. A required check failing at any point moves
the workflow to `FAILED`, never to a retried merge. Closeout never begins on local Git evidence
alone — only on this independently GitHub-confirmed merge.

## 7. Closeout Gate (`CLOSING → DONE`)

Pass requires `verify_final_repository_state` to confirm: local and remote stage branches
removed, local repository checked out to the baseline branch, baseline fast-forwarded to the
merged commit (never force-updated), and the working tree clean. Any failure moves the workflow
to `FAILED` — but only after confirming which cleanup steps, if any, already completed safely
before the failure (`FAILURE_RECOVERY.md` §4); a closeout failure never triggers a retry of a
destructive step without re-verifying its precondition.

## 8. Gate Summary Table

| Gate | States | On pass | On fail |
|---|---|---|---|
| Precondition | `AUTHORIZED`→`BRANCH_CREATED` | advance | `FAILED` |
| Deterministic validation | `VALIDATING` | `QA_RUNNING` | `REPAIRING` or `FAILED` |
| Independent QA | `QA_RUNNING` | `READY_TO_COMMIT` | `REPAIRING` or `FAILED` |
| Merge safety | `PR_OPEN` | `AUTO_MERGE_ENABLED` | `FAILED` |
| Checks-wait | `WAITING_FOR_CHECKS` | `MERGED` | `FAILED` |
| Closeout | `CLOSING` | `DONE` | `FAILED` |

## 9. Decision References
DD-04, DD-05.

## 10. Open Questions
OD-1 (required-checks read mechanism).

## 11. Future Revisions
Adding a new gate condition (e.g. a new required validation) is additive; removing or weakening
an existing gate condition is a MAJOR change requiring explicit Human Owner review, since gates
are what stand in for human approval after authorization.
