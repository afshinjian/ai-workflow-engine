# AgentOS Dashboard — Decisions

| Field | Value |
|---|---|
| **Title** | AgentOS Dashboard — Decisions |
| **Purpose** | Append-only record of dashboard-program decisions (DD-##). Subordinate to `docs/DECISION_LOG.md`; cross-posted there when repository governance requires. |
| **Status** | Draft |
| **Version** | 1.2 |
| **Owner** | Documentation & Governance session (append) · Human Owner (approval) |
| **Dependencies** | `MASTER_PLAN.md` §8 |
| **Related Documents** | `docs/DECISION_LOG.md` |

## Format

Each entry: status, context, decision, consequences, reconsideration trigger. Entries are
appended, never rewritten; supersessions are explicit.

## DD-01 — Separate local control-plane package (Option 2)

- **Status:** Accepted (approved plan, 2026-07-23; wording adapted to `ai-workflow-engine` by
  DD-03).
- **Context:** Three options were evaluated: embed in the engine package
  (`src/ai_workflow_engine/`); separate local control-plane package in the same repository;
  separate service with an independent SPA frontend.
- **Decision:** Option 2 — top-level package `agentos_dashboard/`, served at
  `127.0.0.1:8642`, reusing the already-pinned stack in `pyproject.toml` where possible;
  read-only repository adapters; non-authoritative local SQLite; tests outside the engine
  suite's `testpaths`.
- **Consequences:** Zero risk to the audited engine package and its strict lint/type/test
  gates; each stage is an ordinary `docs/TASK_QUEUE.md` task. The HTTP-serving layer needs a
  dependency decision (OD-D9) because this repository pins no web framework.
- **Reconsider when:** A separately approved decision requires direct agent execution,
  multi-user access, or an independent frontend.

## DD-02 — Stage prompts as a directory

- **Status:** Accepted (documentation architecture amendment, 2026-07-23).
- **Context:** A single `STAGE_PROMPTS.md` mixed the SSP and ten prompts in one file.
- **Decision:** Replace with `stage-prompts/` containing `README.md` (sole canonical SSP +
  usage rules) and `DASH-001.md`..`DASH-010.md` (one canonical prompt each). Organizational
  only; no prompt content changed.
- **Consequences:** Independent per-stage versioning; the DASH-007 loader targets the directory.
- **Reconsider when:** Never expected; a reversal is a MINOR organizational change.

## DD-03 — DASH-001 recovery adaptation to `ai-workflow-engine`

- **Status:** Accepted (Human Owner recovery directive, 2026-07-23).
- **Context:** The original DASH-001 execution was mistakenly performed in a different
  repository (`amozesh_konkur`) whose governance stack (CLAUDE.md/CONSTITUTION.md/AGENTS.md/
  `governance/` directory, CTO roles, `recovery/project-baseline` branch, `baseline-v1` tag,
  handover generator script, FastAPI-pinned environment) does not exist here. The copied
  documentation was declared candidate material only.
- **Decision:** Re-execute DASH-001 in `ai-workflow-engine` by adapting the full documentation
  set to this repository's actual governance: authority chain per `docs/AGENT_PROTOCOL.md` +
  `self-governance.yaml`; task lifecycle per `docs/TASK_QUEUE.md` (Current/Planned/Done) with
  `workflowctl` mirror checks; branches from `main`; handover pair verified by
  `workflowctl check-handover`; upstream check replacing the baseline-tag check; single
  decision log `docs/DECISION_LOG.md`; the orchestration (`ORCH`) package treated as read-only
  observed state (TR-09); dependency reality recorded as OD-D9. No root-level governance file
  from the other repository (AGENTS.md, CONSTITUTION.md, `governance/`) is created here.
- **Consequences:** The documentation set is valid for this repository; the `amozesh_konkur`
  execution is void for this repository and its report was replaced; deviations are traceable
  through this entry, the `CHANGELOG.md` CL-20260723-02 entry, and
  `docs/reports/agentos-dashboard/DASH-001-recovery-report.md`.
- **Reconsider when:** Never — historical record.

## DD-04 — Adapter errors are typed exceptions, not result objects

- **Status:** Accepted (DASH-002 implementation decision, 2026-07-29).
- **Context:** The engine's `agentos_workflow` Skills return a `SkillResult` union rather than
  raising, because an Orchestrator has to branch on a failure *kind* to choose a workflow-state
  transition. The dashboard's adapters have no such caller: a page render either has the data or
  must show the operator a finding.
- **Decision:** Every failure in `agentos_dashboard/core/` is a typed exception deriving from
  one base (`DashboardError`), carrying a `StrEnum` reason (`PathRefusal`, `FileRefusal`,
  `GitFailure`). Nothing from `subprocess`, `OSError`, or `pathlib` crosses an adapter boundary.
  The snapshot builder is the layer that converts those exceptions into `SnapshotFinding`s, so
  SC-34's "degrade, never crash" is implemented once instead of at every call site.
- **Consequences:** Services (DASH-004+) may let an adapter exception propagate to a page-level
  handler, or catch it into a finding, without inventing a second error vocabulary. It also
  keeps the two packages independent: no `agentos_workflow` type is imported.
- **Reconsider when:** A later stage needs a partial-success shape an exception cannot express.

## DD-05 — `core.quotePath=false` as a fixed Git global option

- **Status:** Accepted (DASH-002 implementation decision, 2026-07-29).
- **Context:** `ARCHITECTURE.md` §3 fixes the Git *subcommand forms* the adapter may run. With
  Git's default `core.quotePath=true`, any path containing a non-ASCII byte is returned
  C-quoted (`"docs/\303\251.md"`), so a caller would have to unescape adapter output — a decoding
  step in exactly the layer that must not decode.
- **Decision:** Every invocation carries the fixed global options
  `--no-optional-locks -c core.quotePath=false -C <root>` ahead of the contracted subcommand
  form. These are literals in one private helper, never caller-supplied, so the contracted forms
  and the "no caller-supplied verb" property are both unchanged.
- **Consequences:** Paths come back verbatim and comparable to filesystem paths. Recorded here
  because a reviewer comparing argv to `ARCHITECTURE.md` §3 will see options the contract does
  not list.
- **Reconsider when:** A Git version changes the meaning of either option.

## DD-06 — `project_state_task_queue_contradiction` is scoped to `## Completed` bullets only

- **Status:** Accepted (DASH-003 implementation decision, 2026-07-29).
- **Context:** `DASH-003.md`'s Acceptance section asks the consistency engine to detect "a
  fixture reproduction of a deliberate PROJECT_STATE-vs-TASK_QUEUE contradiction." The real
  `docs/PROJECT_STATE.md` has three status-shaped sections — `## Completed`, `## In progress`,
  `## Planned` — but only `## Completed`'s bullets are structured one-task-per-bullet with the
  id first (`- <ID> (closed ...): ...`); `## In progress`/`## Planned` are free-form prose that
  can name a task id mid-sentence while describing an unrelated fact about it (verified against
  the real document: its `## In progress` section says "AUTO-006 was ... closed to `Done`" while
  narrating GOV-AUTO-03, which a naive whole-section scan would misread as PROJECT_STATE.md
  claiming AUTO-006 is still in progress).
- **Decision:** `agentos_dashboard.parsing.project_state` extracts `SectionTaskRef`s only from
  `## Completed`'s top-level bullets (a line starting `- `, task id first); `## In progress`/
  `## Planned` are left as raw prose for a later stage's decision, not scanned by this rule.
- **Consequences:** The rule is high-precision (verified to produce zero false positives against
  this repository's real `PROJECT_STATE.md`/`TASK_QUEUE.md` pair,
  `agentos_dashboard/tests/test_parsing_project_state.py::test_real_repository_project_state_parses_at_high_confidence`)
  at the cost of not checking the other two sections at all. A later stage that needs that
  coverage will need either a stricter prose convention in those sections or a different
  extraction strategy — an explicit decision, not assumed here.
- **Reconsider when:** `## In progress`/`## Planned` adopt a structured one-bullet-per-task
  convention, or a later stage's UI needs live status for tasks named only in those sections.

## DD-07 — The sole-`Current` invariant is a documented constant, not a parsed config value

- **Status:** Accepted (DASH-003 implementation decision, 2026-07-29).
- **Context:** `check-task-state`'s "too many Current tasks" rule reads
  `workflow.maximum_current_tasks` from `self-governance.yaml`. `DASH-003.md`'s Allowed list
  names five specific document parsers (`docs/PROJECT_STATE.md`, the task queue and its two
  mirrors as one family, `docs/DECISION_LOG.md`, `implementation-state.yaml`, the handover
  manifest) and does not include a general YAML config reader for `self-governance.yaml`, whose
  schema (`GovernanceSettings`, `WorkflowSettings`, …) belongs to the engine.
- **Decision:** `agentos_dashboard.services.consistency.DEFAULT_MAXIMUM_CURRENT_TASKS` is a
  documented `= 1` constant, matching this repository's actual configured value, checked by
  `test_watched_files_match_the_source_of_truth_document`-style equality only informally (by
  code comment, not by a runtime read of `self-governance.yaml`).
- **Consequences:** If a future Human Owner decision changes
  `self-governance.yaml`'s `workflow.maximum_current_tasks`, this constant must be updated by
  hand or it will silently drift from the engine's own enforced value — a known, accepted MVP
  limitation, not a defect DASH-003 is expected to close. A general `self-governance.yaml`
  reader is DASH-004+'s natural home (`ARCHITECTURE.md` §2's `services:` layer already composes
  config-derived facts for later stages).
- **Reconsider when:** A later stage adds a `self-governance.yaml` parser for another reason,
  at which point this constant should be replaced by a read of the real value.

## Decision References
Repository decisions binding this program are recorded in `docs/DECISION_LOG.md` (2026-07-23
entry for program enrollment).

## Open Questions
None held here; see `OPEN_QUESTIONS.md`.

## Future Revisions
Append-only.
