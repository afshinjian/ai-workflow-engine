# AgentOS Dashboard — Decisions

| Field | Value |
|---|---|
| **Title** | AgentOS Dashboard — Decisions |
| **Purpose** | Append-only record of dashboard-program decisions (DD-##). Subordinate to `docs/DECISION_LOG.md`; cross-posted there when repository governance requires. |
| **Status** | Draft |
| **Version** | 1.0 |
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

## Decision References
Repository decisions binding this program are recorded in `docs/DECISION_LOG.md` (2026-07-23
entry for program enrollment).

## Open Questions
None held here; see `OPEN_QUESTIONS.md`.

## Future Revisions
Append-only.
