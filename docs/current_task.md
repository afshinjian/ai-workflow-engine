# Current Task

Mirror of `docs/TASK_QUEUE.md`'s `Current` set. Must contain exactly the same task ID(s) at the
same status as the task queue — `workflowctl check-task-state` fails otherwise.

## AUTO-004 — Claude Code CLI and Codex CLI Providers

Status: Current

Authorized by the Human Owner on 2026-07-28 ("I authorize AUTO-004 — Claude Code CLI and Codex
CLI providers"). Registry state `IN_PROGRESS`
(`docs/workflow-automation/STAGE_REGISTRY.md` §4, §5). The same decision first closed
GOV-AUTO-01 `Current → Done` — implemented, validated, approved, committed as `a302c95`, merged
into `main` via `a3b5b0a` — so AUTO-004 is the single `Current` task under
`maximum_current_tasks: 1`.

Scope — create or modify only: `agentos_workflow/providers/{__init__.py, base.py, claude_cli.py,
codex_cli.py, mock.py}`, `agentos_workflow/tests/**`, and the SSP-required
documentation/report/governance/handoff files. `src/`, `tests/`, `scripts/`, `examples/`,
`pyproject.toml`, and `self-governance.yaml` are untouched; the engine's default `pytest`
collection must be provably unchanged. No dependencies added.

Objective: implement the Model Provider layer of
`docs/workflow-automation/MODEL_PROVIDER_CONTRACTS.md` — the common `Provider` interface (§1),
`ClaudeCLIProvider` (§2) and `CodexCLIProvider` (§3) as subprocess adapters over the configured
executable and timeout (`CONFIGURATION_MODEL.md`) that forward only the target repository's
`allowed_environment_variables` (`SECURITY_MODEL.md` §1), `MockProvider` (§4) as an offline
substitute structurally excluded from any real authorized workflow (`MVP_SCOPE.md` §3), and
session isolation between provider invocations (§5, `SECURITY_MODEL.md` §3). No credentials are
ever constructed, stored, or logged.

Out of scope: the Agents that decide when to call which provider (AUTO-005) and real end-to-end
invocation of a live Claude/Codex CLI (AUTO-007). Commit, push, merge, and beginning AUTO-005 are
explicitly prohibited; the stage stops for Human Owner approval.
