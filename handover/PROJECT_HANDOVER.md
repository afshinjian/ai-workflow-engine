# Project Handover

Narrative context transfer between sessions. This file is checksum-verified by
`handover/PROJECT_CHECKSUM.md`; cross-check its claims against Git and the configured validation
commands.

## Where things stand (2026-07-28)

The released `ai-workflow-engine` 1.0.0 roadmap is complete. In the post-1.0 programs:

- DASH-001 is `Done`; DASH-002..DASH-010 remain `Planned`.
- AUTO-001 through **AUTO-006** are `Done` and registry `COMPLETE`.
- GOV-AUTO-01 and GOV-AUTO-02 are both `Done` — `a302c95`/`a3b5b0a` and
  `d212e4d2dae2cd0a3510c54d7cd098fdfd5da548` respectively.
- **AUTO-006 was approved and closed on 2026-07-28** — implemented, validated, approved by the
  Human Owner, committed as `d8d356d060076be4ad78afb4d20891004a946204`, and authorized for
  publication into `main` under the same decision. Report:
  `docs/reports/workflow-automation/AUTO-006-completion-report.md` (see its Addendum 1).
- **GOV-AUTO-03 was authorized by the Human Owner on 2026-07-28** — "I authorize one new
  governance and developer-experience task: GOV-AUTO-03 — Human-Approved Commit with Automatic
  Task Closeout." Implemented and validated the same day: `scripts/workflow-approve.sh` now
  performs the approved implementation commit and the deterministic governance closeout of that
  same task together as one controlled local commit, gated on the `project.id:
  ai-workflow-engine` marker so every other repository (including the pre-existing test
  sandboxes) keeps the unchanged GOV-AUTO-01 plain commit gate. **Uncommitted**, stopped for
  Human Owner approval. Report: `docs/reports/GOV-AUTO-03-completion-report.md`.
- AUTO-007 remains `NOT_STARTED`/`Planned`. GOV-2 and GOV-3 remain `Planned`, each needing its own
  authorization.

GOV-AUTO-03 is the single `Current` task as of this update. AUTO-007, GOV-2, and GOV-3 remain
`Planned` and unauthorized; authorizing GOV-AUTO-03 authorized none of them.

## What this commit is

This is the **AUTO-006 governance closure commit** — records only, no runtime code. It exists
because the Human Owner's closure-and-publication decision requires `main`, after the merge, to
carry a consistent record set (task queue, both mirrors, project state, stage registry, both
changelogs, decision log, this handover, and the checksum) showing AUTO-006 `Done`/`COMPLETE`. The
implementation itself is `d8d356d060076be4ad78afb4d20891004a946204`, which this commit does not
touch.

The AUTO-006 completion report was **not** rewritten. Its Confirmation section says no commit was
performed, which was true when written — `d8d356d` came afterwards. The commit, the approval, and
the merge are recorded in a new append-only addendum at the end of that report, a new
`docs/workflow-automation/STAGE_REGISTRY.md` §5 row, and `docs/DECISION_LOG.md`
(`STAGE_REGISTRY.md` §3 rule 8; the Human Owner's explicit instruction).

## What AUTO-006 delivered (committed as `d8d356d`, on `feature/auto-006-pr-merge-closeout`)

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
| Active branch | `main` (`origin/main` synchronized at the time GOV-AUTO-03 implementation began) |
| Base HEAD | `c8e59fb` — the AUTO-006 merge into `main` |
| GOV-AUTO-03 implementation | uncommitted on the working tree, directly on `main`; no stage branch was created (governance/developer-experience task, same as GOV-AUTO-01/02) |
| Next step | Human Owner review and approval via `scripts/workflow-approve.sh`, which will create the one implementation + closeout commit |
| AUTO-006 implementation commit | `d8d356d060076be4ad78afb4d20891004a946204`, merged into `main` |
| AUTO-005 implementation commit | `430cbb4`, merged |
| GOV-AUTO-02 implementation commit | `d212e4d2dae2cd0a3510c54d7cd098fdfd5da548`, merged |
| Stage branches | `feature/auto-004-model-providers`, `feature/auto-005-agents`, `feature/auto-006-pr-merge-closeout` — all pushed and **retained**; none may be deleted |
| Stashes | `stash@{0}`, `stash@{1}` — both untouched since before AUTO-002 |

Local `main` carries the `docs(governance): authorize AUTO-006` commit
(`3336184619bc6464f62a162ee34d869957b08928`) one ahead of `origin/main` — a pre-existing,
already-recorded state, not new divergence introduced by this commit.

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

## GOV-AUTO-03 (2026-07-28) — implemented, uncommitted, awaiting Human Owner approval

Extends `scripts/workflow-approve.sh` (GOV-AUTO-01) so that, after the same two exact `APPROVE`
confirmations, it identifies the single `Current` task from `docs/TASK_QUEUE.md`, verifies the
`current_task.md`/`remaining_tasks.md` mirrors, the relevant stage registry (where applicable),
and the approved commit message all correspond to it, performs a fail-closed deterministic
closeout (task queue, mirrors, project state, decision log, changelog, stage registry where
applicable, program changelog where applicable, a completion-report addendum, handover, and
checksum) via `awk`-guarded precondition-checked replacements, re-runs `task-state`/`governance`/
`handover` validation, and creates exactly one local commit containing the approved implementation
and the generated closeout records together — never a separate closure commit. Gated on the
`project.id: ai-workflow-engine` marker `workflow-authorize.sh` already uses, so every other
repository (every pre-existing test sandbox included) keeps the unchanged GOV-AUTO-01 gate. A
pre-closeout backup restores every generated governance file verbatim on any failure, leaving the
approved implementation untouched; the script never pushes, merges, changes branches, alters
upstream, mutates stashes, or authorizes a successor.

26 new tests in `tests/test_workflow_approve_closeout.py`; the pre-existing GOV-AUTO-01 suite
(`tests/test_workflow_runner_scripts.py`, 60 tests) and GOV-AUTO-02 suite
(`tests/test_workflow_authorize_script.py`, 28 tests) pass unmodified. Full repository suite
2,590-green; ruff/black/mypy clean on `src` and `agentos_workflow`; `git diff --check` clean;
`bash -n`/`shellcheck` clean on all three scripts. Full detail:
`docs/reports/GOV-AUTO-03-completion-report.md`.

**Not yet done:** the implementation is uncommitted, awaiting a separate Human Owner approval
decision. No push, merge, or successor authorization has occurred.

## Next session

1. Verify `git status`, recent history, and this handover checksum.
2. Confirm which task, if any, is `Current` — read `docs/TASK_QUEUE.md`, not this file alone. As
   of this writing GOV-AUTO-03 is `Current`, implemented, and awaiting Human Owner approval.
3. AUTO-007, GOV-2, and GOV-3 all require their own fresh written authorization naming them —
   authorizing GOV-AUTO-03 authorized none of them
   (`docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 16).
4. Never delete either stash, and never delete `feature/auto-004-model-providers`,
   `feature/auto-005-agents`, or `feature/auto-006-pr-merge-closeout` — the Human Owner's decision
   explicitly retains all three.

## Closure update — 2026-07-28

GOV-AUTO-03 was approved and closed `Current -> Done` by the Human Owner through
scripts/workflow-approve.sh's automatic task closeout. No task is `Current` after this commit
unless a fresh authorization already named a successor. No push, merge, branch, upstream, or
stash operation was performed by this closeout.

## Authorization update — 2026-07-28

AUTO-007 is the single `Current` task after two exact Human Owner `AUTHORIZE` confirmations.
The authorization-only commit contains governance and handoff records; implementation has not
started. No predecessor was closed automatically, and no push, merge, upstream, branch, or stash
operation was performed.
