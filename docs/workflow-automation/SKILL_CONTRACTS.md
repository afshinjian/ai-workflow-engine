# AgentOS Workflow Automation — Skill Contracts

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Skill Contracts |
| **Purpose** | Contract (inputs, outputs, side effects, idempotency, failure mode) for every named skill, grouped by family. |
| **Status** | Draft |
| **Version** | 1.3 |
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

**Initial-execution retry classification for `create_commit`, `push_stage_branch`,
`create_pull_request`** (`WORKFLOW_STATES.md` §5a; Human Owner policy OD-9,
`OPEN_QUESTIONS.md`, resolved 2026-07-24). The determining question is never *which error type*
occurred — it is *when*: could the underlying `git`/`gh` subprocess have already reached the
remote before the failure was observed? Absence of a confirmed side effect is not proof that no
side effect occurred, so a timeout, connection reset, DNS failure, or lost response is **never**,
by itself, sufficient to classify a failure as pre-effect — each of those can occur exactly as
easily after the remote already received and acted on the write as before it sent anything.

- **Proven pre-side-effect (bounded, same-state retry permitted):** the Skill's own precondition
  check (§2, `SECURITY_MODEL.md` §5, verified immediately before execution) fails, or the `git`/
  `gh` executable itself fails to spawn (not found, permission denied) — in both cases the
  underlying command was never actually invoked, so nothing could have reached the remote. This
  is a narrow, provable set; a network-layer error *surfaced by* an invoked `git`/`gh` subprocess
  is never included here, however immediate it appears, because a subprocess wrapping a network
  client cannot be trusted to report "connection refused before any byte left the machine" versus
  "the write landed and the acknowledgment was lost" — the two are indistinguishable from the
  Skill's own vantage point without positive confirmation.
- **Possible, unknown, or indeterminate side effect (no blind retry — mandatory
  idempotency/reconciliation check instead, same state, before any other action):** every other
  failure of an invoked `git`/`gh` subprocess — process/network timeout, connection reset, DNS
  failure occurring during the call, a lost or incomplete response, an ambiguous non-zero exit.
  This is the default classification for any failure once the subprocess has actually run.
  Reconciliation uses exactly the Skill idempotency check already defined for it (`create_commit`:
  does the tree already match the expected committed diff; `push_stage_branch`: does the remote
  ref already match; `create_pull_request`: does an open PR already exist for the branch).
- **Confirmed successful side effect (reconciliation success):** advance to the state that
  matches reality (`WORKFLOW_STATES.md` §5a item 3) — the side effect is never repeated.
- **Recoverable inconsistency:** not applicable to these three Skills (`WORKFLOW_STATES.md` §5a
  item 4) — nothing at this phase is a code problem `ImplementationAgent` could fix.
- **Unrecoverable or indeterminate (`FAILED`):** the proven-pre-effect retry limit is exhausted;
  or reconciliation cannot establish a safe state; or reconciliation finds an inconsistency with
  no available repair; or a required invariant cannot be restored.
- **Explicitly non-retryable, routed straight to reconciliation-then-`FAILED` if unresolved, never
  retried under any classification:** authentication/permission failure, merge/rebase conflict,
  an invalid or missing ref, a malformed/rejected request (a definitive HTTP 4xx other than 429),
  or any error the Skill itself classifies as permanent in its typed result — none of these is
  ever ambiguous about whether a side effect could have occurred, so none needs the possible-
  side-effect reconciliation step; they are non-retryable exactly because they are diagnosable as
  permanent, not because a side effect is impossible.

Retry limit for the proven-pre-side-effect case: **3 attempts** per Skill invocation, mirroring
the existing repair-attempt ceiling (`FAILURE_RECOVERY.md` §1) for consistency, though counted
independently of it (`WORKFLOW_STATES.md` §5a item 1) — exhausting the limit is never silently
extended, and reconciliation (the second bullet above) is never itself retried blindly; a second
reconciliation attempt only follows a fresh, independent invocation that itself first re-entered
the proven-pre-effect or possible-side-effect classification.

## 6. Reporting Skills

| Skill | Input | Output | Side effect | Idempotent |
|---|---|---|---|---|
| `generate_stage_report` | implementation results, optional sequence | stage report artifact | writes report file | yes — overwrite guarded by content hash |
| `generate_qa_report` | QA results, optional sequence | QA report artifact | writes report file | yes |
| `generate_failure_report` | failure context, optional sequence | failure report artifact | writes report file | yes |
| `generate_closeout_report` | closeout results, optional sequence | closeout report artifact | writes report file | yes |
| `append_audit_event` | event record | none | appends one line to the append-only audit log | yes — appending the same event twice is detectable via event ID and suppressed |

**Sequenced artifacts (GOV-3).** A workflow legitimately produces several genuinely different
reports of the same kind: the bounded repair loop (`FAILURE_RECOVERY.md` §1) runs one
implementation attempt and one QA round per repair. Each generator therefore accepts an optional
`sequence` — a validated integer, never a caller-supplied string — naming the artifact
`<kind>.<sequence>.json` inside that workflow's own audit directory (`AUDIT_MODEL.md`) instead of
the single `<kind>.json` an omitted sequence still produces. Idempotency is unchanged and remains
**per artifact**: identical content is a no-op, and differing content under the same kind *and*
sequence is still refused, because that means a caller reused a round number rather than that the
append-only audit model needs relaxing.

## 7. Common Failure Mode

Every Skill returns a typed failure (never raises an unhandled exception to the Orchestrator)
containing enough evidence for the Orchestrator to decide the next workflow-state transition
(`WORKFLOW_STATES.md` §3). A Skill never partially applies a destructive operation: either the
full effect is applied and confirmed, or nothing is applied.

## 8. Decision References
DD-01, DD-05, DD-09, DD-40 (§6 sequenced report artifacts).

## 9. Open Questions
OD-1 (GitHub auto-merge/required-checks mechanism), OD-2 (secret-detection implementation),
OD-3 (repository lock implementation).

## 10. Future Revisions
New skills are additive; renaming or removing a skill requires updating every Agent contract
that references it (`AGENT_CONTRACTS.md`) in the same change.
