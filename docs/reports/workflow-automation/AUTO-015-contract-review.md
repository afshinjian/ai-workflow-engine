# AUTO-015 Contract Review — Independent Multi-Specialist Review Report (Revision 4)

| Field | Value |
|---|---|
| Reviewed contract | `docs/workflow-automation/stage-prompts/AUTO-015.md`, **Revision 4** |
| Contract status | `PROPOSED — NOT AUTHORIZED` |
| Predecessor | AUTO-014 (`COMPLETE`) |
| Review basis | GOV-AUTO-08's Human Owner decision (`AUTO-015-DECISION-TEMPLATE.md`, 2026-08-04); Revision 2 review; Human Owner acceptance of DEC-001 through DEC-011 (now recorded in `docs/DECISION_LOG.md`); final independent contract review (§4a); predecessor reconciliation |
| This review's own authority | None. This report does not authorize, register, or implement anything. |

## 1. Review Scope

This report reviews a **proposed** AUTO-015 stage contract only, now in its fourth revision. No implementation, registration, authorization, branch creation, commit, push, PR, or merge occurred as part of this review, the original contract's drafting, or any remediation pass. The change set for this correction pass is exactly four documentation files: the contract, this report, one new `docs/DECISION_LOG.md` entry, and one new typed candidate-catalog governance document (§4a). No Registry row, task-state transition, workflow-state change, or provider invocation occurred.

**What changed since Revision 1.** An independent Codex audit reviewed Revision 1 and returned a verdict of `NOT READY FOR AUTHORIZATION`, citing eleven findings (AUTO-015-001 through AUTO-015-011). This session, acting as Lead Contract Remediation Architect, verified each finding against the actual repository state (not merely against the audit's own text), corrected the contract, and re-drafted this report. Revision 1's text is superseded, not amended in place — it was never authorized, registered, or acted upon, so no append-only historical record (`STAGE_REGISTRY.md` §3 rule 8) is being altered, only a proposal draft.

## 2. Preflight Evidence (this remediation session)

| Check | Required | Observed | Result |
|---|---|---|---|
| Current branch | `governance/gov-auto-08-successor-scope` | confirmed via `git status --short` / branch context | PASS |
| `HEAD` | `8b183e4c96aa1e9ddb18c16184ed1a1a2521b387` | confirmed via `git rev-parse HEAD` | PASS |
| Working tree (before edits) | clean except the two allowed-file additions | `git status --short` showed only the two untracked allowed files at session start | PASS |
| Current task set | empty | `docs/current_task.md`: "No task is currently active"; `workflowctl check-task-state` reported `0 Current, 49 Done, 6 Planned` | PASS |
| No AUTO-015 Registry row / task / symbol / branch | required | `grep -n "AUTO-015" docs/workflow-automation/STAGE_REGISTRY.md` shows only Authorization Log narrative mentions of the *name* AUTO-015 inside other stages' entries (AUTO-013, AUTO-014, GOV-AUTO-08 closures) — no Registry table row, no branch, no source symbol | PASS |
| Canonical governance checks | pass except explained upstream condition | `workflowctl check-task-state --config self-governance.yaml`: PASS — `0 Current, 49 Done, 6 Planned` | PASS |
| Only the two allowed paths changed | required | see §12 Changed-Path Proof | PASS |

## 3. Documents and Source Inspected (this remediation session)

**Contract-under-review and its own predecessor state:** `docs/workflow-automation/stage-prompts/AUTO-015.md` (Revision 1, read in full before rewriting), `docs/reports/workflow-automation/AUTO-015-contract-review.md` (Revision 1, this file, read in full before rewriting).

**Human Owner decision package:** `docs/workflow-automation/successor-planning/AUTO-015-CANDIDATES.md` (full, including Candidate 4's own risk statement — see §4 AUTO-015-002), `docs/workflow-automation/successor-planning/AUTO-015-DECISION-TEMPLATE.md` (full).

**Governing architecture and policy:** `docs/workflow-automation/ARCHITECTURE.md` (§1 layering, §4 package layout and its "none of the three import from another's internals" rule, §10 the exact scope of the AUTO-002 exception), `docs/workflow-automation/STAGE_REGISTRY.md` (full §3, all nineteen control rules verbatim, confirming no existing symlink/TOCTOU rule exists at the governance-policy layer), `docs/workflow-automation/OPEN_QUESTIONS.md` (OD-6, OD-7, OD-10, OD-11, OD-12, re-verified `Open`).

**Implementation surfaces read (unmodified):** `src/ai_workflow_engine/prompt/{renderer.py,models.py,store.py}` (canonical_json, CanonicalGitStatus, CanonicalTaskSnapshot, `_reject_repository_containment`, the hardlink-based atomic-write pattern, all read line-by-line); `src/ai_workflow_engine/models.py` (the closed 7-member `WorkflowStage` Literal); `src/ai_workflow_engine/git/{client.py,validators.py}` (the existing single-snapshot `check_git`, the read-only Git command allowlist, `GIT_OPTIONAL_LOCKS=0`); `src/ai_workflow_engine/cli.py` (the existing Typer `prompt_app`/`check-*` subcommand pattern used as the Option A entry-point template); `agentos_workflow/service.py`, `agentos_workflow/config/schema.py` (`WorkflowConfig.repository_path`/`repository_identity`, `RepositoryContext.from_config` — confirming `WorkflowService` is target-repository-shaped); `agentos_workflow/skills/__init__.py` (`redact_secrets`, confirmed `agentos_workflow`-only); a full grep of `agentos_workflow/*.py` for production reads of `TASK_QUEUE.md`/`STAGE_REGISTRY.md`/`DECISION_LOG.md`/`PROJECT_STATE.md` (zero hits outside test fixtures and docstrings); a full grep of `src/ai_workflow_engine/` for any existing secret-redaction primitive (none found — only an unrelated environment-variable allowlist in `agents/runner.py`); `pyproject.toml` (confirming only the `live_cli` pytest marker exists today); `self-governance.yaml` (full, confirming its `handover:` block carries no explicit required/optional flag, and cross-referencing `STAGE_REGISTRY.md` rule 16's unconditional handover-check requirement).

**Live tool output consulted:** `workflowctl check-task-state --config self-governance.yaml` (run directly, `0 Current, 49 Done, 6 Planned`).

## 4. Independent Codex Audit — Findings and Disposition

Each finding was independently re-verified against the repository (not accepted on the audit's assertion alone) before being marked resolved.

| Finding | Audit claim | Independent verification | Disposition |
|---|---|---|---|
| **AUTO-015-001** — architecture conflict | Revision 1 asserted `src/ai_workflow_engine/` as settled while admitting a conflict with the decision template's "WorkflowService" wording, and proposed importing `agentos_workflow.skills.redact_secrets`, itself a boundary violation | Confirmed: `ARCHITECTURE.md` §4 states no cross-package internals import exists among the three packages, with the sole exception being AUTO-002's narrow resume-observer carve-out (§10) — not a general license; `WorkflowService`/`WorkflowConfig` (`agentos_workflow/config/schema.py:69-71`, `service.py:185-212`) are confirmed target-repository-shaped; zero production reads of this repository's own governance docs exist anywhere in `agentos_workflow/*.py` | **Resolved.** Revision 2 §19 defines Option A (recommended, zero new exception) and Option B (the decision-template-literal reading, requires a new architectural exception) side by side, with dependency direction, entry point, affected packages, advantages, risks, test impact, and compatibility stated for each, and marks the choice blocking (§29 item 1). The `redact_secrets` import is removed under both options; §19.3 requires a new, isolated core redaction utility instead. |
| **AUTO-015-002** — catalog text prompt injection | Repository-derived title/mission/description text could be spliced into directive prompt sections; no bounded lengths, grammar, or Markdown/HTML disposition were specified | Confirmed as a real gap: Revision 1's §17 stated the principle but not the mechanism. Confirmed `AUTO-015-CANDIDATES.md`'s own Candidate 4 entry already names "report content is attacker-controlled" as a known risk | **Resolved.** Revision 2 §14.2 defines strict typed parsing, bounded lengths per field (§10.1), identifier grammar, control-character rejection, NFC normalization enforcement, explicit Markdown/HTML-as-inert-data disposition, no raw Markdown interpolation into directive prose, canonical-JSON structured encoding, and a mandatory fixed-text-only non-authorization banner. §26 adds a full adversarial test list (headings, fenced code, blockquotes, HTML, fake authorization text, nested instructions, Unicode direction controls, control characters, long fields, prompt-boundary escapes). |
| **AUTO-015-003** — failure/outcome contradictions | The five-value outcome enum (old §8) and the differently-shaped failure-code list (old §16) were never reconciled; the audit's own required vocabulary (`PROPOSAL_READY`, etc.) does not flatten onto either | Confirmed: old §8 and old §16 used different vocabularies for overlapping concepts | **Resolved.** Revision 2 §12 defines an explicit two-level `outcome_class` / `result_variant` structure reconciling the audit's required vocabulary with the fact that `PROPOSAL_READY` is a wrapper, not a peer of the other four. §13 is a single failure-code table with an explicit `scope` column (`whole_proposal` / `per_candidate`) for every code, closing the "define exactly when... " requirement precisely. |
| **AUTO-015-004** — impossible AUTO-015 self-absence entry condition | Old §4 item 6 forbade any AUTO-015 implementation existing, which is impossible once AUTO-015 is itself authorized and running; old §4 item 3's "other than the invocation itself" implied AUTO-015 might need to be its own `Current` task, contradicting its own State Ownership section | Confirmed both defects by direct re-reading of old §4 | **Resolved.** Revision 2 §4 item 3 removes the self-exception entirely by clarifying AUTO-015 is a stateless tool invocation, never a task-queue entry, so no exception is ever needed. Item 6 is replaced with an "unauthorized or unrecognized successor implementation" rule that explicitly permits AUTO-015's own authorized implementation and any separately-authorized candidate, adding a runtime package-identity check (cross-referenced to §22). |
| **AUTO-015-005** — incomplete TOCTOU protocol | Old §15's drift handling was one sentence; symlink swap, file replacement, and the residual-risk boundary were unaddressed | Confirmed: old §15 said only "observe a single, internally consistent snapshot ... or detect the drift." Independently confirmed `src/ai_workflow_engine/git/validators.py::check_git` performs a single point-in-time check with no re-validation window of its own — so AUTO-015 cannot inherit TOCTOU protection from that existing primitive and must define its own | **Resolved.** Revision 2 §7.3 specifies the complete thirteen-step snapshot sequence (resolve root → no-follow open → symlink rejection → stable-identity capture → read → normalize → hash → Git evidence → parse → render → re-stat/re-hash → re-read Git → abort-on-drift → publish-only-after-validation). §7.4 states the threats addressed and, per instruction, an honest residual-risk paragraph rather than a false perfect-isolation claim. |
| **AUTO-015-006** — candidate duplicate/conflict/unknown/dependency rules | The old candidate table had no `schema_version`, no content hash, no ID grammar, and no rule for duplicates, conflicts, unknown enum values, or cycles | Confirmed by direct re-reading of old §7's table | **Resolved.** Revision 2 §10.1 is the complete typed schema (candidate_id grammar, schema_version, content_hash, typed dependencies/blockers). §10.2 states fail-closed rules for every case the audit listed: same-ID/same-hash, same-ID/different-hash, unknown catalog-level vs. entry-level schema version, unknown source_kind/dependency_type/blocker_type, malformed candidates, cyclic dependencies, missing dependencies, and multi-source conflicts. |
| **AUTO-015-007** — canonicalization and proposal-ID ambiguity | `proposal_id` was "first N hex chars of proposal_sha256" without stating that the *full* digest is canonical identity; several canonicalization dimensions (timezone, ordering, numeric representation, collision handling) were unstated | Confirmed: old §9's `proposal_id` definition used a truncated digest as identity, which the audit correctly flags as ambiguous; independently confirmed `canonicalize_json_value` (`prompt/models.py:77-113`) rejects floats/datetimes outright and enforces NFC + int64 range-checking, giving a concrete primitive to cite rather than merely reference | **Resolved.** Revision 2 §16.1 states `proposal_id` is the full 64-character digest, never truncated for identity purposes; a short form may appear only as a labeled display value. §16.2 states every canonicalization dimension the audit listed (encoding, normalization form, line endings, trailing newline, key/list/candidate/blocker/warning/error/evidence ordering, locale independence, timezone, timestamp exclusion, path normalization, traversal sorting, Git-output locale independence, JSON separators, numeric representation, schema versioning, and collision-as-hard-failure). §16.3 isolates timestamps into an explicitly unhashed `generation_metadata` envelope. |
| **AUTO-015-008** — publication race and restart semantics | The publication protocol assumed hardlink as a universal mechanism (verified: `prompt/store.py:158,167` does use `os.link`, which is filesystem-scoped) without addressing restart/recovery/orphan-file/concurrency cases in full | Confirmed the hardlink assumption is real (direct line citation) and that recovery/restart/concurrency detail was thin in old §14/§15 | **Resolved.** Revision 2 §17 specifies `os.rename` (not hardlink) as the default atomic-publication method, justified by the temp file always sharing a filesystem with the destination under the single-artifact-root design (§17.1); explicitly notes `prompt/store.py`'s hardlink pattern is cited as prior art only, not reused mechanically. §17.2 covers every item the audit listed: root type/ownership/permissions, no-follow/symlink rejection, root identity pinning, temp-file location, write+flush+fsync, parent-directory fsync, no-clobber semantics (same-content idempotent, different-content conflict), multi-file strategy (deliberately avoided, §17.1), recovery from partial publication, orphan temp-file handling, restart reconciliation, lock policy, concurrent identical/conflicting invocation, root change between invocations, and post-publication hash verification. |
| **AUTO-015-009** — Git baseline and repository identity ambiguity | Old §6 claimed AUTO-015 "reads no live Git state of its own," which is incorrect for a tool that must bind its own repository's branch/HEAD into its evidence; `self-governance.yaml`'s repository-identity fields were not examined | Confirmed the claim was factually wrong by re-reading old §6 directly; confirmed via direct inspection of `self-governance.yaml` that `project.repository` is the only root/identity field, with no separate `repository_identity` key, and that the `handover:` block carries no explicit required/optional flag (STAGE_REGISTRY.md rule 16 supplies the "required" answer instead) | **Resolved.** Revision 2 §7.1 reverses the incorrect claim and defines the full `RepositoryIdentity` typed binding (configured root, resolved root, configured ID, Git worktree root, branch, HEAD, upstream, ahead/behind, working-tree status, config hash), reusing the existing `CanonicalGitStatus` shape and `GitClient`'s read-only allowlist rather than inventing new Git access. §7.2 states the exact validation rules (root-vs-worktree-root equality, clean-tree/upstream policy, baseline-drift-aborts). §8 item 10 corrects the handover-optionality claim, citing `STAGE_REGISTRY.md` rule 16 directly. |
| **AUTO-015-010** — overbroad Human Owner decision list | Twelve items were listed as blocking without distinguishing what genuinely blocks contract review from what belongs to a later implementation-authorization step | Confirmed by direct re-reading of old §24's twelve items against the instruction's own retained-list of ten categories | **Resolved.** Revision 2 §29 retains nine genuinely blocking items (architecture, artifact root, candidate source policy, exactly-one and multiple-candidate recommendation policy, entry point, publication concurrency, catalog directive-text-policy confirmation, repository-identity-policy confirmation) and explicitly narrows out branch name, commit/push/PR/merge permissions, live acceptance environment, and history/retention (the last two merged into one non-blocking operational default), each with the reasoning for why it no longer blocks. |
| **AUTO-015-011** — stale `48 Done` count | The contract-review report was flagged as containing a stale `48 Done` count that should read `49 Done` | **Independently verified: not present.** A full-text grep of both `docs/reports/workflow-automation/AUTO-015-contract-review.md` (Revision 1) and `docs/workflow-automation/stage-prompts/AUTO-015.md` (Revision 1) for the literal string `"48 Done"` returns zero matches in either file; both already stated `"49 Done"` (Revision 1 of this report, lines 23 and 168), matching the live `workflowctl check-task-state` output re-run during this session (`0 Current, 49 Done, 6 Planned`). The only two occurrences of `"48 Done"` anywhere in the repository are in `docs/reports/workflow-automation/AUTO-014-completion-report.md:46` and `docs/reports/workflow-automation/GOV-AUTO-08-completion-report.md:22` — both are **append-only, already-published completion reports** (`STAGE_REGISTRY.md` §3 rule 8 forbids editing them in place; they are also outside this task's allowed-file surface), correctly reflecting the task count *at the time each was written*, before a subsequent task closed to `Done`. | **Not applicable to either currently-controlled document — no correction was needed or made.** This finding either described a transient state from an earlier draft that had already self-corrected before this remediation session began, or referred to the two historical completion reports, which are out of scope for both this task's allowed-file surface and `STAGE_REGISTRY.md`'s amendment rules. This disposition is recorded explicitly, per instruction, rather than silently passed over. |

## 4a. Final Independent Contract Review — Findings and Disposition (Revision 4)

A subsequent, genuinely external final independent contract review (distinct from the Reviewer
1/Reviewer 2 passes in §7a, which were run by this same lineage) was performed against the actual
repository state — including live `git`/`workflowctl` output, targeted test runs, and direct source
citation verification — and returned **CONTRACT APPROVED WITH REQUIRED CORRECTIONS** /
**READY AFTER ALLOWLIST AND ACCEPTANCE-PLAN APPROVAL**, with five findings. All four correctable
findings are addressed in this revision; the fifth is a documented methodological caveat, not a
contract defect.

| Finding | Severity | Description | Disposition |
|---|---|---|---|
| F1 | High | DEC-001 through DEC-011 had no independent, authoritative record anywhere outside this contract and its own review report — `docs/DECISION_LOG.md` uses a distinct `DD-##` numbering scheme with zero `DEC-0#` entries, and `TASK_QUEUE.md`/`PROJECT_STATE.md`/`OPEN_QUESTIONS.md` were likewise silent. | **Resolved.** A dated `docs/DECISION_LOG.md` entry ("2026-08-04 — Human Owner accepted DEC-001 through DEC-011 for the proposed AUTO-015 contract") now records all eleven decisions verbatim, states they finalize contract semantics only, and restates that AUTO-015 remains unregistered, unauthorized, and unimplemented pending a separate authorization act. `AUTO-015.md` §6.1/§29 now cross-reference this entry. |
| F2 | Medium | §9 claimed `AUTO-015-CANDIDATES.md`'s twelve entries already "conform closely" to the §10.1 typed Candidate Model; independent inspection found a ~21-field narrative-prose schema with no `candidate_id` grammar, `schema_version`, `content_hash`, or typed `dependencies`/`blockers`/`evidence_references` lists — the claim was factually overstated. | **Resolved.** §9 is corrected to withdraw the claim and name `AUTO-015-CANDIDATES.md` as the historical, narrative decision-support document only. A new, separately authored governance document, `docs/workflow-automation/successor-planning/AUTO-015-AUTHORITATIVE-CATALOG.yaml`, is the proposed typed, versioned, hashed static authoritative catalog (§10.1-conformant), transcribed (not copied verbatim) from the historical document, with real SHA-256 `content_hash` values computed via the existing production `prompt/renderer.py:canonical_json` primitive — independently reproducible, not placeholders. `lifecycle_status` is deliberately omitted from every entry, consistent with §10.1's rule that it is computed at read time, never author-set. The catalog is now named in §8 (evidence), §9 (source policy), §23.6 (allowlist), and §29 item 1 (prerequisites). |
| F3 | Low | §19.2 attributed `WorkflowService`'s `FORBIDDEN_OPERATIONS` frozenset to `agentos_workflow/service.py`; it is actually defined only in `agentos_workflow/tests/test_service.py:76`, a test-only construct. | **Resolved.** §19.2's citation is corrected to attribute the frozenset to its actual location and to note it is a test-asserted, not production, guard. The underlying architectural conclusion (Option B is not structurally blocked but is still the wrong fit) is unaffected. |
| F4 | Low | §16.2 cited `renderer.py:76` for the `(",", ":")` canonical JSON separators; the separators are actually on line 77 (`sort_keys=True` is correctly on line 76). | **Resolved.** §16.2 now cites line 77 for the separators and notes line 76 for the adjacent `sort_keys=True`. |
| F5 | Low / informational | The contract's own narrated provenance (Revision 1 → independent Codex audit → Revision 2 → fan-out remediation agents → Reviewer 1/Reviewer 2 → Revision 3) exists only as prose inside these two self-authored documents; no prior revision text or external transcript exists elsewhere in the repository as a separately checkable artifact. | **Not a contract defect — acknowledged.** This report does not claim §7/§7a's prior rounds are externally verifiable; the final independent review evaluated Revision 3 on its own current merits against live repository state, and this revision's corrections rest on that same standard, not on the strength of the self-narrated prior rounds. |

None of the above findings identified an architecture, determinism, TOCTOU, prompt-security, or
publication-protocol defect — the final independent review's own words: "the core mechanism design
is very thorough and sound." Findings F1 and F2 were assessed as blocking a clean, unqualified pass
(hence "approved with required corrections" rather than an unconditional approval); F3–F4 are
citation-accuracy corrections; F5 is a caveat, not a defect.

## 5. Reconciliation Notes

No two corrections above conflict with each other. Three required cross-checks were performed to confirm this:

1. **§19's architecture options vs. §19.3's redaction utility.** Both options were checked to confirm neither one reintroduces an `agentos_workflow` import into `src/ai_workflow_engine/successor_planning/*` — confirmed clean; only Option B's adapter module (which lives in `agentos_workflow/`, not the core service) would ever import in that direction, and only for the adapter's own translation logic, never for redaction.
2. **§7's Git-evidence reversal vs. §11's eligibility rules.** Confirmed that reversing "AUTO-015 reads no Git state" to "AUTO-015 reads its own repository's Git state" does not change any eligibility rule in §11 — Git evidence remains informational/identity-binding only, never a candidate-eligibility input, exactly as Revision 1 intended before the incorrect §6 sentence was written.
3. **§12/§13's outcome/failure split vs. §26's test matrix.** Every outcome variant and failure code introduced in §12/§13 has at least one named test in §26 exercising it, confirmed by a line-by-line cross-check between the two sections during drafting.

## 6. Contract Completeness Matrix (Revision 3)

| Contract Area | Status | Remaining Decision |
|---|---|---|
| Mission and non-authoritative nature (§2–§3) | Complete | None |
| Entry conditions (§4) | Complete, self-absence paradox removed | None |
| Runtime flow (§5) | Complete, updated to reference the snapshot protocol | None |
| Correction index (§6) | New — traceability table | None |
| Repository identity, Git baseline, snapshot protocol (§7) | Complete | None |
| Authoritative evidence model (§8) | Complete, handover corrected to required | None |
| Candidate source policy (§9) | Complete, fixed to static authoritative catalog by DEC-003 | None |
| Candidate model (§10) | Complete, full schema + fail-closed rules | None |
| Eligibility/recommendation policy (§11) | Complete, fixed by DEC-004 and DEC-005 | None |
| Outcome taxonomy (§12) | Complete, two-level structure | None |
| Failure taxonomy (§13) | Complete, scoped table | None |
| Governed prompt / untrusted-content handling (§14) | Complete | None |
| Structural validation (§15) | Complete | None |
| Proposal artifact / canonicalization (§16) | Complete | None |
| Write authority / publication protocol (§17) | Complete | None |
| Idempotency/resume/concurrency (§18) | Complete | None |
| Architecture (§19) | Complete, Option A fixed by DEC-001 | None |
| State ownership (§20) | Complete | None |
| Provider policy (§21) | Complete | None |
| Security invariants (§22) | Complete, expanded to 17 invariants | None |
| Allowed implementation surface (§23) | Complete, Option A-specific and exact | Remaining allowlist approval only |
| Forbidden surface (§24) | Complete | None |
| Verification plan (§25) | Complete | None |
| Test matrix (§26) | Complete, expanded | None |
| Live acceptance plan (§27) | Complete, expanded to 11 fixture states | None |
| Defect policy / deferred findings (§28) | Complete, all five OD-# re-verified `Open` | None |
| Human Owner decisions (§29) | Complete, DEC-001 through DEC-011 accepted | None; later authorization prerequisites remain |
| Stop condition (§30) | Complete | None |
| Acceptance criteria (§31) | Complete, adds a second-review requirement | None |
| Final authorization boundary (§32) | Complete | None |

## 7. Fan-Out Remediation Review

Two read-only research agents ran in parallel during remediation, each independently verifying a non-overlapping set of code- and document-level claims (not merely re-reading the audit's assertions):

**Agent A — Architecture and security-primitive verification.** Independently confirmed, by direct code inspection: `ARCHITECTURE.md`'s layering rule and the narrow scope of the one existing cross-package exception (AUTO-002); `WorkflowConfig`/`WorkflowService`'s target-repository shape; zero production reads of this repository's governance documents anywhere in `agentos_workflow`; `redact_secrets`'s exact location and behavior; the absence of any equivalent primitive in `src/ai_workflow_engine`; `canonical_json`'s exact NFC/sorted-key/no-float/no-datetime behavior with line citations; `_reject_repository_containment` and the hardlink-based atomic-write pattern in `prompt/store.py` with line citations; the closed 7-member `WorkflowStage` Literal's exact members and location.

**Agent B — Governance/evidence-model verification.** Independently confirmed, by direct code and document inspection: `self-governance.yaml`'s exact structure and the absence of a handover required/optional flag (resolved instead by `STAGE_REGISTRY.md` rule 16); all nineteen `STAGE_REGISTRY.md` §3 control rules, confirming no existing symlink/TOCTOU rule; `git/validators.py::check_git`'s single-point-in-time behavior with no re-validation window; `pyproject.toml`'s single existing pytest marker (`live_cli`); the exact and only two locations of the literal string `"48 Done"` in the repository, both in already-published, append-only completion reports outside this task's scope; the current `Open` status and verbatim disposition text of OD-6, OD-7, OD-10, OD-11, OD-12.

No conflicting recommendation was found between the two agents' findings; both were incorporated directly into the corrected contract with line-level citations preserved in this report (§3, §4).

## 7a. Second-Round Independent Re-Review (§31 item 7)

After Revision 2 was drafted, two further, independent, read-only reviewer agents examined the finished document cold — each was given only the file path, not this report's own reasoning — per `AUTO-015.md` §31 item 7's requirement that closure of the Correction Index (§6) be confirmed by a genuinely independent second pass, not self-certified by the session that wrote the corrections.

**Reviewer 1 — architecture and governance.** Independently re-verified every factual claim in §19 against the actual files (`ARCHITECTURE.md` §4's cross-package-import rule and the narrow AUTO-002 exception; `WorkflowConfig`/`WorkflowService`'s target-repository shape; the zero-production-reads finding for `agentos_workflow`; the absence of a redaction primitive in `src/ai_workflow_engine`; the `48 Done` disposition) and confirmed all of them hold. Confirmed `STAGE_REGISTRY.md` §3 rules 1/3/9/16 are correctly preserved and that no section of the contract implicitly requires AUTO-015 to be a `Current` task. Confirmed the nine blocking Human Owner decisions are genuine policy questions, not disguised factual ones, and that the four narrowed-out items do not silently authorize anything §30 forbids. Confirmed this report's own completeness matrix and verdict accurately reflect the contract. **No blocking issues found.** One minor wording note: §29 items 7-9 are listed under "blocking" even though their own text mostly asks for affirmative sign-off on an already-fully-specified mechanism rather than an open choice — accepted as accurate self-description, not a defect requiring a contract change.

**Reviewer 2 — security and determinism.** Traced the outcome/failure taxonomy (§12/§13) through concrete scenarios and confirmed the TOCTOU/snapshot protocol (§7) and publication protocol (§17) are internally coherent, with §7.4's residual-risk statement judged honest rather than overclaiming. Found **three genuine, blocking gaps**, all since corrected in Revision 2 (this session, immediately following the review):

1. **§14.2's Markdown/HTML-escape mechanism was asserted ("appears only inside a quoting construct") without a concrete rule for *how* fencing defeats an embedded backtick run or blank-line-plus-heading escape attempt** — the exact scenario §26's `TestMaliciousContent` names as a test but which §14.2 did not yet structurally guarantee. **Fixed:** §14.2 now specifies a single-JSON-object-per-fenced-block rendering strategy with an explicit fence-length computation rule (outer fence = one more backtick than the longest backtick run in the serialized content, minimum three) and a hard 32-backtick cap beyond which the field is rejected as `SECURITY_POLICY_FAILURE` rather than accommodated. §26 gained two new dedicated tests (`TestFenceLengthComputation`, `TestFenceLengthCap`).
2. **§16.2 claimed every list-valued field carries an explicit sortedness invariant, but four fields from the Candidate Model (§10.1) — `dependencies`, the per-candidate `blockers`, `evidence_references`, `required_owner_decisions` — had no stated order**, contradicting the section's own completeness claim and leaving those fields able to vary in serialization order between otherwise-identical runs (a determinism gap). **Fixed:** §16.2 now states an explicit canonical order for all four.
3. **Three failure codes named by §4 (`unauthorized_successor_implementation_detected`, and two unnamed conditions in items 1 and 3) did not appear in the §13 table at all**, contradicting §13's own closing claim that every code appears in exactly one row. **Fixed:** §13 gained three new rows (`PREDECESSOR_INCOMPLETE`, `CONFLICTING_CURRENT_TASK`, `UNAUTHORIZED_SUCCESSOR_IMPLEMENTATION_DETECTED`, all `whole_proposal` scope), §4 items 1 and 3 now cite them explicitly, and the naming was standardized to `UPPER_SNAKE_CASE` throughout (§4 item 6 previously used lowercase).

Reviewer 2 also flagged six stray cross-references reading "§26 item N" where the content actually lives in §29 (a renumbering artifact from drafting) — **fixed**, all six corrected to §29.

**Reconciliation.** No contradiction existed between the two reviewers' findings — Reviewer 1's scope (architecture/governance/factual claims) and Reviewer 2's scope (security mechanism completeness/determinism/cross-reference accuracy) did not overlap on the same section in a conflicting way. All of Reviewer 2's three blocking findings and the cross-reference slip were corrected directly in `AUTO-015.md` by this session immediately after the review returned; Reviewer 1's single minor note was assessed and consciously left as-is (accurate self-description, not a defect). §31 item 7's acceptance criterion is now satisfied: a genuinely independent second review occurred, found real issues, and those issues are closed.

## 8. Deferred Findings

No new defect was discovered during this remediation requiring a fix outside the two allowed documents. The following pre-existing findings were re-verified (not merely re-cited) against AUTO-015's specific scope and confirmed **not** to block this contract, per `AUTO-015.md` §28:

- OD-6, OD-7, OD-10, OD-11, OD-12 (`docs/workflow-automation/OPEN_QUESTIONS.md`) — all re-confirmed `Open` as of this session, with disposition text matching the contract's own characterization.
- D-14, D-15, D-16 (`docs/reports/workflow-automation/AUTO-013-completion-report.md` §19) — unchanged assessment.

None is implemented, none is silently bundled into AUTO-015's allowed surface, and none is promoted to a new GOV stage by this review.

## 9. Resolved Human Owner Decisions and Predecessor Reconciliation

The Human Owner accepted DEC-001 through DEC-011. `AUTO-015.md` §6.1 records all decisions as
resolved; no resolved decision remains a contract blocker.

- **DEC-001 / DEC-006:** Option A is fixed: the Core Engine Planning Service exposes
  `workflowctl successor-planning propose` and no `WorkflowService` adapter is introduced.
- **DEC-002 / DEC-010:** artifacts use the external repository-scoped root
  `~/.ai-workflow-engine/successor-proposals/<repository-id>/`, where the repository ID is the
  normalized repository name plus the first 12 hex characters of SHA-256 over the canonical,
  credential-free primary remote identity. Proposal filenames use the full proposal digest.
- **DEC-003:** only the static authoritative candidate catalog is read; derived candidates and
  arbitrary prose extraction are out of MVP scope.
- **DEC-004 / DEC-005:** exactly one eligible candidate receives an advisory recommendation;
  multiple eligible candidates are all listed with no recommendation or ranking.
- **DEC-007:** the lock-free immutable content-addressed atomic/no-clobber publication protocol is
  accepted.
- **DEC-008 / DEC-009:** the §14 safe rendering and §7 identity/baseline/snapshot protocols are
  accepted.
- **DEC-011:** the exact command is:
  `workflowctl successor-planning propose --config <CONFIG_PATH> --predecessor <STAGE_ID>`,
  with optional `--output console|json` (default `console`) and `--dry-run`.

The required predecessor argument is now normative. It identifies the completed predecessor only;
it does not select, authorize, register, implement, mutate, or reopen a successor or predecessor.
The predecessor must match `^AUTO-[0-9]{3}$`, exist in the Registry, be `COMPLETE`, reconcile with
the Task Queue and mirrors, have valid completion evidence, and be bound to the current repository
identity and baseline. Its Registry evidence, completion-evidence hashes, reconciliation result,
and Stage ID are included in the evidence manifest and proposal hash. The typed failure codes are:
`MISSING_PREDECESSOR`, `INVALID_PREDECESSOR_ID`, `PREDECESSOR_NOT_REGISTERED`,
`PREDECESSOR_NOT_COMPLETE`, `PREDECESSOR_STATUS_CONTRADICTION`,
`PREDECESSOR_COMPLETION_EVIDENCE_MISSING`, `PREDECESSOR_EVIDENCE_INVALID`,
`PREDECESSOR_REPOSITORY_MISMATCH`, and `PREDECESSOR_BASELINE_MISMATCH`.

## 10. Changed-Path Proof

```text
$ git status --short
(after this correction session's file writes)
 M docs/DECISION_LOG.md
?? docs/reports/workflow-automation/AUTO-015-contract-review.md
?? docs/workflow-automation/stage-prompts/AUTO-015.md
?? docs/workflow-automation/successor-planning/AUTO-015-AUTHORITATIVE-CATALOG.yaml
```

Exactly the four paths named in the final independent review's required corrections: the two
original contract/review documents (Revision 4), one append-only `docs/DECISION_LOG.md` entry
recording DEC-001 through DEC-011, and one new governance document (the typed candidate catalog).
`docs/workflow-automation/successor-planning/AUTO-015-CANDIDATES.md` was **not** modified — it
remains the unmodified historical decision-support document. No production source, test, script,
or configuration schema was created, modified, or deleted; no commit, push, PR, or merge occurred.

## 11. Validation Results

| Check | Result |
|---|---|
| `git status --short` (final reconciliation) | exactly one modified file (`docs/DECISION_LOG.md`, append-only) and three untracked documentation files; no staged changes; no production/test/script/config change |
| `HEAD` | `8b183e4c96aa1e9ddb18c16184ed1a1a2521b387`, unchanged throughout |
| `workflowctl check-task-state --config self-governance.yaml` | PASS — `0 Current, 49 Done, 6 Planned` |
| `workflowctl check-governance --config self-governance.yaml` | PASS — governance mirrors consistent |
| `workflowctl check-handover --config self-governance.yaml --source working-tree` | PASS — 1 manifest record verified |
| `workflowctl verify --config self-governance.yaml` | Git check reports only the documented tolerated local-only `upstream_missing`; task-state, governance, registries, and handover checks PASS |
| `git diff --check` | PASS; clean |
| YAML parse of `AUTO-015-AUTHORITATIVE-CATALOG.yaml` | PASS — 12 candidates, sorted by `candidate_id` ascending, all IDs match the §10.1 grammar, all `title`/`mission` within bounds, `lifecycle_status` absent from every entry, `content_hash` present and 64 hex characters on every entry |
| Production/test/config/script status scan | PASS — no changes outside the four documentation paths above |
| `grep -rn "AUTO-015" docs/workflow-automation/STAGE_REGISTRY.md` | narrative mentions only inside other stages' closure entries; no Registry table row |
| Search for an AUTO-015 branch | none exists |
| `docs/current_task.md` | still shows "No task is currently active" |
| `grep -n "DEC-00" docs/DECISION_LOG.md` | now finds the eleven decisions in the single new 2026-08-04 entry (previously zero matches) |

## 12. Final Verdict

**CONTRACT READY FOR AUTHORIZATION PREFLIGHT**

Revision 4 preserves the resolutions of all eleven independent-audit findings (§4) and additionally
closes all four correctable findings from the subsequent final independent contract review (§4a):
DEC-001 through DEC-011 are now independently recorded in `docs/DECISION_LOG.md`; the overstated
candidate-catalog-conformance claim is withdrawn and replaced by a real, separately authored,
§10.1-conformant typed catalog (`AUTO-015-AUTHORITATIVE-CATALOG.yaml`) with genuine, reproducible
SHA-256 content hashes; and two inaccurate source citations are corrected. The architecture,
determinism, TOCTOU, prompt-security, and publication-protocol design were all found sound by the
final independent review and are unchanged.

The remaining prerequisites are limited to: formal (not merely substantive) allowlist and
acceptance/verification-plan sign-off — both were substantively reviewed and found sound by the
final independent review — a fresh, dated authorization preflight, and a separate, explicit Human
Owner authorization statement ("I authorize AUTO-015" per `STAGE_REGISTRY.md` §3 rule 3). None of
these prerequisites is satisfied by this report, and none constitutes authorization.

AUTO-015 remains unregistered, unauthorized, and unimplemented. This report does not authorize AUTO-015.
