# AgentOS Workflow Automation — Stage Registry

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Stage Registry |
| **Purpose** | Live status of AUTO-001..007, the stage-lifecycle state model (distinct from the runtime `WORKFLOW_STATES.md` machine the finished engine will use), master stage-control rules, and the append-only authorization log. A *view* of `docs/TASK_QUEUE.md`, never a competing workflow. |
| **Status** | Draft |
| **Version** | 6.14 |
| **Owner** | Documentation & Governance session · Human Owner (approval and stage authorization) |
| **Dependencies** | `README.md` §5; `MVP_SCOPE.md`; `TEST_STRATEGY.md` |
| **Related Documents** | `stage-prompts/README.md`, `docs/AGENT_PROTOCOL.md`, `self-governance.yaml`, `docs/TASK_QUEUE.md` |

## Table of Contents
1. Naming Note · 2. State Model · 3. Control Rules · 4. Registry · 5. Authorization Log ·
6. Decision References · 7. Open Questions · 8. Future Revisions

## 1. Naming Note and Governance Scope

This is the **stage lifecycle** for developing the AUTO engine itself (AUTO-001..AUTO-007),
following exactly the state model this repository already established in
`docs/agentos-dashboard/STAGE_REGISTRY.md` for DASH. It is a different state machine from the
**runtime workflow states** (`WORKFLOW_STATES.md`) the finished engine will use to automate a
target repository's stage. Do not conflate `AUTHORIZED` here with `AUTHORIZED` in
`WORKFLOW_STATES.md` — see that document's §1.

**This document, together with the Standard Stage Protocol (`stage-prompts/README.md`), is the
exclusive governing authority for the AUTO-00x development-stage lifecycle** — authorization
validity, precondition semantics, and state transitions for AUTO-001..AUTO-007 as tasks of
*this* repository. `WORKFLOW_STATES.md` and `HUMAN_AUTHORIZATION_MODEL.md` govern only the
**runtime workflow engine's** future behavior once built: one execution of that engine against
an authorized **target repository's** stage. Neither of those two documents is ever authority
for an AUTO-00x stage's own authorization, precondition, or state-transition question. A prior
record in §5 (2026-07-24) cited `HUMAN_AUTHORIZATION_MODEL.md` for exactly such a question; that
was a citation error, corrected the same day (`docs/DECISION_LOG.md`).

**Authorization preconditions and execution preconditions are separate concepts.** Rule 1 in §3
lists this lifecycle's sole *authorization* preconditions — what must hold before the Human
Owner authorizes a stage. Everything a session must verify before beginning implementation of an
already-authorized stage — including the stage's named branch (rule 14; the SSP) — is an
*execution* precondition instead. A failed execution precondition never invalidates a recorded
authorization (rule 17).

## 2. State Model

Per-stage states: `NOT_STARTED → PROPOSED → AUTHORIZED → IN_PROGRESS → SELF_REVIEW → REVIEW →
APPROVAL → COMPLETE`, plus `BLOCKED` and `SUPERSEDED`. Mapping to the stage's task in
`docs/TASK_QUEUE.md` (three statuses — no fourth status exists or is added): `AUTHORIZED`/
`IN_PROGRESS`/`SELF_REVIEW`/`REVIEW`/`APPROVAL`/`BLOCKED` ≈ `Current`; `NOT_STARTED`/`PROPOSED` ≈
`Planned`; `COMPLETE`/`SUPERSEDED` ≈ `Done`. `BLOCKED` is explicitly `Current`, never `Planned`
and never a loss of authorization: it means an already-authorized stage whose execution
precondition is temporarily unmet (rule 17), not a stage returned to the queue. `BLOCKED` is
reached only from `AUTHORIZED` (rule 17) and exits only to `AUTHORIZED` (precondition resolved —
the SSP's own gate requires status `AUTHORIZED` before `IN_PROGRESS` work begins, so unblocking
always lands back there first, never skips straight to `IN_PROGRESS`) or `SUPERSEDED` (Human
Owner abandons the stage, rule 9) — never back to `NOT_STARTED`/`PROPOSED`.

**`COMPLETE` and `SUPERSEDED` both map to task status `Done`, but are never interchangeable in
meaning** (Human Owner policy decision, OD-8, `OPEN_QUESTIONS.md`): `COMPLETE` means the stage
was successfully finished per rule 12's acceptance criteria; `SUPERSEDED` means the stage was
administratively closed — abandoned or replaced by another authorized stage on Human Owner
directive (rule 9) — and is never represented as, or mistaken for, successful completion. Because
the three-status task model has no fourth status to carry this distinction, `docs/TASK_QUEUE.md`'s
prose for a `SUPERSEDED` stage's task entry must state plainly that it was superseded, not
completed, every time; `Status: Done` alone is not sufficient disclosure for a superseded stage.

At most one AUTO task is `Current` at a time (`self-governance.yaml` `maximum_current_tasks: 1`),
enforced repository-wide, not just within the AUTO family (`docs/DECISION_LOG.md`, 2026-07-23
AUTO-001 entry).

## 3. Control Rules

1. **Authorization preconditions:** predecessor `COMPLETE`; registry and `docs/TASK_QUEUE.md`
   agree; no other AUTO stage active; no other `Current` task anywhere in the queue; clean tree
   (defined below); blocking OD-# resolved.

   **Definition of "clean tree" for this rule:** the working tree contains no uncommitted change
   *other than* the sanctioned governance-transition edit set below — the complete, closed list
   of artifacts an authorized predecessor-closeout/successor-authorization transition may modify.
   That edit is the trigger for this authorization, never a violation of this precondition,
   because a session cannot record "predecessor `COMPLETE`, successor `Current`" without first
   writing exactly that diff — requiring zero diff at the literal instant of authorization would
   make this rule impossible to satisfy by construction. The sanctioned set, evidenced by both
   times this transition has actually occurred (DASH-001→AUTO-001, `docs/DECISION_LOG.md`
   2026-07-23 entry; AUTO-001→AUTO-002, 2026-07-24 entry):
   - `docs/TASK_QUEUE.md` (authoritative task status).
   - `docs/current_task.md`, `docs/remaining_tasks.md` (task-state mirrors).
   - `docs/PROJECT_STATE.md` (prose only; the `Current Version:` fact line untouched).
   - `docs/DECISION_LOG.md` (one new dated entry recording the transition, per
     `docs/AGENT_PROTOCOL.md`).
   - `docs/CHANGELOG.md` (one new `[Unreleased]` entry).
   - This program's own stage registry (this file, or the equivalent for another program) — §4's
     state cell for the predecessor (→ `COMPLETE`) and, once authorized, the successor's row; and
     §5, one new Authorization Log row for the successor.
   - This program's own program-level changelog (e.g. `docs/workflow-automation/CHANGELOG.md`) —
     one new entry; a completeness gap found on audit (the AUTO-001→AUTO-002 transition omitted
     this file, corrected retroactively, `docs/DECISION_LOG.md`), now part of the required set
     going forward.

   Any *other* uncommitted change — `src/`, `tests/`, unrelated documentation, leftover work from
   a different stage, or a different program's files — violates this precondition and must be
   resolved (committed, stashed, or reverted) before authorization. Not included in the sanctioned
   set, and therefore never expected to be dirty at authorization time: `handover/**` (maintained
   on its own cadence, not mechanically required by rule 11) and the predecessor's own completion
   report (already finalized before its closeout, not modified by this transition). This is stated
   explicitly, with a complete list rather than "and its mirrors," because an audit found the
   unqualified phrase "clean tree" ambiguous enough to read as requiring literal zero diff (which
   is unsatisfiable given the above) and found the prior, non-exhaustive wording omitted this
   file's own §4/§5 and the program-level changelog from the set it was itself describing.
2. **Authorizer:** only the Human Owner.
3. **Required language:** a written record — "I authorize AUTO-0XX" (or an equivalent explicit
   directive) — captured in the stage's task record and §5 before work.
4. **Starting:** task `Planned → Current` (requires owner authorization per
   `self-governance.yaml` `require_designer_approval_for_promotion`); registry
   `AUTHORIZED → IN_PROGRESS`. This is the **initial-start** preflight; a session *resuming* an
   already-`IN_PROGRESS` (or `SELF_REVIEW`/`REVIEW`/`APPROVAL`) stage uses rule 19 instead, never
   this rule.
5. **Retry after failure:** stage stays `IN_PROGRESS`; fixes within scope only; all gates rerun.
6. **Review return:** `REVIEW → IN_PROGRESS`, findings preserved; each review round after the
   first uses a fresh reviewer with no memory of prior rounds.
7. **Approval return:** `APPROVAL → IN_PROGRESS`; findings recorded.
8. **Amending a completed stage:** this rule protects two different things differently.
   **Completion records** — a stage's Registry row facts (§4: state, which is never re-lowered
   once `COMPLETE`; branch; which stage delivered what), its Authorization Log rows (§5), its
   stage completion report, and any `docs/DECISION_LOG.md` entry recording what was decided — are
   never edited or deleted in place, by anyone, for any reason; a wrong or incomplete record is
   fixed only via a Governance Correction Record (rule 18), which is always a new, dated,
   attributed entry that references what it corrects without altering the original text.
   **Versioned reference/control documents** that a stage happened to deliver — this registry,
   `HUMAN_AUTHORIZATION_MODEL.md`, `WORKFLOW_STATES.md`, the SSP, individual `stage-prompts/*.md`
   files, `OPEN_QUESTIONS.md` — each carry their own `Version` field (and, where present, their
   own `Future Revisions` clause) precisely because they are living governance documents, not
   frozen deliverables; amending their *content* in place (with a version bump per their own
   revision policy, and a Governance Correction Record or `docs/DECISION_LOG.md` entry stating
   what changed and why) is normal maintenance, not a rule-8 violation, provided the amendment is
   a documentation-correctness or clarity fix and does not silently rewrite what the delivering
   stage's completion record (above) says it did. Substantive re-litigation of a completed stage's
   actual architectural decisions is still corrective work belonging in a new linked task, never
   an in-place edit under either category.
9. **Superseding:** an explicit Human Owner directive (rule 2/3) moves a stage to `SUPERSEDED`;
   the registry entry records the directive and a successor reference; history append-only.
   **Legal source states for `SUPERSEDED`:** `AUTHORIZED`, `BLOCKED`, `IN_PROGRESS`,
   `SELF_REVIEW`, `REVIEW`, `APPROVAL` — i.e. any state where the stage is `Current` and has
   already been authorized. `NOT_STARTED`/`PROPOSED` are never superseded — an unauthorized,
   merely `Planned` stage is dropped or reordered by ordinary `docs/TASK_QUEUE.md` maintenance,
   not by this rule — and `COMPLETE` is never superseded (rule 8 already forbids amending a
   completed stage's completion record; a finished stage cannot be retroactively un-finished).
   **Task-status mapping:** `SUPERSEDED` ≈ `Done` (§2) — administratively closed, never
   successful completion; `docs/TASK_QUEUE.md`'s prose must say so explicitly for that task, per
   §2. **No automatic successor:** exactly as rule 16 already establishes for ordinary closeout,
   moving a stage to `SUPERSEDED` never by itself authorizes or starts a successor — a successor,
   if any, requires its own independent task record in `docs/TASK_QUEUE.md` and its own fresh,
   explicit Human Owner authorization (rules 1–3), never inferred from the superseding directive
   alone, even when both are announced in the same written directive (rule 16's same-session
   principle applies identically here). This is a Human Owner policy decision (OD-8,
   `OPEN_QUESTIONS.md`, resolved 2026-07-24) completing what this rule previously left undefined:
   the state, the directive requirement, and history's append-only nature were already
   established; the task-status mapping, the legal source-state list, and the no-automatic-
   successor rule were not, until now.
10. **Early-start prevention:** stage N+1 is never authorized until N is `COMPLETE` and fresh
    authorization is recorded.
11. **Documentation reconciliation:** a stage closes only after `docs/PROJECT_STATE.md`, the
    task queue and mirrors (`workflowctl check-task-state` green), this registry, and the stage
    report agree.
12. **Evidence before completion:** report complete per template; every acceptance criterion
    individually PASS.
13. **Closing:** commit and merge per rules 15-16; post-merge closeout updates mirrors; registry
    `COMPLETE`; task `Done`; then STOP.
14. **Branches:** one stage = one branch, created from current `main`.
15. **Merges:** one merge per stage into `main`, performed by the Human Owner; commit/push
    remain human-gated per `docs/AGENT_PROTOCOL.md`.
16. **Closeout:** task flips to `Done` only after post-merge consistency checks
    (`workflowctl verify --config self-governance.yaml`). At closeout, `task-state`,
    `governance`, and `handover` must each PASS with no exception. `git` must also PASS unless
    its only finding is a pre-existing, already-documented condition unrelated to the stage's own
    merge (e.g. `upstream_missing` on a branch never intended to be pushed) — the same tolerance
    the SSP already applies mid-stage ("identifying any pre-existing failure as pre-existing");
    a `git` finding caused by the stage's own merge (an unexpected diff, wrong parent, or wrong
    branch) is never tolerated. **No successor is *automatically* selected as a consequence of
    closeout** — closing out a predecessor never by itself promotes or authorizes a successor;
    every promotion to `Current` still requires its own distinct, explicit Human Owner
    authorization (rule 3), never inferred or defaulted from the closeout alone. This has been
    satisfied, not violated, on both occasions this repository's precondition check has found a
    predecessor still `Current` mid-authorization (DASH-001→AUTO-001 and AUTO-001→AUTO-002,
    `docs/DECISION_LOG.md` 2026-07-23 and 2026-07-24 entries): in each case the session stopped,
    reported the conflict, and the Human Owner — presented with it — gave one written directive
    resolving both ("close out DASH-001 first, then proceed with AUTO-001"; the equivalent for
    AUTO-002), which is an explicit, distinct human act for the successor, not an automatic
    consequence of the closeout, even though both landed within one continuous session. This rule
    forbids a session or agent selecting/authorizing a successor on its own initiative in the
    same session as a closeout; it does not forbid the Human Owner directing both, explicitly,
    when presented with a genuine predecessor-still-`Current` conflict.
17. **Execution-precondition failure vs. authorization:** if a stage's execution precondition
    (e.g. rule 14's named branch, or any other SSP pre-flight check) fails after the stage was
    authorized but before `IN_PROGRESS` is reached, the recorded authorization is **not**
    invalidated and implementation simply does not begin. Registry state moves to `BLOCKED` (§2);
    the task's `docs/TASK_QUEUE.md` status stays `Current`. Fresh Human Owner authorization is
    required only where a rule above explicitly says so (rule 9's superseding; rule 10's
    successor-stage start) — never merely because an execution precondition failed.
    `HUMAN_AUTHORIZATION_MODEL.md` is not authority here (§1). The only legal transitions out of
    `BLOCKED` are: (a) `BLOCKED → AUTHORIZED` — the failed precondition is satisfied and
    re-verified; the stage returns to `AUTHORIZED` (never straight to `IN_PROGRESS`, so the SSP's
    own "status is `AUTHORIZED`" check keeps passing unmodified), then proceeds through rule 4's
    normal "Starting" step (`AUTHORIZED → IN_PROGRESS`) exactly as if no interruption had
    occurred; no re-authorization act at either step; or (b) `BLOCKED → SUPERSEDED` — the Human
    Owner instead directs abandoning this stage for a successor (rule 9), an explicit directive,
    never an automatic consequence of remaining blocked. `BLOCKED` has no other legal successor;
    there is no `BLOCKED → NOT_STARTED`/`PROPOSED` transition anywhere in this model.
18. **Governance Correction Record:** the formal mechanism for fixing a wrong or ambiguous
    governance record without violating append-only semantics (rule 8; §5's own "(append-only)"
    label; the equivalent expectation for `docs/DECISION_LOG.md`). A Governance Correction Record
    is always a **new**, dated entry — appended, never overwriting or deleting prior text — that
    states: (a) which prior entry/record it corrects (by date and stage, or by section); (b)
    what was wrong; (c) the corrected fact or rule; (d) who/what found it (e.g. an independent
    audit) and when. It never edits the entry it corrects. It is used for: §5 Authorization Log
    rows found to contain an error (a new row is appended referencing the original by date/stage);
    `docs/DECISION_LOG.md` entries found to contain an error (a new entry is appended, the
    original left untouched); and as the required companion to any in-place edit of a versioned
    reference document permitted under rule 8's second category. A Governance Correction Record
    is not itself a re-authorization, a state change, or a stage promotion — it carries no
    lifecycle-transition authority of its own.
19. **Resume preflight (distinct from initial-start preflight, rule 4):** the SSP's initial-start
    check ("status is `AUTHORIZED`") governs only *starting* a stage — it does not, and was never
    meant to, govern a session *resuming* a stage whose registry state already shows work under
    way. A session resuming a stage whose registry state is `IN_PROGRESS`, `SELF_REVIEW`,
    `REVIEW`, or `APPROVAL` never requires the stage to return to `AUTHORIZED` first; those four
    states are the complete set of legal resume states. `AUTHORIZED` and `BLOCKED` are never
    resume states in this sense — `AUTHORIZED` is where initial start begins (rule 4), and a
    `BLOCKED` stage has not yet begun implementation at all (rule 17), so there is nothing to
    resume; both use the initial-start preflight instead. On resume, the session re-verifies
    every execution precondition that applied at initial start (rule 17's branch/clean-tree
    checks and any stage-specific ones in the stage's own contract) exactly as it did the first
    time. **If re-verification passes**, the session continues implementation normally — no
    registry transition occurs; the stage's state is exactly what rule 5 already establishes
    ("stage stays `IN_PROGRESS`"), and no re-authorization is triggered. **If re-verification
    fails**, the session stops, makes no change, and reports the exact failure to the Human
    Owner — the registry state is **not** demoted to `BLOCKED` (`BLOCKED` per rule 17 is reserved
    for the pre-`IN_PROGRESS` case) and is not otherwise transitioned; it remains exactly where it
    was, pending the Human Owner's resolution, consistent with rule 5's same principle applied to
    an environmental precondition instead of a review finding. A normal `IN_PROGRESS` (or
    `SELF_REVIEW`/`REVIEW`/`APPROVAL`) resume is therefore never routed through `BLOCKED` and
    never requires a new authorization event — both the passing and failing cases leave the
    registry state unchanged, differing only in whether the session may proceed.

## 4. Registry

Report paths: `docs/reports/workflow-automation/AUTO-0XX-completion-report.md`.

| Stage | Title | Role | State | Branch | Prompt |
|---|---|---|---|---|---|
| AUTO-001 | Architecture and governance contracts | Documentation & Governance session | COMPLETE | `governance/auto-001-workflow-automation-planning` | `stage-prompts/AUTO-001.md` |
| AUTO-002 | Orchestrator, state machine, locking, and persistence | Engine implementation session | COMPLETE | `feature/auto-002-orchestrator-state-machine` | `stage-prompts/AUTO-002.md` |
| AUTO-003 | Deterministic repository and validation skills | Engine implementation session | COMPLETE | `feature/auto-003-repository-validation-skills` | `stage-prompts/AUTO-003.md` |
| AUTO-004 | Claude Code CLI and Codex CLI providers | Engine implementation session | COMPLETE | `feature/auto-004-model-providers` | `stage-prompts/AUTO-004.md` |
| AUTO-005 | PMO, implementation, QA, Git, merge, and closeout agents | Engine implementation session | COMPLETE | `feature/auto-005-agents` | `stage-prompts/AUTO-005.md` |
| AUTO-006 | GitHub pull request, automatic squash merge, and closeout integration | Engine implementation session | COMPLETE | `feature/auto-006-pr-merge-closeout` | `stage-prompts/AUTO-006.md` |
| AUTO-007 | End-to-end dry run, recovery tests, and DASH integration | Engine implementation session (+ independent security review) | COMPLETE | `fix/auto-007-e2e-dry-run-recovery` | `stage-prompts/AUTO-007.md` |
| AUTO-008 | Engine CI baseline: packaging, type-checking, and verified blocker fixes | Engine implementation session | COMPLETE | `feature/auto-008-engine-ci-baseline` | `stage-prompts/AUTO-008.md` |
| AUTO-009 | WorkflowService boundary and read-only `workflowctl auto` surface | Engine implementation session | COMPLETE | `feature/auto-009-workflow-service` | (none — authorized directly by written Human Owner directive; no stage contract file was issued) |
| AUTO-010 | Real Non-Interactive Provider Runtime | Engine implementation session | COMPLETE | `feature/auto-010-provider-runtime` | `stage-prompts/AUTO-010.md` |
| AUTO-011 | Unified Provider and Agent Result Contract | Engine implementation session | COMPLETE | `feature/auto-011-agent-result-contract` | `stage-prompts/AUTO-011.md` |

## 5. Authorization Log (append-only)

| Date | Stage | Authorization record | Recorded by |
|---|---|---|---|
| 2026-07-23 | AUTO-001 | Human Owner: "I authorize AUTO-001." Preconditions verified: repository/branch/clean-tree confirmed; DASH-001 (prior `Current` task) closed out to `Done` first, per Human Owner directive, to satisfy the no-conflicting-task precondition (`docs/DECISION_LOG.md`, 2026-07-23 AUTO-001 entry). | Documentation & Governance session |
| 2026-07-24 | AUTO-002 | Human Owner: "I authorize AUTO-002." Preconditions re-checked after AUTO-001 was closed out to `Done` (PR #3, `191f600`): all passed except the planned-stage-branch binding — the session's working branch (`feature/auto-002-orchestrator-foundation`) does not match this registry's bound branch (`feature/auto-002-orchestrator-state-machine`), an invalidation condition under `HUMAN_AUTHORIZATION_MODEL.md` §2/§4. Implementation was not started; blocked pending Human Owner resolution (`docs/DECISION_LOG.md`, 2026-07-24 entry). | Engine implementation session |
| 2026-07-24 | AUTO-002 (correction) | Governance recovery session, no Human Owner action: the row above's citation of `HUMAN_AUTHORIZATION_MODEL.md` §2/§4 as the authority invalidating this authorization was found incorrect on audit and is preserved above unchanged for the historical record. That document's binding fields govern the *runtime* engine's future authorization of workflows against *target* repositories (`WORKFLOW_STATES.md` §1), not this repository's own AUTO-00x development-stage lifecycle. The correct, still-controlling authority is the SSP's "verify you are on the stage's named branch created from a clean baseline" precondition (`stage-prompts/README.md`; contract `stage-prompts/AUTO-002.md`; Control Rule 14 above) — an ordinary stage-lifecycle precondition failure. The Human Owner's "I authorize AUTO-002" authorization was never in question and stands; only the branch precondition is unmet. State corrected from the non-canonical `AUTHORIZED (blocked — …)` to the canonical `BLOCKED` (§2). No lifecycle transition changed; no implementation performed. Full rationale: `docs/DECISION_LOG.md`, 2026-07-24 governance-recovery entry. | Governance Recovery session |
| 2026-07-24 | AUTO-002 (Governance Correction Record, rule 18) | Corrects the two rows above, in place of the in-place merge a prior governance-recovery pass mistakenly applied to them (itself a rule-8/append-only violation, since remediated by restoring both rows verbatim). Both rows above stand as originally written. For the record: the first row's `HUMAN_AUTHORIZATION_MODEL.md` §2/§4 citation is incorrect for the reason the second row already states; the corrected, controlling authority is `STAGE_REGISTRY.md` §3 rule 14 (the SSP's named-branch check) and rule 17 (execution-precondition failure does not invalidate authorization). The Human Owner's "I authorize AUTO-002" authorization stands, unaffected by either row's wording. Full audit trail: `docs/DECISION_LOG.md`, 2026-07-24 entries (three governance-recovery passes). | Governance Recovery session |
| 2026-07-24 | AUTO-002 (execution precondition resolved) | The governance recovery merged into `main` via PR #4 (`163bcee`); the prior non-canonical branch (`feature/auto-002-orchestrator-foundation`) was deleted both locally and remotely. A fresh AUTO-002 session verified `main` == `origin/main`, a clean working tree, and both retained stashes untouched, then created the canonical branch `feature/auto-002-orchestrator-state-machine` from clean `main`, satisfying the SSP's initial-start branch-binding and clean-tree checks (`stage-prompts/README.md`; rule 14). Per rule 17(a), registry state moves `BLOCKED → AUTHORIZED → IN_PROGRESS`; no new Human Owner authorization act occurs at either step — the Human Owner's "I authorize AUTO-002." record above stands unchanged. Implementation of the stage's package skeleton begins under this entry. | Engine implementation session |
| 2026-07-27 | AUTO-002 (Human Owner closure) | Human Owner reviewed the implementation and validation report, accepted AUTO-002 as sufficient, explicitly waived another independent review, directed that out-of-scope observations remain future work, and authorized governance closure plus one local commit. Registry state moves `IN_PROGRESS → COMPLETE`; task status moves `Current → Done`. This closure authorizes no successor, push, or merge. | Human Owner |
| 2026-07-27 | AUTO-002 (publication and merge) | Human Owner authorized the AUTO-002 publication and merge sequence: push `feature/auto-002-orchestrator-state-machine`, merge `20c9890` into `main` by the repository's established procedure, and push `main`. Executed as PR #5, merged by merge commit `87a5062` (parents `163bcee` + `20c9890`) after both CI runs passed; local and remote `main` synchronized; the stage branch was retained and both pre-existing stashes left untouched. No registry state changes — AUTO-002 was already `COMPLETE`. This authorization explicitly excluded beginning AUTO-003. | Human Owner |
| 2026-07-27 | AUTO-003 | Human Owner: "I authorize AUTO-003." Directed branch creation from the clean, synchronized `main` (`87a5062`), implementation of AUTO-003 only, the standard implementation and validation workflow, handover/governance record updates, and a stop for Human Owner approval; commit, push, merge, and beginning AUTO-004 were all explicitly prohibited. Initial-start preflight (§3 rule 4) passed: active stage is exactly AUTO-003, branch `feature/auto-003-repository-validation-skills` created from clean `main`, `git status` clean, AUTO-002 `COMPLETE`. Per rule 17(a) the registry state moves `NOT_STARTED → AUTHORIZED → IN_PROGRESS` under this single recorded authorization act; task status moves `Planned → Current`. | Human Owner |

| 2026-07-27 | AUTO-003 (Human Owner approval and closure) | Human Owner: "I approve the AUTO-003 implementation." Approved the implementation, required a pre-commit scope/`git diff --check`/`git status`/stash re-verification, and authorized exactly one local commit, created as `908be94`; push and merge were explicitly withheld. Registry state moves `IN_PROGRESS → COMPLETE`; task status moves `Current → Done`. The closure to `Done` was applied when the Human Owner subsequently authorized GOV-AUTO-01 as **the single active task**, which AUTO-003 could not remain `Current` alongside under `maximum_current_tasks: 1`. This closure authorizes no successor: AUTO-004 remains `NOT_STARTED` and explicitly unauthorized. | Human Owner |
| 2026-07-27 | GOV-AUTO-01 (recorded here for continuity only) | Human Owner authorized GOV-AUTO-01 — Local Human-Gated Task Runner, a governance/developer-experience task **outside the AUTO family**. It has no stage in this registry, no stage contract, and no lifecycle state here; this row exists solely so the AUTO timeline is not misread as continuing to AUTO-004. Its authoritative record is `docs/TASK_QUEUE.md` and `docs/current_task.md`. | Human Owner |
| 2026-07-28 | GOV-AUTO-01 (closure, recorded here for continuity only) | Human Owner decision closing GOV-AUTO-01 `Current → Done`, recording that it was implemented, validated, approved, committed as `a302c95`, and merged into `main` via `a3b5b0a`. GOV-AUTO-01 has no lifecycle state in this registry (see the row above); this row exists solely because the closure is what freed the single `Current` slot for AUTO-004 below, and the AUTO timeline would otherwise show AUTO-004 authorized while another task was still `Current`. The closure was bookkeeping catching up with `main`: the merge had already landed while `docs/TASK_QUEUE.md`, both mirrors, and `handover/PROJECT_HANDOVER.md` still recorded the task as `Current` and uncommitted. Authoritative record: `docs/TASK_QUEUE.md`. | Human Owner |
| 2026-07-28 | AUTO-004 | Human Owner: "I authorize AUTO-004 — Claude Code CLI and Codex CLI providers." Directed branch creation from the current clean and synchronized `main` (`a3b5b0a`), implementation of AUTO-004 only, the standard implementation workflow with focused tests, full validation, a bounded self-review, and governance/handoff updates, then a stop for Human Owner approval; commit, push, merge, and beginning AUTO-005 or any other task were all explicitly prohibited. **Rule 16 predecessor conflict, presented and resolved:** the session's precondition check found GOV-AUTO-01 still `Current` in the queue and both mirrors although its commit was already merged into `main`, which under `maximum_current_tasks: 1` blocked rule 1's "no other `Current` task" precondition. The session stopped, made no change, and reported the conflict; the Human Owner, presented with it, gave one written decision resolving both — close GOV-AUTO-01 to `Done` (row above), then authorize and begin AUTO-004 as the single `Current` task. This is an explicit, distinct human act for the successor, not an automatic consequence of the predecessor's closeout, exactly as rule 16 contemplates and as the DASH-001→AUTO-001 and AUTO-001→AUTO-002 precedents established. Initial-start preflight (§3 rule 4) then passed: active stage is exactly AUTO-004, AUTO-002 (the contract's named precondition) and AUTO-003 are `COMPLETE`, branch `feature/auto-004-model-providers` created from clean `main`, `git status` clean. Per rule 17(a) the registry state moves `NOT_STARTED → AUTHORIZED → IN_PROGRESS` under this single recorded authorization act; task status moves `Planned → Current`. | Human Owner |

| 2026-07-28 | AUTO-004 (Human Owner approval, closure, and publication) | Human Owner: "I approve the AUTO-004 implementation and authorize its formal closure and publication." Recorded that AUTO-004 was implemented, validated, approved, and committed locally as `84616d5`. Registry state moves `IN_PROGRESS → COMPLETE`; task status moves `Current → Done`. The same decision authorized publication — push `feature/auto-004-model-providers` to `origin`, update local `main` from `origin/main` without rewriting history, merge the stage branch by the repository's established safe merge policy, push `main`, retain the stage branch, and leave both stashes untouched. **Record-integrity note (rule 8):** commit `84616d5` was created *after* `docs/reports/workflow-automation/AUTO-004-completion-report.md` had been written, so that report's "no commit … was performed" Confirmation was accurate at the time of writing; per the Human Owner's explicit instruction it is **not** rewritten. The commit, the approval, and the merge are recorded in a new append-only addendum appended to that report, plus this row and `docs/DECISION_LOG.md` (2026-07-28 AUTO-004 closure entry). This closure authorizes no successor by itself (rule 16); AUTO-005's authorization is a separate, explicitly recorded act in the row below. | Human Owner |

| 2026-07-28 | AUTO-005 | Human Owner: "After AUTO-004 is successfully merged and all closure checks pass, I authorize AUTO-005 — Agents." Authorized in the same written decision that approved and closed AUTO-004 (row above), but as its own explicit, separately-conditioned act rather than as a consequence of that closeout — exactly the distinction rule 16 draws, and the fifth time this repository has resolved a predecessor-still-`Current` conflict this way (DASH-001→AUTO-001, AUTO-001→AUTO-002, GOV-AUTO-01→AUTO-004, and AUTO-004's own closure). The session detected the conflict, made no change, and reported it; the Human Owner, presented with it, decided both halves. **The condition was verified before this row was written**, not assumed: `main` carries the AUTO-004 merge (`4721f9a`, parents `a3b5b0a` + `4659172`), local `main` equals `origin/main`, `agentos_workflow/providers/` exists on `main`, the working tree is clean, no task was `Current`, and `workflowctl verify` returned PASS on all four checks (`git`, `task-state`, `governance`, `handover`). Initial-start preflight (§3 rule 4) then passed: the active stage is exactly AUTO-005, AUTO-002/AUTO-003/AUTO-004 are `COMPLETE`, and branch `feature/auto-005-agents` was created from that clean, synchronized `main`. Per rule 17(a) the registry state moves `NOT_STARTED → AUTHORIZED → IN_PROGRESS` under this single recorded authorization act; task status moves `Planned → Current`. The decision explicitly prohibits committing, pushing, merging, or beginning AUTO-006, and requires the stage to stop at a Human Owner approval report. | Human Owner |

| 2026-07-28 | AUTO-005 (Human Owner approval) | Human Owner: "I approve the AUTO-005 implementation." Explicitly accepted all five documented limitations for this stage — the QA report artifact collision and its scoped per-attempt workaround, the stated three-repair-attempt interpretation, the unverified AUTO-006 Git/GitHub Skill call shapes, the empty future-stage path map, and the deferral of Agent-to-Orchestrator wiring to AUTO-007 — directed that the QA report collision be recorded as explicit future work rather than fixed in scope (now GOV-3, `docs/TASK_QUEUE.md`, `Planned`), required a pre-commit branch/HEAD/scope/stash re-verification, prohibited a further independent review, and authorized exactly one local commit. Created as `430cbb4` after the required verification passed (branch `feature/auto-005-agents`, HEAD still `4721f9a`, diff limited to the Agent implementation, its tests, the stage report, and the governance/changelog/handover/checksum updates, no AUTO-006 or AUTO-007 implementation, both stashes untouched, `git diff --check` clean). Push and merge were withheld at this point; no registry state changed — approval of an implementation is not closure. | Human Owner |
| 2026-07-28 | AUTO-005 (Human Owner closure and publication) | Human Owner: "I approve the formal closure and publication of AUTO-005. The approved AUTO-005 commit is `430cbb4`." Recorded that AUTO-005 was implemented, validated, approved, and committed locally as `430cbb4`. Registry state moves `IN_PROGRESS → COMPLETE`; task status moves `Current → Done`. The same decision authorized publication — push `feature/auto-005-agents` to `origin`, update local `main` from `origin/main` with `--ff-only`, merge by the repository's established safe merge policy, push `main`, retain the stage branch, leave both stashes untouched, and not begin AUTO-006. **Record-integrity note (rule 8):** the AUTO-005 completion report recorded the approval and the authorized commit *before* that commit existed, so it names no hash and is **not** rewritten; the commit hash, the closure, and the merge are recorded in a new append-only addendum appended to it, plus this row and `docs/DECISION_LOG.md`. This closure authorizes no successor (rule 16): AUTO-006, AUTO-007, GOV-2, and GOV-3 all remain `Planned` and unauthorized. | Human Owner |
| 2026-07-28 | GOV-AUTO-02 (recorded here for continuity only) | Human Owner authorized GOV-AUTO-02 — Local Task Authorization and Launch Gate, a governance/developer-experience task outside the AUTO family. It has no lifecycle state in this registry; authoritative status is `Current` in `docs/TASK_QUEUE.md`. Its implementation is complete, validated, uncommitted, and pending Human Owner approval. AUTO-006 remains `NOT_STARTED`/`Planned` and unauthorized. | Human Owner |
| 2026-07-28 | GOV-AUTO-02 (closure, recorded here for continuity only) | Human Owner closed GOV-AUTO-02 `Current → Done`, recording that it was implemented, validated, approved, and committed as `d212e4d2dae2cd0a3510c54d7cd098fdfd5da548`. GOV-AUTO-02 has no AUTO lifecycle state in this registry; its authoritative status is `Done` in `docs/TASK_QUEUE.md`. No task remains `Current`. This governance-only closure authorizes no successor, push, merge, or work on AUTO-006, which remains `NOT_STARTED`/`Planned` and explicitly unauthorized. | Human Owner |

| 2026-07-28 | AUTO-006 | Human Owner supplied both exact `AUTHORIZE` confirmations through `scripts/workflow-authorize.sh`. Preconditions passed on the default-branch baseline at `0a663a35ea502b7524344d69c595cfb1cc9984c0`. Registry moves `NOT_STARTED → AUTHORIZED`; implementation has not started. | Human Owner |
| 2026-07-28 | AUTO-006 (initial-start preflight passed) | Engine implementation session verified: active stage exactly AUTO-006 with registry status `AUTHORIZED`; predecessors AUTO-003 and AUTO-005 `COMPLETE`; `docs/current_task.md`/`docs/TASK_QUEUE.md` agree (`Current`); `main`/`origin/main` clean at `3336184619bc6464f62a162ee34d869957b08928` (the authorization commit itself, `git status` clean, no stray files). Branch `feature/auto-006-pr-merge-closeout` created from that clean `main`. Per rule 4 the registry state moves `AUTHORIZED → IN_PROGRESS`; no new Human Owner authorization act occurs. Implementation of `agentos_workflow/skills/git_github.py` (the eight Git/GitHub Skills of `SKILL_CONTRACTS.md` §5) begins under this entry. | Engine implementation session |
| 2026-07-28 | AUTO-006 (Human Owner approval, closure, and publication) | Human Owner: "I approve the formal closure and publication of AUTO-006. The approved AUTO-006 implementation commit is `d8d356d060076be4ad78afb4d20891004a946204`." Recorded that AUTO-006 was implemented, validated, approved, and committed locally as `d8d356d060076be4ad78afb4d20891004a946204`. Registry state moves `IN_PROGRESS → COMPLETE`; task status moves `Current → Done`. The same decision authorized publication — push `feature/auto-006-pr-merge-closeout` to `origin`, update local `main` from `origin/main`, merge the stage branch by the repository's established safe merge policy, push `main`, retain the stage branch, and leave both stashes untouched. It explicitly withheld authorization for AUTO-007 and for GOV-AUTO-03. **Record-integrity note (rule 8):** commit `d8d356d` was created *after* `docs/reports/workflow-automation/AUTO-006-completion-report.md` had been written, so that report's "no commit … was performed" Confirmation was accurate at the time of writing; per the Human Owner's explicit instruction it is **not** rewritten. The commit, the approval, and the merge are recorded in a new append-only addendum appended to that report, plus this row and `docs/DECISION_LOG.md` (2026-07-28 AUTO-006 closure entry). The two limitations AUTO-006 self-reported (Orchestrator wiring of the Merge Safety Gate / Checks-Wait Gate; the `allowed_environment_variables` gap, OD-10) were explicitly accepted, not fixed, by this closure. This closure authorizes no successor by itself (rule 16); AUTO-007 and GOV-AUTO-03 remain unauthorized. | Human Owner |
| 2026-07-28 | GOV-AUTO-03 (recorded here for continuity only) | Human Owner authorized GOV-AUTO-03 — Human-Approved Commit with Automatic Task Closeout, a governance/developer-experience task outside the AUTO family. It has no lifecycle state in this registry; authoritative status is `Current` in `docs/TASK_QUEUE.md`. Extends `scripts/workflow-approve.sh` to perform the approved implementation commit and the governance closeout of that task together as one commit, gated on the `project.id: ai-workflow-engine` marker so every other repository keeps the unchanged GOV-AUTO-01 gate. Its implementation is complete, validated, uncommitted, and pending Human Owner approval. AUTO-007 remains `NOT_STARTED`/`Planned` and unauthorized. | Human Owner |

| 2026-07-28 | AUTO-007 | Human Owner supplied both exact `AUTHORIZE` confirmations through `scripts/workflow-authorize.sh`. Preconditions passed on the default-branch baseline at `b4abc0a5b2ba67d38b7c156ee7522aef9d8b52e9`. Registry moves `NOT_STARTED → AUTHORIZED`; implementation has not started. | Human Owner |
| 2026-07-28 | AUTO-007 (initial-start preflight passed) | Engine implementation session verified: active stage exactly AUTO-007 with registry status `AUTHORIZED`; predecessors AUTO-002 through AUTO-006 all `COMPLETE`; `docs/current_task.md`/`docs/TASK_QUEUE.md`/`docs/remaining_tasks.md` agree (`Current`); local `main` at `35c41b4` (one commit ahead of `origin/main`, that commit being the AUTO-007 authorization record itself — a pre-existing, already-recorded state, not new divergence), `git status` clean, no stray files. Branch `fix/auto-007-e2e-dry-run-recovery` created from that clean `main`. Per rule 4 the registry state moves `AUTHORIZED → IN_PROGRESS`; no new Human Owner authorization act occurs. Implementation of the AUTO-007 end-to-end dry run, interruption/resume and retry/reconciliation matrices, and security-rule test suite under `agentos_workflow/tests/e2e/**` and `agentos_workflow/tests/recovery/**` begins under this entry. | Engine implementation session |

| 2026-07-29 | AUTO-007 (Human Owner approval and closure) | Human Owner supplied both exact `APPROVE` confirmations through `scripts/workflow-approve.sh`, which performed the deterministic governance closeout on branch `fix/auto-007-e2e-dry-run-recovery` in the same commit as the approved implementation. Registry state moves to `COMPLETE`; task status moves `Current -> Done`. This closure authorizes no successor. | Human Owner |

| 2026-07-30 | AUTO-008 | Human Owner registered and authorized AUTO-008 in one act, following an architectural audit of the repository. Preconditions: AUTO-001..AUTO-007 all `COMPLETE`; branch `feature/auto-008-engine-ci-baseline` created from clean, synchronized `main` at `96a6bb4e7534008cf9516829df7db58fb79b1c50` (which the Human Owner published in the same session by fast-forwarding DASH-004's implementation commit onto `main`). AUTO-008 was not previously registered, so this single entry records both its registration and its authorization; registry state is `AUTHORIZED`. The stage is explicitly scoped to making the existing engine verifiable and adds no capability. Implementation approval, push, and merge remain separate. | Human Owner |

| 2026-07-30 | AUTO-008 (Human Owner approval and closure) | Human Owner required an explicit scope-and-cleanliness verification of the candidate implementation before approving. That verification found and corrected two self-inflicted defects — anticipatory `live_cli`/`live_gh` markers with a CI `-m` filter that had no consumer, and a tautological assertion plus needless `pytest.skip` in the new version test — after which the Human Owner approved the implementation and authorized closure, commit, and push. Evidence: 2,967 tests passing under one `pytest` invocation (from 1,160 collected), `mypy --strict` clean over 115 source files across all three packages, `ruff`/`black` clean, wheel containing all three packages, all three importable from outside the repository root, and the `MVP_SCOPE.md` §4 end-to-end dry run passing with both test-only production workarounds deleted. OD-10 and OD-11 resolved. Registry state moves `AUTHORIZED → COMPLETE`; task status moves `Current → Done`. Reported and deliberately unfixed: F-2 (AUTO-006's eight Git/GitHub Skills still unbound in `default_skill_registry()`, REQUIRED before AUTO-013) and F-1 (`expected`/`actual` convention divergence across the drift raise sites, RECOMMENDED). This closure authorizes no successor. | Human Owner |

| 2026-07-30 | GOV-AUTO-06 (recorded here for continuity only) | Human Owner registered and authorized GOV-AUTO-06 — Bind delivered Git/GitHub skills into the default AgentOS skill registry — a governance/engine follow-up task **outside the AUTO family**, following the GOV-AUTO-01 precedent above. It has no stage in this registry, no stage contract, and no lifecycle state here; this row exists solely because it resolves the F-2 finding AUTO-008 reported and deliberately left unfixed, so the AUTO timeline is not misread as continuing to AUTO-009. F-2: AUTO-006 delivered all eight Git/GitHub Skills, but `PROVISIONAL_SKILL_NAMES` still classifies them as undelivered and `default_skill_registry()` still does not bind them, so `GitAgent`/`MergeAgent` cannot invoke their own contracted Skills through the production registry. The Human Owner's proposed ID `AUTO-008-F2` was not usable — the governance parser resolves it to the existing `Done` task `AUTO-008` — so `GOV-AUTO-06` is used; the recommended branch name is kept. Authoritative record: `docs/TASK_QUEUE.md` and `docs/current_task.md`. AUTO-009 remains unauthorized. | Human Owner |

| 2026-07-30 | GOV-AUTO-06 (closure, recorded here for continuity only) | Human Owner required a final seven-point scope and integrity verification, all of which passed, then approved GOV-AUTO-06 and authorized its closeout commit and push. The eight Git/GitHub Skills AUTO-006 delivered are now bound in `default_skill_registry()` (32 → 40 entries), each identity-verified against `skills/git_github.py`, so `GitAgent` and `MergeAgent` can invoke their own contracted Skills through the production registry for the first time. `AGENT_SKILL_CONTRACTS` is AST-identical to its prior value and a negative test proves no Agent gained reach. Evidence: 2,978 tests passing, `mypy --strict` clean over 115 source files, `ruff`/`black`/pre-commit clean. GOV-AUTO-06 has no lifecycle state in this registry (see the row above); this row exists solely because it resolves the F-2 finding AUTO-008 recorded. Task status moves `Current → Done`. This closure authorizes no successor — F-1 and AUTO-009 remain unauthorized. | Human Owner |

| 2026-07-31 | GOV-AUTO-07 (recorded here for continuity only) | Human Owner registered and authorized GOV-AUTO-07 — Normalize the `AuthorizationBindingDriftError` expected/actual convention — a governance/engine follow-up task **outside the AUTO family**, following the GOV-AUTO-01 precedent above. It has no stage in this registry, no stage contract, and no lifecycle state here; this row exists solely because it resolves the F-1 finding AUTO-008 reported and deliberately left unfixed, so the AUTO timeline is not misread as continuing to AUTO-009. F-1: `_detect_authorization_binding_drift` passes the independently-supplied current value as `expected` and the persisted `AuthorizationRecord` as `actual`, while `_validate_live_resume_observation`/`_live_drift` passes the persisted record as `expected` and the live observation as `actual` — mutually inverted, so `.expected`/`.actual` mean opposite things depending on which safety path raised. Preconditions: branch `feature/gov-auto-07-drift-argument-convention` created from clean, synchronized `main` at `d8d10ec54c38571f6a4453a11d0e99c53d151743`. Authoritative record: `docs/TASK_QUEUE.md` and `docs/current_task.md`. AUTO-009 remains unauthorized. | Human Owner |

| 2026-07-31 | GOV-AUTO-07 (closure, recorded here for continuity only) | Human Owner required a final eight-point verification — convention consistency, changed-site relevance, behaviour invariance, public-surface compatibility, the four cross-record checks, regression-test genuineness, untouched prohibited surfaces, and residue — all of which passed, then approved GOV-AUTO-07 and authorized its implementation/closeout commit and push. `AuthorizationBindingDriftError` now documents one convention obeyed at all 43 of its raise/helper call sites: `expected` is the authorization-bound value where the comparison has one, else the required invariant; `actual` is the current runtime/repository/observed/supplied value judged against it. Three clusters normalized — `_detect_authorization_binding_drift` (ten fields), two `_live_drift` calls, and the four cross-record checks in `_validate_persisted_authorization_evidence` (a third inversion beyond the two F-1 named, included deliberately and flagged as such). Comparisons are symmetric, so drift detection is unchanged; public attributes and the rendered message are byte-identical. Evidence: 3,005 tests passing (2,978 + 27), the new suite failing 17 of 27 against the pre-fix engine, `mypy --strict` clean over 115 source files, `ruff`/`black`/pre-commit clean. GOV-AUTO-07 has no lifecycle state in this registry (see the row above); this row exists solely because it resolves the F-1 finding AUTO-008 recorded. Task status moves `Current → Done`. This closure authorizes no successor — AUTO-009 remains unauthorized. | Human Owner |

| 2026-07-31 | AUTO-009 | Human Owner registered and authorized AUTO-009 — WorkflowService boundary and read-only `workflowctl auto` surface — in one written directive naming the stage, its goal, its required public boundary, its required CLI surface, its strictly prohibited behaviours, and its stop condition. AUTO-009 had never been registered before, so this single entry records both its registration and its authorization. Authorization preconditions (rule 1) verified: AUTO-001..AUTO-008 all `COMPLETE`; the two intervening non-AUTO follow-ups (GOV-AUTO-06, GOV-AUTO-07) both `Done`, each having explicitly left AUTO-009 unauthorized; no other AUTO stage active and no other `Current` task anywhere in the queue (the `Current` set was empty); registry and `docs/TASK_QUEUE.md` agree; working tree clean at `main` == `origin/main` == `98acc1951f0d5d361af907c4333a04992f901918`; no blocking OD-#. Registry state moves `NOT_STARTED → AUTHORIZED`. No stage contract file (`stage-prompts/AUTO-009.md`) was issued; the written directive is the contract, and its scope is transcribed into `docs/TASK_QUEUE.md`. | Human Owner |

| 2026-07-31 | AUTO-009 (initial-start preflight passed) | Engine implementation session verified: active stage exactly AUTO-009 with registry status `AUTHORIZED`; predecessor AUTO-008 `COMPLETE`; `docs/TASK_QUEUE.md`/`docs/current_task.md`/`docs/remaining_tasks.md` agree (`Current`); `main` == `origin/main` at `98acc1951f0d5d361af907c4333a04992f901918`, `git status` clean, no stray files. Branch `feature/auto-009-workflow-service` created from that clean, synchronized `main`. Per rule 4 the registry state moves `AUTHORIZED → IN_PROGRESS`; no new Human Owner authorization act occurs. Implementation of `agentos_workflow/service.py` (the four-operation read-only `WorkflowService` façade) and `agentos_workflow/cli_auto.py` (the additive `workflowctl auto` Typer sub-application) begins under this entry. The directive explicitly withholds the implementation/closeout commit, push, PR, merge, and AUTO-010. | Engine implementation session |

| 2026-07-31 | AUTO-009 (Human Owner approval and closure) | Human Owner approved AUTO-009 for finalization and required a final twelve-point scope, API, and read-only integrity verification before any commit — exact four-operation surface; absence of all twelve forbidden verbs; typed immutable results with no state mutation, no `RepositoryLock` acquisition, no subprocess, no agent or provider invocation, no Git/GitHub mutation, and preserved path-confinement and symlink protections; `StateStore.list_workflow_ids()` ownership, read-only-ness, creation-freeness, unsafe/symlink refusal, and deterministic ordering; `skills.reporting.read_reports()` read-only-ness, non-generation, byte/mtime preservation, and confinement; the exact four-command `workflowctl auto` surface; unchanged existing commands and output contracts; assumptions A3 and A4 implemented as documented; all six deferred defects still deferred; no successor behaviour; and no debug code, TODO/FIXME, skipped or xfail test, temporary workaround, commented-out implementation, or unrelated refactor. **All twelve passed.** Read-only-ness was demonstrated with every mutation channel booby-trapped — `RepositoryLock.acquire`/`__enter__`/`release`, `subprocess.run`/`Popen`, `os.system`/`fork`/`posix_spawn`, both `StateStore` append methods, and all six reporting writers — none of which was reached by any of the six operations, alongside a path+mode+mtime+bytes digest over the state directory, the audit directory, and the target repository that was identical before and after each. Compatibility was proven by byte-comparing fourteen existing command invocations against the baseline worktree at `98acc195`: thirteen byte-identical, the fourteenth being `workflowctl --help`, which gains the intended `auto` group and nothing else. Evidence: 3,151 tests passing (3,005 + 146 new, none skipped, none xfail), `mypy --strict` clean over 117 source files, `ruff`/`black`/pre-commit clean, the wheel carrying both new modules and both importable from outside the repository root. Registry state moves `IN_PROGRESS → COMPLETE`; task status moves `Current → Done`. Six non-blocking defects (D1–D6) were recorded, classified, and remain deferred, none fixed. This closure authorizes no successor — AUTO-010 and every later roadmap phase remain unauthorized. Publication is limited to pushing `feature/auto-009-workflow-service`: no PR, no merge. | Human Owner |
| 2026-07-31 | AUTO-010 | Human Owner registered and authorized AUTO-010 — Real Non-Interactive Provider Runtime — in one written directive naming the stage, its mission, its required architecture (`WorkflowService → Provider Runtime → Claude CLI / Codex CLI`), its closed permission and sandbox enums, its three-layer never-ask enforcement, its minimum typed result contract, its strictly prohibited behaviours, and its stop condition. AUTO-010 had never been registered before, so this single entry records both its registration and its authorization. Authorization preconditions (rule 1) verified: predecessor AUTO-009 `COMPLETE`; AUTO-001..AUTO-009 all `COMPLETE`; the intervening non-AUTO follow-ups GOV-AUTO-06 and GOV-AUTO-07 both `Done`; no other AUTO stage active and no other `Current` task anywhere in the queue (the `Current` set was empty); registry and `docs/TASK_QUEUE.md` agree; working tree clean at `main` == `origin/main` == `5d1b6be516519daf640d45724c910a114fd28104`; `workflowctl verify --config self-governance.yaml` PASS on all five checks; `pytest -q` at the declared 3,151-test baseline; no blocking OD-#. A stage contract file was issued at `stage-prompts/AUTO-010.md`. Registry state moves `NOT_STARTED → AUTHORIZED`. | Human Owner |
| 2026-07-31 | AUTO-010 (initial-start preflight passed) | Engine implementation session verified: active stage exactly AUTO-010 with registry status `AUTHORIZED`; predecessor AUTO-009 `COMPLETE`; `docs/TASK_QUEUE.md`/`docs/current_task.md`/`docs/remaining_tasks.md` agree (`Current`); `main` == `origin/main` at `5d1b6be516519daf640d45724c910a114fd28104`, `git status` clean, no stray files. Branch `feature/auto-010-provider-runtime` created from that clean, synchronized `main`. Per rule 4 the registry state moves `AUTHORIZED → IN_PROGRESS`; no new Human Owner authorization act occurs. Implementation of `agentos_workflow/providers/runtime.py` (the public Provider Runtime boundary), the non-interactive hardening of the shared provider process runner, the explicit Claude permission-mode and Codex sandbox-mode argv, and the narrow `WorkflowService.invoke_provider` delegation begins under this entry. The directive explicitly withholds the implementation/closeout commit, push, PR, merge, and AUTO-011. | Engine implementation session |
| 2026-07-31 | AUTO-010 (Human Owner approval and closure) | Human Owner approved AUTO-010 for finalization and required a final fourteen-point scope, runtime, and safety verification before any commit — both providers fully live-validated; non-interactive execution proven (no TTY, prompt on stdin, stdin closed, no interactive approval, no user questions, timeout enforced, process group reclaimed); closed permission/sandbox enums with `bypassPermissions` and `danger-full-access` unreachable, `shell=False`, no alias execution, no argument injection, no inline environment assignments; account selection by real executable plus allowlisted `CLAUDE_CONFIG_DIR`/`CODEX_HOME`; no account path or credential in source, reports, output, or artifacts; Codex read-only/workspace-write/answer-file/JSONL-fallback behaviour; Claude plan/controlled-write/ambiguous-input behaviour; stdout *and* stderr ceilings with cleanup on breach; disposable repositories and isolated session directories; no leaked child or grandchild process; unchanged `workflowctl auto` behaviour; untouched successor subsystems; unchanged deferred defects; and no debug code, TODO/FIXME, xfail, temporary workaround, commented-out implementation, or unrelated refactor. **All fourteen passed.** Evidence: 3,241 tests passing (3,151 + 90, none skipped, none xfail) plus **25 live acceptance tests against the real installed CLIs with zero skips** — Claude 9, Codex 9, guards 7, each provider validated on all ten of its acceptance criteria; `mypy --strict` clean over 120 source files; `ruff`, `black`, and pre-commit clean; the wheel carrying every new module and all importable from outside the repository root; nine existing `workflowctl` invocations byte-identical to the `5d1b6be` baseline. Three blockers were fixed inside the shared provider process runner and documented (process-group termination and TTY detachment, streaming output ceilings, and the Codex report channel that could never have parsed a real run). **Provenance note:** the approval was given in conversation and the closeout performed manually, not through `scripts/workflow-approve.sh` — no scripted `APPROVE` confirmations were typed, and none were supplied by the session. Registry state moves `IN_PROGRESS → COMPLETE`; task status moves `Current → Done`. Four non-blocking defects (D-3 through D-6) remain deferred, none fixed; D-1 was withdrawn as misdiagnosed and D-2/D-7 resolved. This closure authorizes no successor — AUTO-011 and every later roadmap phase remain unauthorized. Publication is limited to pushing `feature/auto-010-provider-runtime`: no PR, no merge. | Human Owner |
| 2026-08-01 | AUTO-010 (publication) | Human Owner authorized publication of the already-approved, already-closed AUTO-010, which the 2026-07-31 closure had explicitly withheld. Pull request **#10** was opened against `main` containing exactly the one existing commit `8685d6f36028cf1a46642a1d7bd2874975ed6c00` — no file modified, no additional commit created — and merged with the repository's established merge-commit policy (never squash) as merge commit **`fd0b34fe0df21d2c6af8cfc2d681ff17ed2984e1`**, verified to have exactly two parents (`5d1b6be` + `8685d6f`). CI: the single `validate` job passed. Local and remote `main` are both `fd0b34f`; the working tree is clean; the stage branch is retained locally and on origin per repository policy. Post-merge validation on `main`: `workflowctl verify --config self-governance.yaml` full PASS (0 Current, 43 Done, 6 Planned), `pytest -q` 3,241 passed, `pytest -q -m live_cli -rs` 25 passed with zero skips. Registry status is unchanged at `COMPLETE` — publication is a delivery act, not a state change. No deferred defect was fixed and no new defect was discovered. | Human Owner |
| 2026-08-01 | AUTO-011 | Human Owner registered and authorized AUTO-011 — Unified Provider and Agent Result Contract — in one written directive naming the stage, its mission, its required architecture (`WorkflowService → Provider Runtime → Canonical AgentRunResult`), its eighteen required canonical fields, its four-status contract and invariants, its advisory-only authority rule for `recommended_next_state`, its compatibility constraints, its strictly prohibited behaviours, and its stop condition. AUTO-011 had never been registered before, so this single entry records both its registration and its authorization. Authorization preconditions (rule 1) verified: predecessor AUTO-010 `COMPLETE` **and now merged and published**; AUTO-001..AUTO-010 all `COMPLETE`; the intervening non-AUTO follow-ups GOV-AUTO-06 and GOV-AUTO-07 both `Done`; no other AUTO stage active and no other `Current` task anywhere in the queue (the `Current` set was empty); registry and `docs/TASK_QUEUE.md` agree; working tree clean at `main` == `origin/main` == `fd0b34fe0df21d2c6af8cfc2d681ff17ed2984e1`; `workflowctl verify --config self-governance.yaml` PASS on all five checks; `pytest -q` at the declared 3,241-test baseline and `pytest -q -m live_cli -rs` at 25 passed / 0 skipped; no blocking OD-#. A stage contract file was issued at `stage-prompts/AUTO-011.md`. Registry state moves `NOT_STARTED → AUTHORIZED`. | Human Owner |
| 2026-08-01 | AUTO-011 (initial-start preflight passed) | Engine implementation session verified: active stage exactly AUTO-011 with registry status `AUTHORIZED`; predecessor AUTO-010 `COMPLETE`, merged, and published; `docs/TASK_QUEUE.md`/`docs/current_task.md`/`docs/remaining_tasks.md` agree (`Current`); `main` == `origin/main` at `fd0b34fe0df21d2c6af8cfc2d681ff17ed2984e1`, `git status` clean, no stray files; no pre-existing AUTO-011 work anywhere in the repository (no branch, no `AgentRunResult` symbol, no registry row). Branch `feature/auto-011-agent-result-contract` created from that clean, synchronized `main`. Per rule 4 the registry state moves `AUTHORIZED → IN_PROGRESS`; no new Human Owner authorization act occurs. Implementation of `agentos_workflow/results.py` (the canonical `AgentRunResult`, its artifact and failure representations, and the provider adapter) begins under this entry. The directive explicitly withholds the implementation/closeout commit, push, PR, merge, and AUTO-012. | Engine implementation session |
| 2026-08-01 | AUTO-011 (Human Owner approval and closure) | Human Owner approved AUTO-011 for finalization and required a final fourteen-point scope, contract, and compatibility verification before any commit — exactly the approved canonical fields with no speculative successor fields; the four-status contract; every status invariant, including `COMPLETED` rejecting both failure data and blocking issues and unknown statuses rejected; `status` and `final_verdict` still semantically distinct and not collapsed; `recommended_next_state` advisory only and unable to mutate workflow state, authorize a transition, invoke an agent/provider/skill, or bypass deterministic validation; the adapter preserving every AUTO-010 result and failure classification; the single documented normalization (`COMPLETED` + blocking issues -> `FAILED`/`MALFORMED_OUTPUT`) preserving both summary and blockers; deterministic, strict, duplicate-key-rejecting, round-trip-safe, timezone-aware, immutable, secret-redacted serialization; artifacts as references only with unsafe paths refused; no change to any provider, process-runner, service, CLI, agent, skill, state-machine, configuration, Git, GitHub, or shell behaviour; AUTO-010 provider-runtime and live CLI tests unchanged and passing; every deferred finding still deferred; AUTO-012 untouched; and no debug code, TODO/FIXME, skip, xfail, temporary workaround, commented-out implementation, or unrelated refactor. **All fourteen passed.** Evidence: 3,352 tests passing (3,241 + 111, none skipped, none xfail) plus **25 live acceptance tests against the real installed CLIs with zero skips**, unchanged from AUTO-010's closing numbers; the 240 AUTO-010 mocked provider/service tests passing with their files byte-identical; `mypy --strict` clean over 121 source files; `ruff`, `black`, and pre-commit clean; the wheel carrying `results.py` and all modules importable from outside the repository root; six `workflowctl` invocations byte-identical to a clean `fd0b34f` worktree, MD5-compared. `git diff --stat fd0b34f` is empty across every provider, orchestrator, agent, skill, config, CLI, `src/`, `scripts/`, and packaging path — **no production file outside the new module was modified**. **One deviation disclosed and accepted:** `AgentRunResult` carries a nineteenth field, `session_id`, beyond the eighteen enumerated — the invocation's audit identity, populated today from `ProviderRunResult.session_id`, neither speculative nor successor behaviour. **No blocker was fixed, because none existed.** **Provenance note:** the approval was given in conversation and the closeout performed manually, not through `scripts/workflow-approve.sh` — no scripted `APPROVE` confirmations were typed, and none were supplied by the session. Registry state moves `IN_PROGRESS → COMPLETE`; task status moves `Current → Done`. Three new non-blocking defects (D-8, D-9, D-10) are recorded, classified, and deferred, none fixed and no GOV stage created; AUTO-010's D-3 through D-6 and AUTO-009's D1-D6 remain deferred and untouched — D-3 in particular was deliberately narrowed rather than collapsed, because `status` and `final_verdict` answer different questions. This closure authorizes no successor — AUTO-012 and every later roadmap phase remain unauthorized. Publication is limited to pushing `feature/auto-011-agent-result-contract`: no PR, no merge. | Human Owner |

## 6. Decision References
DD-01 through DD-39 (see `DECISIONS.md`; this line has historically lagged DD additions — DD-33
through DD-35 (AUTO-003), DD-36 through DD-38 (AUTO-006), and DD-39 (AUTO-007, discovered not
resolved) are the most recent). (DD-14 was appended out of physical sequence in `DECISIONS.md`; corrected by
Governance Correction Record, `docs/DECISION_LOG.md`, 2026-07-27 — DD-14 itself is unaffected and
binding. DD-15 through DD-20 record the AUTO002-F07 through F12 remediation findings, appended
`docs/DECISION_LOG.md`, 2026-07-27. DD-21 through DD-25 record the AUTO002-IR-01 through IR-05
findings of a *second* independent review, which reproduced five defects — two of them in code
DD-16/DD-17/DD-18 had reported as hardened, invalidating the F04/F05/F08/F09 completion claims as
overstated. DD-26 reclassifies F11 as `INSUFFICIENT_DURABLE_EVIDENCE`, superseding the prior
"already resolved" assertion. The IR-01..IR-05 remediation is **pending fresh independent
review**; no independent approval has been obtained for it. DD-27 through DD-31 record the
Human-Owner-authorized remediation of the third independent review's evidence-binding,
hardlink-alias, workflow-sidecar-confinement, duplicate-key, and audit-schema findings. That
remediation was subsequently accepted for closure by the Human Owner without another independent
review. DD-32 records that explicit closure decision and its no-successor/no-push/no-merge
boundary.)

## 7. Open Questions
OD-1 through OD-7 (`OPEN_QUESTIONS.md`); none block AUTO-001 closure. AUTO-002's authorization
precondition (AUTO-001 `COMPLETE` plus a fresh Human Owner record) was **satisfied and recorded**
on 2026-07-24 (§5) — this is a completed fact, not an outstanding requirement. AUTO-002's
previously-unmet execution precondition (its named branch, per §4) was satisfied on 2026-07-24
once the settled governance-recovery release procedure completed and a fresh AUTO-002 session
created the canonical branch from clean `main` (§5, "execution precondition resolved" entry);
registry state accordingly moved `BLOCKED → AUTHORIZED → IN_PROGRESS` per rule 17(a), with no new
Human Owner authorization act. On 2026-07-27 the Human Owner accepted AUTO-002 for closure and
directed `IN_PROGRESS → COMPLETE` without an additional review. AUTO-003's predecessor condition
is now satisfied, but its separate fresh Human Owner authorization is not; it remains
`NOT_STARTED`. OD-1 (GitHub auto-merge mechanism) was resolved 2026-07-28 as an AUTO-006
implementation decision (`OPEN_QUESTIONS.md`, `DECISIONS.md` DD-37). AUTO-006's own self-review
discovered and recorded a new entry, OD-10 (`allowed_environment_variables` not reaching five of
the eight `gh`-based Skill call sites in `agents/git.py`/`agents/merge.py`), `Open` and requiring
its own fix decision — it blocks nothing's authorization but blocks any real (non-fake-`gh`) run.

## 8. Future Revisions
Registry table and log grow append-only; control-rule changes are MAJOR.
