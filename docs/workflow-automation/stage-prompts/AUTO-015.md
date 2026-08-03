# AUTO-015 — Deterministic Next-Stage Proposal and Governed Prompt Generation

> **PROPOSAL — NOT AUTHORIZED**
> This is a proposed stage contract, not an authorization. See §29.

> **Revision note.** This is Revision 4 of the AUTO-015 contract. Revision 3 remediated eleven
> findings (AUTO-015-001 through AUTO-015-011) raised by an independent Codex audit against
> Revision 1. Revision 4 remediates the findings of the subsequent **final independent contract
> review** (`AUTO-015-contract-review.md` §4a): DEC-001 through DEC-011 are now independently
> recorded in `docs/DECISION_LOG.md` (§6.1, §29); the overstated claim that
> `AUTO-015-CANDIDATES.md` already conformed to §10.1's typed schema is withdrawn and replaced by a
> real, separately-authored typed catalog file (§9, §23.6); the `FORBIDDEN_OPERATIONS` citation
> (§19.2) and the `canonical_json` separators line citation (§16.2) are corrected. Every correction
> is described in its owning section below. Prior revisions' text is superseded, not amended in
> place, consistent with this repository's own append-only-record discipline
> (`STAGE_REGISTRY.md` §3 rule 8) — no revision of this contract was ever authorized, registered,
> or acted upon, so no historical record is being altered, only a proposal draft.

## 1. Contract Metadata

| Field | Value |
|---|---|
| **Stage** | AUTO-015 |
| **Title** | Deterministic Next-Stage Proposal and Governed Prompt Generation |
| **Status** | `PROPOSED — NOT AUTHORIZED` |
| **Predecessor** | AUTO-014 (`COMPLETE`, merged, published) |
| **Human Owner decision source** | `docs/workflow-automation/successor-planning/AUTO-015-DECISION-TEMPLATE.md` (capability selected 2026-08-04; `OPEN_QUESTIONS.md` OD-13 resolved on the same basis) |
| **Contract source** | This document, Revision 4, drafted under GOV-AUTO-08's follow-up scope, remediated against independent Codex audits, and reconciled against DEC-001 through DEC-011 |
| **Proposed report path** | `docs/reports/workflow-automation/AUTO-015-completion-report.md` (does not exist; created only if AUTO-015 is later implemented) |
| **Proposed branch name** | Not fixed by this contract; branch naming is outside this contract's blocking semantics |
| **Implementation class** | Read-only planning/proposal capability — no target-repository mutation, no runtime workflow-state mutation, no Git/GitHub mutation |
| **Implementation authorization** | **None.** No file outside this contract and its review report may be created or modified under this document. |

## 2. Mission

Define — for future, separate authorization — a deterministic, read-only capability that inspects this repository's own authoritative governance and completed-stage evidence (`docs/TASK_QUEUE.md`, `docs/workflow-automation/STAGE_REGISTRY.md`, `docs/DECISION_LOG.md`, `docs/PROJECT_STATE.md`, completion reports, and successor-planning documents), reconciles that evidence, enumerates candidate successor AUTO-00x stages, evaluates deterministic eligibility rules, produces an evidence-supported recommendation only when policy explicitly permits one, renders a governed prompt draft, validates and persists a hash-bound, non-authoritative proposal artifact, and stops at an explicit Human Owner decision gate.

**What this capability is not.** It is not a decision-maker. It never selects a successor stage for the Human Owner. It never registers a stage in `docs/workflow-automation/STAGE_REGISTRY.md`. It never authorizes anything. It never starts, implements, or executes any successor stage. A proposal is evidence, never authority — the same principle `HUMAN_AUTHORIZATION_MODEL.md` §5a constraint 2 already establishes for `ApprovalService` approvals, applied here to a lower-stakes artifact with no state-transition power at all.

**Relationship to GOV-AUTO-08.** GOV-AUTO-08 already performed one, manual, one-time comparison of twelve successor candidates and recorded the Human Owner's selection of this very capability (`AUTO-015-CANDIDATES.md`, `AUTO-015-DECISION-TEMPLATE.md`). AUTO-015, once authorized and implemented, is the *general, reusable* mechanism that performs an analogous comparison automatically for whichever stage completes *after* AUTO-015 itself — it does not retroactively re-propose or re-decide its own existence, and it does not replace GOV-AUTO-08's own historical record, which remains untouched (`STAGE_REGISTRY.md` §3 rule 8).

## 3. Product Outcome

**What the Human Owner receives:** a single, versioned, hash-bound proposal artifact and an accompanying governed prompt draft, both visibly and structurally labeled `PROPOSAL — NOT AUTHORIZED`, containing: the authoritative evidence the tool read (with per-document hashes); the full candidate list with each candidate's eligibility verdict and reasons; an evidence-supported recommendation *only* when the deterministic policy in §11 explicitly permits exactly one; and a rendered prompt draft suitable for the Human Owner to review, edit, and — only through a separate, explicit act — carry into a future stage's own authorization.

**What the system does not do:** it does not create a branch; does not open, merge, or comment on a pull request; does not commit or push anything; does not write to any authoritative governance document; does not register a stage in `STAGE_REGISTRY.md`; does not flip any task from `Planned` to `Current`; does not invoke Claude, Codex, or any other model provider by default; does not chain its own output into any authorization command.

## 4. Entry Conditions

**Correction (AUTO-015-004).** Revision 1 required "no AUTO-015 implementation, branch, registry row, or task record already exists," which is impossible to satisfy once AUTO-015 has itself been authorized and implemented — the very capability being invoked *is* an AUTO-015 implementation. Revision 1 also required "no task ... is `Current` other than the invocation itself," implying the invocation might itself need to be a `Current` task-queue entry, which contradicts §18 (State Ownership) and §30 (Stop Condition)'s requirement that AUTO-015 owns no task-state transition. Both defects are corrected below: AUTO-015 is a stateless, already-authorized tool invocation (the same category as running `workflowctl verify` or `workflowctl prompt plan-review`), not a task-queue-tracked stage-implementation session — it does not require, read as permitting, or create a `Current` task for itself, ever.

AUTO-015 (the future capability), once authorized and implemented, may run only when:

1. The stage whose successor is being proposed is independently confirmed `COMPLETE` in both `docs/TASK_QUEUE.md` (`Done`) and `docs/workflow-automation/STAGE_REGISTRY.md` (`COMPLETE`), consistent with `STAGE_REGISTRY.md` §3 rule 1's own authorization-precondition list, generalized from "one already-chosen stage" to "candidate evaluation." A named stage not confirmed `COMPLETE` in both is `PREDECESSOR_INCOMPLETE` (§13).
2. `docs/current_task.md` and `docs/remaining_tasks.md` agree with `docs/TASK_QUEUE.md` (`workflowctl check-task-state` passes) — a mirror disagreement is whole-evidence-set inconsistency and fails closed per §11/§13 (`MIRROR_CONTRADICTION`), not merely a per-candidate flag.
3. **No task anywhere in `docs/TASK_QUEUE.md` is `Current` at invocation time.** There is no exception for "the invocation itself," because the invocation is never itself a task-queue entry — AUTO-015 does not run *during* another active stage's work, and running AUTO-015 never requires or creates a `Current` row. A `Current` task found at invocation time is `CONFLICTING_CURRENT_TASK` (§13).
4. `workflowctl verify --config self-governance.yaml`'s `task-state`, `governance`, `registries`, and `handover` checks all pass unconditionally (§7's evidence model states why `handover` is required, not optional, here); the `git` check's tolerance for a local-only, unpushed branch's `upstream_missing` finding, already established by precedent, applies unchanged, but `branch_mismatch`/`head_mismatch`/working-tree-dirtiness findings do not receive any tolerance.
5. Every authoritative source document named in §8 — including the candidate catalog and the active `self-governance.yaml` (or configured equivalent) — is present, readable, within configured size limits, and not a symlink escaping the repository root, per the snapshot protocol in §7.
6. **No unauthorized or unrecognized successor-planning implementation exists.** Specifically: no branch, source symbol, or `STAGE_REGISTRY.md` row exists for any successor stage other than (a) AUTO-015's own already-authorized, already-registered implementation, whose package identity is validated at each invocation against the version recorded in this contract's implementation manifest (§22), and (b) any candidate stage that has been separately, explicitly authorized through its own distinct stage contract (which AUTO-015 did not itself propose into existence). A branch, symbol, or registry row matching neither category is `UNAUTHORIZED_SUCCESSOR_IMPLEMENTATION_DETECTED` and fails closed before any evidence read begins.
7. The invocation supplies the required `--predecessor <STAGE_ID>` identifying exactly which
   completed stage's successor is being proposed; no invocation silently infers "the most recent
   stage." A missing or malformed predecessor is classified by the typed predecessor failures in
   §13, while other malformed invocation/configuration inputs are `INVALID_INVOCATION`.
8. The tool's own validated configuration (static candidate catalog location, external repository-scoped artifact-root policy, fixed eligibility/recommendation policies, and repository identity policy) is present and valid; a missing or invalid configuration is a precondition failure (`INVALID_INVOCATION`), not an assumed default.

### 4.1 Required predecessor invocation argument

Every invocation must use the exact command defined in §23.2 and supply
`--predecessor <STAGE_ID>`. The argument identifies the completed stage whose successor
proposal is being generated; it never selects a successor, authorizes or registers anything,
mutates or reopens the predecessor, or requires the predecessor to be numerically latest.

The predecessor Stage ID must match the repository's canonical stage identifier grammar
`^AUTO-[0-9]{3}$`, exist in the authoritative `STAGE_REGISTRY.md`, have status `COMPLETE`,
agree with the authoritative Task Queue and mirrors, and have valid completion evidence.
The predecessor evidence must be bound to the current repository identity and baseline and
must be included in the canonical evidence manifest and proposal hash. Historical stages may
be rejected when their evidence is stale or cannot be bound to the current identity/baseline.

The following typed, whole-proposal failures apply before candidate evaluation:
`MISSING_PREDECESSOR`, `INVALID_PREDECESSOR_ID`, `PREDECESSOR_NOT_REGISTERED`,
`PREDECESSOR_NOT_COMPLETE`, `PREDECESSOR_STATUS_CONTRADICTION`,
`PREDECESSOR_COMPLETION_EVIDENCE_MISSING`, `PREDECESSOR_EVIDENCE_INVALID`,
`PREDECESSOR_REPOSITORY_MISMATCH`, and `PREDECESSOR_BASELINE_MISMATCH` (§13).

## 5. Approved Runtime Flow

```text
Resolve repository identity and Git baseline (§7)
→ take initial evidence snapshot (§7): read, normalize, hash all authoritative sources
→ reconcile authoritative sources and mirrors (§8)
→ enumerate candidate definitions per the selected Candidate Source Policy (§9)
→ evaluate deterministic eligibility and blockers per candidate (§10, §11)
→ produce recommendation or refusal/no-eligible outcome (§12)
→ render governed prompt draft from fixed templates + typed data only (§14)
→ structurally validate proposal and prompt (§15)
→ re-snapshot and re-hash all evidence; re-read Git identity/baseline; abort on drift (§7)
→ persist hash-bound proposal artifact (§17)
→ stop at Human Owner decision gate (§30)
```

Every step in this flow is **proposed, not authorized**. Nothing beyond this contract's own drafting and review exists today. Once (and only if) a future session is separately authorized to implement this flow:

- "Resolve repository identity" and "take initial evidence snapshot" are pure, side-effect-free reads (§7, §8).
- "Reconcile authoritative sources and mirrors" applies the precedence and contradiction rules of §8 and fails closed (§11, §13) on whole-evidence-set inconsistency.
- "Enumerate candidate definitions" reads candidates per the Human-Owner-selected Candidate Source Policy (§9) — it never invents a candidate from free text under either policy option.
- "Evaluate deterministic eligibility and blockers" applies §11's rules per candidate, using the typed Candidate Model of §10.
- "Produce recommendation or refusal/no-eligible result" follows §12's outcome taxonomy — never silently picks a winner among multiple eligible candidates, and never auto-recommends beyond what §11's Human-Owner-set recommendation policies permit.
- "Render governed prompt draft" produces Markdown carrying the mandatory sections of §14, sourcing directive language only from fixed templates — never from untrusted document content (§14's content-sourcing rule and threat model).
- "Structurally validate proposal and prompt" re-derives every hash and required section from the canonical inputs and refuses to persist on any mismatch (§16, §15).
- "Re-snapshot and re-hash" is the second half of the TOCTOU-mitigation snapshot protocol (§7) — it detects evidence that changed between the initial read and the moment of publication and aborts (`INPUT_DRIFT`) rather than publishing a torn read.
- "Persist hash-bound proposal artifact" writes exactly once, atomically, no-clobber, to the
  external repository-scoped artifact root fixed by DEC-002/DEC-010 (§17).
- "Stop at Human Owner decision gate" — no step beyond persistence exists. See §30.

## 6. Correction Index (AUTO-015-001 through AUTO-015-011, plus the final independent review's findings)

This table maps each independent-audit finding to the section(s) that remediate it, so a second reviewer can verify closure without re-deriving the mapping.

| Finding | Description | Remediated in |
|---|---|---|
| AUTO-015-001 | Architecture conflict (decision template vs. `ARCHITECTURE.md` vs. cross-package import) | §19, §6.1 DEC-001 |
| AUTO-015-002 | Catalog text is prompt-injectable, untrusted | §14 (content-sourcing/threat model), §22 (security tests) |
| AUTO-015-003 | Outcome/failure taxonomy contradictions | §12, §13 |
| AUTO-015-004 | Impossible AUTO-015 self-absence entry condition | §4 |
| AUTO-015-005 | Incomplete TOCTOU protocol | §7 |
| AUTO-015-006 | Candidate duplicate/conflict/unknown/dependency rules incomplete | §10 |
| AUTO-015-007 | Canonicalization and proposal-ID ambiguity | §16 |
| AUTO-015-008 | Publication race and restart semantics | §17 |
| AUTO-015-009 | Git baseline and repository identity ambiguity | §7 |
| AUTO-015-010 | Overbroad Human Owner decision list | §29, §6.1 |
| AUTO-015-011 | Stale `48 Done` count in the contract-review report | See `AUTO-015-contract-review.md` §4 — verified not present in either currently-controlled document; see disposition there |
| AUTO-015-F1 | DEC-001–011 had no independent record outside this contract and its own review report | `docs/DECISION_LOG.md` 2026-08-04 entry; §6.1, §29 |
| AUTO-015-F2 | §9 overstated `AUTO-015-CANDIDATES.md`'s conformance to the §10.1 typed schema | §9 (corrected), new `AUTO-015-AUTHORITATIVE-CATALOG.yaml`, §23.6, §29 item 1 |
| AUTO-015-F3 | `FORBIDDEN_OPERATIONS` misattributed to `service.py` (actually test-only) | §19.2 |
| AUTO-015-F4 | `canonical_json` separators cited at `renderer.py:76` instead of `:77` | §16.2 |

## 6.1 Resolved Human Owner Decisions

The Human Owner accepted DEC-001 through DEC-011, recorded independently in `docs/DECISION_LOG.md`
(2026-08-04 entry, "Human Owner accepted DEC-001 through DEC-011 for the proposed AUTO-015
contract"), per §29. These decisions are incorporated into this contract and are no longer blocking
decisions:

1. **DEC-001 — Architecture:** Option A, Core Engine Planning Service under
   `src/ai_workflow_engine/successor_planning/`; no AgentOS `WorkflowService` adapter.
2. **DEC-002 — Artifact root:** external repository-scoped root
   `~/.ai-workflow-engine/successor-proposals/<repository-id>/`, never part of Git.
3. **DEC-003 — Candidate source:** static authoritative catalog only; no arbitrary-prose or
   bounded-derived candidates in AUTO-015 MVP.
4. **DEC-004 — One eligible candidate:** always issue an advisory recommendation; it is never
   selection, registration, authorization, implementation permission, or owner approval.
5. **DEC-005 — Multiple eligible candidates:** list all eligible candidates and recommend none;
   the Human Owner alone selects one.
6. **DEC-006 — Entry surface:** a new read-only `workflowctl successor-planning` command backed
   by the Core Engine Planning Service.
7. **DEC-007 — Publication:** accept the lock-free, immutable, content-addressed, atomic,
   no-clobber protocol in §§17–18.
8. **DEC-008 — Rendering:** accept §14's safe structured rendering; repository-derived content
   remains untrusted data and never becomes directive text.
9. **DEC-009 — Identity and baseline:** accept §7's repository identity, Git baseline, evidence
   snapshot, drift detection, and fail-closed protocol.
10. **DEC-010 — Repository ID:**
    `<normalized-repository-name>--<first-12-hex-characters-of-SHA256(canonical-primary-remote-identity)>`.
    The primary remote identity excludes credentials, query parameters, and fragments; normalizes
    equivalent SSH/HTTPS forms, host casing, and optional `.git`; retains owner and repository
    name; and excludes local filesystem paths. Ambiguous configured-root, worktree, remote, or
    upstream identity fails closed. The repository-specific root is
    `~/.ai-workflow-engine/successor-proposals/ai-workflow-engine--<12-hex-digest>/`.
11. **DEC-011 — CLI:**
    `workflowctl successor-planning propose --config <CONFIG_PATH> --predecessor <STAGE_ID>`,
    with optional `--output console|json` (default `console`) and `--dry-run`. Policy and
    identity inputs come only from validated configuration and this contract; mutation,
    authorization, registration, provider, Git, task, workflow, commit, push, PR, and merge
    options are absent.

## 7. Repository Identity, Git Baseline, and Evidence Snapshot Protocol

**Corrections (AUTO-015-005, AUTO-015-009).** Revision 1's §6 asserted "AUTO-015 reads no live Git state of its own ... it never inspects a target repository's Git state, since AUTO-015 has no target repository." This was incorrect and is reversed here: AUTO-015 has no *target* repository in the AgentOS runtime-workflow sense, but it unconditionally must inspect the Git state of **the repository it is running in**, because that state (branch, HEAD, working-tree cleanliness) is itself part of the evidence a proposal is built on and must be bound into the proposal's hash. Revision 1 also left the snapshot/TOCTOU protocol as a single vague sentence in §15 ("observe a single, internally consistent snapshot ... or detect the drift"). This section replaces both with one complete, coherent protocol.

### 7.1 Repository identity — typed binding

A `RepositoryIdentity` record is captured once at the start of every invocation and re-captured immediately before publication (§7.3). Minimum fields:

| Field | Source | Notes |
|---|---|---|
| `configured_repository_root` | `self-governance.yaml` `project.repository` | the only repository-root field this repository's own configuration defines (verified: no separate `repository_identity` field exists in `self-governance.yaml` today) |
| `resolved_repository_root` | `Path(configured_repository_root).resolve(strict=True)` | no-follow-then-resolve; must succeed or the invocation fails closed |
| `configured_repository_id` | `self-governance.yaml` `project.id` | the closest existing "identity" field; used for the human-readable label only |
| `git_worktree_root` | `git rev-parse --show-toplevel` (read-only, via the existing `GitClient` allowlist pattern in `src/ai_workflow_engine/git/client.py`) | must equal `resolved_repository_root` — see §7.2 rule 1 |
| `branch` | `GitClient.status().branch` (reuses `src/ai_workflow_engine/git/client.py:49-52`) | |
| `head_sha` | `GitClient.status().head` (reuses `client.py:59-62`) | |
| `upstream_ref` | `GitClient.status().upstream` (reuses `client.py:64-70`) | may be `None`; see `self-governance.yaml` `require_upstream` |
| `ahead_behind` | `GitClient.status().ahead_behind` when upstream present (`client.py:72-76`) | |
| `working_tree_status` | `GitClient.status()`'s modified/staged/untracked lists (`client.py:78-107`) | |
| `config_hash` | SHA-256 of the exact bytes of `self-governance.yaml` (or the configured-equivalent file) as read | binds the active configuration into the evidence manifest per §8 |

This directly reuses the existing `CanonicalGitStatus` shape (`src/ai_workflow_engine/prompt/models.py:155-168`) as its Git-fields pattern rather than inventing a second one, and the existing `GitClient`'s read-only command allowlist and `GIT_OPTIONAL_LOCKS=0` discipline (`client.py:15-24, 33-36`) rather than a new Git access path. **No Git command available to AUTO-015 may mutate state** — only the existing read-only allowlisted forms are used; this is a structural (AST-level) invariant, tested per §22 invariant 12.

### 7.1a Canonical repository identifier and artifact root

The canonical repository ID is:

```text
<normalized-repository-name>--<first-12-hex-characters-of-SHA256(canonical-primary-remote-identity)>
```

`canonical-primary-remote-identity` excludes credentials, tokens, query parameters, and
fragments; normalizes equivalent SSH and HTTPS identities, host casing, and an optional `.git`
suffix; and retains the repository owner and name. The local filesystem path never participates
in this identity. Configured repository identity, Git worktree, primary remote, and upstream
identity must reconcile unambiguously or the invocation fails closed. The artifact root is
`~/.ai-workflow-engine/successor-proposals/<repository-id>/`; for this repository it has the
form `~/.ai-workflow-engine/successor-proposals/ai-workflow-engine--<12-hex-digest>/`.
Proposal filenames use the full canonical proposal SHA-256 digest.

### 7.2 Validation rules

1. `git_worktree_root` must equal `resolved_repository_root` after safe resolution. A mismatch is `repository_identity_mismatch` — a whole-invocation, fail-closed failure (§13): the tool refuses to guess which of two disagreeing roots is authoritative.
2. `configured_repository_root` must itself resolve (no missing directory, no symlink escaping to an unexpected location per §7.4). Failure here is `INVALID_INVOCATION`.
3. Branch, HEAD, upstream, and ahead/behind counts are captured verbatim into the evidence snapshot (§7.3) — they are informational for eligibility (AUTO-015 does not bind a runtime-workflow authorization the way `HUMAN_AUTHORIZATION_MODEL.md` §2 does) but **must** be present, hashed, and re-verified before publication, because a branch or HEAD change between read and publish is exactly the drift this protocol exists to catch.
4. **Clean-tree and upstream policy.** AUTO-015 does not require a clean working tree to run (it is a read-only reporting tool, not a stage-implementation session — `STAGE_REGISTRY.md` §3 rule 1's clean-tree precondition governs *authorizing a new stage*, not *invoking an already-authorized read-only tool*). It **does** require `upstream_missing` to be tolerated only under the same documented, precedented condition every other `workflowctl verify` caller already tolerates it (a local-only, intentionally unpushed branch) — any other `git` check finding (`branch_mismatch`, `head_mismatch`, or an unexpected working-tree-dirtiness finding against the *protected paths* the checks are scoped to) fails closed as `dirty_baseline`/`upstream_policy_failure` per §13.
5. **Baseline drift between initial snapshot and publication aborts** the invocation with `input_drift`, publishing nothing beyond a refusal record (§13). Drift is detected by comparing every field of §7.1's `RepositoryIdentity` and every hash in the evidence manifest (§8) between the initial and final snapshots (§7.3), byte-for-byte and field-for-field — not by a heuristic "looks unchanged" check.

### 7.3 Complete snapshot sequence

This is the full thirteen-step protocol; each step is testable (§21, §22) and each failure mode named below maps to a failure code in §13.

1. Resolve `configured_repository_root` safely (`Path.resolve(strict=True)`); reject if it does not exist or resolution fails.
2. Open or stat every authoritative file named in §8 using no-follow semantics where the platform supports it (`os.open(..., O_NOFOLLOW)` on POSIX; documented as a residual gap on platforms without it — see §7.5).
3. Reject any authoritative input that is a symlink, unless an explicit future policy names a narrow allowlisted exception (none exists today) — `symlink_policy_violation`, fail closed.
4. Record stable file identity metadata for every authoritative file: absolute resolved path, `st_dev`/`st_ino` (device+inode pair) where available, size, and mtime — used only to detect *replacement* (a different file swapped in at the same path) between steps, not as a substitute for content hashing.
5. Read bytes for every authoritative file, bounded by an explicit per-file byte ceiling (mirroring `agentos_workflow/skills/contract.py`'s `_MAX_CONTRACT_BYTES` pattern) — oversized content fails the read rather than being truncated or exhausting memory.
6. Normalize each file's content according to its file-type contract (§16's canonicalization rules: UTF-8 decode with strict error handling, NFC normalization, line-ending normalization).
7. Hash both the original bytes and the normalized content where §8/§16 require both (original for tamper/identity evidence, normalized for the canonical evidence-manifest hash actually bound into the proposal).
8. Read Git evidence per §7.1 (branch, HEAD, upstream, ahead/behind, working-tree status) in one synchronous `GitClient.status()` pass, exactly as `src/ai_workflow_engine/git/validators.py::check_git` already does for its own single-snapshot check — reused, not reinvented.
9. Parse all documents (governance parser/registry functions for `TASK_QUEUE.md`/`STAGE_REGISTRY.md`; new typed readers for `DECISION_LOG.md`/`PROJECT_STATE.md`/completion reports/`OPEN_QUESTIONS.md`; the candidate catalog reader per §9/§10).
10. Render the proposal and prompt from the parsed, normalized data (§14, §17).
11. **Re-stat and re-hash all evidence** (repeat steps 2-7) immediately before publication.
12. **Re-read Git HEAD, branch, and status** (repeat step 8) immediately before publication.
13. **Abort on any input drift**: compare every hash, every stable-identity tuple, and the full `RepositoryIdentity` record from steps 1-8/11-12; any difference is `input_drift`, fail closed, no artifact published. **Publish only after this final validation succeeds.**

### 7.4 Threats this protocol addresses, and residual risk (honest statement)

- **File replacement** (different content at the same path between read and publish): detected by re-hashing in step 11.
- **Symlink swap** (a file replaced with a symlink, or vice versa, between read and publish): detected by re-checking symlink status in steps 3/11, plus the device+inode identity check in step 4/11 catching a same-path-different-inode substitution even when the new target is not itself a symlink.
- **Branch/HEAD/worktree change**: detected by step 12's re-read against step 8's original capture.
- **Configuration change**: `self-governance.yaml`'s hash is part of the evidence manifest (§8) and is re-verified in steps 11/13 like any other authoritative source.
- **Candidate catalog / handover / completion-report change**: all are named authoritative sources under §8 and therefore covered by the same re-hash-and-compare discipline — not special-cased or omitted.
- **What this protocol does *not* claim.** This is **not** an OS-level atomic snapshot (no filesystem-level point-in-time isolation is taken; no lock is held across the read window). A sufficiently precisely-timed concurrent writer could in principle alter a file *between* an individual file's own read (step 5) and its own hash (step 7) within a single pass, or between two different files' reads within the same pass, producing a read that is individually self-consistent per file but not perfectly atomic *across* files at the same instant. The mitigation is not perfection but **fail-closed detection at the boundary that matters**: the full re-snapshot immediately before publication (steps 11-13) guarantees that whatever was actually published is provably identical, byte-for-byte and field-for-field, to a state that existed at two distinct, individually-hashed points in time (initial read and pre-publication check) — it does not guarantee no third, intermediate state existed that neither snapshot observed. This residual risk is judged acceptable because (a) AUTO-015 is a local, single-operator, read-only advisory tool with no security boundary between the invoking operator and the repository, and (b) the fail-closed re-check makes exploiting the residual window require winning a race against a re-hash that happens immediately before the one write AUTO-015 ever performs — not a standing window an attacker can probe repeatedly. A future implementation must not describe this as "perfect isolation"; it must state this same residual-risk paragraph in its own design notes.

### 7.5 Symlink no-follow platform note

`O_NOFOLLOW` is a POSIX facility; on a platform lacking it, step 2's no-follow open degrades to "resolve then explicitly check `Path.is_symlink()` before opening," which is check-then-use rather than atomically no-follow, and is itself named as a residual TOCTOU gap in that narrow case — not silently presented as equivalent.

## 8. Authoritative Evidence Model

**Precedence, most authoritative first** (documented fact for rank 1; inferred ordering for the rest, since no single document states a unified precedence across all sources — flagged as a design choice made explicit here rather than left implicit):

1. **`docs/TASK_QUEUE.md`** — self-declared authoritative source for task status (its own header: "This document is the `governance.task_queue` source in `self-governance.yaml`"). Wins on any status contradiction.
2. **`docs/workflow-automation/STAGE_REGISTRY.md`** — self-declared "a view of `docs/TASK_QUEUE.md`, never a competing workflow" for status, but the exclusive source for stage-lifecycle mechanics (its own Registry table, Authorization Log, and Control Rules — verified: nineteen numbered rules, `STAGE_REGISTRY.md` §3). A registry/queue status disagreement is *itself* a required finding (§13), not silently resolved by trusting the queue and discarding the disagreement.
3. **Completion reports** (`docs/reports/workflow-automation/AUTO-0XX-completion-report.md`) — authoritative for what a specific completed stage did and found (append-only, `STAGE_REGISTRY.md` §3 rule 8), but never authoritative for *current* task/registry status, which they do not govern and cannot update.
4. **`docs/DECISION_LOG.md`** — authoritative for decision rationale and Human Owner directives; append-only.
5. **`docs/PROJECT_STATE.md`** — prose mirror, plus the `governance.facts` version fact; never an independent status source.
6. **`docs/current_task.md`, `docs/remaining_tasks.md`** — pure mirrors of #1; consulted only as a consistency-check target, never as an independent source.
7. **The candidate catalog** (`docs/workflow-automation/successor-planning/AUTO-015-AUTHORITATIVE-CATALOG.yaml`, per §9) — authoritative for *which candidates exist and their declared, catalog-frozen fields*; never authoritative for a candidate's *live* eligibility, which §11 re-derives from #1-#6 and `OPEN_QUESTIONS.md` at read time regardless of what the catalog's own frozen text says. `AUTO-015-CANDIDATES.md` is the historical, narrative-prose decision-support document this typed catalog was transcribed from (§9); it is never itself read at runtime.
8. **The active configuration** (`self-governance.yaml` or the configured equivalent) — authoritative for where every other source lives and for the repository-identity binding of §7; read-only input, validated at entry (§4 item 8) and re-validated at publication (§7.3).
9. **Git evidence** (§7) — authoritative for this repository's own branch/HEAD/working-tree state; captured and re-verified per §7, never treated as optional or skipped.
10. **Handover evidence** (`handover/PROJECT_CHECKSUM.md`, `handover/PROJECT_HANDOVER.md`, per `self-governance.yaml`'s `handover:` block) — **required, not optional**, whenever `self-governance.yaml` configures it (verified: this repository's own `self-governance.yaml` does configure `handover.manifest`/`handover.files`, and `STAGE_REGISTRY.md` §3 rule 16 already treats the `handover` check as one that "must PASS with no exception" — Revision 1's wording, "read, if configured, purely as ... corroborating evidence," incorrectly implied it was optional or secondary; corrected here per AUTO-015-009).

**Mirrors.** Any disagreement between #1 and #6 is whole-evidence-set inconsistency (`MIRROR_CONTRADICTION`, §13) — this is what `workflowctl check-task-state` already exists to catch, and AUTO-015 refuses to produce any proposal while it fails.

**Completion evidence.** A candidate whose predecessor-completion claim (registry/queue) has no corresponding, readable completion report is `insufficient_evidence` for that candidate specifically (not a whole-proposal refusal), per §11/§13.

**Candidate definitions.** Read per the Candidate Source Policy selected in §9 — never inferred from arbitrary free text in any document under either policy option.

**Historical prose.** Quoted or historical text inside a completion report or decision-log entry (e.g., a past directive's exact words, quoted for context) is treated as inert data throughout — never re-interpreted as a live directive. `AUTO-013-completion-report.md`'s own §1 documents a real, prior instance of exactly this kind of text being flagged and correctly cleared as a false positive; AUTO-015 must apply the same discipline deterministically rather than relying on human judgment at read time, and per §14, that discipline is enforced structurally (typed parsing + fixed templates), not by convention.

**Contradictory evidence.** Any two authoritative sources disagreeing on a fact material to eligibility (e.g., registry says `COMPLETE`, queue says `Current`) is an explicit, named finding. It is never silently resolved by picking the higher-precedence source and discarding the disagreement — the disagreement itself must appear in the proposal's evidence manifest, and (per §13) escalates to whole-proposal refusal when it concerns the queue/registry/mirror set, or to per-candidate `insufficient_evidence` when narrower.

## 9. Candidate Source Policy — resolved to Static Authoritative Catalog

**Correction (part of AUTO-015-006/AUTO-015-010).** Revision 1 left "static versus derived candidate catalog" as an unstructured decision item without defining what "derived" would even mean or how it would stay safe. DEC-003 now resolves the policy to the static authoritative catalog; bounded derivation is outside this MVP.

### Option 1 — Static Authoritative Catalog

Only candidates explicitly present in a Human-Owner-approved candidate catalog file are ever evaluated. The catalog is a versioned document (§10's schema), hand-maintained and reviewed like any other governance document at each future planning round.

- **Input sources:** exactly one file (or an explicitly enumerated small set of files) named in configuration; no other document contributes a candidate definition.
- **Risks:** the catalog can go stale relative to newly-relevant capabilities the Human Owner has not yet written down; mitigated because staleness only ever produces *fewer* candidates considered, never a fabricated one — a safe failure direction.
- **Deterministic behavior:** trivially deterministic — the candidate set is exactly the catalog's parsed content for a given catalog hash.
- **Validation:** the whole-catalog schema validation of §10.
- **Auditability:** maximal — every candidate traces to one hand-authored, versioned file.
- **Recommended default:** **yes.** No source document commits to any derivation mechanism, and this is the only option with zero risk of a repository-text string being misread as a new candidate definition.

### Option 2 — Bounded Derived Candidates

Candidates may additionally be derived, but only from explicitly enumerated **typed governance records** (e.g., a dedicated, schema-validated "successor candidate" front-matter block inside `OPEN_QUESTIONS.md` or `DECISION_LOG.md` entries, if such a typed record type is separately defined and authorized) — **never** from arbitrary prose, headings, or free text in any document.

- **Input sources:** the static catalog (Option 1's file) plus a fixed, enumerated list of typed record locations; anything outside that enumerated list is not a candidate source, regardless of how candidate-shaped its prose looks.
- **Risks:** materially higher than Option 1 — every new typed-record location is a new place an untrusted-content threat (§14) could in principle be aimed at, and the boundary between "typed record" and "free text that merely looks structured" must be enforced by a strict parser, not a heuristic.
- **Deterministic behavior:** deterministic given a fixed enumeration and a strict typed-record schema, but strictly more complex to reason about than Option 1.
- **Validation:** the same §10 schema, plus a second, independent schema for each typed record location, plus the enumeration itself must be closed (an unenumerated location never contributes).
- **Auditability:** lower than Option 1 — a derived candidate's provenance is "this typed record, at this location, at this hash," one more hop than a hand-authored catalog entry.
- **Recommended default:** not recommended unless a specific future need for it is demonstrated; Option 1 is sufficient for the MVP and carries strictly less risk.

**DEC-003 resolves this policy to Option 1.** Option 2 is out of AUTO-015 MVP scope and requires a
future separately authorized stage. No candidate may be derived from arbitrary repository prose,
comments, completion reports, or historical documents.

**Status of `AUTO-015-CANDIDATES.md` — corrected (final independent review).** `AUTO-015-CANDIDATES.md` is the **historical decision-support document** GOV-AUTO-08 used to compare twelve candidates in narrative prose; it remains exactly that, unmodified, and is never itself read at runtime. Independent verification found its actual field set (~21 narrative headings — Problem solved, Intended user, User-visible result, Relationship to AUTO-013/AUTO-014, MVP, Required architecture changes, Workflow states affected, Provider permissions, Write authority, Approval model, Security implications, Configuration changes, Expected source surface, Expected test surface, Live acceptance requirements, Dependencies, Explicit exclusions, Relative size, Principal risks, Deferred defects, Reasons to select, Reasons to reject/defer) does **not** conform to §10.1's typed schema: it has no `candidate_id` grammar slug, no `schema_version`, no `content_hash`, and no typed `dependencies`/`blockers`/`evidence_references` lists. A prior revision's claim that it "already conforms closely" was inaccurate and is withdrawn.

The proposed, typed, versioned static authoritative catalog under Option 1 is instead
`docs/workflow-automation/successor-planning/AUTO-015-AUTHORITATIVE-CATALOG.yaml` — a one-time,
human-authored typed transcription of the same twelve candidates into §10.1's exact schema
(`schema_version: 1`, `catalog_id: auto-015-successor-catalog`, `authorization_status:
NOT_AUTHORIZED`), produced as a required correction identified by the final independent contract
review and cross-referencing `AUTO-015-CANDIDATES.md` as its `historical_source`. Every
`content_hash` in that file is a real SHA-256 digest, computed with the existing production
`prompt/renderer.py:canonical_json` primitive over each candidate's own canonical fields — not a
placeholder — and is independently reproducible. Per §10.1, `lifecycle_status` is deliberately
absent from every entry in that file, since the schema defines it as computed at read time, never
author-set. This YAML file, like `AUTO-015-CANDIDATES.md` before it, is itself a proposed governance
document only: it does not select, authorize, register, or implement anything, and does not become
an authoritative input until a future, separately authorized AUTO-015 implementation reads it under
this section's Option 1 policy. Authoring/maintaining it is added to the implementation
prerequisites (§29) and allowlist (§23.6), and it is now a named authoritative source (§8), snapshot
input (§7.3), and evidence-manifest/hash member (§16.1), alongside the test and live-acceptance
coverage already required for the candidate catalog (§26, §27).

## 10. Candidate Model

**Correction (AUTO-015-006).** Revision 1's candidate table lacked a `schema_version`, a content hash for duplicate/conflict detection, an explicit ID grammar, and any rule for duplicate IDs, conflicting definitions, unknown enum values, or dependency cycles. This section is the complete replacement.

### 10.1 Typed schema

| Field | Type | Notes |
|---|---|---|
| `candidate_id` | string, grammar `^[a-z][a-z0-9]*(-[a-z0-9]+)*$`, length 3-64 | stable slug, never free text; e.g. `automatic-next-stage-computation` |
| `schema_version` | string, e.g. `"1.0"` | additive versioning only, mirrors §16's proposal-schema versioning |
| `title` | string, max 120 chars, plain-text grammar (§14.2) | human-readable name; rendered only in data-scoped spans (§14) |
| `mission` | string, max 2,000 chars, plain-text grammar (§14.2) | one-paragraph problem statement; bounded, not raw Markdown — see §14 for why this is data, not directive prose. (This contract chooses *bounded mission data* over a fixed `mission_code` enum: twelve distinct, meaningfully different candidate missions do not compress into a closed enum without losing information a Human Owner needs to read; the safety property the audit is after — untrusted text never becoming directive prose — is instead guaranteed structurally by §14, not by pre-compressing the field into an enum.) |
| `source_kind` | enum `{static_catalog}` | all AUTO-015 MVP candidates originate in the DEC-003 static authoritative catalog |
| `source_reference` | typed union: `{catalog_path, catalog_version, entry_index}` for `static_catalog`; `{record_type, path, sha256}` for `bounded_derived` | exact provenance |
| `lifecycle_status` | enum `{eligible, blocked, deferred, insufficient_evidence, unknown}` | **computed by §11, never author-set**; `unknown` is reserved for a load-time value outside this enum (a validation failure, §16) |
| `mvp_relation` | enum `{inside, adjacent, outside_deferred, unknown}` | |
| `dependencies` | `list[{dependency_id: str, dependency_type: enum{stage, subsystem, capability}, status: str}]` | typed, not `list[str]` |
| `blockers` | `list[{blocker_id: str (grammar ^(OD|D)-[0-9]+$), blocker_type: enum{open_question, deferred_defect}, live_status: str}]` | re-resolved live against current `OPEN_QUESTIONS.md`/completion-report status at read time, never trusted from the catalog's frozen text |
| `required_owner_decisions` | `list[str]`, each max 200 chars, plain-text grammar | open design questions this candidate would still need resolved before its own authorization |
| `allowed_recommendation_status` | bool | whether this candidate is even eligible to be *recommended* (as opposed to merely listed) under current policy |
| `evidence_references` | `list[{path: str, sha256: str, size: int}]` | exact documents supporting this candidate's status determination |
| `content_hash` | sha256 hex string | SHA-256 over this candidate's own canonical fields *excluding* `lifecycle_status` (which is computed, not part of the candidate's own identity) — used for duplicate/conflict detection below |

### 10.2 Fail-closed rules

- **Duplicate ID, same `content_hash`:** the same candidate definition appearing more than once (e.g., listed under two enumerated sources) is deduplicated to one entry in the manifest; not an error, not a conflict.
- **Duplicate ID, different `content_hash`:** `DUPLICATE_CANDIDATE_CONFLICT` (§13). Scope: **per-candidate** — that `candidate_id` is excluded from eligibility entirely, both conflicting definitions are listed verbatim with the conflict named, and evaluation continues for every other candidate. This candidate is never silently resolved by picking one definition.
- **Unknown `schema_version` at the catalog-file level** (the file's own declared version, not a single entry's): the catalog cannot be safely parsed at all → `authoritative_source_missing` (§13), whole-proposal, since the candidate catalog is itself a required authoritative source (§8 item 7).
- **Unknown `schema_version` on an individual entry** (the file parses, but one entry declares a version this reader does not support): `MALFORMED_CANDIDATE`, per-candidate, excluded with the reason recorded; other candidates are unaffected.
- **Unknown `source_kind`:** `UNKNOWN_CANDIDATE_TYPE`, per-candidate.
- **Unknown `dependency_type` or `blocker_type`:** `UNKNOWN_CANDIDATE_TYPE`, per-candidate — the candidate is excluded (its eligibility cannot be soundly computed without understanding every typed dependency/blocker), not silently evaluated with the unknown entry ignored.
- **Malformed candidate** (missing required field, grammar violation, field-length violation): `MALFORMED_CANDIDATE`, per-candidate.
- **Cyclic dependencies:** every candidate participating in the cycle is marked `blocked` with `DEPENDENCY_CYCLE` named explicitly, listing the full cycle — never silently broken by dropping one edge.
- **Missing dependency** (a `dependency_id` naming something that does not resolve to a known stage/subsystem/capability): the candidate is `blocked`, with the unmet dependency named.
- **Conflicting definitions from multiple sources** (only reachable under §9 Option 2, where `static_catalog` and `bounded_derived` could name the same `candidate_id`): treated identically to the duplicate-ID rule above — same `candidate_id`, different `content_hash`, per-candidate `DUPLICATE_CANDIDATE_CONFLICT`.
- **Ambiguous authority or identity, generally:** fails closed to per-candidate exclusion at minimum, and to whole-proposal refusal when the ambiguity concerns the evidence set itself (§8, §13) rather than one candidate's own definition.
- **Candidates are never derived from arbitrary prose**, under either §9 policy option — this is a structural property of the reader (a strict typed parser with `extra="forbid"` semantics, mirroring `PromptStrictModel`'s existing discipline in `src/ai_workflow_engine/prompt/models.py`), not a convention.

## 11. Eligibility and Recommendation Policy

Deterministic rules, per candidate and for the proposal as a whole:

- **Eligible:** predecessor-completion facts (queue + registry, in agreement) confirm the stage this candidate would follow is `COMPLETE`; every blocker in `blockers` is either absent or resolves, on live re-check, to a status that does not gate *authorization* (`OPEN_QUESTIONS.md`'s own "blocks stage X's authorization" vs "blocks/affects... implementation" distinction, §1's format note, governs this line exactly); no contradictory evidence exists for this candidate specifically; no `DUPLICATE_CANDIDATE_CONFLICT`/`UNKNOWN_CANDIDATE_TYPE`/`MALFORMED_CANDIDATE`/`DEPENDENCY_CYCLE` finding applies to it.
- **Blocked:** an authorization-blocking OD-# is `Open` and cited against this candidate, or the candidate's own stated dependencies are not yet satisfied, or it participates in a dependency cycle (§10.2).
- **Deferred:** the candidate is structurally sound but the Human Owner has previously and explicitly deferred it (e.g., "No AUTO-015 at this time" style prior disposition) — distinct from `blocked`, which is a hard gate, and carried forward as informational history, never silently dropped.
- **Insufficient evidence:** a specific document this candidate's status determination depends on is missing, unreadable, or fails validation — this candidate alone is marked `insufficient_evidence`; it does not, by itself, refuse the whole proposal (§8, §13).
- **No eligible candidate:** a valid, positive result — not an error, not a refusal. Reported as the `NO_ELIGIBLE_CANDIDATE` variant of `PROPOSAL_READY` (§12), matching `AUTO-015-CANDIDATES.md`'s own explicit statement that "No AUTO-015 at this time" is a valid outcome (Candidate 11).

### 11.1 Exactly one eligible candidate — resolved by DEC-004

**Correction.** Revision 1 silently decided this case ("a recommendation is *permitted*") without offering it as an explicit Human Owner decision, unlike the multiple-candidate case immediately below it. That asymmetry is corrected here.

Options:

1. **Always issue an advisory recommendation** for the single eligible candidate. *Resolved by DEC-004* — every recommendation is already non-binding and immune to override (§18, §30), so surfacing the one available candidate as a labeled, advisory recommendation adds no authority.
2. **Report eligibility without recommendation** — list the one eligible candidate exactly as the multiple-candidate case would, with no `recommendation` field populated.
3. **Recommend only when a static policy explicitly allows it** for that specific candidate (`allowed_recommendation_status` field, §10.1) — the most conservative option, requiring per-candidate opt-in.

**Resolved rule:** always issue the advisory recommendation. It remains informational and never
constitutes selection, registration, authorization, implementation permission, or Human Owner
approval.

### 11.2 Multiple eligible candidates — resolved by DEC-005

Options:

1. **Never recommend** — always report only the eligible set, `recommendation` structurally absent.
2. **Recommend using a Human Owner-approved static ranking policy** — no such policy is authorized anywhere today; this option is inert until one is separately defined and approved.
3. **Return only the eligible set** (equivalent in practice to option 1 under today's absence of a ranking policy).

**Resolved rule:** list all eligible candidates and recommend none — the `recommendation` field is
structurally absent in the `MULTIPLE_ELIGIBLE_NO_RECOMMENDATION` variant (§12). The Human Owner
alone selects one; AUTO-015 never ranks, selects, registers, or authorizes a candidate.

### 11.3 General rules

- **Conflicting candidates:** handled at the candidate-model level (§10.2's `DUPLICATE_CANDIDATE_CONFLICT`) — never silently merged or one silently dropped.
- **The tool never auto-selects or auto-authorizes**, under any eligible-candidate count. Unknown or conflicting candidates (§10.2) are never recommended, regardless of §11.1/§11.2's eventual policy.
- **Recommendation is always advisory.** The rendered prompt and the persisted artifact both carry the non-authoritative labeling of §14/§17 regardless of whether a recommendation is present.
- **Refusal:** whole-evidence-set inconsistency (mirrors disagree; a `workflowctl verify` governance/task-state/registries/handover check fails; the invoked stage's own completion cannot be confirmed; repository-identity mismatch; input drift) refuses to produce *any* candidate list or recommendation at all — only a labeled refusal record, itself hash-bound and persisted like any other outcome (never a bare exception). See §12/§13 for the exact taxonomy.

## 12. Outcome Taxonomy

**Correction (AUTO-015-003, AUTO-015-008).** Revision 1 mixed a five-value flat outcome enum (§8) with a differently-shaped failure-code list (§16) and never fully reconciled them; the independent audit additionally required a specific vocabulary (`PROPOSAL_READY`, `NO_ELIGIBLE_CANDIDATE`, `MULTIPLE_ELIGIBLE_NO_RECOMMENDATION`, `RECOMMENDATION_READY`, `INSUFFICIENT_EVIDENCE`) that does not map one-to-one onto a flat enum, because `PROPOSAL_READY` is not a peer of the other four — it is the outer wrapper meaning "generation succeeded, an artifact was persisted," while the other four are mutually exclusive *variants* describing *what kind* of successful result it is. This contract resolves the ambiguity with an explicit two-level discriminated structure so the same input can never map to two different outcomes:

```text
outcome_class: "PROPOSAL_READY" | "FAILURE"

if outcome_class == "PROPOSAL_READY":
    result_variant: one of
        "NO_ELIGIBLE_CANDIDATE"
        "RECOMMENDATION_READY"                  # exactly-one-eligible, recommendation issued
        "MULTIPLE_ELIGIBLE_NO_RECOMMENDATION"
        "INSUFFICIENT_EVIDENCE"                 # whole-proposal: every candidate individually
                                                  # insufficient_evidence, but the evidence SET
                                                  # itself is internally consistent (§8) — distinct
                                                  # from a FAILURE, because the tool did its job
                                                  # correctly; there was simply not enough signal
                                                  # to say more.

if outcome_class == "FAILURE":
    failure_code: one of §13's codes; no proposal body is produced beyond the refusal record.
```

`result_variant = NO_ELIGIBLE_CANDIDATE` requires zero eligible candidates and at least one candidate evaluated with a definite `blocked`/`deferred`/conflict status (i.e., the evidence was sufficient to reach a definite verdict, it was just never "eligible"). If *every* candidate instead lands on `insufficient_evidence`, the whole-proposal variant is `INSUFFICIENT_EVIDENCE`, not `NO_ELIGIBLE_CANDIDATE` — these are deliberately distinguished so a reader can tell "we know none of these are ready" from "we don't have enough evidence to know."

This is the exhaustive outcome set. A future implementation may not introduce an undocumented sixth variant or a new `outcome_class` without amending this contract, and every test in §22 that exercises an outcome asserts against this exact two-level structure, not a flat string.

## 13. Failure Taxonomy

**Correction (AUTO-015-003).** Every failure code below is tagged with its exact scope (`whole_proposal` or `per_candidate`) so §10.2's "Define exactly when stale or missing evidence is: candidate-level insufficiency; whole-proposal refusal; hard failure" is answered unambiguously and testably (§22), and so no contract section elsewhere may contradict this table.

| Code | Scope | Meaning |
|---|---|---|
| `INVALID_INVOCATION` | whole_proposal | caller supplied invalid paths, unsupported options, or configuration is missing/malformed (§4 item 8) |
| `MISSING_PREDECESSOR` | whole_proposal | required `--predecessor <STAGE_ID>` was omitted |
| `INVALID_PREDECESSOR_ID` | whole_proposal | predecessor does not match `^AUTO-[0-9]{3}$` |
| `PREDECESSOR_NOT_REGISTERED` | whole_proposal | predecessor ID does not exist in the authoritative Stage Registry |
| `PREDECESSOR_NOT_COMPLETE` | whole_proposal | predecessor is not `COMPLETE` in the authoritative lifecycle evidence |
| `PREDECESSOR_STATUS_CONTRADICTION` | whole_proposal | predecessor status conflicts across Registry, Task Queue, or mirrors |
| `PREDECESSOR_COMPLETION_EVIDENCE_MISSING` | whole_proposal | no valid completion report/evidence exists for the named predecessor |
| `PREDECESSOR_EVIDENCE_INVALID` | whole_proposal | predecessor completion evidence is malformed, unreadable, or fails validation |
| `PREDECESSOR_REPOSITORY_MISMATCH` | whole_proposal | predecessor evidence is bound to a different repository identity |
| `PREDECESSOR_BASELINE_MISMATCH` | whole_proposal | predecessor evidence is bound to a different Git baseline or cannot be reconciled with the current baseline |
| `PREDECESSOR_INCOMPLETE` | whole_proposal | the named stage is not confirmed `COMPLETE` in both `docs/TASK_QUEUE.md` and `STAGE_REGISTRY.md` (§4 item 1) |
| `CONFLICTING_CURRENT_TASK` | whole_proposal | some other task is `Current` in `docs/TASK_QUEUE.md` at invocation time (§4 item 3) |
| `UNAUTHORIZED_SUCCESSOR_IMPLEMENTATION_DETECTED` | whole_proposal | a branch, source symbol, or registry row exists for a successor stage that is neither AUTO-015's own authorized implementation nor a separately-authorized candidate (§4 item 6) |
| `REPOSITORY_IDENTITY_MISMATCH` | whole_proposal | `git_worktree_root` != `resolved_repository_root` (§7.2 rule 1) |
| `DIRTY_BASELINE` | whole_proposal | `git` check finds `branch_mismatch`/`head_mismatch`/unexpected working-tree dirtiness (§7.2 rule 4) |
| `UPSTREAM_POLICY_FAILURE` | whole_proposal | `upstream_missing` outside the one documented, precedented tolerance (§7.2 rule 4) |
| `AUTHORITATIVE_SOURCE_MISSING` | whole_proposal | a required document (§8) is absent, unreadable, or (for the candidate catalog specifically) fails file-level schema parsing (§10.2) |
| `MIRROR_CONTRADICTION` | whole_proposal | `docs/current_task.md`/`docs/remaining_tasks.md` disagree with `docs/TASK_QUEUE.md`, or registry/queue status disagree materially (§8) |
| `MALFORMED_CANDIDATE` | per_candidate | one candidate entry fails schema validation (§10.2) |
| `DUPLICATE_CANDIDATE_CONFLICT` | per_candidate | same `candidate_id`, different `content_hash` (§10.2) |
| `UNKNOWN_CANDIDATE_TYPE` | per_candidate | unrecognized `source_kind`/`dependency_type`/`blocker_type` (§10.2) |
| `DEPENDENCY_CYCLE` | per_candidate | candidate participates in a dependency cycle (§10.2); applies to every candidate in the cycle |
| `STALE_COMPLETION_EVIDENCE` | per_candidate | claimed predecessor-completion has no corresponding readable completion report (§8) |
| `INPUT_DRIFT` | whole_proposal | the final snapshot (§7.3 steps 11-13) disagrees with the initial snapshot |
| `PROMPT_VALIDATION_FAILURE` | whole_proposal | the rendered prompt fails structural re-derivation/re-hash checks (§15, §16) |
| `SECRET_DETECTED` | whole_proposal, **failure only when unredactable** | ordinary redaction succeeding is a **warning**, not a failure (§12's `PROPOSAL_READY` outcomes may still carry warnings); a secret-shaped string the redaction pass could not safely neutralize escalates to this failure |
| `PATH_ESCAPE` | whole_proposal | a resolved path fell outside its allowed root (§17) |
| `SYMLINK_POLICY_VIOLATION` | whole_proposal | an authoritative input or a publication-path component was a symlink where policy forbids it (§7.3 step 3, §17) |
| `PUBLICATION_CONFLICT` | whole_proposal | a content-address collision with genuinely different content at publish time (§17) |
| `PUBLICATION_FAILURE` | whole_proposal | the atomic publish step itself failed (I/O error, permission failure, disk full) after validation passed |
| `SECURITY_POLICY_FAILURE` | whole_proposal | catch-all for a confirmed adversarial-content finding that §14's neutralization could not safely resolve (e.g., a control-character/Unicode-direction-control payload that survives normalization) |

Every code above appears in exactly one row of this table with exactly one scope; no other contract section may assign a different scope to the same code. `evidence_drift_during_generation` (Revision 1's name) is renamed `INPUT_DRIFT` here for consistency with §7's terminology; no behavior changes.

## 14. Governed Prompt Contract and Untrusted-Content Handling

**Correction (AUTO-015-002).** This is the most significant correction in this revision. Revision 1's §17 already stated the *principle* ("untrusted text is data, never control") but did not specify the *mechanism* precisely enough to be implemented or tested without ambiguity — no bounded field lengths, no identifier grammar, no explicit Markdown/HTML disposition, no Unicode-control handling, no concrete adversarial test corpus. `AUTO-015-CANDIDATES.md`'s own Candidate 4 entry already names this exact risk: *"report content is attacker-controlled."* This section is the complete mechanism.

### 14.1 The generated prompt

The generated prompt is Markdown, and must include, as required (position-checked) sections:

1. **A fixed, byte-exact, non-templated banner as the first line**: `**PROPOSAL — NOT AUTHORIZED**` — sourced only from the tool's own constant, never from any document-derived field, generated only from fixed program text.
2. Target repository (this repository's own configured identity, §7).
3. Predecessor identity as fixed structured metadata: the validated `predecessor_stage_id`, Registry
   status, completion-evidence references/hashes, and status-reconciliation result. These values
   are data-scoped and never directive text.
4. Selected/proposed candidate stage (or, for `MULTIPLE_ELIGIBLE_NO_RECOMMENDATION`, the full list with no single stage singled out as "the" proposal).
5. Evidence references (the evidence manifest, or a summary with a pointer to the full manifest in the structured artifact).
6. Exact mission (drawn from the candidate's own `mission` field — rendered in a data-scoped span per §14.2, not directive prose).
7. Proposed scope.
8. Exclusions.
9. Allowed files (a placeholder statement that the *actual* stage contract, if this candidate is later authorized, must name its own exact file allowlist — this document never asserts one).
10. Verification (a placeholder pointing at §23's canonical command set as the baseline any future contract must specify concretely).
11. Security invariants (a placeholder pointing at this contract's own §22 as the baseline).
12. Blocker policy (a restatement of the "fix only direct blockers" discipline every AUTO-0xx stage already follows).
13. Stop condition (mirrors §30).
14. **A second, explicit non-authorization banner immediately before any recommendation content** — distinct occurrence from item 1, so the label survives even if a reader jumps past the header.

### 14.2 Typed field grammar for every catalog/document-sourced scalar

Every scalar field that can end up in a rendered prompt or persisted artifact and originates from repository content (title, mission, evidence-quote excerpts, dependency/blocker identifiers, required-owner-decision strings) is parsed through one strict typed-field contract before it is used anywhere:

- **Strict typed parsing:** every field has a declared type (`str`, bounded list, enum) with `extra="forbid"` at the model level (mirroring `PromptStrictModel`) — an unrecognized field in a source document is a schema error, not silently ignored or passed through.
- **Bounded scalar fields:** every string field has an explicit maximum length (§10.1 states them per field: e.g. `title` ≤ 120 chars, `mission` ≤ 2,000 chars); a field exceeding its bound is `MALFORMED_CANDIDATE` (per-candidate) rather than silently truncated (truncation could itself create a misleading, attacker-shaped fragment).
- **Identifier grammar:** `candidate_id`, `dependency_id`, `blocker_id` all match a closed regex grammar (§10.1); no free text is ever accepted where an identifier is expected.
- **Control-character rejection:** every string field is rejected outright (not stripped) if it contains any C0/C1 control character other than `\n` inside a genuinely multi-line field — mirroring `PromptStrictModel`'s existing surrogate-code-point rejection (`prompt/models.py`) extended to the full control-character class, since a stripped-and-continued string is exactly the kind of "best-effort recovery" this contract's fail-closed principle forbids.
- **Unicode normalization policy:** every string field must already be NFC-normalized on input (reusing `canonicalize_json_value`'s existing NFC discipline, `prompt/models.py:77-113`) — a field failing this check is `MALFORMED_CANDIDATE`, not silently re-normalized and accepted (silent re-normalization would let a homoglyph/direction-control payload through under a "corrected" hash that no longer matches what a reviewer actually read).
- **Unicode direction controls specifically:** any codepoint in the Unicode bidirectional-control category (e.g. `U+202E RIGHT-TO-LEFT OVERRIDE`, `U+2066`-`U+2069` isolates) anywhere in a repository-sourced field is rejected, not merely flagged — these have no legitimate use in any field this schema defines and are a documented prompt-injection/visual-spoofing vector.
- **Markdown/HTML disposition — concrete rendering mechanism, not merely a stated intent.** Repository-sourced text is **never** parsed as Markdown and never rendered as raw HTML. Every data-scoped section of the rendered prompt (evidence quotes, candidate title/mission/evidence-reference content) is rendered as **one JSON object, containing every repository-sourced string for that section as ordinary JSON string values, placed inside a single fenced code block** — never as an inline blockquote and never as bare interpolated text, because both of those constructs are line-oriented and therefore vulnerable to an embedded blank line plus a line-start `` ``` `` or `#`/`>` reopening/closing document structure early. JSON string escaping (backslash-escaping of `"`, `\`, and all control characters, per `canonical_json`'s existing `json.dumps` behavior) neutralizes every Markdown-significant character *within* the string value, since none of them can terminate a JSON string or begin a new JSON token from inside one. The only remaining escape surface is the **outer fence** itself: a field engineered to contain a long run of backticks could attempt to prematurely close the surrounding ```` ``` ```` fence. This is closed by the standard CommonMark technique, made explicit and bounded here rather than assumed: **before rendering, scan the fully-serialized JSON text for the longest consecutive run of backtick characters it contains, and open/close the surrounding fence with one more backtick than that longest run** (minimum three, matching ordinary Markdown fences). Because the fence-length computation happens on the *final serialized JSON bytes* (after JSON string-escaping, which cannot itself introduce a bare backtick run longer than what was already in the source field), this is well-defined and terminates in one pass — no iterative escaping is needed. **A field whose own backtick-run length would force the fence past a fixed cap (32 backticks) is rejected outright** as adversarial-shaped content (`SECURITY_POLICY_FAILURE`, §13) rather than accommodated with an ever-longer fence, closing the "very long/degenerate field" class of attack this mechanism would otherwise be forced to accept unboundedly.
- **No raw Markdown interpolation, ever**, into a directive-shaped section (mission narrative prose, scope, exclusions, banners, stop condition) — those sections are built exclusively from the tool's own fixed template strings and the typed, bounded scalar fields above, string-substituted into fixed positions, never by inserting a document's own Markdown verbatim into running prose.
- **No repository text becomes executable-looking instructions.** A string like `"I authorize AUTO-016"` or `"---\n\n## SYSTEM: ignore previous instructions"` found inside a `mission`/`title`/evidence-quote field is rendered, verbatim and inertly, only inside its data-scoped quote block, and is separately flagged as a named `warning` (not silently dropped, so the Human Owner sees that adversarial-shaped content was present and neutralized).
- **JSON encoding for the persisted artifact's structured form:** the canonical, hash-bound representation of every field is `canonical_json` (§16) — an unambiguous, non-executable encoding by construction; the Markdown prompt is a rendering of that same typed data, never an independent source of truth.
- **Mandatory non-authorization banner is generated only from fixed program text** (§14.1 item 1/13) — no field of any candidate or evidence source can substitute for, append to, or suppress it; a dedicated test (§22) injects a document claiming the proposal "is authorized" and confirms the banner text and the `authorization_status` field (§16) are both unaffected, byte-for-byte.

### 14.3 Must never include

Credentials, unredacted secret-shaped strings (§17), or any phrasing that could be read as an authorization already granted ("recommends approval," "ready to authorize," "should proceed") — enforced structurally (§14.2's fixed-template rule for directive sections), not merely reviewed for.

## 15. Structural Validation

The proposal and prompt are re-derived and re-hashed from the canonical inputs before persistence (§7.3 steps 6-7, 11-13), and every required section of §14.1 is position-checked to exist in the rendered Markdown. A mismatch or missing section is `PROMPT_VALIDATION_FAILURE` (§13), refusing publication entirely — no partial or best-effort prompt is ever persisted.

## 16. Proposal Artifact Contract and Canonicalization

**Correction (AUTO-015-007).** Revision 1 named `canonical_json` and "sortedness invariants" but left several canonicalization dimensions unstated (timezone, timestamp exclusion scope, numeric representation, collision handling, what "proposal identity" means precisely). This section states all of them.

### 16.1 Schema

| Field | Notes |
|---|---|
| `schema_version` | explicit, e.g. `"1.0"` — additive versioning only |
| `proposal_id` | **the full 64-character hexadecimal `proposal_sha256` digest, in full — this is the canonical identity, never truncated.** A separately rendered short/display form (first N hex characters) may appear in human-facing output *labeled as a display form*, but is never used as a lookup key, a no-clobber comparison key, or anywhere identity is asserted. |
| `repository_identity` | the `RepositoryIdentity` record of §7.1, embedded in full |
| `predecessor_stage_id` | the exact validated `--predecessor` Stage ID; identifies the proposal target only and is never a successor selection |
| `predecessor_registry_evidence` | Registry path, status, hash, and canonical evidence reference proving the predecessor exists and is `COMPLETE` |
| `predecessor_completion_evidence` | ordered completion-report/evidence references and hashes for the predecessor |
| `predecessor_status_reconciliation` | typed result covering Registry, Task Queue, mirrors, and the reconciled `COMPLETE` status |
| `evidence_manifest` | ordered list of `{path, sha256, size}` for every authoritative document actually read (§8), in **canonical evidence-ordering** (§16.2) |
| `normalized_evidence_hash` | one hash over the whole sorted evidence manifest |
| `candidate_list` | full typed candidates (§10), each with its computed `lifecycle_status` and reasons, in **canonical candidate-ordering** (§16.2) |
| `eligibility_decisions` | per-candidate verdict plus the exact rule from §11 that produced it |
| `blockers` | per-candidate, re-resolved live, in **canonical blocker-ordering** (§16.2) |
| `outcome` | the two-level structure of §12 |
| `generated_prompt` | the full rendered Markdown (§14), embedded verbatim, not merely referenced — see §17.1 for why this is embedded rather than a separate file |
| `prompt_hash` | SHA-256 of the rendered prompt's encoded bytes |
| `proposal_hash` (a.k.a. `proposal_sha256`) | SHA-256 of the full canonical proposal payload, excluding this field itself and excluding `generation_metadata` (§16.3) |
| `warnings` | in **canonical warning-ordering** (§16.2); e.g., a redacted secret was found; an authorization-shaped string was found in a quoted/historical span and rendered only in a data-scoped location |
| `errors` | in **canonical error-ordering** (§16.2); populated only on the `FAILURE` branch of §12 |
| `authorization_status` | fixed `Literal["NOT_AUTHORIZED"]` — never a variable field |
| `human_owner_action_required` | fixed, non-templated string directing the Human Owner to review, then separately register/authorize any successor |
| `generation_metadata` | a **separate, unhashed envelope** (§16.3) carrying wall-clock timestamp and any other non-canonical, purely informational fields |

### 16.2 Canonicalization rules (complete)

- **Encoding:** UTF-8 throughout; a decode failure on any authoritative source is `AUTHORITATIVE_SOURCE_MISSING` (that source could not be read as text at all).
- **Unicode normalization form:** NFC, applied at parse time (§14.2) and asserted, never silently re-applied at hash time — reuses `canonicalize_json_value`'s existing NFC + surrogate-rejection discipline (`prompt/models.py:77-113`).
- **Line-ending normalization:** all authoritative source content is normalized to `\n` before hashing/parsing; a source containing `\r` fails validation rather than being silently rewritten (mirrors the existing `content must use LF line endings only` rule in `prompt/models.py:145-146`).
- **Trailing-newline policy:** every normalized text field ends with exactly one final newline, mirroring `prompt/models.py:147-148`'s existing rule.
- **Key ordering:** `canonical_json`'s `sort_keys=True` (`prompt/renderer.py:69-80`), reused verbatim.
- **List ordering:** every list-valued field carries its own explicit, named sortedness invariant (below), enforced at the model layer, since `canonical_json` does not infer ordering on its own.
  - **Evidence ordering:** sorted by `path` (byte-wise on the UTF-8 encoding), ascending.
  - **Candidate ordering:** sorted by `candidate_id`, ascending.
  - **Blocker ordering (proposal-level `blockers` field, §16.1):** sorted by `blocker_id`, ascending, then by `candidate_id` for candidates sharing a blocker.
  - **Warning ordering / error ordering:** sorted by `(code, path_or_candidate_id)` tuple, ascending — never insertion order, which would make canonical output depend on read-pass timing.
  - **Candidate sub-list ordering (§10.1, applied within each candidate before that candidate is itself placed in candidate order):**
    - `dependencies`: sorted by `dependency_id`, ascending.
    - `blockers` (the per-candidate list): sorted by `blocker_id`, ascending — same key as the proposal-level blocker ordering above, applied per candidate.
    - `evidence_references`: sorted by `path`, ascending (same byte-wise rule as the top-level evidence manifest).
    - `required_owner_decisions`: sorted lexicographically as plain strings, ascending — this is the one list field with no natural identifier key, so the normalized string value itself is the sort key.
  These four sub-list rules close the gap between this section's opening claim ("every list-valued field carries its own explicit, named sortedness invariant") and the fields actually enumerated — every `list[...]`-typed field in §10.1 and §16.1 now has a stated canonical order.
- **Locale-independent parsing:** every date/number/enum parse uses a fixed, locale-independent format (`en_US`-equivalent digit/decimal conventions only, never `locale.setlocale`-dependent parsing) — this applies to Git-output parsing (`GitClient` output format is fixed by `git`'s own porcelain modes, not display-locale-dependent) and to any numeric field in a document.
- **Timezone policy:** every timestamp that does appear anywhere (only in `generation_metadata`, §16.3) is UTC, ISO-8601, with an explicit `Z` suffix — never a local/naive timestamp.
- **Timestamp exclusion from canonical hashes:** wall-clock time is **excluded from every hashed field**, full stop — it exists only in `generation_metadata` (§16.3), never inside `canonical_payload_bytes`'s input, mirroring `prompt/models.py`'s existing payload model, which has no datetime branch at all (`canonicalize_json_value` rejects `datetime` outright, `prompt/models.py:77-113`, confirmed by direct inspection).
- **Absolute-path normalization:** every path in the evidence manifest is stored **relative to `resolved_repository_root`** (§7.1), never as an absolute path — this makes the manifest, and therefore the proposal hash, independent of where the repository happens to be checked out on a given machine.
- **Filesystem traversal sorting:** any directory listing performed while resolving authoritative sources is sorted by name before use, never trusted in raw `readdir` order (which is filesystem/OS-dependent).
- **Git-output parsing independent of display locale:** `GitClient` invocations always run with a fixed `LC_ALL=C`/`LANG=C`-equivalent environment override (extending the existing `GIT_OPTIONAL_LOCKS=0` discipline at `client.py:33-36`) so porcelain output format cannot vary by the invoking operator's shell locale.
- **Canonical JSON separators:** `(",", ":")`, no whitespace — `canonical_json`'s existing behavior (`renderer.py:77`; `sort_keys=True` is the adjacent `renderer.py:76`), reused verbatim.
- **Numeric representation:** integers only, 64-bit range-checked (`canonicalize_json_value`'s existing `_INT64_MIN`/`_INT64_MAX` check, `prompt/models.py:60-61, 88-92`); floats are rejected outright, never coerced — every numeric field in this contract's schema (`size`, `ahead`, `behind`, `content_hash` as a hex string not a number) is deliberately chosen to fit this constraint.
- **Schema versioning:** `schema_version` on both the candidate model (§10.1) and the proposal artifact (this section) are independent, additive-only version strings; a reader encountering a higher minor version than it supports still attempts a best-effort *read* for display purposes only, but never uses an unrecognized-version document as an authoritative input to eligibility computation (falls back to `AUTHORITATIVE_SOURCE_MISSING`/`MALFORMED_CANDIDATE` per §10.2/§13 as appropriate).
- **Collision behavior:** a full-digest collision (two different canonical payloads producing the same `proposal_sha256`) is treated as a **hard failure** (`PUBLICATION_CONFLICT`, but flagged with a distinct, more severe internal marker than an ordinary same-ID-different-content case, since a true SHA-256 collision would itself be a cryptographic anomaly worth surfacing loudly) rather than silently resolved by "last write wins."

### 16.3 `generation_metadata` envelope

A separate, explicitly non-canonical structure alongside the hashed payload, carrying: `generated_at` (UTC ISO-8601 timestamp), `tool_version` (the implementation's own package version, for the identity check in §4 item 6), and any other purely informational, non-hash-bound field a future implementation needs. **Nothing in this envelope may ever be read back into an eligibility, hashing, or identity decision** — it exists for human/operational convenience only.

### 16.4 Load-time re-verification

On load, the artifact is never trusted at rest: every hash is recomputed from the embedded evidence manifest and candidate data and compared byte-for-byte before the artifact is treated as valid, mirroring `prompt/store.py`'s existing recompute-and-compare discipline on `load()`. A `lifecycle_status`/`outcome_class`/`result_variant`/`failure_code` value outside its declared enum at load time is a validation failure (`PROMPT_VALIDATION_FAILURE`), never coerced to a nearest-known value.

## 17. Write Authority and Artifact Publication Protocol

**Correction (AUTO-015-008).** Revision 1's §14 named the right primitives (atomic write, no-clobber, path confinement, symlink rejection) but left restart/recovery, concurrency, and the "hardlink as a universal assumption" problem unaddressed — verified: `prompt/store.py`'s own existing mechanism *does* use hardlink (`os.link`, `store.py:158, 167`), which only works within a single filesystem and is not a general-purpose atomic-publish primitive across arbitrary root/temp-directory placements. This section is the complete protocol.

### 17.1 Single canonical artifact strategy

**The proposal artifact is one file.** The rendered prompt is embedded verbatim inside it (`generated_prompt`, §16.1) rather than published as a second, separate file. This is a deliberate choice to eliminate the torn-pair risk a two-file (manifest + prompt) strategy would otherwise require solving with its own two-phase-commit protocol. If a future, separately-authorized revision of AUTO-015 wants a second, human-readable, prompt-only file for convenience (e.g., to open directly in an editor), that is an additive, explicitly-scoped extension requiring its own manifest-first, two-phase commit design (write manifest declaring the intended pair → write both files → atomically finalize by renaming the manifest into place last) — not assumed here, and not part of the MVP surface (§20).

### 17.2 Protocol

- **Allowed root type:** the external repository-scoped directory
  `~/.ai-workflow-engine/successor-proposals/<repository-id>/`, which must resolve to a location
  **outside** every authoritative governance path (§8) and outside `resolved_repository_root`
  (§7.1) entirely — reusing `prompt/store.py`'s existing `_reject_repository_containment` check
  (`store.py:66-72`) as the enforcement mechanism.
- **Root ownership and permissions:** the root and every file within it use ordinary, non-executable permissions (files `0o600`, directories `0o700`) — no code path grants broader permissions than needed to read the configured documents and write the configured artifact root.
- **No-follow / symlink rejection:** the root itself, and every path component under it used during publication, is rejected if any component is a symlink — `SYMLINK_POLICY_VIOLATION`.
- **Root identity pinning:** the resolved root path is captured once at the start of the invocation (alongside §7's repository-identity snapshot) and re-verified (still exists, still resolves to the same path, still not a symlink) immediately before the atomic publish step — a root that changed underneath the invocation is `PATH_ESCAPE`, fail closed.
- **Temporary file location:** inside the same artifact root (never system `/tmp` or any other filesystem), so the atomic-publish step below can rely on same-filesystem semantics.
- **Write + flush + fsync:** the temp file is written with `O_CREAT | O_EXCL | O_WRONLY`, `fsync`'d before any rename/link attempt (reusing `prompt/store.py`'s existing `_create_temp`/`fsync` pattern, `store.py:92-111`).
- **Parent-directory fsync:** the artifact root directory itself is fsync'd after the atomic operation completes, where the platform supports directory fsync (reusing `store.py:114-124`'s existing `_fsync_directory`).
- **Atomic publication method: `os.rename`, not hardlink, is the default and only method AUTO-015 relies on.** Because the temp file and the final path are both within the same artifact root (guaranteed by the temp-file-location rule above), a same-filesystem rename is always available and is atomic on every POSIX filesystem this repository targets — this removes the cross-filesystem fragility that made hardlink necessary in `prompt/store.py`'s original design (which stages temp files in a location not guaranteed to share a filesystem with its destination). `prompt/store.py`'s hardlink-plus-byte-compare pattern is not assumed as a universal primitive here; it is noted only as prior art for the no-clobber-collision-handling idea below, not reused mechanically.
- **No-clobber semantics:** `os.rename` onto an existing path is *not* used directly (it would silently overwrite); instead, publication first checks whether a file already exists at the content-addressed final path.
  - **Same-ID, same-content (idempotent):** if a file already exists at the target path, its content is read and compared byte-for-byte against the about-to-be-published content; if identical, publication is a no-op success (the existing artifact already satisfies this invocation) — no rename is attempted, no error.
  - **Same-ID, different-content (conflict):** since `proposal_id` is the full `proposal_sha256` digest and the digest is computed over the canonical payload, two different payloads cannot legitimately produce the same ID except via the collision case already addressed in §16.2 — this path is therefore only reachable by a corrupted/hand-edited file already at that address, and is `PUBLICATION_CONFLICT`, refusing to overwrite.
- **Multi-file artifact strategy:** not applicable under §17.1's single-file design; the manifest-first two-phase design is documented only as a future extension point, not built or assumed today.
- **Recovery from partial publication / orphan temp files:** because the only state transition at publish time is "temp file fsync'd" → "atomic rename," there is no window in which a *partially written* file is visible at the final path — the final path either doesn't exist yet or holds a complete, fsync'd file. An orphan temp file (left behind by a crash between temp-write and rename) is inert: it lives at a distinct, namespaced temp filename (never the final content-addressed name), is never mistaken for a completed artifact by any reader, and a future implementation may add opportunistic cleanup of stale temp files on startup as a housekeeping convenience — not a correctness requirement.
- **Restart reconciliation:** because every invocation is stateless and idempotent by content-addressing (§18), there is no "resume" concept to reconcile — a restarted invocation over the same evidence either finds the prior artifact already published (no-op success) or, if evidence changed, produces a new, distinctly-addressed artifact. No workflow-style resume/reconciliation logic (unlike `agentos_workflow`'s stateful runtime) is needed or built.
- **Lock policy:** no OS-level lock is taken (§18), consistent with the statelessness argument there; see concurrency handling immediately below for why this is still safe.
- **Concurrent identical invocation:** two processes racing to publish the same content-addressed artifact both attempt the atomic rename; exactly one succeeds, the other's rename fails with `FileExistsError`, which is then handled exactly like the no-clobber same-content-check above (read-and-compare) — both processes observe success, because the content is in fact identical.
- **Concurrent conflicting invocation:** not reachable under normal operation, because two processes observing genuinely different evidence produce two distinctly-addressed artifacts (different `proposal_id`), never contending for the same path; the only way to reach a same-ID conflict is the corruption case above, already handled as `PUBLICATION_CONFLICT`.
- **Root change between invocations:** if the Human-Owner-configured artifact root itself changes between two invocations, they simply publish to two different roots — no cross-root reconciliation is attempted or needed.
- **Post-publication hash verification:** immediately after the atomic rename succeeds, the published file is re-read and its hash re-derived and compared against `proposal_sha256` before the invocation reports success — catching any last-instant filesystem-level corruption between write and the success report.

## 18. Idempotency, Resume, and Concurrency

- **Repeated identical invocation** (unchanged evidence) must produce a byte-identical proposal artifact and prompt — this is a hard determinism requirement (§16), not merely a convenience.
- **Proposal identity** is content-derived (`proposal_id` = full `proposal_sha256`, §16.1), never random or clock-derived, so identical inputs always address the same artifact.
- **Duplicate prevention:** a second invocation over unchanged inputs recognizes the existing artifact (via its content-derived address, §17.2's idempotent no-clobber path) rather than writing a second, functionally-identical file with a different name.
- **Crash before artifact publication:** since every read is side-effect-free and the write is atomic (§17.2), a crash before the atomic rename leaves the repository and any prior artifact completely unaffected — there is nothing to reconcile, unlike `agentos_workflow`'s stateful, multi-step resumable runtime workflows.
- **Crash after publication:** the artifact is either fully present (atomic rename completed, hash re-verified) or fully absent — no partial-state detection logic is needed.
- **No duplicated side effects** are possible because AUTO-015 performs at most one side effect (the artifact write) per invocation, and that side effect is itself idempotent by content-addressing.
- **Lock behavior:** AUTO-015 takes no OS-level lock of its own (unlike `agentos_workflow.orchestrator.lock`'s per-target-repository lock), since it mutates nothing lock-worthy; concurrent invocations may run safely in parallel as long as each performs a single, internally-consistent read pass, per §7's snapshot protocol and §17.2's concurrency handling.
- **Baseline drift / stale input invalidation:** handled fully by §7's snapshot protocol — a single, internally consistent final snapshot is validated before finalizing, and any drift is `INPUT_DRIFT`, never a silently torn read.
- **Concurrent invocation:** two simultaneous invocations against the same unchanged evidence converge on the same content-addressed artifact (§17.2); two invocations that observe genuinely different evidence produce two distinct, separately addressed artifacts — never a corrupted merge of the two.

## 19. Architecture — Option A resolved by DEC-001

**Correction (AUTO-015-001).** Revision 1 asserted a single answer while admitting a conflict with
the decision-template wording and proposed an impermissible cross-package redaction import. The
independent review confirmed the package-boundary rule. DEC-001 resolves the conflict to Option A;
the rejected Option B is retained below only for audit traceability and is not implementable.

### 19.1 Selected architecture — Core Engine Planning Service

```text
workflowctl (src/ai_workflow_engine/cli.py)
  → new Typer subcommand group, following the existing `prompt_app` pattern
    (cli.py:376-379) and the existing check-*/verify command pattern (cli.py:287-375)
  → successor_planning.propose(...)   # new module, src/ai_workflow_engine/successor_planning/
      → governance readers (reuses governance.parser / governance.registry unmodified)
      → Git/repository-identity reader (reuses src/ai_workflow_engine/git/client.py,
        git/validators.py unmodified)
      → handover reader (new, additive)
      → eligibility policy (new)
      → candidate catalog reader (new)
      → prompt renderer (new, reuses prompt/renderer.py's canonical_json/hashing
        primitives directly — same package, no import boundary crossed)
      → artifact store (new, reuses prompt/store.py's _reject_repository_containment
        and atomic-write *pattern*, adapted per §17)
      → secret-redaction utility (NEW, isolated, defined in this package — see below)
```

- **Dependency direction:** `successor_planning/*` depends only on other `src/ai_workflow_engine/*` modules. **Zero dependency on `agentos_workflow/*`.**
- **Entry point:** a new subcommand group on the existing `workflowctl` CLI.
- **Affected packages:** one new subpackage (`src/ai_workflow_engine/successor_planning/`); one small, additive change to `src/ai_workflow_engine/cli.py`.
- **Advantages:** zero cross-package dependency — fully compliant with `ARCHITECTURE.md` §4's existing rule with **no new exception required at all**, unlike Option B; a direct, already-proven data path to this repository's own governance documents via `governance.parser`/`governance.registry` (verified: zero production reads of `TASK_QUEUE.md`/`STAGE_REGISTRY.md`/`DECISION_LOG.md`/`PROJECT_STATE.md` exist anywhere in `agentos_workflow/*.py`, while `governance/*` already parses exactly these); direct reuse, in the same package, of `prompt/renderer.py`'s `canonical_json` and `prompt/models.py`'s `CanonicalGitStatus`/NFC/int64 primitives without an import-boundary question; consistent with `workflowctl`'s existing stated purpose ("read-only deterministic governance gates for AI-assisted development," `cli.py:68`).
- **Risks:** `workflowctl` gains a materially larger subcommand surface than its current governance-gate framing, a scope-creep risk mitigated by keeping the new commands in a clearly separate, clearly named subcommand group (mirroring how `prompt_app` is already namespaced away from `check-*`); no existing secret-redaction primitive exists in `src/ai_workflow_engine/` (verified: only an unrelated environment-variable allowlist exists, `agents/runner.py:30, 96-97` — not a text-content redaction primitive), so this option requires **defining a new, narrowly-scoped core redaction utility** (e.g. `successor_planning/redaction.py`), explicitly listed in the allowlist (§20), rather than importing `agentos_workflow.skills.redact_secrets`.
- **Test impact:** new test files under `tests/` (this repository's existing top-level convention, not `agentos_workflow/tests/`), reusing `tests/conftest.py`'s real-git-repository fixture convention.
- **Compatibility with existing architecture:** fully compatible; no amendment to `ARCHITECTURE.md` is required.
- **Resolved status:** selected by DEC-001.

### 19.2 Rejected alternative — AgentOS WorkflowService Adapter

```text
workflowctl / agentos CLI entry point
  → agentos_workflow.WorkflowService (or a sibling adapter module)
      → new, narrowly-defined, read-only adapter operation
      → core successor-planning service (same module content Option A would build,
        still located under src/ai_workflow_engine/, still importing nothing from
        agentos_workflow — the dependency is one-directional: agentos_workflow → core
        service, never the reverse)
```

- **Dependency direction:** `agentos_workflow` (the adapter layer only) gains a new dependency on `src/ai_workflow_engine`'s core planning service. The core service itself imports nothing from `agentos_workflow`, so the dependency remains one-directional — but this is itself a **new, currently-unauthorized exception** to `ARCHITECTURE.md` §4's literal "none of the three import from another's internals" rule, broader in shape than the one existing exception (AUTO-002's resume observer is a narrow, read-only, target-repository Git observer — not a general license for `agentos_workflow` to import `src/ai_workflow_engine` modules).
- **Entry point:** a new read-only verb on `WorkflowService`, alongside its existing `APPROVED_OPERATIONS` (verified: a `FORBIDDEN_OPERATIONS` frozenset naming only *mutating* verbs is asserted as a structural invariant in `agentos_workflow/tests/test_service.py:76` — a test-only construct, not an attribute of `WorkflowService` or `service.py` itself, corrected here from a prior revision's inaccurate production-code attribution — so a new read-only verb is not structurally blocked by that test-asserted guard, but structural permission is not the same as architectural fit).
- **Affected packages:** `agentos_workflow/service.py` (new verb), a new adapter module, plus the same core `src/ai_workflow_engine/successor_planning/` service Option A builds regardless.
- **Advantages:** aligns literally with `AUTO-015-DECISION-TEMPLATE.md`'s Architecture row ("WorkflowService → read-only successor-planning operation → ..."), which the Human Owner has already seen — though that document's own explicit disclaimer ("Allowed source files: None authorized by this decision. A separate AUTO-015 contract must name the exact implementation/test paths") means it never committed to this as binding.
- **Risks:** requires a new, currently-unauthorized cross-package exception with no existing precedent of this shape; `WorkflowService.__init__`/`WorkflowConfig` is structurally built around an **externally-named target repository** (verified: `WorkflowConfig.repository_path: Path` / `repository_identity: str`, `agentos_workflow/config/schema.py:69-71`; `RepositoryContext.from_config` populates directly from those fields, `service.py:185-212`) — AUTO-015 has no target repository (it inspects the repository it runs in, per §7), so every call site would need a synthetic, self-referential `WorkflowConfig` pointing back at this engine's own repository, which is semantically confusing, untested territory, and duplicates work `governance/*` already does cleanly.
- **Test impact:** test surface splits across `agentos_workflow/tests/` (adapter) and `tests/` (core service) — more surface area, more places determinism/security invariants must be independently re-verified.
- **Compatibility with existing architecture:** requires a documented, Human-Owner-approved new architectural exception, broader than the existing AUTO-002 precedent.
- **Recommended default:** **no** — offered only because it is what the approved decision template names; every piece of direct code evidence available argues for Option A instead.

### 19.3 Secret detection/redaction under either option

No existing `src/ai_workflow_engine` primitive performs text-content secret redaction (verified above). Under **both** options, AUTO-015's core planning service (which never imports `agentos_workflow` in either option) defines its **own, new, isolated core redaction utility**, added to the allowlist (§20) — it never imports `agentos_workflow.skills.redact_secrets` merely for convenience, and it is not required to exactly replicate that function's pattern table, only its documented design discipline (linear-time matching to avoid ReDoS on untrusted content, lossy/non-reversible redaction, explicit "defense-in-depth, not a guarantee" framing).

Option B is rejected for AUTO-015 and is not an implementation surface. No AgentOS
`WorkflowService` adapter is introduced. The selected implementation surface is only the Option A
surface in §23.

## 20. State Ownership

- No existing `WorkflowState` (the 19-member `agentos_workflow.orchestrator.engine` runtime enum) is owned, read, or changed. That machine governs one execution of the finished engine against an authorized *target repository*; AUTO-015 has no target repository in that sense and no relationship to it.
- No `STAGE_REGISTRY.md` §2 stage-lifecycle state is written. AUTO-015 reads this model's per-stage state (via `governance.registry`) but never transitions a stage's state cell, never registers a row, and never moves anything to `PROPOSED`/`AUTHORIZED`.
- No task-state mutation (`docs/TASK_QUEUE.md`, mirrors) of any kind, and — per §4's correction — AUTO-015 never requires or creates a `Current` task-queue entry for its own invocation.
- No Registry mutation.
- No automatic authorization of any kind, under any condition.
- **Proposal lifecycle status enum.** A future implementation needs its own small, non-authoritative status enum for the proposal artifact itself (e.g., `DRAFT` at generation → immutable once persisted, since the artifact is never edited in place — a new proposal for the same evidence input is a new, distinct artifact, per §18). This is separate from, and carries no authority over, either state machine above.

## 21. Provider Policy

- The canonical operation requires **no AI provider**. Every step in §5 is deterministic given the authoritative evidence.
- No Claude or Codex invocation, under any condition, in the default path.
- Optional future model assistance (e.g., summarizing a candidate's prose more readably) is explicitly **outside this contract's scope** and would require its own separate Human Owner authorization, exactly as `HUMAN_AUTHORIZATION_MODEL.md` §5a required for `ApprovalService`.
- Provider-generated text, if ever introduced, can never determine eligibility, never populate the `recommendation` field's substantive content, and can never satisfy any part of §11's deterministic policy — it could only ever be advisory prose layered on top of an already-deterministic result.

## 22. Security Invariants

Testable invariants, each with a corresponding negative test required in §23:

1. **Repository-relative confinement** — every read/write path resolves inside its respective allowed root; symlinks are rejected, never silently followed (§7.3, §17.2).
2. **No secrets in proposals/prompts** — every string sourced from a governance document passes through the redaction utility (§19.3) before being embedded in any rendered span or persisted field; a redaction event is itself a recorded, visible finding (`warning`), never silently dropped; an unredactable secret-shaped string is `SECRET_DETECTED` (§13).
3. **Untrusted text is data, never control** — enforced structurally per §14.2, not by convention.
4. **Prompt-injection resistance** — an authorization-shaped substring appearing inside quoted/evidence content never changes the computed eligibility outcome or recommendation, and renders only inside a clearly data-scoped location, with a `warning` recorded (§14.2).
5. **No implicit authority** — the proposal schema has no field whose presence or value can be read as authorization, registration, or task mutation; enforced structurally via a strict (`extra="forbid"`) schema, not by convention.
6. **Fail-closed behavior** — every ambiguity/inconsistency case in §12/§13 fails closed by default; there is no silent best-effort fallback.
7. **Canonical input/output hash binding** — every authoritative source document is individually hashed; the aggregate evidence manifest is hashed; the full proposal payload is hashed; the rendered prompt is hashed; every hash is re-derived and compared on load, never trusted at rest (§16.4).
8. **Evidence tampering** — a hand-edited persisted artifact whose embedded hashes no longer match its own re-derivation fails validation outright.
9. **Authority confusion** — the artifact's `authorization_status` field is fixed `Literal["NOT_AUTHORIZED"]` and cannot be set to any other value by any input; a dedicated test injects a document claiming "this proposal is authorized" and confirms the field and banners are unaffected.
10. **Generated-prompt labelling** — the fixed banner (§14.1 item 1) and the machine-checkable `authorization_status` field both appear, are re-verified on load (never merely rendered once and trusted), and cannot be overridden by document content.
11. **Provider non-invocation** — no code path in the default configuration invokes any Model Provider; a structural (AST-level) test asserts no import of a Claude/Codex CLI provider module anywhere in the new package.
12. **Git non-mutation** — no `git` subprocess invocation with a mutating subcommand (`push`/`commit`/`checkout`/`reset`/`clean`/`fetch`/`pull`/`clone`/`merge`/`rebase`) anywhere in the new package's AST; every Git access reuses `git/client.py`'s existing read-only allowlist (§7.1) rather than a new, independently-audited access path.
13. **Governance non-mutation** — a live acceptance run proves every authoritative document's content and mtime are byte-identical before and after invocation.
14. **Size and parse-complexity ceilings** — every document read is bounded by an explicit byte ceiling before parsing (mirroring `agentos_workflow/skills/contract.py`'s `_MAX_CONTRACT_BYTES` pattern); oversized or malformed content fails the read rather than exhausting memory/CPU (§7.3 step 5).
15. **Control-character and Unicode-direction-control rejection** — every repository-sourced scalar field is rejected (not stripped) on any C0/C1 control character or bidirectional-control codepoint (§14.2).
16. **Snapshot-drift detection** — the pre-publication re-snapshot (§7.3 steps 11-13) catches any authoritative input, Git-state, or configuration change since the initial read, and aborts publication rather than persisting a torn read.
17. **Publication idempotency and no-clobber** — repeated identical invocations converge on one artifact; a same-address/different-content collision is refused, never overwritten (§17.2).

## 23. Allowed Future Implementation Surface

**Resolved implementation surface.** DEC-001 fixes Option A. No import of `agentos_workflow` from
`src/ai_workflow_engine/successor_planning/` and no AgentOS adapter is permitted.

### 23.1 Files required under selected Option A

- `src/ai_workflow_engine/successor_planning/__init__.py`
- `src/ai_workflow_engine/successor_planning/models.py` — strict Pydantic models for the Candidate (§10), the proposal artifact (§16), `RepositoryIdentity` (§7.1), and the outcome/failure taxonomy (§12/§13).
- `src/ai_workflow_engine/successor_planning/sources.py` — new, additive readers for `docs/DECISION_LOG.md`, `docs/PROJECT_STATE.md`, completion reports, `docs/workflow-automation/OPEN_QUESTIONS.md`, and the handover manifest, composing (not modifying) the existing `governance.parser`/`governance.registry` functions for `docs/TASK_QUEUE.md`/`STAGE_REGISTRY.md`.
- `src/ai_workflow_engine/successor_planning/catalog.py` — the static authoritative candidate
  catalog reader fixed by DEC-003; it never derives candidates from prose or other documents.
- `src/ai_workflow_engine/successor_planning/eligibility.py` — the deterministic eligibility/blocking policy of §11.
- `src/ai_workflow_engine/successor_planning/redaction.py` — the new, isolated core secret-redaction utility (§19.3).
- `src/ai_workflow_engine/successor_planning/snapshot.py` — the repository-identity and evidence-snapshot protocol (§7).
- `src/ai_workflow_engine/successor_planning/proposal.py` — assembly of the candidate list, recommendation-or-refusal, and the hash-bound artifact.
- `src/ai_workflow_engine/successor_planning/prompt.py` — the governed-prompt renderer/validator (§14), reusing `prompt.renderer.canonical_json` and hashing conventions without extending the closed `WorkflowStage` enum (verified closed, 7-member `Literal`, `src/ai_workflow_engine/models.py:12-20`).
- `src/ai_workflow_engine/successor_planning/store.py` — atomic, no-clobber artifact persistence per §17.

### 23.2 Fixed CLI entry point and invocation

Option A is fixed by DEC-001 and DEC-006. The implementation adds one new, additive Typer
subcommand group in `src/ai_workflow_engine/cli.py`, delegating entirely to
`successor_planning.proposal` with no business logic of its own. The exact command is:

```bash
workflowctl successor-planning propose --config <CONFIG_PATH> --predecessor <STAGE_ID>
```

Optional arguments are `--output console|json` (default `console`) and `--dry-run`.
`--dry-run` performs complete inspection, reconciliation, eligibility evaluation, prompt
rendering, and validation without publishing. Configuration and contract policy values are not
ordinary CLI overrides. No authorization, registration, implementation, provider, Git/task/
workflow mutation, commit, push, PR, or merge options exist.

### 23.3 CLI implementation surface

- `src/ai_workflow_engine/cli.py` — the fixed command above, following the existing
  `prompt_app`/`check-*` command pattern exactly (`cli.py:287-379`). No existing command changes.

### 23.4 Files expected to need NO change (confirmed by direct inspection)

`pyproject.toml` (wheel packaging and `mypy`/`testpaths` config already cover whole-tree paths that include a new subpackage; **no new pytest marker is required** — verified only `live_cli` exists today (`pyproject.toml:67-69`), and unlike `live_cli`'s purpose (excluding tests that spawn a real installed provider CLI), AUTO-015's live acceptance plan (§25) uses only disposable local Git fixtures with no real CLI/network dependency, so it fits inside the default `pytest -q` selection without needing an opt-out marker); `src/ai_workflow_engine/governance/{parser,registry,validators}.py` and `src/ai_workflow_engine/git/{client,validators}.py` (already generic enough to compose without modification); `self-governance.yaml` (no new governance-config field is required for the fixed read-only command; the artifact-root policy is the external repository-scoped policy fixed by DEC-002/DEC-010).

### 23.5 New tests

- `tests/test_successor_planning_eligibility.py`
- `tests/test_successor_planning_proposal.py`
- `tests/test_successor_planning_sources.py`
- `tests/test_successor_planning_snapshot.py` (the §7 protocol, including drift/TOCTOU cases)
- `tests/test_successor_planning_security.py` (negative/adversarial corpus, §22/§25)
- `tests/test_successor_planning_publication.py` (§17's protocol)
- CLI tests appended to the existing `tests/test_cli*.py` convention.

### 23.6 Documentation/report files

`docs/reports/workflow-automation/AUTO-015-completion-report.md`, created only on actual future implementation.

`docs/workflow-automation/successor-planning/AUTO-015-AUTHORITATIVE-CATALOG.yaml` — the typed,
versioned static candidate catalog required by §9/§10.1, already authored (as a governance
document, not source code) as a correction identified by the final independent contract review;
maintaining/revising it at each future planning round is part of this allowlist. It is a required
authoritative source (§8 item 7), snapshot input (§7.3), and evidence-manifest/hash member (§16.1)
once AUTO-015 is implemented. `docs/workflow-automation/successor-planning/AUTO-015-CANDIDATES.md`
is not modified and remains the historical decision-support source it was transcribed from.

### 23.7 Packaging/entry-point changes

None expected beyond the additive Option A CLI command; no `agentos_workflow` package boundary changes.

Every path above has a stated rationale; none is included merely because it may be convenient.

## 24. Explicitly Forbidden Surface

Must remain unchanged unless a direct blocker is independently proved (none is known today, per §27's Deferred Findings):

- `agentos_workflow/orchestrator/engine.py` (`WorkflowState`), `agentos_workflow/orchestrator/lock.py`, `agentos_workflow/orchestrator/state_store.py`.
- `agentos_workflow/implementer.py` (AUTO-013's `ImplementerModeDriver`).
- `agentos_workflow/merge_closeout.py` (AUTO-014's `MergeCloseoutModeDriver`).
- `agentos_workflow/providers/**` and `agentos_workflow/cli_auto.py` (provider runtime and CLI providers).
- `agentos_workflow/approvals.py` (`ApprovalService` semantics).
- `agentos_workflow/service.py` — unchanged; no adapter or new verb is added.
- **`agentos_workflow.skills.redact_secrets` is never imported by `src/ai_workflow_engine/successor_planning/*`** under either option (§19.3) — a dedicated AST-level test (§22 invariant 12's sibling) asserts this.
- `src/ai_workflow_engine/git/**`, `src/ai_workflow_engine/prompt/{models,renderer,validator,store,templates,context}.py` — read for pattern-reuse/direct-primitive-reuse only (§7, §16, §17); none of their content is modified, and the closed `WorkflowStage` enum is not extended.
- `docs/workflow-automation/STAGE_REGISTRY.md`, `docs/TASK_QUEUE.md`, `docs/current_task.md`, `docs/remaining_tasks.md`, `docs/DECISION_LOG.md`, `docs/PROJECT_STATE.md` — read-only at runtime, unconditionally.
- `agentos_dashboard/**` — no relationship to this scope.
- Any deferred defect not proven to directly block AUTO-015 (D-14, D-15, D-16 from AUTO-013; OD-6, OD-7, OD-10, OD-11, OD-12 from `OPEN_QUESTIONS.md`, all confirmed still `Open` as of this revision) — investigated below (§27) and confirmed non-blocking; none may be silently bundled into this stage's implementation.

## 25. Verification Plan

Exact commands, reusing the canonical set AUTO-013/AUTO-014 already established (no new command invented):

- `pytest -q` — full suite; AUTO-015's own tests run inside this default selection (§23.4 — no new marker needed).
- `pytest -q -m live_cli -rs` — existing live-CLI suite must remain unaffected (AUTO-015 adds no provider dependency).
- `ruff check .`
- `black --check .`
- `mypy --strict`
- `pre-commit run --all-files`
- `pip wheel --no-deps` (or `python -m build --no-isolation`) — packaging verification.
- Out-of-tree import check (fresh venv, wheel installed, `cwd` not the repository) — confirms the new `successor_planning` package imports cleanly.
- `workflowctl verify --config self-governance.yaml` — before and after every test/acceptance run, proving AUTO-015's own test suite never perturbs this repository's real governance state.
- `git diff --check`.
- Changed-path allowlist check: `git diff --stat main` (or the equivalent base) restricted to exactly §23's allowed surface for whichever architecture option was selected.
- Proof of no provider invocation: an AST-level structural test (§22 invariant 11) plus a process/environment check during live acceptance confirming no `claude`/`codex` subprocess was ever spawned.
- Proof of no Git/task/Registry/workflow mutation: `git status --porcelain` and a full governance-document byte/mtime comparison, before and after every test and live-acceptance run.
- AST-level check that `agentos_workflow` is never imported by `src/ai_workflow_engine/successor_planning/*`.

## 26. Test Matrix

**Correction (AUTO-015-014).** Expanded to cover every category the independent audit named that Revision 1's matrix omitted.

- `TestDeterministicOutput` — canonical determinism: identical fixture inputs, byte-identical proposal/prompt hashes across repeated runs.
- `TestPredecessorArgumentAndIdentity` — the required `--predecessor` is included in the
  proposal hash and fixed structured prompt metadata, never directive text; omission and malformed
  IDs produce `MISSING_PREDECESSOR` and `INVALID_PREDECESSOR_ID`.
- `TestPredecessorResolution` — unknown, unregistered, incomplete, contradictory, missing-report,
  invalid-evidence, repository-mismatch, and baseline-mismatch predecessors produce respectively
  `PREDECESSOR_NOT_REGISTERED`, `PREDECESSOR_NOT_COMPLETE`,
  `PREDECESSOR_STATUS_CONTRADICTION`, `PREDECESSOR_COMPLETION_EVIDENCE_MISSING`,
  `PREDECESSOR_EVIDENCE_INVALID`, `PREDECESSOR_REPOSITORY_MISMATCH`, and
  `PREDECESSOR_BASELINE_MISMATCH`.
- `TestSuccessfulAUTO014Predecessor` — a valid, current, `COMPLETE` AUTO-014 predecessor with
  reconciled Task Queue/Registry/mirror status and bound completion evidence proceeds to candidate
  evaluation.
- `TestSingleEligibleCandidate` — one eligible candidate → `RECOMMENDATION_READY` with an advisory,
  non-authoritative recommendation per DEC-004.
- `TestMultipleEligibleCandidates` — competing eligible candidates → `MULTIPLE_ELIGIBLE_NO_RECOMMENDATION`, all listed, `recommendation` structurally absent.
- `TestNoEligibleCandidate` — predecessor incomplete or all blocked → `NO_ELIGIBLE_CANDIDATE`.
- `TestInsufficientEvidenceWholeProposal` — every candidate individually insufficient → whole-proposal `INSUFFICIENT_EVIDENCE` variant, distinguished from `NO_ELIGIBLE_CANDIDATE` (§12).
- `TestBlockedCandidate` — an authorization-blocking OD-# correctly excludes a candidate, with the reason recorded.
- `TestStaleEvidence` / `TestContradictoryMirrors` — mismatched queue/registry/mirror fixtures → whole-proposal `MIRROR_CONTRADICTION`, never a silent pick.
- `TestMissingCompletionEvidence` — a claimed-complete predecessor with no corresponding completion report → per-candidate `STALE_COMPLETION_EVIDENCE`.
- `TestDuplicateCandidateSameHash` — repeated identical definition deduplicates silently.
- `TestDuplicateCandidateConflict` — same ID, different hash → `DUPLICATE_CANDIDATE_CONFLICT`, per-candidate exclusion, both definitions listed.
- `TestUnknownCandidateType` — unrecognized `source_kind`/`dependency_type`/`blocker_type` → `UNKNOWN_CANDIDATE_TYPE`.
- `TestUnknownSchemaVersion` — catalog-file-level (whole-proposal `AUTHORITATIVE_SOURCE_MISSING`) and entry-level (per-candidate `MALFORMED_CANDIDATE`), tested separately.
- `TestDependencyCycle` — a cycle marks every participant `blocked` with `DEPENDENCY_CYCLE` and the full cycle named.
- `TestMissingDependency` — an unmet dependency blocks the candidate with the reason named.
- `TestMaliciousContent` / `TestPromptInjection` — adversarial fixture content (fake authorization strings, secret-shaped tokens, path-traversal-shaped fields, symlinked evidence directories) neutralized per §14/§22, with dedicated fixtures for each of: Markdown heading injection, fenced-code-block injection, blockquote injection, raw HTML injection, fake authorization text, nested/recursive instruction-shaped text, Unicode directional controls, control characters, very long fields (bound-exceeding), and prompt-boundary escape attempts (a field crafted to look like it closes a quoted block and opens a new directive section).
- `TestFenceLengthComputation` — a field containing an embedded run of N consecutive backticks produces an outer fence of exactly N+1 backticks (§14.2), verified by asserting the rendered output's outer fence length directly, not merely that no visible breakage occurred.
- `TestFenceLengthCap` — a field engineered to force the outer fence past the 32-backtick cap is rejected as `SECURITY_POLICY_FAILURE` (§14.2, §13), never accommodated with an ever-longer fence.
- `TestSecretRedaction` — a secret-shaped token in a fixture document never appears in any rendered/persisted output; an unredactable one produces `SECRET_DETECTED`.
- `TestPathTraversal` / `TestSymlinkEscape` — hostile path/symlink fixtures rejected outright, including: output-root symlink replacement, parent-directory symlink swap, and root permission failure.
- `TestRepositoryIdentityMismatch` — configured root vs. observed Git root mismatch → `REPOSITORY_IDENTITY_MISMATCH`.
- `TestBranchDrift` / `TestHeadDrift` / `TestDirtyTreeDrift` — each individually detected and reported as `DIRTY_BASELINE` (§7.2).
- `TestCandidateCatalogDrift` / `TestHandoverDrift` / `TestConfigurationDrift` — each a fixture mutated between initial and final snapshot → `INPUT_DRIFT` (§7.3).
- `TestBaselineDriftDuringGeneration` — a simulated mid-read document change is detected and fails closed, never silently accepted.
- `TestOrphanTempFile` — a stale, namespaced temp file from a prior interrupted run is never mistaken for a completed artifact.
- `TestInterruptedPublication` — a simulated crash between temp-file write and atomic rename leaves no partial artifact at the final path.
- `TestPartialArtifactRecovery` — a simulated interruption immediately after fsync but before rename is fully recoverable on the next invocation (no corrupted state).
- `TestRepeatedInvocation` — idempotency: unchanged inputs, run twice, produce the same content-addressed artifact.
- `TestConcurrentIdenticalInvocation` — two simultaneous invocations over unchanged evidence converge on the same artifact without corruption.
- `TestConcurrentConflictingInvocation` — two simultaneous invocations over genuinely different evidence produce two distinct, correctly-addressed artifacts.
- `TestSameContentDuplicatePublication` — republishing identical content is a no-op success.
- `TestConflictingPublication` — a hand-corrupted file at a content-addressed path is detected and refused (`PUBLICATION_CONFLICT`).
- `TestMalformedPrompt` — a corrupted rendered prompt fails structural validation.
- `TestProposalHashMismatch` — a hand-edited persisted artifact fails re-derivation.
- `TestFullDigestIdentity` — `proposal_id` is asserted to be the full 64-character digest in every fixture; a truncated form never appears where identity is asserted.
- `TestTimestampExcludedFromHash` — two artifacts differing only in `generation_metadata.generated_at` hash identically.
- `TestLineEndingNormalization` — a `\r\n` source document is normalized before hashing, never silently accepted with mixed endings.
- `TestLocaleIndependence` — Git/number parsing produces identical results under at least two different `LC_ALL` settings for the invoking shell.
- `TestNoMutationAssertions` — full before/after byte/mtime comparison of every authoritative governance document across a live acceptance run.
- `TestNonAuthoritativeLabeling` — the banner and `authorization_status` field are present, correct, and immune to document-content override.
- `TestStructuralSecurityProperties` — AST-level: no `shell=True`, no direct `subprocess`/`os.system`, no mutating Git subcommand, no provider-module import, no `agentos_workflow` import from `successor_planning/*` (Option A), anywhere in the new package.
- `TestNoProviderCall` — proof of no provider invocation, process-level.
- `TestNoGitMutation` — proof of no mutating Git subcommand invocation, process-level.
- `TestNoTaskRegistryWorkflowMutation` — proof of no task/registry/workflow-state file change, byte-level.

## 27. Live Acceptance Plan

Disposable repositories/fixtures only — never this repository's own live governance state as the subject under test (only as the thing proven untouched, §25).

- **Setup:** a disposable local Git repository under `tmp_path`, containing a realistic governance-doc set (`TASK_QUEUE.md`, `PROJECT_STATE.md`, `current_task.md`, `remaining_tasks.md`, `DECISION_LOG.md`, `OPEN_QUESTIONS.md`, one or more completion reports, a candidate catalog, a `self-governance.yaml`), committed to a clean HEAD — following the existing `tests/conftest.py` fixture convention (real files, real `git init`/`add`/`commit`, no in-memory mocks).
- **Controlled evidence cases:** missing predecessor; malformed predecessor ID; unknown predecessor;
  incomplete predecessor; contradictory Task Queue/Registry status; missing completion report;
  invalid completion evidence; repository mismatch; baseline mismatch; successful AUTO-014
  predecessor; one eligible candidate; competing eligible candidates; no eligible candidate;
  all-candidates-insufficient-evidence; duplicate/conflicting candidate definitions; dependency
  cycle; malicious/prompt-injection-like content; repository-identity mismatch; and mid-run drift.
- **Invocation:** `workflowctl successor-planning propose --config <CONFIG_PATH> --predecessor <STAGE_ID>`
  against the disposable repository as its configured self-governance target; `--dry-run` is tested
  to perform all inspection and validation without publication.
- **Expected artifact:** the correct outcome variant (§12) or failure code (§13) for each fixture state, correctly labeled, correctly hash-bound.
- **Git before/after comparison:** `git status --porcelain` empty; HEAD SHA unchanged; every tracked file's content byte-identical.
- **Governance/task/Registry before/after comparison:** every authoritative document's content and mtime unchanged.
- **Process/environment evidence proving no provider call:** no `claude`/`codex` subprocess spawned during the run (process-list or subprocess-mock assertion).
- **Safe refusal cases:** the stale-mirror, missing-evidence, and drift fixtures produce the correct refusal record, never a crash, never a best-effort guess.
- **Cleanup:** the disposable repository is discarded with the test's `tmp_path`; no persistent state survives the test process.
- **Accepted proof standard:** every one of the above assertions passes with zero exceptions; any single failure is a blocking finding, not a soft warning.

## 28. Newly Discovered Defect Policy

Unchanged from AUTO-013/AUTO-014's established discipline: reproduce first; classify severity; fix only a defect proven to directly block this contract's own authorized scope; smallest possible scope; explicit documentation in the eventual completion report's Deferred Findings section; no bundled deferred work; no silent scope expansion. A defect not directly blocking AUTO-015 is recorded and left unimplemented — no GOV stage is created for it.

**Deferred findings reviewed and confirmed non-blocking for this contract** (re-verified current as of this revision — all five OD-# items remain `Open` in `docs/workflow-automation/OPEN_QUESTIONS.md`):

- **OD-6** (cancellation semantics for an actively-implementing runtime workflow) — concerns `agentos_workflow`'s `CANCELLED`/`FAILED` transition rule. AUTO-015 performs no implementation and owns no runtime transition. Not a blocker.
- **OD-7** (safe re-authorization after baseline-commit drift) — concerns re-binding an `AUTHORIZED` runtime workflow's authorization. AUTO-015 authorizes nothing and binds no baseline in that sense. Not a blocker, though any baseline-drift-shaped signal AUTO-015 happens to observe must be treated as unresolved/hard-stop per §7's own snapshot protocol, never given a more lenient reading locally.
- **OD-10** (five Git/GitHub Skill call sites not forwarding `allowed_environment_variables`) — concerns live `gh` CLI authentication in `GitAgent`/`MergeAgent`. AUTO-015 invokes no Git/GitHub Skill and no `gh` CLI at all. Not a blocker.
- **OD-11** (`stage_contract_hash` prefix disagreement in `agentos_workflow`'s `calculate_contract_hash`/`LocalResumeObserver`) — a distinct hashing function for a distinct purpose (runtime authorization binding). AUTO-015's own hash-binding (§16) uses `prompt.renderer.canonical_json`/SHA-256 directly, a separate code path, with `proposal_id` explicitly defined as the *full* digest (§16.1) — the exact prefix-disagreement class of bug OD-11 describes is structurally avoided here, not merely unaffected. Not a blocker.
- **OD-12** (QA round-numbering collision in `run_repair_loop`) — concerns the repair loop. AUTO-015 runs no repair loop. Not a blocker.
- **D-14, D-15, D-16** (AUTO-013's deferred findings, concerning `RemoteRefEvidence`/`PullRequestEvidence` reconciliation and report sequencing) — concern `agentos_workflow`'s runtime evidence model. Not applicable to AUTO-015's read-only, non-runtime scope.

None of the above may be silently bundled into AUTO-015's implementation even though several are generally "relevant background" per the candidate catalog's own per-candidate fields.

## 29. Resolved Human Owner Decisions and Remaining Prerequisites

DEC-001 through DEC-011 are resolved and recorded in §6.1, and independently recorded in
`docs/DECISION_LOG.md`'s 2026-08-04 entry "Human Owner accepted DEC-001 through DEC-011 for the
proposed AUTO-015 contract," closing the final independent review's finding that these decisions
previously had no corroborating record outside this contract. No resolved decision remains a
blocking contract decision. The following later authorization prerequisites remain, and none of
them authorizes implementation:

1. Architecture-specific file allowlist approval (§23), including confirmation that the forbidden
   surface (§24) remains unchanged, and including the typed candidate catalog
   (`docs/workflow-automation/successor-planning/AUTO-015-AUTHORITATIVE-CATALOG.yaml`, §23.6) now
   authored as part of that allowlist.
2. Acceptance and verification-plan approval (§25–§27).
3. Fresh authorization preflight confirming AUTO-014 remains `COMPLETE`, no conflicting `Current`
   task exists, no AUTO-015 Registry row or implementation branch exists, and no new blocker has
   appeared.
4. Final independent contract review.
5. A separate explicit Human Owner authorization statement required by `STAGE_REGISTRY.md` §3
   rule 3. This contract itself remains non-authorizing.

Branch naming, commit/push/PR/merge permissions, live acceptance environment, and retention
policy remain outside this contract's semantic decision set. They do not grant any authority and
are governed by the later authorization boundary and the fixed stop condition below.

## 30. Implementation Stop Condition

The future implementation must stop after:

- Proposal generation.
- Structural validation (proposal and prompt, §15).
- Artifact publication (atomic, no-clobber, to the Human-Owner-named root, §17).
- Human Owner notification/output (the artifact and prompt are made available for review; no further action is taken by the tool itself).

It must never:

- Select a candidate authoritatively.
- Register a stage in `STAGE_REGISTRY.md`.
- Authorize anything.
- Implement any candidate.
- Start any workflow.
- Require or create a `Current` task-queue entry for its own invocation (§4).
- Commit.
- Push.
- Open a pull request.
- Merge.
- Close out any successor stage.

## 31. Contract Acceptance Criteria

Before the Human Owner may authorize implementation of AUTO-015, all of the following must hold:

1. The exact Option A file allowlist (§23) has been reviewed and approved, with any changes explicitly re-confirmed against §24's forbidden surface.
2. The acceptance plan (§26, §27) and verification plan (§25) are accepted as sufficient.
3. A fresh preflight (per `STAGE_REGISTRY.md` §3 rule 1/4) confirms: AUTO-014 remains `COMPLETE`; no other AUTO stage is active; no other task is `Current`; no AUTO-015 Registry row or implementation branch exists; the working tree is clean except the sanctioned governance-transition edit set; and no blocking OD-# has newly appeared.
4. A final independent contract review confirms this revision closes every item in §6's Correction Index without introducing a new contradiction.
5. The Human Owner records the literal authorization language `STAGE_REGISTRY.md` §3 rule 3 requires ("I authorize AUTO-015" or an equivalent explicit directive) in the stage's task record and Authorization Log.

## 32. Final Authorization Boundary

```text
PROPOSED — NOT AUTHORIZED

This contract does not authorize AUTO-015 implementation.
No production file, test, branch, task state, Registry state, workflow state,
provider invocation, commit, push, pull request, or merge may occur until the
remaining prerequisites in §29 are satisfied and the Human Owner explicitly
authorizes AUTO-015.
```
