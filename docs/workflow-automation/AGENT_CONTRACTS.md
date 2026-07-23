# AgentOS Workflow Automation — Agent Contracts

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Agent Contracts |
| **Purpose** | Responsibilities, allowed skills, inputs/outputs, and boundaries for each Agent. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Documentation & Governance session (AUTO-001) · Human Owner (approval) |
| **Dependencies** | `ARCHITECTURE.md`, `SKILL_CONTRACTS.md`, `MODEL_PROVIDER_CONTRACTS.md` |
| **Related Documents** | `WORKFLOW_STATES.md`, `MACHINE_GATES.md` |

## Table of Contents
1. Common Agent Rules · 2. PMOAgent · 3. ImplementationAgent · 4. QAAgent · 5. GitAgent ·
6. MergeAgent · 7. CloseoutAgent · 8. Agent-to-State Map · 9. Decision References ·
10. Open Questions · 11. Future Revisions

## 1. Common Agent Rules

- An Agent may only invoke the Skills and Model Providers explicitly listed in its contract.
- An Agent never authorizes anything, never bypasses a machine gate, and never mutates the
  authorization binding.
- An Agent always returns a structured result (success/failure + evidence); the Orchestrator,
  not the Agent, decides the resulting workflow-state transition.
- An Agent never has direct subprocess, filesystem, or network access — every side effect is
  through a named Skill or Model Provider.
- An Agent's output is evidence for the Orchestrator's machine gates, never itself an authority
  (mirrors `ARCHITECTURE.md` §6).

## 2. PMOAgent

**Role:** Precondition verification and stage-branch creation.

**Allowed skills:** `verify_repository_identity`, `inspect_working_tree`,
`inspect_current_branch`, `verify_baseline_ancestry`, `locate_stage_contract`,
`parse_stage_metadata`, `calculate_contract_hash`, `validate_stage_ordering`,
`detect_future_stage_work`, `create_stage_branch`, `append_audit_event`.

**Input:** the bound authorization record (`HUMAN_AUTHORIZATION_MODEL.md`).

**Output:** a precondition report (pass/fail per check) and, on full pass, the created stage
branch name and its base commit SHA.

**Drives transitions:** `AUTHORIZED → PRECONDITIONS_CHECKED → BRANCH_CREATED`.

## 3. ImplementationAgent

**Role:** Implements the stage contract via the default implementation provider, and performs
automatic repair when directed.

**Allowed skills/providers:** `ClaudeCLIProvider`, `inspect_diff`, `list_changed_files`,
`validate_allowed_paths`, `validate_completion_report`, `append_audit_event`.

**Input (implementation):** stage contract, target repository state, stage branch.
**Input (repair):** the latest structured QA report (`validate_qa_report` output) plus the
prior implementation diff.

**Output:** a diff on the stage branch plus a stage completion report artifact.

**Drives transitions:** `BRANCH_CREATED → IMPLEMENTING → VALIDATING`;
`REPAIRING → VALIDATING`.

## 4. QAAgent

**Role:** Independent QA via the default QA provider, isolated from `ImplementationAgent`'s
session.

**Allowed skills/providers:** `CodexCLIProvider`, `run_tests`, `run_lint`,
`run_formatting_checks`, `run_scope_validation`, `run_security_checks`, `run_secret_detection`,
`validate_qa_report`, `generate_qa_report`, `append_audit_event`.

**Input:** the implementation diff, the deterministic validation results, the stage contract.

**Output:** a structured QA report with a pass/fail verdict and findings, independently derived
— never copied from `ImplementationAgent`'s self-report.

**Drives transitions:** `QA_RUNNING → READY_TO_COMMIT` (pass) or `QA_RUNNING → REPAIRING`/
`FAILED` (fail).

## 5. GitAgent

**Role:** Commit, push, and pull-request creation.

**Allowed skills:** `create_commit`, `push_stage_branch`, `create_pull_request`,
`read_pull_request_state`, `verify_head_sha`, `append_audit_event`.

**Input:** the validated, QA-passed diff on the stage branch.

**Output:** commit SHA, pushed ref, PR number/URL.

**Drives transitions:** `READY_TO_COMMIT → COMMITTED → PUSHED → PR_OPEN`.

## 6. MergeAgent

**Role:** Safe automatic squash merge, gated on expected head SHA and required checks.

**Allowed skills:** `verify_head_sha`, `read_required_checks`, `enable_automatic_squash_merge`,
`verify_merge_completion`, `append_audit_event`.

**Input:** the open PR, the expected head SHA recorded when the PR was opened.

**Output:** merge confirmation (only after GitHub independently confirms the merge).

**Drives transitions:** `PR_OPEN → AUTO_MERGE_ENABLED → WAITING_FOR_CHECKS → MERGED`.

**Hard rule:** `MergeAgent` never invokes any admin-bypass merge path (`MACHINE_GATES.md` §5,
`SECURITY_MODEL.md` §4).

## 7. CloseoutAgent

**Role:** Remote/local branch cleanup, baseline checkout and fast-forward update, final
repository verification, closeout reporting.

**Allowed skills:** `checkout_baseline`, `fast_forward_pull`, `delete_local_branch`,
`delete_remote_branch`, `verify_final_repository_state`, `generate_closeout_report`,
`append_audit_event`.

**Input:** the independently-verified `MERGED` state.

**Output:** closeout report, final repository state confirmation.

**Drives transitions:** `MERGED → CLOSING → DONE`.

**Hard rule:** `CloseoutAgent` never begins until `MergeAgent`'s merge confirmation is
independent (GitHub-verified), and never performs destructive cleanup (branch deletion) without
first re-verifying the merge (`FAILURE_RECOVERY.md` §4).

## 8. Agent-to-State Map

| Agent | States driven |
|---|---|
| `PMOAgent` | `AUTHORIZED` → `PRECONDITIONS_CHECKED` → `BRANCH_CREATED` |
| `ImplementationAgent` | `BRANCH_CREATED` → `IMPLEMENTING` → `VALIDATING`; `REPAIRING` → `VALIDATING` |
| `QAAgent` | `QA_RUNNING` → `READY_TO_COMMIT` / `REPAIRING` / `FAILED` |
| `GitAgent` | `READY_TO_COMMIT` → `COMMITTED` → `PUSHED` → `PR_OPEN` |
| `MergeAgent` | `PR_OPEN` → `AUTO_MERGE_ENABLED` → `WAITING_FOR_CHECKS` → `MERGED` |
| `CloseoutAgent` | `MERGED` → `CLOSING` → `DONE` |

Deterministic validation between `VALIDATING` and `QA_RUNNING` is Orchestrator-owned (not a
named Agent) — see `MACHINE_GATES.md` §2.

## 9. Decision References
DD-01, DD-03.

## 10. Open Questions
None blocking AUTO-001; agent implementation detail is AUTO-005 scope.

## 11. Future Revisions
Adding, removing, or renaming an Agent, or moving a Skill between Agents, requires updating
this document, `ARCHITECTURE.md` §4, and `WORKFLOW_STATES.md` consistently.
