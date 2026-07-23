# DASH-005 — Workflow Board and Task Detail

| Field | Value |
|---|---|
| **Stage** | DASH-005 · Role: Dashboard implementation session |
| **Branch** | `feature/dash-005-board-task-detail` |
| **Commit message** | `feat(dashboard): add workflow board and task detail views (DASH-005)` |
| **Report** | `docs/reports/agentos-dashboard/STAGE-05-completion.md` |
| **Status/Version** | Draft · 1.0 |

Apply the Standard Stage Protocol in `README.md` in full.

## Canonical Prompt

You are the **Dashboard implementation session** executing **DASH-005 — Workflow board and task
detail**. Preconditions: DASH-004 `COMPLETE`; recorded authorization; branch
`feature/dash-005-board-task-detail`.

**Allowed**: create board/task services, API routes (EP-04/EP-05/EP-06), templates
(PG-02/PG-03), tests within `agentos_dashboard/**`; SSP documentation updates.

**Build**: board with queue lanes for the three `docs/TASK_QUEUE.md` statuses
(Planned/Current/Done), a per-task workflow-stage strip driven by a coded mirror of the
engine's seven workflow stages and fixed transition table (display-only), and a visually
separated program lane rendering ORCH stages from `implementation-state.yaml` (statuses
NOT_STARTED..REVIEW_APPROVED, blockers, prerequisites); unclassified lane + finding for
unknown statuses; card fields per `../PRODUCT_SPEC.md` DR-020..DR-023; task detail page with
recorded scope, acceptance-criteria checklist, lifecycle history parsed from queue prose (and
persisted workflow events where present), verified Git provenance badges, linked
decision/report references, and a raw-source toggle showing the exact Markdown section.

**Acceptance**: the real repository renders GOV-1 and T-501 as Done — including the
multi-round review history recorded in their queue prose (e.g., T-401's two-round plan
review) — and DASH-001 in its actual state; zero interactive mutation affordances exist.

Write the report, recommend the commit message above, then STOP per SSP.

## Stage-Specific Notes

Reference: `../PRODUCT_SPEC.md` DR-020..DR-033; the engine's workflow model
(`src/ai_workflow_engine/workflow/`, read as prior art only, never imported or modified).
