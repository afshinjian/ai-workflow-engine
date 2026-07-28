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
- **AUTO-005 is `Done`** and registry `COMPLETE` as of 2026-07-28 — implemented, validated,
  approved, committed as `430cbb4`, and merged into `main` under the same decision.
- AUTO-006 and AUTO-007 remain `Planned`/`NOT_STARTED`. **AUTO-006 is explicitly not authorized** —
  the closure decision said so in terms.
- GOV-2 and GOV-3 remain `Planned`, each needing its own authorization. **GOV-3** was created on
  2026-07-28 to carry the QA report artifact collision AUTO-005 found and worked around.
- **GOV-AUTO-02 is `Done`** as of 2026-07-28 — implemented, validated, approved, and committed as
  `d212e4d2dae2cd0a3510c54d7cd098fdfd5da548`. Report:
  `docs/reports/GOV-AUTO-02-completion-report.md`.

No task is `Current`. No successor is authorized. AUTO-006, GOV-3, and DASH-002 remain `Planned`.

## What happened on 2026-07-28

Two AUTO stages were closed and merged on the same day. The **AUTO-005** sequence came second:
approve the implementation and authorize exactly one commit (`430cbb4`); then, separately, approve
closure and publication — governance records committed on their own, branch pushed, merged into
`main`, `main` pushed, stage branch retained, stashes untouched, AUTO-006 explicitly not
authorized. The QA report artifact collision AUTO-005 disclosed was **recorded as GOV-3 rather than
fixed**, so `agentos_workflow/skills/**` stayed byte-unchanged.

The **AUTO-004** sequence came first, and one Human Owner decision did three things in order:

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
| Baseline | `main` and `origin/main` matched at GOV-AUTO-02 implementation commit `d212e4d2dae2cd0a3510c54d7cd098fdfd5da548` before closure |
| Current local state | one governance-only GOV-AUTO-02 closure commit ahead of `origin/main`; not pushed or merged |
| GOV-AUTO-02 implementation commit | `d212e4d2dae2cd0a3510c54d7cd098fdfd5da548`, approved and closed |
| AUTO-005 implementation commit | `430cbb4`, merged |
| Stage branches | `feature/auto-004-model-providers` and `feature/auto-005-agents` — both pushed and **retained**; neither may be deleted |
| Stashes | `stash@{0}`, `stash@{1}` — both untouched since before AUTO-002 |

The GOV-AUTO-02 implementation and validation are recorded in
`docs/reports/GOV-AUTO-02-completion-report.md`. Its closure changes governance and handoff
records only. A stage branch created later and not yet pushed will produce the pre-existing
`upstream_missing` finding — the tolerance `STAGE_REGISTRY.md` §3 rule 16 and the SSP both name.

## AUTO-005 — what was delivered

The six Agents in `agentos_workflow/agents/` (`AGENT_CONTRACTS.md` §2-7):

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

Approved, committed as `430cbb4`, closed to `Done`/`COMPLETE`, and merged into `main` — all on
2026-07-28, under two separate Human Owner decisions (approval, then closure and publication).

## Known open items

- **QA report artifacts collide within one workflow** — tracked as **GOV-3** (`docs/TASK_QUEUE.md`,
  `Planned`, unauthorized). `generate_qa_report` allows one `reports/qa.json` per workflow
  identifier, but a repair loop runs up to four different QA rounds. AUTO-005 works around it with
  a per-attempt audit scope because `skills/**` was outside its allowed paths; the Human Owner
  accepted that for the stage and directed the real fix — an attempt-aware artifact name — be
  deferred rather than absorbed into AUTO-005's scope.
- **The Git/GitHub Skill call shapes are AUTO-005's proposal**, exercised against fakes and
  unverified against AUTO-006's eventual signatures.
- **`detect_future_stage_work` needs a later-stage path map** that no configuration field supplies;
  with the default empty map the check passes trivially. Worth an explicit wiring decision.
- **The Agents are not yet driven by the Orchestrator's state machine** — that wiring is outside
  this stage's allowed files and belongs to AUTO-007.

## Next session

1. Verify `git status`, recent history, and this handover checksum.
2. Confirm which task, if any, is `Current` — read `docs/TASK_QUEUE.md`, not this file alone.
3. As of this writing, no task is `Current`. Starting any work requires a fresh written Human
   Owner authorization naming the task. AUTO-006 is explicitly not authorized, and neither are
   AUTO-007, GOV-2, GOV-3, or DASH-002..010.
4. Never delete either stash, and never delete `feature/auto-004-model-providers` or
   `feature/auto-005-agents`.

Completing GOV-AUTO-02 did not authorize a successor. AUTO-006 requires its own fresh written
authorization naming it; do not begin it or GOV-3.

## Authorization update — 2026-07-28

AUTO-006 is the single `Current` task after two exact Human Owner `AUTHORIZE` confirmations.
The authorization-only commit contains governance and handoff records; implementation has not
started. No predecessor was closed automatically, and no push, merge, upstream, branch, or stash
operation was performed.
