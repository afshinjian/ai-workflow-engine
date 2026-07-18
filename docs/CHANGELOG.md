# Changelog

All notable changes to `ai-workflow-engine` are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); this project does not yet follow a formal
release-versioning cadence beyond the milestone numbering in `docs/milestones.md`.

## [1.0.0] — 2026-07-18 — Roadmap complete

Version 1.0.0: all four milestones of `docs/milestones.md` are implemented, validated, and
governance-reviewed. Completion report: `docs/FINAL_COMPLETION_REPORT.md`.

### Fixed
- T-501 (2026-07-18): the `version` governance-fact regex in `self-governance.yaml` (and
  `examples/amozesh_konkur.yaml`) widened from `0\.\d+\.\d+` to `\d+\.\d+\.\d+`, so the fact
  extracts a `1.x`+ version; without this the 1.0.0 bump would have made `check-governance` FAIL.

### Changed
- T-501 (2026-07-18): version bumped to 1.0.0 (`pyproject.toml`, `__init__.py`,
  `docs/PROJECT_STATE.md`). The `WorkflowSettings` auto-flag validator message reworded from the
  now-stale "Milestone 1 forbids…" to state the permanent invariant (config-level automatic
  commit/push are always forbidden; use the approval-gated Milestone 4 commands). Behavior
  unchanged.

## [0.3.0] — 2026-07-18 — Milestone 4

Milestone 4 (controlled commit and push), released as v0.3.0. Every task (T-401..T-404) passed an
independent review; the plan review took two rounds (five blocking findings remediated).
Demonstration: `docs/MILESTONE_4_VALIDATION.md`.

### Added
- T-401 (2026-07-18): `docs/milestone-4-plan.md` — the normative Milestone 4 plan.
- T-402 (2026-07-18): the writable-Git surface and commit gate — `git/writer.py`
  (typed-methods-only `GitWriter` + `GitWriteError`), six read-only `GitClient` gate helpers
  (`READ_ONLY_FORMS` byte-unchanged), `git/approval.py` (`CommitApproval`/`PushApproval` +
  loaders), `commit/gates.py` (`run_commit_gate`), and `workflowctl commit`.
- T-403 (2026-07-18): `run_push_gate` + `run_apply_patch_gate` and the `workflowctl push` /
  `apply-patch` commands. The push gate mechanically applies the Milestone 2 push algorithm;
  apply-patch writes a verified Milestone 3 patch to the working tree only.
- T-404 (2026-07-18): Milestone 4 closeout — version 0.3.0, `docs/MILESTONE_4_VALIDATION.md`, and
  README/architecture updates for the commit/push/apply-patch surfaces.

Refusal-by-default throughout: no commit or push without a matching per-invocation human approval
artifact, and every gate failure writes nothing. `allow_automatic_commit`/`allow_automatic_push`
remain hard-false.

## [0.2.0] — 2026-07-18 — Milestone 3

Milestone 3 (non-interactive agent execution) plus the Stage-0 work that preceded it, released
as v0.2.0. Every task (Stage 0 T-101..T-104; Milestone 3 T-301..T-306) passed an independent
fresh review. Full-cycle demonstration and the lying-agent detection evidence:
`docs/MILESTONE_3_VALIDATION.md`.

### Added
- `docs/IMPLEMENTATION_GAP_ANALYSIS.md` — full fresh-session audit of implementation vs.
  documentation (2026-07-17); repository verified healthy (448 tests, lint/type clean,
  self-governance verify PASS).
- `docs/MASTER_ROADMAP.md` — human-approved (2026-07-17) roadmap to version 1.0.0: Stage 0
  closeout/sync/CI, Milestone 3 (T-301..T-306), Milestone 4 (T-401..T-404), release (T-501).
- GOV-1 closed via T-101; Stage 0 tasks T-102 (documentation sync) and T-103 (lightweight CI,
  human-approved addition) registered in the task queue.

- T-103 (2026-07-17): `.github/workflows/ci.yml` — lightweight CI running lint, format check,
  strict typing, the test suite, and the three repository-content governance checks on every
  push and pull request.
- T-301 (2026-07-17): `docs/milestone-3-plan.md` — the normative Milestone 3 architecture plan
  (event-sourced workflow state machine, agent config/report schemas, snapshot-sandbox runner,
  independent claim verification). Approved after two independent plan-review rounds (round 1
  REJECTED, remediated; round 2 APPROVED).
- T-302 (2026-07-18): `ai_workflow_engine.workflow` event-sourced state machine —
  append-only hash-chained `WorkflowEvent`s, the fixed transition table with verdict
  enforcement, collision-free tamper-evident storage (Milestone 2 atomic no-clobber protocol),
  next-stage computation, and the `workflowctl state show|next|record` CLI. Independent
  implementation review APPROVED. (First Milestone 3 implementation task.)
- T-303 (2026-07-18): `EngineConfig.agents` configuration section (per-agent name/executable/
  args/mode/timeout/stages, with mode-stage compatibility and `push` forbidden for any agent)
  and the strict `AgentReport`/`AgentFinding` output contract (`ai_workflow_engine.agents`).
  `WorkflowStage` moved to `ai_workflow_engine.models` (re-exported from `prompt.models`).

- T-304 (2026-07-18): `ai_workflow_engine.agents.sandbox` + `.runner` — throwaway sandbox
  clones with a sandbox-only `SandboxGit` surface, and the non-interactive `run_agent` execution
  protocol (clean-tree/HEAD precondition gate, hard timeout with process-group kill, scrubbed
  environment, before/after target-repository fingerprint, and the agent-output failure
  taxonomy). Observes the raw run facts (change set, patch, verification exit codes) for T-305;
  never writes the target repository. Independent implementation review APPROVED.
- T-305 (2026-07-18): `ai_workflow_engine.agents.verification` + `.artifacts` and the
  `workflowctl agent run` CLI — independent claim verification (`RunObservation` →
  `CheckResult`: claim equality, scope/protected-path containment, verification-command exit
  codes), tamper-evident content-addressed `AgentRunRecord` artifacts (base64 stdout/stderr with
  recomputable digests, `.patch` sidecar), and `state record --agent-run` evidence binding. A
  scoped-write agent's verified patch is stored, never applied (that is Milestone 4). Independent
  implementation review APPROVED.
- T-306 (2026-07-18): Milestone 3 closeout — version 0.2.0, `docs/MILESTONE_3_VALIDATION.md`, and
  README/architecture updates for the state + agent CLI surfaces.
- T-401 (2026-07-18): `docs/milestone-4-plan.md` — the normative Milestone 4 plan (typed
  `GitWriter`, approval artifacts, commit/push/apply-patch gates). Approved after two independent
  plan-review rounds (round 1 REJECTED with five blocking findings, remediated; round 2 APPROVED).
- T-402 (2026-07-18): the writable-Git surface and commit gate — `git/writer.py` (typed-methods-
  only `GitWriter` + `GitWriteError`), six read-only `GitClient` gate helpers (`READ_ONLY_FORMS`
  byte-unchanged), `git/approval.py` (`CommitApproval`/`PushApproval` + loaders), `commit/gates.py`
  (`run_commit_gate`), and `workflowctl commit`. Refusal-by-default; every FAIL/ERROR path writes
  nothing. First real-Git-write code; independent implementation review APPROVED.

### Changed
- T-303 (2026-07-18): **prompt-artifact schema bump 1.0 → 1.1.** The `agents` config section
  now enters the canonical prompt payload, so `PromptContext`/`PromptMetadata`/`PromptSuccess`
  are `schema_version` 1.1 and `workflowctl prompt` stored artifacts from before this change no
  longer load. Prompt **templates** (the seven byte-pinned bodies) are unchanged; only
  content-derived identity (`prompt_id`) shifts. Accepted, documented break (pre-1.0, local
  ephemeral artifacts) — see `docs/milestone-3-plan.md`.

### Fixed
- T-104 (2026-07-18): `workflowctl` machine-readable output (`--output json` for every
  check/verify/inspect, and `version`) no longer emits ANSI color codes when `FORCE_COLOR` is
  set in the environment, which had corrupted the stable 1.0 JSON contract into unparseable
  output. Machine output now bypasses Rich via a `_write_stdout` helper. Independent
  implementation review APPROVED.

### Changed
- T-102 (2026-07-17): `docs/milestone-2-plan.md` status line now records implemented/approved
  reality; `README.md` and `docs/architecture.md` extended to cover the Milestone 2 prompt
  subsystem and self-governance usage.
- `ai_workflow_engine.prompt` package: deterministic, canonically-hashed rendering, structural
  validation, and race-safe atomic storage of governed workflow prompts for all seven stages
  (`plan-review`, `implementation`, `implementation-review`, `remediation`,
  `governance-closeout`, `governance-review`, `push`).
- `workflowctl prompt <stage>` CLI commands, with `--output human|json` and `--store/--no-store`.
- `project.conda_environment` required configuration field (rejects empty/whitespace-only).
- Self-governance layer: `docs/PROJECT_STATE.md`, `docs/TASK_QUEUE.md`, `docs/current_task.md`,
  `docs/remaining_tasks.md`, `docs/CONTEXT.md`, `docs/DECISION_LOG.md`, `docs/CHANGELOG.md`,
  `docs/AGENT_PROTOCOL.md`, `handover/PROJECT_HANDOVER.md` + checksum manifest, and
  `self-governance.yaml`, so `workflowctl` can be pointed at this repository itself. See
  `docs/GOVERNANCE_AUDIT.md`.

### Fixed
- `workflowctl`'s `_protected` error path (used by every command, not just `prompt`) no longer
  corrupts or soft-wraps `ERROR: <message>` stderr output. Previously routed through Rich's
  `Console`, which interpreted bracketed substrings as markup/highlighting and soft-wrapped long
  messages at the console width — both violated the exact-bytes stderr contract. Now writes
  directly to `sys.stderr`.

### Process
- Milestone 2 passed three independent fresh implementation reviews (no reviewer had memory of
  a prior round's fixes) before approval, fixing two real defects and closing several
  test-coverage gaps (per-field prompt-identity sensitivity tests, genuine thread-based
  concurrency tests for the atomic store, a `load()` mixed-pair test, an expanded validator
  mutation matrix, byte-exact CLI golden tests).

## [0.1.0] — 2026-07-16 — Milestone 1

### Added
- Deterministic, read-only Git inspection (`GitClient`, `READ_ONLY_FORMS` allowlist).
- Governance mirror checking: task-state parsing from Markdown (`Current`/`Done`/`Planned`),
  configurable cross-document fact consistency checks.
- Handover integrity verification via a checksummed manifest, sourced from the working tree,
  Git index, or a specific commit.
- Protected-path enforcement (`never_stage`/`never_commit` glob patterns).
- Structured `CheckResult`/`VerificationReport` schema (`schema_version: "1.0"`), Rich console
  and JSON output.
- `workflowctl` CLI: `version`, `inspect`, `check-git`, `check-task-state`, `check-governance`,
  `check-handover`, `verify`.

## 2026-07-15 — Project initialization

### Added
- Repository scaffolding, packaging (`pyproject.toml`, `hatchling`), lint/type/format tooling
  (`ruff`, `black`, `mypy --strict` on `src`), `pre-commit` configuration.
