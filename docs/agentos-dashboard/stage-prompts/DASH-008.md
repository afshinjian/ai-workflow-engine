# DASH-008 — Run Records, Evidence, and Audit Timeline

| Field | Value |
|---|---|
| **Stage** | DASH-008 · Role: Dashboard implementation session |
| **Branch** | `feature/dash-008-runs-evidence-audit` |
| **Commit message** | `feat(dashboard): add run records, evidence and audit timeline (DASH-008)` |
| **Report** | `docs/reports/agentos-dashboard/STAGE-08-completion.md` |
| **Status/Version** | Draft · 1.0 |

Apply the Standard Stage Protocol in `README.md` in full.

## Canonical Prompt

You are the **Dashboard implementation session** executing **DASH-008 — Run records, evidence,
and audit timeline**. Preconditions: DASH-007 `COMPLETE`; recorded authorization; branch
`feature/dash-008-runs-evidence-audit`.

**Allowed**: create `agentos_dashboard/storage/**` (stdlib `sqlite3`),
run/approval/finding/note/audit services, routes (EP-15..EP-18, EP-22, EP-23), templates
(PG-05/PG-06/PG-10), tests; SSP documentation updates. This repository has no `data/`
directory: create `data/agentos_dashboard/` at runtime and add the narrowest `.gitignore` rule
covering it (allowed modification: `.gitignore`), disclosing the addition in the report.

**Build**: `dashboard.db` with `PRAGMA user_version = 1`, foreign keys ON; tables per
`../DATA_MODEL.md` §3 including an **append-only** `audit_events` table (no UPDATE/DELETE
statement anywhere; assert by source scan and behavior) + JSONL mirror; idempotent POSTs via
client UUIDs (replay returns original); run records verifying report-path existence and linking
prompt hashes; evidence pages splitting repo-verified from user-claimed values; merged audit
timeline. The database is non-authoritative: deleting it must not break any read-only view
(test).

Write the report, recommend the commit message above, then STOP per SSP.

## Stage-Specific Notes

Reference: DR-050..DR-071, DR-110..DR-111; EN-11..EN-29; SC-21..SC-24, SC-30, SC-33; OD-D5.
