# DASH-001 — Planning Foundation and Dashboard Contracts

| Field | Value |
|---|---|
| **Stage** | DASH-001 · Role: Documentation & Governance session |
| **Branch** | `governance/dash-001-documentation` |
| **Commit message** | `docs(governance): establish AgentOS dashboard planning foundation (DASH-001)` |
| **Report** | `docs/reports/agentos-dashboard/STAGE-01-completion.md` |
| **Status/Version** | Draft · 1.0 |

Apply the Standard Stage Protocol in `README.md` in full. For this stage the planning corpus
does not exist in the repository yet (or, in the 2026-07-23 recovery execution, exists only as
unvalidated candidate material copied from a mis-targeted run); the master-plan source is the
approved plan text supplied with the authorization, adapted to this repository per
`../DECISIONS.md` DD-03.

## Canonical Prompt

You are the **Documentation & Governance session**, executing **DASH-001 — Planning foundation
and dashboard contracts** for the AgentOS Local Dashboard program in `ai-workflow-engine`.

**Authorization**: this prompt is valid only if the Human Owner has recorded: "I authorize
DASH-001" (or equivalent) and the DASH family may be enrolled. If that record is absent, stop
and report.

**Branch**: `governance/dash-001-documentation`, created from clean `main` (the configured
default branch in `self-governance.yaml`).

**Allowed files (create)**: `docs/agentos-dashboard/{MASTER_PLAN.md, ARCHITECTURE.md,
PRODUCT_SPEC.md, SECURITY_MODEL.md, SOURCE_OF_TRUTH.md, DATA_MODEL.md, API_SPEC.md, UI_SPEC.md,
MVP_SCOPE.md, STAGE_REGISTRY.md, TEST_STRATEGY.md, DECISIONS.md, OPEN_QUESTIONS.md,
CHANGELOG.md, STAGE_REPORT_TEMPLATE.md}`, `docs/agentos-dashboard/stage-prompts/{README.md,
DASH-001.md … DASH-010.md}`, `docs/reports/agentos-dashboard/.gitkeep`, plus the stage report.
**Allowed files (modify)**: `docs/TASK_QUEUE.md` (append a self-contained "AgentOS Dashboard
program" section enrolling DASH-001 as the sole `Current` task and DASH-002..DASH-010 as
`Planned`, each as its own `## DASH-00X — …` heading with a `Status:` line so
`workflowctl check-task-state` parses them), `docs/current_task.md` (mirror DASH-001 as the
sole Current task with its acceptance criteria), `docs/remaining_tasks.md` (mirror the Current
and Planned DASH entries), `docs/PROJECT_STATE.md` ("In progress"/"Planned" prose only — keep
the `Current Version:` fact line byte-identical), `docs/DECISION_LOG.md` (one prepended dated
entry recording the program-enrollment decision, per `docs/AGENT_PROTOCOL.md`'s
record-the-change rule), `docs/CHANGELOG.md` (an Unreleased note).

**Forbidden**: everything else — no code, no `src/`, `tests/`, `scripts/`, `examples/`; no
dependency or configuration change (`pyproject.toml`, `.pre-commit-config.yaml`,
`self-governance.yaml` untouched); no `handover/**` change (the manifest refresh is a
human-gated step and `handover/PROJECT_HANDOVER.md` is not modified by this stage); no
`docs/implementation/orchestration/**` change; no successor promotion beyond
enrollment-as-Planned.

**Content requirements**: transcribe the approved master plan faithfully into the planning
files, adapted to this repository's real governance (no silent redesign; every adaptation is
recorded in `../DECISIONS.md` DD-03); STAGE_REGISTRY.md lists DASH-001..010 with states
(DASH-001 `IN_PROGRESS`, others `NOT_STARTED`), preconditions, roles, branch names, and report
paths; `stage-prompts/README.md` contains the SSP verbatim and the usage rules; each
`stage-prompts/DASH-00X.md` contains only that stage's canonical prompt and notes;
OPEN_QUESTIONS.md carries OD-D1..OD-D9 with owner dispositions where given (OD-D9 open).

**Validation**: documentation gates only — repo-relative link/path check across all new files,
terminology/status consistency search (no file may claim any DASH stage beyond DASH-001 is
active; no file may reference the mis-targeted repository's governance stack),
`git diff --check`, file-scope audit proving no runtime/test/dependency change,
`python -m pytest tests --collect-only -q` collection count unchanged,
`workflowctl verify --config self-governance.yaml` with task-state/governance/handover PASS
(any `check-git` upstream failure on a local feature branch is identified as pre-existing).

**Acceptance criteria**: (1) all planning files exist and are mutually consistent; (2) DASH
family enrolled with exactly one `Current` task and mirrors agreeing
(`workflowctl check-task-state` PASS); (3) no repository-root governance file is created or
altered beyond the allowed list; (4) the enrollment decision is recorded in
`docs/DECISION_LOG.md`; (5) handover checksum verification still PASSes without touching
`handover/**`; (6) zero forbidden-file changes; (7) engine test collection untouched.

Write the report, recommend the commit message above, then STOP per SSP.

## Stage-Specific Notes

Preconditions: OD-D1 resolved (owner authorization); no other `Current` task anywhere in
`docs/TASK_QUEUE.md`. Risk: the task-state parser (`workflowctl check-task-state`) reads
`## <ID> — …` headings with `Status: Current|Planned|Done` lines and Markdown table rows —
keep DASH queue entries in exactly that shape and never mention a task ID with a conflicting
status in a mirror document.
