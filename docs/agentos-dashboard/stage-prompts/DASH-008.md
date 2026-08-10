# DASH-008 — Run Records, Evidence, and Audit Timeline

| Field | Value |
|---|---|
| **Stage** | DASH-008 · Role: Dashboard implementation session |
| **Branch** | `feature/dash-008-runs-evidence-audit` |
| **Commit message** | `feat(dashboard): add run records, evidence and audit timeline (DASH-008)` |
| **Report** | `docs/reports/agentos-dashboard/STAGE-08-completion.md` |
| **Status/Version** | Draft · 1.1 |

Apply the Standard Stage Protocol in `README.md` in full.

## Canonical Prompt

You are the **Dashboard implementation session** executing **DASH-008 — Run records, evidence,
and audit timeline**. Preconditions: DASH-007 `COMPLETE`; recorded authorization; branch
`feature/dash-008-runs-evidence-audit`.

**Allowed**: create `agentos_dashboard/storage/**` (stdlib `sqlite3`),
run/approval/finding/note/audit/**orchestration** services, routes (EP-15, EP-16, EP-17,
**EP-18**, EP-22, EP-23), templates (PG-05/PG-06/PG-10), tests; SSP documentation updates. This
repository has no `data/` directory: create `data/agentos_dashboard/` at runtime and add the
narrowest `.gitignore` rule covering it (allowed modification: `.gitignore`), disclosing the
addition in the report.

**Build**: `dashboard.db` with `PRAGMA user_version = 1`, foreign keys ON; tables per
`../DATA_MODEL.md` §3 including an **append-only** `audit_events` table (no UPDATE/DELETE
statement anywhere; assert by source scan and behavior) + JSONL mirror; idempotent POSTs via
client UUIDs (replay returns original); run records verifying report-path existence and linking
prompt hashes; evidence pages splitting repo-verified from user-claimed values; merged audit
timeline. The database is non-authoritative: deleting it must not break any read-only view
(test).

**Build — EP-18 orchestration view, made an explicit stage responsibility by PLAN-001
(documentation only — not implemented by this correction):** `GET /orchestration` (EP-18) is a
strictly **read-only** endpoint reading the ORCH feature-state (stages, blockers, evidence paths)
from the existing orchestration parser/state source DASH-003 already delivers
(`implementation-state.yaml` parsing, TR-09) — no new parsing layer, no new persistence, and no
dependency on this stage's own `dashboard.db` for its data. Per `../UI_SPEC.md` §3, EP-18
introduces **no separate page**: it renders inside PG-02's board program lane and as a
PG-03-style drill-down for ORCH stages, so no new route template is created for it beyond that
existing surface's data source.

**Acceptance**: idempotent-POST replay returns the original record; the append-only audit table
has no UPDATE/DELETE code path (source scan); deleting `dashboard.db` does not break any
read-only view. EP-18 specifically: the endpoint is reachable with zero write to `dashboard.db`,
zero Git invocation, and zero agent/subprocess invocation (each proved by a negative test); its
response is read-only ORCH feature-state, never a mutation affordance.

Write the report, recommend the commit message above, then STOP per SSP.

## Stage-Specific Notes

Reference: DR-050..DR-071, DR-110..DR-111; **EP-18**; EN-11..EN-29; SC-21..SC-24, SC-30, SC-33;
OD-D5. The EP-18 clause above was added by PLAN-001 (2026-08-10, governance/documentation-only
correction) to make an already-allowlisted endpoint an explicit Build/Acceptance responsibility
rather than a bare mention inside the EP-15..EP-18 range; no code for it exists yet and none was
written by that correction.
