# AgentOS Dashboard — UI Specification

| Field | Value |
|---|---|
| **Title** | AgentOS Dashboard — UI Specification |
| **Purpose** | Page register (PG-01..12), global design rules, state matrix, and interaction conventions. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Dashboard implementation session · Human Owner (approval) |
| **Dependencies** | `PRODUCT_SPEC.md`; `API_SPEC.md`; `SECURITY_MODEL.md` |
| **Related Documents** | `ARCHITECTURE.md` §6 |

## Table of Contents
1. Global Rules · 2. State Matrix · 3. Page Register · 4. Badge Vocabulary ·
5. Decision References · 6. Open Questions · 7. Future Revisions

## 1. Global Rules

English operator UI (DR-123). Left navigation: Overview, Board, Tasks, Stages & Prompts, Runs,
Evidence, Git, Governance, Orchestration, Handover, Audit, Consistency, Settings. Persistent
header: branch · snapshot age · upstream badge · staleness banner. Design system: minimal
custom CSS, self-hosted assets only (no CDN, SC-05). Status uses color **plus** text+icon
(color-blind safe). Confirmation dialog on every POST. Read-only is the default everywhere.
Dark mode via `prefers-color-scheme`. Tables: client-side sort/filter, pagination over ~200
rows. Large logs: head/tail with download (SC-35). Copy uses the Clipboard API with fallback.
Keyboard: full tab order, `/` focuses search, `Esc` closes dialogs. ARIA landmarks and labels.
Desktop-first, responsive to ~1024 px.

## 2. State Matrix (every page)

Loading = skeleton · Empty = explicit text; healthy-empty states say "— expected" (DR-013) ·
Error = typed message + retry, never a traceback · Stale = banner + refresh action (SC-32) ·
Contradiction = inline finding chips linking to PG-11.

## 3. Page Register

| ID | Page (route) | Purpose / key components | Visible actions | Disabled/absent |
|---|---|---|---|---|
| PG-01 | Overview `/` | status tiles, current-task panel, blockers, gate health, Git/upstream/handover badges, last event | Refresh | any mutation |
| PG-02 | Board `/board` | queue lanes (Planned/Current/Done) + workflow-stage strip + ORCH program lane; transition chips | filter, open task | drag/drop absent (DR-023) |
| PG-03 | Task detail `/tasks/{id}` | record, AC checklist, history, provenance, evidence links, raw toggle | copy section, note | edit absent |
| PG-04 | Prompt generator `/stages` | registry, precondition panel, preview, rendered prompt | generate, copy, export | generate disabled with itemized reasons (DR-041) |
| PG-05 | Run detail `/runs/{uuid}` | record fields, prompt-hash link, verification flags | create, add note | editing verified fields absent |
| PG-06 | Evidence `/evidence` | gate matrix, verified-vs-claimed split | filter, open report | re-run buttons absent |
| PG-07 | Git `/git` | status, commits, branches, tags, upstream check, merge map | copy SHA | all mutations absent (DR-083) |
| PG-08 | Governance `/governance` | doc browser, search, cross-refs, authority chain | search, anchor nav | editing absent |
| PG-09 | Handover `/handover` | handover pair, checksum table, staleness | copy manual refresh procedure | refresh button absent (OD-D6) |
| PG-10 | Audit `/audit` | merged timeline, filters | filter, export copy | deletion absent (SC-22) |
| PG-11 | Consistency `/consistency` | findings with both-sided file+line sources, history | acknowledge (local note) | auto-fix absent |
| PG-12 | Settings `/settings` | repo root (display), bind/port, caps, lock status, about | copy config | repo switching absent |

The Orchestration view (EP-18) renders inside PG-02's program lane and as a drill-down under
PG-03-style detail for ORCH stages; it introduces no separate mutation surface.

## 4. Badge Vocabulary

`VERIFIED` (repo-verified) · `CLAIMED` (user-entered) · `PASS` / `FAIL` / `UNKNOWN` ·
`STALE` · `MISSING` · `UNCLASSIFIED` · `NON-AUTHORITATIVE (local)` · `DEFERRED` ·
severity: `BLOCKER` / `MAJOR` / `MINOR` / `OBSERVATION`.

## 5. Decision References
DD-01, DD-03.

## 6. Open Questions
OD-D9 (templating engine; page contracts are engine-independent).

## 7. Future Revisions
New pages require PRODUCT_SPEC DR coverage first.
