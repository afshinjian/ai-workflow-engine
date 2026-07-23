# AgentOS Workflow Automation — Security Model

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Security Model |
| **Purpose** | Secrets handling, session isolation, forbidden operations, and destructive-operation preconditions. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Documentation & Governance session (AUTO-001) · Human Owner (approval) |
| **Dependencies** | `SKILL_CONTRACTS.md`, `MODEL_PROVIDER_CONTRACTS.md` |
| **Related Documents** | `MACHINE_GATES.md` §5, `AUDIT_MODEL.md`, `CONFIGURATION_MODEL.md` |

## Table of Contents
1. Secrets Handling · 2. Forbidden Git/GitHub Operations · 3. Session Isolation ·
4. No Admin Bypass · 5. Destructive-Operation Preconditions · 6. Repository Identity Guard ·
7. Scope Enforcement · 8. Decision References · 9. Open Questions · 10. Future Revisions

## 1. Secrets Handling

- Secrets and tokens are **never stored** by the workflow engine — not in workflow state, not
  in audit records, not in reports, not in configuration files it writes.
- Every target-repository configuration declares an explicit `allowed_environment_variables`
  allowlist (`CONFIGURATION_MODEL.md`); only those variables are passed to a Model Provider or
  Skill subprocess. Everything else in the operator's environment is not forwarded.
- Command output (stdout/stderr) is sanitized before it is referenced in an audit record or
  report: known secret-shaped patterns (tokens, keys, credential-looking strings) are redacted,
  and raw output is stored only as a file reference under the configured audit directory, never
  inlined into a report or log line that might be copied elsewhere (`AUDIT_MODEL.md` §2). Exact
  redaction rules are `OPEN_QUESTIONS.md` OD-2, resolved before AUTO-003/AUTO-004 ship code.
- Authorization and audit records never include raw credentials, even redacted-in-place; they
  reference the environment allowlist by variable name only, never by value.

## 2. Forbidden Git/GitHub Operations

Under all conditions, the workflow engine never:

- Commits directly to the configured baseline branch.
- Pushes directly to the configured baseline branch.
- Force-pushes, to any branch.
- Rewrites Git history (`rebase`, `commit --amend`, `reset --hard` against shared history).
- Bypasses GitHub branch protection.
- Uses a GitHub admin-bypass merge path (`gh pr merge --admin` is never called, under any
  condition — `MACHINE_GATES.md` §5).
- Merges without every required machine gate passing.
- Deletes a branch without the corresponding merge/cleanup precondition independently verified
  first (§5).

These are structural constraints on the Skill layer (`SKILL_CONTRACTS.md` §5): the Skills that
can mutate Git/GitHub state have argv shapes that make the forbidden operations unreachable,
not merely policy comments — mirroring this repository's own `GitWriter` design principle
(typed methods, fixed argv, force-push/history-rewrite structurally absent).

## 3. Session Isolation

`ClaudeCLIProvider` and `CodexCLIProvider` sessions never share process state, prompts, or raw
output with each other (`MODEL_PROVIDER_CONTRACTS.md` §5). This is a security boundary as well
as a correctness one: an implementation session compromised or manipulated (e.g. via a
prompt-injection attempt inside target-repository content) cannot directly influence the
independent QA session's verdict, since QA only ever receives the diff and deterministic
validation results — not the implementation session's reasoning or transcript.

## 4. No Admin Bypass

No component in this system — CLI, Orchestrator, any Agent, any Skill — has a code path that
invokes an administrative override of GitHub branch protection or required checks. This is
true even in `FAILED` or manual-recovery scenarios: recovery from a stuck merge is a human
action taken outside this engine, never a fallback the engine itself performs.

## 5. Destructive-Operation Preconditions

Every destructive Skill (`create_stage_branch` is non-destructive; `checkout_baseline`,
`fast_forward_pull`, `delete_local_branch`, `delete_remote_branch` are destructive with respect
to local state) re-verifies its specific precondition **immediately before execution**, not
only earlier in the workflow:

- `delete_local_branch` / `delete_remote_branch` — only after `verify_merge_completion` has
  independently confirmed the corresponding PR is merged.
- `fast_forward_pull` — only performs a fast-forward; any divergence is a hard refusal, never a
  forced update.
- `checkout_baseline` — only after confirming no uncommitted stage-branch work would be lost.

## 6. Repository Identity Guard

Every workflow verifies target repository identity (`verify_repository_identity`) before any
mutation and again as part of the precondition gate re-check on resume
(`WORKFLOW_STATES.md` §6). The workflow never continues when identity cannot be verified
(`HUMAN_AUTHORIZATION_MODEL.md` §4).

## 7. Scope Enforcement

`validate_allowed_paths` and `detect_future_stage_work` (`SKILL_CONTRACTS.md` §3) run as part
of the deterministic validation gate (`MACHINE_GATES.md` §3) on every implementation and every
repair attempt — scope creep is a validation failure, not a warning, and triggers the same
repair/fail path as a test failure.

## 8. Decision References
DD-01, DD-05.

## 9. Open Questions
OD-2 (secret-redaction implementation).

## 10. Future Revisions
Any relaxation of §2 or §4 is out of scope for this program permanently unless a future,
explicitly separate governance decision overrides it — this document does not anticipate that
happening and defines no mechanism for it.
