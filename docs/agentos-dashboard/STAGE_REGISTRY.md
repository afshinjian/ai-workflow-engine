# AgentOS Dashboard — Stage Registry

| Field | Value |
|---|---|
| **Title** | AgentOS Dashboard — Stage Registry |
| **Purpose** | Live status of DASH-001..010, stage-state model, master stage-control rules, and the append-only authorization log. A *view* of the `docs/TASK_QUEUE.md` lifecycle, never a competing workflow. |
| **Status** | Draft |
| **Version** | 5.0 |
| **Owner** | Documentation & Governance session · Human Owner (approval and stage authorization) |
| **Dependencies** | `MASTER_PLAN.md` §4; `MVP_SCOPE.md`; `TEST_STRATEGY.md` |
| **Related Documents** | `stage-prompts/README.md`, `docs/AGENT_PROTOCOL.md`, `self-governance.yaml` |

## Table of Contents
1. State Model · 2. Control Rules · 3. Registry · 4. Authorization Log ·
5. Stage→Requirement Map · 6. Decision References · 7. Open Questions · 8. Future Revisions

## 1. State Model

Per-stage states: `NOT_STARTED → PROPOSED → AUTHORIZED → IN_PROGRESS → SELF_REVIEW → REVIEW →
APPROVAL → COMPLETE`, plus `BLOCKED` and `SUPERSEDED`. Mapping to the stage's task in
`docs/TASK_QUEUE.md` (which knows exactly three statuses — no fourth is added): `AUTHORIZED`/
`IN_PROGRESS`/`SELF_REVIEW`/`REVIEW`/`APPROVAL`/`BLOCKED` ≈ `Current`; `NOT_STARTED`/`PROPOSED` ≈
`Planned`; `COMPLETE`/`SUPERSEDED` ≈ `Done`. `BLOCKED` is explicitly `Current`, never `Planned`
and never a loss of authorization (rule 18). `COMPLETE` and `SUPERSEDED` both map to `Done` but
are never interchangeable: `SUPERSEDED` means administratively closed (abandoned/replaced on
Human Owner directive), never successful completion — `docs/TASK_QUEUE.md`'s prose must say so
explicitly for that task (Human Owner policy decision, OD-8, mirroring
`docs/workflow-automation/STAGE_REGISTRY.md` rule 9, resolved 2026-07-24). A stage's registry
state can never be more advanced than its task's
status in `docs/TASK_QUEUE.md`, and at most one DASH task is `Current` at a time
(`self-governance.yaml` `maximum_current_tasks: 1`). This state model is identical to
`docs/workflow-automation/STAGE_REGISTRY.md` (the AUTO program's equivalent registry). Of §2's
control rules: rules 1–13 and 15–20 are identical in substance to AUTO's rules 1–13 and 14–19
respectively (that document carries the fuller worked rationale for several; where this registry
states one more briefly, it is a restatement, not a different rule — verified rule-by-rule on
audit, including a real gap found and fixed in rule 17's closeout criteria, which had omitted the
`git`-check tolerance AUTO's rule 16 states). **Rule 14 (Rollback) is DASH-specific, with no AUTO
counterpart** — it concerns `dashboard.db`, an artifact that has no equivalent in the AUTO
program, which persists no local database. This is the one intentional, documented substantive
difference between the two registries' rule sets; any other divergence found on audit is a
defect, not a design choice, and is corrected rather than left standing.

## 2. Control Rules

1. **Authorization preconditions:** predecessor `COMPLETE`; registry and `docs/TASK_QUEUE.md`
   agree; no other DASH stage active; no other `Current` task in the queue; clean tree (defined
   below); blocking OD-D# resolved.

   **Definition of "clean tree":** no uncommitted change other than the sanctioned
   predecessor-closeout/successor-authorization edit set itself — `docs/TASK_QUEUE.md` and its
   mirrors (`docs/current_task.md`, `docs/remaining_tasks.md`), `docs/PROJECT_STATE.md` (prose
   only), `docs/DECISION_LOG.md` (new entry), `docs/CHANGELOG.md` (new entry), this registry's §3
   state cells and §4 Authorization Log (new row), and this program's own changelog if it has one
   — never a violation of this precondition, since recording "predecessor `COMPLETE`, successor
   `Current`" is necessarily that exact diff. Any *other* uncommitted change does violate it. Full
   rationale and the DASH-001→AUTO-001 evidence: `docs/workflow-automation/STAGE_REGISTRY.md` §3
   rule 1, which this rule mirrors.
2. **Authorizer:** only the Human Owner.
3. **Required language:** a written record — "I authorize DASH-0XX" (or an equivalent explicit
   directive) — captured in the stage's task record and §4 before work.
4. **Starting:** the assigned agent verifies the SSP initial-start preflight; task `Planned → Current`
   (promotion requires the owner authorization per `self-governance.yaml`
   `require_designer_approval_for_promotion`); registry `AUTHORIZED → IN_PROGRESS`.
5. **Retry after failure:** stage stays `IN_PROGRESS`; fixes within scope only; all gates rerun;
   failed results preserved in the report.
6. **Review return:** `REVIEW → IN_PROGRESS` with findings preserved; every review round after
   the first uses a fresh reviewer with no memory of prior rounds (`docs/AGENT_PROTOCOL.md`);
   repeat review reruns all contract gates.
7. **Approval return:** `APPROVAL → IN_PROGRESS`; findings recorded; approval names the exact
   diff/commit.
8. **Amending a completed stage:** as `docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 8
   states in full (mirrored here): completion records (this registry's §3 state/branch facts,
   §4 Authorization Log rows, stage completion reports, `docs/DECISION_LOG.md` entries) are frozen
   — corrected only via a Governance Correction Record (rule 19), never in place. Versioned
   reference/control documents a stage happened to deliver (this registry, `stage-prompts/*.md`,
   `OPEN_QUESTIONS.md`) each carry their own `Version` field precisely because they are living
   documents; amending their content in place, with a version bump and a logged rationale, is
   normal maintenance, not a violation — provided it is a documentation-correctness or clarity fix
   that does not rewrite what a stage's completion record says it did. Substantive re-litigation
   of a completed stage's actual decisions remains a new linked task either way.
9. **Superseding:** as `docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 9 states in full
   (mirrored here): an explicit Human Owner directive moves a stage to `SUPERSEDED`, recorded
   with a successor reference, history append-only. Legal source states: `AUTHORIZED`,
   `BLOCKED`, `IN_PROGRESS`, `SELF_REVIEW`, `REVIEW`, `APPROVAL` — never `NOT_STARTED`/`PROPOSED`
   (ordinary `docs/TASK_QUEUE.md` maintenance instead) or `COMPLETE` (rule 8 forbids it). Maps to
   task status `Done` (§1), administratively closed, never successful completion. Never
   automatically authorizes or starts a successor — a successor requires its own independent
   task record and its own fresh, explicit Human Owner authorization (rules 1–3), exactly as
   rule 17 already establishes for ordinary closeout.
10. **Early-start prevention:** the prompt generator refuses stage N+1 until N is `COMPLETE`
    **and** fresh authorization is recorded; the SSP orders the agent to stop; sole-active
    checks flag violations.
11. **Documentation reconciliation:** a stage closes only after `docs/PROJECT_STATE.md`, the
    task queue and its mirrors (`workflowctl check-task-state` green), this registry, and the
    stage report agree.
12. **Evidence before completion:** report complete per template; all validation results
    recorded; scope audit clean; every acceptance criterion individually PASS.
13. **Closing:** commit and merge per rules 15–16; post-merge closeout updates mirrors;
    registry `COMPLETE`; task `Done`; then STOP.
14. **Rollback:** revert the stage's exact commit(s); dashboard.db never blocks rollback.
15. **Branches:** one stage = one branch, named per the registry table, created from current
    `main` (the configured default branch), never from another stage branch.
16. **Merges:** one merge per stage into `main`, performed by the Human Owner. Commits and any
    push are human-gated per `docs/AGENT_PROTOCOL.md`; the approval-gated
    `workflowctl commit` / `push` gates may be used but a plain human-run Git command with
    explicit approval is equally valid.
17. **Closeout:** merge commit recorded in the task record; task flips to `Done` only after
    post-merge consistency checks (`workflowctl verify --config self-governance.yaml`). At
    closeout, `task-state`, `governance`, and `handover` must each PASS with no exception; `git`
    must also PASS unless its only finding is a pre-existing, already-documented condition
    unrelated to the stage's own merge (e.g. `upstream_missing` on a branch never intended to be
    pushed) — the same tolerance the SSP applies mid-stage; a `git` finding caused by the stage's
    own merge is never tolerated (this is one shared `self-governance.yaml`/`workflowctl verify`
    surface across both programs, so this clause is identical in substance to AUTO's, not merely
    similar). No successor is *automatically* selected as a consequence of closeout — every promotion to
    `Current` still requires its own distinct, explicit Human Owner authorization (rule 3), never
    inferred from the closeout alone. When a precondition check for the next stage finds a
    predecessor still `Current` (as happened at DASH-001→AUTO-001, `docs/DECISION_LOG.md`
    2026-07-23 entry), the Human Owner may resolve both the predecessor's closeout and the
    successor's authorization in one written directive without violating this rule, provided the
    directive is explicit for each — this rule forbids automatic/agent-initiated chaining, not an
    explicit human decision that happens to cover both in one session. Full rationale:
    `docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 16, which this rule mirrors.
18. **Execution-precondition failure vs. authorization:** if a stage's execution precondition
    (its named branch, or any other SSP pre-flight check) fails after authorization but before
    `IN_PROGRESS`, the authorization is **not** invalidated; registry state moves to `BLOCKED`
    (§1), task status stays `Current`. The only legal exits are `BLOCKED → AUTHORIZED`
    (precondition resolved, then rule 4's normal "Starting" step — no re-authorization) or
    `BLOCKED → SUPERSEDED` (Human Owner directive, rule 9). No other transition out of `BLOCKED`
    is legal. Full rationale: `docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 17, which this
    rule mirrors.
19. **Governance Correction Record:** the formal, append-only-compliant mechanism for fixing a
    wrong governance record without editing it in place — a new, dated entry stating what it
    corrects, what was wrong, and the corrected fact, appended (never overwriting) to this
    registry's §4 or to `docs/DECISION_LOG.md`. Full definition:
    `docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 18, adopted here by reference rather than
    duplicated, so the two programs' registries cannot drift on this shared mechanism's definition.
20. **Resume preflight:** a session resuming a stage whose registry state is `IN_PROGRESS`,
    `SELF_REVIEW`, `REVIEW`, or `APPROVAL` re-verifies the same execution preconditions that
    applied at initial start, but never requires the stage to return to `AUTHORIZED`. If
    re-verification passes, work continues with no registry transition and no re-authorization.
    If it fails, the session stops and reports the exact failure to the Human Owner; registry
    state remains unchanged and is not moved to `BLOCKED`, which rule 18 reserves for execution-
    precondition failure before `IN_PROGRESS`. This is the Dashboard restatement of
    `docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 19, required by §1's existing
    substantive-equivalence rule; it adds no state or transition.

## 3. Registry

Report paths: `docs/reports/agentos-dashboard/STAGE-XX-completion.md`.

| Stage | Title | Role | State | Branch | Prompt |
|---|---|---|---|---|---|
| DASH-001 | Planning foundation and dashboard contracts | Documentation & Governance session | COMPLETE | `governance/dash-001-documentation` | `stage-prompts/DASH-001.md` |
| DASH-002 | Repository adapter and read-only snapshot | Dashboard implementation session | COMPLETE | `feature/dash-002-repo-adapter` | `stage-prompts/DASH-002.md` |
| DASH-003 | Governance and Markdown parsing | Dashboard implementation session | COMPLETE | `feature/dash-003-governance-parsing` | `stage-prompts/DASH-003.md` |
| DASH-004 | Local backend and dashboard shell | Dashboard implementation session | NOT_STARTED | `feature/dash-004-dashboard-shell` | `stage-prompts/DASH-004.md` |
| DASH-005 | Workflow board and task detail | Dashboard implementation session | NOT_STARTED | `feature/dash-005-board-task-detail` | `stage-prompts/DASH-005.md` |
| DASH-006 | Git, upstream, handover, consistency views | Dashboard implementation session | NOT_STARTED | `feature/dash-006-git-handover-views` | `stage-prompts/DASH-006.md` |
| DASH-007 | Stage registry and prompt generation | Dashboard implementation session | NOT_STARTED | `feature/dash-007-prompt-generation` | `stage-prompts/DASH-007.md` |
| DASH-008 | Run records, evidence, audit timeline | Dashboard implementation session | NOT_STARTED | `feature/dash-008-runs-evidence-audit` | `stage-prompts/DASH-008.md` |
| DASH-009 | Security hardening and failure handling | Dashboard implementation session (+ mandatory independent security review) | NOT_STARTED | `fix/dash-009-security-hardening` | `stage-prompts/DASH-009.md` |
| DASH-010 | Integration testing, documentation, release readiness | Dashboard implementation session | NOT_STARTED | `feature/dash-010-release-readiness` | `stage-prompts/DASH-010.md` |

## 4. Authorization Log (append-only)

| Date | Stage | Authorization record | Recorded by |
|---|---|---|---|
| 2026-07-23 | DASH-001 | Human Owner: "I authorize DASH-001." Original planning-session authorization. The resulting execution was mistakenly performed in a different repository and is void for `ai-workflow-engine`; superseded by the recovery record below. | Documentation & Governance session |
| 2026-07-23 | DASH-001 (recovery) | Human Owner: "I authorize recovery and correct execution of DASH-001 in the ai-workflow-engine repository." Preconditions verified (branch `governance/dash-001-documentation`; the copied documentation treated as candidate material only; commit/push/merge prohibited; DASH-002+ not authorized). | Documentation & Governance session |

| 2026-07-29 | DASH-002 | Human Owner supplied both exact `AUTHORIZE` confirmations through `scripts/workflow-authorize.sh`. Preconditions passed on the default-branch baseline at `5a111563a6bcec4c86d32e08efcfd3946f693eb6`. Registry moves `NOT_STARTED → AUTHORIZED`; implementation has not started. | Human Owner |
| 2026-07-29 | DASH-002 (initial-start preflight: branch precondition unmet, implemented on `main`) | Dashboard implementation session. Verified: the active stage is exactly DASH-002 with registry state `AUTHORIZED`; DASH-001 is `COMPLETE`; `docs/TASK_QUEUE.md`, `docs/current_task.md`, and `docs/remaining_tasks.md` all agree (`Current`); no other task is `Current`; OD-D9 does not gate this stage; `main` clean at `729f746` (the DASH-002 authorization commit itself), `git status` empty, both stashes untouched. **The named-branch precondition (§2 rules 4 and 15) was not met and was not resolved**: the local runner prompt this session was launched with (`scripts/prompts/implement-next-task.md` §7) explicitly forbids creating or switching branches, so `feature/dash-002-repo-adapter` was not created; the stage was implemented on `main` in the working tree, uncommitted. Recorded as OD-D10 for a Human Owner decision. Registry state is therefore left at `AUTHORIZED` — **not** advanced to `IN_PROGRESS`, which would assert a preflight that did not pass, and not moved to `BLOCKED` (§2 rule 18), which would assert that no work was done. The Human Owner's authorization above stands unchanged and is unaffected either way. Report: `docs/reports/agentos-dashboard/STAGE-02-completion.md`. | Dashboard implementation session |

| 2026-07-29 | DASH-002 (Human Owner approval and closure) | Human Owner supplied both exact `APPROVE` confirmations through `scripts/workflow-approve.sh`, which performed the deterministic governance closeout on branch `feature/dash-002-repo-adapter` in the same commit as the approved implementation. Registry state moves to `COMPLETE`; task status moves `Current -> Done`. This closure authorizes no successor. | Human Owner |

| 2026-07-29 | DASH-003 | Human Owner supplied both exact `AUTHORIZE` confirmations through `scripts/workflow-authorize.sh`. Preconditions passed on the default-branch baseline at `f80919793cfb7776f094733484c837833995e23a`. Registry moves `NOT_STARTED → AUTHORIZED`; implementation has not started. | Human Owner |

| 2026-07-29 | DASH-003 (initial-start preflight: branch precondition unmet, implemented on `main`) | Dashboard implementation session. Verified: the active stage is exactly DASH-003 with registry state `AUTHORIZED`; DASH-002 is `COMPLETE`; `docs/TASK_QUEUE.md`, `docs/current_task.md`, and `docs/remaining_tasks.md` all agree (`Current`); no other task is `Current`; no OD-D# blocks this stage; `main` clean at `651e53e` (the DASH-003 authorization commit itself), `git status` empty, both stashes untouched (this working copy holds none, per the pre-existing document/reality disagreement DASH-002's report already recorded). **The named-branch precondition (§2 rules 4 and 15) recurred exactly as OD-D10 describes**: the local runner prompt this session was launched with forbids creating or switching branches, so `feature/dash-003-governance-parsing` was not created; the stage was implemented on `main` in the working tree, uncommitted. Registry state is therefore left at `AUTHORIZED` — **not** advanced to `IN_PROGRESS`, which would assert a preflight that did not pass, and not moved to `BLOCKED` (§2 rule 18), which would assert that no work was done. The Human Owner's authorization above stands unchanged. Report: `docs/reports/agentos-dashboard/STAGE-03-completion.md`. | Dashboard implementation session |

| 2026-07-29 | DASH-003 (Human Owner approval and closure) | Human Owner supplied both exact `APPROVE` confirmations through `scripts/workflow-approve.sh`, which performed the deterministic governance closeout on branch `feature/dash-003-governance-parsing` in the same commit as the approved implementation. Registry state moves to `COMPLETE`; task status moves `Current -> Done`. This closure authorizes no successor. | Human Owner |

## 5. Stage→Requirement Map

DASH-002 → adapters underpinning all DRs · DASH-003 → DR-120..122 foundations · DASH-004 →
DR-010..013, DR-123 (formerly blocked on OD-D9; resolved 2026-07-29) · DASH-005 → DR-020..033 ·
DASH-006 → DR-080..083,
DR-100..102, DR-120 · DASH-007 → DR-040..043 · DASH-008 → DR-050..071, DR-110..111 ·
DASH-009 → SC-01..36 verification · DASH-010 → MVP acceptance.

## 6. Decision References
DD-01, DD-02, DD-03.

## 7. Open Questions
OD-D1 is resolved (see `OPEN_QUESTIONS.md`). OD-D9, which had to be resolved before DASH-004
authorization, is resolved 2026-07-29 (`DECISIONS.md` DD-09) — that precondition is satisfied, and
DASH-004 authorization now needs only DASH-003 `COMPLETE` (it is) plus a fresh Human Owner record,
like any other stage. DASH-002 authorization required DASH-001 `COMPLETE` plus a fresh Human Owner
record.

## 8. Future Revisions
Registry table and log grow append-only; control-rule changes are MAJOR.
