# DASH-010 — Integration Testing, Documentation, and Local Release Readiness

| Field | Value |
|---|---|
| **Stage** | DASH-010 · Role: Dashboard implementation session |
| **Branch** | `feature/dash-010-release-readiness` |
| **Commit message** | `docs(dashboard): complete MVP integration, docs and release readiness (DASH-010)` |
| **Report** | `docs/reports/agentos-dashboard/STAGE-10-completion.md` |
| **Status/Version** | Draft · 1.0 |

Apply the Standard Stage Protocol in `README.md` in full.

## Canonical Prompt

You are the **Dashboard implementation session** executing **DASH-010 — Integration testing,
documentation, and local release readiness**. Preconditions: DASH-009 `COMPLETE`; recorded
authorization; branch `feature/dash-010-release-readiness`.

**Allowed**: `agentos_dashboard/**` (E2E/golden tests, startup checks),
`docs/agentos-dashboard/{OPERATIONS.md, STAGE_REGISTRY.md, MVP_SCOPE.md}`; SSP documentation
updates.

**Build**: end-to-end tests driving the full page set against a constructed fixture repository
and read-only against this repository; golden-file snapshots of key pages;
`python -m agentos_dashboard --check` self-test (bind guard, lock, snapshot build, DB open);
port-in-use behavior; `OPERATIONS.md` covering start/stop, the manual handover manifest-refresh
procedure (per `handover/PROJECT_CHECKSUM.md`'s own instructions; OD-D6), dashboard.db
backup/disposal, troubleshooting, and the explicit statement of prohibited operations.

**Confirm**: full dashboard suite green; engine suite collection unchanged; all ten stage
reports exist; registry states accurate. This stage recommends MVP closure to the Human Owner —
it does not declare acceptance itself.

Write the report, recommend the commit message above, then STOP per SSP.

## Stage-Specific Notes

Cold-start acceptance: a fresh clone (Conda env `ai-workflow-engine` present) reaches a correct
Overview in ≤ 2 commands. Reference: `../MVP_SCOPE.md` §4.
