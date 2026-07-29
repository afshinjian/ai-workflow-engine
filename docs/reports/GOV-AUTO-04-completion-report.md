# GOV-AUTO-04 Completion Report

## Result

Implemented GOV-AUTO-04 — "Automatic registered-branch preparation and canonical
completion-report naming" — exactly as its authorized scope describes: a new shared library,
`scripts/lib/branch_prepare.sh`, gives `scripts/workflow-authorize.sh` and
`scripts/workflow-next.sh` one tested branch-preparation/verification routine (resolves OD-D10),
and `scripts/workflow-approve.sh`'s completion-report discovery now also accepts the Dashboard
program's canonical `STAGE-XX-completion.md` name (resolves OD-D11). The implementation is
complete and validated; it is **uncommitted**, stopped for Human Owner approval per the standard
workflow. Task status remains `Current`.

## The defects, and what changed

**OD-D10.** The SSP's execution precondition requires a registry-governed AUTO/DASH stage to run
on its registered branch, created from clean `main`, but `scripts/workflow-authorize.sh` recorded
authorization on the default-branch baseline and explicitly documented the branch as "created
later by the implementation session, never by this gate," while the canonical runner prompt
(`scripts/prompts/implement-next-task.md` §7) flatly forbids that same session from creating or
switching branches. No session could satisfy both, so DASH-002 and DASH-003 were each implemented
on `main`, and `scripts/workflow-approve.sh` then refused their closeout until the Human Owner
manually ran `git switch -c ...`.

Resolution: neither instruction is relaxed. `scripts/workflow-authorize.sh` itself now prepares
the registered branch — immediately after its own authorization commit, from the clean,
just-committed default-branch baseline, before any agent is ever launched. The runner prompt's
no-branch-creation rule is untouched: by the time an implementation session starts, the branch
already exists and is already checked out, so the session has nothing to create or switch.
`scripts/workflow-next.sh` independently re-verifies (read-only) that the Current task's
registered branch matches the working branch before launching an agent, so a session resumed
without going through `workflow-authorize.sh` first cannot silently run on the wrong branch either.

**OD-D11.** The Dashboard program's own documented naming convention
(`docs/agentos-dashboard/STAGE_REGISTRY.md` §3) is
`docs/reports/agentos-dashboard/STAGE-XX-completion.md`, but `workflow-approve.sh`'s
report-discovery loop only ever accepted `<TASK_ID>-completion-report.md`, so every DASH stage's
report needed a manual duplicate copy to satisfy the gate — as the current repository state shows
first-hand: `docs/reports/agentos-dashboard/DASH-002-completion-report.md` and
`DASH-003-completion-report.md` are duplicate copies of `STAGE-02-completion.md` and
`STAGE-03-completion.md` respectively, and only the duplicates carry the
`workflow-approve.sh`-generated "Addendum — Human Owner approval and closure" section — the
canonical files DASH-001 established the convention with do not, because the gate never looked at
them.

Resolution: the discovery loop now also accepts the canonical name for a DASH task, with the
two-digit stage number cross-checked against the registry's own Branch cell (e.g.
`feature/dash-002-repo-adapter` → `02`) rather than derived from unchecked filename construction
on the task ID alone. A disagreeing or malformed registry silently disables the canonical lookup
(never guesses); two present reports with differing content are refused outright
(`EXIT_REPORT_CONFLICT`, exit 18); byte-identical duplicates — the exact shape DASH-002/DASH-003
already left behind — are accepted without preferring one name over the other. Existing
`<TASK_ID>-completion-report.md` behavior for AUTO/GOV tasks is unchanged.

## Delivered

- **`scripts/lib/branch_prepare.sh`** (new): three functions, sourced by both wrapper scripts.
  - `workflow_registered_branch <repo_root> <task_id>` — read-only lookup of a task's Branch cell
    across both stage registries; empty output for a GOV/plain task with no row.
  - `workflow_prepare_branch <repo_root> <default_branch> <required_branch>` — no-op when
    `required_branch` is empty or equals `default_branch`; otherwise creates `required_branch`
    from the current HEAD and switches to it, or (idempotent resume) switches to it if it already
    exists at that same HEAD. Refuses — prints one diagnostic to stderr, returns 1, mutates
    nothing — on a dirty worktree, unresolved conflicts, a starting branch that is neither
    `default_branch` nor already `required_branch`, or an existing `required_branch` pointing
    anywhere else (divergent/ambiguous history a human must resolve).
  - `workflow_verify_branch <repo_root> <task_id> <current_branch>` — read-only launch
    precondition; prints an explanatory error and returns 1 only when a registered branch exists
    and disagrees with `current_branch`.
- **`scripts/workflow-authorize.sh`**: sources the library; after the authorization commit's
  existing branch/upstream/stash/clean-tree safety checks, calls `workflow_prepare_branch` using
  the already-computed `required_branch`. Reports the resulting branch ("Working branch : ...").
  A preparation failure is a distinct new exit code, `EXIT_BRANCH_PREP` (10), and never rolls back
  the already-created authorization commit — only branch preparation failed, not authorization.
- **`scripts/workflow-next.sh`**: sources the library; after the existing dirty-worktree check,
  reads `docs/TASK_QUEUE.md` for the single Current task (skipping the check entirely if the file
  is absent, or if zero or more than one task is Current) and calls `workflow_verify_branch`,
  dying with a new `EXIT_BRANCH_MISMATCH` (8) before ever invoking an agent if it fails.
- **`scripts/workflow-approve.sh`**: the report-discovery loop keeps its three existing
  `<TASK_ID>-completion-report.md` candidates unchanged, then — only for a task ID matching
  `^DASH-([0-9]{3})$` whose registry row was already found in
  `docs/agentos-dashboard/STAGE_REGISTRY.md` — cross-checks that number against the digits
  embedded in the registry's own Branch cell and, only if they agree, additionally considers
  `docs/reports/agentos-dashboard/STAGE-<2 digits>-completion.md`. A new exit code,
  `EXIT_REPORT_CONFLICT` (18), covers two present reports with differing content.
- **`docs/agentos-dashboard/OPEN_QUESTIONS.md`**: OD-D10 and OD-D11 moved from Open to Resolved
  (append-only relocation, original question/recommendation text preserved, Disposition updated).
- **`docs/agentos-dashboard/DECISIONS.md`**: new DD-08 recording the rationale for both
  resolutions.
- Governance/handoff records: `docs/TASK_QUEUE.md`, `docs/current_task.md`,
  `docs/remaining_tasks.md`, `docs/PROJECT_STATE.md`, `docs/DECISION_LOG.md`, `docs/CHANGELOG.md`,
  `handover/PROJECT_HANDOVER.md`, `handover/PROJECT_CHECKSUM.md`.

## Scope decision

The runner prompt (`scripts/prompts/implement-next-task.md`) was **not** modified, even though it
is named in GOV-AUTO-04's allowed paths and OD-D10's own recorded recommendation (b) proposed
giving it an explicit branch-creation exception. Recommendation (a) — automatic preparation by the
authorization gate — was chosen instead: it resolves the conflict without weakening the runner
prompt's blanket no-branch-mutation guarantee for every other kind of task, and by the time an
implementation session starts under this design, the branch already exists, so no exception is
needed. This is recorded here as a deliberate choice between the two recommendations OD-D10 itself
offered, not an omission.

Path-traversal rejection for the canonical report name is structural rather than a separate
explicit check: the two-digit stage number is derived only from digits already confirmed to match
the registry's own Branch cell, and `printf '%02d'` on a small validated integer can never produce
`..` or a path separator — there is no user-controlled string ever concatenated into the
constructed path.

## Validation

All commands run via `conda run -n ai-workflow-engine`.

- `pytest tests/test_workflow_branch_prepare.py tests/test_workflow_authorize_script.py
  tests/test_workflow_runner_scripts.py tests/test_workflow_report_discovery.py
  tests/test_workflow_approve_closeout.py` → **147 passed**.
- `pytest tests agentos_workflow/tests` → **2726 passed, 0 failed**. No pre-existing failure
  reproduced this session (the `test_dry_run.py` `engine_version` mismatch GOV-2/GOV-3 each
  recorded as pre-existing and environment-dependent did not occur in this run).
- `ruff check --no-cache .` → **All checks passed!** (two long-line and one unused-import finding
  in the new test files were fixed during this pass; see Self-review.)
- `black --check .` → one new test file needed reformatting, applied; **All done!**, all files
  left unchanged on the re-check.
- `mypy --no-incremental src` → **Success: no issues found in 56 source files.**
- `mypy --no-incremental agentos_workflow` → **Success: no issues found in 63 source files.**
- `git diff --check` → clean.
- `workflowctl verify --config self-governance.yaml` → **Verdict: PASS** (git, task-state,
  governance, registries, handover).
- `bash -n` and `shellcheck` on all three modified scripts and the new library → clean (only
  shellcheck's info-level SC1091 for the dynamic `source` path, already annotated with a
  `# shellcheck source=` directive, exactly as this repository's existing scripts already do).

## Tests Added or Updated

`tests/test_workflow_branch_prepare.py` (new, 16 tests): `workflow_registered_branch` found in
either registry and empty when absent; `workflow_prepare_branch` no-op on GOV/plain tasks,
creation from a clean default branch, idempotent switch when already on/at the required branch,
and refusal (no mutation) on a dirty worktree, wrong starting branch, or a diverging existing
branch; `workflow_verify_branch` passes with no registry row or a matching branch and fails with a
message naming both branches on mismatch; a static check that the library never contains `eval`,
`git push`, `git merge`, `--hard`, or a branch-deletion verb.

`tests/test_workflow_authorize_script.py` (fixture updated to include the new library; 4 new
tests): the working-branch line is reported; a GOV-family task (no registry row) stays on the
default branch; a branch-preparation failure after a successful commit is reported distinctly
(`exit 10`) without rolling back the authorization commit; and the existing
`test_governance_transition_and_commit_are_consistent` assertion was updated from "branch
unchanged" to "branch switched to the registered branch, at the same commit as the default
branch" — the intended behavior change this task makes, not a defect.

`tests/test_workflow_runner_scripts.py` (fixture updated to include the new library; 3 new tests):
launch is blocked with the mismatch reported and no agent invoked when the Current task's
registered branch differs from the working branch; launch proceeds and the agent runs when they
match; and a Current task with no registered branch (empty Branch cell) never blocks launch.

`tests/test_workflow_report_discovery.py` (new, 6 tests, self-contained DASH/AUTO sandbox
fixtures): the canonical name is discovered directly with no duplicate ever created; a
byte-identical duplicate alongside the canonical name is accepted; a genuine content conflict
between the two is refused with no mutation; a malformed registry (Branch cell not encoding the
task's own stage number) disables the canonical lookup and the closeout still refuses safely; a
DASH task with no report at all is still rejected; and an AUTO-family registry-governed task's
existing exact-name discovery is unaffected (regression guard).

## Self-review

Re-read the whole diff once, looking for the four things the task workflow names.

- **Scope creep.** Every change is confined to GOV-AUTO-04's allowed-file list: the three
  wrapper scripts, the new `scripts/lib/branch_prepare.sh`, the matching `tests/**workflow**`
  files, `docs/agentos-dashboard/OPEN_QUESTIONS.md` and `DECISIONS.md`, and the standard
  governance/handoff documents. Nothing under `agentos_workflow/agents/**`,
  `agentos_workflow/orchestrator/**`, `src/`, or dashboard runtime code was touched. The runner
  prompt was deliberately left unmodified (see "Scope decision").
- **A test that passes trivially.** Every new assertion was checked against what the *old* code
  path would produce: `test_governance_transition_and_commit_are_consistent`'s updated branch
  assertion is the one that actually caught the new behavior mid-implementation (it failed with
  `main != feature/auto-002` before this fix, proving it exercises real behavior, not a restated
  no-op); the report-discovery conflict/malformed-registry tests each assert a specific refusal
  exit code and zero mutation, not just "something failed"; the branch-mismatch test for
  `workflow-next.sh` asserts the agent stub's log file does not exist, so it would fail if the
  precondition were silently skipped.
- **A silently swallowed failure.** Every new refusal path in `branch_prepare.sh` prints one
  diagnostic to stderr and returns non-zero; every caller (`workflow-authorize.sh`,
  `workflow-next.sh`) checks that return value explicitly with `die`. `workflow-approve.sh`'s new
  canonical-lookup block only ever *adds* a candidate path or refuses outright on conflict; it
  never silently prefers one report over another when they disagree.
- **Unintended Git or network calls.** `scripts/lib/branch_prepare.sh` contains exactly one
  mutating Git verb, `git checkout` (branch creation/switch, the routine's entire purpose), gated
  behind the clean-tree and exact-branch checks above; grepped all three modified scripts and the
  library for `git push`, `git merge`, `git reset`, `--hard`, and `git rebase` — none found beyond
  what already existed.

Found and fixed during this pass: two ruff line-length findings and one unused import in the new
test files (`tests/test_workflow_branch_prepare.py`, `tests/test_workflow_report_discovery.py`),
and one black reformat in `tests/test_workflow_branch_prepare.py` — all style-only, no assertion
changed.

This is an ordinary governance/developer-experience task — not a milestone, release, or
trust-boundary change in the sense of adding a new capability the engine did not have before — so
a bounded self-review is the standard and no independent review is mandated. It does touch the
scripts that gate every future authorization/approval action, so the Human Owner may reasonably
want a closer look at `scripts/lib/branch_prepare.sh`'s refusal conditions before approving; that
is a recommendation, not a claim that independent review was performed here.

## Limitations and follow-ups

- `workflow_prepare_branch`'s divergence check compares the existing branch's tip to the exact
  current HEAD; it does not attempt a fast-forward or any merge — any prior state on that branch
  name other than the exact expected commit is refused, by design, rather than reconciled.
- The DASH canonical-report cross-check assumes the Branch cell encodes the stage number as
  `dash-NNN-` with exactly three digits, matching every row in
  `docs/agentos-dashboard/STAGE_REGISTRY.md` today; a future stage using a different Branch-name
  shape would simply fall back to requiring the exact `<TASK_ID>-completion-report.md` name,
  never silently misfire.
- **Two pre-existing documentation drifts were observed, not fixed** (outside this task's scope):
  `docs/PROJECT_STATE.md`'s "In progress" section had continued narrating GOV-AUTO-03 as active
  for several task cycles after its own closure; this session added GOV-AUTO-04's entry above it
  without touching the stale GOV-AUTO-03 text. `docs/remaining_tasks.md`'s prose paragraph had not
  been updated to record DASH-003's approval and closure; since that gap was immediately adjacent
  to this session's own edit and trivially verifiable against `docs/TASK_QUEUE.md`, it was
  corrected in passing. Neither is machine-checked by `workflowctl verify` (both are free
  narrative prose, not the parsed task-status fields), so neither gate result depends on this
  observation; recorded here for a Human Owner decision on whether a future task should sweep
  `PROJECT_STATE.md`'s "In progress"/"Planned" sections for similar staleness.

## Review and Git

No commit, push, merge, branch change, or stash operation was performed; the complete diff is
left in the working tree for Human Owner inspection.

## Addendum — Human Owner approval and closure (2026-07-29)

The Human Owner reviewed this report and the implementation diff, typed the two exact `APPROVE`
confirmations required by `scripts/workflow-approve.sh`, and approved the Conventional Commit
message `fix(workflow): automate registered branches and canonical report discovery (GOV-AUTO-04)`. The script then performed the deterministic governance closeout
recorded in `docs/DECISION_LOG.md`'s matching entry and staged the approved implementation
together with the generated closeout records in one local commit. This commit's hash, and any
later publication or merge, are recorded separately — a commit cannot record its own hash.
