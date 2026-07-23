# DASH-004 — Local Backend and Dashboard Shell

| Field | Value |
|---|---|
| **Stage** | DASH-004 · Role: Dashboard implementation session |
| **Branch** | `feature/dash-004-dashboard-shell` |
| **Commit message** | `feat(dashboard): add local dashboard shell with security baseline (DASH-004)` |
| **Report** | `docs/reports/agentos-dashboard/STAGE-04-completion.md` |
| **Status/Version** | Draft · 1.0 |

Apply the Standard Stage Protocol in `README.md` in full.

## Canonical Prompt

You are the **Dashboard implementation session** executing **DASH-004 — Local backend and
dashboard shell**. Preconditions: DASH-003 `COMPLETE`; **OD-D9 resolved by the Human Owner**
(serving-stack dependency decision, including where the dependency is declared); recorded
authorization; branch `feature/dash-004-dashboard-shell`.

**Allowed**: create `agentos_dashboard/{main.py, __main__.py, settings.py, web/**, api/**}`,
templates/static under `agentos_dashboard/web/` (self-hosted assets only, English operator UI),
tests; SSP documentation updates; plus exactly the dependency-declaration change OD-D9's
disposition names (and nothing else outside `agentos_dashboard/`).

**Build**: app factory with `{ok, data, error}` envelope and typed handlers; `AWED_`-prefixed
environment settings parsed into a Pydantic model (no `.env` file loading); a
`python -m agentos_dashboard` entry that refuses any non-loopback bind, acquires a PID
lockfile, and prints the exact URL; middleware: Host-header allowlist
(`localhost`/`127.0.0.1` with port), CSP `default-src 'self'`, `X-Content-Type-Options`,
`Cache-Control: no-store`, per-session CSRF token enforced on POST; endpoints
EP-01/EP-02/EP-03/EP-20; base layout + Overview page (PG-01) rendering live snapshot data with
healthy-empty states ("No Current task — expected between authorized tasks").

**Security tests**: non-loopback refusal, foreign-Host rejection, CSRF negative cases, CSP
header presence. No repository write exists in any code path.

Write the report, recommend the commit message above, then STOP per SSP.

## Stage-Specific Notes

Reference: `../SECURITY_MODEL.md` SC-01..SC-05, SC-10, SC-36; `../API_SPEC.md` §1;
`../OPEN_QUESTIONS.md` OD-D9.
