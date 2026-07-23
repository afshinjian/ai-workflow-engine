# AgentOS Workflow Automation — Configuration Model

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Configuration Model |
| **Purpose** | Per-target-repository configuration schema; the baseline branch is never hard-coded globally. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Documentation & Governance session (AUTO-001) · Human Owner (approval) |
| **Dependencies** | `TARGET_REPOSITORY_MODEL.md` |
| **Related Documents** | `SECURITY_MODEL.md` §1, `AUDIT_MODEL.md` §5, `CLI_SPEC.md` |

## Table of Contents
1. Principle · 2. Discovery · 3. Schema · 4. Validation Rules · 5. Example ·
6. Decision References · 7. Open Questions · 8. Future Revisions

## 1. Principle

Every target repository has its own configuration. **No field in this schema — especially the
baseline branch — is ever hard-coded globally in the workflow engine.** `main` is only
`ai-workflow-engine`'s own baseline; it has no special status to the engine when automating any
other repository.

## 2. Discovery

A target repository's configuration lives at `<target-repo>/.agentos/workflow.yaml` by
convention. The CLI also accepts an explicit `--config <path>` override
(`CLI_SPEC.md`). Discovery never guesses or defaults the baseline branch when the file is
absent — a missing configuration is a precondition failure, not an assumed-`main` fallback.

## 3. Schema

| Field | Type | Required | Description |
|---|---|---|---|
| `repository_path` | path | yes | Absolute local path to the target repository. |
| `repository_identity` | string | yes | Expected identity used by `verify_repository_identity` (e.g. canonical remote URL). |
| `remote_name` | string | yes | Git remote to push to / read PR state from (e.g. `origin`). |
| `baseline_branch` | string | yes | The repository's own protected branch (e.g. `main`, `recovery/project-baseline`). Never defaulted globally. |
| `stage_contract_directory` | path | yes | Where stage contracts live in the target repository. |
| `stage_branch_naming` | string (template) | yes | Naming convention for stage branches (e.g. `governance/{stage_id}-{slug}`). |
| `test_command` | string | yes | Command `run_tests` executes. |
| `lint_command` | string | yes | Command `run_lint` executes. |
| `formatting_command` | string | yes | Command `run_formatting_checks` executes. |
| `security_command` | string | yes | Command `run_security_checks` executes. |
| `required_github_checks` | list[string] | yes | Checks `read_required_checks` must see pass before merge. |
| `merge_method` | enum | yes | Fixed to `squash` for this program (`MVP_SCOPE.md`); present so intent is explicit, not implicit. |
| `claude_cli_executable` | path | yes | Local Claude Code CLI executable. |
| `claude_cli_timeout_seconds` | integer | yes | Hard timeout for `ClaudeCLIProvider` invocations. |
| `codex_cli_executable` | path | yes | Local Codex CLI executable. |
| `codex_cli_timeout_seconds` | integer | yes | Hard timeout for `CodexCLIProvider` invocations. |
| `allowed_environment_variables` | list[string] | yes | Allowlist forwarded to Skill/Provider subprocesses (`SECURITY_MODEL.md` §1). |
| `allowed_changed_paths` | list[glob] | yes | Paths a stage implementation may touch. |
| `forbidden_changed_paths` | list[glob] | yes | Paths a stage implementation must never touch, even if not covered by `allowed_changed_paths`. |
| `repair_attempt_limit` | integer | yes | Fixed to `3` for this program (`FAILURE_RECOVERY.md` §1); present for explicitness, not for raising above policy. |
| `state_directory` | path | yes | Local, persistent workflow-state storage location. |
| `audit_directory` | path | yes | Local audit-record storage location (`AUDIT_MODEL.md` §5). |

## 4. Validation Rules

- Every path field must resolve inside the target repository or an explicitly configured local
  state/audit root — no path may resolve outside the intended boundary (mirrors this
  repository's own root-confinement discipline).
- `merge_method` and `repair_attempt_limit` are schema fields for explicitness and auditability,
  not knobs a target-repository operator can use to raise the repair limit above 3 or change the
  merge method away from squash-via-PR in this program's MVP (`MVP_SCOPE.md`).
- `allowed_environment_variables` must never include a wildcard that would forward the entire
  environment.
- `baseline_branch` must be independently verifiable as an existing, real branch at
  precondition-check time; it is never assumed correct from configuration alone.

## 5. Example (illustrative, not a real target)

```yaml
repository_path: /home/user/some-other-repo
repository_identity: github.com/org/some-other-repo
remote_name: origin
baseline_branch: main
stage_contract_directory: docs/some-program/stage-prompts
stage_branch_naming: "governance/{stage_id}-{slug}"
test_command: "pytest"
lint_command: "ruff check ."
formatting_command: "black --check ."
security_command: "bandit -r src"
required_github_checks: ["ci/tests", "ci/lint"]
merge_method: squash
claude_cli_executable: /usr/local/bin/claude
claude_cli_timeout_seconds: 1800
codex_cli_executable: /usr/local/bin/codex
codex_cli_timeout_seconds: 1800
allowed_environment_variables: ["PATH", "HOME", "LANG"]
allowed_changed_paths: ["docs/some-program/**"]
forbidden_changed_paths: ["src/**", "tests/**", ".github/**"]
repair_attempt_limit: 3
state_directory: /home/user/.agentos/state/some-other-repo
audit_directory: /home/user/.agentos/audit/some-other-repo
```

## 6. Decision References
DD-02.

## 7. Open Questions
OD-5 (final configuration file location/naming convention).

## 8. Future Revisions
New fields are additive (MINOR); changing the meaning of an existing field, or introducing any
global default for `baseline_branch`, is explicitly prohibited by this document's Principle
(§1) and would require rewriting it, not just extending it.
