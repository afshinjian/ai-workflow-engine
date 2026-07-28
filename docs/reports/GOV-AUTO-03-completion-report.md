# GOV-AUTO-03 Completion Report

## Result

`IMPLEMENTED_PENDING_HUMAN_APPROVAL`

Task: GOV-AUTO-03 — Human-Approved Commit with Automatic Task Closeout
Date: 2026-07-28
Repository baseline: `main` at `c8e59fb` (AUTO-006 merge)

## Delivered

- `scripts/workflow-approve.sh` now branches on the same stable `project.id: ai-workflow-engine`
  marker `scripts/workflow-authorize.sh` already uses (plus the full governance file set being
  present). Any other repository — including every pre-existing disposable test sandbox — takes
  the byte-for-byte original GOV-AUTO-01 approval/commit gate. This repository takes a new
  closeout-enabled path.
- Closeout-path task discovery: the single `Current` task is read from the authoritative
  `docs/TASK_QUEUE.md`; zero or multiple `Current` tasks, a duplicate task heading, a
  `docs/current_task.md` or `docs/remaining_tasks.md` mirror disagreement, an unmet stage-registry
  agreement (state, or a mismatched required branch), blocked-language in the task's own section,
  or a missing completion report all fail closed before any Human prompt or any file mutation.
- Approval-evidence binding: the approved Conventional Commit message must literally name the
  Current task ID, in addition to the existing shape/length checks, or the gate refuses before
  generating anything.
- Full transition display (task ID, title, branch, base HEAD, implementation files, the governance
  files closeout will generate/update, and the proposed commit message) before either of the two
  existing exact `APPROVE` confirmations — reusing exactly two confirmations, not a third.
- Deterministic closeout generation, entirely via `awk`-guarded, precondition-checked replacements
  (never broad free-form text substitution): task queue `Current → Done`; `current_task.md`
  rewritten to the empty-Current template; the task's row removed from `remaining_tasks.md`;
  `docs/PROJECT_STATE.md` either flips an existing per-task heading or appends a plain prose
  bullet under `## Completed` (deliberately never introduces a *new* task-shaped heading, since a
  later stale duplicate would silently out-rank a correct one under this repository's
  first-occurrence-wins task parser); one new append-only `docs/DECISION_LOG.md` entry; one new
  `docs/CHANGELOG.md` `[Unreleased]` bullet; for AUTO/DASH-family tasks, the matching stage
  registry's state flips to `COMPLETE` and a new Authorization Log row is appended, plus the
  program's own changelog if it keeps one; an append-only completion-report addendum (never
  claiming a commit hash, push, or merge — a commit cannot record its own hash); an append-only
  `handover/PROJECT_HANDOVER.md` update; and a regenerated `handover/PROJECT_CHECKSUM.md` row.
- Post-closeout `git diff --check`, `workflowctl check-task-state`, `check-governance`, and
  `check-handover` all re-run before staging; any failure aborts before any commit.
- Fail-closed atomicity: a byte-for-byte backup of every governance file the closeout may touch is
  taken before the first edit. Any failure during generation or post-closeout validation restores
  every one of those files verbatim, restores the index if staging had already begun, and leaves
  the approved implementation diff completely untouched, before printing a diagnostic and exiting
  non-zero. No partial closeout state is ever left on disk.
- Exactly one local commit, containing only the previously-displayed implementation files and the
  fixed closeout file set — verified by re-diffing after generation and refusing any unexpected
  change — followed by `git diff --cached --name-status` / `--check`, then `git commit`. No second
  `git commit` invocation exists anywhere in the script.
- Post-commit branch/upstream/stash equality assertions, and a report of the next `Planned`
  (unauthorized) task.
- `docs/automation-workflow.md` updated: the new standard cycle, the updated state-transition
  diagram (both the closeout-enabled and legacy paths), new safety guarantees, new exit codes
  (`10`-`17`), and new recovery/failure-atomicity documentation, including that a later
  publication/merge may still need its own append-only record because this commit cannot name its
  own future hash.

## Safety Evidence

The closeout branch contains no push, merge, branch-change, upstream-mutation, or stash-mutation
code path — the same forbidden-verb regression test already covering both prior scripts
(`test_scripts_never_push_merge_or_mutate_stashes`) continues to pass unmodified against the
edited file. Every governance edit is a guarded `awk` replacement that exits non-zero (caught and
converted to a fail-closed diagnostic) if its expected heading, status, or table row is missing or
duplicated — never a blind text substitution that could silently touch the wrong row. The legacy
(non-closeout) path is byte-identical in behaviour to the original GOV-AUTO-01 script; it is
reached whenever `self-governance.yaml` lacks the `project.id: ai-workflow-engine` marker.

## Tests Added or Updated

- `tests/test_workflow_approve_closeout.py` (new, 26 tests): task discovery (single/zero/multiple
  Current, duplicate heading, both mirror mismatches, blocked task, missing completion report);
  approval gates (both confirmation declines, exact-token enforcement, invalid message shape,
  message not naming the task, no closeout before confirmation); closeout content (decision log,
  changelog, completion-report addendum, handover, checksum); commit behaviour (implementation +
  closeout in exactly one commit, commit subject, clean final tree, next-Planned reporting, no
  successor authorized); failure atomicity (a broken version fact makes `check-governance` fail
  after closeout has already mutated other files — verified the closeout files are restored
  byte-for-byte and the implementation file is untouched); Git safety (no push/merge/branch
  change/stash mutation against a real bare remote and a real stash).
- `tests/test_workflow_runner_scripts.py` (GOV-AUTO-01, 60 tests) and
  `tests/test_workflow_authorize_script.py` (GOV-AUTO-02, 28 tests): **unmodified**, both still
  green — their sandbox fixtures use `project.id: sandbox` and no governance file set, so they
  exercise the unchanged legacy path.

## Validation

- `pytest -q tests/test_workflow_runner_scripts.py tests/test_workflow_authorize_script.py tests/test_workflow_approve_closeout.py`: PASS — 114 tests.
- `pytest tests agentos_workflow/tests`: PASS — 2,590 tests.
- `ruff check --no-cache .`: PASS.
- `black --check .`: PASS — 148 files unchanged.
- `mypy --no-incremental src`: PASS — 55 source files.
- `mypy --no-incremental agentos_workflow`: PASS — 57 source files.
- `git diff --check`: PASS.
- `bash -n scripts/workflow-authorize.sh`: PASS.
- `bash -n scripts/workflow-next.sh`: PASS.
- `bash -n scripts/workflow-approve.sh`: PASS.
- `shellcheck scripts/workflow-authorize.sh`: PASS (already installed; no installation performed).
- `shellcheck scripts/workflow-next.sh`: PASS.
- `shellcheck scripts/workflow-approve.sh`: PASS.

`workflowctl verify --config self-governance.yaml` was not run as a final gate in this report,
because this repository's own governance files (task queue, mirrors, decision log, changelog,
stage registry, handover, checksum) are themselves part of the diff this report describes — they
now correctly show GOV-AUTO-03 `Current` and pending approval, not yet closed. `check-task-state`,
`check-governance`, and `check-handover` are exercised directly and repeatedly by
`tests/test_workflow_approve_closeout.py` against disposable sandboxes, including the negative
case where they are expected to fail.

## Limitations

- Closeout only *appends* an addendum to an existing completion report; it never authors the
  report body. The canonical implementation prompt already directs the agent to write one before
  approval is requested, so this is ordinarily satisfied by the time `workflow-approve.sh` runs.
- Closeout recognizes stage registries only at the two fixed paths this repository already uses
  (`docs/workflow-automation/STAGE_REGISTRY.md`, `docs/agentos-dashboard/STAGE_REGISTRY.md`) and
  completion reports only under the three fixed `docs/reports/**` conventions already in use. A
  future program with a differently-shaped registry or report path would need the same kind of
  extension `workflow-authorize.sh`'s own registry-candidate loop would also need.
- The task-ID-in-commit-message check is structural evidence, not semantic verification — it
  cannot confirm the message honestly describes the diff, the same limitation the pre-existing
  Conventional-Commit-shape check already has.
- As with GOV-AUTO-01/02, this task carries no stage-registry lifecycle state of its own; it is
  recorded in `docs/workflow-automation/STAGE_REGISTRY.md` §5 for continuity only, per precedent.

## Review and Git

No independent review was performed or claimed. This is an authorization/commit-boundary and
governance-mutation change and should receive Human Owner inspection before commit. The GOV-AUTO-03
implementation has not been committed, pushed, or merged; neither existing stash was modified;
AUTO-007 was not begun.

## Addendum — Human Owner approval and closure (2026-07-28)

The Human Owner reviewed this report and the implementation diff, typed the two exact `APPROVE`
confirmations required by `scripts/workflow-approve.sh`, and approved the Conventional Commit
message `feat(workflow): add automatic task closeout to approval gate (GOV-AUTO-03)`. The script then performed the deterministic governance closeout
recorded in `docs/DECISION_LOG.md`'s matching entry and staged the approved implementation
together with the generated closeout records in one local commit. This commit's hash, and any
later publication or merge, are recorded separately — a commit cannot record its own hash.
