# Project State

Overall condition of `ai-workflow-engine`. This document is a governance mirror
(`governance.project_state` in `self-governance.yaml`) and a `governance.facts` source for the
`version` fact — it is cross-checked against `pyproject.toml` by `workflowctl check-governance`,
so keep the version line's wording exact if you edit it.

Current Version: 1.0.0

## Latest governance activity — T-307 registered as a candidate for authorization

T-307 — Target-bound governed verification evidence and engine execution provenance — was
registered in `docs/TASK_QUEUE.md` on 2026-09-02 as `Planned`. **This is a registration only.** The
Human Owner has not authorized it; no planning, implementation, branch, commit, or push is
permitted until they do, through `scripts/workflow-authorize.sh T-307`. The `Current` set was empty
before the registration and is empty after it, and no successor was promoted.

The task restores target-bound governed review evidence and execution provenance in this engine:
optional named verification bundles in configuration, engine-side execution of the selected argv
commands inside a disposable clone of the exact, clean target HEAD, capture of exact argv and
observed exit codes as engine evidence (never agent self-report), a new `## Verification evidence`
prompt section, and fail-closed engine version/HEAD/worktree-cleanliness/install-mode/package-path
provenance recorded in both the prompt payload and metadata and the agent-run artifact — with
review agents left `read-only` and the `## Identity` block preserved byte-for-byte. It is the next
unused canonical ID in Milestone 3, the family that owns the T-304 sandbox executor and the T-305
agent-run artifact it extends; `T-406` was rejected because Milestone 4 owns controlled commit and
push, which this task does not touch.

**Scope of the registration change itself: governance and task-contract documentation only.**
`docs/TASK_QUEUE.md`, `docs/current_task.md`, `docs/remaining_tasks.md`, this file,
`docs/CHANGELOG.md`, `docs/DECISION_LOG.md`, and the new contract
`docs/t-307-governed-verification-evidence-and-engine-provenance.md` were the only files touched.
No file under `src/`, `tests/`, `scripts/`, `agentos_workflow/`, or `agentos_dashboard/` changed;
`pyproject.toml`, `self-governance.yaml`, the handover pair, and every dependency are unchanged;
and no branch, commit, push, pull request, or merge was performed. The engine version remains
1.0.0.

**Both contract decisions were resolved by the Human Owner on 2026-09-02, and the contract was
amended the same day to Revision 2; none remain open.** OD-1 is stricter than Revision 1 froze and
supersedes it: an `editable` engine installation whose resolved engine worktree is dirty fails
closed on every governed prompt/review/provenance execution, regardless of bundle selection —
governed review evidence must never be produced from uncommitted engine code. `editable` + clean is
permitted; a non-editable distribution is permitted only when version/provenance validation
succeeds. The refusal is bounded to the T-307 governed surface and is not a prohibition on ordinary
development commands. OD-2 confirms the already-frozen bundle design (optional configuration, only
explicitly configured bundles selectable, deterministic pre-execution errors for unknown or
duplicated selections, selection order fixing execution order, no-selection preserving
backward-compatible behaviour, and no consumer-specific hardcoding), settling availability by
configuration rather than by stage. Acceptance criteria 7 and 10 were rewritten accordingly.

The 2026-09-02 amendment also corrected one preparation defect found while reading the
authorization gate: `docs/remaining_tasks.md` carried a second, non-canonical `Status:` line for
T-307 inside its narrative registration section, which `scripts/workflow-authorize.sh` does not
update and which would therefore have gone stale at promotion. The narrative now carries no status
line, leaving the table row as the single parseable source, per the convention already used by the
`AUTO-015 closure`, `DASH-005 implementation update`, and `PLAN-001 closure` sections.

T-307 remains `Planned` and unauthorized; the `Current` set remains empty. A first attempt to run
`scripts/workflow-authorize.sh T-307` on 2026-09-02 was correctly **refused** by the gate with
`branch baseline not met: HEAD differs from origin/main` (exit 6, `EXIT_PRECONDITION`) before any
prompt or file change, because `main` is ahead of `origin/main` and `require_upstream` is `true`.
The local governance baseline must be published to the existing `origin/main` before the gate can
succeed.

## Prior governance activity — PLAN-001 closed

PLAN-001 — Close dashboard requirement-to-stage coverage gaps — was registered and, in the same
written directive, authorized by the Human Owner on 2026-08-10: "PLAN-001 is authorized as a
governance/documentation-only correction to close Dashboard MVP requirement-to-stage ownership
gaps." This authorization explicitly does **not** authorize DASH-007 implementation. The `Current`
set was empty beforehand; predecessor DASH-006 is `COMPLETE`/`Done`.

It corrects `docs/agentos-dashboard/STAGE_REGISTRY.md` §5's Stage→Requirement Map, and the
DASH-007/DASH-008/DASH-010 stage contracts, so every included requirement has exactly one
normative delivery/evidence owner: DR-090, DR-091, EP-07, EP-08, and PG-08 become explicit
DASH-007 responsibilities (a bounded, read-only Governance browser/search surface — fixed document
allowlist, bounded search `q <= 200`, escaping, traversal refusal, zero repository writes; no
database, no search index, no DASH-008 persistence dependency, no governance mutation, no agent or
Git mutation; baseline security owned here, final adversarial reconciliation still DASH-009's);
EP-18 becomes an explicit DASH-008 Build/Acceptance/evidence responsibility rather than a bare
mention inside its `EP-15..EP-18` allowlist range (still the same read-only orchestration endpoint
over the existing DASH-003 parser; no new page); and DR-121, DR-122, and PG-12 become explicit
DASH-010 responsibilities (final cross-page verification of the staleness banner and the
file/line-provenance-with-raw-fallback behavior every page-delivering stage already builds
in-line, plus a bounded read-only Settings/About page explicitly excluding editable config,
persistent preferences, governance editing, repository switching, agent/provider configuration,
secrets, and any authoritative write). DASH-003 remains an infrastructure/foundation contributor
for DR-120..122, never their final normative owner (its own already-`Done` record is unchanged);
DASH-006 is confirmed the sole delivery owner of DR-120 (already correct, unchanged). SC-01..36
final reconciliation stays DASH-009's; DR-900..912 remain deferred/outside MVP. No DASH-011 was
created, no MVP requirement was deferred, and the stage sequence
`DASH-007 → DASH-008 → DASH-009 → DASH-010` is unchanged. Full rationale:
`docs/agentos-dashboard/DECISIONS.md` DD-16; `docs/DECISION_LOG.md`, 2026-08-10 entry.

**Scope: documentation/governance only.** `docs/agentos-dashboard/STAGE_REGISTRY.md` (§5 rewritten
as an explicit per-requirement table, 5.0 → 5.1), `stage-prompts/{DASH-007.md, DASH-008.md,
DASH-010.md}` (each 1.0 → 1.1, contract amendments only — nothing implemented),
`docs/agentos-dashboard/DECISIONS.md` (new DD-16), `docs/agentos-dashboard/CHANGELOG.md` (new
CL-20260810-01), and this repository's own governance mirrors (`docs/TASK_QUEUE.md`,
`docs/current_task.md`, `docs/remaining_tasks.md`, this file, `docs/DECISION_LOG.md`,
`docs/CHANGELOG.md`) were the only files touched. `PRODUCT_SPEC.md`, `API_SPEC.md`, `UI_SPEC.md`,
`MVP_SCOPE.md`, `TEST_STRATEGY.md`, and `MASTER_PLAN.md` were inspected and confirmed to need no
change. No file under `src/`, `tests/`, `agentos_workflow/`, or `agentos_dashboard/` (runtime) was
created, modified, or deleted; no dependency changed; no branch, commit, push, PR, or merge was
performed.

**Closed `Current -> Done` on 2026-08-10** in the same session, following the GOV-AUTO-08/
GOV-AUTO-10 precedent for a documentation-only governance task that authors its own closed final
governance state in one pass, leaving the actual commit for a separate Human Owner review (this
session held no commit authority under its own git-safety bound). The `Current` set is empty
again. This closure authorizes no successor: DASH-007, DASH-008, DASH-009, and DASH-010 all remain
`Planned`/`NOT_STARTED` and explicitly unauthorized. It does not begin, authorize, or start
DASH-007.

## Prior governance activity — AUTO-016 closed

AUTO-016 — Integrated Milestone Automation Runner — was registered and authorized by the Human Owner
on 2026-08-05: "I authorize AUTO-016 implementation under the finalized AUTO-016 contract and its
exact implementation allowlist." Authorization was bounded to the finalized Revision 4 contract
(`docs/workflow-automation/stage-prompts/AUTO-016.md`, SHA-256
`56f6a8f5720f30543f5b0623f5cb52ffa2cc45cbe51be8c5f9b9f5f256b90a7e`) and its exact nineteen-file
implementation allowlist (§23), with the forbidden surface (§24) unchanged. A separate initial-start
session on 2026-08-06 created branch `feature/auto-016-milestone-runner` from `main` at
`4cbd714dd6a83de1b390feac39223e0b8f5d4cbf` and moved the registry state
`AUTHORIZED → IN_PROGRESS`.

AUTO-016 is now **complete and merged**: implemented on that branch and published via pull request
#19, merged into `main` as `b4534c7` on 2026-08-08, with PR #19 CI green. It delivers a supported
`workflowctl milestone-runner` capability under `src/ai_workflow_engine/milestone_runner/` — exactly
nineteen files (fifteen modules plus the four-file `providers/` subpackage) — that executes an
already-authorized stage as a bounded, resumable sequence of typed milestones, runs deterministic
verification, obtains one bounded independent review, and stops at a human commit approval gate that
is disabled by default; with shipped defaults it commits nothing, pushes nothing, opens no pull
request and merges nothing, proved four independent ways. The completion report
(`docs/reports/workflow-automation/AUTO-016-completion-report.md`) records the §25 verification
evidence, the twenty §22 security invariants each held by a named negative test, the ten
prototype-defect regressions, a real wheel build and out-of-tree import, the §27 Tier 1 acceptance
matrix, the GOV-AUTO-11 correction round (F1–F4), and the independent implementation review's three
High blockers (AUTO016-IMPL-001, -002, -003).

Per Human Owner–confirmed external runner evidence (runner run ID
`auto016-20260805T213855Z-7fea75fc`, produced by the local AUTO-016 runner at
`~/.local/share/auto016-runner/` and not stored as a repository artifact): all nine milestones
AUTO-016-M01 … AUTO-016-M09 complete; exactly one bounded Codex review, initially
`AUTO016_REVIEW_BLOCKED`; one correction round; one closure verification closing AUTO016-IMPL-002
and AUTO016-IMPL-003; then one Human Owner-authorized, narrowly bounded remediation whose
out-of-band read-only Codex verification returned `AUTO016-IMPL-001 CLOSED` while consuming no
review budget; final verification 11/11 exit 0; final runner state `READY_FOR_COMMIT_APPROVAL` with
the durable blocking-findings list empty. The single deferred finding `AUTO-016-M08-BLOCKER-001` is
retained as explicitly non-blocking, as are the pre-existing OD-6, OD-7, OD-10, OD-11, OD-12 and
D-14 through D-16. Registry state moved `IN_PROGRESS → COMPLETE`; task status moved
`Current → Done`. No task is currently `Current`. This closure authorizes no successor — AUTO-017
and every later roadmap phase remain unauthorized and `Planned`. The local prototype runner at
`~/.local/share/auto015-runner/` is unchanged by this work and its deprecation and deletion remain
separate acts (DEC-016-006).

## Prior governance activity — GOV-AUTO-10 closed; AUTO-016 contract defined

GOV-AUTO-10 — AUTO-016 Integrated Runner Contract Definition — was registered as the sole Current
task and closed `Current -> Done` on 2026-08-05, after the Human Owner selected **Integrated
Milestone Automation Runner** as the AUTO-016 capability. This documentation-only governance task
produced the finalized AUTO-016 stage contract
(`docs/workflow-automation/stage-prompts/AUTO-016.md`, now Revision 4) — a supported
`workflowctl milestone-runner` capability under `src/ai_workflow_engine/milestone_runner/` that
converts the proven local AUTO-015 prototype runner into a packaged subsystem — together with its
independent review (`docs/reports/workflow-automation/AUTO-016-contract-review.md`, verdict
"CONTRACT READY FOR HUMAN OWNER AUTHORIZATION"). One bounded Codex review returned two blockers
(AUTO016-REV-001, AUTO016-REV-002); both were remediated in one correction round and confirmed
through one closure verification. On the same date the Human Owner ruled the three decisions the
closure had recorded as open — DEC-016-002 (package-owned provider adapters under
`milestone_runner/providers/`), DEC-016-005 (external default plan root; repository-local plans only
at exact contract-allowlisted paths; no repository plan discovery), and DEC-016-006 (prototype
unchanged until live acceptance, deprecated afterwards, never automatically deleted) — and the
rulings were propagated into contract Revision 3 and review-report Revision 3.

**As of that closure, no contract decision remained open and nothing was yet authorized.** Design
rulings are not an implementation authorization: at that point AUTO-016 was still unregistered,
unauthorized, and unimplemented, with no Registry row, task entry, branch, or source, and still
required allowlist sign-off, acceptance-plan approval, a fresh authorization preflight, and the
explicit authorization statement `STAGE_REGISTRY.md` §3 rule 3 requires — each of which the separate
2026-08-05 authorization recorded above then satisfied. The Current task set was empty until that
authorization.

## Prior governance activity — AUTO-015 closed

AUTO-015 — Deterministic Next-Stage Proposal and Governed Prompt Generation — was registered and
authorized by the Human Owner on 2026-08-04 within the finalized Revision 4 contract
(`docs/workflow-automation/stage-prompts/AUTO-015.md`) and its independent final review (verdict
"CONTRACT READY FOR AUTHORIZATION PREFLIGHT"). It was implemented on branch
`feature/auto-015-successor-planning`, committed as `05b819e`, and published via pull request #17,
merged into `main` as `e325f95` on 2026-08-05. The completion report
(`docs/reports/workflow-automation/AUTO-015-completion-report.md`) records full repository-native
verification evidence and a correction round that closed three independent-review High findings
(AUTO015-REV-001, AUTO015-REV-002, AUTO015-REV-003). Per Human Owner–confirmed external runner
evidence (runner run ID `auto015-20260804T060616Z-dedd54c6`, produced outside this repository and
not stored as a repository artifact), a full Codex review and a separate closure verification each
ran exactly once against those same three findings, with all three closed and full verification
11/11 PASS. Registry state moved `IN_PROGRESS → COMPLETE`; task status moved `Current → Done`. No
task is currently `Current`. This closure authorizes no successor — AUTO-016 and every later
roadmap phase remain unauthorized and `Planned`. GOV-AUTO-08 — AUTO-015 Successor Scope and
Contract Definition — was closed `Current → Done` on 2026-08-04 after the Human Owner selected
**Automatic Next-Stage Computation and Prompt Generation** as the proposed basis for AUTO-015.

## Summary

`ai-workflow-engine` is a local orchestration foundation for governed AI-assisted software
development: deterministic read-only inspection, governed prompt generation, non-interactive
agent execution with independent claim verification and a persisted workflow state machine, and
approval-gated controlled commit and push. All four milestones are implemented. See
`docs/milestones.md` for the four-milestone roadmap, `docs/MASTER_ROADMAP.md` for the task-level
plan to 1.0, and `docs/architecture.md` for the pipeline shapes.

## Completed
- PLAN-001 (closed 2026-08-10): governance/documentation-only correction of the Dashboard MVP
  requirement-to-stage ownership gaps — DR-090/091, EP-07/08, PG-08 to DASH-007; EP-18 explicit in
  DASH-008; DR-121/122 final closure and PG-12 to DASH-010. `STAGE_REGISTRY.md` §5 rewritten as an
  explicit per-requirement table. No code changed; DASH-007 remains unauthorized. See "Latest
  governance activity" above and `docs/agentos-dashboard/DECISIONS.md` DD-16.
- GOV-AUTO-03 (closed 2026-07-28): implemented, Human-Owner-approved, and
  closed via scripts/workflow-approve.sh's automatic task closeout (GOV-AUTO-03).

- AUTO-006 (closed 2026-07-28): the eight Git/GitHub Skills of `SKILL_CONTRACTS.md` §5 in
  `agentos_workflow/skills/git_github.py` — `create_commit`, `push_stage_branch`,
  `create_pull_request`, `read_pull_request_state`, `verify_head_sha`, `read_required_checks`,
  `enable_automatic_squash_merge`, `verify_merge_completion` — binding the eight Skill names
  `GitAgent`/`MergeAgent` (AUTO-005) already called against fakes; no Agent code changed. OD-1
  resolved in favor of native GitHub auto-merge (`gh pr merge --auto --squash`). Implemented,
  validated, approved by the Human Owner, committed as
  `d8d356d060076be4ad78afb4d20891004a946204`, and merged into `main` under the same decision.
  Report: `docs/reports/workflow-automation/AUTO-006-completion-report.md`.
- GOV-AUTO-02 (closed 2026-07-28): the local Human task authorization and launch gate in
  `scripts/workflow-authorize.sh`, with exact task naming, fail-closed readiness and baseline
  checks, two Human confirmations, governance-only authorization commits, and optional launch
  through the existing runner only after authorization is committed and verified. Implemented,
  validated, approved by the Human Owner, and committed as
  `d212e4d2dae2cd0a3510c54d7cd098fdfd5da548`. Report:
  `docs/reports/GOV-AUTO-02-completion-report.md`.
- AUTO-005 (closed 2026-07-28): the six AgentOS Workflow Automation Agents in
  `agentos_workflow/agents/` — `PMOAgent`, `ImplementationAgent`, `QAAgent`, `GitAgent`,
  `MergeAgent`, `CloseoutAgent` — each bounded by a capability broker to the Skills and Provider
  roles its own contract lists, none deciding its own workflow-state transition, plus the
  Orchestrator-owned `VALIDATING` sequence and the bounded repair loop. Implemented, validated,
  approved by the Human Owner, committed as `430cbb4`, and merged into `main` under the same
  decision. Report: `docs/reports/workflow-automation/AUTO-005-completion-report.md`.
- AUTO-004 (closed 2026-07-28): the AgentOS Workflow Automation Model Provider layer in
  `agentos_workflow/providers/` — the common `Provider` interface, `ClaudeCLIProvider` and
  `CodexCLIProvider` as subprocess adapters over each target repository's own configured
  executable and timeout, and `MockProvider` as an offline substitute structurally excluded from
  any real authorized workflow. Implemented, validated, approved by the Human Owner, committed as
  `84616d5`, and merged into `main` under the same decision. Report:
  `docs/reports/workflow-automation/AUTO-004-completion-report.md`.
- AUTO-003 (closed 2026-07-27): the deterministic Repository, Contract, Validation, and Reporting
  Skill families in `agentos_workflow/skills/`, committed as `908be94` and merged into `main` via
  `a3b5b0a`.
- AUTO-002 (closed 2026-07-27): orchestrator, 19-state workflow machine, authorization capture,
  append-only persistence, per-repository locking, retry accounting, local resume/evidence
  observation, security-boundary hardening, and regression coverage under `agentos_workflow/`.
  The Human Owner accepted the implementation for closure without another independent review
  after the approved remediation and configured gates passed.
- AUTO-001 (closed 2026-07-24): AgentOS Workflow Automation architecture and governance
  contracts — the complete documentation set under `docs/workflow-automation/`, merged into
  `main` via PR #3 (`191f600`). Formally flipped to `Done` per Human Owner review (see
  `docs/DECISION_LOG.md`, 2026-07-24 entry).
- DASH-001 (closed 2026-07-23): AgentOS Dashboard planning foundation and contracts — the
  complete documentation set under `docs/agentos-dashboard/`, merged into `main` via PR #1
  (`5f82996`). Formally flipped to `Done` as an AUTO-001 precondition (see
  `docs/DECISION_LOG.md`, 2026-07-23 AUTO-001 entry).
- Milestone 1 (v0.1.0, released 2026-07-16): deterministic read-only Git inspection, governance
  and task-state mirror checks, source-aware handover checksum verification, protected paths,
  structured CLI/JSON results.
- Milestone 2 (approved; committed locally 2026-07-17): governed prompt generation — deterministic,
  canonically-hashed rendering/validation/atomic storage for all seven workflow stages, plus the
  `workflowctl prompt <stage>` CLI surface. Passed three independent fresh implementation
  reviews; two real defects found and fixed along the way (see `docs/DECISION_LOG.md`).
- GOV-1 (closed 2026-07-17): the self-governance layer — this document and its siblings —
  validated end-to-end in `docs/VALIDATION_REPORT.md` and formally closed via task T-101.
- Milestone 3 (v0.2.0, 2026-07-18): non-interactive agent execution — a persisted, hash-chained
  workflow state machine (`workflowctl state`), the `agents` config section + strict report
  contract, a snapshot-sandbox runner with hard timeouts and isolation, and independent claim
  verification with tamper-evident run artifacts (`workflowctl agent run`). Each task (T-301..
  T-306) passed independent review; the normative plan is `docs/milestone-3-plan.md` and the
  demonstration is `docs/MILESTONE_3_VALIDATION.md`.
- Milestone 4 (released in v1.0.0, 2026-07-18): controlled commit and push — a separate typed
  writable-Git surface (`GitWriter`, read-only `GitClient` untouched), per-invocation human
  approval artifacts, and the `workflowctl commit` / `push` / `apply-patch` gates. Each task
  (T-401..T-404) passed independent review (the plan review took two rounds); normative plan
  `docs/milestone-4-plan.md`, demonstration `docs/MILESTONE_4_VALIDATION.md`. This completes all
  four milestones of `docs/milestones.md`.
- Version 1.0.0 (T-501, 2026-07-18): the approved roadmap is 100% complete. The `version`-fact
  regex was widened so `check-governance` extracts a `1.x` version; full summary in
  `docs/FINAL_COMPLETION_REPORT.md`.

## In progress

**AUTO-016** (registered and authorized 2026-08-05; initial start 2026-08-06): Integrated Milestone
Automation Runner — a
supported, production-grade Core Engine capability, `src/ai_workflow_engine/milestone_runner/`
(nineteen files: fifteen modules plus the four-file `providers/` subpackage), exposed as
`workflowctl milestone-runner <verb>`. It executes an already-authorized stage as a bounded,
resumable sequence of typed milestones — one Claude CLI invocation per milestone, deterministic
focused verification after each, the full verification set at the end, exactly one bounded
independent Codex review, at most one correction round and one closure verification — writing
durable, redacted run state outside the repository and stopping at a human commit approval gate that
is disabled by default. Registry state `NOT_STARTED → AUTHORIZED → IN_PROGRESS`; branch
`feature/auto-016-milestone-runner` created from `main` at
`4cbd714dd6a83de1b390feac39223e0b8f5d4cbf`. Initial-start transition only — no implementation
performed, no commit made; progress remains 0%. Contract:
`docs/workflow-automation/stage-prompts/AUTO-016.md`.
**Closed — historical record only (noted 2026-08-08).** The paragraph above records AUTO-016's
state as of its 2026-08-06 initial start and is retained unchanged as historical evidence. AUTO-016
was subsequently implemented, approved, and closed `IN_PROGRESS → COMPLETE` / `Current → Done` on
2026-08-08, merged as `b4534c7` via pull request #19 — see "Latest governance activity — AUTO-016
closed" above, `docs/reports/workflow-automation/AUTO-016-completion-report.md`, and
`docs/workflow-automation/STAGE_REGISTRY.md`. AUTO-016 is **not** in progress. No other entry in
this section was touched.

**AUTO-015** (registered and authorized 2026-08-04; initial start 2026-08-04): Deterministic
Next-Stage Proposal and Governed Prompt Generation — a new read-only Core Engine Planning Service,
`src/ai_workflow_engine/successor_planning/`, exposed as `workflowctl successor-planning propose`.
Registry state `NOT_STARTED → AUTHORIZED → IN_PROGRESS`; branch
`feature/auto-015-successor-planning` created from `main` at
`c9cda8823c4c9e37c806a057dba1b83684619dfe`. Initial-start transition only — no implementation
performed, no commit made; progress remains 0%. Contract:
`docs/workflow-automation/stage-prompts/AUTO-015.md`.
**Closed — historical record only (noted 2026-08-06).** The paragraph above records AUTO-015's
state as of its 2026-08-04 initial start and is retained unchanged. AUTO-015 was subsequently
implemented, approved, and closed `IN_PROGRESS → COMPLETE` / `Current → Done` on 2026-08-05, merged
as `e325f95` via pull request #17 — see "Prior governance activity — AUTO-015 closed" above and
`docs/workflow-automation/STAGE_REGISTRY.md`. AUTO-015 is **not** in progress. This note was added
by the AUTO-016 initial-start session solely to remove the contradiction with its own preflight
finding that no other AUTO stage is `AUTHORIZED` or `IN_PROGRESS`; no other stale entry in this
section was touched.

**DASH-004** (authorized 2026-07-30): the local backend and dashboard shell —
`agentos_dashboard/{settings.py, main.py, __main__.py, api/**, web/**}`. Loopback-only FastAPI
app behind a `Host`-allowlist/CSRF/CSP security middleware, the `{ok, data, error}` API envelope
(EP-01 health, EP-02 snapshot, EP-03 status, EP-20 snapshot refresh), a single-instance PID
lockfile kept outside the repository, and a Jinja2 Overview page (PG-01) with healthy-empty
states. Implemented and validated on branch `feature/dash-004-dashboard-shell`; stopped for Human
Owner approval before any commit. Decisions: `docs/agentos-dashboard/DECISIONS.md` DD-10, DD-11.
Report: `docs/reports/agentos-dashboard/STAGE-04-completion.md`.

**GOV-AUTO-04** (authorized 2026-07-29): gives `workflow-authorize.sh`/`workflow-next.sh` one
shared, tested branch-preparation library (`scripts/lib/branch_prepare.sh`) so a registry-governed
task's registered branch is created or safely switched to automatically, right after the
authorization commit, resolving OD-D10; and extends `workflow-approve.sh`'s report discovery to
accept the Dashboard program's canonical `STAGE-XX-completion.md` name directly, cross-checked
against registry data, resolving OD-D11. Implemented and validated; stopped for Human Owner
approval before any commit. Decisions: `docs/agentos-dashboard/DECISIONS.md` DD-08. Report:
`docs/reports/GOV-AUTO-04-completion-report.md`.

**GOV-AUTO-03** (authorized 2026-07-28): extends `scripts/workflow-approve.sh` so that, after
Human Owner approval, it performs the approved implementation commit and the deterministic
governance closeout of that same task together as one controlled local commit, gated on the
`project.id: ai-workflow-engine` marker so every other repository keeps the unchanged GOV-AUTO-01
plain commit gate. Implemented and validated; stopped for Human Owner approval before any commit.
Report: `docs/reports/GOV-AUTO-03-completion-report.md`. AUTO-006 was implemented, validated,
approved, committed as `d8d356d060076be4ad78afb4d20891004a946204`, closed to `Done`, and merged
into `main` on 2026-07-28. Authorizing GOV-AUTO-03 authorizes no successor; AUTO-007, GOV-2, and
GOV-3 remain explicitly unauthorized.

## Planned

**GOV-AUTO-05** (`docs/TASK_QUEUE.md`) is registered as `Planned` and unauthorized: fix
`scripts/workflow-authorize.sh` so only explicit blocked task status and active unresolved entries
in an `OPEN_QUESTIONS.md` `## Open` section refuse authorization, while resolved entries and
negated or historical wording do not produce false positives. The task preserves all existing
predecessor, registry, branch, dirty-tree, and Human confirmation checks and carries no structured
AUTO/DASH stage-registry row.

AUTO-007 (`docs/TASK_QUEUE.md`; program plan `docs/workflow-automation/README.md`)
and Dashboard stages DASH-002..DASH-010 (program plan
`docs/agentos-dashboard/MASTER_PLAN.md`), each requiring its own fresh Human Owner
authorization. DASH-004 onward was additionally gated on the OD-D9 dependency decision; **OD-D9
was resolved by the Human Owner on 2026-07-29** — FastAPI + Uvicorn + Jinja2, declared in a new
optional `dashboard` dependency group in `pyproject.toml`, with the core install left free of
dashboard-serving dependencies (`docs/agentos-dashboard/OPEN_QUESTIONS.md`; `DECISIONS.md`
DD-09) — so that extra gate is lifted and only the ordinary per-task authorization remains.
DASH-004 stays `Planned` and unauthorized. Separately,
two ordinary (non-AUTO/DASH-family) governance/tooling tasks. **GOV-3**
(`docs/TASK_QUEUE.md`) was recorded on 2026-07-28 by Human Owner decision as explicit future work:
the Reporting Skills write one artifact per workflow identifier per kind, but a bounded repair loop
produces several genuinely different QA and stage reports per workflow; AUTO-005 works around it
with a per-attempt audit scope, and the fix is an attempt-aware artifact name. **GOV-2**
(`docs/TASK_QUEUE.md`):
extending `workflowctl check-governance` to machine-verify stage-registry/lifecycle consistency,
assessed but deliberately not implemented during the 2026-07-24 governance recovery (real
validator code needing its own authorization, out of scope for a documentation-only recovery
session) — requires its own fresh authorization like any other Planned task. GOV-AUTO-04 is no
longer Planned — see "In progress" above. Candidate future
engine work (explicitly out of the delivered 1.0.0 scope) remains listed in
`docs/FINAL_COMPLETION_REPORT.md` under "Future improvements".

## Blockers

There is no active task blocker. Every planned successor still requires separate Human Owner
authorization.

## GOV-AUTO-05 exception authorization and implementation update — 2026-07-30

Status: Done

The Human Owner explicitly authorized GOV-AUTO-05 through a one-time governance exception because
the false-positive defect in `scripts/workflow-authorize.sh` prevented the normal gate from
authorizing the task that repairs it. The manual `Planned → Current` mirror transition authorizes
only GOV-AUTO-05's registered scope.

Implementation is complete and validated, uncommitted, and stopped for Human Owner approval. The
task-status parser now treats only the first non-blank whole canonical status line after the task
heading as authoritative, and the open-question parser considers only active structured blockers
under `## Open`. Explicit blocked status and active unresolved questions still refuse; resolved,
negated, historical, quoted, emphasized, acceptance-criteria, and explanatory text do not produce
false positives. The approval gate now uses the same canonical-field rule for Current-task
discovery and `Current → Done` replacement, fixing its matching false positive without changing
any approval or Git safety gate. Report: `docs/reports/GOV-AUTO-05-completion-report.md`.

`main` and `origin/main` are identical and carry the AUTO-006 merge; `feature/auto-004-model-
providers`, `feature/auto-005-agents`, and `feature/auto-006-pr-merge-closeout` were all pushed to
`origin` and retained, not deleted. Stage branches created later and not yet pushed produce the
pre-existing `upstream_missing` finding from `workflowctl check-git` — the tolerance
`docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 16 and the SSP both name.

## Authorization update — 2026-07-28

## AUTO-007

Status: Done

The Human Owner explicitly authorized this single task through the local authorization gate.
Implementation and approval remain separate phases.

## Authorization update — 2026-07-29

## GOV-2

Status: Done

The Human Owner explicitly authorized this single task through the local authorization gate.
Implementation and approval remain separate phases.

## Authorization update — 2026-07-29

## GOV-3

Status: Done

The Human Owner explicitly authorized this single task through the local authorization gate.
Implementation and approval remain separate phases.

## Authorization update — 2026-07-29

## DASH-002

Status: Done

The Human Owner explicitly authorized this single task through the local authorization gate.
Implementation and approval remain separate phases.

## Authorization update — 2026-07-29

## DASH-003

Status: Done

The Human Owner explicitly authorized this single task through the local authorization gate.
Implementation and approval remain separate phases.

## Authorization update — 2026-07-29

## GOV-AUTO-04

Status: Done

The Human Owner explicitly authorized this single task through the local authorization gate.
Implementation and approval remain separate phases.

## Authorization update — 2026-07-30

## DASH-004

Status: Done

The Human Owner explicitly authorized this single task through the local authorization gate.
Implementation and approval remain separate phases.

## DASH-004 implementation update — 2026-07-30

Status: Current

DASH-004 is implemented and validated on the registered branch `feature/dash-004-dashboard-shell`,
uncommitted, stopped for Human Owner approval. Approval and implementation remain separate phases.
Report: `docs/reports/agentos-dashboard/STAGE-04-completion.md`.

## Authorization update — 2026-07-30 (AUTO-008)

## AUTO-008

Status: Done

Registered and authorized by the Human Owner in one act following an architectural audit, then
implemented, validated, approved, and closed on 2026-07-30. The engine is now verified by CI:
one `pytest` invocation collects and passes all three suites (1,160 -> 2,967 tests), `mypy --strict`
covers all three packages, the wheel ships all three, and the end-to-end acceptance demonstration
passes with no test-only production workarounds. OD-10 and OD-11 resolved.

## Authorization update — 2026-07-30 (GOV-AUTO-06)

## GOV-AUTO-06

Status: Done

Registered and authorized to resolve AUTO-008's deferred F-2 finding, then implemented, validated,
approved, and closed on 2026-07-30. The eight delivered Git/GitHub Skills are bound in the
production registry, so `GitAgent` and `MergeAgent` can run against it for the first time.
Capability isolation is unchanged and proven by a negative test.

## Authorization update — 2026-07-31 (GOV-AUTO-07)

## GOV-AUTO-07

Status: Done

Registered and authorized to resolve AUTO-008's deferred F-1 finding, then implemented, validated,
approved, and closed on 2026-07-31. `AuthorizationBindingDriftError` now carries one documented
argument convention, enforced at every raise site: `expected` is the authorization-bound or
otherwise required reference value, `actual` is the current value judged against it. Drift-detection
behaviour is unchanged — only the diagnostic orientation — and the public attributes and rendered
message are byte-identical.

## Authorization update — 2026-07-31 (AUTO-009)

## AUTO-009

Status: Done

Registered and authorized by the Human Owner as the single `Current` task: the first public
application-service boundary for the automated workflow engine. `WorkflowService` exposes exactly
four read-only operations (`status`, `list`, `audit`, `report`) over the existing AgentOS state,
audit, report, and configuration components, and an additive `workflowctl auto` Typer
sub-application surfaces the same four. Read-only by construction: no agent execution, no Git or
GitHub mutation, no write lock, no state transition. Implementation and approval remain separate
phases; AUTO-010 is not authorized.

**Closed `Current -> Done` on 2026-07-31** after a Human-Owner-required twelve-point scope, API,
and read-only integrity verification, all of which passed. The four-operation `WorkflowService`
and the four-command `workflowctl auto` sub-application are delivered and read-only by
construction; 3,151 tests pass; `mypy --strict` clean over 117 source files. Six non-blocking
defects remain deferred. AUTO-010 was subsequently authorized, implemented, and closed (below).

## AUTO-010 — Real Non-Interactive Provider Runtime

Status: Done

Registered and authorized by the Human Owner on 2026-07-31 as the single `Current` task, then
implemented, validated, approved, and **closed `Current -> Done` the same day** after a
fourteen-point scope, runtime, and safety verification that passed in full.

The engine can now really execute Claude Code and Codex without a terminal:

    WorkflowService.invoke_provider -> ProviderRuntime.invoke -> Claude CLI / Codex CLI

Both providers are live-validated against the real installed CLIs (Claude 2.1.220, codex-cli
0.146.0) on all ten acceptance criteria each — 25 live tests, zero skipped — rather than by mocks,
which the suite keeps strictly separate and says so. Non-interactivity is structural: the child
runs in its own session with no controlling terminal, receives exactly one prompt on stdin and then
EOF, and every run terminates in `COMPLETED`, `COMPLETED_WITH_ASSUMPTIONS`, `BLOCKED`, or `FAILED`.
Permission and sandbox policy are closed enums defaulting to the least capable value, so
`bypassPermissions` and `danger-full-access` are inexpressible anywhere in the engine.

Three blockers in the shared provider process runner were fixed: process-group termination with TTY
detachment, streaming stdout/stderr ceilings with cleanup on breach, and a Codex report channel
that could never have parsed a real run. 3,241 tests pass; `mypy --strict` clean over 120 source
files. Four non-blocking defects (D-3 through D-6) remain deferred. AUTO-011 is not authorized.

## AUTO-011 — Unified Provider and Agent Result Contract

Status: Done

Registered and authorized by the Human Owner on 2026-08-01 as the single `Current` task, on branch
`feature/auto-011-agent-result-contract` created from clean, synchronized `main` at `fd0b34f` (the
AUTO-010 publication merge). The `Current` set was empty beforehand.

The stage creates one canonical typed result contract for provider and agent execution:

    WorkflowService -> Provider Runtime -> Canonical AgentRunResult

`AgentRunResult` becomes the canonical result contract for future Claude execution, Codex
execution, internal agents, and the Preparation, Reviewer, and Implementer Modes, none of which
this stage implements. It standardizes execution results only — no workflow mode, no workflow
lifecycle, no state transition.

Existing models are reused rather than duplicated: `ProviderRunStatus` supplies the four terminal
statuses, `ProviderVerdict` the pass/fail axis, `ProviderFailure` the typed failure, and
`ProviderKind` the provider identity. `recommended_next_state` is advisory only and can never
mutate workflow state or authorize a transition. AUTO-010's Provider Runtime continues to work
unchanged, with compatibility preserved by adapters rather than by interface changes.

AUTO-012 and every later roadmap phase remain unauthorized.

**Closed `Current -> Done` on 2026-08-01** after a Human-Owner-required fourteen-point scope,
contract, and compatibility verification, all of which passed. The canonical `AgentRunResult` is
delivered and reached from AUTO-010's `ProviderRunResult` through an adapter, so the Provider
Runtime is byte-identical and compatibility is preserved by projection rather than by interface
change. All eighteen required canonical fields are present, plus `session_id` as the invocation's
trace identity; status and verdict remain deliberately distinct; `recommended_next_state` is
advisory only and no module outside the contract reads it. 3,352 tests pass and 25 live CLI tests
pass with zero skips; `mypy --strict` clean over 121 source files. No blocker was fixed because
none existed. Three non-blocking defects (D-8, D-9, D-10) remain deferred. AUTO-012 is not
authorized.

## AUTO-012 — Configurable Approval Policy, Persistence, and Invalidation

Status: Done

Registered and authorized by the Human Owner on 2026-08-01 as the single `Current` task, on branch
`feature/auto-012-approval-policy` created from clean, synchronized `main` at `e2b069c` (the
AUTO-011 publication merge). The `Current` set was empty beforehand.

The stage builds a configurable, durable approval subsystem for future workflow gates:

    WorkflowService -> ApprovalService -> policy resolution, request persistence,
                                          manual decisions, timeout decisions,
                                          checksum binding, invalidation

`agentos_workflow/approvals.py` delivers a strict typed policy resolved across built-in, project,
gate, and run layers into an immutable snapshot; an append-only per-workflow `approvals.jsonl`
history written through the existing `StateStore` discipline; absolute timezone-aware deadlines
evaluated lazily with no timer, thread, or sleep; the five timeout actions; and four-checksum
binding whose recomputation immediately before consumption is what invalidates a stale approval.

A separate governance act accompanies it: `HUMAN_AUTHORIZATION_MODEL.md` moves to v2.0 with a new
§5a recording the Human Owner's decision that future workflow modes may use configurable approval
gates governed by `ApprovalService`. That decision authorizes the subsystem only — no specific
mode, no gate placement, no successor stage — and relaxes none of the existing safety constraints.

No workflow mode is implemented. AUTO-013 and every later roadmap phase remain unauthorized.

**Closed `Current -> Done` on 2026-08-01.** The reusable approval subsystem is delivered and the
governance decision permitting configurable approval gates is recorded as
`HUMAN_AUTHORIZATION_MODEL.md` v2.0 §5a, authorizing the subsystem only. No workflow mode,
lifecycle, or state was implemented: `WorkflowState` remains 19 members with 37 edges and
`orchestrator/engine.py` is byte-identical. Both modified production files are purely additive.
3,469 tests pass and 25 live CLI tests pass with zero skips; `mypy --strict` clean over 122 source
files. No blocker was fixed because none existed. Three non-blocking defects (D-11, D-12, D-13)
remain deferred. AUTO-013 is not authorized.

## Authorization update — 2026-08-02

## GOV-4

Status: Done

The Human Owner explicitly authorized this single task through the local authorization gate, as
an ordinary (non-AUTO/GOV-AUTO) engine task record following the GOV-2/GOV-3 precedent.

**Closed `Current -> Done` on 2026-08-02.** Two pre-AUTO-013 live acceptance test-harness defects
are resolved, test-only: session-scoped forwarding of the configured Claude account's real
`CLAUDE_CONFIG_DIR` (replaced by a per-invocation ephemeral copy of a read-only authentication
template), and non-deterministic first-attempt compliance with the strict bare-JSON auto-mode
contract (bounded to 3 attempts, retrying only `FAILED`/`MALFORMED_OUTPUT`). Two full live-suite
runs: 32 passed/0 failed/0 skipped each. No production code changed. AUTO-013 remains
unauthorized.

## Authorization update — 2026-08-08

## DASH-005

Status: Done

The Human Owner explicitly authorized this single task through the local authorization gate.
Implementation and approval remain separate phases.

## DASH-005 implementation update — 2026-08-08

Status: Current

DASH-005 is implemented and validated on the registered branch
`feature/dash-005-board-task-detail`, uncommitted, stopped for Human Owner approval.
Implementation and approval remain separate phases. Report:
`docs/reports/agentos-dashboard/STAGE-05-completion.md`.

## Authorization update — 2026-08-10

## PLAN-001

Status: Done

The Human Owner explicitly authorized this governance/documentation-only correction through a
written directive; it was implemented, validated, and closed `Current -> Done` in the same
session, uncommitted, awaiting a separate Human Owner review. See "Latest governance activity —
PLAN-001 closed" above.

## Authorization update — 2026-08-09

## DASH-006

Status: Done

The Human Owner explicitly authorized this single task through the local authorization gate.
Implementation and approval remain separate phases.

## DASH-006 implementation update — 2026-08-09

Status: Current

DASH-006 is implemented and validated on the registered branch
`feature/dash-006-git-handover-views`, uncommitted, stopped for Human Owner approval.
Implementation and approval remain separate phases. Report:
`docs/reports/agentos-dashboard/STAGE-06-completion.md`.

## Authorization update — 2026-08-10

## DASH-007

Status: Done

The Human Owner explicitly authorized this single task through the local authorization gate.
Implementation and approval remain separate phases.

## Authorization update — 2026-08-10

## DASH-008

Status: Done

The Human Owner explicitly authorized this single task through the local authorization gate.
Implementation and approval remain separate phases.

## Authorization update — 2026-08-10

## DASH-009

Status: Done

The Human Owner explicitly authorized this single task through the local authorization gate.
Implementation and approval remain separate phases.

## Authorization update — 2026-08-11

## DASH-010

Status: Done

The Human Owner explicitly authorized this single task through the local authorization gate.
Implementation and approval remain separate phases.

## Authorization update — 2026-08-19

## T-405 — Governed first publication of an absent remote branch

Status: Done

The Human Owner registered T-405 as a new ordinary Milestone 4 remediation linked to completed
T-403 and selected the strict create-only concurrency policy: an exact approved remote branch may
be created only while the exact destination remains absent at update time, enforced by a narrowly
typed zero-expected-OID CAS. The task contract is
`docs/t-405-governed-first-push-remediation.md`. T-403 remains `Done`; T-405 is prepared for a
fresh independent `plan-review`, and implementation must not begin before an `APPROVED` verdict.
No production code, test, workflow event, commit, push, branch, or remote was changed by this
registration.

The first independent plan review returned `REJECTED / PLAN_REMEDIATION_REQUIRED` and was not
recorded as a workflow event. The contract now closes T405-PR-001..004 by requiring a field-local
strict boolean, an immutable validated `approval.head` source OID, ERROR classifications for remote
query execution/malformed-evidence failures, distinct matching/conflicting/definite-rejection/
indeterminate states, and the associated deterministic race and post-write tests. At that review
point, Human Owner policy, scope, authorization, and task status were unchanged: T-405 remained
`Current`, had zero events, and awaited a fresh independent `plan-review`.

The second independent plan review also returned `REJECTED / PLAN_REMEDIATION_REQUIRED`, while
confirming T405-PR-001..004 closed. The contract now closes T405-PR-005..006 by deriving exactly one
immutable effective push endpoint from complete configured push/fallback URL sets; refusing
missing, multiple, malformed, or ambiguous endpoint configurations; using that same direct value
for inspection, zero-OID publication, and verification; preventing symbolic-config redirection;
and hardcoding invocation-local tag-following/submodule-recursion suppression. The deterministic
matrix now contains 44 cases. No workflow event or implementation change occurred; status and next
stage remain unchanged.

The third independent plan review again returned `REJECTED / PLAN_REMEDIATION_REQUIRED`. It kept
T405-PR-001..004 closed but identified the post-publication tracking gap, URL-rewrite repository-
identity gap, pre-push-hook/push-option gap, and an accidental T-403 postcondition expansion. The
final contract closes T405-PR-007..010 and completes endpoint/push containment: accepted direct
endpoint forms plus total rewrite-rule refusal preserve actual inspect/write/verify/materialize
repository identity; `--no-verify` and empty invocation-local `push.pushOption` prevent client
hook/option expansion; one post-verification fixed exact-ref fetch may update only the approved
local remote-tracking ref; and T-403's existing gates, writer argv, and result semantics remain
exactly unchanged. Every post-CAS materialization/verification failure is indeterminate/ERROR,
permits no workflow event, and causes no second remote write. The deterministic local-only matrix
now contains 70 cases. No workflow event or implementation change occurred; at that review point,
T-405 remained the sole `Current` task with `plan-review` next.

**Final Human Owner disposition — 2026-08-19:** T-405 is deferred/closed without implementation
using the repository's canonical administrative `Done` status. Repeated plan reviews established
that safely automating first publication would require materially broader Git transport, URL-
rewrite, hook, ambient-configuration, environment, tracking, and local-metadata isolation than the
intended remediation. This is a deliberate policy/scope decision rather than an implementation
defect; no T-405 production or test implementation occurred. T405-PR-001..010 and the complete
contract remain historical evidence.

The resulting boundary is: first publication is an explicit Human Owner manual bootstrap outside
`workflowctl push`, establishing the remote branch and upstream; subsequent publication uses the
unchanged T-403 path and still requires a resolvable approved upstream. T-403 history,
`GitWriter`, and production behavior are unchanged. T-405 has zero workflow events, no synthetic
stage outcome is recorded, the Current set is empty, and no replacement or successor is created or
authorized.

**Human Owner ratification — 2026-09-02:** the T-405 decision above is ratified as a real Human
Owner governance decision made on 2026-08-19. T-405 remains `Done` and the `Current` set remains
empty. The ratification explicitly preserves rather than repairs its evidence gaps: the executable
authorization gate `scripts/workflow-authorize.sh` (GOV-AUTO-02) **was not used**, **no committed
`authorize T-405` transition exists**, the cited `INTENTIONAL_POLICY` bootstrap-audit artifact is
**`NOT_FOUND`**, and the three narrated plan-review rounds behind T405-PR-001..010 are
**`NOT_FOUND / UNVERIFIABLE`**. Nothing was fabricated to close those gaps and no claim is made
that the missing artifacts existed; T-405's "zero workflow events" proves nothing either way, since
the engine's event store holds no `ai-workflow-engine` project at all. The substance of the policy
is independently corroborated by the Human Owner's own later action: DOCFLOW-005 event 8, recorded
2026-08-19 at 22:57, completed the manual bootstrap "under recorded first-publication policy" at
HEAD `dced1783788c64ec0c97576ea5709b7e2dc27600`. The DOCFLOW-005 evidence corroborates the substance of the
deferral/manual-bootstrap policy only. It does not prove, supply, or substitute for T-405's missing
authorization event, the missing `INTENTIONAL_POLICY` artifact, or any of the three missing
plan-review artifacts, which remain `NOT_FOUND` / `UNVERIFIABLE`. The ratification establishes the
governance decision now; it manufactures no historical evidence. Rationale:
`docs/DECISION_LOG.md`, 2026-09-02 entry.

## Authorization update — 2026-09-03

## T-307

Status: Current

The Human Owner explicitly authorized this single task through the local authorization gate.
Implementation and approval remain separate phases.
