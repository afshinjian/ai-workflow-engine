# AgentOS Workflow Automation — Stage Registry

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Stage Registry |
| **Purpose** | Live status of AUTO-001..007, the stage-lifecycle state model (distinct from the runtime `WORKFLOW_STATES.md` machine the finished engine will use), master stage-control rules, and the append-only authorization log. A *view* of `docs/TASK_QUEUE.md`, never a competing workflow. |
| **Status** | Draft |
| **Version** | 6.7 |
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
| AUTO-005 | PMO, implementation, QA, Git, merge, and closeout agents | Engine implementation session | NOT_STARTED | `feature/auto-005-agents` | `stage-prompts/AUTO-005.md` |
| AUTO-006 | GitHub pull request, automatic squash merge, and closeout integration | Engine implementation session | NOT_STARTED | `feature/auto-006-pr-merge-closeout` | `stage-prompts/AUTO-006.md` |
| AUTO-007 | End-to-end dry run, recovery tests, and DASH integration | Engine implementation session (+ independent security review) | NOT_STARTED | `fix/auto-007-e2e-dry-run-recovery` | `stage-prompts/AUTO-007.md` |

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

## 6. Decision References
DD-01 through DD-32. (DD-14 was appended out of physical sequence in `DECISIONS.md`; corrected by
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
`NOT_STARTED`.

## 8. Future Revisions
Registry table and log grow append-only; control-rule changes are MAJOR.
