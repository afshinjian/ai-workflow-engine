# AgentOS Dashboard — MVP Scope

| Field | Value |
|---|---|
| **Title** | AgentOS Dashboard — MVP Scope |
| **Purpose** | Binding boundary of the first release: included, deferred, prohibited, and the MVP acceptance definition. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Dashboard implementation session · Human Owner (approval) |
| **Dependencies** | `PRODUCT_SPEC.md` |
| **Related Documents** | `SECURITY_MODEL.md` §5, `STAGE_REGISTRY.md` |

## Table of Contents
1. Included · 2. Deferred · 3. Prohibited · 4. MVP Acceptance Definition · 5. Closure Record ·
6. Decision References · 7. Open Questions · 8. Future Revisions

## 1. Included (DR-010..DR-123)

Repository connection (fixed to the containing repo root); read-only snapshot; governance
document parsing; task queue and workflow visualization; task detail; orchestration (`ORCH`)
feature-state visibility; consistency detection; Git status and upstream visibility; handover
visibility with checksum verification; stage prompt generation with precondition refusal;
prompt copy/export; local manual run records; validation evidence display; draft approvals and
notes; audit timeline; security hardening; operator documentation.

## 2. Deferred

DR-900..DR-912 (`PRODUCT_SPEC.md` §4).

## 3. Prohibited

`SECURITY_MODEL.md` §5, without exception.

## 4. MVP Acceptance Definition

All DASH-001..010 stages `COMPLETE` per `STAGE_REGISTRY.md`; every included DR has passing TC
coverage recorded in stage reports; engine test collection unchanged throughout; Human Owner
records final MVP acceptance.

## 5. Closure Record

**DASH-010, 2026-08-11 — MVP closure recommended to the Human Owner; not self-declared.** This
stage does not accept the MVP on its own authority (`stage-prompts/DASH-010.md`: "This stage
recommends MVP closure to the Human Owner — it does not declare acceptance itself"); the
recommendation below is evidence for that separate decision.

- **§4 acceptance definition, checked:** DASH-001..009 are `COMPLETE` per `STAGE_REGISTRY.md` §3;
  DASH-010 itself is `IN_PROGRESS` (this implementation), uncommitted, and requires its own
  Human Owner approval before it too is `COMPLETE` — the acceptance definition's first clause is
  therefore not yet fully satisfied, and closure cannot be declared *by* this stage in this
  session regardless of what else passes.
- **Included DRs (§1):** every included DR has a named delivery/evidence owner in
  `STAGE_REGISTRY.md` §5's per-requirement table (PLAN-001/DD-16 closed the prior gaps), and each
  owning stage's own completion report records passing TC coverage. DR-121's *final* cross-page
  verification — this stage's own responsibility — passed against all 14 delivered routes in
  both fresh and genuinely stale repository states, followed by explicit refresh. DR-122's final
  UI-level checks cover the parsed values and raw fallbacks on Overview, Board, Task detail,
  Stages/Prompts, Git, Governance, Orchestration, Handover, and Consistency; database-backed pages
  retain record/run/report provenance under their owning-stage tests. See
  `docs/reports/agentos-dashboard/STAGE-10-completion.md` for the exact evidence.
- **Engine test collection unchanged throughout:** confirmed for this stage's diff — no file
  under `src/`, `tests/`, `agentos_workflow/**`, `scripts/`, or `pyproject.toml` was touched (see
  the completion report's scope audit and collection-count evidence).
- **Not yet true:** DASH-010 is not `COMPLETE`, so the acceptance definition's first bullet is
  not met until the Human Owner approves this implementation and the registry records `COMPLETE`.

**Recommendation:** once this independently reviewed implementation is approved and DASH-010 moves
to `COMPLETE`, the Human Owner may reasonably record final MVP acceptance. The bounded final
machine review corrected its in-scope findings and left no unresolved BLOCKER/HIGH/MEDIUM issue.
That final acceptance act, and any closure narrative beyond this evidence summary, remains the
Human Owner's alone.

## 6. Decision References
DD-01, DD-03.

## 7. Open Questions
OD-D6, OD-D7 (deferred features); OD-D9 (dependency decision — resolved 2026-07-29: FastAPI +
Uvicorn + Jinja2 in the optional `dashboard` group; DASH-004 is no longer gated on it).

## 8. Future Revisions
Scope changes are MAJOR and require Human Owner approval.
