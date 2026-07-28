# Project Handover

Narrative context transfer between sessions. This file is checksum-verified by
`handover/PROJECT_CHECKSUM.md`; cross-check its claims against Git and the configured validation
commands.

## Where things stand (2026-07-28)

The released `ai-workflow-engine` 1.0.0 roadmap is complete. In the post-1.0 programs:

- DASH-001 is `Done`; DASH-002..DASH-010 remain `Planned`.
- AUTO-001, AUTO-002, AUTO-003, and **AUTO-004** are `Done` and registry `COMPLETE`.
- GOV-AUTO-01 is `Done` — committed as `a302c95`, merged into `main` via `a3b5b0a`.
- **AUTO-004 was approved and closed on 2026-07-28** — implemented, validated, approved by the
  Human Owner, committed as `84616d5`, and authorized for publication into `main` under the same
  decision.
- AUTO-005..AUTO-007 remain `Planned`/`NOT_STARTED`, each requiring its own fresh written
  authorization naming it.
- GOV-2 remains `Planned`.

No task is `Current` as of this commit. That is a legal state: `maximum_current_tasks: 1` is a
ceiling, not a quota.

## What this commit is

This is the **AUTO-004 governance closure commit** — records only, no runtime code. It exists
because the Human Owner's closure-and-publication decision requires `main`, after the merge, to
carry a consistent record set (task queue, both mirrors, project state, stage registry, both
changelogs, decision log, this handover, and the checksum) showing AUTO-004 `Done`/`COMPLETE`. The
implementation itself is `84616d5`, which this commit does not touch.

The AUTO-004 completion report was **not** rewritten. Its Confirmation section says no commit was
performed, which was true when written — `84616d5` came afterwards. The commit, the approval, and
the merge are recorded in a new append-only addendum at the end of that report, a new
`docs/workflow-automation/STAGE_REGISTRY.md` §5 row, and `docs/DECISION_LOG.md`
(`STAGE_REGISTRY.md` §3 rule 8; the Human Owner's explicit instruction).

## Current Git state

| Fact | Value |
|---|---|
| Branch | `feature/auto-004-model-providers` |
| Created from | clean `main` at `a3b5b0a` |
| Implementation commit | `84616d5` — the approved AUTO-004 work |
| This commit | governance closure records for AUTO-004 |
| Next step | push this branch, merge into `main`, push `main` (authorized) |
| Stashes | `stash@{0}`, `stash@{1}` — both untouched since before AUTO-002 |

## AUTO-004 — what was delivered

The Model Provider layer in `agentos_workflow/providers/`
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

Validation at implementation time: 106 focused tests, 1,332 engine tests, 1,037 in `tests/`
(collection unchanged); ruff, black, mypy, and `pre-commit` clean; `git diff --check` clean;
`workflowctl verify` green except the pre-existing `upstream_missing`. Full detail:
`docs/reports/workflow-automation/AUTO-004-completion-report.md`.

## Known open risk

The two providers' argv shapes (`--print --output-format json`, `exec --json`) are defined by
AUTO-004 but **not verified against a live CLI** — `MODEL_PROVIDER_CONTRACTS.md` §7 assigns the
invocation shape to AUTO-004 while real end-to-end invocation is AUTO-007's. If a live CLI rejects
a flag, the fix is one line in that provider's `_ARGV_SUFFIX`.

## Next session

1. Verify `git status`, recent history, and this handover checksum.
2. Confirm which task, if any, is `Current` — read `docs/TASK_QUEUE.md`, not this file alone.
3. AUTO-005 requires its own fresh written authorization naming it. Closing AUTO-004 authorized
   no successor (`docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 16).
4. Never delete either stash, and never delete `feature/auto-004-model-providers` — the Human
   Owner's decision explicitly retained it.
