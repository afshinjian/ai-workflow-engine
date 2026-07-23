# AgentOS Dashboard — Source of Truth

| Field | Value |
|---|---|
| **Title** | AgentOS Dashboard — Source of Truth |
| **Purpose** | Normative authority rules (TR-##): which data is authoritative, mirrored, or derived; synchronization, contradiction, missing-data, and staleness behavior; the MVP write boundary. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Documentation & Governance session · Human Owner (approval) |
| **Dependencies** | `MASTER_PLAN.md` §1; `ARCHITECTURE.md`; `self-governance.yaml` |
| **Related Documents** | `DATA_MODEL.md`, `SECURITY_MODEL.md` SC-30..SC-32 |

## Table of Contents
1. Rules · 2. Authority Table · 3. Watched Files · 4. Decision References ·
5. Open Questions · 6. Future Revisions

## 1. Rules

- **TR-01** The dashboard never selects a winner between contradictory authoritative records:
  it renders both, raises a ConsistencyFinding, and advises STOP (mirroring
  `docs/CONTEXT.md` step 7: a document/reality disagreement is itself the most urgent thing to
  report).
- **TR-02** Parsed views are derived, non-authoritative, and always carry file+line provenance
  and a raw-source fallback.
- **TR-03** For task execution state, `docs/TASK_QUEUE.md` governs; `docs/current_task.md` and
  `docs/remaining_tasks.md` are mirrors (exactly as `workflowctl check-task-state` treats
  them) and are displayed as such, never merged.
- **TR-04** Missing authoritative data renders an explicit "unknown" state plus a finding —
  never a silent default.
- **TR-05** Staleness is computed from the snapshot fingerprint (watched-file mtimes + HEAD);
  divergence produces a banner, not a silent refresh.
- **TR-06** The dashboard's local database is never authoritative over repository state;
  deleting it must not affect any governance conclusion.
- **TR-07** Every doc-named commit SHA is verified against Git; unresolvable references are
  findings.
- **TR-08** The MVP writes only to the local database (runs, drafts, notes, audit); zero
  repository writes exist.
- **TR-09** For orchestration (`ORCH`) feature state,
  `docs/implementation/orchestration/implementation-state.yaml` governs (per that package's
  `README.md`); it is displayed as a separate program view and never merged into the task
  queue.

## 2. Authority Table

| Data | Authoritative | Mirror(s) | Dashboard view | Contradiction / missing / stale behavior | MVP write |
|---|---|---|---|---|---|
| Live project state | `docs/PROJECT_STATE.md` | `handover/PROJECT_HANDOVER.md` (narrative) | Overview fields | TR-01 / TR-04 / TR-05 | No |
| Task execution state | `docs/TASK_QUEUE.md` | `docs/current_task.md`, `docs/remaining_tasks.md` | Board, task detail | TR-01, TR-03 | No |
| Version fact | `pyproject.toml` + `docs/PROJECT_STATE.md` (must agree; `workflowctl check-governance`) | — | Overview badge | disagreement → finding | No |
| Decisions | `docs/DECISION_LOG.md` (dated entries, newest first) | program `DECISIONS.md` (DD-##, subordinate) | Decision browser | both displayed, labeled; conflicts → finding | No |
| Blockers / risks | `docs/PROJECT_STATE.md` Blockers section; ORCH stage `blockers` | — | Issues panel | TR-01/04 | No |
| Completion/validation reports | `docs/reports/**`, `docs/*_VALIDATION.md`, `docs/FINAL_COMPLETION_REPORT.md` | — | Evidence views | missing report → finding | No |
| Handover pair | `handover/PROJECT_HANDOVER.md` + `handover/PROJECT_CHECKSUM.md` (manifest) | — | Handover viewer | checksum mismatch / MISSING / source-newer warnings | No |
| ORCH feature state | `docs/implementation/orchestration/implementation-state.yaml` | package evidence/reviews/handoffs | Orchestration view | TR-09; schema-invalid state → finding | No |
| Git history/tags/merges | Git | prose references in docs | Git pages | TR-07 | No |
| PR evidence | GitHub (remote) | merge commits + doc references | PR reference list | unverified label (OD-D7) | No |
| Runs / drafts / notes / audit | dashboard.db (local, non-authoritative) | — | Run/audit pages | reconciliation check vs repo; divergence → finding | **Yes (only these)** |

## 3. Watched Files (snapshot fingerprint inputs)

`docs/PROJECT_STATE.md`, `docs/TASK_QUEUE.md`, `docs/current_task.md`,
`docs/remaining_tasks.md`, `docs/CONTEXT.md`, `docs/DECISION_LOG.md`, `docs/CHANGELOG.md`,
`self-governance.yaml`, `pyproject.toml`, `handover/PROJECT_HANDOVER.md`,
`handover/PROJECT_CHECKSUM.md`,
`docs/implementation/orchestration/implementation-state.yaml`, plus Git `HEAD`. Extension of
this list is a MINOR change.

## 4. Decision References
DD-01, DD-03.

## 5. Open Questions
OD-D7 (PR verification, deferred).

## 6. Future Revisions
Any change to an "Authoritative" cell is MAJOR and requires Human Owner approval.
