# AUTO-016 — Integrated Milestone Automation Runner

> **PROPOSAL — NOT AUTHORIZED**
> This is a proposed stage contract, not an authorization. See §30 and §33.

> **Revision note.** This is **Revision 4** of the AUTO-016 contract, drafted under GOV-AUTO-10 —
> AUTO-016 Integrated Runner Contract Definition — after the Human Owner selected
> **Integrated Milestone Automation Runner** as the AUTO-015 successor capability. It is
> reconciled against a complete read of the local AUTO-015 prototype runner
> (`~/.local/share/auto015-runner/`), this repository's architecture and security governance, and
> the AUTO-015 contract-definition precedent. The prototype is treated throughout as **evidence,
> never as authoritative design** (§6).
>
> Revision 2 remediated the two blockers returned by the single bounded independent Codex review
> (`AUTO-016-contract-review.md` §4). **Revision 3 records the Human Owner's rulings on the three
> decisions Revision 2 left open** — DEC-016-002 (provider-adapter ownership), DEC-016-005
> (milestone plan location), and DEC-016-006 (prototype disposition) — and propagates each ruling
> into the module surface, plan format, provider boundary, configuration model, allowlist, forbidden
> surface, test matrix, acceptance plan, and migration plan (§1b). Superseded revision text is
> replaced, not amended in place; no revision of this contract was ever authorized, registered, or
> acted upon, so no historical record is altered — only a proposal draft
> (`STAGE_REGISTRY.md` §3 rule 8).
>
> **Revision 4** is a documentation-only correction of AUTO016-REV-003 (§1a): two residual absolute
> Git-authority statements — the §1 implementation-class summary and §4.4's baseline-invariance
> justification — contradicted §20's gated commit/push capability. No design, decision, ruling, or
> Git authority changed; the correction narrows and makes explicit what was already contracted.
>
> **Recording these rulings does not authorize AUTO-016.** The status remains
> `PROPOSED — NOT AUTHORIZED`; a ruling on a design question is not an authorization to implement
> (`HUMAN_AUTHORIZATION_MODEL.md` §5a — a mechanism is authorized, never a placement).

## 1. Contract Metadata

| Field | Value |
|---|---|
| **Stage** | AUTO-016 |
| **Title** | Integrated Milestone Automation Runner |
| **Status** | `PROPOSED — NOT AUTHORIZED` |
| **Predecessor** | AUTO-015 (`COMPLETE`, merged as `e325f95`, published via PR #17) |
| **Human Owner decision source** | Human Owner capability selection recorded under GOV-AUTO-10 (2026-08-05): "AUTO-016 — Integrated Milestone Automation Runner"; capability selection only, explicitly not an implementation authorization |
| **Contract source** | This document, Revision 4, drafted under GOV-AUTO-10's bounded contract-definition scope |
| **Human Owner design rulings** | DEC-016-002, DEC-016-005, DEC-016-006 ruled 2026-08-05 (§1b, §30); design rulings only, explicitly not an implementation authorization |
| **Contract review** | `docs/reports/workflow-automation/AUTO-016-contract-review.md` |
| **Proposed report path** | `docs/reports/workflow-automation/AUTO-016-completion-report.md` (does not exist; created only if AUTO-016 is later implemented) |
| **Proposed branch name** | `feature/auto-016-milestone-runner` (registered only at a future authorization act; not created by this contract) |
| **Implementation class** | Supervised execution capability — invokes model-provider CLIs, reads the repository, runs deterministic verification, writes durable run state **outside** the repository, and stops at human gates. Performs **no automatic** commit, push, pull-request creation, merge, branch deletion, reset, restore, rebase, stash, or governance mutation. Commit and push execute only when explicitly enabled by configuration, separately approved by the Human Owner, bound to repository identity / branch / baseline SHA / the exact staged diff or commit payload / the exact operation, single-use, and invalidated by branch drift, HEAD drift, changed-path drift, verification failure, expiry, or prior use (§20). Pull-request creation, merge, branch deletion, reset, restore, rebase, stash, and governance mutation remain forbidden outright unless a future separate contract explicitly authorizes them. |
| **Implementation authorization** | **None.** No file outside this contract, its review report, and GOV-AUTO-10's own governance records may be created or modified under this document. |

## 1a. Correction Index

| Finding | Severity | Description | Remediated in |
|---|---|---|---|
| **AUTO016-REV-001** | Critical | Revision 1 both permitted a human-gated commit/push (§20, per the Human Owner's "gated and disabled by default" direction) and asserted as a security invariant that no mutating Git argv was reachable anywhere (§22 invariant 4), with §31 stating an unqualified "never commit, push." An internal contradiction; the review also noted the gates omitted `HUMAN_AUTHORIZATION_MODEL.md` §5a's binding, invalidation, and single-use properties. | §8 and §23.1 isolate the capability in a single `approval_git.py` module; §22 invariant 4 is restated precisely (zero mutating argv in every other package file; exactly one gated caller path) rather than absolutely; §20 adopts §5a constraints 2–6 in full — bound to branch/HEAD/changed-path digests/verification results/review verdict, invalidated on any change, single-use, evidence-not-authority, never inherited, durably recorded; §31 states the one deliberate exception explicitly instead of an unqualified "never"; §25/§27 proofs are re-scoped to match. |
| **AUTO016-REV-003** | High | The §1 metadata row still described the implementation class with the unqualified sentence "Performs no commit, push, PR, merge, or governance mutation," and entry condition §4.4 still justified baseline invariance with "the runner never commits." Both contradict §20's Human Owner–gated, single-use commit and push capability — the same class of contradiction as AUTO016-REV-001, in two instances the Revision 2 sweep missed because it searched for mutating-Git *argv* language rather than capability summaries. | §1 states the precise semantics: no **automatic** commit, push, PR creation, merge, branch deletion, reset, restore, rebase, stash, or governance mutation; commit and push only under configuration enablement, separate Human Owner approval, full binding, single use, and the six invalidation triggers; every other mutation forbidden outright absent a future separate contract. §4.4 is rescoped to invariance up to the §20 gate. §20's binding bullet gains repository identity and the exact authorized operation, and its invalidation bullet names all six triggers. Git authority is **narrowed and made explicit, never broadened**. |
| **AUTO016-REV-002** | High | Revision 1 required complete raw provider and command output to be persisted (§16, §17, §22 invariant 2) with no sanitization step, while `SECURITY_MODEL.md` §1 and `AUDIT_MODEL.md` §2 require redaction *before* a referenced file is written — §2 explicitly forbidding a raw credential "even in a referenced file." Referencing rather than inlining is necessary but not sufficient. | New **§17a**: no byte reaches any transcript, verification-output, or state file before passing redaction at a single enforced write boundary; DEC-016-008 fixes the utility as an intra-package reuse of `successor_planning.redaction.redact_text` (no boundary crossing, no modification, no duplicated security primitive); an honest limitation statement replaces any claim of provable cleanliness; redaction events are recorded, never silent. §22 invariant 2 is rewritten and §26 gains four dedicated tests. |

## 1b. Human Owner Decision Rulings (Revision 3)

The Human Owner ruled on 2026-08-05 on the three decisions Revision 2 recorded as genuinely open.
Each ruling is binding on the future implementation and is propagated into the sections named below.
None of them authorizes implementation.

| Decision | Ruling | Relation to the Revision 2 recommendation | Propagated into |
|---|---|---|---|
| **DEC-016-002 — Provider-adapter ownership** | Provider adapters belong under `src/ai_workflow_engine/milestone_runner/providers/` and are **owned by the AUTO-016 milestone-runner package**. `agentos_workflow` provider runtime must **not** be reused directly. Adapters must use validated configuration, stdin prompt delivery, bounded timeout, captured stdout/stderr, durable transcripts, strict result parsing, and no credential storage. | Confirms the recommendation and **tightens its shape**: Revision 2 proposed a single `providers.py` module; the ruling requires a dedicated `providers/` subpackage. | §8, §17, §21, §22, §23.1, §23.3, §26, §28 |
| **DEC-016-005 — Milestone plan location** | The default milestone-plan root is **external to the target repository**: `~/.ai-workflow-engine/milestone-runs/<repository-id>/plans/`. Repository-local plans are permitted **only** when the governing stage contract explicitly lists their exact paths in its implementation allowlist. Arbitrary repository-local plan discovery is **forbidden**. | Resolves the recommendation in a **narrower and more specific** form: Revision 2 proposed only "a configured, root-confined directory" with no default and no rule for repository-local plans. | §11, §14, §21, §22, §23.3, §24, §26, §27 |
| **DEC-016-006 — Prototype disposition** | The prototype at `~/.local/share/auto015-runner/` **remains unchanged** as historical/reference tooling until AUTO-016 live acceptance succeeds. After successful live acceptance: mark it deprecated; do **not** automatically delete it; do **not** migrate or rewrite its historical state or transcripts; deletion requires a **separate explicit Human Owner decision**. | Confirms the recommendation and **adds a sequencing condition and an explicit deletion barrier** absent from Revision 2. | §24, §27, §28 |

## 2. Mission

Define — for future, separate authorization — a supported, production-grade capability of
`ai-workflow-engine` that executes an authorized stage's implementation as a bounded, resumable
sequence of typed milestones: driving a Claude CLI implementation session per milestone, running
deterministic focused verification after each, running the full verification set once at the end,
obtaining exactly one bounded independent Codex review, permitting at most one correction round and
one closure verification, and then **stopping at an explicit human commit gate**.

The capability converts the proven local AUTO-015 prototype runner into a first-class, packaged,
tested, `mypy --strict`-clean subsystem reachable through `workflowctl milestone-runner`.

**What this capability is not.** It is not an autonomous agent. It never authorizes a stage, never
changes task or Registry state, never accepts a scope expansion, never accepts a Critical or High
finding as closed on a provider's say-so, and never commits, pushes, opens a pull request, merges,
or deletes a branch on its own initiative. It owns no runtime `WorkflowState` and grants no
authority that `HUMAN_AUTHORIZATION_MODEL.md` reserves to the Human Owner. Every provider report it
receives is **evidence to verify, not an authority to act** — the same principle
`ARCHITECTURE.md` §6 already establishes for Codex's QA verdict.

**Relationship to the prototype.** The local AUTO-015 runner already performed this job once, end
to end, under real conditions, and its recorded run (`auto015-20260804T060616Z-dedd54c6`) is the
evidence base for this contract (§6). AUTO-016 is the supported reimplementation of that proven
behavior inside the engine — not a port, and not an endorsement of every prototype choice.

## 3. Product Outcome

**What the Human Owner receives:** a supported CLI capability that takes an already-authorized
stage contract plus a typed milestone plan and drives it to a reviewed, verified,
ready-to-commit state without ever taking an irreversible action; a durable, inspectable run record
with full provider transcripts; and a hard stop at a commit approval gate that is **disabled by
default** and requires explicit configuration plus explicit interactive confirmation to execute
anything at all.

**What the system does not do:** it does not authorize; does not register or transition a stage;
does not modify `docs/TASK_QUEUE.md`, its mirrors, or `STAGE_REGISTRY.md`; does not create,
switch, or delete a branch; does not commit, push, open a PR, or merge by default; does not reset,
restore, stash, rebase, clean, or discard repository work under any condition; does not widen an
allowlist at runtime; and does not continue past any tripped safety gate.

## 4. Entry Conditions

AUTO-016 (the future capability), once authorized and implemented, may run only when:

1. A **separately authorized** stage contract exists and is named in the runner's validated
   configuration, pinned by SHA-256. AUTO-016 never authorizes the stage it implements; it refuses
   to start against a stage that is not already `AUTHORIZED` or `IN_PROGRESS` in
   `docs/workflow-automation/STAGE_REGISTRY.md` (`STAGE_ID_NOT_AUTHORIZED`, §13).
2. The configured repository resolves to a real Git worktree whose canonical identity matches the
   configured identity (`REPOSITORY_IDENTITY_MISMATCH`).
3. The current branch equals the configured `expected_branch` exactly
   (`BRANCH_MISMATCH`). The runner never creates, switches, or deletes a branch.
4. `HEAD` equals the configured `baseline_sha` exactly at start and at every subsequent gate
   (`HEAD_DRIFT`). Because the runner performs no automatic commit, this value is invariant for the
   whole run up to the §20 commit gate; a Human Owner–approved commit executed through that gate is
   the only event that may advance `HEAD`, and it is recorded with the approval that authorized it.
5. The working tree carries no change outside the cumulative allowlist (§15). Pre-existing
   unexpected modifications are a hard stop (`DIRTY_TREE`), never something the runner cleans.
6. The milestone plan loads, schema-validates (§14), forms a acyclic dependency graph, and the
   union of every milestone's `allowed_files` equals the configured `required_coverage` **exactly**
   — no gaps, no extras (`PLAN_COVERAGE_MISMATCH`).
7. The canonical governance checks pass, with exactly one documented tolerance: `check-git`'s
   `upstream_missing` finding on a local-only, unpushed stage branch, the same tolerance
   `STAGE_REGISTRY.md` §3 rule 16 and AUTO-015 §7.2 already established. No other finding is
   tolerated (`GOVERNANCE_CONTRADICTION`).
8. The runner's own configuration is present and valid. A missing or invalid configuration is a
   precondition failure (`INVALID_CONFIGURATION`), never an assumed default —
   `CONFIGURATION_MODEL.md` §2's "a missing configuration is a precondition failure, not an
   assumed-`main` fallback" applies unchanged.
9. No other runner process holds the run lock for the same canonical repository (§12).

Every condition above is re-verified at **every** milestone boundary and before every provider
invocation, not only at start — `MACHINE_GATES.md` §2a's rule that observations are obtained
independently and "caller-copied authorization strings are never live evidence" applies in full.

## 5. Approved Runtime Flow

```text
doctor / plan            (read-only preflight and plan validation)
→ PREFLIGHT              (§4 conditions; acquire run lock; publish initial state)
→ for each milestone in dependency order:
      IMPLEMENTING       (exactly one Claude CLI invocation, one milestone, one prompt)
      → FOCUSED_VERIFYING (deterministic, milestone-scoped commands only)
      → MILESTONE_COMPLETE
→ FINAL_VERIFYING        (the full configured verification set)
→ REVIEWING              (exactly one bounded, read-only Codex review)
→ [NEEDS_CORRECTION → CORRECTING → CLOSURE_VERIFYING]   (at most one round)
→ READY_FOR_COMMIT_APPROVAL      (human gate; disabled by default)
→ READY_FOR_PUSH_APPROVAL        (human gate; disabled by default)
→ DONE
```

Every step is **proposed, not authorized**. Any tripped gate moves the run to
`HUMAN_INTERVENTION_REQUIRED` with the working tree untouched; no step repairs, reverts, or
retries its way past a safety stop.

## 6. Prototype Evidence Base and Assessment

The local prototype (`~/.local/share/auto015-runner/`, 103,601 bytes of `auto015_runner.py`, plus
`config.yaml`, seven milestone files, four prompt templates, two JSON schemas, a 54,664-byte
self-test suite, and one real run's durable state) is the evidence base for this contract. It is
**not modified, deleted, moved, or imported** by AUTO-016 or by GOV-AUTO-10 (§24, §28).

**Recorded real-run evidence** (`state/state.json`, run `auto015-20260804T060616Z-dedd54c6`), which
this contract treats as the empirical justification for its recovery surface:

| Observed event | Count | What it proves |
|---|---|---|
| `provider_runs` | 8 implementation + review invocations | The per-invocation transcript model works at real durations (one run: 1,022 s) |
| `provider_failure_count` | 1 | Provider failures occur and must not be conflated with consumed review budget |
| `reconciliations` | 1 — "provider result was semantically valid but wrapped in a Markdown code fence" | The single-optional-fence tolerance (§18) is empirically required |
| `reopenings` | 1 — milestone result "not parseable YAML"; `reason: milestone_plan_correction` | Plan correction under an explicit Human Owner scope ruling is a real need |
| `review_recoveries` | 1 — `classification: token_expired` | Provider authentication failure must be separable from review budget (§19) |
| `revalidations` | 1 — cleared stop reason "tests failed after the correction round" | Post-correction revalidation is a real, bounded need |
| Final state | `READY_FOR_COMMIT_APPROVAL`, `successful_review_rounds: 1` | The budget model held under real conditions |

**Retain as proven (reimplement faithfully):** the twelve-command surface; the state vocabulary;
the cumulative-allowlist-plus-per-milestone-scope double check; the branch/baseline pinning; the
separation of `provider_failure_count` from `successful_review_rounds`; the print-only default Git
authority with a second interactive confirmation; the durable per-invocation transcript triple
(prompt/stdout/stderr); the milestone schema's thirteen required fields; the review-budget
constants and their refuse-to-start validation; the fenced machine-result grammar with distinct
start/end sentinels per role; the "stop and leave the tree exactly as found" discipline.

**Must be redesigned for production:**

| Prototype property | Why it cannot ship as-is |
|---|---|
| Single 2,334-line module | Violates this repository's package/module discipline; untestable in units. Becomes nineteen files — fifteen modules plus the four-file `providers/` subpackage (§8). |
| `argparse` + a hand-rolled `COMMANDS` dict, with four commands bolted on after the dict literal (`auto015_runner.py:1767`, `:2278-2281`) | The engine CLI is Typer with a fixed group/sub-app pattern (§9). |
| Module-level path constants (`:37-46`) forcing tests to monkey-patch nine module globals | The single largest packaging blocker. Paths become an injected workspace object. |
| Untyped `dict`-shaped state; one monotonically growing 61 KB blob rewritten and re-validated every step | Must be Pydantic v2 `StrictModel` (`extra="forbid"`), `mypy --strict`-clean, schema-versioned, and split into a small current-state document plus append-only event/audit logs (§11). |
| Hand-rolled JSON-Schema subset validator (`:228-271`) that silently ignores `$ref`, `oneOf`, and schema-valued `additionalProperties` — so `additive_reuse_justification` values are unvalidated today | Replaced by typed models; any JSON Schema becomes a derived artifact, not the source of truth. |
| Config hard-pinned to one stage, one branch, one baseline, one repository, with `AUTO-015` literals throughout (state prefix, sentinels, milestone-ID pattern, an `AUTH_OK_AUTO015` probe, and a `reconstructed_from_verified_m05_evidence` key naming one specific milestone) | Must be a general, validated configuration and a declarative workflow spec for any authorized stage (§21). |
| Run state under the runner's own install directory | Must be an external, repository-scoped artifact root, provably outside the worktree (§11), reusing AUTO-015's `_reject_repository_containment` discipline. |
| Provider commands read from free-form config lists; role→provider binding hard-coded at every call site; `output_from` a three-way string switch | Must be closed, validated templates with an unrepresentable unrestricted mode, behind a provider protocol with a configured role binding (§17). |
| Self-tests as a standalone `devtools/selftest.py` with a bespoke `@test` registry | Becomes real `pytest` tests inside the repository suite (§26). |

**Prototype defects this contract requires fixing** — found by direct inspection during contract
drafting, each reproduced against the prototype source and none fixed there (the prototype is not
modified by this work, §24):

| # | Defect | Required AUTO-016 behavior |
|---|---|---|
| P-1 | **Allowlist widening.** `path_matches()` (`:667-675`) uses `fnmatch`, whose `*` crosses `/`, so `tests/test_*.py` also matches `tests/test_pkg/inner.py`. A latent scope hole in the security-critical guard, and the existing `t_path_matches` self-test does not cover it. | Segment-aware matching in which `*` never crosses `/`; explicit negative tests for the directory-crossing case (§15, §26). |
| P-2 | **Uncaught `KeyError`.** `parse_milestone_result` (`:948`) never requires or defaults `milestone`, but callers index `result["milestone"]` (`:1252`, `:1838`), producing a traceback with no `stop_reason` recorded. | The parser validates the complete result shape; every field is typed and required-or-defaulted before any caller reads it (§18). |
| P-3 | **Inconsistent budget accounting.** `correction_round` (`:1388`) and `closure_round` (`:1425`) increment *before* their exit-code checks, so a failed provider call burns the round — the opposite of the careful review accounting three functions earlier. | One shared budget-accounting helper; a round is consumed only after a well-formed result parses (§19). |
| P-4 | **Unreachable retry constant.** `MAX_REVIEW_ATTEMPTS = 3` (`:123`) can never be reached: every failed attempt becomes `HUMAN_INTERVENTION_REQUIRED`, which `resume` refuses (`:1550`). | Either a genuinely resumable provider-failure stop distinct from a safety violation, or no such constant. No vestigial limits (§19). |
| P-5 | **Mutating Git bypasses the guard.** `git add`/`git commit`/`git push` (`:1707`, `:1710`, `:1741`) call `run_command` directly rather than the allowlisted `Repo.git()` wrapper, so the structural guarantee rests on config defaults alone. | All Git access, without exception, routes through the read-only inspector; the commit/push commands are a separate, explicitly gated façade so the guarantee is structural (§20). |
| P-6 | **Unlocked state write.** `cmd_abort` (`:1751`) writes state holding no lock. | Every state-mutating command acquires the run lock (§12). |
| P-7 | **Fragile governance gate.** `governance_check` (`:1073-1101`) scrapes box-drawing characters out of `workflowctl verify`'s rendered table under a forced `LC_ALL=C`; any formatting change breaks the gate unpredictably, in either direction. | Consume machine-readable output, never scraped human rendering (§16). |
| P-8 | **Evidence loss.** `run_verification` (`:1169`) keeps only the last 800 characters of a failed command's output. | Full verification output persisted to disk alongside provider transcripts (§16). |
| P-9 | **Transcript collisions.** Second-granularity `f"{stamp}-{role}"` naming plus `Path.with_suffix` can silently overwrite an earlier transcript. | A monotonic per-run sequence number in every transcript name (§11). |
| P-10 | **Heuristic failure classification.** Recovery re-greps stderr for `"401"`, `"websocket"`, `"connection"` (`:2000-2014`) — substrings that can appear in model-authored text. | A first-class failure class determined at invocation time and persisted with the run; recovery consults the recorded class, never re-greps (§17). |

**Stays external, never migrated:** the prototype's own installed copy; its `state/` directory and
the historical transcripts of run `auto015-20260804T060616Z-dedd54c6` (852 KB), which remain
exactly where they are as immutable historical evidence (§28); and provider authentication, which
the runner never reads, writes, forwards, or stores.

## 7. Architecture — Core Engine Milestone Runner

**Selected architecture (DEC-016-001).** AUTO-016 is a Core Engine capability under
`src/ai_workflow_engine/milestone_runner/`, exposed through one additive `workflowctl` command
group. It does **not** integrate through `agentos_workflow.WorkflowService`.

```text
workflowctl milestone-runner <verb>          (src/ai_workflow_engine/cli.py — parsing/rendering only)
        ↓
MilestoneRunnerApplication                   (application.py — the sole transition authority)
        ↓
RunStateStore   ProviderInvoker   MilestonePlanLoader   ScopeGuard
VerificationExecutor   ReviewCoordinator   RecoveryCoordinator   GitReadOnlyInspector
        ↓
ClaudeCLIAdapter / CodexCLIAdapter           (fixed argv, stdin prompt, bounded timeout)
```

**Why not `agentos_workflow.WorkflowService` — proved, not assumed.** The Human Owner's direction
permits that route only if existing architecture proves it mandatory. It does not:

1. `ARCHITECTURE.md` §4 states the three top-level packages import none of each other's internals
   across the writable-surface boundary. The only `src → agentos_workflow` edge in the entire tree
   is one line — `from agentos_workflow.cli_auto import auto_app` (`src/ai_workflow_engine/cli.py:1268`)
   — importing exactly one CLI sub-app, with a docstring recording that this is deliberately the
   sole edge.
2. `WorkflowService.__init__` requires a `WorkflowConfig`, which is a **target-repository**
   `.agentos/workflow.yaml` (`agentos_workflow/config/loader.py`,
   `DEFAULT_CONFIG_RELATIVE_PATH = Path(".agentos/workflow.yaml")`). This repository has no such
   file, and a milestone runner driving an engine stage is not a target-repository workflow.
3. `WorkflowService` exposes no verb for milestone-sequenced implementation, and AUTO-015 §24
   already lists `agentos_workflow/service.py` as forbidden surface — "unchanged; no adapter or new
   verb is added" — an immediate, accepted precedent for a capability that declines this route.
4. AUTO-015 delivered a complete Core Engine capability under `src/ai_workflow_engine/` with zero
   `agentos_workflow` imports and an AST-level test proving it. AUTO-016 follows that precedent
   exactly.

**Business logic never lives in CLI handlers.** `src/ai_workflow_engine/cli.py` gains one
`typer.Typer` sub-app, one `app.add_typer(..., name="milestone-runner")`, and thirteen thin command
functions. Each parses options, calls exactly one `MilestoneRunnerApplication` method, renders the
typed result, and selects an exit code — the discipline `successor_planning_propose`
(`cli.py:1159-1256`) already establishes.

**Relationship to the canonical state machine.** AUTO-016 owns **no** `WorkflowState`. It defines
its own run-status enum, exactly as `ApprovalStatus` (`agentos_workflow/approvals.py:193`, ten
values), `ImplementerPhase` (`implementer.py:281`), and `MergeCloseoutPhase`
(`merge_closeout.py:161`) already do without `WORKFLOW_STATES.md` ever being amended.
`WORKFLOW_STATES.md` §1 is explicit that it governs "the runtime workflow state machine" only and
"is [never] authority for an AUTO-00x stage's own … state transitions." No new `WorkflowState`
member and no new `ALLOWED_TRANSITIONS` edge is added; both counts (19 and 37) are asserted
unchanged by test.

## 8. Package and Module Surface

```text
src/ai_workflow_engine/milestone_runner/
  __init__.py          docstring-only marker; re-exports nothing (successor_planning precedent)
  models.py            typed run state, milestone plan, results, outcome/failure taxonomy
  config.py            validated runner configuration (§21)
  plan.py              MilestonePlanLoader: load, validate, dependency-order, coverage-reconcile
  state.py             RunStateStore: atomic publication, schema versioning, resume
  lock.py              RunLock: fcntl.flock process lock (§12)
  scope.py             ScopeGuard: cumulative allowlist, per-milestone scope, forbidden paths
  git_inspect.py       GitReadOnlyInspector: read-only Git evidence, drift detection
  approval_git.py      the ONLY module able to construct a mutating Git argv (§20); gated, off by default
  verification.py      VerificationExecutor: bounded command execution and PASS/FAIL classification
  providers/           provider-adapter subpackage, owned by this package (DEC-016-002, §17)
    __init__.py        docstring-only marker; re-exports nothing
    base.py            ProviderInvoker, the shared subprocess discipline, failure taxonomy
    claude_cli.py      ClaudeCLIAdapter (implementation, correction)
    codex_cli.py       CodexCLIAdapter (review, closure; fixed read-only)
  results.py           machine-result grammar, extraction, strict parsing (§18)
  review.py            ReviewCoordinator: budget accounting, severity policy, findings ledger (§19)
  recovery.py          RecoveryCoordinator: reconcile/reopen/recover/revalidate (§13)
  prompts.py           fixed prompt templates and typed-data interpolation
  application.py       MilestoneRunnerApplication: the sole transition authority
```

Nineteen files: fifteen top-level modules plus the four-file `providers/` subpackage.

`__init__.py` re-exports nothing, following `successor_planning/__init__.py`'s recorded rationale
that a marker-only package file means no later module addition requires editing it and no import
of one submodule drags in the rest. `providers/__init__.py` follows the same rule, so adding a
future adapter never edits an existing file.

**`providers/` is a subpackage, not a module, by Human Owner ruling DEC-016-002.** The separation is
load-bearing rather than cosmetic: it gives the adapters — the only part of the package that spawns
an external process on untrusted-output terms — a boundary that the AST tests of §26 can name
directly, keeps each adapter's fixed argv constant beside the adapter that owns it, and makes
"the runner owns its providers" a structural property rather than a comment.

## 9. CLI Contract

One additive Typer sub-app registered as `milestone-runner`, matching the existing hyphenated
group-name convention (`successor-planning`, `check-task-state`):

```bash
workflowctl milestone-runner doctor               --config <PATH>
workflowctl milestone-runner plan                 --config <PATH>
workflowctl milestone-runner start                --config <PATH>
workflowctl milestone-runner resume               --config <PATH>
workflowctl milestone-runner status               --config <PATH> [--json]
workflowctl milestone-runner verify               --config <PATH>
workflowctl milestone-runner reconcile-milestone  --config <PATH> --milestone <ID> --reason <TEXT>
workflowctl milestone-runner reopen-milestone     --config <PATH> --milestone <ID> --reason <TEXT>
workflowctl milestone-runner recover-failed-review --config <PATH> --classification <KIND> --ruling <TEXT>
workflowctl milestone-runner revalidate-correction --config <PATH>
workflowctl milestone-runner approve-commit       --config <PATH>
workflowctl milestone-runner approve-push         --config <PATH>
workflowctl milestone-runner abort                --config <PATH> --reason <TEXT>
```

All twelve capabilities the Human Owner's direction requires are present under their required
names; the existing CLI conventions required no renaming. `verify` is a **thirteenth** command
retained from the prototype (`auto015_runner.py:1633`): a read-only re-run of the safety gates plus
the full verification set. It is called out explicitly here rather than added silently, and may be
struck at authorization without affecting any other command.

Conventions followed: long-form `--kebab-case` options only, no short flags; module-level
`Annotated` option aliases; `--config` naming a validated runner configuration file; exit codes
`0` success / `1` domain failure or tripped gate / `2` operational error via `_protected`.

## 10. Run State Machine

Typed, durable, runner-local states — a `StrEnum` in `models.py`, never a `WorkflowState`:

```text
IDLE  PREFLIGHT  IMPLEMENTING  FOCUSED_VERIFYING  MILESTONE_FAILED  MILESTONE_COMPLETE
FINAL_VERIFYING  REVIEWING  NEEDS_CORRECTION  CORRECTING  CLOSURE_VERIFYING
PROVIDER_WAIT  PROVIDER_RETRY_PENDING
READY_FOR_COMMIT_APPROVAL  READY_FOR_PUSH_APPROVAL  HUMAN_INTERVENTION_REQUIRED  DONE  ABORTED
```

The fifteen states the Human Owner's direction names are present verbatim. Three additions are
justified rather than assumed:

- `MILESTONE_FAILED` — already in the prototype's own vocabulary; distinguishes a milestone whose
  focused verification failed (recoverable via `reopen-milestone`) from a global safety stop.
- `PROVIDER_WAIT` — the durable state during a long provider invocation. Justified by real
  evidence: a recorded implementation invocation ran 1,022 seconds, so a crash mid-invocation is a
  realistic case, and resume must be able to tell "provider was running" from "provider never
  started." This directly serves `MODEL_PROVIDER_CONTRACTS.md` §2's requirement that classification
  turn on **when** a failure occurred, not what kind it was.
- `PROVIDER_RETRY_PENDING` — the bounded-retry state, entered **only** on a proven
  pre-side-effect failure (spawn failure: executable not found, permission denied). Any failure
  after the process started goes to `HUMAN_INTERVENTION_REQUIRED` with reconciliation required
  first, never to a blind retry.

**Transition rules.** `MilestoneRunnerApplication` is the sole transition authority; no adapter,
coordinator, or provider report transitions the run. `ALLOWED_RUN_TRANSITIONS` is an explicit,
closed frozenset asserted by test. Terminal states are `DONE` and `ABORTED`; neither has an
outbound edge. `HUMAN_INTERVENTION_REQUIRED` exits only through an explicit recovery command
(§13), never automatically.

## 11. Durable State Model and Atomicity

**Location.** Run state lives at an external, repository-scoped artifact root — never inside the
worktree, so a runner operating on a repository cannot pollute the diff it is guarding:

```text
~/.ai-workflow-engine/milestone-runs/<repository-id>/
    plans/                the default milestone-plan root (DEC-016-005, §14) — run input
    <run-id>/
        state.json        the typed run record (schema-versioned)
        plan.json         the resolved, validated milestone plan (a snapshot, not the source)
        transcripts/      <NNNN>-<UTC>-<role>.prompt.md | .stdout.txt | .stderr.txt
        run.lock          the flock target (§12)
```

`plans/` is a sibling of the run directories under the same repository-scoped root, so plan input
and run output share one containment check, one identity derivation, and one no-follow discipline.
`<run-id>/plan.json` remains a resolved snapshot written by the runner; it never shadows or
rewrites the source plan.

`<repository-id>` is derived exactly as AUTO-015 fixed it (DEC-002/DEC-010): normalized repository
name plus the first 12 hex characters of SHA-256 over the canonical, credential-free primary remote
identity. The root is verified to resolve **outside** the repository via the same
`_reject_repository_containment` discipline AUTO-015's `store.py:180` implements, and every path
component is opened no-follow with symlink rejection.

**Atomicity.** Every state publication is `write to a namespaced temp file in the same directory →
flush → fsync → os.replace → fsync parent directory`. A crash never leaves a partial `state.json`
at the canonical path. A stale temp file from an interrupted run is namespaced and never mistaken
for state.

**Schema versioning.** `state.json` carries `schema_version`. An unknown version is a hard refusal
(`STATE_SCHEMA_UNKNOWN`), never a best-effort read. Records are typed Pydantic models with
`extra="forbid"`; duplicate JSON keys are rejected on load, matching
`agentos_workflow/orchestrator/state_store.py`'s `_loads_rejecting_duplicate_keys` discipline.

**Recorded fields** (the prototype's proven set, typed): `schema_version`, `run_id`,
`repository_root`, `repository_identity`, `expected_branch`, `baseline_sha`, `contract_sha256`,
`workflow_state`, `stop_reason`, `created_at`, `updated_at`, `current_milestone`,
`completed_milestones`, `changed_paths`, `provider_runs`, `verification_results`,
`blocking_findings`, `deferred_findings`, `approvals`, and the five independent counters and
ledgers of §19 (`review_attempts`, `successful_review_rounds`, `provider_failure_count`,
`correction_round`, `closure_round`) plus the four append-only recovery ledgers
(`reconciliations`, `reopenings`, `review_recoveries`, `revalidations`).

**Transcript names carry a monotonic per-run sequence number** (`<NNNN>`), so two invocations of the
same role within the same second cannot collide — correcting prototype defect P-9, where
second-granularity naming plus `Path.with_suffix` could silently overwrite an earlier transcript.

**Append-only.** Ledgers and transcripts are append-only from the runner's perspective; no record is
ever rewritten or deleted, per `AUDIT_MODEL.md` §4. Provider transcripts are referenced by path,
never inlined into the state record, per `AUDIT_MODEL.md` §2 and `SECURITY_MODEL.md` §1.

**Record shape.** The state document holds current state only; the event log and the audit ledgers
are separate append-only streams. The prototype's single growing blob — rewritten and re-validated
in full on every step, quadratic in run length, and mixing current state with event history — is
not carried over (§6).

## 12. Process Locking and Concurrency

**Finding: no engine-side process lock exists.** A full search of `src/ai_workflow_engine/` returns
zero `fcntl`/`flock` uses; the only production lock in the repository is
`agentos_workflow/orchestrator/lock.py` (`RepositoryLock`, `fcntl.flock` + fd-relative
`O_NOFOLLOW`), which `src/ai_workflow_engine/` may not import (§7) and whose `for_config`
constructor requires a `WorkflowConfig`.

AUTO-016 therefore implements its own `RunLock` in `milestone_runner/lock.py`, adopting
`RepositoryLock`'s **documented disciplines** without importing it — precisely the pattern
AUTO-015's `redaction.py` used when it declined to import `agentos_workflow.skills.redact_secrets`
and its `store.py` used when it chose `os.rename` over `prompt/store.py`'s `os.link` and recorded
why. The disciplines adopted: an OS-level advisory `fcntl.flock` hold is the sole authority; any
metadata written beside it is diagnostic only and never authoritative; the lock file is never
deleted on release (deleting it races a second acquirer onto a different inode and defeats mutual
exclusion); every path component is opened fd-relative with `O_NOFOLLOW`.

Exactly one runner process per canonical repository. Contention is a typed refusal
(`LOCK_CONTENTION`) naming the holding run, never a wait-and-steal. A stale hold from a dead
process is reacquirable because `flock` releases on process exit; **no PID-liveness heuristic is
used** — the prototype's `os.kill(pid, 0)` check is racy under PID reuse and is not carried over.

**Every state-mutating command acquires the lock**, including `abort` — correcting prototype defect
P-6, where `cmd_abort` wrote state holding no lock. The read-only commands (`doctor`, `plan`,
`status`, `verify`) do not acquire it and are safe against torn reads because publication is
atomic (§11).

## 13. Idempotent Resume and Recovery

**Resume.** `resume` reads the durable state and continues from exactly where the run stopped,
re-verifying every §4 entry condition first. Resume never repeats a completed side effect: before
re-invoking a provider for a milestone, the runner reconciles the recorded invocation evidence
against the repository's actual diff, per `MACHINE_GATES.md` §2a — "a possible … provider
invocation … effect is reconciled against its persisted operation evidence before repetition or
transition; appearance alone never advances the workflow." Running `resume` twice with no
intervening change is a no-op success.

**The four recovery commands**, each requiring an explicit reason and each writing an append-only
ledger entry recording the pre-state, the post-state, the budgets touched, and the branch/HEAD at
recovery time:

| Command | Clears | Budget effect | Guard |
|---|---|---|---|
| `reconcile-milestone` | A milestone whose provider result was semantically valid but non-conforming (e.g. the recorded Markdown-fence case) | None | Requires the result file to hash-match its recorded transcript; records `reconstructed_from_verified_evidence` honestly |
| `reopen-milestone` | An unparseable or scope-corrected milestone, under an explicit `human_owner_scope_ruling` | None; `completed_milestones` and all budgets preserved | Prior attempt transcripts preserved, never deleted; a corrected `allowed_files` set must still satisfy §4 item 6 coverage |
| `recover-failed-review` | A review budget consumed by a **provider** failure (the recorded `token_expired` case) | Restores exactly one review budget; requires a typed `classification` and an explicit Human Owner ruling string | Never usable on a review that actually completed and returned a verdict |
| `revalidate-correction` | A post-correction verification failure | None; budgets explicitly untouched | Limited to the already-open blocker IDs; cannot introduce new findings |

No recovery command may widen an allowlist beyond the authorized contract surface, raise a budget
above its configured ceiling, mark a blocker closed, or move the run directly to
`READY_FOR_COMMIT_APPROVAL`.

## 14. Milestone Plan Format

A versioned, typed schema. Thirteen required fields and two optional, matching the prototype's
proven `milestone.schema.json` (`additionalProperties: false`):

```yaml
schema_version: 1                    # required; unknown version is a hard refusal
milestone_id: AUTO-0XX-M02           # required; grammar ^AUTO-[0-9]{3}-M[0-9]{2}$
title: ...                           # required
objective: ...                       # required
depends_on: [AUTO-0XX-M01]           # required; must form an acyclic graph
contract_sections: [...]             # required; the contract sections this milestone implements
allowed_files: [...]                 # required; this milestone's exact writable scope
forbidden_files: [...]               # required
required_symbols: [...]              # required; verified present after implementation
explicit_exclusions: [...]           # required; what this milestone must NOT do
acceptance_criteria: [...]           # required
focused_verification: [...]          # required; command + optional purpose
completion_evidence: [...]           # required
additive_reuse_justification: ...    # optional; required when reusing an existing primitive
human_owner_scope_ruling: ...        # optional; written only by reopen-milestone
```

Validation is fail-closed: unknown fields rejected, unknown `schema_version` rejected, dependency
cycles rejected naming the full cycle, duplicate `milestone_id` rejected, and the union of every
`allowed_files` reconciled against the configured `required_coverage` exactly.

**Plan location (DEC-016-005 — ruled).** A milestone plan is run input, not a governance document.

1. **The default plan root is external to the target repository:**
   `~/.ai-workflow-engine/milestone-runs/<repository-id>/plans/`. `<repository-id>` is derived
   exactly as in §11, so the plan root and the run root share one identity and one containment
   check. With no `stage.plan_directory` configured, this default is used and nothing inside the
   worktree is consulted.
2. **Repository-local plans are permitted only by explicit contract allowlisting.** A plan path
   inside the worktree is accepted only when the *governing stage contract's* implementation
   allowlist lists that **exact path** — not a directory, not a glob, not a prefix. The runner
   verifies the listing at load and refuses otherwise (`PLAN_PATH_NOT_ALLOWLISTED`).
3. **Arbitrary repository-local plan discovery is forbidden.** There is no search, walk, glob,
   default-directory scan, or "nearest plan wins" behaviour anywhere in the package. Every plan
   path is either the external default root or an exact allowlisted path; a configured plan
   directory that resolves inside the worktree without satisfying rule 2 is refused at load, before
   any provider is invoked.

The reasoning behind the default is that fixing plans inside `docs/` would make every run a
governance edit, and letting the runner *discover* plans inside the worktree would let a file the
runner is supposed to be guarding decide what the runner is allowed to change. The narrow exception
keeps a deliberately contract-published plan possible without reopening discovery: the escape hatch
is a written allowlist entry a human authored, not a path the runner found.

## 15. Scope Guard

Three independent checks, all evaluated after every provider invocation and before every
transition:

**Path matching is segment-aware.** `*` matches within one path segment and never crosses `/`;
`**` is the only construct that spans segments. This is a required correction of prototype defect
P-1 (§6), where `fnmatch` semantics silently widened `tests/test_*.py` to match
`tests/test_pkg/inner.py`. Matching is performed on normalized, repository-relative POSIX paths.

1. **Cumulative allowlist** — every changed path (tracked modifications plus untracked files) must
   match `allowlist.allowed_paths`, the authorized stage contract's implementation surface.
2. **Per-milestone scope** — every changed path must additionally match the *current* milestone's
   own `allowed_files`. A path inside the cumulative allowlist but outside the active milestone is
   a stop (`OUT_OF_MILESTONE_SCOPE`), not a warning.
3. **Forbidden paths** — any match against `allowlist.forbidden_paths` is an immediate stop,
   evaluated with forbidden taking precedence over allowed.

`SECURITY_MODEL.md` §7 is binding here: "scope creep is a validation failure, not a warning." On
any violation the runner stops at `HUMAN_INTERVENTION_REQUIRED` and leaves every file exactly as
found — it never reverts, restores, checks out, resets, stashes, or deletes the offending change.

Branch, HEAD, and repository identity are re-read and compared at each gate; any drift is a stop.

## 16. Verification Execution

Commands come from validated configuration as argv **lists**, never shell strings; there is no
`shell=True` path anywhere in the package (AST-asserted, §22). Each command runs with a bounded
timeout, in the configured environment (the conda environment's `bin` prepended to `PATH`), with
stdout/stderr captured, truncated at an explicit ceiling, and recorded with exit code and duration.

Exit code `0` is `PASS`; anything else is `FAIL`; a timeout is `FAIL` with `timed_out: true` — never
success. `WORKFLOW_STATES.md` §5a item 6's "a workflow never reports success solely because a
command timed out" is binding.

**Full output is persisted**, not truncated to a tail — correcting prototype defect P-8. Each
command's complete stdout and stderr are **sanitized (§17a) and then** written to the run's
transcript directory and referenced by path in the record, exactly as provider transcripts are; the
record itself carries only the exit code, duration, timeout flag, and references.

**The governance gate consumes machine-readable output**, never a scraped human-rendered table —
correcting prototype defect P-7. The gate is evaluated from structured check results, so a change
in `workflowctl`'s console formatting can neither silently open nor silently close it.

Focused verification is milestone-scoped and runs after every milestone. The full verification set
runs once at `FINAL_VERIFYING` and again at `CLOSURE_VERIFYING` if a correction round occurred.
`workflowctl verify`'s four unconditional checks are run individually so the `git` check can be
evaluated against the single documented `upstream_missing` tolerance (§4 item 7) without loosening
the others.

## 17. Provider Boundary

Two adapters — `ClaudeCLIAdapter` (implementation, correction) and `CodexCLIAdapter` (review,
closure) — behind one `ProviderInvoker`, all inside the package-owned
`milestone_runner/providers/` subpackage (DEC-016-002).

**Requirements, each testable:**

- **Command templates from validated configuration.** A closed, typed template: executable, fixed
  argument vector, and a small set of named interpolation slots (`{repo_root}`,
  `{last_message_path}`). Never a caller-supplied command string, never a shell.
- **Closed capability enums.** Claude's permission mode and Codex's sandbox mode are closed enums
  that **cannot express** `bypassPermissions` or `danger-full-access` — not values rejected at load
  but values the type system cannot represent, exactly as `agentos_workflow/config/policy.py`
  already does and `CONFIGURATION_MODEL.md` §4 requires. Codex's review invocation is fixed
  read-only. Defaults are the least-capable mode.
- **Stdin prompt delivery.** The prompt is always written to the child's stdin, never passed as an
  argument, so it never appears in a process listing.
- **Bounded timeout**, per provider, from configuration, required — no default.
- **Captured stdout/stderr** with explicit byte ceilings, sanitized per §17a, then written to
  durable transcript files.
- **Durable transcripts.** Every invocation writes prompt, stdout, and stderr (and, for Codex, the
  last-message file). Transcripts are referenced by path in the run record, never inlined
  (`AUDIT_MODEL.md` §2).
- **Exit-code handling and failure classification** into a typed taxonomy: `SPAWN_FAILED`,
  `TIMEOUT`, `COMMAND_FAILED`, `MALFORMED_OUTPUT`, `AUTH_FAILED`, `TRANSPORT_FAILED`,
  `PROVIDER_REPORTED`. Classification turns on **when** the failure occurred, never on error text
  alone (`MODEL_PROVIDER_CONTRACTS.md` §2). The class is **determined at invocation time and
  persisted with the run record**; recovery consults the recorded class and never re-greps stderr.
  This corrects prototype defect P-10, where recovery matched substrings such as `"401"`,
  `"websocket"`, and `"connection"` against output that a model may itself have authored.
- **Bounded retries.** Retry is permitted **only** for `SPAWN_FAILED` — the sole provably
  pre-side-effect class — capped at 3 attempts, counted in a durable counter kept independent of
  both the repair counter and the review budget (`WORKFLOW_STATES.md` §5: three separate counters,
  never conflated). Every other failure requires reconciliation before any repetition.
- **No credential storage.** The runner never reads, writes, forwards, logs, or stores provider
  authentication; it inherits whatever the installed CLIs already use. Only an explicit
  `allowed_environment_variables` allowlist is forwarded, with no wildcard permitted
  (`SECURITY_MODEL.md` §1, `CONFIGURATION_MODEL.md` §4).
- **No recursive provider invocation.** A provider is never invoked from inside a provider's own
  handling path; the invocation count per milestone is structurally bounded and asserted.
- **Session isolation.** Claude and Codex never share process state, prompts, or raw output.
  Codex receives only the diff, the changed-path list, and the deterministic verification results —
  never Claude's transcript or reasoning (`SECURITY_MODEL.md` §3,
  `MODEL_PROVIDER_CONTRACTS.md` §5).
- **Strict result parsing** per §18.

**Provider-adapter ownership (DEC-016-002 — ruled).** The Human Owner ruled that provider adapters
live under `src/ai_workflow_engine/milestone_runner/providers/` and are owned by the AUTO-016
milestone-runner package, and that the `agentos_workflow` provider runtime must **not** be reused
directly. The ruling is binding; the alternative (importing `agentos_workflow/providers/**`) is
closed and may not be reopened at implementation time.

The ruling is consistent with the evidence gathered for this contract: that package is forbidden
surface under AUTO-015 §24, its `ProviderRuntime` requires a target-repository `WorkflowConfig`, and
importing it would breach `ARCHITECTURE.md` §4. The honest cost — a second subprocess implementation
in the tree — is accepted deliberately and mitigated by adopting `base.run_provider_process`'s
documented disciplines verbatim (fixed argv from a provider-owned constant, no shell, `Popen` with
process-group termination on timeout, bounded stream readers, environment allowlisting, normalized
command identity in records), by copying no code, and by an AST-level test proving no
`agentos_workflow` import exists anywhere in the package (§22 invariant 6). "Adopt the discipline,
import nothing" is the operative rule; a future convergence of the two implementations would be its
own stage with its own authorization, never a silent refactor under this one.

**The ruling's seven adapter requirements** are each already specified above and each carry a named
test in §26: validated configuration (closed typed templates, no caller-supplied strings); stdin
prompt delivery; bounded per-provider timeout with no default; captured stdout/stderr with byte
ceilings; durable transcripts referenced by path; strict result parsing (§18); and no credential
storage of any kind. None is advisory.

## 17a. Sanitization Before Persistence

`SECURITY_MODEL.md` §1 requires that command output "is sanitized before it is referenced in an
audit record or report," and `AUDIT_MODEL.md` §2 goes further: "Sanitization (secret redaction)
happens **before** a reference file is written; the audit record itself never contains a raw
credential, **even in a referenced file**." Referencing rather than inlining is therefore necessary
but **not sufficient** — the referenced file must itself be clean.

Accordingly, **no byte is written to any transcript, verification-output, or state file before
passing through redaction.** This applies to provider stdout, provider stderr, Codex's last-message
file, every verification command's output, and every rendered prompt. Redaction is applied at the
single write boundary in `state.py`, so no call site can bypass it; an AST-level test asserts that
no module writes to the state root except through that boundary.

**Redaction utility (DEC-016-008).** The runner reuses
`ai_workflow_engine.successor_planning.redaction.redact_text` — AUTO-015's self-contained,
linear-time (ReDoS-safe), non-reversible redactor. This is an intra-package import within
`src/ai_workflow_engine/`, not a cross-package boundary crossing, so `ARCHITECTURE.md` §4 is not
engaged and AUTO-015's reason for *declining* to import
`agentos_workflow.skills.redact_secrets` does not apply here. `successor_planning/` is read and
imported, never modified, which §24 already permits. Duplicating a security primitive rather than
reusing it would be the worse choice: two redactors drift, and the weaker one becomes the
vulnerability. If transcript-scale content proves to need patterns the existing utility lacks, a
runner-local **extension** is added in `milestone_runner/`, with the gap documented — the shared
utility is still not modified.

**Honest limitation.** Redaction is defense in depth, not a guarantee. It cannot recognize every
credential shape, and a novel secret format may survive it. The contract states this plainly rather
than claiming the transcripts are provably clean. The primary control remains §22 invariant 1: the
runner never reads, forwards, or handles credentials in the first place, so a secret can reach a
transcript only if a provider itself emits one.

**Redaction events are recorded, never silent** — a redaction produces a counted, visible finding
on the run record, so an operator can see that secret-shaped content was present and neutralized.

## 18. Machine-Result Grammar and Parsing

Each provider role returns exactly one machine-readable block delimited by role-specific sentinels,
the prototype's proven grammar:

```text
AUTO016_MILESTONE_RESULT   … END_AUTO016_MILESTONE_RESULT
AUTO016_CORRECTION_RESULT  … END_AUTO016_CORRECTION_RESULT
AUTO016_REVIEW_RESULT      … END_AUTO016_REVIEW_RESULT
AUTO016_CLOSURE_RESULT     … END_AUTO016_CLOSURE_RESULT
```

Parsing rules, all fail-closed:

- The block body is parsed with a **safe** YAML loader; no arbitrary object construction.
- **Exactly one optional Markdown fence is tolerated** around the block — the empirically observed
  case (§6) — and tolerating it weakens nothing else: the fence is stripped before parsing and the
  body must still satisfy every schema rule. Two fences, a partial fence, text after the end
  sentinel, more than one block, a missing sentinel, or a mismatched sentinel pair are all
  rejected.
- The parsed body is validated against a typed model with `extra="forbid"`, **completely, before
  any caller reads a field**. Every field is required or explicitly defaulted at the parser
  boundary. This corrects prototype defect P-2, where a result block missing its `milestone` key
  passed the parser and raised an uncaught `KeyError` in the caller — a traceback with no
  `stop_reason` recorded.
- Semantic contradictions are rejected as malformed: a `BLOCKED` verdict with no blockers, an
  `APPROVED` verdict carrying blockers, a blocker whose severity is not Critical or High, or more
  blockers than the configured `max_blockers`.
- **A rejected result never destroys evidence.** The raw stdout, stderr, and prompt transcripts are
  preserved and referenced from the stop record, so a human can inspect exactly what the provider
  said (`SECURITY_MODEL.md` §1's file-reference discipline).
- Untrusted provider text is data, never control: no provider output is ever interpolated into a
  later prompt's directive sections, only into clearly data-scoped quoted regions.

## 19. Review Policy and Budget Accounting

Default policy, validated at load; the runner refuses to start if any value exceeds its ceiling:

```yaml
max_full_reviews: 1
max_correction_rounds: 1
max_closure_reviews: 1
max_blockers: 3
blocking_severities: [critical, high]
defer_severities: [medium, low]
```

Exactly one full review, one correction round, one closure verification by default. Medium and Low
findings go to a deferred ledger and never block. If a blocker remains open after the single
correction round, the run stops at `HUMAN_INTERVENTION_REQUIRED`.

**One shared budget-accounting helper owns every counter.** A round — review, correction, or
closure — is consumed **only after a well-formed result parses**, never before the provider's exit
code is known. This corrects prototype defect P-3, where `correction_round` and `closure_round`
incremented ahead of their exit-code checks while the review counter did not, leaving three
counters with two different meanings. No counter has a ceiling that no code path can reach
(defect P-4).

**Provider attempts and consumed review budgets are separate durable counters.**
`review_attempts` counts invocations; `successful_review_rounds` counts reviews that actually
returned a well-formed verdict; `provider_failure_count` counts failures. A provider failure —
authentication expiry, timeout, spawn failure, unparseable output — increments the failure counter
and **never** consumes `successful_review_rounds`. This is not a theoretical nicety: the recorded
run consumed a review budget to a `token_expired` failure and required an explicit recovery act to
restore it (§6, §13).

Closure verification is strictly limited to the already-open blocker IDs. It may mark them `CLOSED`
or leave them open; it may not introduce a new finding, and a closure result naming an unknown
finding ID is rejected as malformed.

## 20. Human Gates and Git Authority

AUTO-016 must never automatically: authorize a stage; change task or Registry state; accept a scope
expansion; accept a Critical or High finding; commit; push; create a pull request; merge; or delete
a branch.

**Git authority is print-only by default.** `approve-commit` and `approve-push` print the exact
commands and execute nothing. Executing requires **both** an explicit configuration flip
(`git.execute_commit` / `git.execute_push`, both defaulting to `false`) **and** an interactive
typed confirmation (`APPROVE COMMIT` / `APPROVE PUSH`). This double gate is the prototype's proven
design and matches `HUMAN_AUTHORIZATION_MODEL.md` §5a constraint 6 and `MACHINE_GATES.md` §4a's
established discipline: a dangerous capability is opt-in **at the point of use** and is refused
when inherited from a built-in or project-wide default. `self-governance.yaml`'s
`allow_automatic_commit: false` / `allow_automatic_push: false` remain independently binding for
this repository.

**The commit approval is bound, invalidated, and single-use.** `HUMAN_AUTHORIZATION_MODEL.md` §5a's
approval constraints are adopted in full for both gates, because a commit gate is exactly the kind
of approval that section governs:

- **Bound to the state it was granted against** (constraint 4) — the recorded approval carries the
  repository identity, the branch, the baseline SHA and current HEAD, the canonical changed-path
  set, the digest of every changed file (the exact staged diff or commit payload), the final
  verification result set, the review verdict with its finding IDs, and **the exact operation it
  authorizes** (commit or push, never both, never a substitute).
- **Invalidated by any change** — branch drift, HEAD drift, changed-path or digest drift, a
  verification failure, expiry, or prior use each void the approval and the gate refuses; it is
  never silently re-bound.
- **Single-use** (constraint 5) — one approval authorizes exactly one execution; a second
  execution requires a fresh approval.
- **Evidence, never authority** (constraint 2) — the approval does not itself transition the run;
  `MilestoneRunnerApplication` decides, and a failed deterministic gate still fails with an
  approval in hand (constraint 3). There is no override path.
- **Never inherited** (constraint 6) — the configuration flip and the typed confirmation are both
  required at the point of use; neither can be satisfied by a project-wide or built-in default.
- **Durably recorded** — every approval and every consumption is an append-only record noting
  whether a human supplied the confirmation, so an ungated execution could never be mistaken for a
  gated one.

**Two Git surfaces, and only two.** All Git access is routed through one of exactly two modules;
there is no third path and no raw subprocess call to `git` anywhere else in the package. This
corrects prototype defect P-5, where `git add`, `git commit`, and `git push` called the raw
subprocess helper directly and bypassed the allowlisted wrapper entirely, leaving the guarantee
resting on configuration defaults rather than on structure.

1. **`GitReadOnlyInspector`** — used by every state, gate, and coordinator. It accepts only an
   allowlist of read-only subcommands. `checkout`, `switch`, `reset`, `clean`, `stash`, `rebase`,
   `merge`, `cherry-pick`, `revert`, `branch -d/-D`, `fetch`, `pull`, `commit`, and `push` are all
   unreachable through it — not policy comments but argv shapes that cannot express them, exactly
   as `SECURITY_MODEL.md` §2 requires ("argv shapes that make the forbidden operations unreachable,
   not merely policy comments").
2. **`approval_git.py`** — the single gated façade, able to construct exactly two mutating argv
   shapes (`add` + `commit`, and `push`) and nothing else. It is reachable only from the two
   approval commands, only in their two approval states, and only with the configuration flip, the
   typed confirmation, and a bound single-use approval all satisfied. **Every other destructive
   subcommand in the list above remains unreachable from this module too** — it cannot express
   `reset`, `clean`, `stash`, `rebase`, `checkout`, `merge`, or a branch deletion at all.

No `gh` CLI invocation exists anywhere in the package, so no pull request is ever opened and no
merge is ever performed. There is no `--admin` path and no branch-protection override, per
`SECURITY_MODEL.md` §4, whose §10 makes any relaxation permanently out of scope.

## 21. Configuration Model

A validated, typed configuration file named by `--config`, distinct from `self-governance.yaml`.
Sections mirror the prototype's proven shape, promoted to Pydantic v2 `StrictModel`
(`extra="forbid"`): `schema_version`, `repository` (root, expected branch, baseline SHA,
environment), `stage` (contract path and SHA-256, optional plan directory), `allowlist` (allowed,
forbidden,
required coverage), `review_policy`, `git` (both flags defaulting to `false`), `providers`
(closed-enum capability modes, argv templates, required timeouts,
`allowed_environment_variables`), and `verification` (focused and final command sets with
per-command timeouts).

`stage.plan_directory` is **optional**; when omitted the external default root of §14 rule 1 is
used. When present it must resolve either outside the worktree under the repository-scoped artifact
root, or — for a repository-local plan — to an exact path the governing stage contract's
implementation allowlist lists verbatim (§14 rule 2). Any other value is refused at load. No
configuration key enables plan discovery; none exists to add.

Binding rules: every path field resolves inside the repository or an explicitly configured external
state root — nothing outside either boundary; `allowed_environment_variables` may never contain a
wildcard; no value is globally hard-coded in the engine (`CONFIGURATION_MODEL.md` §1 —
"`main` … has no special status to the engine"); review-budget ceilings and the fixed retry cap are
present for explicitness and auditability, not as knobs to raise a limit; and every
capability-granting field is a closed enum defaulting to the least-capable mode.

**No `self-governance.yaml` change and no `pyproject.toml` change is required.** Wheel `packages`,
`mypy.files`, and `pytest.testpaths` all name whole trees, so a new subpackage is covered
automatically — the same reasoning AUTO-015 §23.4 verified and this contract re-verified.

## 22. Security Invariants

Each has a corresponding negative test required in §26.

1. **No credential storage or forwarding** — no token, key, or account identifier is read, written,
   logged, or embedded anywhere; only the explicit non-wildcard environment allowlist is forwarded.
2. **Transcripts sanitized before writing, and referenced rather than inlined** — provider output
   lives in files under the state root and is referenced by path in every record, **and every byte
   passes through redaction at the single write boundary before it reaches disk** (§17a), because
   `AUDIT_MODEL.md` §2 forbids a raw credential even inside a referenced file. A test writes
   secret-shaped provider output and asserts it appears nowhere on disk.
3. **No shell** — no `shell=True`, no `os.system`, no `subprocess` call built from a string,
   anywhere in the package (AST-asserted).
4. **Structural Git non-mutation outside the approval façade** — no mutating Git subcommand is
   reachable from any module except `approval_git.py` (§20), which is the single module permitted
   to construct a mutating argv and is itself reachable only from the two approval commands in
   their two approval states, under both the configuration flip and the typed confirmation. Stated
   precisely rather than absolutely: AUTO-016 *does* have a human-gated commit/push capability by
   the Human Owner's direction ("commit and push commands must be gated and disabled by default"),
   and an invariant claiming no mutating argv exists anywhere would contradict §20. The AST test
   therefore asserts (a) zero mutating Git subcommands in the other eighteen files of §8, and
   (b) that `approval_git.py` has exactly one caller path, from the approval commands.
5. **No GitHub access** — no `gh` invocation and no network call anywhere in the package.
6. **No `agentos_workflow` import** from `src/ai_workflow_engine/milestone_runner/*`
   (AST-asserted), preserving `ARCHITECTURE.md` §4.
7. **State root outside the repository** — the artifact root provably resolves outside the
   worktree; a root that would land inside is refused.
8. **Symlink and path-escape rejection** — every path component is resolved no-follow; a symlinked
   component or traversal-shaped path is rejected, never followed.
9. **Atomic publication** — no crash point leaves a partial or torn state record at the canonical
   path.
10. **Single-holder mutual exclusion** — two concurrent runners against the same canonical
    repository cannot both hold the lock.
11. **Budget integrity** — no provider failure consumes a successful-review budget; no code path
    raises a configured ceiling at runtime.
12. **Scope integrity** — no runtime path widens the cumulative allowlist or a milestone's
    `allowed_files`; a forbidden path always loses to nothing.
13. **Non-destruction** — no code path resets, restores, stashes, rebases, cleans, checks out, or
    deletes repository work, under any condition, including every failure path (AST- and
    behaviour-asserted).
14. **Untrusted provider text is data, never control** — provider output never reaches a later
    prompt's directive sections and never alters a computed verdict.
15. **Evidence preservation** — a rejected or failed provider result never deletes its transcripts.
16. **Governance non-mutation** — a live acceptance run proves every authoritative governance
    document's content and mtime are byte-identical before and after.
17. **Capability modes unrepresentable** — no configuration, request, or call site can express
    Claude's `bypassPermissions` or Codex's `danger-full-access`.
18. **No fabricated success** — a timeout, a missing result block, or an unparseable result is
    never recorded as a pass.
19. **No plan discovery inside the repository** (DEC-016-005) — plan input comes from the external
    default root or from an exact contract-allowlisted path, never from a search, walk, glob, or
    default scan of the worktree. A repository-local plan path that the governing contract does not
    list verbatim is refused at load, before any provider runs.
20. **Provider adapters are package-owned** (DEC-016-002) — every provider-spawning call site lives
    under `milestone_runner/providers/`, and no other module in the package constructs a provider
    argv or spawns a provider process (AST-asserted, complementing invariant 6).

## 23. Allowed Future Implementation Surface

### 23.1 Core package (new)

Every file listed in §8, under `src/ai_workflow_engine/milestone_runner/` — **nineteen files**:
fifteen top-level modules plus the four files of the `providers/` subpackage
(`providers/__init__.py`, `providers/base.py`, `providers/claude_cli.py`,
`providers/codex_cli.py`), whose existence and location are fixed by DEC-016-002. No file outside
this list may be created under the package without a fresh Human Owner ruling.

### 23.2 CLI surface

- `src/ai_workflow_engine/cli.py` — additive only: one import of the application entry points, one
  `typer.Typer` sub-app, one `app.add_typer(..., name="milestone-runner")`, and the thirteen thin
  command functions of §9. **No existing command is moved, renamed, or changed.**

### 23.3 New tests

- `tests/test_milestone_runner_plan.py` (also covers DEC-016-005 plan-root resolution and refusal)
- `tests/test_milestone_runner_state.py`
- `tests/test_milestone_runner_lock.py`
- `tests/test_milestone_runner_scope.py`
- `tests/test_milestone_runner_providers.py` (also covers the DEC-016-002 ownership boundary)
- `tests/test_milestone_runner_results.py`
- `tests/test_milestone_runner_review.py`
- `tests/test_milestone_runner_recovery.py`
- `tests/test_milestone_runner_application.py`
- `tests/test_milestone_runner_security.py`
- `tests/test_milestone_runner_acceptance.py`
- CLI tests appended to the existing `tests/test_cli.py`.

All engine-side tests live in the flat `tests/` directory, matching the convention that CLI tests
follow the CLI (`tests/test_cli_auto.py` sits there even though `auto_app` lives in
`agentos_workflow`).

### 23.4 Files expected to need NO change (confirmed by direct inspection)

`pyproject.toml` (wheel `packages`, `mypy.files`, and `pytest.testpaths` all name whole trees; no
new pytest marker is required because live acceptance reuses the existing `live_cli` marker rather
than introducing a second exclusion, which would also require editing `addopts`);
`self-governance.yaml`; `src/ai_workflow_engine/{config,models,result,exceptions}.py`;
`src/ai_workflow_engine/git/**`, `governance/**`, `prompt/**`, `successor_planning/**`
(read for pattern reuse only); `.pre-commit-config.yaml`; `.github/workflows/ci.yml`.

### 23.5 Documentation/report files

`docs/reports/workflow-automation/AUTO-016-completion-report.md`, created only on actual future
implementation.

Every path above has a stated rationale; none is included merely because it may be convenient.

## 24. Explicitly Forbidden Surface

Must remain unchanged unless a direct blocker is independently proved (none is known today, §29):

- `agentos_workflow/**` in its entirety — `orchestrator/{engine,lock,state_store}.py`,
  `providers/**`, `implementer.py`, `merge_closeout.py`, `approvals.py`, `service.py`,
  `cli_auto.py`, `skills/**`, `agents/**`, `config/**`. Neither modified nor imported by the new
  package (AST-asserted, §22 invariant 6).
- `agentos_dashboard/**` — no relationship to this scope.
- `src/ai_workflow_engine/{git,governance,prompt,successor_planning,workflow,agents,commit,handover,migration,reporting,schema}/**`
  and `src/ai_workflow_engine/{config,models,result,exceptions}.py` — read for pattern reuse, and
  in the single case of `successor_planning.redaction.redact_text` imported (§17a, DEC-016-008);
  **no content in any of them is modified**. The closed 7-member `WorkflowStage` `Literal` is not
  extended.
- `docs/TASK_QUEUE.md`, `docs/current_task.md`, `docs/remaining_tasks.md`, `docs/DECISION_LOG.md`,
  `docs/PROJECT_STATE.md`, `docs/CONTEXT.md`,
  `docs/workflow-automation/STAGE_REGISTRY.md`, `docs/workflow-automation/OPEN_QUESTIONS.md`,
  every other `docs/workflow-automation/stage-prompts/*.md`, `handover/**` — read-only at runtime,
  unconditionally.
- `pyproject.toml`, `.pre-commit-config.yaml`, `.github/**`, `self-governance.yaml`, `scripts/**`.
- **Any repository-local milestone-plan directory** — AUTO-016 creates none, and the implementation
  adds no plan files under `docs/` or anywhere else in the worktree. Plans live at the external
  default root (§14 rule 1); a repository-local plan is possible only when a *future* governing
  stage contract lists its exact path in that contract's own allowlist, which is that contract's act
  and not AUTO-016's (DEC-016-005).
- **The local prototype runner** (`~/.local/share/auto015-runner/`) — never modified, deleted,
  moved, imported, vendored, or copied into the repository by AUTO-016 (§28). Under DEC-016-006 it
  **remains unchanged in full** until AUTO-016 live acceptance succeeds; the post-acceptance
  deprecation note is a separate operator act, never an implementation step, and deletion is barred
  outright pending a separate explicit Human Owner decision.
- Any deferred defect not proven to directly block AUTO-016 — D-14, D-15, D-16 (AUTO-013); OD-6,
  OD-7, OD-10, OD-11, OD-12 (`OPEN_QUESTIONS.md`, all re-verified `Open` and explicitly
  "blocks nothing's authorization" as of this revision) — investigated in §29 and confirmed
  non-blocking; none may be silently bundled into this stage.

## 25. Verification Plan

Exact commands, reusing the canonical set AUTO-013/AUTO-014/AUTO-015 established (no new command
invented):

- `pytest -q` — full suite; AUTO-016's own tests run inside the default selection.
- `pytest -q -m live_cli -rs` — the existing live suite must remain green, and AUTO-016's real-CLI
  smoke tests are added **under this same marker** so they stay excluded from the default run.
- `ruff check .`
- `black --check .`
- `mypy --strict`
- `pre-commit run --all-files`
- `pip wheel --no-deps` — packaging verification.
- Out-of-tree import check (fresh venv, wheel installed, `cwd` outside the repository) — confirms
  `ai_workflow_engine.milestone_runner` imports cleanly.
- `workflowctl verify --config self-governance.yaml` — before and after every test and acceptance
  run, proving AUTO-016's own suite never perturbs this repository's governance state.
- `git diff --check`.
- Changed-path allowlist check: `git diff --stat main` restricted to exactly §23's surface.
- AST-level proofs, anywhere in the new package: no `agentos_workflow` import; no
  `shell=True`/`os.system`; no `gh` invocation; no network call; and **no mutating Git subcommand
  outside the single gated `approval_git.py` module**, which must additionally be shown to have
  exactly one caller path, from the two approval commands (§22 invariant 4). The mutating-Git proof
  is scoped this way deliberately: an unqualified package-wide claim would contradict §20's
  human-gated, default-disabled commit/push capability.
- Process/environment proof that no `claude`/`codex` subprocess is spawned by any non-live test.

## 26. Test Matrix

**Unit and model** — `TestPlanSchema` (thirteen required fields; unknown field rejected; unknown
`schema_version` rejected), `TestPlanDependencyOrder`, `TestPlanDependencyCycle` (full cycle
named), `TestPlanDuplicateMilestone`, `TestPlanCoverageMismatch` (gap and extra each detected),
`TestConfigValidation` (every §21 rule), `TestConfigRejectsWildcardEnvironment`,
`TestCapabilityModeUnrepresentable`.

**Plan location (DEC-016-005)** — `TestDefaultPlanRootIsExternal` (no `stage.plan_directory` →
`~/.ai-workflow-engine/milestone-runs/<repository-id>/plans/`, and nothing in the worktree is
opened), `TestPlanRootSharesRepositoryIdentityDerivation`,
`TestRepositoryLocalPlanRefusedWhenNotAllowlisted` (`PLAN_PATH_NOT_ALLOWLISTED`),
`TestRepositoryLocalPlanAcceptedOnlyOnExactAllowlistedPath` (a directory entry, a glob, and a
prefix each rejected; only the verbatim path accepted), `TestNoPlanDiscoveryInWorktree` (AST and
behavioural: no walk, glob, or default scan of the repository exists),
`TestPlanRootSymlinkEscapeRejected`, `TestResolvedPlanSnapshotNeverRewritesSourcePlan`.

**State machine** — `TestAllowedRunTransitions` (the closed frozenset asserted exactly),
`TestTerminalStatesHaveNoExit`, `TestHumanInterventionExitsOnlyViaRecovery`,
`TestSoleTransitionAuthority` (no coordinator or adapter mutates state),
`TestNoWorkflowStateExtension` (19 members and 37 edges unchanged).

**Parser** — `TestResultGrammarPerRole`, `TestSingleOptionalFenceTolerated`,
`TestDoubleFenceRejected`, `TestPartialFenceRejected`, `TestTextAfterEndSentinelRejected`,
`TestMissingBlockRejected`, `TestMultipleBlocksRejected`, `TestMismatchedSentinelsRejected`,
`TestUnsafeYamlConstructRejected`, `TestBlockedVerdictWithNoBlockersRejected`,
`TestApprovedVerdictWithBlockersRejected`, `TestNonBlockingSeverityInBlockersRejected`,
`TestBlockerCapExceededRejected`, `TestRejectedResultPreservesTranscripts`.

**Fake provider** — `TestHappyPathAllMilestones`, `TestOneCorrectionRound`,
`TestStillBlockedAfterCorrection`, `TestUnparseableProviderOutput`, `TestProviderSpawnFailure`,
`TestProviderTimeoutIsNotSuccess`, `TestProviderAuthenticationFailure`,
`TestTransportFailureClassification`, `TestNoRecursiveProviderInvocation`,
`TestSessionIsolation` (Codex never receives Claude's transcript).

**Provider ownership (DEC-016-002)** — `TestProviderSpawnOnlyFromProvidersSubpackage` (AST: no
provider argv construction or process spawn outside `milestone_runner/providers/`),
`TestNoAgentosWorkflowProviderImport` (AST, specific to `agentos_workflow.providers`),
`TestAdapterUsesStdinNotArgvForPrompt`, `TestAdapterTimeoutRequiredNoDefault`,
`TestAdapterTranscriptsWrittenForEveryInvocation`, `TestAdapterStoresNoCredential`.

**Process lock** — `TestLockContentionRefused`, `TestLockReleasedOnProcessExit`,
`TestLockFileNotDeletedOnRelease`, `TestLockPathSymlinkRejected`,
`TestConcurrentRunnersMutuallyExcluded`.

**Interruption and resume** — `TestResumeAfterInterruptDuringImplementing`,
`TestResumeAfterInterruptDuringVerification`, `TestResumeIsIdempotent`,
`TestResumeReconcilesBeforeReinvoking`, `TestResumeRejectsBranchDrift`,
`TestResumeRejectsHeadDrift`, `TestResumeRejectsSchemaVersionUnknown`.

**Atomicity** — `TestCrashBeforeRenameLeavesNoPartialState`,
`TestCrashAfterFsyncBeforeRenameRecoverable`, `TestOrphanTempFileNeverMistakenForState`,
`TestDuplicateJsonKeysRejected`, `TestStateRootOutsideRepositoryEnforced`.

**Scope violation** — `TestForbiddenPathStop`, `TestOutsideCumulativeAllowlistStop`,
`TestOutOfMilestoneScopeStop`, `TestForbiddenBeatsAllowed`, `TestUntrackedFileCounted`,
`TestNoRuntimeAllowlistWidening`, `TestStopLeavesWorkingTreeByteIdentical`.

**Review accounting** — `TestProviderFailureDoesNotConsumeReviewBudget`,
`TestSuccessfulReviewConsumesExactlyOne`, `TestBudgetCeilingRefusedAtLoad`,
`TestClosureLimitedToOpenBlockerIds`, `TestClosureCannotIntroduceNewFinding`,
`TestMediumLowDeferredNeverBlock`, `TestThreeCountersNeverConflated`.

**Recovery** — `TestReconcileRequiresHashMatch`, `TestReopenPreservesBudgetsAndTranscripts`,
`TestReopenScopeRulingRecorded`, `TestRecoverFailedReviewRestoresExactlyOne`,
`TestRecoverFailedReviewRefusedOnCompletedReview`, `TestRevalidateLeavesBudgetsUntouched`,
`TestRecoveryCannotCloseBlocker`, `TestRecoveryCannotReachCommitApproval`,
`TestRecoveryLedgersAppendOnly`.

**CLI** — one test per command (thirteen), plus `TestCommitGateIsPrintOnlyByDefault`,
`TestPushGateIsPrintOnlyByDefault`, `TestExecuteFlagStillRequiresTypedConfirmation`,
`TestExitCodeContract`, `TestNoBusinessLogicInCliHandlers` (AST: handlers call exactly one
application method).

**Security** — one test per §22 invariant, including `TestSecretShapedProviderOutputNeverReachesDisk`,
`TestAllStateWritesGoThroughTheRedactionBoundary` (AST),
`TestRedactionEventIsRecordedNotSilent`, `TestCommitApprovalBoundToDiffAndInvalidatedOnChange`,
`TestCommitApprovalIsSingleUse`, `TestMutatingGitOnlyInApprovalGitModule` (AST),
`TestNoDestructiveGitPathAnywhere`,
`TestNoGhInvocation`, `TestNoNetworkCall`, `TestNoAgentosWorkflowImport`, `TestNoShellTrue`,
`TestSymlinkComponentRejected`, `TestUntrustedProviderTextNeverDirective`,
`TestNoCredentialInAnyRecord`.

**Prototype-defect regressions** — one named test per §6 defect, so none can reappear:
`TestP1GlobDoesNotCrossPathSeparator` (`tests/test_*.py` must not match `tests/test_pkg/inner.py`),
`TestP2MissingResultFieldIsTypedRejection` (never a `KeyError`),
`TestP3RoundConsumedOnlyAfterResultParses` (correction and closure, not just review),
`TestP4NoUnreachableRetryCeiling`, `TestP5AllGitRoutesThroughGuard` (AST),
`TestP6AbortAcquiresLock`, `TestP7GovernanceGateUsesMachineReadableOutput`,
`TestP8FullVerificationOutputPersisted`, `TestP9TranscriptSequenceNumberPreventsCollision`,
`TestP10FailureClassRecordedNotRegrepped`.

**Packaging** — `TestWheelContainsMilestoneRunner`, `TestOutOfTreeImport`.

## 27. Live Acceptance Plan

Two tiers, both required.

**Tier 1 — disposable-repository acceptance (default suite).** A real `git init` repository under
`tmp_path` with a realistic contract, a three-milestone plan, and a scripted **fake** provider
producing deterministic result blocks — the pattern the prototype's own self-tests proved and the
repository's `tests/conftest.py` fixtures already establish (real files, real git, no in-memory
mocks). Cases: full happy path to `READY_FOR_COMMIT_APPROVAL`; one correction round; still-blocked
after correction; every scope-violation class; every parser-rejection class; interruption and
resume at each state; lock contention; each of the four recovery commands; and the print-only
commit/push gates. Assertions after every case: `git status --porcelain` shows only expected
allowlisted changes; HEAD unchanged; no governance file touched; no `claude`/`codex` subprocess
spawned; the disposable repository discarded with `tmp_path`.

**Tier 2 — real Claude/Codex smoke acceptance (`live_cli` marker only).** Excluded from the default
run and from CI. A minimal single-milestone plan against a disposable repository, driving one real
Claude implementation invocation and one real Codex read-only review, asserting: the invocation
succeeds; transcripts are written; the result block parses; the review budget accounts correctly;
and the run reaches `READY_FOR_COMMIT_APPROVAL` without committing. Credential isolation follows
the per-attempt discipline GOV-4 established for the existing live suite.

**Proof that commit/push/PR/merge are never performed automatically** — required in both tiers, by
four independent means: (a) an AST proof that no mutating Git subcommand outside `approval_git.py`
(§22 invariant 4) and no `gh` invocation is
reachable in the package; (b) a behavioural proof that `approve-commit`/`approve-push` with shipped
defaults produce output and change nothing; (c) a Git-level proof that HEAD, the reflog, and the
remote refs are unchanged across a complete run; (d) a process-level proof that no `git commit`,
`git push`, or `gh` subprocess was ever spawned.

**Prototype non-interference (DEC-016-006) — required in both tiers.** Every acceptance run asserts
that `~/.local/share/auto015-runner/` is byte-identical before and after: same file set, same
contents, same mtimes, including `state/` and its 852 KB of historical transcripts. No acceptance
case reads prototype state as input, and none writes there. The prototype stays exactly as it is
**until AUTO-016 live acceptance succeeds**, which is the condition the Human Owner's ruling
attaches the deprecation to.

**Plan-location assertions (DEC-016-005) — required in both tiers.** Each run asserts that the plan
was loaded from the external root (or from a path the test contract's allowlist lists verbatim),
that no plan file was created inside the disposable repository, and that no directory scan of the
worktree occurred.

**Post-acceptance disposition is not part of acceptance.** On success, marking the prototype
deprecated is a separate operator act performed outside this stage's allowlist; deleting it is
barred until a separate explicit Human Owner decision. AUTO-016's implementation never performs
either.

**Accepted proof standard:** every assertion passes with zero exceptions; any single failure is a
blocking finding, not a soft warning.

## 28. Migration Plan

**Retained behavior (reimplemented faithfully, not ported):** the thirteen-command surface; the
state vocabulary; the double scope check; branch/baseline pinning; the separated review counters;
print-only Git authority with a second typed confirmation; the transcript triple; the thirteen-field
milestone schema; the review-budget constants and their refuse-to-start validation; the fenced
result grammar; the never-touch-the-tree stop discipline. Each is listed in §6 with the evidence
that it worked.

**Redesigned:** everything in §6's redesign table — module decomposition, Typer CLI, typed Pydantic
state, general configuration, external state root, closed provider capability enums, and real
`pytest` tests replacing `devtools/selftest.py`.

**Runner-local files → package modules:**

| Prototype artifact | Becomes |
|---|---|
| `auto015_runner.py` command dispatch | `cli.py` sub-app + `application.py` |
| its state read/write helpers | `state.py` (typed, atomic, versioned) |
| its lock handling | `lock.py` |
| its allowlist matching | `scope.py` |
| its git wrapper | `git_inspect.py` |
| its verification runner | `verification.py` |
| its provider invocation | the `providers/` subpackage — `base.py` plus one module per adapter (DEC-016-002) |
| its block extraction/parsers | `results.py` |
| its review-budget logic | `review.py` |
| its four recovery commands | `recovery.py` |
| `templates/*.md` | `prompts.py` (fixed templates, typed interpolation) |
| `schemas/*.json` | typed models in `models.py`; JSON Schema becomes derived, not authoritative |
| `milestones/*.yaml` | operator-supplied plan files under the external default plan root (§14, DEC-016-005); the AUTO-015 set stays where it is as history and is neither moved nor converted |
| `devtools/selftest.py` | the `tests/test_milestone_runner_*.py` suite (§23.3) |
| `config.yaml` | the validated runner configuration (§21) |

**Local state stays external.** The prototype's `state/` directory — including run
`auto015-20260804T060616Z-dedd54c6`'s 852 KB of transcripts and its `state.json` — is **not
migrated, converted, imported, or referenced by path** from the repository. It remains historical
evidence in place. AUTO-016 reads no prototype state and provides no importer: a v1 prototype record
and a v1 AUTO-016 record are different schemas that happen to share ancestry, and pretending
otherwise would put unvalidated historical data into a safety-critical path. Historical runs stay
readable exactly as they are today, with the prototype that wrote them.

**Prototype disposition (DEC-016-006 — ruled).** The Human Owner ruled the disposition in four
binding parts:

1. **Until AUTO-016 live acceptance succeeds, the prototype remains unchanged** at
   `~/.local/share/auto015-runner/` as historical and reference tooling. Not modified, not moved,
   not frozen in place by any AUTO-016 action — simply untouched. §27 asserts this byte-for-byte in
   both acceptance tiers.
2. **After successful live acceptance, it is marked deprecated** — a deprecation note in its
   `README.md`, and no further stage is driven with it.
3. **It is never automatically deleted**, and its historical state and transcripts are **never
   migrated or rewritten**. They stay readable exactly as they are today, with the executable that
   wrote them.
4. **Deletion requires a separate explicit Human Owner decision.** No AUTO-016 step, acceptance
   result, or later cleanup task may treat deprecation as permission to remove it.

**AUTO-016's implementation touches the prototype at no point in any of the four parts.** Even the
step-2 deprecation note is a separate operator act outside this stage's allowlist (§24); the
implementation's only relationship to the prototype is to prove it unchanged.

## 29. Newly Discovered Defect Policy

Unchanged from the AUTO-013/AUTO-014/AUTO-015 discipline: reproduce first; classify severity; fix
only a defect proven to directly block this contract's own authorized scope; smallest possible
scope; explicit documentation in the completion report's Deferred Findings section; no bundled
deferred work; no silent scope expansion. A defect not directly blocking AUTO-016 is recorded and
left unimplemented; no GOV stage is created for it.

**Deferred findings reviewed and confirmed non-blocking** (all re-verified `Open` as of this
revision):

- **OD-6** (cancellation semantics for an actively-implementing runtime workflow) — concerns
  `agentos_workflow`'s `CANCELLED`/`FAILED` transition rule. AUTO-016 owns no runtime workflow
  state and drives no `WorkflowState` transition. Not a blocker.
- **OD-7** (safe re-authorization after baseline-commit drift) — AUTO-016 treats any baseline drift
  as an unconditional hard stop (§4 item 4, §15) and never re-binds an authorization, so it takes
  the strict reading OD-7 leaves open rather than depending on its resolution. Not a blocker.
- **OD-10** (five Git/GitHub Skill call sites not forwarding `allowed_environment_variables`) —
  concerns `GitAgent`/`MergeAgent` and the `gh` CLI. AUTO-016 invokes no Skill and no `gh`. Not a
  blocker.
- **OD-11** (`stage_contract_hash` prefix disagreement) — AUTO-016 pins the contract by full
  SHA-256 in its own configuration and shares no code with `calculate_contract_hash`, so the
  prefix-disagreement class is structurally avoided, not merely unaffected. Not a blocker.
- **OD-12** (QA round-numbering collision in `run_repair_loop`) — AUTO-016 runs no repair loop and
  owns its own separately-tested round counters (§19). Not a blocker, and §19's three-counter
  separation is designed so the same class of collision cannot recur here.
- **D-14, D-15, D-16** (AUTO-013's deferred findings on `RemoteRefEvidence`/`PullRequestEvidence`
  reconciliation and report sequencing) — concern `agentos_workflow`'s runtime evidence model, which
  AUTO-016 neither reads nor writes. Not applicable.

None may be silently bundled into AUTO-016's implementation.

## 30. Human Owner Decisions and Remaining Prerequisites

**Ruled by the Human Owner on 2026-08-05** (binding; recorded in `docs/DECISION_LOG.md`; full text
and propagation in §1b):

- **DEC-016-002 — Provider-adapter ownership.** **RULED:** adapters live under
  `src/ai_workflow_engine/milestone_runner/providers/`, owned by this package; the
  `agentos_workflow` provider runtime is **not** reused directly; adapters must use validated
  configuration, stdin prompt delivery, bounded timeout, captured stdout/stderr, durable
  transcripts, strict result parsing, and no credential storage (§8, §17, §22 invariant 20).
- **DEC-016-005 — Milestone plan location.** **RULED:** the default plan root is
  `~/.ai-workflow-engine/milestone-runs/<repository-id>/plans/`, external to the target repository;
  repository-local plans are permitted only at exact paths a governing stage contract's
  implementation allowlist lists verbatim; arbitrary repository-local plan discovery is forbidden
  (§11, §14, §21, §22 invariant 19).
- **DEC-016-006 — Prototype disposition.** **RULED:** unchanged until AUTO-016 live acceptance
  succeeds; deprecated afterwards; never automatically deleted; historical state and transcripts
  never migrated or rewritten; deletion requires a separate explicit Human Owner decision (§24,
  §27, §28).

**Proposed and pre-resolved by direct evidence** (the Human Owner's confirmation is still required
at authorization, but no open question remains):

- **DEC-016-001 — Architecture.** Core Engine Milestone Runner under
  `src/ai_workflow_engine/milestone_runner/`; no `agentos_workflow.WorkflowService` integration.
  Proved not mandatory by four independent lines of evidence (§7).
- **DEC-016-003 — Process lock.** Own `fcntl.flock` implementation, because no engine-side lock
  exists and the only one in the tree is unimportable across the package boundary (§12).
- **DEC-016-004 — Run-state location.** External, repository-scoped artifact root outside the
  worktree, reusing AUTO-015's containment rejection (§11).
- **DEC-016-007 — Command surface.** The twelve required commands plus the retained read-only
  `verify` (§9).
- **DEC-016-008 — Redaction utility.** Intra-package reuse of
  `successor_planning.redaction.redact_text` rather than a duplicated runner-local redactor
  (§17a). Resolved by the AUTO016-REV-002 correction; no boundary is crossed and no existing module
  is modified.

**Genuinely open:** none. As of Revision 3 every decision this contract raised is ruled or resolved
by direct evidence. A new open decision may still arise from a future independent review; none is
known today.

**Remaining authorization prerequisites, none of which this contract satisfies:**

1. Approval of the exact implementation allowlist (§23, now nineteen package files) and
   confirmation that the forbidden surface (§24) is unchanged.
2. Approval of the verification, test, and live-acceptance plans (§25–§27), including the tests and
   assertions added by the Revision 3 rulings.
3. A fresh authorization preflight confirming AUTO-015 remains `COMPLETE`, no conflicting `Current`
   task exists, no AUTO-016 Registry row or implementation branch exists, and no new blocker has
   appeared.
4. A separate, explicit Human Owner authorization statement per `STAGE_REGISTRY.md` §3 rule 3
   ("I authorize AUTO-016" or an equivalent explicit directive). This contract itself remains
   non-authorizing.

**Prerequisite 3 of Revision 2 — "rulings on DEC-016-002, DEC-016-005, DEC-016-006" — is now
satisfied.** The remaining four are not, and the design rulings do not stand in for any of them:
deciding *how* the capability should be built is a different act from authorizing that it *be*
built.

## 31. Implementation Stop Condition

The future implementation must stop after reaching `READY_FOR_COMMIT_APPROVAL` and printing the
exact commit commands. It must never, on its own initiative:

- Authorize a stage, or record any authorization.
- Register or transition a stage in `STAGE_REGISTRY.md`.
- Change any task status in `docs/TASK_QUEUE.md` or its mirrors.
- Accept a scope expansion, or widen an allowlist at runtime.
- Accept, close, or downgrade a Critical or High finding.
- Create, switch, or delete a branch.
- Open a pull request or merge — under any condition, gated or not.
- Commit or push **except** through the §20 approval façade: both disabled by default, both
  requiring an explicit configuration flip *and* a typed interactive confirmation *and* a bound,
  unexpired, single-use approval. With the shipped defaults the runner executes neither, and its
  own terminal state is `READY_FOR_COMMIT_APPROVAL`. This is the one deliberate exception to
  "never," stated explicitly here so the boundary is not read as broader than it is.
- Reset, restore, stash, rebase, clean, or discard any repository work.
- Continue past a tripped safety gate.

## 32. Contract Acceptance Criteria

Before the Human Owner may authorize implementation of AUTO-016, all of the following must hold:

1. The §23 allowlist is reviewed and approved against §24's forbidden surface.
2. The verification (§25), test (§26), and live-acceptance (§27) plans are accepted as sufficient.
3. DEC-016-002, DEC-016-005, and DEC-016-006 are ruled on and recorded in `docs/DECISION_LOG.md`
   — **satisfied 2026-08-05** (§1b, §30); the rulings are propagated through §8, §11, §14, §17,
   §21, §22, §23, §24, §26, §27, and §28.
4. A fresh preflight confirms AUTO-015 `COMPLETE`; no other AUTO stage active; no other task
   `Current`; no AUTO-016 Registry row or implementation branch; a clean tree except the sanctioned
   governance-transition edit set; and no newly blocking OD-#.
5. An independent contract review confirms this revision introduces no contradiction with
   `SECURITY_MODEL.md`, `MACHINE_GATES.md`, `HUMAN_AUTHORIZATION_MODEL.md`, `WORKFLOW_STATES.md`,
   `CONFIGURATION_MODEL.md`, `MODEL_PROVIDER_CONTRACTS.md`, `AUDIT_MODEL.md`, or `ARCHITECTURE.md`.
6. The Human Owner records the literal authorization language `STAGE_REGISTRY.md` §3 rule 3
   requires.

## 33. Final Authorization Boundary

```text
PROPOSED — NOT AUTHORIZED

This contract does not authorize AUTO-016 implementation.
No production file, test, branch, task state, Registry state, workflow state,
provider invocation, commit, push, pull request, or merge may occur until the
remaining prerequisites in §30 are satisfied and the Human Owner explicitly
authorizes AUTO-016.
```
