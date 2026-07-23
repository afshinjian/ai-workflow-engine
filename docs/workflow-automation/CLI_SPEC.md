# AgentOS Workflow Automation — CLI Specification

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — CLI Specification |
| **Purpose** | Command surface for the `agentos workflow` CLI namespace. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Documentation & Governance session (AUTO-001) · Human Owner (approval) |
| **Dependencies** | `HUMAN_AUTHORIZATION_MODEL.md`, `CONFIGURATION_MODEL.md` |
| **Related Documents** | `WORKFLOW_STATES.md`, `AUDIT_MODEL.md` |

## Table of Contents
1. Namespace · 2. Commands · 3. Common Options · 4. Exit Codes · 5. Output ·
6. Decision References · 7. Open Questions · 8. Future Revisions

## 1. Namespace

All commands live under `agentos workflow`, in the package `agentos_workflow/cli.py`
(`ARCHITECTURE.md` §4). The CLI contains no business logic; every command forwards to the
Orchestrator and reports its result.

## 2. Commands

| Command | Purpose |
|---|---|
| `agentos workflow authorize <STAGE_ID> --target-repo <path> [--config <path>]` | The single human gate. Captures and validates the authorization binding, then drives the workflow to completion (or `FAILED`) in the foreground unless `--no-run` is given. |
| `agentos workflow status [--target-repo <path>]` | Reports the current state of the active workflow for a target repository (or all configured targets). |
| `agentos workflow resume --target-repo <path>` | Resumes a persisted, still-valid, interrupted workflow (`WORKFLOW_STATES.md` §6). Refuses if the workflow has reached a terminal state or if bound authorization values have drifted. |
| `agentos workflow cancel --target-repo <path>` | Operator abort. Only reachable from `CREATED`/`AUTHORIZED`/`PRECONDITIONS_CHECKED`/`BRANCH_CREATED` (`WORKFLOW_STATES.md` §3); not a human gate (`HUMAN_AUTHORIZATION_MODEL.md` §5). |
| `agentos workflow audit --target-repo <path> [--workflow-id <id>]` | Prints the append-only audit trail for a workflow (`AUDIT_MODEL.md`). |
| `agentos workflow report --target-repo <path> --workflow-id <id>` | Prints the stage/QA/failure/closeout report artifacts for a workflow. |
| `agentos --version` | Prints the workflow engine version (bound into every authorization). |

`agentos workflow authorize` is deliberately the only command that can move a workflow past
`CREATED`; every other command is read-only or restricted to states that predate any
target-repository mutation (`cancel`).

## 3. Common Options

- `--target-repo <path>` — required on every command except `--version`; identifies which
  target repository's configuration and state to use.
- `--config <path>` — overrides the default `<target-repo>/.agentos/workflow.yaml` discovery
  (`CONFIGURATION_MODEL.md` §2).
- `--output {text,json}` — machine-readable output for scripting; JSON output follows the same
  sanitization rules as audit records (`SECURITY_MODEL.md` §1) — never raw secrets.

## 4. Exit Codes

| Code | Meaning |
|---|---|
| `0` | Command succeeded; for `authorize`, the workflow reached `DONE`. |
| `1` | Command-level error (bad arguments, missing configuration). |
| `2` | Workflow reached `FAILED`. |
| `3` | A precondition for the requested command was not met (e.g. `resume` on a non-resumable workflow, `cancel` on a workflow past the cancellable states). |

## 5. Output

Every command's output is deterministic given the same workflow state and never includes raw
secret values, mirroring this repository's own stable-JSON-output discipline
(`docs/architecture.md` in the engine repository) adapted to this program's own schema.

## 6. Decision References
DD-04.

## 7. Open Questions
None blocking AUTO-001; exact flag names/JSON schema are AUTO-002 implementation detail — this
document is binding on behavior, not on final syntax.

## 8. Future Revisions
Adding a new read-only command (e.g. `list`) is additive; adding any command that can move a
workflow past `CREATED` other than `authorize` is a MAJOR change requiring Human Owner review,
since it would introduce a second path to the human gate.
