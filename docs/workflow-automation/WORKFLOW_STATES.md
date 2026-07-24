# AgentOS Workflow Automation — Workflow States

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Workflow States |
| **Purpose** | Normative runtime state machine for one workflow execution against one target-repository stage: exact allowed/forbidden transitions, retry behavior, interruption recovery, and idempotency. |
| **Status** | Draft |
| **Version** | 4.1 |
| **Owner** | Documentation & Governance session (AUTO-001) · Human Owner (approval) |
| **Dependencies** | `ARCHITECTURE.md` §3; `HUMAN_AUTHORIZATION_MODEL.md`; `MACHINE_GATES.md` |
| **Related Documents** | `AGENT_CONTRACTS.md`, `FAILURE_RECOVERY.md`, `AUDIT_MODEL.md` |

## Table of Contents
1. Scope and Naming Note · 2. States · 3. Allowed Transitions · 4. Forbidden Transitions ·
5. Retry Behavior · 5a. Initial-Execution Failure and Reconciliation · 6. Interruption Recovery ·
7. Idempotency · 8. Terminal States · 9. Decision References · 10. Open Questions ·
11. Future Revisions

## 1. Scope and Naming Note

This document defines the **runtime workflow state machine** — the lifecycle of one execution
of the workflow engine against one authorized target-repository stage. It is a distinct state
machine from the **AUTO-00x stage lifecycle** used to track development of this engine itself
(`STAGE_REGISTRY.md`), which reuses this repository's `docs/agentos-dashboard/STAGE_REGISTRY.md`
state model (`NOT_STARTED`/`PROPOSED`/`AUTHORIZED`/`IN_PROGRESS`/... /`COMPLETE`). The word
`AUTHORIZED` appears in both machines with an analogous but not identical meaning; every
reference to workflow state in this document means the runtime machine defined below unless
explicitly qualified as "stage lifecycle."

Nothing in this document — nor in `HUMAN_AUTHORIZATION_MODEL.md`, which depends on it — is
authority for an AUTO-00x stage's own authorization validity, precondition semantics, or state
transitions. That lifecycle is governed exclusively by `STAGE_REGISTRY.md` and the Standard
Stage Protocol (`stage-prompts/README.md`).

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

Every transition below belongs to one of two phases: **initial start** — the unbroken sequence
`CREATED → AUTHORIZED → PRECONDITIONS_CHECKED → BRANCH_CREATED → IMPLEMENTING → ...` a workflow
follows the first time, with no interruption — or **resume** — re-entering the same in-flight
workflow after a process restart, governed entirely by §6. The `→ FAILED` rows attributed to
"interruption/resume detects authorization-bound-value drift" belong to the resume phase only;
every other row (gate-driven or forward-progress `machine`/`machine gate` rows) belongs to
initial start, though the identical check also re-runs if resume re-enters that same state (§6
item 2). No state is exclusive to one phase except `CREATED` (initial-start only — nothing is yet
persisted to resume into) and the terminal states (neither phase — no outgoing transition at
all, §8).

```
CREATED            → AUTHORIZED             (human action — the only human gate)
AUTHORIZED         → PRECONDITIONS_CHECKED  (machine gate: PMOAgent preconditions pass)
AUTHORIZED         → FAILED                 (machine gate: precondition check fails — MACHINE_GATES.md §2)
PRECONDITIONS_CHECKED → BRANCH_CREATED       (machine gate: stage branch created)
PRECONDITIONS_CHECKED → FAILED              (machine gate: stage-branch creation fails — MACHINE_GATES.md §2)
BRANCH_CREATED     → IMPLEMENTING           (machine: ImplementationAgent starts)
BRANCH_CREATED     → FAILED                 (machine: interruption/resume detects authorization-bound-value drift — §6 item 3)
IMPLEMENTING       → VALIDATING             (machine: implementation attempt complete, or §5a item 3 reconciliation success)
IMPLEMENTING       → FAILED                 (machine: interruption/resume detects authorization-bound-value drift — §6 item 3 — or §5a item 5 initial-execution failure)
VALIDATING         → QA_RUNNING             (machine gate: deterministic validation passes)
VALIDATING         → REPAIRING              (machine gate: deterministic validation fails, attempts remain)
VALIDATING         → FAILED                 (machine gate: deterministic validation fails, no attempts remain)
QA_RUNNING         → READY_TO_COMMIT        (machine gate: independent QA passes)
QA_RUNNING         → REPAIRING              (machine gate: independent QA fails, attempts remain)
QA_RUNNING         → FAILED                 (machine gate: independent QA fails, no attempts remain)
REPAIRING          → VALIDATING             (machine: repair attempt complete, re-validate)
REPAIRING          → FAILED                 (machine: interruption/resume authorization-bound-value drift — §6 item 3 — or the repair attempt itself is unrecoverable, e.g. the provider invocation crashes or times out with no usable output to re-validate — FAILURE_RECOVERY.md §1)
READY_TO_COMMIT    → COMMITTED              (machine: GitAgent commits, or §5a item 3 reconciliation success)
READY_TO_COMMIT    → FAILED                 (machine: interruption/resume detects authorization-bound-value drift — §6 item 3 — or §5a item 5 initial-execution failure)
COMMITTED          → PUSHED                 (machine: GitAgent pushes, or §5a item 3 reconciliation success)
COMMITTED          → FAILED                 (machine: interruption/resume detects authorization-bound-value drift — §6 item 3 — or §5a item 5 initial-execution failure)
PUSHED             → PR_OPEN                (machine: GitAgent opens PR, or §5a item 3 reconciliation success)
PUSHED             → FAILED                 (machine: interruption/resume detects authorization-bound-value drift — §6 item 3 — or §5a item 5 initial-execution failure)
PR_OPEN            → AUTO_MERGE_ENABLED     (machine gate: expected head SHA verified)
PR_OPEN            → FAILED                 (machine gate: merge safety gate fails — MACHINE_GATES.md §5/§8)
AUTO_MERGE_ENABLED → WAITING_FOR_CHECKS     (machine: automatic merge enabled, checks pending)
AUTO_MERGE_ENABLED → FAILED                 (machine: interruption/resume detects authorization-bound-value drift — §6 item 3)
WAITING_FOR_CHECKS → MERGED                 (machine gate: all required checks pass and GitHub confirms merge)
WAITING_FOR_CHECKS → FAILED                 (machine gate: a required check fails)
MERGED             → CLOSING                (machine: merge independently verified)
MERGED             → FAILED                 (machine: interruption/resume detects authorization-bound-value drift — §6 item 3)
CLOSING            → DONE                   (machine gate: final verification passes)
CLOSING            → FAILED                 (machine gate: final verification fails — see §5, cleanup already-safe)
{CREATED, AUTHORIZED, PRECONDITIONS_CHECKED, BRANCH_CREATED} → CANCELLED (operator abort, before any destructive/shared-state action)
```

Three distinct reasons now populate this table's `→ FAILED` rows: (a) one of
`MACHINE_GATES.md`'s six named machine gates fails during forward progress — the Precondition
gate spans the two transition-source states `AUTHORIZED` and `PRECONDITIONS_CHECKED`, and the
other five gate states are `VALIDATING`, `QA_RUNNING`, `PR_OPEN`, `WAITING_FOR_CHECKS`, and
`CLOSING`; (b) **interruption/resume detects authorization-bound-value drift** (§6 item 3;
required to be tested "at each state," `TEST_STRATEGY.md` §4a) — reachable from every other
non-terminal, non-`CREATED` state (`BRANCH_CREATED`, `IMPLEMENTING`, `REPAIRING`,
`READY_TO_COMMIT`, `COMMITTED`, `PUSHED`, `AUTO_MERGE_ENABLED`, `MERGED`); or (c) **an
initial-execution side-effecting operation exhausts its retry limit or reaches an unrecoverable/
indeterminate reconciliation outcome** (§5a) — `IMPLEMENTING`, `READY_TO_COMMIT`, `COMMITTED`,
and `PUSHED` only. `REPAIRING` uniquely carries reason (b) and a `REPAIRING`-specific variant of
reason (c): the repair attempt itself proves unrecoverable (provider crash/timeout with no
output to re-validate, §5a item 5's logic applied to a repair attempt — `FAILURE_RECOVERY.md`
§1), distinct from exhausting the 3-attempt repair policy (which fails out via
`VALIDATING`/`QA_RUNNING`, already covered by reason (a)). `CREATED` has no `→ FAILED` row:
nothing is yet bound to drift before authorization, and its abort path is `→ CANCELLED`. This
table is now the complete, closed set of every `FAILED`-reachable state in this model; no prose
elsewhere in this document set requires a `→ FAILED` transition this table does not contain.

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

## 5a. Initial-Execution Failure and Reconciliation

Human Owner policy decision (OD-9, `OPEN_QUESTIONS.md`, resolved 2026-07-24), governing the
first-time (not resume-time; §6 covers resume) execution of every side-effecting operation this
scope names: the implementation-provider invocation (`IMPLEMENTING`), `create_commit`
(`READY_TO_COMMIT → COMMITTED`), `push_stage_branch` (`COMMITTED → PUSHED`), and
`create_pull_request` (`PUSHED → PR_OPEN`). It adds **no new state and no new transition** — it
defines the trigger policy the Orchestrator applies before firing an edge already in §3's table,
and a same-state, non-transitioning retry/reconciliation sub-procedure comparable in kind to the
existing infrastructure retry in §5, generalized and formalized across these four operations as
this policy requires.

1. **Proven failure before any side effect** — the provider process failed to spawn, or the
   Skill's own precondition check failed before the underlying `git`/`gh` command was ever
   invoked: the Orchestrator permits a bounded retry while remaining in the same state
   (`IMPLEMENTING`/`READY_TO_COMMIT`/`COMMITTED`/`PUSHED` respectively) — not a workflow-state
   transition. This category is deliberately narrow and never determined by error *type*: a
   timeout, connection reset, DNS failure, or lost response is **never**, by itself, sufficient
   to place a failure here, because none of those proves the underlying command had not already
   reached the remote before it happened — absence of confirmation is not proof that no side
   effect occurred. Any failure surfaced by an already-invoked `git`/`gh` subprocess or an
   already-started provider process belongs to item 2 instead, regardless of how immediate it
   appears. The retry limit and the exact, non-error-type-based classification are explicit and
   deterministic, recorded in `SKILL_CONTRACTS.md` (Git/GitHub Skills) and
   `MODEL_PROVIDER_CONTRACTS.md` (provider invocation) respectively, not left to runtime
   judgment. Exhausting the retry limit transitions the workflow to `FAILED`
   (`IMPLEMENTING`/`READY_TO_COMMIT`/`COMMITTED`/`PUSHED` → `FAILED`, each already in §3's table;
   this is a new *reason* for an existing edge, not a new edge) — never reported as success
   because the underlying command merely timed out (§5a item 6).
2. **Failure with a possible or unknown side effect** (e.g. `push_stage_branch` times out after
   the network write may have already reached the remote; the provider process is killed after
   it may have already written files): the Orchestrator never retries blindly. It first performs
   an idempotency/reconciliation check, remaining in the same state, using exactly the Skill
   idempotency guarantees already established in §7 (`create_commit`: does the tree already match
   the expected committed diff; `push_stage_branch`: does the remote ref already match;
   `create_pull_request`: does an open PR already exist for the branch; the equivalent check for
   an implementation-provider attempt is inspecting the stage branch's actual diff against what
   the provider was asked to produce) to determine whether the intended side effect already
   occurred.
3. **Reconciliation success:** if the side effect occurred correctly, the Orchestrator advances
   to the state that accurately represents repository or remote reality — the same forward edge
   the operation would have produced on ordinary success (`IMPLEMENTING → VALIDATING`;
   `READY_TO_COMMIT → COMMITTED`; `COMMITTED → PUSHED`; `PUSHED → PR_OPEN`; each already in §3's
   table, gaining "or reconciliation confirms the side effect already succeeded" as an additional
   reason, not a new edge). The side effect is never duplicated — §7's idempotency guarantees are
   exactly what make advancing safe instead of re-invoking the Skill.
4. **Recoverable inconsistency:** if the state is inconsistent but safely repairable under the
   existing recovery model, the workflow uses the existing `REPAIRING` path
   (`FAILURE_RECOVERY.md` §1) — never a second repair lifecycle. In practice this condition is
   reachable only from `IMPLEMENTING`: an ambiguous or partial implementation-provider outcome is
   never routed directly into `REPAIRING` (no new `IMPLEMENTING → REPAIRING` edge is added) — it
   proceeds forward via the existing `IMPLEMENTING → VALIDATING` edge, and deterministic
   validation's own existing `VALIDATING → REPAIRING` edge (§3) is what actually engages the
   repair cycle if a real problem is found. For `READY_TO_COMMIT`/`COMMITTED`/`PUSHED`, this
   condition does not apply: nothing at the commit/push/PR-creation phase is a code problem
   `ImplementationAgent`/`ClaudeCLIProvider` could fix, so an inconsistency there that
   reconciliation cannot resolve is never "recoverable" in this sense — it falls to item 5.
5. **Unrecoverable or indeterminate failure:** the workflow transitions to `FAILED` (the same
   existing edge as item 1) when: the retry limit is exhausted (item 1); reconciliation cannot
   establish a safe state (item 2 finds neither clean success nor a resolvable inconsistency);
   the side effect is inconsistent and not safely repairable (item 4's negative case); or a
   required invariant cannot be restored. `FAILURE_RECOVERY.md` §3's existing failure-report
   requirement (which gate failed, on which attempt, with what evidence) applies identically to
   an item-5 `FAILED` reached this way.
6. **Safety:** a workflow never reports success solely because a command timed out — a timeout
   with an unconfirmed side effect is always item 2, never item 3, until reconciliation actually
   confirms success. A side-effecting operation is never repeated without first performing
   reconciliation (never blind-retried once any possibility of a prior side effect exists — that
   is precisely the item-1/item-2 boundary). The Orchestrator alone owns every transition
   decision in this section, based on the typed result an Agent or Skill returns
   (`AGENT_CONTRACTS.md` §1; `SKILL_CONTRACTS.md` §7) — an Agent's or Skill's own report is
   evidence, never itself an authority to transition. This policy changes no authorization or
   clean-tree requirement anywhere in this document set or `STAGE_REGISTRY.md`.

Human Owner approval basis for this section, quoted verbatim: "I approve the following policy for
initial execution failures involving: implementation providers; commit operations; push
operations; PR creation; comparable external or side-effecting operations. [the six numbered
items above, restated in this document's own words] ... Treat the new failure-trigger semantics
as the appropriate normative governance change under the applicable version policy." Full
verbatim text: `docs/DECISION_LOG.md`, 2026-07-24 OD-8/OD-9 entry.

## 6. Interruption Recovery

State is persisted after every transition (`AUDIT_MODEL.md`). On process restart:

1. The Orchestrator loads the persisted state for the target repository's active workflow.
2. It re-verifies the preconditions relevant to the *current* state (repository identity,
   branch existence, working-tree cleanliness where expected, authorization binding fields
   still matching live repository state) before resuming any further transition.
3. If any bound authorization value has drifted (e.g. the baseline commit SHA no longer
   matches), the workflow moves to `FAILED` and requires new authorization to restart — it is
   never silently continued (`HUMAN_AUTHORIZATION_MODEL.md` §4). This item authorizes a
   `→ FAILED` transition from **every** non-terminal state reachable at resume time except
   `CREATED` (nothing yet bound to drift) — §3's table lists each one explicitly; none is left
   as an unlisted, prose-only requirement.
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
DD-04, DD-05, DD-09.

## 10. Open Questions
OD-4, OD-6. (OD-8, OD-9 resolved 2026-07-24 — `OPEN_QUESTIONS.md`.)

## 11. Future Revisions
Any new state or transition is a MAJOR change to this document and requires Human Owner
review, since it changes the machine-gate surface that stands in for human approval after
authorization.
