# Governance Audit — Self-Hosting a Deterministic AI Workflow Governance System

Status: DRAFT. Produced per the Phase 1 audit gate — no implementation has occurred. This
document is the deliverable for that gate; Phases 2–8 do not begin until the open decisions
below are resolved.

## 1. Current state

### 1.1 What `ai-workflow-engine` already is

This repository is not a blank slate. It is version 0.1.0 of a tool whose entire purpose is
"deterministic governance gates for AI-assisted software development" (`pyproject.toml`
description) — applied to a **target** project supplied via `--config`, not to itself. The
example config (`examples/amozesh_konkur.yaml`) governs a separate repository at
`/home/afshin-jian/amozesh_konkur`; `ai-workflow-engine`'s own working tree currently has no
governance documents describing itself and is not a `--config` target of its own tool.

The codebase already implements, end-to-end and under test (438 tests as of this audit):

| Concern | Where | Notes |
|---|---|---|
| Config schema | `src/ai_workflow_engine/models.py` (`EngineConfig`) | `project`, `governance`, `handover`, `protected_paths`, `workflow` sections. Strict, `extra="forbid"`. |
| Config loading/validation | `src/ai_workflow_engine/config.py` | Repository-bound path resolution, symlink/traversal defense, Git-worktree verification. |
| Read-only Git inspection | `src/ai_workflow_engine/git/` | `GitClient`, `READ_ONLY_FORMS` allowlist, `check_git` validator. |
| Task-state parsing | `src/ai_workflow_engine/governance/{parser,models,validators}.py` | 3-state model (`Current`/`Done`/`Planned`) parsed from Markdown headings/table rows across configured documents. `check_task_state`. |
| Governance fact extraction | `src/ai_workflow_engine/governance/validators.py` | Configurable regex "fact rules" (e.g. version, phase) checked for consistency across documents. `check_governance`. |
| Handover integrity | `src/ai_workflow_engine/handover/` | Checksum-manifest verification of named deliverable files, sourced from working tree, index, or a commit. `check_handover`. |
| Workflow summary | `src/ai_workflow_engine/workflow/` | Thin `WorkflowSummary` over the task snapshot. |
| Structured results | `src/ai_workflow_engine/result.py`, `reporting/` | `CheckResult`/`Status` (`PASS`/`FAIL`/`ERROR`), Rich console + JSON rendering, stable 1.0 schema (`docs/architecture.md`). |
| CLI | `src/ai_workflow_engine/cli.py` | `version`, `inspect`, `check-git`, `check-task-state`, `check-governance`, `check-handover`, `verify`, and `prompt <stage>` for all seven stages below. |
| Governed prompt generation | `src/ai_workflow_engine/prompt/` (Milestone 2, just approved) | Deterministic, canonically-hashed, byte-exact Markdown prompts for **seven fixed workflow stages** — `plan-review`, `implementation`, `implementation-review`, `remediation`, `governance-closeout`, `governance-review`, `push` — each with a fixed role/scope/prohibited/verification/stop/verdict template, race-safe atomic storage under `~/.ai-workflow-engine/workflow-runs/prompts/`. |

### 1.2 The documented roadmap already answers most of Phases 3, 4, and 7

`docs/milestones.md` is a four-milestone roadmap this project has followed literally for two
milestones already, each gated behind an independent fresh-review process:

1. **Milestone 1 (done, 0.1.0):** deterministic read-only inspection.
2. **Milestone 2 (done, this session's prior work):** prompt generation from verified state.
3. **Milestone 3 (not started):** *"Non-interactive agent execution. Codex read-only review and
   scoped OpenCode writes, strict report schemas, isolation, timeouts, and independent claim
   verification."*
4. **Milestone 4 (not started):** *"Controlled commit and push. Approval-bound staging
   allowlists, commit verification, protected-path enforcement, remote/upstream checks, and
   explicit push gates."*

In other words: **Codex/OpenCode role separation (Phase 4) and git commit/push approval gates
(Phase 7) are not missing pieces — they are Milestone 3 and Milestone 4**, already scoped, not
yet built, by explicit design ("Later milestones must preserve the Milestone 1 rule that agent
output is evidence to verify, not an authority").

### 1.3 What genuinely does not exist yet

- No `docs/governance/` directory or any of the eight files requested in Phase 2.
- No governance config (`EngineConfig` YAML) describing `ai-workflow-engine` itself — the tool
  has never been pointed at its own repository.
- No task-state documents for this repo in the shape `governance/parser.py` expects.
- No persisted, timestamped, evidence-bearing task-transition log of any kind. Milestone 1 and 2
  are both explicitly documented as read-only/stateless (Milestone 2's own plan: *"Persisted
  workflow state, verdict recording, transition enforcement, reachability checks, and automatic
  next-stage computation are deferred to Milestone 3"*).
- No `governance status|validate|handover|closeout` CLI verbs (see §2.2 — close but not
  identical functionality already exists under different names).
- No CI configuration (no `.github/`); only local `pre-commit` (`ruff check --fix`, `ruff
  format`, `black`, `mypy src`).
- No cross-agent protocol document (Claude/Codex/OpenCode/Human responsibilities) as prose,
  though the milestone boundaries encode the intended division implicitly.

## 2. Missing pieces vs. the requested architecture — a direct mapping

This is the section that matters most before writing any new code: most of the "missing"
components in the request already have a same-purpose, differently-shaped counterpart in this
codebase. Building the requested system verbatim, in parallel, would create two
governance systems describing the same repository with incompatible vocabularies.

### 2.1 File-for-file

| Requested (Phase 2) | Existing counterpart | Compatible as-is? |
|---|---|---|
| `docs/governance/PROJECT_STATE.md` | `governance.project_state` (config points at an arbitrary path; example uses `docs/PROJECT_STATE.md`) | Yes — same concept, same conventional name. |
| `docs/governance/CURRENT_TASK.md` | `governance.current_task` | Yes. |
| `docs/governance/TASK_QUEUE.md` | `governance.task_queue` | Yes. |
| `docs/governance/HANDOVER.md` | `handover.manifest` + `handover.files` (checksum-verified deliverable list) **and/or** `governance.context` (free-form context doc; example config uses `docs/CHATGPT_CONTEXT.md` for exactly "context transfer between sessions") | Partially — the existing `handover` concept is a *checksum manifest of specific files*, not a narrative document. The narrative-context need maps better to `governance.context`. |
| `docs/governance/DECISION_LOG.md` | none | New — pure documentation, no conflict. |
| `docs/governance/CHANGELOG.md` | none (no `CHANGELOG.md` anywhere in the repo) | New — pure documentation, no conflict. |
| `docs/governance/WORKFLOW_RULES.md` | `docs/milestones.md`, `docs/architecture.md`, per-milestone plan docs (`docs/milestone-2-plan.md`) already carry this content, spread across files | Could consolidate, or add a thin index — no conflict either way. |
| `docs/governance/AGENT_PROTOCOL.md` | implicit in milestone boundaries; no prose statement | New — pure documentation, no conflict. |

### 2.2 Command-for-command

| Requested (Phase 6) | Existing counterpart | Gap |
|---|---|---|
| `governance status` | `workflowctl verify` (combined PASS/FAIL/ERROR across all four checks, JSON or human) | Naming only, functionally close. |
| `governance validate` | `workflowctl check-governance`, `check-task-state`, `check-handover` (already check "required files exist", "task state is valid", "documentation is synchronized" — that is literally what `check_governance`'s fact-consistency checking does) | Naming only, functionally close. |
| `governance handover` | `workflowctl prompt governance-closeout` (assesses closeout readiness) plus `workflowctl check-handover` (verifies a checksum manifest) — but neither *writes* a narrative "handover report" | Partial — no command currently *generates* a handover write-up; existing tooling *verifies* one. |
| `governance closeout` | `workflowctl prompt governance-closeout` | Already exists, different name, and already went through a full plan-review → implementation → implementation-review → remediation cycle. |

### 2.3 The task lifecycle — the one real, substantive conflict

Phase 3 requests: `BACKLOG → PLANNED → APPROVED → IMPLEMENTING → VALIDATING → COMPLETED →
HANDED_OVER`, with a mandatory timestamp/reason/evidence/responsible-agent on every transition.

The existing model (`governance/models.py: TaskStatus`) is `Current | Done | Planned` — three
states, parsed fresh from Markdown on every read, with **no transition history at all** by
design (Milestone 1: read-only mirror of whatever the documents currently say, not a state
machine with memory).

These are not compatible by renaming. Introducing a 7-state, evidence-logged transition system
is a **new capability** — persisted, mutable, audit-logged state — which is precisely what
Milestone 2's own plan document explicitly deferred to Milestone 3 twice over (once for "prompt"
state, once implicitly for task state). Building it now, ad hoc, under a different name
(`docs/governance/`) than the roadmap's own Milestone 3/4 would fork the project's state model in
two directions at once.

## 3. Recommended architecture

Two genuinely different paths are available. I am not choosing between them — this is exactly
the kind of "major architecture decision" the request itself says must be explained and agreed
before implementation.

### Option A — Extend the existing engine to govern itself ("dogfood")

Point `ai-workflow-engine`'s own tooling at its own repository:

1. Create `docs/PROJECT_STATE.md`, `docs/TASK_QUEUE.md`, `docs/current_task.md`,
   `docs/remaining_tasks.md`, `docs/CONTEXT.md` in the shapes `governance/parser.py` already
   parses (Markdown headings/tables with `Status: Current|Done|Planned`).
2. Create a `handover/` manifest + tracked deliverable files (mirroring
   `examples/amozesh_konkur.yaml`'s `handover` section) — the natural home for the Phase 2
   "HANDOVER.md" concept, using the checksum-verified mechanism that already exists and is
   already tested.
3. Write a new config file (e.g. `self-governance.yaml`, analogous to
   `examples/amozesh_konkur.yaml`) with `project.repository` pointing at this repo, so
   `workflowctl verify --config self-governance.yaml` and `workflowctl prompt governance-closeout
   --config self-governance.yaml` work against `ai-workflow-engine` itself, today, with zero new
   code.
4. Add exactly three new pure-documentation files with no existing counterpart:
   `docs/DECISION_LOG.md`, `docs/CHANGELOG.md`, `docs/AGENT_PROTOCOL.md` (the last one writing
   down, as prose, the Claude/Codex/OpenCode/Human split that `docs/milestones.md` already implies
   but never states directly).
5. Leave the 7-state lifecycle, new CLI verbs, and multi-agent orchestration **out of scope for
   now**, explicitly deferred to Milestones 3–4 as the project has already committed to in
   writing — unless the user decides here, explicitly, to pull that work forward.

Effort: small. Risk: near zero — no existing code changes, only new documents plus one new
example config. Fully reversible. Immediately usable with the CLI that already passed three
independent implementation reviews.

### Option B — Build the requested system exactly as specified, in parallel

Implement Phases 2–8 literally: a new `docs/governance/` tree with the eight named files, a new
7-state task lifecycle (new Pydantic models, a new parser or a hand-maintained log, transition
validation), new `governance status/validate/handover/closeout` CLI commands as a second command
surface alongside the existing `check-*`/`verify`/`prompt` commands, and prose defining
Claude/Codex/OpenCode/Human roles independent of the milestone boundaries that already encode
that split.

Effort: large (this is realistically Milestones 3 and 4 pulled forward, done differently than
planned, plus new documentation scaffolding). Risk: real — two parallel, differently-shaped
governance vocabularies describing the same repository (`Current/Done/Planned` vs.
`BACKLOG/PLANNED/APPROVED/.../HANDED_OVER`; `check-governance` vs. `governance validate`) is a
maintenance and confusion liability, and it would not preserve the project's own "later
milestones build on the same result/invariant layer" principle (`docs/architecture.md`).

### My recommendation

**Option A**, for one reason above all others: this project has already run two milestones
through a real, working, three-times-independently-reviewed governance discipline (the last of
which is the conversation immediately preceding this audit — plan review, implementation,
fresh implementation-review, remediation, repeat). Replacing that working discipline with a new,
parallel, hand-specified one — before ever having pointed the existing one at this repository —
discards proven infrastructure to rebuild a shape of it from a template. The three genuinely
missing *pure documentation* pieces (`DECISION_LOG.md`, `CHANGELOG.md`, `AGENT_PROTOCOL.md`) carry
real value and have no existing counterpart; they should be added regardless of which option is
chosen.

If the user's actual goal is to pull Milestone 3 (multi-agent execution) and Milestone 4
(approval-gated commit/push) forward in time under new names, that is a legitimate call to
make — but it should be made explicitly, as a roadmap change, not arrived at implicitly by
building Phases 3, 4, and 7 as originally specified.

## 4. Implementation roadmap (pending the Option A/B decision above)

If Option A is chosen, in dependency order:

1. Add `docs/DECISION_LOG.md`, `docs/CHANGELOG.md`, `docs/AGENT_PROTOCOL.md` (pure docs, no
   code, no config dependency — safe to do immediately).
2. Create the five governance documents (`PROJECT_STATE.md`, `TASK_QUEUE.md`,
   `current_task.md`, `remaining_tasks.md`, `CONTEXT.md`) plus a handover manifest/file set,
   populated with this project's real current state (Milestone 2 approved, Milestone 3/4 planned
   next).
3. Add a self-governance `EngineConfig` YAML pointing at this repository.
4. Run `workflowctl verify --config <that file>` and `workflowctl prompt governance-closeout
   --config <that file> --task-id <id>` against the real repository and confirm they produce
   sane output — this *is* Phase 8's validation demonstration, using the real tool instead of a
   new demo script.
5. Only after that round-trip is proven: revisit whether a `governance status`
   convenience alias (thin wrapper over `verify`) is worth adding, and whether Milestones 3/4
   should be pulled forward — as separate, explicitly-scoped decisions.

If Option B is chosen instead, Phases 2–8 proceed as originally specified, and this document
should be updated to record that the roadmap in `docs/milestones.md` is being superseded/merged,
so a future fresh session doesn't find two contradictory plans.

## 5. Open decision for the user

**Option A (extend/dogfood the existing engine) or Option B (build the parallel system exactly
as specified)?** Everything past this point in the original 8-phase request depends on that
answer, and Phase 1 explicitly gates further implementation on this audit being reviewed first.
