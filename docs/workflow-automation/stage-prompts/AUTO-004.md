# AUTO-004 — Claude Code CLI and Codex CLI Providers

| Field | Value |
|---|---|
| **Stage** | AUTO-004 · Role: Engine implementation session |
| **Branch** | `feature/auto-004-model-providers` |
| **Commit message** | `feat(workflow): add Claude Code CLI and Codex CLI provider adapters (AUTO-004)` |
| **Report** | `docs/reports/workflow-automation/AUTO-004-completion-report.md` |
| **Status/Version** | Draft · 1.0 |

Apply the Standard Stage Protocol in `README.md` in full.

## Canonical Prompt

You are the **Engine implementation session** executing **AUTO-004 — Claude Code CLI and Codex
CLI providers**. Preconditions: AUTO-002 `COMPLETE`; recorded authorization
"I authorize AUTO-004"; branch `feature/auto-004-model-providers` from clean `main`.

**Allowed**: create `agentos_workflow/providers/{__init__.py, base.py, claude_cli.py,
codex_cli.py, mock.py}`, `agentos_workflow/tests/**`, plus SSP-required documentation/report
updates.

**Build**: the common `Provider` interface (`../MODEL_PROVIDER_CONTRACTS.md` §1);
`ClaudeCLIProvider` and `CodexCLIProvider` as subprocess adapters over the configured executable
+ timeout (`../CONFIGURATION_MODEL.md`), passing only the target repository's
`allowed_environment_variables`; `MockProvider` returning configurable canned reports for tests
and dry runs, structurally excluded from any code path that selects a provider for a real
authorized workflow (`../MVP_SCOPE.md` §3). Session isolation between `ClaudeCLIProvider` and
`CodexCLIProvider` invocations per `../MODEL_PROVIDER_CONTRACTS.md` §5.

**Tests**: subprocess invocation mocked at the process boundary (no real CLI required for the
default suite); environment-variable allowlist enforcement (nothing outside the allowlist is
forwarded); timeout enforcement and typed timeout error; `MockProvider` drop-in equivalence
against the same interface used by `ClaudeCLIProvider`/`CodexCLIProvider`; isolation test
proving no shared state/object crosses between two provider instances in the same workflow.

**Out of scope**: Agents that decide when to call which provider — AUTO-005. Real end-to-end
invocation of a live Claude/Codex CLI — AUTO-007 (opt-in only).

Write the report, recommend the commit message above, then STOP per SSP.

## Stage-Specific Notes

Reference: `../SECURITY_MODEL.md` §1 (secrets), §3 (session isolation). No credentials are ever
constructed, stored, or logged by this stage's code.
