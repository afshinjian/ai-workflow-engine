# DASH-003 — Governance and Markdown Parsing

| Field | Value |
|---|---|
| **Stage** | DASH-003 · Role: Dashboard implementation session |
| **Branch** | `feature/dash-003-governance-parsing` |
| **Commit message** | `feat(dashboard): add governance parsing and consistency engine (DASH-003)` |
| **Report** | `docs/reports/agentos-dashboard/STAGE-03-completion.md` |
| **Status/Version** | Draft · 1.0 |

Apply the Standard Stage Protocol in `README.md` in full.

## Canonical Prompt

You are the **Dashboard implementation session** executing **DASH-003 — Governance and Markdown
parsing**. Preconditions: DASH-002 `COMPLETE`; recorded authorization; branch
`feature/dash-003-governance-parsing`.

**Allowed**: create `agentos_dashboard/parsing/**`,
`agentos_dashboard/services/consistency.py`, tests + malformed-document fixture corpus;
SSP documentation updates. Stdlib + already-pinned dependencies only.

**Build** tolerant, confidence-scored parsers for: `docs/PROJECT_STATE.md` (summary, version
fact, Blockers); `docs/TASK_QUEUE.md` task sections (`## <ID> — …` headings with
`Status: Current|Planned|Done`, matching the semantics of `workflowctl check-task-state`) and
the mirrors `docs/current_task.md` and `docs/remaining_tasks.md`, extracting recorded scope /
acceptance-criteria prose with file+line provenance; `docs/DECISION_LOG.md` dated entries;
`docs/implementation/orchestration/implementation-state.yaml` (safe YAML loading with
duplicate-key rejection; stages, statuses, prerequisites, blockers, evidence paths — read-only,
TR-09); handover checksum manifest (`handover/PROJECT_CHECKSUM.md`) parsing + recomputation.
Build the consistency engine v1 with rules: queue-vs-mirror agreement (mirroring
`check-task-state`), version-fact equality across `pyproject.toml` and
`docs/PROJECT_STATE.md` (mirroring `check-governance`), sole-Current invariant
(`maximum_current_tasks: 1`), doc-named commit existence (via gitread), handover checksum +
staleness, implementation-state schema sanity, parse-failure findings. Every parser failure
degrades to raw text + ConsistencyFinding — no exceptions escape.

**Acceptance** includes detecting a fixture reproduction of a deliberate
PROJECT_STATE-vs-TASK_QUEUE contradiction and a tampered handover manifest, and checksum
recomputation matching `handover/PROJECT_CHECKSUM.md`'s digest for the real repository.

Write the report, recommend the commit message above, then STOP per SSP.

## Stage-Specific Notes

Risk: prose heterogeneity → confidence scoring, never hard-fail. Reference:
`../SOURCE_OF_TRUTH.md` TR-01..TR-09. The engine's parser
(`src/ai_workflow_engine/governance/parser.py`) defines the authoritative task-status
semantics; mirror them, do not import or modify the engine.
