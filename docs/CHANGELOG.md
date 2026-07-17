# Changelog

All notable changes to `ai-workflow-engine` are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); this project does not yet follow a formal
release-versioning cadence beyond the milestone numbering in `docs/milestones.md`.

## [Unreleased] — Milestone 2 work, pending governance-closeout/review/push

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
