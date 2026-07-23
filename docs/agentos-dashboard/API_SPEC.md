# AgentOS Dashboard — API Specification

| Field | Value |
|---|---|
| **Title** | AgentOS Dashboard — API Specification |
| **Purpose** | Endpoint register (EP-##) with conventions, mutation rules, error semantics, and absent-by-design endpoints. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Dashboard implementation session · Human Owner via independent review (approval) |
| **Dependencies** | `DATA_MODEL.md`; `SECURITY_MODEL.md`; `PRODUCT_SPEC.md` |
| **Related Documents** | `UI_SPEC.md`, `ARCHITECTURE.md` |

## Table of Contents
1. Conventions · 2. Read Endpoints · 3. Mutating Endpoints · 4. Absent by Design ·
5. Error Catalogue · 6. Decision References · 7. Open Questions · 8. Future Revisions

## 1. Conventions

Base path `/dash/api/v1`. Envelope `{ok, data, error}` on every response (mirroring the
engine's CLI contract-v2 envelope discipline: `ok=true` requires `data` and no `error`;
`ok=false` requires `error` and no `data`). `Cache-Control: no-store`. GETs are pure (SC-03).
POSTs require the CSRF header and a client idempotency UUID, touch **only** dashboard.db, emit
an AuditEvent on success, and on failure return a typed envelope error with no partial write
(SC-33). Source of truth per endpoint follows `SOURCE_OF_TRUTH.md`.

## 2. Read Endpoints

| ID | Method + path | Purpose | Notes |
|---|---|---|---|
| EP-01 | GET `/health` | liveness, lock, bind, snapshot age | — |
| EP-02 | GET `/snapshot` | snapshot metadata (fingerprint, staleness, confidence) | — |
| EP-03 | GET `/status` | overview aggregate (DR-010..013) | degraded fields flagged |
| EP-04 | GET `/tasks` | board data with status/program filters | unknown status → unclassified |
| EP-05 | GET `/tasks/{id}` | task detail + record + history + provenance | 404 typed |
| EP-06 | GET `/workflow` | workflow-stage machine + per-task allowed/blocked transitions | display-only |
| EP-07 | GET `/governance/docs`, `/governance/docs/{name}` | governance browser | path allowlist only |
| EP-08 | GET `/governance/search?q=` | full-text search (q ≤ 200 chars) | escaped output |
| EP-09 | GET `/git/status`, `/git/commits`, `/git/branches`, `/git/tags` | Git pages | bounded params; timeout → typed error |
| EP-10 | GET `/git/upstream` | upstream/default-branch verification (DR-081) | violation → Blocker finding |
| EP-11 | GET `/handover` | handover pair, checksum verify, staleness | MISSING surfaced |
| EP-12 | GET `/consistency` | findings + history | — |
| EP-13 | GET `/stages` | stage registry + precondition state | — |
| EP-14 | GET `/prompts/{uuid}/export` | download generated prompt `.md` | only previously generated |
| EP-15 | GET `/runs`, `/runs/{uuid}` | run records | — |
| EP-16 | GET `/audit` | merged audit timeline with filters | — |
| EP-17 | GET `/evidence/{ref}` | verified-vs-claimed evidence view | — |
| EP-18 | GET `/orchestration` | ORCH feature-state view (stages, blockers, evidence paths) | read-only; TR-09 |

## 3. Mutating Endpoints (local DB only)

| ID | Method + path | Purpose | Required human action | Prohibited repo mutation | Idempotency |
|---|---|---|---|---|---|
| EP-20 | POST `/snapshot/refresh` | rebuild snapshot | explicit click | none possible (read-only rebuild) | 409 while building |
| EP-21 | POST `/prompts/generate` | generate stage prompt | stage selection under authorization | all | UUID; refusal = 422 with itemized unmet preconditions; success **and** refusal audited |
| EP-22 | POST `/runs` | create manual run record | form submission | all | UUID replay returns original |
| EP-23 | POST `/approvals`, `/findings`, `/notes` | local drafts | form submission | all | UUID; enums enforced |

## 4. Absent by Design

No `exec`, `shell`, `git-write`, `repo-file-write`, `workflowctl-invoke`, or `agent-invoke`
endpoint exists (SC-11, SC-29; DR-912). Their absence is asserted by tests.

## 5. Error Catalogue

`VALIDATION_ERROR` (422, includes unmet-precondition list for EP-21), `NOT_FOUND` (404),
`CSRF_REQUIRED` (403), `HOST_REJECTED` (400, SC-36), `SNAPSHOT_BUILDING` (409),
`GIT_TIMEOUT` (504-equivalent typed error), `INTERNAL` (500, redacted, no traceback).

## 6. Decision References
DD-01, DD-03.

## 7. Open Questions
OD-D9 (serving framework; envelope and endpoint contracts are framework-independent).

## 8. Future Revisions
New endpoints require MAJOR version and independent review; mutating endpoints additionally
require security review.
