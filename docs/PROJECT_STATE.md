# Project State

Overall condition of `ai-workflow-engine`. This document is a governance mirror
(`governance.project_state` in `self-governance.yaml`) and a `governance.facts` source for the
`version` fact — it is cross-checked against `pyproject.toml` by `workflowctl check-governance`,
so keep the version line's wording exact if you edit it.

Current Version: 1.0.0

## Summary

`ai-workflow-engine` is a local orchestration foundation for governed AI-assisted software
development: deterministic read-only inspection, governed prompt generation, non-interactive
agent execution with independent claim verification and a persisted workflow state machine, and
approval-gated controlled commit and push. All four milestones are implemented. See
`docs/milestones.md` for the four-milestone roadmap, `docs/MASTER_ROADMAP.md` for the task-level
plan to 1.0, and `docs/architecture.md` for the pipeline shapes.

## Completed
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
