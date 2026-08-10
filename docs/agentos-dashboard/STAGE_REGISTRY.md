# AgentOS Dashboard — Stage Registry

| Field | Value |
|---|---|
| **Title** | AgentOS Dashboard — Stage Registry |
| **Purpose** | Live status of DASH-001..010, stage-state model, master stage-control rules, and the append-only authorization log. A *view* of the `docs/TASK_QUEUE.md` lifecycle, never a competing workflow. |
| **Status** | Draft |
| **Version** | 5.1 |
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
| DASH-004 | Local backend and dashboard shell | Dashboard implementation session | COMPLETE | `feature/dash-004-dashboard-shell` | `stage-prompts/DASH-004.md` |
| DASH-005 | Workflow board and task detail | Dashboard implementation session | COMPLETE | `feature/dash-005-board-task-detail` | `stage-prompts/DASH-005.md` |
| DASH-006 | Git, upstream, handover, consistency views | Dashboard implementation session | COMPLETE | `feature/dash-006-git-handover-views` | `stage-prompts/DASH-006.md` |
| DASH-007 | Stage registry and prompt generation | Dashboard implementation session | COMPLETE | `feature/dash-007-prompt-generation` | `stage-prompts/DASH-007.md` |
| DASH-008 | Run records, evidence, audit timeline | Dashboard implementation session | COMPLETE | `feature/dash-008-runs-evidence-audit` | `stage-prompts/DASH-008.md` |
| DASH-009 | Security hardening and failure handling | Dashboard implementation session (+ mandatory independent security review) | AUTHORIZED | `fix/dash-009-security-hardening` | `stage-prompts/DASH-009.md` |
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

| 2026-07-30 | DASH-004 | Human Owner supplied both exact `AUTHORIZE` confirmations through `scripts/workflow-authorize.sh`. Preconditions passed on the default-branch baseline at `e1817372e5b11500839bcae4b51666b19c804f57`. Registry moves `NOT_STARTED → AUTHORIZED`; implementation has not started. | Human Owner |

| 2026-07-30 | DASH-004 (initial-start preflight passed) | Dashboard implementation session. Verified: the active stage is exactly DASH-004 with registry state `AUTHORIZED`; DASH-003 is `COMPLETE`; `docs/TASK_QUEUE.md`, `docs/current_task.md`, and `docs/remaining_tasks.md` all agree (`Current`); no other task is `Current`; OD-D9 is resolved and does not gate this stage; the working branch is exactly `feature/dash-004-dashboard-shell`, created from clean `main` (GOV-AUTO-04's branch-preparation routine, run by `workflow-authorize.sh`), `git status` empty, both stashes untouched. Every precondition passed, including the named-branch check OD-D10 previously blocked DASH-002/DASH-003 on. Per §2 rule 4 the registry state moves `AUTHORIZED → IN_PROGRESS`; no new Human Owner authorization act occurs. Implementation of `agentos_dashboard/{settings.py, main.py, __main__.py, api/**, web/**}` begins under this entry. | Dashboard implementation session |

| 2026-07-30 | DASH-004 (Human Owner approval and closure) | Human Owner supplied both exact `APPROVE` confirmations through `scripts/workflow-approve.sh`, which performed the deterministic governance closeout on branch `feature/dash-004-dashboard-shell` in the same commit as the approved implementation. Registry state moves to `COMPLETE`; task status moves `Current -> Done`. This closure authorizes no successor. | Human Owner |

| 2026-08-08 | DASH-005 | Human Owner supplied both exact `AUTHORIZE` confirmations through `scripts/workflow-authorize.sh`. Preconditions passed on the default-branch baseline at `1bfa860bf2583405e2e7e4caabef52ebff771f2e`. Registry moves `NOT_STARTED → AUTHORIZED`; implementation has not started. | Human Owner |

| 2026-08-08 | DASH-005 (initial-start preflight passed) | Dashboard implementation session. Verified: the active stage is exactly DASH-005 with registry state `AUTHORIZED`; DASH-004 is `COMPLETE`; `docs/TASK_QUEUE.md`, `docs/current_task.md`, and `docs/remaining_tasks.md` all agree (`Current`); no other task is `Current`; every OD-D# is resolved and none gates this stage; the working branch is exactly `feature/dash-005-board-task-detail`, checked out at `87203a6` (the DASH-005 authorization commit) with `main` at the identical commit, `git status` empty, both pre-existing stashes untouched. Every precondition passed. Per §2 rule 4 the registry state moves `AUTHORIZED → IN_PROGRESS`; no new Human Owner authorization act occurs. Implementation of the board and task-detail views (EP-04/EP-05/EP-06, PG-02/PG-03) begins under this entry. | Dashboard implementation session |

| 2026-08-08 | DASH-005 (Human Owner approval and closure) | Human Owner supplied both exact `APPROVE` confirmations through `scripts/workflow-approve.sh`, which performed the deterministic governance closeout on branch `feature/dash-005-board-task-detail` in the same commit as the approved implementation. Registry state moves to `COMPLETE`; task status moves `Current -> Done`. This closure authorizes no successor. | Human Owner |

| 2026-08-09 | DASH-006 | Human Owner supplied both exact `AUTHORIZE` confirmations through `scripts/workflow-authorize.sh`. Preconditions passed on the default-branch baseline at `81ec25aec4490868557149db2599c347d1722647`. Registry moves `NOT_STARTED → AUTHORIZED`; implementation has not started. | Human Owner |

| 2026-08-09 | DASH-006 (initial-start preflight passed) | Dashboard implementation session. Verified: the active stage is exactly DASH-006 with registry state `AUTHORIZED`; DASH-005 is `COMPLETE`; `docs/TASK_QUEUE.md`, `docs/current_task.md`, and `docs/remaining_tasks.md` all agree (`Current`); no other task is `Current`; `OPEN_QUESTIONS.md` §Open is empty; the working branch is exactly `feature/dash-006-git-handover-views`, checked out at `5e55a05` (the DASH-006 authorization commit) with `main` at the identical commit, `git status` empty. Every precondition passed. Per §2 rule 4 the registry state moves `AUTHORIZED → IN_PROGRESS`; no new Human Owner authorization act occurs. Implementation of the Git/upstream/handover/consistency views (EP-09..EP-12, PG-07/PG-09/PG-11) begins under this entry. | Dashboard implementation session |

| 2026-08-09 | DASH-006 (scope amendment: `core/gitread.py::read_merged_branch_names`) | The implementation session extended `agentos_dashboard/core/gitread.py`, a path outside DASH-006's Allowed list, to satisfy DR-080's merged-into-target branch indication, and recorded that deviation as `DECISIONS.md` DD-14 rather than as a Human Owner authorization — self-review and Human Owner review both identified this as a real scope violation, not merely an undocumented one, since only the Human Owner may grant a path outside a stage's contracted scope (§2 rule 2). Per the Human Owner's explicit ruling recorded in `docs/DECISION_LOG.md` (2026-08-09, "Human Owner authorized a narrow DASH-006 scope amendment"), the session (1) preserved the original out-of-scope diff as evidence (`docs/reports/agentos-dashboard/evidence/DASH-006-core-gitread-scope-diff.patch`), (2) restored `core/gitread.py` to HEAD, (3) recorded this authorization here and in `docs/DECISION_LOG.md` before any further change, and (4) only then re-applied exactly the authorized `read_merged_branch_names` function and nothing else under `agentos_dashboard/core/**`. This is not a new stage authorization and does not move the registry state (already `IN_PROGRESS`); it is a scoped grant narrowing exactly one out-of-scope file addition to exactly one function, with no mutating Git capability and no new Git verb. | Human Owner |

| 2026-08-09 | DASH-006 (Human Owner approval and closure) | Human Owner supplied both exact `APPROVE` confirmations through `scripts/workflow-approve.sh`, which performed the deterministic governance closeout on branch `feature/dash-006-git-handover-views` in the same commit as the approved implementation. Registry state moves to `COMPLETE`; task status moves `Current -> Done`. This closure authorizes no successor. | Human Owner |

| 2026-08-10 | DASH-007 | Human Owner supplied both exact `AUTHORIZE` confirmations through `scripts/workflow-authorize.sh`. Preconditions passed on the default-branch baseline at `92fb3e0ace48f7ce34cea8b53f49d48e5f63889a`. Registry moves `NOT_STARTED → AUTHORIZED`; implementation has not started. | Human Owner |

| 2026-08-10 | DASH-007 (initial-start preflight passed) | Dashboard implementation session. Verified: the active stage is exactly DASH-007 with registry state `AUTHORIZED`; DASH-006 is `COMPLETE`; `docs/TASK_QUEUE.md`, `docs/current_task.md`, and `docs/remaining_tasks.md` all agree (`Current`); no other task is `Current`; `OPEN_QUESTIONS.md` §Open is empty; the working branch is exactly `feature/dash-007-prompt-generation`, checked out at `089750f` (the DASH-007 authorization commit) with `main` at the identical commit, `git status` empty. Every precondition passed. Per §2 rule 4 the registry state moves `AUTHORIZED → IN_PROGRESS`; no new Human Owner authorization act occurs. Implementation of the stage-registry loader, precondition engine, gated prompt generation (EP-13/EP-14/EP-21, PG-04), and the governance browser/search surface (EP-07/EP-08, PG-08, added by PLAN-001) begins under this entry. | Dashboard implementation session |

| 2026-08-10 | DASH-007 (Human Owner approval and closure) | Human Owner supplied both exact `APPROVE` confirmations through `scripts/workflow-approve.sh`, which performed the deterministic governance closeout on branch `feature/dash-007-prompt-generation` in the same commit as the approved implementation. Registry state moves to `COMPLETE`; task status moves `Current -> Done`. This closure authorizes no successor. | Human Owner |

| 2026-08-10 | DASH-008 | Human Owner supplied both exact `AUTHORIZE` confirmations through `scripts/workflow-authorize.sh`. Preconditions passed on the default-branch baseline at `c664fcb58d3fae64877ce04020e4d0dbcdc961a6`. Registry moves `NOT_STARTED → AUTHORIZED`; implementation has not started. | Human Owner |

| 2026-08-10 | DASH-008 (initial-start preflight passed) | Dashboard implementation session. Verified: the active stage is exactly DASH-008 with registry state `AUTHORIZED`; DASH-007 is `COMPLETE`; `docs/TASK_QUEUE.md`, `docs/current_task.md`, and `docs/remaining_tasks.md` all agree (`Current`); no other task is `Current`; `OPEN_QUESTIONS.md` §Open is empty; the working branch is exactly `feature/dash-008-runs-evidence-audit`, checked out at `7277943` (the DASH-008 authorization commit) with `main` at the identical commit, `git status` empty. Every precondition passed. Per §2 rule 4 the registry state moves `AUTHORIZED → IN_PROGRESS`; no new Human Owner authorization act occurs. Implementation of the local `dashboard.db` storage layer, the run/approval/finding/note/audit/orchestration services, routes (EP-15, EP-16, EP-17, EP-18, EP-22, EP-23), and templates (PG-05/PG-06/PG-10) begins under this entry. | Dashboard implementation session |

| 2026-08-10 | DASH-008 (Human Owner approval and closure) | Human Owner supplied both exact `APPROVE` confirmations through `scripts/workflow-approve.sh`, which performed the deterministic governance closeout on branch `feature/dash-008-runs-evidence-audit` in the same commit as the approved implementation. Registry state moves to `COMPLETE`; task status moves `Current -> Done`. This closure authorizes no successor. | Human Owner |

| 2026-08-10 | DASH-009 | Human Owner supplied both exact `AUTHORIZE` confirmations through `scripts/workflow-authorize.sh`. Preconditions passed on the default-branch baseline at `c871459ecc7b65fe307fa56a1ee823dbcd5b3bbd`. Registry moves `NOT_STARTED → AUTHORIZED`; implementation has not started. | Human Owner |

## 5. Stage→Requirement Map

**Revised 2026-08-10 (PLAN-001).** Superseded the prior prose-range form below, which hid
individual IDs (most visibly: DR-090/DR-091/EP-07/EP-08/PG-08 had no stage at all; DR-121/DR-122
had no final owner; EP-18/PG-12 were never mapped). Every DR/EP/PG in this table has **exactly
one** normative delivery/evidence owner, except where explicitly marked `foundation` (an earlier
stage's infrastructure contribution, not final ownership) or `final` (the stage that owns
cross-page verification/evidence closure, distinct from — and not contradicted by — the
page-delivering stages that implement the underlying control locally as they build each page).
Rationale: `DECISIONS.md` DD-16; `docs/DECISION_LOG.md` 2026-08-10 entry.

| Stage | Delivery/evidence-owned requirements |
|---|---|
| DASH-002 | adapters underpinning all DRs (no requirement IDs of its own — read-only Git/file adapters, snapshot builder) |
| DASH-003 | none as final owner — `foundation` only for DR-120, DR-121, DR-122 (tolerant parsers + consistency engine v1; final ownership below) |
| DASH-004 | DR-010, DR-011, DR-012, DR-013, DR-123 · EP-01, EP-02, EP-03, EP-20 · PG-01 |
| DASH-005 | DR-020, DR-021, DR-022, DR-023, DR-030, DR-031, DR-032, DR-033 · EP-04, EP-05, EP-06 · PG-02, PG-03 |
| DASH-006 | DR-080, DR-081, DR-082, DR-083, DR-100, DR-101, DR-102, **DR-120 (sole delivery owner)** · EP-09, EP-10, EP-11, EP-12 · PG-07, PG-09, PG-11 |
| DASH-007 | DR-040, DR-041, DR-042, DR-043, **DR-090, DR-091** · EP-13, EP-14, EP-21, **EP-07, EP-08** · PG-04, **PG-08** |
| DASH-008 | DR-050, DR-051, DR-052, DR-060, DR-061, DR-062, DR-070, DR-071, DR-110, DR-111 · EP-15, EP-16, EP-17, EP-22, EP-23, **EP-18** · PG-05, PG-06, PG-10 |
| DASH-009 | SC-01..SC-36 final reconciliation/verification (each stage above implements its own baseline controls in-line; DASH-009 owns the mandatory independent adversarial reconciliation) |
| DASH-010 | **DR-121 (final: staleness/banner behavior across every delivered page), DR-122 (final: file/line provenance and raw fallback across every delivered page)** · **PG-12** · MVP acceptance |

Bold marks the DR-090/DR-091/EP-07/EP-08/PG-08 → DASH-007, EP-18 → DASH-008, and DR-121/DR-122/
PG-12 → DASH-010 corrections made by PLAN-001. Every other assignment preserves either the
prior DR mapping or the pre-PLAN stage contracts; the explicit EP/PG rows make those existing
contract assignments visible in this registry for the first time. Deferred, outside MVP, no stage
owner: DR-900..DR-912 (`../PRODUCT_SPEC.md` §4) — unchanged, no scope silently deferred by this
revision.

<details><summary>Prior form (superseded 2026-08-10, retained for audit trail)</summary>

DASH-002 → adapters underpinning all DRs · DASH-003 → DR-120..122 foundations · DASH-004 →
DR-010..013, DR-123 (formerly blocked on OD-D9; resolved 2026-07-29) · DASH-005 → DR-020..033 ·
DASH-006 → DR-080..083,
DR-100..102, DR-120 · DASH-007 → DR-040..043 · DASH-008 → DR-050..071, DR-110..111 ·
DASH-009 → SC-01..36 verification · DASH-010 → MVP acceptance.

</details>

## 6. Decision References
DD-01, DD-02, DD-03, DD-16 (§5 requirement-ownership correction, PLAN-001).

## 7. Open Questions
OD-D1 is resolved (see `OPEN_QUESTIONS.md`). OD-D9, which had to be resolved before DASH-004
authorization, is resolved 2026-07-29 (`DECISIONS.md` DD-09) — that precondition is satisfied, and
DASH-004 authorization now needs only DASH-003 `COMPLETE` (it is) plus a fresh Human Owner record,
like any other stage. DASH-002 authorization required DASH-001 `COMPLETE` plus a fresh Human Owner
record.

## 8. Future Revisions
Registry table and log grow append-only; control-rule changes are MAJOR.
