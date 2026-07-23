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

Populated at DASH-010; empty until then.

## 6. Decision References
DD-01, DD-03.

## 7. Open Questions
OD-D6, OD-D7 (deferred features); OD-D9 (dependency decision required before DASH-004).

## 8. Future Revisions
Scope changes are MAJOR and require Human Owner approval.
