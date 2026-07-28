# Decision Log

Architectural decisions for `ai-workflow-engine`, newest first. Each entry records what was
decided, what alternatives were considered, and why — so a fresh session can understand *why*
the code looks the way it does, not just what it does. **This log is append-only, with exactly
one closed, non-repeatable exception**, on par with `docs/workflow-automation/STAGE_REGISTRY.md`
§5: an existing entry's text is never edited or deleted once written. The sole exception —
two specific, named, pre-protocol edits made on 2026-07-24 before this rule was stated in so many
words — is defined precisely, with its Human Owner basis, in the "append-only grandfathering
exception" entry below; no other edit, past or future, is covered by it. Every entry from that
one forward, including it, is append-only in fact. A wrong or incomplete entry is fixed only by
appending a new, dated entry that names what it corrects — a Governance Correction Record
(`docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 18) where the correction concerns an
AUTO-00x matter, or an equivalent plainly-labeled corrective entry otherwise.

## 2026-07-28 — GOV-AUTO-02 closed to `Done`

**Decision:** The Human Owner closed GOV-AUTO-02 from `Current` to `Done` and directed the
governance and handoff records to state that it was implemented, validated, approved, and
committed as `d212e4d2dae2cd0a3510c54d7cd098fdfd5da548`. Exactly one governance-only local commit
is authorized for this closure.

**Resulting state:** No task is `Current`. GOV-AUTO-02 is `Done`; AUTO-006, AUTO-007, GOV-2,
GOV-3, and DASH-002..010 remain `Planned` and require their own fresh written Human Owner
authorization. This decision authorizes no successor and specifically does not authorize
AUTO-006.

**Boundaries:** No push, merge, successor implementation, branch/upstream change, or stash
mutation is authorized. The session must stop after the single local closure commit and report
its hash.

## 2026-07-28 — GOV-AUTO-02 local task authorization and launch gate

**Decision:** The Human Owner authorized GOV-AUTO-02 — Local Task Authorization and Launch Gate.
The task is the single `Current` task while its completed implementation remains uncommitted and
pending Human Owner approval. AUTO-006, GOV-3, DASH-002, and every other planned task remain
unauthorized.

**Design:** `scripts/workflow-authorize.sh <TASK_ID> [claude|codex]` accepts only an explicit task
ID; it never reads queue order to choose work. It requires the default-branch baseline, a clean
worktree/index, no existing `Current` task, a `Planned`/ready target, completed structured program
predecessors, resolved established owner-decision gates, and passing task-state/governance/
handover checks. The script displays the task, status, predecessor, canonical implementation
branch, current branch/HEAD, agent, and exact governance allowlist, then requires two exact
`AUTHORIZE` confirmations before changing anything.

**Phase separation:** authorization reconciles the queue, mirrors, project state, decision log,
changelogs, relevant stage registry, handoff, and checksum, validates again, and creates exactly
one local `docs(governance): authorize TASK-ID` commit containing only those records. An optional
agent is invoked through `workflow-next.sh` only after the commit is verified and the worktree is
clean. Implementation and its later `workflow-approve.sh` commit remain separate. The script has
no push, merge, branch/upstream mutation, stash mutation, automatic predecessor closure, or task
implementation path.

**Limitations:** AUTO/DASH predecessor and canonical-branch data are structured in their stage
registries. Ordinary queue-only GOV tasks declare no machine-readable predecessor, so the gate
reports none declared and relies on their explicit status/blocker prose plus the common baseline
and Human confirmations. Open-decision refusal recognizes the repository's established
“blocked on” and “must be resolved before TASK authorization” wording; a future structured
dependency schema could replace that conservative text check.

## 2026-07-28 — AUTO-005 approved, closed to `Done`, and merged; the QA report collision deferred to GOV-3

**Decision:** The Human Owner approved the AUTO-005 implementation, explicitly accepted all five
limitations the stage report documented, authorized exactly one local commit (created as
`430cbb4`), and then — in a second decision — approved AUTO-005's formal closure and publication:
task `Current → Done`, registry `IN_PROGRESS → COMPLETE`, push, merge into `main`, push `main`,
retain the stage branch, touch neither stash, and do not begin AUTO-006.

**Rationale — why the QA report collision was deferred rather than fixed.** AUTO-005 found a real
integration defect: `agentos_workflow/skills/reporting.py` writes one artifact per workflow
identifier per report kind and correctly refuses to overwrite differing content, but the bounded
repair loop (`FAILURE_RECOVERY.md` §1) produces up to four genuinely different QA reports per
workflow, so the second round failed on the *artifact* rather than on the code under review. The
stage could not fix it — `agentos_workflow/skills/**` is outside AUTO-005's allowed paths — so it
shipped a scoped per-attempt audit workaround, disclosed it in the report, and asked. The Human
Owner accepted the workaround for this stage and directed that the underlying defect be recorded as
explicit future work, not fixed in scope. It is now **GOV-3 — Attempt-aware report artifact naming
in the Reporting Skills** (`docs/TASK_QUEUE.md`, `Planned`, requiring its own fresh authorization),
carrying the defect description, why the workaround is not the fix, and a recommended shape.
Expanding AUTO-005's allowed paths to fix it in place was rejected: a stage that widens its own
scope to absorb a defect it discovers is exactly the drift the allowed-path list exists to prevent,
and the fix touches a module three other stages depend on.

**Rationale — why the completion report was not rewritten.** AUTO-005's report was deliberately
finished *before* its commit was created, recording the approval and the authorized commit without
naming a hash — the record-integrity problem AUTO-004 had hit, avoided by construction this time.
Closure then added a fact the report could not have known (the hash `430cbb4`) plus the merge
result, so those are recorded in a new append-only addendum, a new `STAGE_REGISTRY.md` §5 row, and
this entry, leaving the report's own text untouched (rule 8).

**What this decision does not do:** it authorizes no successor (rule 16). AUTO-006, AUTO-007,
GOV-2, and GOV-3 all remain `Planned` and explicitly unauthorized, and the Human Owner's directive
said so in terms ("Do not authorize AUTO-006"). Neither stash was touched, and both
`feature/auto-004-model-providers` and `feature/auto-005-agents` were retained, not deleted.

## 2026-07-28 — AUTO-004 approved, closed to `Done`, and merged; AUTO-005 authorized separately

**Decision:** An AUTO-005 session's authorization-precondition check found AUTO-004 still
`IN_PROGRESS`/`Current` with its work committed as `84616d5` on `feature/auto-004-model-providers`
but absent from `main`. Three preconditions were therefore unmet:
`docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 1 (predecessor `COMPLETE`) and rule 10
(no stage N+1 before N is `COMPLETE`); `maximum_current_tasks: 1` (AUTO-004 held the single
`Current` slot); and rule 14 (AUTO-005's branch must come from current `main`, which carried no
`agentos_workflow/providers/` for AUTO-005's Agents to be restricted to). Per rule 16 the session
stopped, made no change, and reported the conflict rather than resolving it on its own initiative.

The Human Owner, presented with it, gave one written decision resolving all of it: approve the
AUTO-004 implementation; close it `Current → Done` and `IN_PROGRESS → COMPLETE` recording commit
`84616d5`; publish it (push the stage branch, update `main` from `origin/main` without rewriting
history, merge by the established safe merge policy, push `main`, retain the branch, leave both
stashes untouched); and *then*, only after that integration and its closure checks passed,
authorize AUTO-005 as the single `Current` task.

**Rationale — why the completion report was not rewritten:** commit `84616d5` was created after
`docs/reports/workflow-automation/AUTO-004-completion-report.md` was written, so that report's
"No commit, push, pull request, merge … was performed" Confirmation was true when written. Rule 8
protects completion records from in-place editing, and the Human Owner's decision explicitly
required that the report "is not rewritten to pretend the commit existed when it was produced".
The later commit, approval, and merge are recorded instead by three append-only artifacts: a new
addendum section at the end of that report, a new `STAGE_REGISTRY.md` §5 row, and this entry.
Editing the report's Confirmation section in place — the tempting "just make it accurate now" fix —
was rejected because it would silently rewrite what the delivering session actually did and
observed, which is exactly the failure rule 8 and rule 18 exist to prevent.

**Rationale — why closure and authorization are two acts, not one:** this is the fourth occurrence
of the predecessor-still-`Current` pattern (after DASH-001→AUTO-001, AUTO-001→AUTO-002, and
GOV-AUTO-01→AUTO-004) and was handled identically: the session detects and reports, the Human
Owner decides both halves explicitly in one written directive. Rule 16 forbids a session selecting
or authorizing a successor on its own initiative in the same session as a closeout; it does not
forbid the Human Owner directing both when shown a genuine conflict. The `Current` set was
verifiably empty between the two acts, and AUTO-005's authorization is recorded as its own
`STAGE_REGISTRY.md` §5 row conditioned on the AUTO-004 integration having succeeded first.

**What this decision does not do:** it authorizes no AUTO-005 commit, push, or merge — AUTO-005
stops at a Human Owner approval report — and it authorizes no work on AUTO-006 or any later stage.
Neither stash was touched, and `feature/auto-004-model-providers` was retained, not deleted.

## 2026-07-28 — GOV-AUTO-01 closed to `Done`; AUTO-004 authorized as the single `Current` task

**Decision:** An AUTO-004 session's authorization-precondition check found GOV-AUTO-01 still
recorded `Current` in `docs/TASK_QUEUE.md`, `docs/current_task.md`, and `docs/remaining_tasks.md`
even though its commit `a302c95` had already been merged into `main` via `a3b5b0a`. Under
`self-governance.yaml`'s `maximum_current_tasks: 1`, that blocked
`docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 1's "no other `Current` task anywhere in the
queue" precondition, so AUTO-004 could not be recorded `Current`. Per rule 16 the session stopped,
made no change, and put the conflict to the Human Owner rather than resolving it on its own
initiative.

The Human Owner, presented with the conflict, gave one written decision resolving both: close
GOV-AUTO-01 `Current → Done` — recording that it was implemented, validated, approved, committed
as `a302c95`, and merged into `main` via `a3b5b0a` — and then authorize and begin AUTO-004 as the
single `Current` task, with commit, push, merge, and any work on AUTO-005 or another task
explicitly prohibited.

**Rationale:** This is the third occurrence of the predecessor-still-`Current` pattern rule 16
describes, after DASH-001→AUTO-001 (2026-07-23) and AUTO-001→AUTO-002 (2026-07-24), and it was
handled the same way: the session detects and reports, the Human Owner decides. Rule 16 forbids a
session selecting or authorizing a successor on its own initiative in the same session as a
closeout; it does not forbid the Human Owner directing both explicitly when shown a genuine
conflict. Recording the closure as an inference from the merge — "it is on `main`, therefore it
must be `Done`" — was rejected for exactly that reason: the merge is evidence of the Human Owner's
approval, not a substitute for the Human Owner's closure act, and a session that promotes itself
past a `Current` task on inferred approval is the failure mode `maximum_current_tasks: 1` and
rule 16 exist to prevent.

**What this decision does not do:** it authorizes no successor to AUTO-004 (rule 16), no push or
merge of the AUTO-004 work, and no reopening of GOV-AUTO-01. The stale
`handover/PROJECT_HANDOVER.md` — which still described GOV-AUTO-01 as uncommitted and reported
HEAD as `908be94` on the AUTO-003 branch — is refreshed under the same decision's explicit
instruction to update the handoff.

## 2026-07-27 — Human Owner accepts AUTO-002 for closure without another independent review

**Decision:** After reviewing the implementation report and validation results, the Human Owner
accepted the current AUTO-002 implementation as sufficient, explicitly directed that no further
independent review or search for findings occur, and authorized final integrity checks,
governance closure, and one local Conventional Commit. This is the controlling closure decision
for the pending-review language in the entry immediately below; the technical remediation record
remains intact.

AUTO-002 moves from registry `IN_PROGRESS` to `COMPLETE` and task status `Current` to `Done`.
AUTO-003 remains `NOT_STARTED`/`Planned`: predecessor completion satisfies only one precondition
and is not successor authorization. The approved action includes no push, merge, upstream change,
branch change, stash mutation, architectural redesign, or AUTO-003 implementation.

**Future work:** Existing POSIX portability boundaries, infrastructure-retry accounting when a
future stage first introduces such operations, remote/GitHub reconciliation, and other
out-of-scope improvements do not reopen or block AUTO-002. They remain assigned to the relevant
future AUTO stage or project backlog and require separate Human Owner authorization.

## 2026-07-27 — AUTO002-IR3-01..IR3-05: Human-Owner-authorized remediation pending fresh independent review

**Decision:** The Human Owner authorized implementation of every task from the third independent
review. The implementation is deliberately not self-approved: AUTO-002 remains `IN_PROGRESS` and
must receive a completely fresh independent review before any commit or merge approval.

The approved changes bind implementation reconciliation to the authorization record, exact current
branch tip, latest persisted attempt, independently-derived authorized-baseline diff, path policy,
and an exact structured completion report (DD-27); reject hardlinked mutable persistence targets
before writes (DD-28); confine authorization and attempt sidecars to the literal workflow directory
using descriptor-relative no-symlink operations (DD-29); reject duplicate JSON keys in those
sidecars and completion reports (DD-30); and reconcile the audit model's separate repository
identity/path fields with the implemented record schema (DD-31).

**Scope:** Only the five approved remediation tasks, their regression tests, and their governance
updates were performed. No dependency, packaged `src/` implementation, AUTO-003/AUTO-005 work,
commit, push, merge, branch, stash, upstream, GitHub, or other external-service action was
authorized or performed.

## 2026-07-27 — AUTO002-IR-01..IR-05: a second independent review reproduced five defects the prior pass reported as resolved; all five remediated, F11 reclassified

**Decision:** A second, independent review of AUTO-002 reproduced five concrete defects, two of
them in code the immediately preceding remediation pass (the entry directly below) had reported
as hardened. That prior pass's completion claims for **F04, F05, F08, and F09 are therefore
invalidated as overstated**: each fixed a real defect, but none closed the class of defect its
governance text claimed. This entry records the corrected position and the remediation. The
verdict of the review that found these is not erased and is not to be read as approval of this
work — this remediation is **pending fresh independent review**, and no independent approval has
been obtained for it.

**What the review reproduced, and the corrected status of the prior claims:**

- **IR-01 (lock, `agentos_workflow/orchestrator/lock.py`)** — `canonical_lock_path` resolves the
  repository *root* but appends `.agentos/workflow.lock` lexically, so a symlinked `<repo>/.agentos`
  was followed at open time and an external file was truncated and overwritten. **Corrects F04
  (`DECISIONS.md` DD-16):** resolving the root is not confinement. Fixed by a descriptor-relative
  `O_NOFOLLOW` walk (`DECISIONS.md` DD-21); 8 regression tests.
- **IR-02 (state/audit storage, `state_store.py`)** — validating `workflow_id` as a safe path
  *component* does not stop a symlinked `<root>/<workflow_id>` directory being followed; audit
  records were written outside the configured root, and unconfined reads could replay a planted
  external history. **Corrects F05 (DD-16) and the path-confinement half of F08 (DD-17).** Fixed by
  one shared confined-open primitive used by both histories and by reads and writes
  (`DECISIONS.md` DD-22); 10 regression tests.
- **IR-03 (changed-path authorization, `config/schema.py`, `orchestrator/engine.py`)** —
  noncanonical-but-non-traversing patterns (`docs/./secret/**`, `docs//secret/**`, backslash,
  Windows-drive and UNC forms) were accepted and passed raw into matching, so a
  `forbidden_changed_paths` rule stayed inert and a broader allowed rule won. **Corrects F09
  (DD-18):** rejecting absolute and `..` patterns was necessary but far from sufficient, and the
  inert-forbidden-pattern hazard DD-18 named was still live. Fixed by strict rejection of every
  noncanonical spelling plus canonicalisation of observed Git paths (`DECISIONS.md` DD-23); 48
  regression tests.
- **IR-04 (writer ordering, `state_store.py`)** — the reader enforced non-decreasing timestamps but
  the writer did not, so the supported writer could append a record that made the history
  permanently unreadable by the supported reader. **Corrects the ordering half of F08 (DD-17):**
  a read-side-only check was an incomplete invariant. Fixed by enforcing the reader's own rule at
  append time, under the append lock, before any byte is written (`DECISIONS.md` DD-24); 17
  regression tests.
- **IR-05 (duplicate JSON keys, `state_store.py`)** — standard JSON parsing accepted duplicate
  object keys with last-key-wins, so a record carrying two `to_state` or `timestamp` values
  validated cleanly and replayed as whichever value the parser kept. Fixed by
  `object_pairs_hook`-based rejection at every nesting level, before model validation
  (`DECISIONS.md` DD-25); 12 regression tests.

**F11:** the prior pass asserted "F11 was already resolved by a prior session and was not
reopened." That claim is superseded. An exhaustive local search (all governance records, reports,
addenda, stage prompts, tests, implementation, `git log -S` across all refs, and both stashes; no
network) finds the token `F11` only in the two prose assertions that it was resolved — never a
definition. F11 is reclassified **`INSUFFICIENT_DURABLE_EVIDENCE`**: *F11 historical definition and
regression mapping could not be reconstructed from durable repository evidence.* No definition was
invented and no code was changed to manufacture evidence (`DECISIONS.md` DD-26).

**F13 (governance consistency):** the prior F13 entry is not deleted, but its assertion that
governance was consistent with the code no longer held once IR-01..IR-05 were reproduced. This
entry, DD-21 through DD-26, and the corresponding report addendum are the corrected record.

**Validation:** `pytest tests agentos_workflow/tests` — 1967 passed, 0 failed, 0 errors, 0 skipped,
0 xfailed, 0 deselected, 0 warnings (baseline before this pass: 1872 passed; +95 regression tests).
Bare `pytest` — 978 passed; this is *not* full coverage of this work, because
`pyproject.toml`'s `testpaths = ["tests"]` excludes `agentos_workflow/tests` entirely. Ruff, Black,
`mypy src`, `mypy agentos_workflow`, and `git diff --check` all clean. `workflowctl verify` reports
the single pre-existing `upstream_missing` finding (this branch has no upstream and upstream
configuration was out of scope and untouched); all other checks pass.

**Alternatives considered:** for IR-03, normalizing patterns to canonical form instead of rejecting
them — declined, because a rewriting step risks reinterpreting glob tokens and because two
spellings mapping to one stored pattern makes configuration review harder; strict rejection gives
exactly one spelling per intent. For IR-01/IR-02, checking the resolved path before opening —
declined as a check-then-open race; the kernel refusing the open is the enforcement.

**Status:** AUTO-002 remains `IN_PROGRESS`, now **pending fresh independent review**. No commit,
push, merge, branch change, upstream change, or stash mutation occurred. AUTO-003 and AUTO-005
remain unauthorized and `NOT_STARTED`.

## 2026-07-27 — AUTO002-F04/F05/F06/F08/F09/F10/F12/F13: sequential remediation pass completed; governance reconciled

**Decision:** Following the F07 Human Owner decision recorded immediately below, remediation
continued sequentially through F08 (audit-record invariants), F09 (configuration-pattern
confinement), F10 (workflow-ID reuse bypass), and F12 (regression-test-adequacy audit), each
reproduced adversarially before being fixed, per the same discipline F04-F07 already established.
This entry is F13: the governance-reconciliation finding, synchronizing `DECISIONS.md`,
`CHANGELOG.md`, and the completion report for every finding in this pass.

**What was found and fixed, in order:**

- **F04/F05/F06** (canonical repository locking, JSONL append durability, durable retry/attempt
  accounting) were implemented and tested earlier in this same remediation session, ahead of F07;
  `DECISIONS.md` DD-16 records them at the level of detail directly verifiable against current
  code.
- **F07** (local reconciliation-evidence verification): recorded in the entry immediately below
  this one and in `DECISIONS.md` DD-15.
- **F08** (audit-record invariants, `state_store.py`): a naive (non-timezone-aware) timestamp, a
  command's `completion_time` preceding its own `start_time`, an `stdout_ref`/`stderr_ref`
  resolving outside the audit directory, a `StateTransitionRecord` whose own `workflow_id` field
  disagreed with the file it was read from, and a persisted sequence with out-of-order timestamps
  were all previously accepted with no validation. All four are now rejected
  (`DECISIONS.md` DD-17); 44 new regression tests.
- **F09** (configuration-pattern confinement, `config/schema.py`): `allowed_changed_paths`/
  `forbidden_changed_paths` accepted an absolute or parent-traversal glob pattern that could never
  match any real repository-relative changed path — for `forbidden_changed_paths` specifically, an
  inert pattern gives the false appearance of a protection that was never in effect. Now rejected
  (`DECISIONS.md` DD-18); 8 new regression tests.
- **F10** (workflow-ID reuse, `engine.py`): `ResumedWorkflow` — a plain, unguarded dataclass, unlike
  `WorkflowSession` — could be constructed directly and used to durably persist a fabricated
  `CREATED -> AUTHORIZED` transition (via `.transition_to(WorkflowState.AUTHORIZED, actor="human")`
  against a fresh, never-replayed machine) *before* `AuthorizationBypassError` was finally raised —
  the corrupting write happened first, every time. `ResumedWorkflow.transition_to` now rejects
  `AUTHORIZED` before any persistence is attempted (`DECISIONS.md` DD-19); 5 new regression tests.
  `authorize()` itself was independently re-verified and found already airtight against reuse.
- **F12** (regression-test-adequacy audit, no code change): a full-suite run plus a targeted sweep
  found no test anywhere in the AUTO-002 suite still asserting, as expected, behavior any of the
  above fixes made unsafe (`DECISIONS.md` DD-20).

**Validation, every finding:** full combined suite (`pytest tests agentos_workflow/tests`) green
throughout, ending at 1872 passed; `ruff check --no-cache agentos_workflow/`,
`black --check agentos_workflow/`, and `mypy --no-incremental agentos_workflow` all clean after
every fix; `git diff --check` clean. No dependency added; no network or GitHub access
implemented; no general Skill/Agent interface implemented; no mutable Git operation authorized;
no commit, push, merge, pull request, branch change, upstream change, or stash mutation occurred
at any point in this pass.

**Acknowledged, explicitly recorded limitations (not silently papered over):** `CommandExecutionRecord`
has no `workflow_id` field, so its identity cannot be cross-checked against its file the way
`StateTransitionRecord`'s now is (F08/DD-17); `ImplementationDiffEvidence` has no `attempt_number`
or `changed_paths` field, so per-attempt evidence binding and changed-path scope checking remain
open (F07/DD-15).

**Scope/status:** AUTO-002 remains `IN_PROGRESS`; AUTO-003 and AUTO-005 remain unauthorized and
`NOT_STARTED`. F11 was already resolved by a prior session and was not reopened. F13 (this entry)
completes the sequential remediation pass F04 through F13; remaining next steps belong to a fresh
independent review, not to this session.

## 2026-07-27 — Human Owner decision: AUTO002-F07 evidence verification scope

**Decision:** `ReconciliationEvidence` must never be accepted merely because a caller supplies a
success Boolean, internally self-consistent fields, or a nonblank reference string — lack of an
authorized verifier must never be interpreted as successful evidence. The Human Owner authorized a
narrow extension of DD-14's existing read-only local-observation boundary, evidence-verification-
only: `ImplementationDiffEvidence` (`IMPLEMENTING`) and `CommitEvidence` (`READY_TO_COMMIT`) are
locally verifiable and are now independently re-derived from real Git state (commit existence,
branch-ancestry reachability, or an independently recomputed tree SHA) before being trusted, using
a new fixed-argv, read-only `LocalEvidenceObserver` (`agentos_workflow/observation/evidence.py`)
built on the same pattern as DD-14's `LocalResumeObserver` — no arbitrary command surface, no
mutable Git operation, no network or GitHub call. `ImplementationDiffEvidence`'s completion-report
reference is confined to a bare filename the engine itself resolves to
`<audit_directory>/<workflow_id>/evidence/<state.value>/<artifact_name>`
(`resolve_evidence_artifact`), with path-component validation, audit-root confinement (defeating
both parent traversal and symlink escape), and an existing-regular-file check — a caller-supplied
path is never taken at face value. `RemoteRefEvidence` (`COMMITTED`) and `PullRequestEvidence`
(`PUSHED`) describe remote/GitHub facts AUTO-002 has no authorized network-reaching observer for;
both now unconditionally fail closed with a new `ReconciliationVerifierUnavailableError`, remaining
pending future authorized Skill/GitHub observation work. This decision explicitly does not
authorize network access, GitHub access, a general Skill or Agent interface, any mutable Git
operation, or starting AUTO-003 or AUTO-005.

**Rationale:** Without this decision, any caller (or a future buggy or compromised Skill) could
claim any reconciliation outcome for any commit, remote ref, or pull request and have it accepted
verbatim — the exact "evidence-free bypass path" class of defect this program's governance has
previously required be closed rather than left as a weaker parallel path. Confining the newly
authorized verification strictly to already-locally-observable facts, and failing closed rather
than guessing for everything else (remote/PR state), keeps the extension narrow and auditable
rather than opening a general execution or network capability.

**What changed:** `agentos_workflow/observation/evidence.py` added (`LocalEvidenceObserver`,
`LocalEvidenceObservationError`, `resolve_evidence_artifact`); `agentos_workflow/observation/
__init__.py` exports them; `agentos_workflow/orchestrator/engine.py` gained
`ReconciliationVerifierUnavailableError`, `LocalEvidenceVerificationFailedError`, and
`_verify_evidence_locally`, wired into the existing `evaluate_initial_execution_failure`
immediately after its existing internal-consistency check — no public signature changed.
`docs/workflow-automation/DECISIONS.md` gained DD-15 (version 1.4 → 1.5);
`docs/workflow-automation/CHANGELOG.md` gained a corresponding `[Unreleased]` entry (version 2.3 →
2.4); `docs/reports/workflow-automation/AUTO-002-completion-report.md` gained a corresponding
addendum. Two gaps are explicitly acknowledged as remaining, not silently assumed solved:
evidence-artifact binding does not yet reach the specific retry attempt (no `attempt_number` field
exists on any evidence type to bind against), and `ImplementationDiffEvidence` has no
`changed_paths` field, so changed-path scope is not independently checkable from evidence alone
today.

**Scope/status:** AUTO-002 remains `IN_PROGRESS`; AUTO-003 and AUTO-005 remain unauthorized and
`NOT_STARTED`. No commit, push, merge, branch change, upstream change, or stash mutation occurred.

## 2026-07-27 — Governance Correction Record: DD-14 ordering defect in `DECISIONS.md` corrected; `STAGE_REGISTRY.md` §6 decision index synchronized

**Decision:** A fresh session, resuming AUTO-002 under an explicit trust-boundary instruction not
to treat its handoff as authoritative proof, independently reconciled the F01/F02/F03 findings
before starting F04. That reconciliation found two governance-document defects, both introduced by
the immediately preceding (F03) session, neither previously disclosed in any handoff or report:

1. `docs/workflow-automation/DECISIONS.md`'s DD-14 entry (recorded in the entry immediately below
   this one) was physically appended between DD-01 and DD-02, rather than after DD-13, breaking
   this file's otherwise-strict ascending DD-01→DD-13 ordering with no supersession note explaining
   the placement.
2. `docs/workflow-automation/STAGE_REGISTRY.md` §6 ("Decision References") still read "DD-01
   through DD-13," not updated to reflect DD-14's addition.

The Human Owner reviewed this finding and authorized this Governance Correction Record
(`STAGE_REGISTRY.md` §3 rule 18), explicitly directing that DD-14 not be moved, deleted,
renumbered, or rewritten, and that no earlier decision entry's text be altered.

**Corrected facts:**

- DD-14 is valid and binding, exactly as originally recorded; its content is unchanged by this
  correction.
- The ordering defect does not invalidate DD-14 or any other decision.
- No decision identifier is being changed by this record; no historical decision text is being
  removed.
- The effective decision sequence, for all purposes going forward, is **DD-01 through DD-14**,
  regardless of DD-14's physical position in `DECISIONS.md`.
- This record supersedes only the implied physical ordering of `DECISIONS.md`; it does not
  supersede or re-litigate the content of any decision, including DD-14 itself.

**What changed:** `docs/workflow-automation/DECISIONS.md` gained an append-only "Governance
Correction Record (2026-07-27) — DD-14 physical placement" note after DD-13 (version 1.3 → 1.4),
cross-referencing this entry; DD-14's own text is untouched. `docs/workflow-automation/
STAGE_REGISTRY.md` §6 corrected to "DD-01 through DD-14," with a one-line note pointing back to
this record (version 6.1 → 6.2). `docs/workflow-automation/CHANGELOG.md` gained a corresponding
`[Unreleased]` entry (version 2.2 → 2.3). `docs/reports/workflow-automation/
AUTO-002-completion-report.md` gained a short addendum disclosing the defect and its correction,
per the same append-only, no-rewrite discipline every prior addendum to that report has followed.

**Who found it and when:** an independent fresh-session governance reconciliation audit, performed
2026-07-27, before any AUTO002-F04 work began, per the session's standing instruction not to trust
the prior session's handoff without direct verification.

**Scope/status:** AUTO-002 remains `IN_PROGRESS`; AUTO-003 remains unauthorized and `NOT_STARTED`.
No workflow state, transition, implementation file, or test file was touched by this correction. No
commit, push, merge, branch change, or stash mutation occurred. The pre-existing, expected
`upstream_missing` `workflowctl verify` finding is untouched and not addressed by this record.

## 2026-07-27 — Human Owner decisions: AUTO002-F03 local read-only observation boundary and state-specific resume policy

**Decision:** The Human Owner expanded AUTO-002 only enough to add a typed, local, read-only
resume observation boundary, then supplied the authoritative per-state branch, HEAD,
working-tree, control-artifact, ancestry, baseline-protection, and uncertain-operation policy.
Production resume constructs the observer internally and makes every authorization decision;
test adapters may return raw observations but never a verdict. Fixed allowlisted local Git
queries, confined contract reads, and canonical runtime-version observation are permitted.
Arbitrary commands, mutation, network/GitHub access, Providers, the general Skill interface,
and importing the root `GitClient` remain prohibited.

**Rationale:** `WorkflowSession.resume` could previously accept a
`CurrentAuthorizationBinding` copied directly from `authorization.json`, so repository,
contract, Git, and runtime facts were never independently observed. The prior phrases
"working tree state as expected" and "cleanliness where expected" also lacked a state/crash-
boundary definition. The new policy closes both gaps without adding a workflow state, changing
an edge, or starting AUTO-003.

**Scope/status:** Recorded normatively in `docs/workflow-automation/DECISIONS.md` DD-14,
`WORKFLOW_STATES.md` §6a, `MACHINE_GATES.md` §2a, `ARCHITECTURE.md`, and
`stage-prompts/AUTO-002.md`. AUTO-002 remains `IN_PROGRESS`; AUTO-003 remains unauthorized and
`NOT_STARTED`.

## 2026-07-26 — Human Owner policy decision recorded and applied: OD-4 (infrastructure retries, repair attempts, and initial-execution attempts are three separate durable counters)

**Decision:** The Human Owner supplied the explicit policy sign-off `OPEN_QUESTIONS.md` OD-4 was
waiting on before AUTO-002 could encode the infrastructure-retry/repair-attempt separation as
load-bearing behavior rather than documentation intent. Recorded here verbatim as the approval
basis, then summarized by what changed.

**OD-4 approval, verbatim:**

> I am the Human Owner of this repository.
>
> I approve the following governance decision for OD-4.
>
> Infrastructure retries are separate from the provider-driven repair-attempt counter.
>
> Infrastructure retries are permitted only when durable evidence proves that invocation did not
> begin and no external side effect could have occurred.
>
> Infrastructure retries do not increment the repair-attempt counter.
>
> If invocation may have started, infrastructure retry is prohibited. Mandatory reconciliation is
> required.
>
> Repair attempts, initial-execution attempts, and infrastructure retries are three separate
> durable event streams and counters.
>
> Record this as the official Human Owner disposition for OD-4.
>
> Update only the required governance documentation and completion report accordingly.
>
> Do not change implementation unless this governance decision requires a purely documentary
> synchronization.

**What changed:** `docs/workflow-automation/WORKFLOW_STATES.md` §5's parenthetical ("`OPEN_QUESTIONS.md`
OD-4 tracks confirming this separation before AUTO-002 implementation") is replaced with a
resolved-confirmation statement citing this entry — no wording about the *policy itself* changed,
since §5 already stated exactly the three-way separation this approval confirms (infrastructure
retry: Skill-internal, bounded, backoff, never touches the repair counter; repair attempts:
the `VALIDATING`/`QA_RUNNING` ⇄ `REPAIRING` cycle, §3/`FAILURE_RECOVERY.md`; initial-execution
attempts: §5a's provider/commit/push/PR policy, OD-9) — version 4.1 → **4.2**. Cross-posted as
`docs/workflow-automation/DECISIONS.md` DD-13. `OPEN_QUESTIONS.md` OD-4 moved from Open to
Resolved (version 1.3 → 1.4). `docs/workflow-automation/STAGE_REGISTRY.md` §6 corrected to include
DD-13 (and, on the same pass, DD-09 through DD-12, which a prior audit found missing — version 6.0
→ **6.1**).

**No AUTO-002 code change was required or made**, per this approval's own instruction to leave
implementation untouched absent a genuine documentary-synchronization need. AUTO-002's
`AttemptKind.INITIAL_EXECUTION`/`AttemptKind.REPAIR` (`agentos_workflow/orchestrator/engine.py`)
already implement two of this approval's three streams as independent, durable counters exactly
as approved. The third stream — infrastructure retry (e.g. a flaky GitHub API call) — has no
corresponding code anywhere in `agentos_workflow/` today, because AUTO-002 implements no Skill,
Provider, or Git/GitHub call of any kind (`AUTO-002.md`'s own out-of-scope list) — there is no
infrastructure call yet for such a retry to apply to. Building that third counter is therefore
correctly deferred to whichever future stage first introduces an actual infrastructure call
(a Git/GitHub Skill, most likely AUTO-003 or AUTO-006) — that stage's own implementation must
honor this approval's three-way separation from the moment it introduces the first retryable
infrastructure call, not retrofit it later. Checked `docs/TASK_QUEUE.md`, `docs/current_task.md`,
`docs/PROJECT_STATE.md` for any other live content referencing OD-4's `Open` status needing
sync — none found beyond the AUTO-002 completion report, corrected separately in its own addendum.

**Alternatives considered:** Adding a placeholder third `AttemptKind` member to AUTO-002's code now,
even with no infrastructure call to drive it — rejected as speculative implementation for a
capability this stage's own contract explicitly excludes, and as exactly the kind of
unrequested, unused abstraction this repository's engineering discipline avoids elsewhere.

**Rationale:** OD-4 was a policy-confirmation gate, not an open design question — `WORKFLOW_STATES.md`
§5 already fully specified the three-way separation this approval ratifies; what was missing was
solely the Human Owner's sign-off making it load-bearing, which this entry supplies.

## 2026-07-24 — Governance Correction Record: OD-9 retry-classification defect fixed, a missing Dashboard changelog entry appended, and the AUTO-002 branch procedure made fully durable

**Decision:** A further independent audit (Codex) found three defects in how the already-approved
OD-8/OD-9 policies (entry directly below) and this recovery's own prior work were represented —
resolved here without revisiting either policy's substance.

1. **The OD-9 retry classification in `SKILL_CONTRACTS.md`/`MODEL_PROVIDER_CONTRACTS.md` was
   weaker than the approved policy.** Confirmed real by re-reading the exact prior text: it
   listed "process/network timeout, connection reset, DNS failure" as unconditionally
   `retryable` "before any confirmed side effect" — treating error *type* as determinative, when
   the approved policy makes error *timing* determinative ("absence of confirmation is not proof
   that no side effect occurred"). A timeout can occur exactly as easily after a `git push`
   already reached the remote as before it sent anything. Corrected: `SKILL_CONTRACTS.md` §5 and
   `MODEL_PROVIDER_CONTRACTS.md` §2 now classify strictly by timing — "proven pre-side-effect"
   is narrowed to failures before the underlying `git`/`gh`/provider subprocess was ever
   invoked (precondition-check failure, spawn failure); every failure surfaced by an
   already-invoked subprocess, regardless of how the error is labeled, defaults to the
   possible/unknown-side-effect (mandatory reconciliation) bucket. `WORKFLOW_STATES.md` §5a
   item 1 tightened to state this explicitly and rule out error-type-based classification. No
   new state or transition — this is a correction to make the documentation actually implement
   OD-9 as approved, not a new decision. Versions: `SKILL_CONTRACTS.md` 1.1 → **1.2**,
   `MODEL_PROVIDER_CONTRACTS.md` 1.1 → **1.2**, `WORKFLOW_STATES.md` 4.0 → **4.1** (wording
   fidelity to the existing MAJOR approval, not a further MAJOR change).
2. **`docs/agentos-dashboard/STAGE_REGISTRY.md`'s 4.0 → 5.0 transition (incorporating the OD-8
   mirror) had no corresponding `docs/agentos-dashboard/CHANGELOG.md` entry.** Confirmed by
   direct comparison: the changelog's newest entry (`CL-20260724-05`) only accounted for the
   3.0 → 4.0 step. Appended `CL-20260724-06` (newest-first, above the existing entries, none of
   which were touched) recording the 4.0 → 5.0 transition, its OD-8 reason, and the existing
   approval basis. Audited every other version transition from this recovery for a matching
   changelog entry — none else was missing.
3. **Live documents still framed AUTO-002's branch route as an open Human Owner choice,
   including renaming the recovery branch before merge.** That framing predates the settled
   release procedure. Rewrote `docs/PROJECT_STATE.md` ("In progress" and "Blockers"),
   `docs/TASK_QUEUE.md`, `docs/current_task.md`, `docs/remaining_tasks.md`,
   `docs/workflow-automation/STAGE_REGISTRY.md` §7, and `handover/PROJECT_HANDOVER.md` to state
   the durable procedure as settled fact: this recovery branch is reviewed, committed, pushed,
   merged, and deleted through the ordinary recovery release process, never renamed into the
   AUTO-002 branch; only after that does an AUTO-002 session begin from clean `main` and create
   the canonical branch; this is not a new AUTO-002 authorization, and implementation does not
   begin during governance recovery. `stage-prompts/AUTO-002.md` needed no change — it already
   named only the canonical branch, never the temporary one. `STAGE_REGISTRY.md` §5's append-only
   Authorization Log rows (the historical discovery) were **not** touched.

Verified after all edits: `workflowctl verify` — `task-state`/`governance`/`handover` PASS, `git`
FAILs only on the same pre-existing `upstream_missing`. `ruff`/`black`/`mypy` all pass; `pytest`
978 passed, unchanged. Exactly one `Current` task (AUTO-002, `BLOCKED`, unchanged). No lifecycle
transition, authorization, or AUTO-002 implementation changed; no stash mutated; no branch
renamed.

**Alternatives considered:** (a) For item 1, keeping the error-type-based classification and
just widening its exception list — rejected: any finite list of "usually pre-effect" error types
would still be vulnerable to the exact counterexample that motivated the finding (a timeout is a
timeout whether it happens before or after the write); timing, not type, is the only classifier
consistent with "absence of confirmation is not proof." (b) For item 2, folding the missing entry
into the existing `CL-20260724-05` — rejected: that entry is already written and this changelog
is explicitly append-only ("Entries are appended, never edited"). (c) For item 3, leaving
`docs/DECISION_LOG.md`'s own historical entries describing the original discovery unedited —
correct and done: only *live* documents describing *current/future* state were rewritten; the
append-only historical record stands.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`. All three are fidelity/completeness
corrections to already-approved policy and already-recorded facts — no new governance decision
was made, and the Human Owner's OD-8/OD-9 approvals (entry below) are unchanged.

## 2026-07-24 — Human Owner policy decisions recorded and applied: OD-8 (`SUPERSEDED` task-status semantics) and OD-9 (initial-execution failure policy)

**Decision:** The Human Owner supplied explicit policy decisions for the two design questions
the twelfth pass (entry below) deliberately left open, and directed that both be fully and
consistently applied. Both are recorded here verbatim as their approval basis, then summarized
by what changed.

**OD-8 approval, verbatim:**

> I approve the following policy:
>
> - A lifecycle stage in SUPERSEDED maps to task status Done.
> - Done here means administratively closed and no longer active or planned.
> - SUPERSEDED must not be represented as successful completion.
> - Lifecycle outcome remains distinguishable:
>   - COMPLETE means successfully completed.
>   - SUPERSEDED means closed because a Human Owner replaced or abandoned it in favor of another
>     authorized stage.
> - Any successor stage must have its own independent task record and lifecycle authorization.
> - SUPERSEDED must not automatically authorize or start a successor.
> - Define the legal source transitions to SUPERSEDED explicitly.
> - Do not introduce a new fourth task status.

**OD-9 approval, verbatim:**

> I approve the following policy for initial execution failures involving: implementation
> providers; commit operations; push operations; PR creation; comparable external or
> side-effecting operations.
>
> 1. TRANSIENT FAILURE BEFORE ANY SIDE EFFECT — Permit a bounded retry while remaining in the
>    same runtime state. The retry limit and retryable-error classification must be explicit and
>    deterministic. Exhausting the retry limit transitions the workflow to FAILED.
> 2. FAILURE WITH POSSIBLE OR UNKNOWN SIDE EFFECT — Do not retry blindly. First perform an
>    idempotency/reconciliation check while remaining in the same state. Determine whether the
>    intended side effect already occurred.
> 3. RECONCILIATION SUCCESS — If the side effect occurred correctly, advance to the runtime state
>    that accurately represents repository or remote reality. Do not duplicate the commit, push,
>    or PR.
> 4. RECOVERABLE INCONSISTENCY — If the state is inconsistent but safely repairable under the
>    existing recovery model, use the existing REPAIRING path. Do not invent a second repair
>    lifecycle.
> 5. UNRECOVERABLE OR INDETERMINATE FAILURE — Transition to FAILED when: retry is exhausted;
>    reconciliation cannot establish a safe state; the side effect is inconsistent and not safely
>    repairable; required invariants cannot be restored.
> 6. SAFETY — Never report success solely because a command timed out. Never repeat a
>    side-effecting operation without reconciliation. The Orchestrator owns the transition
>    decision based on typed Agent/Skill results. Existing authorization and clean-tree
>    requirements remain unchanged.
>
> Treat the new failure-trigger semantics as the appropriate normative governance change under
> the applicable version policy. Record this message verbatim as the Human Owner approval basis.

**What changed, OD-8:** `docs/workflow-automation/STAGE_REGISTRY.md` §2 (state-mapping sentence
now includes `SUPERSEDED` ≈ `Done`, with the administratively-closed-vs-successful distinction
stated explicitly) and rule 9 (rewritten: legal source states — `AUTHORIZED`, `BLOCKED`,
`IN_PROGRESS`, `SELF_REVIEW`, `REVIEW`, `APPROVAL`; never `NOT_STARTED`/`PROPOSED`/`COMPLETE`;
the `Done` mapping; no automatic successor authorization; a successor's independent task record
and authorization requirement) — version 5.0 → **6.0**. Mirrored into
`docs/agentos-dashboard/STAGE_REGISTRY.md` §1/rule 9 — version 4.0 → **5.0**. No fourth task
status was introduced anywhere; `self-governance.yaml`/`workflowctl` still recognize exactly
`Current`/`Planned`/`Done`. Cross-posted as `DECISIONS.md` DD-08. `OPEN_QUESTIONS.md` OD-8 moved
from Open to Resolved (its own append-only-by-convention Format). Checked `docs/TASK_QUEUE.md`,
`docs/PROJECT_STATE.md`, `docs/current_task.md`, `docs/remaining_tasks.md` for any live
`SUPERSEDED`-related content needing sync — none found (no stage is currently `SUPERSEDED`), so
none required editing.

**What changed, OD-9:** `docs/workflow-automation/WORKFLOW_STATES.md` gained new §5a
(Initial-Execution Failure and Reconciliation), restating the six-point policy in this
document set's own terms, scoped exactly to `IMPLEMENTING`, `READY_TO_COMMIT`, `COMMITTED`,
`PUSHED` (the implementation-provider invocation and the `create_commit`/`push_stage_branch`/
`create_pull_request` Skills) — no state or transition added; only new *reasons* on the four
already-existing `→ FAILED` edges for those states (already added in the ninth-pass approval)
and expanded reasons on their four forward edges (already existing); §3's table and explanatory
paragraph updated to name this as a third `→ FAILED` reason alongside the existing two — version
3.2 → **4.0**. Cross-referenced (not substantively changed) in `MACHINE_GATES.md` §1 (a third,
non-gate failure path, → 1.2), `FAILURE_RECOVERY.md` (new §1a distinguishing this from the
existing code-repair policy, Purpose line updated, → 1.2), `AGENT_CONTRACTS.md`
(`ImplementationAgent`/`GitAgent`/Agent-to-State-Map notes that the Orchestrator, never the
Agent, decides the resulting transition, → 1.2), `TEST_STRATEGY.md` (new §4b naming the required
test coverage for all five numbered outcomes plus the safety property, → 1.2). Added the
explicit, deterministic retryable/non-retryable error classification and 3-attempt retry limit
OD-9 item 1 requires to `SKILL_CONTRACTS.md` (Git/GitHub Skills, → 1.1) and
`MODEL_PROVIDER_CONTRACTS.md` (provider invocation, → 1.1). Cross-posted as `DECISIONS.md` DD-09.
`OPEN_QUESTIONS.md` OD-9 moved from Open to Resolved. Checked `docs/TASK_QUEUE.md`,
`docs/PROJECT_STATE.md` for any live content needing sync — none found (no provider/commit/push/
PR failure is currently in progress; AUTO-002 has not started implementation), so none required
editing.

**Design judgment calls made while applying OD-9 (flagged explicitly, not silently decided):**
(a) "comparable external or side-effecting operations" in the approval's own preamble was read
narrowly — applied only to the four operations the approval's numbered policy and this
program's own document set actually name (provider invocation, `create_commit`,
`push_stage_branch`, `create_pull_request`) — not extended to `enable_automatic_squash_merge`,
`read_required_checks`, or the Closeout Skills, which already have their own complete gate
semantics in `MACHINE_GATES.md` §5–§7 that this decision does not touch. (b) Item 4's "use the
existing REPAIRING path" was read as applying only where `REPAIRING` is actually reachable today
(from `IMPLEMENTING`, via the existing `VALIDATING` route) — for `READY_TO_COMMIT`/`COMMITTED`/
`PUSHED`, where no code-fix path exists, an unresolved inconsistency was read as falling to item
5 (`FAILED`) rather than inventing a new edge into `REPAIRING` from those states. Both are
documented here so the Human Owner can correct either reading if it does not match intent.

**Alternatives considered:** for OD-8, mapping `SUPERSEDED` to `Current` instead of `Done` (it
*was* rejected by the user's own explicit "Done here means administratively closed" instruction,
recorded only for completeness) — the approval is unambiguous and was applied as given, not
re-derived. For OD-9, adding a literal `IMPLEMENTING → REPAIRING` edge for a cleaner-looking
direct path — rejected per the "do not invent a second repair lifecycle" instruction and this
recovery's standing preference for reusing existing edges over adding new ones wherever the
existing model already suffices.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`'s requirement that governance changes,
including policy decisions with their approval basis, be logged verbatim rather than summarized
or inferred. Both approvals were applied completely and consistently across every document named
in the Human Owner's own audit list, with the two judgment calls above disclosed rather than
silently resolved.

## 2026-07-24 — Governance recovery, twelfth pass: approved consistency fixes applied; two design questions deferred

**Decision:** The latest independent Codex review produced six findings. A subsequent
classification pass, performed without repository mutation, classified four as corrections that
do not require a new Human Owner policy decision and two as unresolved design decisions. The
operator then explicitly directed this recovery to apply only the four non-policy corrections,
record the other two as open questions without selecting a policy, rerun the complete validation
suite, and perform no release action or AUTO-002 implementation.

Applied corrections:

1. **Dashboard resume preflight:** `docs/agentos-dashboard/STAGE_REGISTRY.md` now restates AUTO
   rule 19's already-established initial-start/resume distinction as Dashboard rule 20, and the
   Dashboard SSP has matching initial-start and resume sections. This closes a real inconsistency
   with that registry's existing substantive-equivalence rule. It adds no state or transition:
   pass and fail during resume both leave registry state unchanged, and neither changes
   authorization or task status. Registry 3.0 → 4.0 under its control-rule revision policy; SSP
   1.2 → 1.3.
2. **Dashboard/AUTO rule crosswalk:** the explanatory equivalence range now includes Dashboard
   rule 20 ↔ AUTO rule 19. No governing behavior changed independently of item 1.
3. **Machine-gate count wording:** `WORKFLOW_STATES.md` now identifies six named gates correctly:
   the single Precondition gate spans two transition-source states, followed by five one-state
   gates. No state, transition, trigger, gate condition, or failure policy changed; version
   3.1 → 3.2 as a wording-only clarification.
4. **Git stash wording:** the handover now says the recovery branch is the sole local branch
   without an upstream, rather than the sole "unpushed ref," and separately records the two
   retained local stash snapshots. No stash was applied, dropped, or modified.

Deliberately unresolved, with no policy invented:

- `OPEN_QUESTIONS.md` OD-8 records the missing `SUPERSEDED` development-stage task-status
  mapping. The existing state, transitions, Human Owner directive requirement, and three-status
  task model remain unchanged.
- `OPEN_QUESTIONS.md` OD-9 records the undefined initial-execution failure policy for provider,
  commit, push, and PR operations. The runtime transition table, transition reasons,
  authorization model, repair counter, and release behavior remain unchanged.

**Alternatives considered:** implementing a `SUPERSEDED` mapping or assigning ordinary
initial-execution failures to an existing `→ FAILED` edge — rejected for this pass because each
would select new semantics among multiple valid policies and therefore requires a Human Owner
decision. Treating the Dashboard resume defect as the same kind of policy gap was also rejected:
the Dashboard registry already promises substantive equivalence with AUTO except for its named
Rollback rule, so mirroring AUTO's zero-transition resume preflight corrects an existing promise
rather than expanding it.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`. This pass is restricted to internal
consistency and factual synchronization. It does not start or re-authorize AUTO-002 and does not
authorize a commit, push, pull request, merge, branch rename, stash mutation, or branch deletion.

## 2026-07-24 — Governance recovery, eleventh pass: initial-start/resume preflight separated, GOV-2 mirrored into all remaining-work summaries, and the AUTO-002 branch blocker made durable

**Decision:** An eleventh independent audit (Codex) raised three further findings.

1. **The SSP's single preflight check ("status is `AUTHORIZED`") made resuming an already-
   `IN_PROGRESS` AUTO-00x stage impossible**, since a session picking up mid-implementation would
   find registry state `IN_PROGRESS`, not `AUTHORIZED`, and fail the literal check. Confirmed
   real by direct re-reading of `stage-prompts/README.md`'s prior text, which stated one
   undifferentiated check "before any change" with no resume carve-out. Resolved with **no new
   transitions**: added `STAGE_REGISTRY.md` §3 rule 19 (Resume Preflight), which states the legal
   resume-state set (`IN_PROGRESS`/`SELF_REVIEW`/`REVIEW`/`APPROVAL` — never `AUTHORIZED` again),
   requires re-verifying the same execution preconditions checked at initial start, and — for
   both the pass and fail outcome — causes **zero registry transition**: a passing resume simply
   continues (rule 5's existing "stage stays `IN_PROGRESS`" principle, now stated to also cover
   resume, not only review-retry); a failing resume stops the session and reports to the Human
   Owner without moving to `BLOCKED` (`BLOCKED` remains reserved for the pre-`IN_PROGRESS` case,
   rule 17) and without triggering re-authorization. This required no Human Owner approval:
   `STAGE_REGISTRY.md` §8's revision policy requires only a MAJOR version bump for control-rule
   changes, not the separate "Human Owner review" gate `WORKFLOW_STATES.md` §11 imposes for its
   own (different) machine — confirmed by re-reading both documents' revision-policy text
   side by side. The SSP (`stage-prompts/README.md`) was restructured into explicit
   "Initial-start preflight" and "Resume preflight" sections citing rules 4 and 19 respectively;
   `stage-prompts/AUTO-002.md` reworded to cite both. On the runtime-machine side
   (`WORKFLOW_STATES.md`), the existing model (built and Human-Owner-approved in the ninth/tenth
   passes) already fully satisfies the same initial-start/resume distinction — confirmed by
   re-reading `WORKFLOW_STATES.md` §6, `FAILURE_RECOVERY.md` §6, `TEST_STRATEGY.md` §4a, and
   `AGENT_CONTRACTS.md` directly; only a labeling paragraph was added to `WORKFLOW_STATES.md` §3
   (no new transition) making the initial-start/resume phase split explicit there too.
2. **`GOV-2` was a `Planned` task in `docs/TASK_QUEUE.md` and `docs/remaining_tasks.md` but
   absent from `docs/PROJECT_STATE.md`'s "Planned" section and `handover/PROJECT_HANDOVER.md`'s
   "What's next" summary.** Confirmed by direct re-reading of both files — neither mentioned it.
   Added to both, preserving the existing AUTO/DASH/governance-tooling distinction (GOV-2 is
   explicitly framed as the one non-AUTO/DASH-family Planned task in each), kept `Planned`, not
   described as implemented or authorized.
3. **Every live description of AUTO-002's branch blocker named the specific temporary
   governance-recovery branch** (`feature/auto-002-orchestrator-foundation`) as the subject of
   the mismatch — an assertion that becomes false the moment that branch is merged and deleted.
   Rewrote every live-state document (`docs/PROJECT_STATE.md`, `docs/TASK_QUEUE.md`,
   `docs/current_task.md`, `docs/remaining_tasks.md`, `handover/PROJECT_HANDOVER.md`,
   `docs/workflow-automation/STAGE_REGISTRY.md` §7) to state the blocker as a durable rule
   independent of any branch name: `BLOCKED` until this recovery merges; an AUTO-002 session must
   then begin from updated clean `main` and create/check out the canonical branch
   (`feature/auto-002-orchestrator-state-machine`, unchanged — not reauthorized, not renamed);
   that branch must pass the initial-start branch-binding/clean-tree checks before
   `AUTHORIZED → IN_PROGRESS`. `STAGE_REGISTRY.md` §5's append-only Authorization Log rows
   (which do name the temporary branch, as an accurate record of what was found on 2026-07-24)
   were **not** touched — they remain the correct historical record of the original discovery;
   only the *live, ongoing* assertions in the documents above were made durable.

Verified after all edits: `workflowctl verify` — `task-state`/`governance`/`handover` PASS, `git`
FAILs only on the same pre-existing `upstream_missing`. `pytest` 978 passed, unchanged;
`ruff`/`black`/`mypy` all pass. Exactly one `Current` task (AUTO-002, `BLOCKED`, unchanged). No
lifecycle transition changed; no AUTO-002 implementation performed; AUTO-002's canonical branch
binding, authorization, and this recovery's own working branch were none of them altered.

**Alternatives considered:** (a) For item 1, adding a literal `IN_PROGRESS → BLOCKED` transition
for resume failures (mirroring rule 17's `AUTHORIZED → BLOCKED` pattern) — rejected: it would
recreate the exact `BLOCKED`-must-return-to-`AUTHORIZED`-not-`IN_PROGRESS` deadlock pattern fixed
in the fourth pass, this time demoting a stage that may have substantial `IN_PROGRESS` work
already done; rule 5's "stage stays `IN_PROGRESS`" principle already covers this with zero new
transitions, so it was extended rather than a new one added. (b) For item 3, editing
`STAGE_REGISTRY.md` §5's authorization-log rows to remove the temporary branch's name — rejected:
those rows are the append-only historical record of what was actually found on 2026-07-24 on that
actual branch; removing the name would falsify history rather than make it durable — durability
belongs in the *live* documents describing *current* and *future* state, not in the log of what
already happened.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`. Item 1 closes a genuine SSP defect with no
new normative surface, consistent with this recovery's repeated preference for extending an
existing rule's stated scope over inventing a new transition. Items 2 and 3 are completeness/
durability corrections to already-established facts, not new governance decisions.

## 2026-07-24 — Governance recovery, tenth pass: Dashboard SSP formatter documentation resynchronized, and Dashboard changelog completeness closed

**Decision:** A tenth independent audit (Codex) raised two further findings, both scoped to
`docs/agentos-dashboard/`:

1. **`docs/agentos-dashboard/stage-prompts/README.md` still described the removed pre-commit
   pipeline.** Its pre-commit warning named `` `ruff --fix`, `ruff-format` `` as the auto-fixing
   hooks — stale since the seventh pass removed `ruff-format` from `.pre-commit-config.yaml`
   entirely (Black is the sole formatter; `ruff-check` is lint/import-sort only). Checked
   `docs/workflow-automation/stage-prompts/README.md` (the AUTO program's equivalent) for the
   same staleness — it does not name specific hooks, so it was not stale in this way and needed
   no change. Fixed the DASH SSP to name the actual current hooks in actual pre-commit order
   (`ruff-check --fix`, `black`, `mypy`, matching `.pre-commit-config.yaml` exactly) and added
   `` `ruff format --check .` `` to its recorded validation-command list, matching the AUTO
   program's SSP and this repository's actual validation practice. No repository policy changed
   — only the documentation was synchronized with the already-implemented toolchain (→ 1.2).
2. **`docs/agentos-dashboard/CHANGELOG.md` was missing entries for two already-approved
   revisions**: `STAGE_REGISTRY.md` 2.0 → 3.0 (the seventh-pass rule-17 gap fix and narrowed
   equivalence claim, entry directly below) and `stage-prompts/README.md` 1.0 → 1.1 (the
   fifth-pass `BLOCKED`/SSP-deadlock mirror, entry below), plus the 1.1 → 1.2 change this same
   entry's item 1 just made. Appended three new entries (`CL-20260724-02..04`) to
   `docs/agentos-dashboard/CHANGELOG.md`, each naming version, reason, the pre-existing approval
   basis (this log's own prior entries — no new authorization act), date, and affected files. The
   existing three entries were not touched, per that file's own explicit "Entries are appended,
   never edited" convention.

Verified after the edits: `workflowctl verify` — `task-state`/`governance`/`handover` PASS,
`git` FAILs only on the same pre-existing `upstream_missing`. `ruff format --check .` /
`black --check .` / `ruff check .` / `mypy src` all pass; `pytest` 978 passed, unchanged.

**Alternatives considered:** (a) Editing `docs/agentos-dashboard/CHANGELOG.md`'s existing
`CL-20260724-01` entry to also mention the SSP 1.0 → 1.1 change it happened alongside — rejected:
that entry is already written and this file is explicitly append-only; a new entry documents
what was missed instead. (b) Leaving the DASH SSP's stale hook names since removing
`ruff-format` was itself already fully documented in `docs/DECISION_LOG.md` — rejected: a stage
session executing the SSP verbatim would still be told to expect a hook that no longer exists;
the SSP itself, not just the decision record, needed to reflect current reality.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`. Both items are documentation-synchronization
fixes, not new governance decisions — no repository policy changed, only stale documentation
brought into agreement with already-implemented, already-approved reality.

## 2026-07-24 — Governance recovery, eighth pass: ruff-format/black disagreement fixed at the source file, and governance-validator overclaiming audited (none found)

**Decision:** An eighth independent audit (Codex) raised two further findings and reopened the
failure-transition-completeness question resolved in the entries above.

1. **`ruff format --check .` still failed on `tests/test_migration_plan_apply.py`** even after
   the prior pass removed `ruff-format` as a pre-commit gate — Codex correctly required it not
   be left failing regardless of gate status. Diagnosed as (B) a genuine ruff-format/black
   disagreement on wrapping a long `assert cond, "msg"` (ruff-format hugs the message in trailing
   parens; black wraps the condition instead) — not formatting debt (A) or unstable test logic
   (C). Fixed by extracting the message to a short-lived local variable so the line no longer
   needs wrapping by either tool; both formatters now produce byte-identical output. Verified:
   `ruff format --check .` → "88 files already formatted" (was 1 disagreeing); `black --check .`
   clean; `pytest tests/test_migration_plan_apply.py` → 15 passed, unchanged behavior.
2. **Audited every mention of `check-governance`/`check-task-state`/`workflowctl verify` across
   `docs/CONTEXT.md`, `docs/TASK_QUEUE.md`, and both programs' `STAGE_REGISTRY.md` rule 11/16**
   for overclaiming registry or lifecycle coverage. Found none: every mention already scopes the
   claim precisely to task-status mirror agreement and the `version` fact — never to
   `STAGE_REGISTRY.md` content. `GOV-2`'s existing entry (prior pass) already states the current
   limitation accurately. No documentation changes were needed for this finding; lightweight
   validation remains correctly deferred to `GOV-2`, unimplemented, for the same authorization
   reasons as before.

The failure-transition-completeness question these two findings' audit reopened is resolved in
the entry above (eight approved transitions, Human Owner approval quoted verbatim) — not
repeated here.

**Files changed:** `tests/test_migration_plan_apply.py` (message extracted to a local; no logic
change). No governance document required a change for item 2.

**Verified after the edit:** `ruff check .` / `ruff format --check .` / `black --check .` /
`mypy src` all pass; `pytest` 978 passed (was 978 before — this pass added no new tests, the
existing test's assertion behavior is unchanged); `workflowctl verify` — `task-state`/
`governance`/`handover` PASS, `git` FAILs only on the same pre-existing `upstream_missing`.

**Alternatives considered:** (a) For item 1, pinning `ruff-format` to an older version believed
compatible with the installed `black` instead of restructuring the test — rejected: no version
pair is guaranteed to stay compatible, whereas removing the line-wrapping decision entirely
(short enough line, no wrap needed) cannot regress by tool version drift. (b) For item 2, adding
speculative disclaimers to every governance document "just in case" — rejected: the audit found
no actual overclaiming, and adding unnecessary hedges to already-accurate text would itself be a
form of the imprecision this recovery has been correcting elsewhere.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`. Item 1 is a genuine repository/tooling
defect fixed at its source rather than patched around; item 2 is a verification that produced a
negative result (nothing to fix), recorded so the audit itself is traceable.

## 2026-07-24 — Human Owner approval recorded: `WORKFLOW_STATES.md` §11 MAJOR change (eight normative runtime transitions completing the failure-transition model)

**Decision:** The Human Owner explicitly reviewed and approved, in this Governance Recovery
session, the addition of eight normative runtime transitions to
`docs/workflow-automation/WORKFLOW_STATES.md` §3, closing the gap an independent audit (Codex)
identified: `TEST_STRATEGY.md` §4a requires interruption/authorization-drift testing "at each
state," but §3's table listed `→ FAILED` from only 7 of the 15 non-terminal, non-`CREATED`
states.

**The eight approved transitions:**

- `BRANCH_CREATED → FAILED`
- `IMPLEMENTING → FAILED`
- `REPAIRING → FAILED`
- `READY_TO_COMMIT → FAILED`
- `COMMITTED → FAILED`
- `PUSHED → FAILED`
- `AUTO_MERGE_ENABLED → FAILED`
- `MERGED → FAILED`

For `REPAIRING` specifically, the Human Owner approved the transition for **both** (a)
authorization-drift/interruption detection (the same reason as the other seven) and (b)
unrecoverable failure of the repair attempt itself (provider crash/timeout with no output to
re-validate) — a `REPAIRING`-specific third reason, distinct from (a) and from the
already-covered exhausted-3-attempts path (which fails out via `VALIDATING`/`QA_RUNNING`).

**Classification:** MAJOR, per `WORKFLOW_STATES.md` §11. This is a **separate** MAJOR change
from the three-transition approval recorded earlier today (which brought the document to
2.0) — per the Human Owner's explicit instruction not to reuse that version number, this change
brings `WORKFLOW_STATES.md` to **3.0**.

**Approval basis — quoted verbatim, in full:**

> HUMAN OWNER APPROVAL (this message is the required review/approval).
>
> I approve adding these 8 normative transitions to WORKFLOW_STATES.md, classified as a MAJOR
> change under §11:
> - BRANCH_CREATED → FAILED
> - IMPLEMENTING → FAILED
> - REPAIRING → FAILED
> - READY_TO_COMMIT → FAILED
> - COMMITTED → FAILED
> - PUSHED → FAILED
> - AUTO_MERGE_ENABLED → FAILED
> - MERGED → FAILED
>
> Rationale: authorization drift can surface when resuming from any non-terminal in-flight
> state; interruption recovery needs a legal terminal failure path; TEST_STRATEGY.md requires
> drift testing at each applicable state; the canonical table must not forbid behavior required
> elsewhere in normative governance.
>
> For REPAIRING specifically, approve the FAILED transition for both (a) authorization-drift/
> interruption detection, and (b) unrecoverable failure of the repair attempt itself.

No approval is inferred, assumed, or fabricated beyond what is quoted above.

**Purpose:** to make `WORKFLOW_STATES.md` §3 the complete, closed set of every legal `→ FAILED`
transition in this model, so no prose requirement elsewhere (`§6` interruption recovery,
`FAILURE_RECOVERY.md` §1/§6, `TEST_STRATEGY.md` §4a) implies a transition the canonical table
omits.

**Consistency updates made across the affected document set** (all citing this approval, none
independently re-deciding anything): `WORKFLOW_STATES.md` §3 (the eight rows, plus one
disambiguating paragraph distinguishing the two/three reason-classes populating `→ FAILED`) and
§6 item 3 (cross-reference confirming completeness); `MACHINE_GATES.md` §1 (new paragraph
clarifying its six gates are the forward-progress subset, not the exhaustive `→ FAILED` source,
→ 1.1); `FAILURE_RECOVERY.md` §1 (the `REPAIRING`-specific unrecoverable-attempt path, distinct
from the exhausted-attempts path, → 1.1); `TEST_STRATEGY.md` §4a (cross-reference confirming
"at each state" now has a legal transition to exercise at every state named, → 1.1);
`AGENT_CONTRACTS.md` §8 (a new Agent-to-State Map row attributing the drift-driven transitions to
the Orchestrator, not any named Agent, → 1.1).

**Scope of this approval:** as with the prior `WORKFLOW_STATES.md` approval, this concerns only
the classification and version number of this documentation change. **It does not authorize
AUTO-002 implementation or any commit, push, pull request, merge, or branch rename.** AUTO-002
remains `Current`/`BLOCKED`, unchanged.

**Alternatives considered:** (a) Treating `REPAIRING`'s unrecoverable-attempt case as already
implied by the drift-path approval and not calling it out separately — rejected per the Human
Owner's own explicit instruction to approve it as a distinct, named reason. (b) Reusing version
2.0 since both approvals happened "today" — rejected per the Human Owner's explicit instruction
that a further MAJOR change beyond the already-approved 2.0 change must not reuse that number.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`'s requirement that governance changes,
including MAJOR version classifications, be logged with their approval basis quoted verbatim,
not summarized or inferred.

## 2026-07-24 — Human Owner approval recorded: `WORKFLOW_STATES.md` §11 MAJOR change (three normative runtime transitions)

**Decision:** The Human Owner explicitly reviewed and approved, in this Governance Recovery
session, the addition of three normative runtime transitions to
`docs/workflow-automation/WORKFLOW_STATES.md` §3:

- `AUTHORIZED → FAILED`
- `PRECONDITIONS_CHECKED → FAILED`
- `PR_OPEN → FAILED`

**Classification:** MAJOR, per `WORKFLOW_STATES.md` §11 ("Any new state or transition is a MAJOR
change to this document and requires Human Owner review, since it changes the machine-gate
surface that stands in for human approval after authorization."). A prior governance-recovery
pass added these three transitions but classified the change as MINOR (version bump 1.1 → 1.2)
without a separate, explicit Human Owner review act for this specific document under this
specific policy — an independent audit (Codex) correctly identified this as unresolved. This
entry supplies that missing review and closes the gap; `WORKFLOW_STATES.md` is now version 2.0.

**Approval basis:** the Human Owner's direct, explicit instruction in this session: "I explicitly
approve the addition of these three normative runtime transitions: AUTHORIZED → FAILED,
PRECONDITIONS_CHECKED → FAILED, PR_OPEN → FAILED. Treat this message as the required Human Owner
review and approval under WORKFLOW_STATES.md §11. Classify the change as MAJOR. Bump
WORKFLOW_STATES.md to version 2.0." No approval is inferred, assumed, or fabricated — it is
quoted verbatim above.

**Purpose:** to reconcile `WORKFLOW_STATES.md` §3's canonical transition table with failure
behavior that `MACHINE_GATES.md` §2 (Precondition Gate) and §5/§8 (Merge Safety Gate) already
state as normative and mandatory — `MACHINE_GATES.md` documents these three gates failing to
`FAILED` from `AUTHORIZED`, `PRECONDITIONS_CHECKED`, and `PR_OPEN` respectively, and prior to this
change `WORKFLOW_STATES.md` §3 did not list any of the three, an inconsistency between two
equally normative documents (found and reasoned through in the prior "fifth pass" entry below).
This approval brings the transition table into agreement with behavior that was already
mandatory, rather than introducing new machine-gate behavior that did not exist before.

**Scope of this approval:** this approval concerns only the classification and version number of
this specific documentation change. **It does not authorize AUTO-002 implementation, any
commit, push, pull request, merge, or branch rename, or any other release action.** AUTO-002
remains `Current`/`BLOCKED` in `docs/TASK_QUEUE.md` and `docs/workflow-automation/
STAGE_REGISTRY.md` §4, unchanged by this entry.

Updated for consistency with the 2.0 version number: `docs/CHANGELOG.md`,
`docs/workflow-automation/CHANGELOG.md`, and `handover/PROJECT_HANDOVER.md` (+ regenerated
`handover/PROJECT_CHECKSUM.md`) — see the entries/edits following this one for the exact changes.

**Alternatives considered:** (a) Classifying as MINOR on the reasoning that
`MACHINE_GATES.md` already mandated this behavior, so nothing "new" was added to the system's
actual behavior — this was presented to the Human Owner as an available option; not chosen. (b)
Reverting the three transitions pending a separately authorized future task — also presented;
not chosen. (c) Silently leaving the MINOR classification uncorrected — never a real option,
since the mission underlying this recovery explicitly required stopping and asking rather than
fabricating or assuming approval for exactly this kind of self-versioning-policy question.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`'s requirement that governance changes,
including version classifications for documents with their own explicit revision policy, be
logged with their approval basis and rationale — verbatim, not summarized or inferred.

## 2026-07-24 — Governance recovery, seventh pass: Dashboard/AUTO equivalence claim corrected, stale AUTO-002 authorization wording fixed, formatter non-determinism eliminated, and governance-validator coverage gap tracked

**Decision:** A seventh independent audit (Codex) raised four further findings and one release
gate. Resolved as follows:

1. **The claim that Dashboard and AUTO registry rules are "identical in substance" was audited
   rule-by-rule against the actual current text of both files, not asserted.** Found: (a) a real
   gap — `docs/agentos-dashboard/STAGE_REGISTRY.md` rule 17 (Closeout) was missing the entire
   `git`-check exception-tolerance clause that `docs/workflow-automation/STAGE_REGISTRY.md` rule
   16 has (task-state/governance/handover PASS with no exception, `git` PASS unless pre-existing
   and unrelated to the merge) — fixed by adding the matching clause to DASH's rule 17; (b) DASH
   has one genuine, intentional program-specific rule with no AUTO counterpart — rule 14
   (Rollback, concerning `dashboard.db`, an artifact AUTO has no equivalent of). Every other rule
   (1–13, 15–19 in DASH ≈ 1–13, 14–18 in AUTO, accounting for the rule-14 offset) was checked and
   found substantively equivalent, differing only in verbosity (DASH states some rules — early-
   start prevention, evidence-before-completion — with more procedural detail; this is
   longstanding original-authorship wording, not new drift, and not a contradiction). `docs/
   agentos-dashboard/STAGE_REGISTRY.md` §1 was reworded from a blanket "identical in substance"
   claim to a precise list (which rules are shared, which is program-specific), so the claim is
   now exactly as strong as the evidence supports.
2. **`docs/workflow-automation/STAGE_REGISTRY.md` §7 stated "AUTO-002 authorization requires
   AUTO-001 `COMPLETE` plus a fresh Human Owner record"** — stale: both conditions were already
   satisfied and recorded on 2026-07-24 (§5). Reworded to state this as a completed fact (with the
   date and evidence location), distinguish it from AUTO-002's actual, still-open item (the
   execution-precondition branch mismatch, unrelated to authorization), and contrast it with
   AUTO-003, whose authorization precondition genuinely remains outstanding (AUTO-002 has not
   reached `COMPLETE`) — so the same sentence pattern is not applied where it would itself become
   stale.
3. **Formatter non-determinism, investigated as a release gate rather than dismissed.** Root
   cause confirmed, not assumed: `.pre-commit-config.yaml` ran **two different formatters**
   (`ruff-format` and `black`) over the same files, which have measurably diverged (a long
   parenthesized `assert x, "msg"` is wrapped differently by each), so which one "won" depended on
   hook order and left the other's preferred form as a perpetual pending diff — this was the
   actual non-determinism, not merely stale version pins. `docs/workflow-automation/
   stage-prompts/README.md`'s own required validation command list has only ever named
   `ruff check .` and `black --check .` — never `ruff format --check .` — confirming Black is this
   repository's actual canonical formatter and `ruff-format`'s presence in the pre-commit hook set
   was the misconfiguration. Fixed: removed the `ruff-format` hook entirely (ruff now runs
   `ruff-check --fix` only — linting and import-sorting, not formatting); separately, and because
   drift existed there too, re-pinned all three hooks to the exact revisions matching the locally
   installed tool versions confirmed by direct version query (`ruff-pre-commit` v0.12.3 → v0.15.21;
   `black-pre-commit-mirror` 25.1.0 → 25.12.0; `mirrors-mypy` v1.16.1 → v1.20.2 — all three tags
   confirmed to exist via `git ls-remote` before pinning). Verified idempotent: `pre-commit run
   --all-files` run twice in sequence from a clean pre-commit cache, both runs reporting all three
   hooks Passed with zero file modifications either time (previously, every run had mutated
   `tests/test_migration_readers.py`). `black --check .` passes repository-wide;
   `ruff format --check .` still disagrees with `black` on one file, which is now expected and
   non-blocking, since `ruff-format` is no longer a gate.
4. **Governance-validator coverage assessed, not implemented.** Read
   `src/ai_workflow_engine/governance/validators.py` directly: `check_governance`/
   `check_task_state` validate only task-status mirror agreement and byte-equality of configured
   regex "facts" (currently just `version`) — neither reads either program's `STAGE_REGISTRY.md`
   at all. Confirmed this cannot be safely retrofitted via `self-governance.yaml` configuration
   alone: the existing fact-checker only expresses byte-equality, and a registry-state-to-
   task-status check needs a semantic mapping (`BLOCKED` ≈ `Current`, etc.), which requires new
   code. Writing that code now would be implementation work outside a governance-recovery
   session's mandate, and — applying this recovery's own rules to itself — a new `workflowctl`
   validator is engine functionality requiring its own stage authorization and independent
   review, not something to add unauthorized during a documentation pass. Tracked instead as
   **GOV-2** (`docs/TASK_QUEUE.md`, `Planned`), with the exact gap, why config alone can't close
   it, and a recommended shape for when it is authorized, so the limitation is documented rather
   than left implied.

**Not resolved in this entry:** the WORKFLOW_STATES.md version-policy question (whether adding
the three failure transitions found in the prior pass was a MAJOR change requiring explicit
Human Owner review before the version number reflects it) is a genuine open decision, not
something this entry resolves — see the immediately following note to the Human Owner; no version
number or approval claim has been fabricated for it.

Verified after the edits above: `workflowctl verify` — `task-state`/`governance`/`handover` PASS;
`git` FAILs only on the same pre-existing `upstream_missing`. `pytest` 978 passed;
`pytest --collect-only` 978 collected (unchanged); `mypy`/`ruff check`/`black --check` all pass;
`git diff --check` clean; `git fsck --full` shows two pre-existing dangling commits dated
2026-07-21 (before this entire recovery), unrelated to this session's work. Exactly one `Current`
task (AUTO-002, `BLOCKED`, unchanged). No lifecycle transition changed; no AUTO-002
implementation performed; no commit, push, PR, merge, or branch rename.

**Alternatives considered:** (a) For the Dashboard/AUTO claim, leaving it as a blanket assertion
since most rules genuinely do match — rejected: one real gap existed, and an unverified blanket
claim is exactly the failure mode being corrected throughout this recovery. (b) For the formatter
fix, pinning `ruff-format` and `black` to some specific version pair believed compatible instead
of removing one — rejected: no version pair is guaranteed to stay compatible as either tool
evolves, whereas removing the redundant formatter is a structural fix that cannot regress by
version drift, and it matches what this repository's own documented validation commands already
required. (c) For GOV-2, writing the validator now since the gap is well-understood and the fix
sounds small — rejected: "small" is not the test; authorization and review discipline apply
regardless of estimated size, per this recovery's own repeatedly-stated principle that fixing
governance must not itself bypass governance.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`. Items 1–2 are further mis-citation/staleness
corrections in the pattern of earlier passes; item 3 is a genuine repository/tooling defect now
fixed at its root cause rather than patched; item 4 is a scoping decision, documented so the
absence of coverage is never mistaken for its presence.

## 2026-07-24 — Governance Correction Record: append-only grandfathering exception for two pre-protocol edits, closed and non-repeatable

**Decision:** A sixth independent audit (Codex) correctly found that declaring this log
append-only (fourth-pass entry, "this log's own append-only rule was violated twice...") while
leaving two disclosed-but-unremedied in-place edits sitting in the live document is an
unreconciled contradiction: an absolute "never edited" rule cannot coexist with acknowledged
historical edits that are neither undone nor formally excepted. Two ways to close this were
available: (A) restore the two edited entries to their exact original bytes and layer corrections
on top, or (B) define a precise, closed, non-repeatable grandfathering exception covering exactly
those two edits. **Chosen: (B).** (A) was rejected on reflection: it would require re-inserting
the original incorrect `HUMAN_AUTHORIZATION_MODEL.md` citation text back into the live log as
"restored," which is more likely to mislead a future reader who does not carefully trace the
correction layered after it than a plainly labeled, bounded exception is. `STAGE_REGISTRY.md` §5
kept the (A) treatment already applied to it in the fourth pass — that was a two-row table, cheap
and unambiguous to restore verbatim; the reasoning here is specific to this log's longer prose
entries, not a reversal of that choice.

**The exception, defined completely and precisely:**

- **Scope (exactly these two edits, no others):** (1) the second governance-recovery pass's
  removal of the `HUMAN_AUTHORIZATION_MODEL.md` §2/§4 citation from the "2026-07-24 — AUTO-001
  closed out to Done; AUTO-002 authorized but halted on a branch-binding mismatch" entry
  (replaced in place with an inline editorial-correction bracket, rather than left untouched with
  a separate appended correction); (2) that same pass's wholesale replacement of the first pass's
  "Governance recovery: corrected a mis-cited authority and a non-canonical registry state for
  the AUTO-002 block" entry with the "Governance recovery, completed: ..." entry that follows
  this one, rather than appending the latter alongside the former.
- **Cutoff:** both edits were made before the fourth-pass entry ("this log's own append-only rule
  was violated twice...", immediately below the "completed" entry) first stated this log's
  append-only rule in explicit words. No edit made after that entry is, or can be, covered — the
  fourth and fifth passes made zero in-place edits to any entry, confirmed by re-reading this
  file's full history when preparing this entry.
- **Non-repeatable:** this is a one-time exception for the two edits above, closed as of this
  entry. It sets no precedent and authorizes nothing else; any future incorrect entry is fixed
  exclusively by a new appended Governance Correction Record, with no exception route available.
- **Preserved disclosure:** the fourth-pass entry's full account of what was edited and why
  remains below, unedited, and is incorporated here by reference rather than restated.
- **Human Owner basis:** this session's operator has, across this Governance Recovery
  conversation, directly authored every instruction actually executed (the mission text framing
  each pass, including this one) — the same standing this repository's other authorization
  records treat as the Human Owner's explicit direction. This entry's specific basis is the
  operator's instruction in this turn to resolve Finding 2 "via either (A) ... or (B) ... a
  narrowly scoped, explicit, non-repeatable grandfathering exception ... with defined
  cutoff/entries, preserved disclosure, recorded Human Owner basis" — i.e., the operator named
  option (B) and its required components directly; choosing and fully specifying it here is
  acting on that explicit direction, not inferring authorization from silence.

Verified after this edit: no entry other than this one was modified; `docs/DECISION_LOG.md`'s
full entry count and every other entry's byte content is unchanged from before this edit.

**Alternatives considered:** covered above (choice of (B) over (A)). Also considered: leaving
the contradiction as a documented "known limitation" without resolving it — rejected, since the
mission is explicit that "no absolute 'never edited' rule can coexist with unexplained historical
edits," which requires resolving the contradiction, not further documenting it.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`. This entry converts an absolute,
unreconciled append-only claim into a rule with exactly one bounded, already-disclosed, closed
exception, which is both true to what actually happened and leaves no ambiguity for future
sessions about what may or may not be edited going forward (nothing, ever, again).

## 2026-07-24 — Governance recovery, fifth pass: Rule 16 revised (not the authorizations invalidated), every registry audited repository-wide, runtime failure-transitions synchronized, and Rule 1's artifact list completed

**Decision:** A fifth independent audit (Codex) raised four further findings, investigated and
resolved as follows, all in `docs/workflow-automation/STAGE_REGISTRY.md` (bumped 4.0, another
MAJOR change) unless noted:

1. **Rule 16 ("no successor selected in the same session") contradicted the Decision Log,
   which records both DASH-001→AUTO-001 and AUTO-001→AUTO-002 closing out a predecessor and
   authorizing a successor within one continuous session.** Codex was correct that this happened
   — verified against both 2026-07-23 and 2026-07-24 entries independently of this recovery's own
   framing. Investigated whether to revise the rule or retroactively invalidate both
   authorizations; chose **revision**, not invalidation, because in both cases the trigger was a
   precondition check finding a predecessor still `Current`, the session stopped and reported the
   conflict rather than proceeding silently, and the Human Owner then gave one written directive
   explicitly resolving *both* actions ("close out DASH-001 first, then proceed with AUTO-001";
   the AUTO-002 equivalent) — an explicit, distinct human decision for the successor, not an
   automatic consequence of the closeout. That is exactly the safety property rule 16 protects
   (no *automatic*/agent-initiated chaining); only the literal "same session" wording was
   violated, not the substance. Rule 16 now states this distinction explicitly. Invalidating two
   already-merged, Human-Owner-directed authorizations to satisfy a literal wording gap would have
   been disproportionate and itself a worse governance outcome (unwinding real, deliberate human
   decisions to fix an editorial ambiguity).
2. **Registry audit found DASH's own stage registry was stale and had drifted from AUTO's**
   (`docs/agentos-dashboard/STAGE_REGISTRY.md`): its §3 table still showed DASH-001 `IN_PROGRESS`,
   though it has been `Done`/merged (PR #1, `5f82996`) since 2026-07-23 — this registry was never
   updated at that closeout, a real, previously-undiscovered staleness bug, confirmed against
   `docs/TASK_QUEUE.md`/`docs/PROJECT_STATE.md` (both correctly say `Done`). Fixed: state
   corrected to `COMPLETE`; the same BLOCKED-mapping, clean-tree, rule-8, and same-session
   clarifications made to AUTO's registry were mirrored into DASH's (new rules 18–19, referencing
   AUTO's fuller versions to avoid two independently-editable copies of shared mechanisms
   drifting). `docs/agentos-dashboard/CHANGELOG.md` was also found stale (both entries still say
   "pending Human Owner acceptance at DASH-001 completion" though it completed 2026-07-23); a new
   entry was appended (its own convention: "Entries are appended, never edited") rather than
   editing the stale ones. `docs/implementation/orchestration/migration-registry.yaml` was
   checked and found out of scope: frozen historical evidence from the pre-GOV-1 ORCH-00x program,
   explicitly forbidden to modify by the SSP, not a live registry expected to track current
   `docs/TASK_QUEUE.md` state.
3. **Runtime lifecycle documents disagreed on failure transitions.** Cross-checked
   `MACHINE_GATES.md` against `WORKFLOW_STATES.md` §3's Allowed Transitions table directly (not by
   assertion) and found three real gaps: `MACHINE_GATES.md` §2 documents the Precondition Gate
   failing from `AUTHORIZED` or `PRECONDITIONS_CHECKED` to `FAILED`, and §5/§8 document the Merge
   Safety Gate failing from `PR_OPEN` to `FAILED` — none of these three transitions appeared in
   `WORKFLOW_STATES.md` §3 at all (not merely mis-worded; absent). Added all three
   (`AUTHORIZED → FAILED`, `PRECONDITIONS_CHECKED → FAILED`, `PR_OPEN → FAILED`) to
   `WORKFLOW_STATES.md` §3 (→ 1.2), each citing the `MACHINE_GATES.md` section that requires it.
   Every other gate's failure transition (`VALIDATING`, `QA_RUNNING`, `WAITING_FOR_CHECKS`,
   `CLOSING`) was already present and cross-checked as consistent.
4. **Rule 1's "clean tree" definition (added in the fourth pass) was itself incomplete** — it
   said "`docs/TASK_QUEUE.md` and its mirrors, `docs/DECISION_LOG.md`, and `docs/CHANGELOG.md`"
   without naming this registry's own §4/§5 (which the same transition also modifies — the
   AUTO-001→AUTO-002 entry itself says so: "`STAGE_REGISTRY.md` §4/§5 was updated only with the
   required status reference") or the program-level changelog (which the historical transition
   *should* have updated but didn't — a gap this recovery's third pass already fixed
   retroactively). Rewrote rule 1 with a complete, itemized list of every artifact, and an
   explicit list of what is *not* included (`handover/**`, the predecessor's own completion
   report) and why.

Verified after all edits: `workflowctl verify` — `task-state`/`governance`/`handover` PASS,
`git` FAILs only on the same pre-existing `upstream_missing`. Exactly one `Current` task
(AUTO-002, `BLOCKED`, unchanged). No lifecycle transition changed; no AUTO-002 implementation
performed; no commit, push, PR, or merge.

**Alternatives considered:** (a) For rule 16, invalidating and re-issuing both historical
authorizations — rejected per the reasoning above: the evidence shows deliberate, explicit human
decisions, not silent chaining; invalidating them would discard real approvals to fix wording.
(b) For the DASH registry, leaving it un-mirrored since Finding 2 named it as a target but the
active work is on the AUTO program — rejected: the mission explicitly required auditing every
registry, and the staleness (DASH-001 `IN_PROGRESS`) was a genuine, independent defect, not
housekeeping that could wait. (c) For the runtime transitions, assuming `MACHINE_GATES.md`'s
prose was merely informal and `WORKFLOW_STATES.md`'s table was the sole source of truth needing
no change — rejected: `MACHINE_GATES.md` §8's own Gate Summary Table is exactly as normative as
`WORKFLOW_STATES.md` §3, and an omission in either is a real inconsistency, not a stylistic
choice.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`. Finding 1 in particular required judging
whether a genuine violation should be fixed by changing the rule or by undoing history; the
evidence-based conclusion is that this repository's actual practice (stop, report the conflict,
obtain one explicit directive covering both actions) already satisfied the safety property the
rule exists to protect, so the rule — not the two historical decisions — was corrected.

## 2026-07-24 — Governance recovery, fourth pass: "clean tree" redefined, the BLOCKED/SSP deadlock resolved, and rule 8 rewritten to distinguish frozen records from living documents

**Decision:** A further independent audit (Codex) found three more substantive governance defects
— not citation errors this time, but genuine rule-design flaws — all repaired in
`docs/workflow-automation/STAGE_REGISTRY.md` (bumped 2.1 → 3.0, a MAJOR control-rule change per
its own §8):

1. **Rule 1's "clean tree" was literally impossible to satisfy.** Verified against repository
   evidence: recording "predecessor `COMPLETE`, successor `Current`" in `docs/TASK_QUEUE.md` and
   its mirrors is itself the edit that authorizes a stage — the tree cannot be byte-clean at the
   exact instant of authorization, because that edit is sitting uncommitted at that instant by
   construction. Confirmed independently via `git status` at every point in this recovery: the
   dirty set has only ever contained the sanctioned governance-mirror closeout files (never
   `src/`, `tests/`, or unrelated documents). Codex was correct that the literal wording was
   impossible; incorrect (unevidenced) would be any claim that this invalidates either the
   AUTO-001 or AUTO-002 authorization, since no foreign drift was ever present. Fixed by
   redefining "clean tree" in rule 1: no uncommitted change *other than* the sanctioned
   closeout/enrollment edit itself, which is the trigger, not a violation.
2. **The registry's own `BLOCKED → IN_PROGRESS` transition (added in an earlier pass, rule 17)
   deadlocked against the SSP**, which gates implementation on registry status literally reading
   `AUTHORIZED` — a stage leaving `BLOCKED` straight for `IN_PROGRESS` would never pass that
   textual check. This was introduced by this recovery's own second pass and is a genuine defect,
   not a pre-existing one. Resolved by choosing `BLOCKED → AUTHORIZED → IN_PROGRESS`: unblocking
   always returns a stage to `AUTHORIZED` first (no re-authorization act), so the SSP's existing
   "status is `AUTHORIZED`" check keeps working unmodified. `STAGE_REGISTRY.md` §2/§3 rule 17 and
   the SSP (`stage-prompts/README.md`, → 1.2) now state this identically.
3. **Rule 8 ("never amend a completed stage in place") contradicted this recovery's own actions**,
   which repeatedly edited `docs/workflow-automation/` documents that AUTO-001 (`COMPLETE`)
   delivered. Resolved by distinguishing, in rule 8 itself, two different things it was
   conflating: **completion records** (Registry §4 state/branch facts, §5 rows, stage reports,
   `docs/DECISION_LOG.md` entries) — frozen, corrected only via a Governance Correction Record
   (new rule 18), never in place; versus **versioned reference/control documents** a stage
   happened to deliver (this registry, `HUMAN_AUTHORIZATION_MODEL.md`, `WORKFLOW_STATES.md`, the
   SSP, `stage-prompts/*.md`, `OPEN_QUESTIONS.md`) — each already carries its own `Version` field
   (and, where present, a `Future Revisions` clause) precisely because they are living documents;
   amending their content in place, with a version bump and a logged rationale, is normal
   maintenance and was never a rule-8 violation. Substantive re-litigation of a completed stage's
   actual decisions remains out of bounds for in-place editing either way.

New rule 18 (Governance Correction Record) formalizes the correction mechanism these three fixes
and Finding 4 (next entry) all rely on. Verified after all edits: `workflowctl verify --config
self-governance.yaml` — `task-state`/`governance`/`handover` PASS, `git` still FAILs only on the
same pre-existing `upstream_missing` condition. Exactly one `Current` task (AUTO-002, state
`BLOCKED`, unchanged). No lifecycle transition changed; no AUTO-002 implementation performed.

**Alternatives considered:** (a) For "clean tree," declaring the AUTO-001/AUTO-002 authorizations
retroactively invalid and requiring fresh ones — rejected: the evidence shows no foreign drift was
ever present, only the sanctioned closeout edit; invalidating a correctly-conducted authorization
because a rule's *wording* was ambiguous would penalize correct behavior for an editorial gap. (b)
For the `BLOCKED` deadlock, changing the SSP to also accept status `BLOCKED` directly (skipping
back through `AUTHORIZED`) — rejected: it would require the SSP to carry special-cased logic for
resuming from `BLOCKED`, whereas routing back through `AUTHORIZED` first keeps the SSP's existing
single invariant true unmodified. (c) For rule 8, requiring every documentation clarity fix to go
through a brand-new authorized linked task — rejected as disproportionate for citation/clarity
fixes on living reference documents, and inconsistent with those documents' own explicit
versioning/revision-policy fields, which already anticipate this maintenance mode.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`. These three findings are rule-design flaws,
two of them (BLOCKED deadlock, rule-8 conflict) introduced by this recovery's own earlier passes —
acknowledged as such rather than attributed solely to the original governance.

## 2026-07-24 — Governance Correction Record: this log's own append-only rule was violated twice by the two prior recovery passes, before it was made explicit

**Decision:** An independent audit (Codex) found that this log — despite `docs/AGENT_PROTOCOL.md`
treating it as *the* audit trail for governance changes — had never explicitly stated it was
append-only, and, in that gap, two prior governance-recovery passes today edited existing entries
in place rather than appending: (1) the second pass rewrote parts of the "AUTO-001 closed out to
Done; AUTO-002 authorized but halted on a branch-binding mismatch" entry (removing its
`HUMAN_AUTHORIZATION_MODEL.md` citation) instead of leaving it untouched and appending a
correction; (2) the second pass also replaced the first pass's "Governance recovery: corrected a
mis-cited authority..." entry wholesale with a new "Governance recovery, completed: ..." entry,
rather than leaving the first pass's entry in place and appending. Both are real, confirmed
violations of the append-only principle this log now states explicitly — not a citation error
like the earlier findings, a process error in how this recovery itself was conducted.

This entry does **not** attempt to mechanically reconstruct and replay the exact prior byte
history: the entries that replaced the originals are themselves now real, dated facts about what
happened in this recovery, and unwinding them would mean deleting or rewriting *those*, compounding
the violation rather than fixing it. Full byte-exact reconstruction was performed only where it
was cheap and mechanical and the append-only promise had been explicit from the start — see
`docs/workflow-automation/STAGE_REGISTRY.md` §5, where both original AUTO-002 authorization-log
rows have been restored verbatim and a proper new correction row appended instead. For this log,
the corrective action is: declare append-only status explicitly (done, above), disclose the two
violations precisely (above), and commit that every entry from this one forward — including this
one — is append-only in fact, not just in name. No entry below this one has been altered by this
correction.

**Alternatives considered:** (a) Silently continuing to treat this log as we always effectively
had (no explicit rule, informal append-only-by-convention) — rejected: this is exactly the
ambiguity Codex flagged, and `docs/AGENT_PROTOCOL.md` requires governance rules to be explicit,
not assumed. (b) Attempting a full archaeological restoration of every edited entry, then
re-appending corrections on top — rejected as explained above: for prose entries (unlike
`STAGE_REGISTRY.md` §5's two-row table) this produces a nested, harder-to-read mess without adding
real audit value beyond a clear disclosure, and it would require discarding real facts about what
this recovery actually did in its second pass. (c) Doing nothing since no rule technically
existed to violate at the time — rejected: `docs/AGENT_PROTOCOL.md`'s spirit (governance changes
must be traceable) was violated regardless of whether this file had said "append-only" in so many
words; disclosure and going forward compliance is the correct remedy, per this recovery's
standing instruction to fix governance rather than defend prior decisions.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`'s requirement that governance changes be
logged with their rationale, and because Finding 4 of this recovery's audit specifically named
this log's append-only ambiguity as unresolved. This entry closes that ambiguity going forward and
is honest about the two violations rather than concealing them.

## 2026-07-24 — Governance recovery, third pass: OD-3/OD-4 disambiguated, rule 16 clarified, BLOCKED lifecycle completed, stale mirrors and handover corrected

**Decision:** A further audit backlog (framed as independent-review findings) identified six more
governance gaps beyond the two prior passes, all repaired without changing any lifecycle state or
starting AUTO-002 work:

1. **OD-3/OD-4 blocking ambiguity.** `OPEN_QUESTIONS.md` used "blocks AUTO-002" loosely for two
   different relationships: a hard `STAGE_REGISTRY.md` §3 rule 1 authorization gate, versus a
   question the implementer must resolve before `COMPLETE` (rule 12). Since AUTO-002 was in fact
   authorized while OD-3 and OD-4 were (and remain) `Open`, and `stage-prompts/AUTO-002.md`
   explicitly assigns OD-3 to AUTO-002's own implementation, neither was ever a rule-1 gate. Added
   an explicit definition of the two relationships to `OPEN_QUESTIONS.md`'s Format section and
   reworded both entries' Dispositions accordingly. No new blocking behavior invented — this
   documents what the entries' own history already showed.
2. **Rule 16 (closeout) silence on `workflowctl verify` tolerance.** The rule required
   post-merge `verify` to run but did not say whether a `git`-check finding (e.g.
   `upstream_missing`) could ever be tolerated at closeout, unlike the SSP's mid-stage runs which
   already say to identify pre-existing failures as such. Clarified: `task-state`/`governance`/
   `handover` must PASS with no exception at closeout; `git` must PASS unless its only finding is
   pre-existing and unrelated to the stage's own merge — never for a finding the merge itself
   caused. This does not currently gate anything (AUTO-002 is nowhere near closeout).
3. **`BLOCKED` lifecycle incomplete.** §2/§3 established `BLOCKED` as a state and rule 17
   established how it is entered, but never stated its legal exits. Added: `BLOCKED` is reached
   only from `AUTHORIZED`, and exits only to `IN_PROGRESS` (precondition resolved, resuming rule
   4's "Starting" step, no re-authorization) or `SUPERSEDED` (Human Owner directive, rule 9) —
   never to `NOT_STARTED`/`PROPOSED`. §2's state-model prose, rule 17, and the SSP now all state
   this the same way.
4. **`docs/remaining_tasks.md`** still carried the retired "authorization-binding branch
   mismatch" phrase this recovery's first pass had already corrected everywhere else. Reworded to
   "execution-precondition branch mismatch... registry state `BLOCKED`."
5. **`docs/PROJECT_STATE.md`** contradicted itself: its "In progress" section said AUTO-002 is
   `BLOCKED`, but its "Blockers" section said "None currently" and then described stale Git
   history — "`main` is one commit ahead of `origin/main` and nothing has been pushed," which as
   of the DASH-001/AUTO-001 PR merges is false (`main`/`origin/main` are identical at `191f600`,
   0 ahead/0 behind; verified via `git rev-list --left-right --count origin/main...main`).
   Rewrote "Blockers" to state the real current blocker (AUTO-002 `BLOCKED`) and the real Git
   state (main/origin/main in sync; the only unpushed ref is the session's own working branch).
6. **`handover/PROJECT_HANDOVER.md`** was dated 2026-07-18 and described a since-superseded world
   (no task-tracked work remaining, an uncommitted 1.0.0 working tree, `main` one commit ahead of
   `origin/main`) — checksum-valid against `handover/PROJECT_CHECKSUM.md` but factually stale, per
   that file's own warning that a checksum match only proves byte-identity, not continued truth.
   Rewrote it in full to describe the current state (DASH-001/AUTO-001 `Done` and pushed, AUTO-002
   `Current`/`BLOCKED`, this recovery's corrections, and the real Git history), then regenerated
   `handover/PROJECT_CHECKSUM.md`'s size/digest/date for the new content (`workflowctl
   check-handover` re-verified PASS).

Also synchronized `docs/workflow-automation/CHANGELOG.md`, which still read as though AUTO-001
were in progress and AUTO-002 did not exist; added `Changed` entries mirroring AUTO-001's closeout,
AUTO-002's authorization/`BLOCKED` state, and this pass's document revisions, without deleting the
original (still-true) `Added` entry.

Verified after all edits: `workflowctl verify --config self-governance.yaml` — `task-state`,
`governance`, `handover` all PASS; `git` still FAILs only on the same pre-existing
`upstream_missing` condition (this session's own unpushed working branch), now correctly
described rather than contradicted in `PROJECT_STATE.md`. Exactly one `Current` task (AUTO-002).
No lifecycle transition changed; no AUTO-002 implementation performed; no commit, push, PR, or
merge.

**Alternatives considered:** (a) Leaving OD-3/OD-4's wording as-is since no rule ever literally
said "authorization gate" — rejected: the ambiguity is exactly what a reviewer flagged, and rule
1's "blocking OD-# resolved" language invites the misreading that any "blocks AUTO-002" line is
such a gate. (b) Deleting the stale `docs/workflow-automation/CHANGELOG.md` `Added` entry instead
of adding beside it — rejected: it is a true historical fact (those files were added on
2026-07-23); only its incompleteness, not its content, was the defect. (c) Treating the handover
checksum's PASS as sufficient evidence the file was fine — rejected per the file's own stated
purpose: checksum validity proves byte-identity to a prior snapshot, never continued factual
accuracy.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`'s requirement that governance changes be
logged with their rationale. This entry documents the third and (at time of writing) final
governance-recovery pass; the first two are recorded in the entries directly below.

## 2026-07-24 — Governance recovery, completed: corrected the mis-cited authority, the non-canonical registry state, and made the authorization/execution-precondition boundary explicit

**Decision:** An independent governance audit of the AUTO-001 post-merge state (the closeout
recorded in the entry directly below) found, and this two-pass recovery repaired, three related
defects — none of which changed any lifecycle state or started AUTO-002 work:

1. **Mis-cited authority.** The entry below, and its mirrors in `docs/current_task.md`,
   `docs/TASK_QUEUE.md`, `docs/PROJECT_STATE.md`, `docs/CHANGELOG.md`, and
   `docs/workflow-automation/STAGE_REGISTRY.md` §5, grounded the AUTO-002 branch mismatch in
   `docs/workflow-automation/HUMAN_AUTHORIZATION_MODEL.md` §2 field 8 / §4, treating it as an
   "authorization-binding invalidation." That document's own Dependencies field and
   `docs/workflow-automation/WORKFLOW_STATES.md` §1 state that it governs the **runtime workflow
   engine's** future authorization of workflows against **target repositories** — a system that
   does not exist as code yet (AUTO-001 was documentation-only) — not this repository's own
   AUTO-00x development-stage lifecycle, which is governed instead by `docs/workflow-automation/
   STAGE_REGISTRY.md` §3 and the Standard Stage Protocol (`docs/workflow-automation/
   stage-prompts/README.md`). Under the correct authority (the SSP's named-branch precondition
   and `STAGE_REGISTRY.md` §3 rule 14), the branch mismatch is an ordinary execution-precondition
   failure, not an event that calls the Human Owner's "I authorize AUTO-002." authorization
   itself into question. The practical outcome is unchanged — no AUTO-002 implementation may
   begin on the current branch, and resolution is still a Human Owner decision — only the stated
   reason was wrong. Every mirror, including the `STAGE_REGISTRY.md` §5 log row itself, has been
   corrected in place so no document retains the incorrect claim; the log row's own text now
   discloses that it was corrected and why, rather than leaving a second, contradicting row
   beside it.
2. **Non-canonical registry state.** `STAGE_REGISTRY.md` §4 recorded AUTO-002's state as
   `AUTHORIZED (blocked — branch-binding mismatch, see §5)` — a composite string that is not one
   of the canonical states in §2 (`NOT_STARTED`/`PROPOSED`/`AUTHORIZED`/`IN_PROGRESS`/
   `SELF_REVIEW`/`REVIEW`/`APPROVAL`/`COMPLETE`/`BLOCKED`/`SUPERSEDED`). Corrected to the
   canonical `BLOCKED`.
3. **Implicit rather than explicit governance boundary.** The scope boundary above was
   previously derivable only by cross-reading three documents' Dependencies/Naming-Note fields.
   Made explicit instead: `STAGE_REGISTRY.md` §1 now states in prose that it and the SSP are the
   exclusive authority for the AUTO-00x lifecycle, that `WORKFLOW_STATES.md`/
   `HUMAN_AUTHORIZATION_MODEL.md` govern only the runtime engine, and that authorization
   preconditions and execution preconditions are separate concepts; a new §3 rule 17 states
   plainly that a failed execution precondition moves a stage to `BLOCKED` (never invalidates
   authorization, never by itself requires re-authorization); §2's `Current`/`Planned`/`Done`
   mapping now names `BLOCKED` explicitly (≈ `Current`) instead of leaving it unmapped.
   `HUMAN_AUTHORIZATION_MODEL.md` §1 and `WORKFLOW_STATES.md` §1 each gained one added sentence
   stating the same boundary from their side; the SSP gained one sentence stating the
   `BLOCKED`/no-invalidation consequence at the point it checks the branch precondition;
   `stage-prompts/AUTO-002.md` now separates its "Preconditions" line into an authorization half
   and an execution half instead of one undifferentiated list.

Verified after the edits: `workflowctl check-task-state --config self-governance.yaml` and
`workflowctl check-governance --config self-governance.yaml` both PASS; exactly one `Current`
task (AUTO-002); AUTO-001 remains `Done`/`COMPLETE` everywhere. No lifecycle transition was
changed by this recovery: AUTO-001 is still `Done`/`COMPLETE`, AUTO-002 is still `Current` in
`docs/TASK_QUEUE.md` (registry state `BLOCKED`), and AUTO-002 implementation still has not
started. `workflowctl check-git` continues to `FAIL` on a pre-existing, unrelated condition — the
branch has no upstream configured (`require_upstream: true`). No commit, push, PR, merge, branch
rename, or AUTO-002 runtime change was performed.

**Alternatives considered:** (a) Leaving the mis-citation in place since the practical outcome
(stop and wait for a Human Owner decision) happened to be correct anyway — rejected: a governance
document that cites the wrong authority for a safety-relevant claim misleads the next session
that reads it literally, and `docs/AGENT_PROTOCOL.md` requires governance changes to be logged
with rationale. (b) Preserving `STAGE_REGISTRY.md` §5's original row byte-for-byte and only
appending a separate correcting row (the first pass's approach, out of deference to §8's
"append-only" framing for that log) — superseded in this second pass on the operator's explicit
instruction to leave no conflicting historical guidance anywhere in the live governance surface;
the row's own text still discloses that a correction was made and why, which preserves audit
value without leaving two rows that assert opposite things. (c) Introducing a new state token
(e.g. `AUTHORIZED_BLOCKED`) instead of reusing `BLOCKED` — rejected: only canonical registry
state values are used. (d) Treating the scope boundary as adequately covered by the pre-existing
Dependencies fields and leaving it implicit — rejected on the operator's explicit instruction
that the governance should state it outright rather than require cross-reading three documents.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`'s requirement that governance changes be
logged with their rationale. This entry documents a documentation-correctness repair and a
clarity amendment identified by independent audit, distinct from the substantive AUTO-001/
AUTO-002 governance decision it corrects (recorded directly below, with its own erroneous
citations corrected in place for the same reason).

## 2026-07-24 — AUTO-001 closed out to Done; AUTO-002 authorized but halted on a branch-binding mismatch

**Decision:** Before beginning AUTO-002, the Human Owner authorized the required governance
closeout: AUTO-001 (merged into `main` via PR #3, commit `191f600`) was flipped from `Current`
to `Done` in `docs/TASK_QUEUE.md`, `docs/current_task.md`, `docs/remaining_tasks.md`, and
`docs/PROJECT_STATE.md` (prose only), and AUTO-002 was enrolled as the sole `Current` task,
authorized in the same session ("I authorize AUTO-002."). `workflowctl check-task-state
--config self-governance.yaml` and `workflowctl check-governance --config self-governance.yaml`
were re-run after the edit and both PASS.

With governance state consistent, AUTO-002's own preconditions (`docs/workflow-automation/
STAGE_REGISTRY.md` §3 rule 1; Standard Stage Protocol,
`docs/workflow-automation/stage-prompts/README.md`) were re-checked. Every authorization
precondition passed; one execution precondition did not: the session's actual working branch is
`feature/auto-002-orchestrator-foundation`, but the canonical stage contract
(`docs/workflow-automation/stage-prompts/AUTO-002.md`) and the stage registry
(`docs/workflow-automation/STAGE_REGISTRY.md` §4) both bind AUTO-002 to
`feature/auto-002-orchestrator-state-machine`. The Standard Stage Protocol requires verifying
"you are on the stage's named branch created from a clean baseline" before any implementation
begins (`docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 14). *[Editorial correction, same
day, during final governance cleanup: this paragraph originally also cited "Planned stage branch
name" as authorization-binding field 8 of `docs/workflow-automation/HUMAN_AUTHORIZATION_MODEL.md`
§2 and its §4 as "an explicit invalidation condition" for this mismatch. That citation was
incorrect — `HUMAN_AUTHORIZATION_MODEL.md` governs only the runtime engine's future authorization
of workflows against target repositories (`WORKFLOW_STATES.md` §1), never this repository's own
AUTO-00x stages — and has been removed rather than left as conflicting historical guidance; see
the entry above.]*

Per the SSP and the Human Owner's own explicit instruction ("If any precondition still fails
after the authorized closeout: stop, make no AUTO-002 runtime implementation changes, report the
exact failed precondition"), AUTO-002 implementation was **not started**. AUTO-002 remains the
sole `Current` task (registry state `BLOCKED` per `docs/workflow-automation/STAGE_REGISTRY.md`
§2/§3 rule 17 — authorization intact, execution precondition unmet) pending a Human Owner
decision: rename the working branch to the canonical `feature/auto-002-orchestrator-state-machine`,
or formally amend the canonical branch binding (a new entry in `docs/workflow-automation/
OPEN_QUESTIONS.md` plus a `docs/workflow-automation/STAGE_REGISTRY.md` update) to bind
`feature/auto-002-orchestrator-foundation` instead. `docs/workflow-automation/STAGE_REGISTRY.md`
§4/§5 was updated only with the required status reference (AUTO-001 row → `COMPLETE`; AUTO-002
row → `BLOCKED`; authorization log appended) — no architecture content in that document set was
altered.

**Alternatives considered:** (a) Renaming the local branch to the canonical name and proceeding
— rejected: unilaterally resolving a detected branch-precondition mismatch without a Human Owner
decision bypasses the Human Owner's own stated instruction to stop and report, even though the
fix is mechanically trivial. (b) Editing the canonical contract and registry to match the actual
branch — rejected for the same reason: the canonical branch value is a stage-contract fact, not
documentation drift to be silently corrected. (c) Proceeding with AUTO-002 implementation on the
actual branch, treating the contract's branch field as non-binding — rejected: the stage
contract and the SSP both make this a hard execution precondition, not an advisory note.

**Rationale:** Recorded here because `docs/AGENT_PROTOCOL.md` requires governance changes to be
logged with their rationale, and because this decision documents both an authorized governance
transition and a precondition-check outcome that a future session (or the Human Owner) needs to
understand without replaying this session. No commit, push, PR, merge, or branch deletion was
performed.

## 2026-07-23 — DASH-001 closed out; AgentOS Workflow Automation program (AUTO) enrolled with AUTO-001 current

**Decision:** Before starting AUTO-001, the AUTO-001 stage prompt's own precondition check
("no conflicting task is active") found that DASH-001 was still recorded `Status: Current` in
`docs/TASK_QUEUE.md` and its mirrors, even though its PR (#1, `5f82996`) had already merged into
`main` — the formal flip-to-`Done` closeout step had not yet run. `self-governance.yaml` sets
`workflow.maximum_current_tasks: 1`, enforced by `workflowctl check-task-state`, so starting a
second `Current` task would have broken that invariant. Presented with the conflict, the Human
Owner chose "close out DASH-001 first, then proceed with AUTO-001." DASH-001 was flipped to
`Done` in `docs/TASK_QUEUE.md`, `docs/current_task.md`, `docs/remaining_tasks.md`, and
`docs/PROJECT_STATE.md` (prose only; the `Current Version:` fact line untouched), and the new
**AgentOS Workflow Automation program** (AUTO-001..AUTO-007, entry point
`docs/workflow-automation/README.md`) was enrolled in the same edit: AUTO-001 as the sole
`Current` task and AUTO-002..AUTO-007 as `Planned`, mirroring exactly how the DASH program was
enrolled at DASH-001. `workflowctl check-task-state --config self-governance.yaml` re-run after
the edit to confirm exactly 1 `Current` task.

**Alternatives considered:** (a) Leaving DASH-001 marked `Current` and treating AUTO-001 as
exempt from `docs/TASK_QUEUE.md` tracking, since AUTO-001's own file scope
(`docs/workflow-automation/`) never overlaps DASH-001's — rejected: this repository's
`maximum_current_tasks: 1` rule is a whole-repository invariant, not a per-program one (DASH-001's
own stage prompt encoded the same precondition: "no other `Current` task anywhere in
`docs/TASK_QUEUE.md`"), and a program-private state file (the option taken for the read-only
`docs/implementation/orchestration/` ORCH package) was rejected for DASH-001 on the grounds that
"DASH stages are ordinary tasks and belong under the existing `check-task-state` discipline" —
the same reasoning applies to AUTO. (b) Stopping entirely and asking the Human Owner to close out
DASH-001 in a separate session first — rejected as the Human Owner's explicit choice, given they
authorized the closeout in the same turn as being asked. (c) Leaving AUTO-002..AUTO-007
unenrolled (only adding AUTO-001) since the AUTO-001 authorization text did not explicitly
request `TASK_QUEUE.md` changes — rejected for internal consistency: the DASH precedent enrolls a
program's full known roadmap as `Planned` at its first authorized stage, and AUTO-001's own
required deliverables already define all seven stages' scope in
`docs/workflow-automation/stage-prompts/`.

**Rationale:** Recorded here because `docs/AGENT_PROTOCOL.md` requires governance changes to be
logged with their rationale, and because promotion of AUTO-001 to `Current` needs the recorded
owner approval (`self-governance.yaml` `require_designer_approval_for_promotion`). The Human
Owner's 2026-07-23 authorization ("I authorize AUTO-001.") plus the explicit "close out DASH-001
first" choice made when presented with the conflict are that approval for both actions. This
entry, and the `docs/TASK_QUEUE.md`/mirror edits it describes, are governance/task-state changes
required by repository governance to satisfy AUTO-001's own preconditions — not part of
AUTO-001's documentation deliverable set, which remains scoped to `docs/workflow-automation/`.
No commit, push, PR, merge, or branch deletion was performed for either the closeout or the
AUTO-001 work.

## 2026-07-23 — AgentOS Dashboard program enrolled; DASH-001 recovered from a mis-targeted execution

**Decision:** Adopt the ten-stage AgentOS Dashboard program (DASH-001..DASH-010) as post-1.0
work, enrolled in `docs/TASK_QUEUE.md` with DASH-001 as the sole `Current` task, and complete
DASH-001 by **recovery**: the first execution was mistakenly performed in a different
repository (`amozesh_konkur`), and its documentation output — copied here as untracked
candidate material — was rewritten in place so every assumption matches this repository's
actual governance (authority chain per `docs/AGENT_PROTOCOL.md` + `self-governance.yaml`;
Current/Planned/Done task lifecycle with `workflowctl` mirror checks; branches from `main`;
handover pair verified by `workflowctl check-handover`; upstream check instead of a baseline
tag; this single decision log; the orchestration package treated as read-only observed state).
The program is documentation-first, and the dashboard itself will be a separate top-level
package (`agentos_dashboard/`) with read-only repository access — it never gains commit, push,
or governance-mutation authority.

**Alternatives considered:** (a) Discarding the copied material and re-planning from scratch —
rejected as wasteful: the product/security/test design is repository-agnostic and sound; only
its governance bindings were wrong. (b) Keeping the copied files verbatim and reconciling later
— rejected: they cited nonexistent files (`CONSTITUTION.md`, `governance/`, root `AGENTS.md`,
`scripts/create_handover.py`), a nonexistent base branch (`recovery/project-baseline`), a
nonexistent baseline tag, foreign decision IDs (CTO-xxx/D-xxx/ISS-xxx), and a false "zero new
dependencies (FastAPI)" claim, so leaving them in place would have created a second, false
authority. (c) Enrolling the DASH stages outside `docs/TASK_QUEUE.md` in a program-private
state file, like the ORCH package — rejected: unlike ORCH (a reviewed design package with its
own session protocol), DASH stages are ordinary tasks and belong under the existing
`check-task-state` discipline.

**Rationale:** Recorded here because `docs/AGENT_PROTOCOL.md` requires governance changes to be
logged with their rationale, and because promotion of DASH-001 to `Current` needs the recorded
owner approval (`self-governance.yaml` `require_designer_approval_for_promotion`). The Human
Owner's 2026-07-23 recovery directive ("I authorize recovery and correct execution of DASH-001
in the ai-workflow-engine repository") is that approval. The known dependency gap (this
repository pins no web framework) is deliberately not decided here; it is held open as OD-D9 in
`docs/agentos-dashboard/OPEN_QUESTIONS.md` and blocks DASH-004, not DASH-001..003. Full
correction inventory: `docs/agentos-dashboard/DECISIONS.md` DD-03 and
`docs/reports/agentos-dashboard/DASH-001-recovery-report.md`.

## 2026-07-18 — `state` CLI emits a deterministic bespoke payload, not a timestamped CheckResult (T-302)

**Decision:** `workflowctl state show|next|record` success output is a purpose-built canonical-JSON
object (`{status, command, ...}`) written Rich-free to stdout, rather than a `CheckResult` routed
through `render_json`. Failures carry `{status: "FAIL", command, finding: {code, message}}` and
exit 1; success exits 0; usage/unexpected errors exit 2 via `_protected`.

**Alternatives considered:** Emitting a `CheckResult(check_name="state", ...)` exactly as
`docs/milestone-3-plan.md` loosely worded it ("CheckResult-style PASS"). Rejected because
`CheckResult` carries a wall-clock `timestamp`, which would make identical state queries produce
different bytes — at odds with this project's determinism principle and with the timestamp-free
canonical outputs used everywhere else in the workflow layer. `show`/`next` are also queries, not
pass/fail checks, so the `CheckResult` shape fits them poorly.

**Rationale:** The Milestone 2 prompt CLI set the precedent of a bespoke success payload
(`PromptSuccess`) with `CheckResult` reserved for validation *failures*; the state CLI follows the
same pattern. Recorded here because it is a conscious, reviewer-flagged (T-302 review, finding N1)
deviation from the plan's literal wording, kept for a determinism reason rather than an oversight.
`docs/current_task.md`'s T-302 acceptance criteria describe the CLI contract without `check_name`,
consistent with this decision.

## 2026-07-18 — Milestone 4 writer is typed-methods-only; push gate reads live, not recorded (T-401)

**Decision:** In the `docs/milestone-4-plan.md` contracts, (a) the writable-Git surface
`GitWriter` exposes only typed methods (`stage_paths`, `unstage_paths`, `commit`, `push`,
`apply_check`, `apply_patch`), each emitting one fixed argv template — there is no method that
runs a caller-supplied argv, so dangerous forms (force push, remote-branch deletion, `reset`,
`commit --amend`/`-a`, `add -A`) are structurally unreachable rather than blocked by a denylist;
and (b) the push gate reads live Git state and decides on `behind == 0` computed by the exact
Milestone 2 `rev-list --left-right --count @{upstream}...HEAD` command, without carrying
recorded ahead/behind counts in the `PushApproval`.

**Alternatives considered (all from round-1 plan-review findings):** an allowlist that runs
arbitrary argv and scans it for denylisted tokens (rejected — B2/B3: it both false-rejects
operand data like a commit message containing "reset" and misses real dangers like
`push --delete`); carrying recorded ahead/behind in the approval to mirror M-2's cross-check
(rejected — B5: M-2 needed that only because its prompt was a snapshot that could drift from
execution; the M-4 gate reads live state, so the live computation is itself authoritative).

**Rationale:** An independent round-1 plan review REJECTED the first draft with five blocking
findings; the typed-writer redesign resolves three of them (B1 self-contradictory unstage,
B2 operand-scanning, B3 non-airtight allowlist) at once and is a stronger safety posture for the
project's first writable-Git milestone. The live-read push gate (B5) and the read-only `GitClient`
extension using already-allowlisted forms (B4) are the other two. Recorded here because these are
genuine safety-architecture choices, not typo fixes. Full history in `docs/milestone-4-plan.md`'s
status and disposition sections.

## 2026-07-18 — `AgentRunRecord` stores the agent's stdout bytes, not a re-parsed `AgentReport` (T-305)

**Decision:** The stored `AgentRunRecord` does not carry a structured `AgentReport` field. The
agent's report is preserved byte-exactly as `stdout_b64` under a committed `stdout_sha256`, and
its material claims (verdict, changed-path judgement) live in the `verification` snapshot's
`evidence`. The `docs/milestone-3-plan.md` "Run artifacts" wording listed "the full AgentReport"
as a member.

**Alternatives considered:** Adding a parsed `AgentReport` field alongside the raw stdout
(rejected — it duplicates data already recoverable from `stdout_b64`, and a separately-stored
parse could drift from the bytes that were actually digested, weakening tamper-evidence);
storing only the report and discarding raw stdout (rejected — then non-report stdout noise and
the exact bytes an operator saw would be lost, and a malformed-report run would have nothing to
store).

**Rationale:** Storing the exact bytes under a digest is strictly more tamper-evident than a
re-parsed copy, and it also covers the failure cases where there is no valid report at all
(`agent_report_invalid`, timeout). Downstream Milestone 4 consumes the verified verdict and
patch, both already present. Recorded per the T-305 review's non-blocking finding N3 so a future
session sees this as a conscious choice, not an omission.

## 2026-07-18 — Machine-readable CLI output must bypass Rich entirely (T-104)

**Decision:** All of `workflowctl`'s machine-readable stdout — every `--output json` payload and
the `version` string — is written as plain bytes via a `_write_stdout` helper, never through
Rich's `Console`.

**Alternatives considered:** Configuring the Rich `Console` with `no_color=True` /
`force_terminal=False` (rejected — `FORCE_COLOR` overrides those, and Rich still owns
soft-wrapping and other transforms); leaving it and documenting "unset FORCE_COLOR" (rejected —
a governance tool whose JSON is meant for CI consumption must not emit invalid JSON under a
common env var).

**Rationale:** Discovered during T-301's round-2 plan review: with `FORCE_COLOR` set, Rich
injected ANSI codes into `verify --output json`, producing unparseable JSON and violating the
stable 1.0 schema contract in `docs/architecture.md`. This is the same Rich-corruption class the
2026-07-17 `_protected` decision fixed for stderr; T-104 extends the same bytes-not-Rich
principle to the stdout machine paths that were missed. Human output and the Rich summary tables
are unchanged. Also hardens the `conda run ... pytest` verification path Milestone 3 re-executes.

## 2026-07-17 — Milestone 3 plan: two boundary decisions surfaced by round-1 plan review

**Decision:** In the `docs/milestone-3-plan.md` contracts, (a) Milestone 3 makes **no** change
to the target repository at all — a scoped-write agent's output is captured as a verified patch
artifact and applying it to the working tree is deferred to Milestone 4 (the earlier `agent
apply` verb was cut); and (b) `agent run` requires a **clean** target working tree at the
recorded HEAD before running, so the committed-HEAD sandbox faithfully reproduces the prompt's
working-tree-derived evidence.

**Alternatives considered:** Keeping `agent apply` in M-3 (rejected — it sat adjacent to
Milestone 4's controlled-change scope and added a third, un-allowlisted writable-Git surface on
the real repository); building the sandbox from the dirty working tree instead of committed HEAD
(rejected — it would make run inputs non-deterministic and diverge from the governance principle
that committed state is the source of truth).

**Rationale:** An independent round-1 plan review (fresh session, no memory of the drafting)
returned REJECTED with three blocking findings (missing `renderer.py` in the file list;
unspecified/non-deterministic verification-command re-execution; a task-ID slug collision hole)
and two substantive ones (sandbox-vs-dirty-tree tension; an unverifiable lossy-stderr digest).
All were remediated in a round-2 revision; the two items above were genuine scope/architecture
choices worth recording, not mere typo fixes. This is the same independent-review discipline
that caught a real regression in Milestone 2 (see the 2026-07-16 entry).

## 2026-07-17 — Master roadmap to 1.0 approved; local-commit and CI decisions

**Decision:** The human approved `docs/MASTER_ROADMAP.md` as written: Stage 0 (GOV-1 closeout,
documentation sync, plus a lightweight CI task the human opted into), then Milestone 3, then
Milestone 4, then the 1.0.0 release. The human additionally approved creating **one local git
commit** before Milestone 3 begins, to preserve the validated M-2 + GOV-1 working tree —
explicitly no push and no remote branch. Versioning follows Semantic Versioning; intermediate
versions are recommended by the engine's maintainer session at each milestone closeout
(suggested 0.2.0 after M-3, 0.3.0 after M-4).

**Alternatives considered:** Leaving the working tree uncommitted until 1.0 (rejected — largest
recoverability risk in the gap analysis); skipping CI (rejected by the human — a minimal
workflow improves reliability at negligible complexity).

**Rationale:** Recorded here because commit approval and roadmap approval are exactly the class
of human decisions `docs/AGENT_PROTOCOL.md` says must not be inferred from prior context by a
future session.

## 2026-07-17 — Self-governance: extend the existing engine rather than build a parallel system

**Decision:** Point this project's own tooling at its own repository (new governance documents
+ `self-governance.yaml` config), rather than building a second, differently-shaped governance
system under `docs/governance/` with new file names, a new task-lifecycle model, and new CLI
verbs.

**Alternatives considered:** A from-scratch system with an 8-file `docs/governance/` tree, a
7-state task lifecycle (`BACKLOG → PLANNED → APPROVED → IMPLEMENTING → VALIDATING → COMPLETED →
HANDED_OVER`) with timestamped/evidenced transitions, and new `governance status/validate/
handover/closeout` CLI commands running alongside the existing `check-*`/`verify`/`prompt`
surface.

**Rationale:** The existing `EngineConfig` schema, `governance`/`handover` validators, and
`prompt` module already cover nearly everything a from-scratch system would provide, under
different names, and had already been through two full milestone review cycles. Building a
parallel system would create two incompatible vocabularies describing the same repository
(`Current/Done/Planned` vs. a 7-state machine; `check-governance` vs. `governance validate`).
The genuinely new task-lifecycle/multi-agent-execution/push-gate capabilities the alternative
implied were already scoped as Milestones 3 and 4 in `docs/milestones.md` — pulling them forward
under new names would fork the roadmap rather than extend it. Full reasoning:
[`docs/GOVERNANCE_AUDIT.md`](GOVERNANCE_AUDIT.md).

## 2026-07-17 — `_protected` CLI error output bypasses Rich's `Console` entirely

**Decision:** `_protected()` in `src/ai_workflow_engine/cli.py` writes `ERROR: <message>\n`
directly to `sys.stderr` rather than through Rich's `Console.print`.

**Alternatives considered:** `Console.print(..., markup=False)` (insufficient — Rich's automatic
repr-highlighter still bolds bracketed substrings with ANSI codes even with markup parsing off);
`Console.print(..., markup=False, highlight=False)` (insufficient — Rich still soft-wraps text
to the console's line width, splicing a spurious newline into any message near or past ~80
columns, even when not attached to a TTY).

**Rationale:** Milestone 2's plan requires `_protected`'s stderr output to be the exact bytes
`ERROR: <message>` in every mode. Two independent fresh implementation-reviews each found one of
the above defects in turn; bypassing Rich's console formatting layer entirely was the only fix
that satisfied the byte-exact contract for arbitrary message content (brackets, tabs, length).
This also silently fixed the same latent defect for every pre-existing Milestone 1 command that
shares `_protected`.

## 2026-07-16 — Three-round independent fresh-review discipline for Milestone 2

**Decision:** After every remediation pass, dispatch a new reviewer with *no memory of the prior
session's fixes* rather than self-certifying that a fix resolved a prior review's findings.

**Rationale:** A reviewer that already knows "these four things were fixed" is anchored on that
frame and is structurally prone to missing anything new. Milestone 2 went through three such
rounds; round 2 caught a real regression-adjacent bug (the wrapping defect above) that round 1's
own fix had introduced by not going far enough. Self-certification would have missed it.

## Milestone 2 plan — Prompt generation is read-only and stateless

**Decision:** `ai_workflow_engine.prompt` renders, validates, and optionally stores a prompt for
an operator-specified stage. It does not persist workflow state, record verdicts, enforce stage
transitions, or compute the next stage automatically.

**Alternatives considered:** Coupling prompt rendering to a live workflow state machine tracking
which stage a task is "in."

**Rationale:** No state machine had been designed yet at the time Milestone 2 was scoped.
Building one implicitly, as a side effect of prompt generation, would have made Milestone 2's
correctness depend on an undesigned, untested state model. Deferred explicitly to Milestone 3;
see `docs/milestone-2-plan.md`.

## Milestone 2 plan — Prompt identity is a pinned, canonical, byte-exact hash

**Decision:** Every rendered prompt's identity (`prompt_id`) is the first 16 hex characters of
the SHA-256 of a canonical JSON serialization of its complete context (config, git status, task
snapshot, check evidence, template content/version/digest — everything). Canonical JSON uses
NFC-normalized, sorted-key, no-float, signed-64-bit-int-only serialization with a golden test
vector. All seven built-in templates are pinned to fixed byte counts and SHA-256 digests.

**Rationale:** Free-form or non-deterministic prompt generation would make two renders of "the
same" prompt potentially differ, breaking the atomic no-clobber storage protocol's core
assumption (two writers at the same address must be writing the same bytes) and making stored
prompts unverifiable without the exact code version that produced them. Byte-exact canonical
identity makes verification independent of the installed template registry.

## Milestone 1 — Governance/task-state parsing is conservative, with one authoritative source

**Decision:** Task states come only from explicit Markdown headings (`## TASK-ID` + a `Status:`
field) or table rows containing a task-ID-shaped token and a status word — no fuzzy inference.
Exactly one configured document (`governance.task_queue`) is authoritative; every other
configured document is a mirror that must agree with it, checked by `check_task_state` and
`check_governance`.

**Rationale:** A governance tool whose job is to catch documentation drift must not itself
introduce ambiguity about what a document says. Treating one document as authoritative and
everything else as a verified mirror turns "these two docs quietly disagree" into a detectable
`FAIL` instead of a silent inconsistency an agent (or a human) could act on incorrectly.
