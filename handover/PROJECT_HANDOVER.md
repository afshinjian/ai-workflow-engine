# Project Handover

Narrative context transfer between sessions. This file is checksum-verified by
`handover/PROJECT_CHECKSUM.md`; cross-check its claims against Git and the configured validation
commands.

## Where things stand (2026-07-28)

The released `ai-workflow-engine` 1.0.0 roadmap is complete. In the post-1.0 programs:

- DASH-001 is `Done`; DASH-002..DASH-010 remain `Planned`.
- AUTO-001, AUTO-002, and AUTO-003 are `Done` and registry `COMPLETE`.
- **GOV-AUTO-01 is `Done`** as of 2026-07-28 — implemented, validated, approved, committed as
  `a302c95`, and merged into `main` via `a3b5b0a`.
- **AUTO-004 — Claude Code CLI and Codex CLI providers is `Current`**, registry `IN_PROGRESS`,
  implemented and validated on `feature/auto-004-model-providers`, **uncommitted**, awaiting Human
  Owner approval.
- AUTO-005..AUTO-007 remain `Planned`/`NOT_STARTED`. **AUTO-005 is explicitly not authorized.**
- GOV-2 remains `Planned`.

### Correction to the previous handover

The 2026-07-27 edition of this file was stale and should not be trusted if encountered in an old
context: it reported HEAD as `908be94` on the AUTO-003 branch and described GOV-AUTO-01 as
uncommitted and awaiting approval. Both AUTO-003's and GOV-AUTO-01's commits were subsequently
merged into `main`. It also left open the question of whether AUTO-003's closure to `Done` should
be reverted; the Human Owner's 2026-07-28 decision settles it — AUTO-003 stays `Done`.

## Current Git state

| Fact | Value |
|---|---|
| Branch | `feature/auto-004-model-providers` |
| Created from | clean `main` at `a3b5b0a` |
| Upstream | **none** — this branch has never been pushed |
| Worktree | dirty by design: the complete AUTO-004 diff awaits inspection |
| Stashes | `stash@{0}`, `stash@{1}` — both untouched since before AUTO-002 |

`main` is at `a3b5b0a` and matches `origin/main`. That merge brought both `908be94` (AUTO-003) and
`a302c95` (GOV-AUTO-01) onto the baseline, so neither is outstanding any longer.

`workflowctl check-git` reports `upstream_missing` on this branch. That is expected and
pre-existing for a stage branch never intended to be pushed — the tolerance
`STAGE_REGISTRY.md` §3 rule 16 and the SSP both name. Every other configured check passes.

## AUTO-004 — current state

Authorized by the Human Owner on 2026-07-28 in a decision that first closed GOV-AUTO-01 to `Done`,
freeing the single `Current` slot under `maximum_current_tasks: 1`. That closure was itself the
resolution of a rule-16 predecessor conflict this session detected and reported rather than
resolving on its own initiative (`docs/DECISION_LOG.md`, 2026-07-28;
`docs/workflow-automation/STAGE_REGISTRY.md` §5).

Delivered the Model Provider layer in `agentos_workflow/providers/`
(`docs/workflow-automation/MODEL_PROVIDER_CONTRACTS.md`):

- `base.py` — the `Provider` interface (`kind` + `invoke`, nothing else), the shared
  `CLIProvider` invocation sequence, the typed failure/report types, the provider subprocess
  primitive (prompt on stdin, fixed argv, bounded timeout), and the environment allowlist.
- `claude_cli.py` — implementation and repair provider; unwraps the CLI's result envelope.
- `codex_cli.py` — independent QA provider; reads the last JSON object from a JSON Lines stream.
- `mock.py` — offline substitute, structurally excluded from live selection on four counts.
- `__init__.py` — the live role→provider registry, typed to return a `CLIProvider`.

Nothing raises to the Orchestrator. Retry classification follows the "*when*, not *what*" rule:
spawn failure is the only proven-pre-side-effect case. Session isolation is a per-invocation
`0o700` directory with `TMPDIR` pointed into it. Only allowlisted environment variables reach a
provider process; `HOME` is never forwarded implicitly.

Validation: 106 focused tests, 1,332 engine tests, 1,037 in `tests/` (collection unchanged);
ruff, black, mypy, and `pre-commit` clean; `git diff --check` clean; `workflowctl verify` green
except the pre-existing `upstream_missing`. Full detail:
`docs/reports/workflow-automation/AUTO-004-completion-report.md`.

Two defects were found and fixed during the stage's own self-review rather than merely recorded:
redacting stdout before JSON parsing destroyed valid reports (notably the credential-related QA
findings an operator most needs), and the session directory was created but never actually handed
to the CLI. Both are described in the report's Known limitations section.

**Nothing is committed.** Approval and commit are the Human Owner's next act.

## Known open risk

The two providers' argv shapes (`--print --output-format json`, `exec --json`) are defined by this
stage but **not verified against a live CLI** — `MODEL_PROVIDER_CONTRACTS.md` §7 assigns the
invocation shape to AUTO-004 while the stage contract assigns real end-to-end invocation to
AUTO-007. If a live CLI rejects a flag, the fix is one line in that provider's `_ARGV_SUFFIX`.

## Next session

1. Verify `git status`, recent history, and this handover checksum.
2. Confirm AUTO-004 is the only `Current` task.
3. AUTO-004 awaits **Human Owner approval**. Do not commit it without a fresh instruction.
4. Publication decisions remain open and unauthorized: pushing or merging anything on this branch,
   and anything to do with AUTO-005.

Completing a task never authorizes its successor. AUTO-005 requires its own fresh written
authorization naming it.
