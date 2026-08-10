# DASH-010 — Integration Testing, Documentation, and Local Release Readiness

| Field | Value |
|---|---|
| **Stage** | DASH-010 · Role: Dashboard implementation session |
| **Branch** | `feature/dash-010-release-readiness` |
| **Commit message** | `docs(dashboard): complete MVP integration, docs and release readiness (DASH-010)` |
| **Report** | `docs/reports/agentos-dashboard/STAGE-10-completion.md` |
| **Status/Version** | Draft · 1.1 |

Apply the Standard Stage Protocol in `README.md` in full.

## Canonical Prompt

You are the **Dashboard implementation session** executing **DASH-010 — Integration testing,
documentation, and local release readiness**. Preconditions: DASH-009 `COMPLETE`; recorded
authorization; branch `feature/dash-010-release-readiness`.

**Allowed**: `agentos_dashboard/**` (E2E/golden tests, startup checks, **and the bounded read-only
PG-12 Settings/About surface** — a minimal route/service reusing existing snapshot/health/lock
data plus a template, added by PLAN-001's contract amendment below),
`docs/agentos-dashboard/{OPERATIONS.md, STAGE_REGISTRY.md, MVP_SCOPE.md}`; SSP documentation
updates.

**Build**: end-to-end tests driving the full page set against a constructed fixture repository
and read-only against this repository; golden-file snapshots of key pages;
`python -m agentos_dashboard --check` self-test (bind guard, lock, snapshot build, DB open);
port-in-use behavior; `OPERATIONS.md` covering start/stop, the manual handover manifest-refresh
procedure (per `handover/PROJECT_CHECKSUM.md`'s own instructions; OD-D6), dashboard.db
backup/disposal, troubleshooting, and the explicit statement of prohibited operations.

**Build — PG-12 Settings/About (added by PLAN-001; documentation only — not implemented by this
correction):** a bounded, strictly **read-only** Settings/About page. Allowed conceptual content
is limited to what `../UI_SPEC.md` PG-12 and `../PRODUCT_SPEC.md` already support: repository root
display, bind address/port, configured caps, lock status, and application/about information, plus
a browser-side copy-config action (clipboard only — no server-side config write). Explicitly
excluded: editable runtime configuration, persistent user preferences, governance editing,
repository switching, agent/provider configuration, secret editing, and any authoritative write —
this page carries **zero** mutation affordance, matching PG-12's own "repo switching absent" note
and this program's read-only-first posture.

**Build — Final DR-121/DR-122 cross-page verification (added by PLAN-001; documentation only —
not implemented by this correction):** DASH-010 performs the MVP's final verification, across
every page delivered by the completed program, that DR-121 (snapshot staleness banner present and
correct on every page, per `../UI_SPEC.md` §1's persistent header) and DR-122 (every parsed value
links to its file+line, with a raw fallback on parse failure) actually hold — recorded as explicit
per-page evidence in this stage's completion report. This is verification/evidence closure, not
re-implementation: each page-delivering stage (DASH-004 through DASH-008) already builds these
cross-cutting behaviors into its own pages as it goes; DASH-010 does not re-build them, and does
not claim implementation credit those stages' own completion records already hold (rule 8 — those
records are not rewritten by this verification).

**Confirm**: full dashboard suite green; engine suite collection unchanged; all ten stage
reports exist; registry states accurate; PG-12 is confirmed to have zero mutation affordance; the
DR-121/DR-122 cross-page verification evidence above is present and PASS on every delivered page.
This stage recommends MVP closure to the Human Owner — it does not declare acceptance itself.

Write the report, recommend the commit message above, then STOP per SSP.

## Stage-Specific Notes

Cold-start acceptance: a fresh clone (Conda env `ai-workflow-engine` present) reaches a correct
Overview in ≤ 2 commands. Reference: `../MVP_SCOPE.md` §4; **DR-121, DR-122 (final); PG-12**. The
PG-12 and DR-121/DR-122-final clauses above were added by PLAN-001 (2026-08-10,
governance/documentation-only correction); no code for either exists yet and none was written by
that correction.
