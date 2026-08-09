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

## Closure update — 2026-07-29

AUTO-007 was approved and closed `Current -> Done` by the Human Owner through
scripts/workflow-approve.sh's automatic task closeout. No task is `Current` after this commit
unless a fresh authorization already named a successor. No push, merge, branch, upstream, or
stash operation was performed by this closeout.

## Authorization update — 2026-07-29

GOV-2 is the single `Current` task after two exact Human Owner `AUTHORIZE` confirmations.
The authorization-only commit contains governance and handoff records; implementation has not
started. No predecessor was closed automatically, and no push, merge, upstream, branch, or stash
operation was performed.

## GOV-2 (2026-07-29) — implemented, uncommitted, awaiting Human Owner approval

GOV-2 ("Extend `check-governance` to validate stage-registry/lifecycle consistency") is
implemented and validated on `main` in the working tree, **uncommitted**, stopped for Human Owner
approval. Task status remains `Current`.

Delivered a new deterministic governance check, `check-registries`, that cross-checks each
configured stage registry's per-stage lifecycle `State` against the authoritative
`docs/TASK_QUEUE.md` status under the state→task-status mapping both program registries document
identically. New `src/ai_workflow_engine/governance/registry.py` (tolerant `## N. Registry`
table parser, `RegistryState`, the shared mapping, `classify_state`); `RegistryState`/
`RegistryRow`/`RegistryParse` in `governance/models.py`; `check_registries` in
`governance/validators.py`; a `GovernanceSettings.registries` config surface (repo-relative,
default empty); `self-governance.yaml` now names this repository's two registries; and a
`workflowctl check-registries` command plus a `registries` entry in `workflowctl verify` (now five
checks). Only the machine-checkable registry↔queue property was implemented; cross-registry
rule-equivalence and version-policy classification are documented deferrals per GOV-2's own
recommended shape. Report: `docs/reports/GOV-2-completion-report.md`.

Validation: `pytest tests agentos_workflow/tests` 2680 passed, 1 failed — the single failure
(`agentos_workflow/tests/e2e/test_dry_run.py`) is pre-existing and environment-dependent
(`running_engine_version()` resolves the installed package's `1.0.0` while the test hardcodes
`0.1.0`), reproduced identically on a clean `HEAD` worktree; my diff touches no `agentos_workflow`
file. ruff, black, mypy (`src` and `agentos_workflow`), and `git diff --check` all clean;
`workflowctl verify` PASS (the new `registries` check green: 17 stages across 2 registries).

The `ai-workflow-engine` conda env lacked the `dev` extra at session start;
`pip install -e ".[dev]"` was run to install the declared dev tooling so the gates could execute.
No source, dependency declaration, or lockfile changed as a result.

**Not yet done:** uncommitted, awaiting a separate Human Owner approval via
`scripts/workflow-approve.sh`, which performs the implementation commit and the deterministic
GOV-AUTO-03 closeout together. No push, merge, branch, upstream, or stash operation was performed.

## Closure update — 2026-07-29

GOV-2 was approved and closed `Current -> Done` by the Human Owner through
scripts/workflow-approve.sh's automatic task closeout. No task is `Current` after this commit
unless a fresh authorization already named a successor. No push, merge, branch, upstream, or
stash operation was performed by this closeout.

## Authorization update — 2026-07-29

GOV-3 is the single `Current` task after two exact Human Owner `AUTHORIZE` confirmations.
The authorization-only commit contains governance and handoff records; implementation has not
started. No predecessor was closed automatically, and no push, merge, upstream, branch, or stash
operation was performed.

## GOV-3 (2026-07-29) — implemented, uncommitted, awaiting Human Owner approval

GOV-3 ("Attempt-aware report artifact naming in the Reporting Skills") is implemented and
validated on `main` in the working tree, **uncommitted**, stopped for Human Owner approval. Task
status remains `Current`.

The four report generators in `agentos_workflow/skills/reporting.py` now take an optional,
validated `sequence` (`_validate_sequence`: an integer in `1..9999`, `bool` excluded), naming the
artifact `<kind>.<sequence>.json` inside that workflow's own audit directory beside its
`audit.jsonl`, instead of the single `<kind>.json` a repair loop's second round could not write.
An omitted sequence produces the previous artifact byte-identically, so every existing caller is
unaffected. `QAAgent._report_scope` — AUTO-005's per-attempt *derived workflow identifier*, which
put the rounds in sibling directories — is deleted in the same change, so the Skill and its only
caller cannot drift apart again. Contract: `docs/workflow-automation/SKILL_CONTRACTS.md` §6
(Version 1.3); rationale: `DECISIONS.md` DD-40 (Version 1.11). Report:
`docs/reports/GOV-3-completion-report.md`.

**Deliberately not fixed, recorded as OD-12** (`docs/workflow-automation/OPEN_QUESTIONS.md`,
Version 1.6): the Orchestrator's pre-loop QA round and `run_repair_loop`'s own first internal
round are both numbered attempt 1, so they still collide — correctly, since two different reports
claiming one round number ought to. Giving the round number a single owner changes
`agentos_workflow/agents/**` and the Orchestrator sequence, which is a design decision outside the
artifact-naming shape GOV-3 authorizes. It costs one repair attempt out of three on every workflow
that repairs.

Validation: `pytest tests agentos_workflow/tests` 2697 passed, 1 failed — the single failure
(`agentos_workflow/tests/e2e/test_dry_run.py`) is the same pre-existing, environment-dependent
`engine_version` failure GOV-2 recorded (`running_engine_version()` resolves the installed
package's `1.0.0` while the test hardcodes `0.1.0`), reproduced identically against a clean `HEAD`
(`58ed4f6`) tree and failing at `test_dry_run.py:407`, before the repair-loop section this change
touches. ruff, black, mypy (`src` and `agentos_workflow`), and `git diff --check` all clean;
`workflowctl verify` PASS on all five checks. 17 new tests; 16 of them fail against clean `HEAD`,
confirming they exercise the change rather than passing trivially.

**Not yet done:** uncommitted, awaiting a separate Human Owner approval via
`scripts/workflow-approve.sh`, which performs the implementation commit and the deterministic
GOV-AUTO-03 closeout together. No push, merge, branch, upstream, or stash operation was performed.

## Closure update — 2026-07-29

GOV-3 was approved and closed `Current -> Done` by the Human Owner through
scripts/workflow-approve.sh's automatic task closeout. No task is `Current` after this commit
unless a fresh authorization already named a successor. No push, merge, branch, upstream, or
stash operation was performed by this closeout.

## Authorization update — 2026-07-29

DASH-002 is the single `Current` task after two exact Human Owner `AUTHORIZE` confirmations.
The authorization-only commit contains governance and handoff records; implementation has not
started. No predecessor was closed automatically, and no push, merge, upstream, branch, or stash
operation was performed.

## Closure update — 2026-07-29

DASH-002 was approved and closed `Current -> Done` by the Human Owner through
scripts/workflow-approve.sh's automatic task closeout. No task is `Current` after this commit
unless a fresh authorization already named a successor. No push, merge, branch, upstream, or
stash operation was performed by this closeout.

## Authorization update — 2026-07-29

DASH-003 is the single `Current` task after two exact Human Owner `AUTHORIZE` confirmations.
The authorization-only commit contains governance and handoff records; implementation has not
started. No predecessor was closed automatically, and no push, merge, upstream, branch, or stash
operation was performed.

## Closure update — 2026-07-29

DASH-003 was approved and closed `Current -> Done` by the Human Owner through
scripts/workflow-approve.sh's automatic task closeout. No task is `Current` after this commit
unless a fresh authorization already named a successor. No push, merge, branch, upstream, or
stash operation was performed by this closeout.

## Registration update — 2026-07-29

A new task, `GOV-AUTO-04 — Automatic registered-branch preparation and canonical
completion-report naming`, was proposed by Human Owner directive and registered in
`docs/TASK_QUEUE.md` (and its prose mirror `docs/remaining_tasks.md`) as `Planned`. It resolves
OD-D10 and OD-D11 (`docs/agentos-dashboard/OPEN_QUESTIONS.md`) — the registered-branch-vs-
no-branch-runner conflict and the completion-report filename mismatch both DASH-002 and DASH-003
recorded — by giving `workflow-authorize.sh`/`workflow-next.sh` shared, automatic branch
preparation and teaching `workflow-approve.sh`'s report discovery the Dashboard program's
canonical `STAGE-XX-completion.md` name. **This is a governance-registration commit only: no
code was written, no task was authorized, and no task became `Current`.** No task is `Current`
after this commit. `GOV-AUTO-04` requires its own fresh, explicit Human Owner authorization
(`scripts/workflow-authorize.sh GOV-AUTO-04 [claude|codex]`) before any implementation may begin.
No push, merge, branch, upstream, or stash operation was performed by this registration.

## Authorization update — 2026-07-29

GOV-AUTO-04 is the single `Current` task after two exact Human Owner `AUTHORIZE` confirmations.
The authorization-only commit contains governance and handoff records; implementation has not
started. No predecessor was closed automatically, and no push, merge, upstream, branch, or stash
operation was performed.

## GOV-AUTO-04 (2026-07-29) — implemented, uncommitted, awaiting Human Owner approval

GOV-AUTO-04 ("Automatic registered-branch preparation and canonical completion-report naming") is
implemented and validated on `main` in the working tree, **uncommitted**, stopped for Human Owner
approval. Task status remains `Current`.

Resolves OD-D10 and OD-D11 (`docs/agentos-dashboard/OPEN_QUESTIONS.md`, both now `Resolved`).
New shared library `scripts/lib/branch_prepare.sh`
(`workflow_registered_branch`/`workflow_prepare_branch`/`workflow_verify_branch`), sourced by both
`scripts/workflow-authorize.sh` and `scripts/workflow-next.sh`. `workflow-authorize.sh` now
creates or safely switches to a registry-governed task's registered branch immediately after its
own authorization commit — refusing (no mutation) on a dirty worktree, an unexpected starting
branch, or an already-existing branch diverging from the commit it would be created from — while
GOV/plain tasks with no registry row stay on the default branch exactly as before; a preparation
failure after a successful authorization commit is reported distinctly (`EXIT_BRANCH_PREP`, exit
10), never rolling back the commit itself. `workflow-next.sh` independently verifies, read-only,
that the Current task's registered branch matches the working branch before launching an agent
(`EXIT_BRANCH_MISMATCH`, exit 8) — resolving OD-D10 without any exception to the runner prompt's
existing no-branch-creation rule, since by the time an implementation session starts the
registered branch already exists and is already checked out.

`scripts/workflow-approve.sh`'s completion-report discovery now also accepts the Dashboard
program's canonical `docs/reports/agentos-dashboard/STAGE-XX-completion.md` name for a DASH task,
with the two-digit stage number cross-checked against the registry's own Branch cell — never
derived from unchecked filename construction on the task ID alone — so a disagreeing or malformed
registry silently disables the canonical lookup rather than guessing, and two present reports
with differing content are refused outright (`EXIT_REPORT_CONFLICT`, exit 18); byte-identical
duplicates (the shape DASH-002/DASH-003 already left behind) are accepted without preferring one
over the other. Existing `<TASK_ID>-completion-report.md` behavior for AUTO/GOV tasks is
unchanged, resolving OD-D11. Rationale for both resolutions:
`docs/agentos-dashboard/DECISIONS.md` DD-08; implementation decision:
`docs/DECISION_LOG.md` (2026-07-29 entry). Report:
`docs/reports/GOV-AUTO-04-completion-report.md`.

Validation: 40 new focused tests (`tests/test_workflow_branch_prepare.py`,
`tests/test_workflow_report_discovery.py`, and additions to
`tests/test_workflow_authorize_script.py`/`tests/test_workflow_runner_scripts.py`, including a
regression test proving AUTO/GOV report discovery is unaffected). `pytest tests
agentos_workflow/tests` 2726 passed, 0 failed (the `test_dry_run.py` `engine_version` mismatch
GOV-2/GOV-3 previously recorded as pre-existing did not reproduce this session). ruff, black, and
mypy (`src` and `agentos_workflow`) clean; `git diff --check` clean; `workflowctl verify` PASS on
all five checks (`git`, `task-state`, `governance`, `registries`, `handover`).

**Two pre-existing documentation drifts were observed but not fixed in this pass** (outside
GOV-AUTO-04's scope; noted in the completion report as open items for a future session):
`docs/PROJECT_STATE.md`'s "In progress" section still narrated GOV-AUTO-03 as if active, and
`docs/remaining_tasks.md`'s prose paragraph had not been updated after DASH-003's approval —
both several task-cycles stale. This session added GOV-AUTO-04's own entries without disturbing
the pre-existing stale text (`PROJECT_STATE.md`) or, where the staleness was immediately adjacent
to this session's own edit and easily verified, corrected it in passing (`remaining_tasks.md`'s
DASH-003 closure sentence).

**Not yet done:** uncommitted, awaiting a separate Human Owner approval via
`scripts/workflow-approve.sh`, which performs the implementation commit and the deterministic
governance closeout together. No push, merge, branch, upstream, or stash operation was performed.

## Closure update — 2026-07-29

GOV-AUTO-04 was approved and closed `Current -> Done` by the Human Owner through
scripts/workflow-approve.sh's automatic task closeout. No task is `Current` after this commit
unless a fresh authorization already named a successor. No push, merge, branch, upstream, or
stash operation was performed by this closeout.

## Decision update — 2026-07-29 — OD-D9 resolved (dashboard serving stack)

The Human Owner resolved **OD-D9**, the last open question in the Dashboard register
(`docs/agentos-dashboard/OPEN_QUESTIONS.md` — its Open section is now empty). The AgentOS
Dashboard's serving stack is **FastAPI** (local HTTP application framework) + **Uvicorn** (ASGI
server) + **Jinja2** (server-rendered HTML templates), declared in a **new optional dependency
group `dashboard`** in `pyproject.toml`:

```toml
dashboard = [
  "fastapi>=0.111,<1",
  "jinja2>=3.1,<4",
  "uvicorn>=0.30,<1",
]
```

`[project].dependencies` is untouched, so `pip install ai-workflow-engine` still installs no web
framework and the audited engine keeps no HTTP surface; the dashboard is installed deliberately
with `pip install -e '.[dashboard]'` inside the `ai-workflow-engine` Conda environment. **The
dependencies were not installed by this session**, and there is no lockfile to update. Stdlib
`http.server` is explicitly rejected as the primary implementation. Binding stays loopback-only by
default — remote exposure, authentication, TLS, and production deployment remain later-stage
concerns. DASH-004 and later dashboard stages may use only these three distributions unless
separately authorized. Rationale: `docs/agentos-dashboard/DECISIONS.md` DD-09; repository record:
`docs/DECISION_LOG.md` (2026-07-29 entry).

**DASH-004 is no longer blocked by OD-D9** as of this governance commit, and needs no
`pyproject.toml` change of its own — that declaration is already spent. **DASH-004 nonetheless
remains `Planned` and unauthorized**: it still requires its own fresh written Human Owner
authorization (`scripts/workflow-authorize.sh DASH-004 [claude|codex]`), which will also prepare
its registered branch `feature/dash-004-dashboard-shell` (GOV-AUTO-04). Resolving an open question
authorizes nothing. **No task is `Current` after this commit.**

This is a governance/architecture/dependency-declaration commit only: no dashboard server code was
written, no runtime source or test was modified, and no branch, push, merge, rebase, reset, or
stash operation was performed. (Dates: the decision and this record are 2026-07-29; the session
crossed local midnight before committing, so Git timestamps the commit 2026-07-30.)

## Registration update — 2026-07-30

`GOV-AUTO-05 — Fix resolved-blocker false positives in authorization` is registered in
`docs/TASK_QUEUE.md` and its remaining-work mirror as `Planned`. A later, separately authorized
implementation may fix `scripts/workflow-authorize.sh` so explicit blocked status and active
unresolved questions in `OPEN_QUESTIONS.md`'s `## Open` section still refuse, while resolved
entries and negated or historical wording (`no longer blocked`, `not blocked`, `formerly
blocked`) do not. The full allowed paths, exclusions, safety invariants, and acceptance criteria
are recorded in the task queue.

This registration has no structured AUTO/DASH stage-registry row. The already-prepared patch was
not applied; no implementation, authorization, script, test, branch, push, merge, rebase, reset,
or stash operation occurred. GOV-AUTO-05 remains `Planned`, no task is `Current`, and fresh
explicit Human Owner authorization is required before implementation.

## GOV-AUTO-05 exception authorization and implementation — 2026-07-30

The Human Owner explicitly authorized GOV-AUTO-05 through a one-time governance exception because
the false-positive defect in `scripts/workflow-authorize.sh` prevented the normal gate from
authorizing its own repair. The task and mirrors record a manual `Planned → Current` transition;
no authorization-only commit was created. GOV-AUTO-05 is the sole `Current` task.

Implementation is complete and uncommitted for Human Owner approval. The canonical task status is
now only the first non-blank whole status-field line after the task heading, so quoted examples,
Markdown emphasis, acceptance criteria, explanatory prose, and fenced examples later in the
section cannot override it. Explicit canonical `Status: Blocked` still refuses. For a
registry-governed task, only structured active blocker entries under `OPEN_QUESTIONS.md`'s
`## Open` section are authoritative; resolved entries and negated or historical wording do not
refuse. The approval gate's matching whole-section scan was also fixed before approval:
Current-task discovery and guarded `Current → Done` replacement now use the same canonical-field
rule, while canonical Blocked refuses before any governance mutation. Existing predecessor,
registry, branch, report, scope, dirty-tree, Human confirmation, closeout, staging, checksum,
commit, remote, and stash protections are unchanged.

Focused authorization tests are 40-green, focused approval-closeout tests are 32-green, and the
broader workflow-specific regression set is 247-green. Full validation and bounded review are recorded in
`docs/reports/GOV-AUTO-05-completion-report.md`. No commit, push, merge, branch creation or
switching, rebase, reset, amend, force/history rewrite, or stash operation was performed.

## Closure update — 2026-07-30

GOV-AUTO-05 was approved and closed `Current -> Done` by the Human Owner through
scripts/workflow-approve.sh's automatic task closeout. No task is `Current` after this commit
unless a fresh authorization already named a successor. No push, merge, branch, upstream, or
stash operation was performed by this closeout.

## Authorization update — 2026-07-30

DASH-004 is the single `Current` task after two exact Human Owner `AUTHORIZE` confirmations.
The authorization-only commit contains governance and handoff records; implementation has not
started. No predecessor was closed automatically, and no push, merge, upstream, branch, or stash
operation was performed.

## Closure update — 2026-07-30

DASH-004 was approved and closed `Current -> Done` by the Human Owner through
scripts/workflow-approve.sh's automatic task closeout. No task is `Current` after this commit
unless a fresh authorization already named a successor. No push, merge, branch, upstream, or
stash operation was performed by this closeout.

## Authorization update — 2026-07-30 (AUTO-008)

AUTO-008 — Engine CI baseline — is the single `Current` task, registered and authorized by the
Human Owner in one act after an architectural audit. The audit's material finding: `agentos_workflow`
has never run as a program and no automated gate verifies it (no `cli.py`, absent from wheel
`packages`, not importable outside the repository root, not type-checked, 1,575 tests never
collected by CI, and its `MVP_SCOPE.md` §4 acceptance demonstration failing on `main`). AUTO-008 is
scoped to making that engine verifiable and adds no capability.

Separately authorized in the same session: DASH-004's implementation commit `96a6bb4` was published
to `main` by fast-forward, reconciling `main` with governance, which had already recorded DASH-004
as `Done` while its code sat unmerged. The authorization-only commit for AUTO-008 contains
governance and handoff records; implementation has not started. No predecessor was closed
automatically, and no merge, upstream, or stash operation was performed.

## Closure update — 2026-07-30 (AUTO-008)

AUTO-008 was approved and closed `Current -> Done` by the Human Owner in the same commit as its
implementation. No task is `Current` after this commit.

**What changed for anyone resuming work.** The engine is verified now. `pytest` collects all three
suites by default (1,160 -> 2,967 tests) and CI runs them; `mypy --strict` covers
`src/ai_workflow_engine`, `agentos_workflow`, and `agentos_dashboard` (115 source files, clean);
`pip install -e .` installs all three packages, so `agentos_workflow` is importable outside the
repository root for the first time. `agentos_workflow` has its own version in
`agentos_workflow/__about__.py`, so bumping the distribution version no longer invalidates
in-flight authorizations. OD-10 and OD-11 are resolved and the two test-only production workarounds
in `tests/e2e/test_dry_run.py` are gone.

**Two known open items, both reported rather than fixed, and both worth reading before starting
AUTO-009+.** F-2: AUTO-006's eight Git/GitHub Skills are delivered in `skills/git_github.py` but
still listed as undelivered in `agents.PROVISIONAL_SKILL_NAMES` and still unbound in
`default_skill_registry()`, so `GitAgent`/`MergeAgent` cannot function with the default registry —
the dry run binds them by hand. This blocks a first real run and is REQUIRED before AUTO-013. F-1:
the `expected`/`actual` parameter convention diverges between the two
`AuthorizationBindingDriftError` raise sites; the message was made faithful to both, but the
divergence itself remains. Full detail in
`docs/reports/workflow-automation/AUTO-008-completion-report.md` §6.

Still outstanding and unchanged by this stage: no real Claude CLI, Codex CLI, or GitHub call has
ever been made by this engine, and there is still no production code that sequences the six agents.
`MVP_SCOPE.md` §4's second acceptance demonstration -- a real target-repository run -- remains
unmet. No push, merge, upstream, or stash operation was performed by this closeout.

## Authorization update — 2026-07-30 (GOV-AUTO-06)

GOV-AUTO-06 — Bind delivered Git/GitHub skills into the default AgentOS skill registry — is the
single `Current` task, registered and authorized by the Human Owner to resolve the F-2 finding
AUTO-008 reported and deliberately did not fix: AUTO-006 delivered all eight Git/GitHub Skills, but
`PROVISIONAL_SKILL_NAMES` still classifies them as undelivered and `default_skill_registry()` still
does not bind them, so `GitAgent`/`MergeAgent` cannot invoke their own contracted Skills through the
production registry.

The Human Owner proposed the ID `AUTO-008-F2`; it was not used, because the governance parser
resolves it to the existing `Done` task `AUTO-008` and would have produced a duplicate `Current`
entry. `GOV-AUTO-06` is used instead, following the GOV-AUTO-01 precedent for follow-up tasks
outside the AUTO family (no stage-registry row, no stage contract). The recommended branch name is
kept. Implementation has not started; no push, merge, upstream, or stash operation was performed.

## Closure update — 2026-07-30 (GOV-AUTO-06)

GOV-AUTO-06 was approved and closed `Current -> Done` in the same commit as its implementation. No
task is `Current` after this commit.

**What changed.** The eight Git/GitHub Skills AUTO-006 delivered are now bound in
`default_skill_registry()` (32 -> 40 entries). Until now they were still listed in
`PROVISIONAL_SKILL_NAMES` as undelivered and absent from the bindings, so the broker answered every
one with "not yet implemented; it is delivered by AUTO-006" — a message emitted by the stage that
had already delivered them — and neither `GitAgent` nor `MergeAgent` could run against the
production registry. AUTO-008's F-2 finding is resolved.

`PROVISIONAL_SKILL_NAMES` is now empty but deliberately retained as a public symbol: the mechanism
is general and still enforced by `CapabilityBroker`. `GitAgent._is_unbound` was widened to match
both of the broker's no-binding answers so the existing `SKILL_UNAVAILABLE` classification is
preserved rather than silently decaying to `SKILL_FAILED`.

**Unchanged and worth knowing:** `AGENT_SKILL_CONTRACTS` is AST-identical to its prior value — no
Agent gained reach, proven by a negative test over all six Agents. The end-to-end dry run still
hand-binds the eight; that is now redundant rather than load-bearing, and simplifying it is
optional follow-up work, not a defect.

**Still open.** F-1 — the `expected`/`actual` parameter convention diverges between the two
`AuthorizationBindingDriftError` raise sites in `orchestrator/engine.py`. Still no real Claude CLI,
Codex CLI, or GitHub call has ever been made by this engine, and nothing yet sequences the six
agents; `MVP_SCOPE.md` §4's real-target-repository demonstration remains unmet. No merge was
performed by this closeout.

## Authorization update — 2026-07-31 (GOV-AUTO-07)

GOV-AUTO-07 — Normalize the `AuthorizationBindingDriftError` expected/actual convention — is the
single `Current` task, registered and authorized by the Human Owner to resolve the F-1 finding
AUTO-008 reported and deliberately did not fix.

F-1: `AuthorizationBindingDriftError(field, expected, actual)` is raised from two
authorization-drift call paths that pass those arguments in opposite senses.
`_detect_authorization_binding_drift` passes the independently-supplied *current* value as
`expected` and the persisted `AuthorizationRecord` as `actual`; `_validate_live_resume_observation`
/ `_live_drift` passes the persisted record as `expected` and the *live observation* as `actual`.
AUTO-008 found this while fixing the error's inverted message and could only neutralize the
wording, because no fixed "bound value X / current value Y" text is correct at both sites. As a
result `.expected` and `.actual` carry opposite meanings depending on which safety path raised.

Scope is the convention and its raise sites only: `field`, `expected`, and `actual` remain the
public attributes; no workflow transition, Git/GitHub skill registration, public CLI, shell script,
or other exception type changes, and the end-to-end dry run's redundant manual Skill bindings are
deliberately left alone. Implementation has not started; no push, merge, upstream, or stash
operation was performed.

## Closure update — 2026-07-31 (GOV-AUTO-07)

GOV-AUTO-07 — Normalize the `AuthorizationBindingDriftError` expected/actual convention — was
approved by the Human Owner after a required eight-point verification, closed `Current -> Done`, and
committed together with its implementation in one local commit on
`feature/gov-auto-07-drift-argument-convention`, which was then pushed. **No PR was opened and no
merge was performed.** The `Current` set is empty again.

AUTO-008's F-1 is resolved. `AuthorizationBindingDriftError` now documents one argument convention
and all 43 of its raise/helper call sites obey it: `expected` is the authorization-bound value where
the comparison has one, otherwise the invariant the check requires; `actual` is the current runtime,
repository, live-observation, or caller/disk-supplied value judged against it. Three clusters were
normalized — `_detect_authorization_binding_drift` (all ten `_BINDING_DRIFT_FIELDS`), two
`_live_drift` calls in `_validate_live_resume_observation`, and the four cross-record checks in
`_validate_persisted_authorization_evidence`. That third cluster is beyond the two paths F-1
literally named; it was included deliberately, flagged as a judgement call in the report, and is
independently reversible.

Every comparison is symmetric, so drift detection, its ordering, and its durable `-> FAILED`
consequence are unchanged — only the diagnostic orientation moved. The public attributes
`field`/`expected`/`actual` and the rendered message are byte-identical, so no caller must migrate.
Evidence: 3,005 tests passing (2,978 + 27 new); the new suite fails 17 of 27 against the pre-fix
engine while the 10 that pass are exactly the already-conforming sites; `mypy --strict` clean over
115 source files; `ruff`, `black`, and pre-commit clean.

Still outstanding and unchanged by this stage: no real Claude CLI, Codex CLI, or GitHub API call has
ever been made by this engine, and there is still no production code that sequences the six agents.
`MVP_SCOPE.md` §4's second acceptance demonstration — a real target-repository run — remains unmet.
AUTO-009 and every later roadmap phase remain unauthorized. No merge, upstream change, or stash
operation was performed by this closeout.

## Closure update — 2026-07-31 (AUTO-009)

AUTO-009 — WorkflowService boundary and read-only `workflowctl auto` surface — was approved by the
Human Owner after a required twelve-point scope, API, and read-only integrity verification, closed
`Current -> Done`, and committed together with its implementation in one local commit on
`feature/auto-009-workflow-service`, which was then pushed. Its authorization was a separate,
earlier commit on the same branch. **No PR was opened and no merge was performed.** The `Current`
set is empty again.

The engine now has a public boundary at which its persisted state can be observed from outside the
package, which it has lacked since AUTO-002:

    workflowctl auto -> WorkflowService -> agentos_workflow read-only state, audit,
                                           report, and configuration APIs

`agentos_workflow.service.WorkflowService` exposes exactly four operations — `status`, `list`,
`audit`, `report` — each returning a frozen, `extra="forbid"` pydantic result.
`agentos_workflow.cli_auto` surfaces the same four as `workflowctl auto`, reusing the engine CLI's
own `_protected`/`_write_stdout`/`_contract_v2_success` helpers so the error envelopes, exit codes,
and stdout/stderr discipline are the same code path rather than a second copy.
`src/ai_workflow_engine/cli.py` changed by +14/-0 lines and reaches AgentOS through exactly one
name.

Everything the surface does is read-only, and that was demonstrated rather than asserted: with
`RepositoryLock.acquire`/`__enter__`/`release`, `subprocess.run`/`Popen`, `os.system`/`fork`/
`posix_spawn`, both `StateStore` append methods, and all six reporting writers replaced by
functions that raise, all six operation invocations completed without reaching any of them, while a
path+mode+mtime+bytes digest over the state directory, the audit directory, and the target
repository stayed identical across each. Path confinement is unchanged: symlinked workflow
directories, history files, and report files are all still refused, and a malformed report is
surfaced rather than repaired.

Two supporting primitives were added to the modules that already own the corresponding storage
layout, deliberately not to the service, so the descriptor-relative `O_NOFOLLOW` discipline is not
duplicated: `StateStore.list_workflow_ids()` and `skills.reporting.read_reports()`. Neither creates
missing storage. No workflow state-machine change was needed or made.

Evidence: 3,151 tests passing (3,005 + 146 new, none skipped, none xfail); `mypy --strict` clean
over 117 source files; `ruff`, `black`, and pre-commit clean; the wheel carries both new modules and
both import from outside the repository root; thirteen of fourteen byte-compared existing command
invocations are identical to the `98acc195` baseline, the fourteenth being `workflowctl --help`,
which gains the intended `auto` group and nothing else.

Six non-blocking defects were recorded, classified, and deferred, none fixed: two stale
`STAGE_REGISTRY.md` prose lines (D1, D2, `OPTIONAL`); the CLI-helper extraction that would remove
`cli_auto`'s `OutputFormat` mirror and its deferred imports (D3, `RECOMMENDED` — the fix is a
refactor of the existing CLI, which AUTO-009 was forbidden to perform, and it should land before a
second AgentOS sub-app is added); the unreadable Skill-level `audit.jsonl` (D4, `FUTURE`); tests
shipping inside the wheel (D5, `RECOMMENDED`, pre-existing since AUTO-008); and a package-surface
inconsistency between `config/__init__.py` and `orchestrator/__init__.py` (D6, `OPTIONAL`).

Still outstanding and unchanged by this stage: no real Claude CLI, Codex CLI, or GitHub API call has
ever been made by this engine, and there is still no production code that sequences the six agents.
`MVP_SCOPE.md` §4's second acceptance demonstration — a real target-repository run — remains unmet.
This stage deliberately did not move toward it: it built the read half of the boundary first, so
that the write-capable operations, when separately authorized, are added to a boundary whose read
path is already tested. AUTO-010 and every later roadmap phase remain unauthorized. No merge,
upstream change to any other branch, or stash operation was performed by this closeout.

## AUTO-010 — Real Non-Interactive Provider Runtime (closed 2026-07-31)

**The engine now really executes Claude Code and Codex without a terminal.** That sentence was the
outstanding gap the AUTO-009 handover ends on, and it is the one this stage closed:

    WorkflowService.invoke_provider -> ProviderRuntime.invoke -> ClaudeCLIProvider / CodexCLIProvider
                                                              -> run_provider_process

`WorkflowService` gained exactly one operation, `invoke_provider`, whose whole body is a
delegation. Its surface is now five names — the four AUTO-009 read operations, unchanged and still
read-only, plus this one. It still holds no `RepositoryLock`, no `WorkflowSession`, and no path to
`StateStore`'s append methods, so a provider run cannot transition workflow state by itself; that
is asserted by booby-trapping both store writers for the duration of a real invocation. `service.py`
names no CLI flag and imports exactly one provider module (`providers.runtime`), both checked over
the parsed syntax tree rather than the source text.

**No second provider framework was built.** Everything below `runtime.py` is AUTO-004's, reused:
`ProviderInvocation`, `ProviderReport`, `ProviderFailure`, `ProviderVerdict`, the environment
allowlist, the session-directory layout, the retry classification, and secret redaction. The
runtime owns three things only: the auto-mode prompt contract, the closed `CLAUDE`/`CODEX` target
mapping, and the terminal-result contract. `select_live_provider` moved verbatim into
`providers/selection.py` so the runtime can select a provider without importing the package that
re-exports it — contents, typing, and public names unchanged.

**Never-ask is enforced at three layers, each tested against real child processes.** The prompt
contract states its four clauses verbatim and cannot be omitted, because `ProviderRunRequest`
carries a `task` and has no `prompt` field. Mechanically, the child gets its own session with no
controlling terminal (`open('/dev/tty')` raises), no TTY on any standard stream, exactly one prompt
on stdin, and EOF thereafter. Structurally, every run ends in `COMPLETED`,
`COMPLETED_WITH_ASSUMPTIONS`, `BLOCKED`, or `FAILED`; `BLOCKED` requires concrete blockers,
`COMPLETED_WITH_ASSUMPTIONS` requires recorded assumptions, and a report omitting `status` is
rejected rather than inferred from the pass/fail verdict.

**Policy is closed by construction, not by validation.** `ClaudePermissionMode` admits
`plan`/`dontAsk`/`acceptEdits` and `CodexSandboxMode` admits `read-only`/`workspace-write`, both
defaulting to the least capable value. Because configuration is typed to these enums
(`agentos_workflow/config/policy.py`, a leaf module importing nothing from this engine), Claude's
`bypassPermissions` and Codex's `danger-full-access` are not values the engine refuses — they are
values nothing in it can name.

**Verified argv, checked against the installed binaries and not against documentation:**

    claude --print --output-format json --permission-mode <mode>                        (2.1.220)
    codex exec --json --sandbox <mode> -c approval_policy="never" \
          --output-last-message <session>/codex-last-message.txt                 (codex-cli 0.146.0)

**Three blockers were fixed inside the shared process runner**, each minimal and each documented in
the report: `subprocess.run`'s timeout killed only the direct child and left the parent's
controlling terminal attached (now `Popen(start_new_session=True)` plus SIGTERM-then-unconditional
-SIGKILL of the whole process group); output ceilings were unenforced during capture and stderr had
none (now bounded streaming readers that keep draining past the limit so the child cannot deadlock,
while reclaiming the group); and AUTO-004's Codex parser took the last JSON object on stdout, which
in a real run is always a `turn.*` envelope and never the report — so that adapter could never have
worked against the live CLI, and had never been exercised against one.

**Account selection is an environment variable, never a shell alias.** The host's `codexA`/
`claudeA` aliases expand to `CODEX_HOME=... codex`; an alias is a shell construct that a
`shell=False`, fixed-argv spawn cannot expand, so configuring one fails at spawn (pinned by a test).
Selecting an account is the real `claude`/`codex` binary plus an allowlisted `CLAUDE_CONFIG_DIR`/
`CODEX_HOME`. No account path is hard-coded in the engine or in the tests.

Evidence: 3,241 tests passing (3,151 + 90, none skipped, none xfail) **plus 25 live acceptance
tests against the real installed CLIs with zero skips** — Claude 9, Codex 9, suite guards 7, each
provider validated on all ten of its acceptance criteria. `mypy --strict` clean over 120 source
files; `ruff`, `black`, and pre-commit clean; the wheel carries every new module and all import
from outside the repository root; nine existing `workflowctl` invocations are byte-identical to the
`5d1b6be` baseline. Live tests are opt-in (`-m live_cli`, excluded from the default run by
`addopts`), always run against disposable git repositories under `tmp_path`, and refuse loudly if a
working directory ever resolves inside this checkout.

Two process notes worth reusing. **Live provider tests must assert termination, not model
compliance:** an early version asserted that an ambiguous task always yields `BLOCKED`, and it was
flaky — the same prompt produced a well-formed `blocked` report on one run and unparseable output
on another. Both terminated promptly, which is what the stage actually requires. **A skip is not a
pass, and a precondition is better than a weakened assertion:** when Ubuntu 24.04's
`apparmor_restrict_unprivileged_userns` blocked bubblewrap and Codex's `workspace-write` sandbox
could not run, the test was gated on a probed precondition rather than relaxed to accept "no file
was created" — which would have been unfalsifiable, since a Codex that had genuinely stopped
writing would look identical. The Human Owner resolved it host-side with a scoped
`/etc/apparmor.d/bwrap` profile, after which the test passes unchanged.

Four non-blocking defects remain deferred, none fixed: the two overlapping outcome axes on
`ProviderReport` (`verdict` and `status`, D-3, `RECOMMENDED`, for AUTO-011 to collapse); persisted
provider artifacts having no reader and no audit linkage (D-4, `FUTURE`); no retry policy when a
model violates the output contract (D-5, `FUTURE`); and AUTO-009's own six (D-6). All six of
AUTO-009's are confirmed untouched.

Still outstanding: there is still no production code that sequences the six agents, and
`MVP_SCOPE.md` §4's second acceptance demonstration — a real target-repository run — remains unmet.
This stage deliberately built the execution primitive without the lifecycle that would use it.
AUTO-011 and every later roadmap phase remain unauthorized. No PR, merge, upstream change to any
other branch, or stash operation was performed by this closeout.

## AUTO-011 — Unified Provider and Agent Result Contract (closed 2026-08-01)

The engine now has one canonical result type for every execution it performs, present and future:

    WorkflowService -> Provider Runtime -> AgentRunResult

`agentos_workflow/results.py` delivers `AgentRunResult` alongside `RunFailure` and
`ArtifactReference`, all frozen and `extra="forbid"`. It is reached from AUTO-010's
`ProviderRunResult` through `agent_run_result_from_provider_run`, so nothing about the Provider
Runtime changed: every provider, orchestrator, agent, skill, config, CLI, `src/`, `scripts/`, and
packaging path is byte-identical to `fd0b34f`, the 240 AUTO-010 mocked tests pass with their files
untouched, all 25 live CLI tests pass with zero skips, and six `workflowctl` invocations are
byte-identical to a clean baseline worktree. Compatibility here was preserved by projection, not by
interface change — which is the pattern to reuse when the next stage needs an existing boundary to
keep working.

**Reuse was the governing constraint, and it decided the design.** `RunStatus` *is*
`ProviderRunStatus` — an alias asserted by identity, not a parallel enum — and `ProviderVerdict`,
`ProviderFailureKind`, `RetryClassification`, `ProviderKind`, `AgentKind`, and `WorkflowState` are
all reused. Only `ExecutionMode` and `ArtifactKind` are new, and a test parses the module to assert
they are the *only* enums it declares, so a second status or verdict vocabulary cannot be added
without failing. A unified contract that ships a parallel enum plus a mapping has unified nothing.

**Adapter totality is the constraint a future stage should inherit.** The canonical model must not
add a rejection on data AUTO-010 permits, except where the contract explicitly requires one.
Exactly one conflict existed — a provider reporting `COMPLETED` while naming blocking issues, which
AUTO-010 permits and the canonical contract forbids. It is recorded as `FAILED` with a
`MALFORMED_OUTPUT` failure naming the contradiction, preserving both the summary and the blockers,
because dropping the blockers erases evidence and raising would make the adapter partial. The same
reasoning kept `changed_files` permissive (a producer's *claim*, verified elsewhere) while
`ArtifactReference` is strict (a path a reader actually follows).

**D-3 was deliberately narrowed, not collapsed.** AUTO-010 deferred the `verdict`/`status` overlap
*to* this stage, and this stage kept both axes on purpose: a `COMPLETED` run reporting `fail` is a
QA provider finding real defects — a successful execution with a failing verdict. Merging them
would destroy that distinction. What was removed is the ambiguity, by giving each axis one
canonical type and one documented meaning. Do not "finish" D-3 by deleting a field.

**`recommended_next_state` is advisory and must stay that way.** No module in `agentos_workflow`
outside the contract contains the string; ten structural tests assert it over parsed syntax trees
rather than in prose, including that the module imports no `StateStore`, `RepositoryLock`, or
`WorkflowSession` and calls nothing that spawns or writes. An agent reports; the Orchestrator
decides.

Three new non-blocking defects remain deferred, none fixed: `ProviderRunResult` still permits
`COMPLETED` alongside blocking issues (D-8, `RECOMMENDED`); an output-limit breach is not
distinguishable by failure kind, so the canonical failure recovers it by prefix-matching
engine-generated wording, pinned by two tests that provoke a real breach through the real process
runner (D-9, `RECOMMENDED`); and `results.py` importing `AgentKind` and `WorkflowState` will become
an `agents -> results -> agents` cycle once agents actually produce these results, whose remedy is
to move those enums into a leaf module exactly as `config/policy.py` did (D-10, `RECOMMENDED`).
AUTO-010's D-3 through D-6 and AUTO-009's D1-D6 are confirmed untouched.

Still outstanding: this stage standardized results without implementing any producer of them beyond
the provider adapter. There is still no production code that sequences the six agents, no
Preparation, Reviewer, or Implementer Mode, and `MVP_SCOPE.md` §4's second acceptance demonstration
— a real target-repository run — remains unmet. AUTO-012 and every later roadmap phase remain
unauthorized. No PR, merge, upstream change to any other branch, or stash operation was performed
by this closeout.

## AUTO-012 — Configurable Approval Policy, Persistence, and Invalidation (closed 2026-08-01)

The engine has a reusable approval subsystem for future workflow gates:

    WorkflowService -> ApprovalService -> policy resolution, request persistence,
                                          manual decisions, timeout decisions,
                                          checksum binding, invalidation

`agentos_workflow/approvals.py` holds a `StateStore` and nothing else — no provider, no agent, no
Skill, no lock, no workflow session, no network client — so an approval cannot cause work to
happen. It records only that permission was asked for, given, withheld, expired, or spent.

**Read the governance documents before implementing, because one of them can forbid the stage.**
`HUMAN_AUTHORIZATION_MODEL.md` v1.1 §1 declared the `CREATED -> AUTHORIZED` transition "the only
human gate in this system", and its own §8 made adding any second human-approval point a MAJOR
change requiring explicit Human Owner sign-off. Building an approval subsystem without that
sign-off would have contradicted the governing document while implementing the thing it forbade.
The prerequisite was therefore satisfied as its own act, ahead of the code: that document is now
**v2.0**, §1 is amended in place from "the only" to "the founding" gate, and a new **§5a** records
the decision. It authorizes the **subsystem only** — never a mode, never a gate placement, never a
successor — and restates seven constraints it does not relax. Reuse this ordering: obtain the
governance amendment first, and never quietly outgrow a written safety property.

**No workflow state was added, on purpose.** The directive permitted `AWAITING_APPROVAL`,
`APPROVAL_TIMED_OUT`, and `HUMAN_INTERVENTION_REQUIRED` but preferred none if avoidable. They were
avoidable: this stage implements no lifecycle, so every such state would be unreachable and every
new `ALLOWED_TRANSITIONS` edge untested — dead weight in the safety-critical core the same directive
says not to refactor. Approval status lives on `ApprovalStatus` inside the subsystem that owns it,
which also satisfies the rule that workflow states must not duplicate policy logic. `WorkflowState`
is still 19 members with 37 edges. The stage that first *consumes* an approval will have the
evidence to choose the right states; do not guess them earlier.

**Events plus replay, not a mutable record.** An approval is an append-only sequence of
`ApprovalEvent`s and the current `ApprovalRequest` is derived by replaying them. That makes "no
decision is ever overwritten" a property of the file format rather than a promise — there is no code
path that rewrites a line, because the only write is an append. Same idiom as the transition
history.

**Reuse persistence; do not rebuild it.** `StateStore` gained exactly two additive methods,
`record_approval` and `read_approvals`, deliberately generic in the record type: the approval
vocabulary is built *on* the store, and naming it there would invert the dependency into an import
cycle. Everything the approval path needs — exclusive locking across the whole open-write-fsync
sequence, non-decreasing timestamps, complete writes, fsync of file and directory, and the confined
symlink-refusing walk — is inherited rather than reimplemented, and each property is exercised
through `ApprovalService` in the tests rather than assumed.

**`AUTO_APPROVE` fails closed and loudly.** It is refused when inherited from a built-in or
project-wide default and accepted only from the specific gate or a per-run override. It raises
rather than silently downgrading to `PAUSE`, because a downgrade leaves a configuration that *says*
`auto_approve` behaving as `pause` — a trap the operator discovers only when a deadline passes,
with nothing in the record explaining why. The snapshot keeps `timeout_action_source`, so an
automatic approval is never indistinguishable from a human one in the audit trail.

**Deadlines are facts on disk.** Absolute, timezone-aware, evaluated lazily. There is no thread,
timer, sleep, or scheduler anywhere in the module — asserted over its syntax tree — which is why a
deadline survives a process or machine restart, proven by a test that builds an entirely new service
over the same directory. `get_approval` deliberately stays a pure read so an audit view can observe
an expired-but-unevaluated approval without deciding its outcome.

Three new non-blocking defects remain deferred, none fixed: a workflow with approvals but no
transition history is invisible to `list_workflow_ids` (D-11, `RECOMMENDED`, genuinely ambiguous
until a lifecycle consumes approvals); all approvals for a workflow share one ordered file, so
timestamps must be non-decreasing across otherwise-independent approvals (D-12, `OPTIONAL`); and
multi-tier escalation is not expressible, which is a deliberate bound rather than an oversight
(D-13, `OPTIONAL`). AUTO-011's D-8 through D-10, AUTO-010's D-3 through D-6, and AUTO-009's D1-D6
are confirmed untouched — D3 in particular because no CLI command was added, the service boundary
having been validated by tests as the directive preferred.

Still outstanding: this stage built the approval *mechanism* and nothing that uses it. There is
still no production code that sequences the six agents, no Preparation, Reviewer, or Implementer
Mode, no gate placement anywhere, and `MVP_SCOPE.md` §4's second acceptance demonstration — a real
target-repository run — remains unmet. AUTO-013 and every later roadmap phase remain unauthorized.

## Authorization update — 2026-08-02

GOV-4 is the single `Current` task after Human Owner authorization, registered and authorized in
one act as an ordinary (non-AUTO/GOV-AUTO-family) engine task record following the GOV-2/GOV-3
precedent. It is a pre-AUTO-013 live acceptance test-harness correction discovered while verifying
the AUTO-013 baseline — two independent defects in `agentos_workflow/tests/live/` and its mocked
companion `agentos_workflow/tests/test_provider_runtime.py`: session-scoped forwarding of the
configured Claude account's real `CLAUDE_CONFIG_DIR` letting Claude Code's own continuity state
accumulate across invocations, and real Claude's non-deterministic first-attempt compliance with
the strict bare-JSON auto-mode contract. Scope is test-only; no production code, parser, provider
argv, permission mode, or workflow state changes. The authorization-only commit contains
governance and handoff records; implementation has not started. No predecessor was closed
automatically, and no push, merge, upstream, branch, or stash operation was performed.

## Closure update — 2026-08-02

GOV-4 was approved and closed `Current -> Done` on 2026-08-02. `_stage_ephemeral_claude_config_dir`
makes the configured Claude account directory a read-only authentication template, copying only
`.credentials.json` into a fresh per-invocation directory. `run_live_claude_with_bounded_format_
repair` bounds retry to exactly 3 attempts, strictly limited to `FAILED`/`MALFORMED_OUTPUT`, each
attempt isolated in its own ephemeral config/session/repository directory; every other failure
kind is accepted unchanged on attempt one. A new deterministic mocked test pins single-attempt
rejection of malformed output, unweakened. Evidence: two full `pytest -q -m live_cli -rs` runs at
32 passed/0 failed/0 skipped each; the authentication template byte- and mtime-identical across
every live run; zero `.claude-A` contamination; 3,470 tests green; `mypy` clean over 122 source
files; `ruff`/`black`/pre-commit clean; `workflowctl verify` full PASS. No production code was
changed. This closure authorizes no successor — AUTO-013 and every later roadmap phase remain
unauthorized. Report: `docs/reports/GOV-4-completion-report.md`.

## Authorization update — 2026-08-08

DASH-005 is the single `Current` task after two exact Human Owner `AUTHORIZE` confirmations.
The authorization-only commit contains governance and handoff records; implementation has not
started. No predecessor was closed automatically, and no push, merge, upstream, branch, or stash
operation was performed.

## Closure update — 2026-08-08

DASH-005 was approved and closed `Current -> Done` by the Human Owner through
scripts/workflow-approve.sh's automatic task closeout. No task is `Current` after this commit
unless a fresh authorization already named a successor. No push, merge, branch, upstream, or
stash operation was performed by this closeout.

## Authorization update — 2026-08-09

DASH-006 is the single `Current` task after two exact Human Owner `AUTHORIZE` confirmations.
The authorization-only commit contains governance and handoff records; implementation has not
started. No predecessor was closed automatically, and no push, merge, upstream, branch, or stash
operation was performed.

## Closure update — 2026-08-09

DASH-006 was approved and closed `Current -> Done` by the Human Owner through
scripts/workflow-approve.sh's automatic task closeout. No task is `Current` after this commit
unless a fresh authorization already named a successor. No push, merge, branch, upstream, or
stash operation was performed by this closeout.
