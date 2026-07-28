# Project Handover

Narrative context transfer between sessions. This file is checksum-verified by
`handover/PROJECT_CHECKSUM.md`; cross-check its claims against Git and the configured validation
commands.

## Where things stand (2026-07-28)

The released `ai-workflow-engine` 1.0.0 roadmap is complete. In the post-1.0 programs:

- DASH-001 is `Done`; DASH-002..DASH-010 remain `Planned`.
- AUTO-001, AUTO-002, AUTO-003, and AUTO-004 are `Done` and registry `COMPLETE`. All four are
  merged into `main`.
- GOV-AUTO-01 is `Done` — committed as `a302c95`, merged via `a3b5b0a`.
- **AUTO-005 — Agents is `Current`**, registry `IN_PROGRESS`, implemented, validated, and
  **approved by the Human Owner on 2026-07-28**, who accepted every documented limitation and
  authorized exactly one local commit on `feature/auto-005-agents` — the commit this handover is
  part of. Push and merge were explicitly withheld, so the branch is unpushed and unmerged, and
  the stage stays `IN_PROGRESS`/`Current`: approval of the implementation is not closure.
- AUTO-006 and AUTO-007 remain `Planned`/`NOT_STARTED`. **AUTO-006 is explicitly not authorized.**
- GOV-2 and GOV-3 remain `Planned`, each needing its own authorization.

## What happened on 2026-07-28

One Human Owner decision did three things, in order, and the order matters:

1. **Approved and closed AUTO-004**, recording commit `84616d5`. Its completion report was **not**
   rewritten — that report's "no commit was performed" statement was accurate when written, and the
   commit came afterwards. The commit, approval, and merge are recorded in a new append-only
   addendum at the end of it, a new `STAGE_REGISTRY.md` §5 row, and `docs/DECISION_LOG.md`
   (§3 rule 8).
2. **Published AUTO-004**: the governance closure records were committed as `4659172`, the branch
   was pushed, and `main` moved `a3b5b0a → 4721f9a` by a no-fast-forward merge (parents `a3b5b0a` +
   `4659172`). `main` was pushed. The stage branch was **retained**, not deleted.
3. **Authorized AUTO-005**, explicitly conditioned on step 2 succeeding. It did — all four
   `workflowctl verify` checks returned PASS on `main` — so `feature/auto-005-agents` was created
   from that clean, synchronized `main` and AUTO-005 became the single `Current` task.

This was the fifth predecessor-still-`Current` conflict this repository has hit. It was handled the
same way as the previous four: the session detected it, made no change, and reported it; the Human
Owner decided both halves explicitly (`STAGE_REGISTRY.md` §3 rule 16).

## Current Git state

| Fact | Value |
|---|---|
| Branch | `feature/auto-005-agents` |
| Created from | clean `main` at `4721f9a` |
| Upstream | **none** — this branch has never been pushed |
| HEAD before this commit | `4721f9a` (the AUTO-004 merge on `main`) |
| Stashes | `stash@{0}`, `stash@{1}` — both untouched since before AUTO-002 |

`main` is at `4721f9a` and matches `origin/main`. `feature/auto-004-model-providers` exists locally
and on `origin` and must not be deleted — the Human Owner's decision retained it explicitly.

`workflowctl check-git` reports `upstream_missing` on the AUTO-005 branch. Expected and
pre-existing for a stage branch never intended to be pushed (`STAGE_REGISTRY.md` §3 rule 16; the
SSP). Every other configured check passes. On `main`, all four checks pass.

## AUTO-005 — current state

Delivered the six Agents in `agentos_workflow/agents/` (`AGENT_CONTRACTS.md` §2-7):

- `__init__.py` — the capability primitives: `AgentResult` (which has **no** state field, so an
  Agent deciding its own transition is unrepresentable), the `CapabilityBroker`, the per-Agent
  Skill/Provider contract tables, the live provider gateway, and the two **Orchestrator-owned**
  sequences §8 says are not Agents: `run_deterministic_validation` (`MACHINE_GATES.md` §3) and
  `run_repair_loop` (`FAILURE_RECOVERY.md` §1-2).
- `pmo.py` — every Precondition Gate check, reported together; the contract-hash comparison catches
  a stage contract edited after authorization; branch name and base SHA come from the authorization
  record, never the contract.
- `implementation.py` — implement and repair; the provider's `files_changed` is a claim, and the
  truth is derived from Git independently.
- `qa.py` — independent QA; cannot read the implementation report (the Skill is not in its
  capability set) and refuses to let a QA pass override a failed deterministic gate.
- `git.py`, `merge.py`, `closeout.py` — commit/push/PR, the merge-safety gate (head SHA verified
  *before* the merge is enabled, no admin path in executable code), and closeout (no destructive
  step without a `MergeConfirmation` bound to its own branch; baseline restored first).

The eight GitHub-facing Skills belong to AUTO-006 and are **named but unbound**: reaching for one
fails as `SKILL_UNAVAILABLE` naming AUTO-006 rather than returning a fabricated success.

Validation: 133 focused tests, 1,465 in `agentos_workflow` (from 1,332), 1,037 in `tests/`
(collection unchanged); ruff, black, mypy, and `pre-commit` clean; `git diff --check` clean. Full
detail: `docs/reports/workflow-automation/AUTO-005-completion-report.md`.

The Human Owner approved this implementation on 2026-07-28 and authorized **exactly one local
commit**, which is the commit containing this file. Push, merge, branch switching, upstream
changes, stash changes, and beginning AUTO-006 were all explicitly prohibited, and none was
performed.

## Known open items

- **QA report artifacts collide within one workflow.** `generate_qa_report` allows one
  `reports/qa.json` per workflow identifier, but a repair loop runs up to four different QA rounds.
  AUTO-005 works around it with a per-attempt audit scope, because `skills/**` is outside its
  allowed paths. The Human Owner accepted this for AUTO-005 and directed it be tracked as explicit
  future work: **GOV-3 — Attempt-aware report artifact naming in the Reporting Skills**
  (`docs/TASK_QUEUE.md`, `Planned`, needs its own authorization).
- **The Git/GitHub Skill call shapes are AUTO-005's proposal**, exercised against fakes and
  unverified against AUTO-006's eventual signatures.
- **`detect_future_stage_work` needs a later-stage path map** that no configuration field supplies;
  with the default empty map the check passes trivially. Worth an explicit wiring decision.
- **The Agents are not yet driven by the Orchestrator's state machine** — that wiring is outside
  this stage's allowed files and belongs to AUTO-007.

## Next session

1. Verify `git status`, recent history, and this handover checksum.
2. Confirm AUTO-005 is the only `Current` task.
3. AUTO-005's implementation is approved and committed, but the stage is **not closed** — closure
   (`IN_PROGRESS → COMPLETE`, `Current → Done`) is a separate Human Owner act.
4. Publication decisions remain open and unauthorized: pushing or merging this branch, and anything
   to do with AUTO-006.
5. Never delete either stash, and never delete `feature/auto-004-model-providers`.

Completing a task never authorizes its successor. AUTO-006 requires its own fresh written
authorization naming it.
