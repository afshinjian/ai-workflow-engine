# AgentOS Workflow Automation — Skill Contracts

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Skill Contracts |
| **Purpose** | Contract (inputs, outputs, side effects, idempotency, failure mode) for every named skill, grouped by family. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Documentation & Governance session (AUTO-001) · Human Owner (approval) |
| **Dependencies** | `ARCHITECTURE.md`, `AGENT_CONTRACTS.md` |
| **Related Documents** | `WORKFLOW_STATES.md` §7, `MACHINE_GATES.md`, `SECURITY_MODEL.md` |

## Table of Contents
1. Naming Convention · 2. Repository Skills · 3. Contract Skills · 4. Validation Skills ·
5. Git and GitHub Skills · 6. Reporting Skills · 7. Common Failure Mode · 8. Decision References ·
9. Open Questions · 10. Future Revisions

## 1. Naming Convention

Skill names are `snake_case` verb phrases, used identically across every document in this
program and, later, as the literal function/tool names in `agentos_workflow/skills/`. A Skill
is deterministic: given the same repository state and inputs, it produces the same result. No
Skill invokes a Model Provider; only Agents do.

## 2. Repository Skills

| Skill | Input | Output | Side effect | Idempotent |
|---|---|---|---|---|
| `verify_repository_identity` | target repo path, expected identity | pass/fail + identity evidence | none | yes (read-only) |
| `inspect_working_tree` | target repo path | clean/dirty + file list | none | yes |
| `inspect_current_branch` | target repo path | branch name, HEAD SHA | none | yes |
| `verify_baseline_ancestry` | target repo path, baseline branch | pass/fail (current branch descends from baseline) | none | yes |
| `create_stage_branch` | stage branch name, base commit SHA | branch ref | creates local branch (only if absent) | yes — no-op if branch already exists at expected base |
| `inspect_diff` | branch, base | diff summary | none | yes |
| `list_changed_files` | branch, base | file list | none | yes |
| `checkout_baseline` | baseline branch | pass/fail | switches working tree to baseline | yes — no-op if already on baseline |
| `fast_forward_pull` | baseline branch, remote | pass/fail | fast-forward-only update; refuses on divergence | yes — no-op if already up to date |
| `delete_local_branch` | branch name | pass/fail | deletes local branch (post-merge only) | yes — no-op if already absent |
| `delete_remote_branch` | branch name, remote | pass/fail | deletes remote branch (post-merge only) | yes — no-op if already absent |
| `verify_final_repository_state` | baseline branch | pass/fail | none | yes |

All destructive Repository Skills (`checkout_baseline` mutating the working tree,
`fast_forward_pull`, `delete_local_branch`, `delete_remote_branch`) require their preconditions
(§7, `SECURITY_MODEL.md` §5) verified immediately before execution, not merely earlier in the
workflow.

## 3. Contract Skills

| Skill | Input | Output | Side effect | Idempotent |
|---|---|---|---|---|
| `locate_stage_contract` | stage ID, contract directory | contract file path | none | yes |
| `parse_stage_metadata` | contract file | typed stage metadata | none | yes |
| `calculate_contract_hash` | contract file | content hash | none | yes |
| `validate_stage_ordering` | stage ID, stage registry | pass/fail | none | yes |
| `validate_allowed_paths` | changed files, contract's allowed/forbidden paths | pass/fail + violations | none | yes |
| `detect_future_stage_work` | changed files, current + later stage contracts | pass/fail + flagged files | none | yes |

`calculate_contract_hash` is the value bound into the authorization record
(`HUMAN_AUTHORIZATION_MODEL.md`); any later mismatch invalidates the authorization.

## 4. Validation Skills

| Skill | Input | Output | Side effect | Idempotent |
|---|---|---|---|---|
| `run_tests` | target repo, configured test command | pass/fail + exit code | none (read-only w.r.t. repo state) | yes |
| `run_lint` | target repo, configured lint command | pass/fail + findings | none | yes |
| `run_formatting_checks` | target repo, configured formatting command | pass/fail | none | yes |
| `run_scope_validation` | changed files, allowed/forbidden paths | pass/fail + violations | none | yes |
| `run_security_checks` | target repo, configured security command | pass/fail + findings | none | yes |
| `run_secret_detection` | changed files/diff | pass/fail + findings (redacted) | none | yes |
| `validate_completion_report` | implementation report artifact | pass/fail + schema errors | none | yes |
| `validate_qa_report` | QA report artifact | pass/fail + schema errors | none | yes |

Every Validation Skill invocation is recorded via the command-execution audit fields in
`AUDIT_MODEL.md` §2 (normalized command identity, timing, exit code, timeout status, sanitized
output references) — never raw stdout/stderr containing potential secrets.

## 5. Git and GitHub Skills

| Skill | Input | Output | Side effect | Idempotent |
|---|---|---|---|---|
| `create_commit` | staged allowed paths, commit message | commit SHA | creates one commit on the stage branch | yes — no-op if tree already matches expected commit |
| `push_stage_branch` | stage branch | pushed ref | pushes stage branch only (never baseline) | yes — no-op if remote already matches |
| `create_pull_request` | stage branch, baseline branch, title/body | PR number, head SHA | opens PR (never merges) | yes — reuses existing open PR for the branch |
| `read_pull_request_state` | PR number | PR state, mergeability | none | yes |
| `read_required_checks` | PR number | list of required checks + status | none | yes |
| `verify_head_sha` | PR number, expected SHA | pass/fail | none | yes |
| `enable_automatic_squash_merge` | PR number | pass/fail | enables GitHub auto-merge (squash) via the PR — never `gh pr merge --admin` | yes — no-op if already enabled with matching configuration |
| `verify_merge_completion` | PR number | pass/fail + merge commit SHA | none | yes |

`push_stage_branch` and every commit/PR/merge skill are structurally incapable of targeting the
configured baseline branch — the skill's argv is fixed to the stage branch, never a caller-
supplied arbitrary ref (`SECURITY_MODEL.md` §2).

## 6. Reporting Skills

| Skill | Input | Output | Side effect | Idempotent |
|---|---|---|---|---|
| `generate_stage_report` | implementation results | stage report artifact | writes report file | yes — overwrite guarded by content hash |
| `generate_qa_report` | QA results | QA report artifact | writes report file | yes |
| `generate_failure_report` | failure context | failure report artifact | writes report file | yes |
| `generate_closeout_report` | closeout results | closeout report artifact | writes report file | yes |
| `append_audit_event` | event record | none | appends one line to the append-only audit log | yes — appending the same event twice is detectable via event ID and suppressed |

## 7. Common Failure Mode

Every Skill returns a typed failure (never raises an unhandled exception to the Orchestrator)
containing enough evidence for the Orchestrator to decide the next workflow-state transition
(`WORKFLOW_STATES.md` §3). A Skill never partially applies a destructive operation: either the
full effect is applied and confirmed, or nothing is applied.

## 8. Decision References
DD-01, DD-05.

## 9. Open Questions
OD-1 (GitHub auto-merge/required-checks mechanism), OD-2 (secret-detection implementation),
OD-3 (repository lock implementation).

## 10. Future Revisions
New skills are additive; renaming or removing a skill requires updating every Agent contract
that references it (`AGENT_CONTRACTS.md`) in the same change.
