# DASH-006 — Git, Upstream, Handover, and Consistency Views

| Field | Value |
|---|---|
| **Stage** | DASH-006 · Role: Dashboard implementation session |
| **Branch** | `feature/dash-006-git-handover-views` |
| **Commit message** | `feat(dashboard): add git, upstream, handover and consistency views (DASH-006)` |
| **Report** | `docs/reports/agentos-dashboard/STAGE-06-completion.md` |
| **Status/Version** | Draft · 1.0 |

Apply the Standard Stage Protocol in `README.md` in full.

## Canonical Prompt

You are the **Dashboard implementation session** executing **DASH-006 — Git, upstream,
handover, and consistency views**. Preconditions: DASH-005 `COMPLETE`; recorded authorization;
branch `feature/dash-006-git-handover-views`.

**Allowed**: create git/handover/consistency services, routes (EP-09..EP-12), templates
(PG-07/PG-09/PG-11), tests in `agentos_dashboard/**`; SSP documentation updates.

**Build**: Git page (status, staged/modified/untracked, recent commits, branches with
merged-into-target indication, tags, ahead/behind); upstream verification mirroring
`workflowctl check-git` semantics (default branch `main`, upstream presence, ahead/behind;
violation = Blocker-severity finding, DR-081); doc-referenced commit resolution badges (every
SHA named in governance documents — e.g., the `expected_base_head`/`implementation_commit`
values in `implementation-state.yaml` and commit SHAs in `docs/DECISION_LOG.md` — resolved via
gitread, TR-07); handover viewer rendering the handover pair with recomputed checksum
verification (`handover/PROJECT_CHECKSUM.md` semantics), MISSING rows, and stale warnings when
the narrative is older than the governance mirrors it summarizes; consistency page listing
findings with both-sided file+line sources and local acknowledgment notes (in-memory until
DASH-008).

**Constraint**: no destructive or mutating Git affordance may exist in any template or route.

Write the report, recommend the commit message above, then STOP per SSP.

## Stage-Specific Notes

Reference: DR-080..DR-083, DR-100..DR-102, DR-120; SC-28, SC-29, SC-31.
