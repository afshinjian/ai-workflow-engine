# Project Handover

Narrative context transfer between sessions. This file is checksum-verified by
`handover/PROJECT_CHECKSUM.md`; cross-check its claims against Git and the configured validation
commands.

## Where things stand (2026-07-28)

The released `ai-workflow-engine` 1.0.0 roadmap is complete. In the post-1.0 programs:

- DASH-001 is `Done`; DASH-002..DASH-010 remain `Planned`.
- AUTO-001 through AUTO-005 are `Done` and registry `COMPLETE`. All five are merged into `main`.
- GOV-AUTO-01 and GOV-AUTO-02 are both `Done` — `a302c95`/`a3b5b0a` and
  `d212e4d2dae2cd0a3510c54d7cd098fdfd5da548` respectively.
- **AUTO-006 is `Current`** — authorized by the Human Owner on 2026-07-28 through
  `scripts/workflow-authorize.sh`, registry `IN_PROGRESS`, **implemented and validated but
  uncommitted**, awaiting Human Owner review. Report:
  `docs/reports/workflow-automation/AUTO-006-completion-report.md`.
- AUTO-007 remains `NOT_STARTED`/`Planned`. GOV-2 and GOV-3 remain `Planned`, each needing its own
  authorization.

No task other than AUTO-006 is `Current`. AUTO-006's implementation is complete but its
authorization does not extend to committing, pushing, merging, or beginning AUTO-007 — those all
require separate, explicit Human Owner acts.

## What AUTO-006 delivered (uncommitted, on `feature/auto-006-pr-merge-closeout`)

Two new files only: `agentos_workflow/skills/git_github.py` (the eight Git/GitHub Skills of
`SKILL_CONTRACTS.md` §5 — `create_commit`, `push_stage_branch`, `create_pull_request`,
`read_pull_request_state`, `verify_head_sha`, `read_required_checks`,
`enable_automatic_squash_merge`, `verify_merge_completion`) and
`agentos_workflow/tests/test_skills_git_github.py` (33 tests). No file under
`agentos_workflow/agents/**`, `agentos_workflow/orchestrator/**`, `src/`, or `tests/` was touched.

Binds the eight Skill names `GitAgent`/`MergeAgent` (AUTO-005) already called against fakes —
those Agents needed no code change because this stage matched their existing call shapes exactly.
OD-1 (native GitHub auto-merge vs. engine-side polling) resolved in favor of native
`gh pr merge --auto --squash` (`docs/workflow-automation/DECISIONS.md` DD-37).

**Two things this stage explicitly did not do**, both flagged for a Human Owner decision rather
than resolved unilaterally:

1. **Orchestrator wiring.** The stage contract's Build section says to "wire the Merge Safety Gate
   and Checks-Wait Gate into the Orchestrator," but the contract's own Allowed-files list names
   only the Skill file, tests, and docs — not `agentos_workflow/orchestrator/**`. This session
   followed the Allowed-files list; `orchestrator/engine.py` is untouched, consistent with
   AUTO-005's own report already stating Agent-to-Orchestrator wiring belongs to AUTO-007.
2. **`allowed_environment_variables` gap (new: OD-10, `DECISIONS.md` DD-38).** Five of the eight
   Skill calls — `create_pull_request`, `read_pull_request_state`,
   `enable_automatic_squash_merge`, `read_required_checks`, `verify_merge_completion` — are
   invoked by `GitAgent`/`MergeAgent` (AUTO-005 code) without `allowed_environment_variables`, so
   in a real deployment `gh` has no path to a `GH_TOKEN`/`GITHUB_TOKEN` or a readable `$HOME` and
   cannot authenticate. The fix is small and mechanical (five call sites in
   `agents/git.py`/`agents/merge.py`) but requires authorization to touch
   `agentos_workflow/agents/**`, outside AUTO-006's allowed files. Does not affect the default test
   suite (the fake `gh` needs no auth) but would block a real end-to-end run.

Validation: 33 new focused tests; `agentos_workflow` suite 1,498-green (from 1,465); engine
`tests` collection unchanged at 1,066 (no `tests/`/`src/` file touched); ruff, black, mypy clean
on both `agentos_workflow` and `src`; `git diff --check` clean; `workflowctl verify` PASSes
`task-state`/`governance`/`handover` and FAILs only the pre-existing, documented
`upstream_missing` finding for the freshly created, not-yet-pushed stage branch. Full detail:
`docs/reports/workflow-automation/AUTO-006-completion-report.md`.

## Current Git state

| Fact | Value |
|---|---|
| `main` / `origin/main` | matched at `3336184619bc6464f62a162ee34d869957b08928` ("authorize AUTO-006") before this session |
| Active branch | `feature/auto-006-pr-merge-closeout`, created from that clean `main`; **not pushed** |
| Working tree | two new untracked files only (`agentos_workflow/skills/git_github.py`, `agentos_workflow/tests/test_skills_git_github.py`); no commit made |
| AUTO-005 implementation commit | `430cbb4`, merged |
| GOV-AUTO-02 implementation commit | `d212e4d2dae2cd0a3510c54d7cd098fdfd5da548`, merged |
| Stage branches | `feature/auto-004-model-providers`, `feature/auto-005-agents` — pushed and **retained**; `feature/auto-006-pr-merge-closeout` — local only, not yet pushed; none may be deleted |
| Stashes | `stash@{0}`, `stash@{1}` — both untouched since before AUTO-002 |

A stage branch created and not yet pushed produces the pre-existing `upstream_missing` finding on
`workflowctl check-git` — the tolerance `STAGE_REGISTRY.md` §3 rule 16 and the SSP both name; it
is expected here and is not a defect.

## Known open items

- **OD-10 / DD-38** (new, AUTO-006): five Git/GitHub Skill call sites never receive
  `allowed_environment_variables` — see above. Requires its own Human Owner decision.
- **Orchestrator wiring of the Merge Safety Gate / Checks-Wait Gate** is not performed — see
  above; likely AUTO-007's responsibility, unresolved.
- **QA report artifacts collide within one workflow** — tracked as **GOV-3** (`docs/TASK_QUEUE.md`,
  `Planned`, unauthorized). `generate_qa_report` allows one `reports/qa.json` per workflow
  identifier, but a repair loop runs up to four QA rounds. AUTO-005 worked around it with a
  per-attempt audit scope; the real fix — an attempt-aware artifact name — is deferred.
- **`detect_future_stage_work` needs a later-stage path map** that no configuration field
  supplies; with the default empty map the check passes trivially. Worth an explicit wiring
  decision.

## Next session

1. Verify `git status`, recent history, and this handover checksum.
2. Confirm which task is `Current` — read `docs/TASK_QUEUE.md`, not this file alone. As of this
   writing it is AUTO-006, implemented but uncommitted.
3. AUTO-006's implementation requires Human Owner review (report above) before any commit, push,
   merge, or start of AUTO-007. Starting AUTO-007, GOV-2, GOV-3, or any DASH-00x task requires its
   own fresh written authorization — none currently authorized.
4. Never delete any stash, and never delete `feature/auto-004-model-providers` or
   `feature/auto-005-agents`. `feature/auto-006-pr-merge-closeout` also should not be deleted
   while AUTO-006 remains `Current`.
