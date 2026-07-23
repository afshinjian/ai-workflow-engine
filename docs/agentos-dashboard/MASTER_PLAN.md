# AgentOS Dashboard — Master Plan

| Field | Value |
|---|---|
| **Title** | AgentOS Dashboard — Master Plan |
| **Purpose** | Single entry point and authority anchor for the AgentOS Local Dashboard program in `ai-workflow-engine`: declares subordination to repository governance, fixes the approved product and architecture direction, indexes the complete documentation set, and defines how the set is read, versioned, and changed. |
| **Status** | Draft (becomes Approved upon DASH-001 completion and Human Owner acceptance) |
| **Version** | 1.0 |
| **Owner** | Documentation & Governance session (maintainer) · Human Owner (approving authority) |
| **Dependencies** | Approved implementation-ready master plan (2026-07-23 planning session), as adapted to `ai-workflow-engine` by the 2026-07-23 DASH-001 recovery directive |
| **Related Documents** | All documents listed in §5; `self-governance.yaml`; `docs/AGENT_PROTOCOL.md`; `docs/CONTEXT.md`; `docs/DECISION_LOG.md` |

## Table of Contents

1. [Authority and Subordination](#1-authority-and-subordination)
2. [Program Intent](#2-program-intent)
3. [Approved Architecture Direction](#3-approved-architecture-direction)
4. [Delivery Model](#4-delivery-model)
5. [Document Set Index](#5-document-set-index)
6. [Cold-Start Reading Order](#6-cold-start-reading-order)
7. [Versioning and Status Lifecycle](#7-versioning-and-status-lifecycle)
8. [Change Management](#8-change-management)
9. [Traceability](#9-traceability)
10. [Decision References](#10-decision-references)
11. [Open Questions](#11-open-questions)
12. [Future Revisions](#12-future-revisions)
- [Appendix A — Conformance Table](#appendix-a--conformance-table)
- [Appendix B — Glossary](#appendix-b--glossary)

---

## 1. Authority and Subordination

The AgentOS Dashboard program is subordinate to the repository's existing authority chain and
creates no competing workflow. For `ai-workflow-engine`, authority descends as follows:

1. Human Owner decisions and `docs/AGENT_PROTOCOL.md` (what no agent may do; review discipline).
2. `self-governance.yaml` and the recorded decisions in `docs/DECISION_LOG.md`.
3. The authoritative live state: `docs/TASK_QUEUE.md` and its mirrors
   (`docs/current_task.md`, `docs/remaining_tasks.md`, `docs/PROJECT_STATE.md`), verified by
   `workflowctl check-task-state`, `check-governance`, and `check-handover`.
4. Approved plans: `docs/MASTER_ROADMAP.md`, the milestone plans, and the orchestration design
   package under `docs/implementation/orchestration/`.
5. Approved task plans and acceptance criteria — this documentation set operates at this level.
6. Implementation details.

Binding consequences:

- The dashboard is a **controlled read-only interface over the existing governance layer**, not
  a replacement for it. Markdown records, Git history, `workflowctl` gate results, the
  orchestration implementation state, validation evidence, and human approval remain the
  authoritative sources at all times (`SOURCE_OF_TRUTH.md`).
- No document in this set may contradict `docs/AGENT_PROTOCOL.md`, `self-governance.yaml`, or a
  recorded decision in `docs/DECISION_LOG.md`. A discovered conflict stops work and is reported
  to the Human Owner — the disagreement itself is the most urgent thing to report
  (`docs/CONTEXT.md`).
- Every dashboard implementation stage is an ordinary task enrolled in `docs/TASK_QUEUE.md`,
  executed under the review discipline of `docs/AGENT_PROTOCOL.md`, and closed only with Human
  Owner authority. `STAGE_REGISTRY.md` is a *view* of that lifecycle, never an alternative to it.
- The dashboard program never touches the orchestration (`ORCH`) design package under
  `docs/implementation/orchestration/`; that package keeps its own state, evidence, and session
  protocol, and the dashboard only reads it.
- The Human Owner is the sole stage-authorization authority. Completion of any stage never
  authorizes its successor.

## 2. Program Intent

The program delivers a **local, single-user, localhost-bound, read-only-first web dashboard**
through which the Human Owner can visualize, operate, and govern this repository's governance
layer: project state, the task queue and its mirrors, workflow-stage legality, stage prompt
generation, manual run records, validation evidence, Git and upstream status, handover
integrity, orchestration (`ORCH`) feature-state visibility, consistency findings, and a
complete audit history.

The dashboard is developer/PM tooling; its user interface is English.

The complete requirement register, the conservative MVP boundary, and the deferred-feature
register are normative in `PRODUCT_SPEC.md` and `MVP_SCOPE.md`. The prohibited-operation set —
including arbitrary shell execution, autonomous Git mutation, automatic lifecycle transitions,
automatic task selection, unattended agent execution, and modification of authoritative
governance documents — is normative in `SECURITY_MODEL.md` and applies to every stage without
exception. These prohibitions restate, and may only strengthen, `docs/AGENT_PROTOCOL.md`.

## 3. Approved Architecture Direction

Decision **DD-01** (recorded in `DECISIONS.md`) fixes the architecture:

- **Option 2 — separate local control-plane application in the same repository**: a new
  top-level Python package `agentos_dashboard/`, served at `http://127.0.0.1:8642/`, running
  beside — and fully isolated from — the engine package `src/ai_workflow_engine/` and its
  audited test suite.
- Minimal-dependency posture: the dashboard reuses the already-pinned stack in `pyproject.toml`
  (Pydantic, PyYAML, pytest) wherever possible. `ai-workflow-engine` pins **no web framework**,
  so the HTTP-serving layer requires a Human Owner dependency decision — **OD-D9 in
  `OPEN_QUESTIONS.md`, open** — before DASH-004. Adapter and parsing stages (DASH-002,
  DASH-003) are stdlib + existing-dependency only.
- Repository access is confined to two read-only adapters (root-confined file adapter; Git
  subprocess adapter with a fixed read-only verb allowlist).
- Local persistence is a **non-authoritative** SQLite database for run records, drafts, notes,
  and the append-only audit trail.
- Dashboard tests live in `agentos_dashboard/tests/`, outside the engine suite's configured
  `testpaths = ["tests"]`, so the audited engine test collection is provably unchanged.

The normative component model, adapter contracts, technology selections, topology, and rejected
options are in `ARCHITECTURE.md`. The security controls that constrain this architecture are in
`SECURITY_MODEL.md`. This section is a summary and defines nothing not present in those annexes.

## 4. Delivery Model

Delivery proceeds in ten independently authorized stages, **DASH-001 … DASH-010**, one task
each, executed one at a time under the human-controlled loop:

1. Dashboard (or, before it exists, this documentation set) explains the current state.
2. The Human Owner authorizes exactly one stage in writing.
3. The stage's canonical prompt (`stage-prompts/DASH-00X.md`, applied under the Standard Stage
   Protocol in `stage-prompts/README.md`) is executed in an approved agent tool.
4. The agent implements only that stage, runs the required gates, writes the stage report
   (`STAGE_REPORT_TEMPLATE.md`, reports under `docs/reports/agentos-dashboard/`), and stops.
5. The Human Owner independently reviews (per `docs/AGENT_PROTOCOL.md`, including fresh-session
   independent review where the protocol requires it) and authorizes the next action. Commit
   and push remain human-gated, per `docs/AGENT_PROTOCOL.md` and the `workflowctl commit`/`push`
   gates.

Stage definitions, states, preconditions, control rules, branch discipline, and the
authorization log are normative in `STAGE_REGISTRY.md`. Gate commands and test obligations are
normative in `TEST_STRATEGY.md`.

## 5. Document Set Index

Location: `docs/agentos-dashboard/`. Tiers per the approved documentation architecture.
"Maintaining role" names the discipline of the executing agent session; every approval
ultimately rests with the Human Owner, assisted by independent review sessions per
`docs/AGENT_PROTOCOL.md`.

| Tier | Document | Role | Maintaining role | Approving authority |
|---|---|---|---|---|
| 0 | `MASTER_PLAN.md` | Entry point and authority anchor (this document) | Documentation & Governance session | Human Owner |
| 1 | `ARCHITECTURE.md` | Normative technical architecture | Dashboard implementation session | Human Owner (independent review) |
| 1 | `PRODUCT_SPEC.md` | Master requirement register (DR-###) | Dashboard implementation session | Human Owner |
| 1 | `SECURITY_MODEL.md` | Threat model, controls (SC-##), operation classification | Dashboard implementation session | Human Owner (independent security review) |
| 1 | `SOURCE_OF_TRUTH.md` | Authority/mirror/derived rules (TR-##) | Documentation & Governance session | Human Owner |
| 1 | `DATA_MODEL.md` | Entity catalogue (EN-##), local DB schema | Dashboard implementation session | Human Owner (independent review) |
| 1 | `API_SPEC.md` | Endpoint register (EP-##) | Dashboard implementation session | Human Owner (independent review) |
| 1 | `UI_SPEC.md` | Page specifications (PG-01..12), design rules | Dashboard implementation session | Human Owner |
| 1 | `MVP_SCOPE.md` | Binding in/out/prohibited boundary | Dashboard implementation session | Human Owner |
| 1 | `TEST_STRATEGY.md` | Test classes (TC-##), gates, fixture policy | Dashboard implementation session | Human Owner (independent review) |
| 2 | `STAGE_REGISTRY.md` | Stage states, preconditions, control rules | Documentation & Governance session | Human Owner (authorization) |
| 2 | `stage-prompts/README.md` | Prompt-directory index; sole canonical home of the Standard Stage Protocol; usage rules | Documentation & Governance session | Human Owner |
| 2 | `stage-prompts/DASH-001.md` … `DASH-010.md` | One canonical stage prompt per file, plus stage-specific notes | Documentation & Governance session | Human Owner |
| 2 | `STAGE_REPORT_TEMPLATE.md` | Mandatory stage report skeleton | Documentation & Governance session | Human Owner |
| 3 | `DECISIONS.md` | Append-only program decisions (DD-##) | Documentation & Governance session | Human Owner |
| 3 | `OPEN_QUESTIONS.md` | Owner-decision register (OD-D#) | Documentation & Governance session | Human Owner (dispositions) |
| 3 | `CHANGELOG.md` | Append-only change log (CL entries) | Completing agent per stage | Verified at review |
| 4 | `OPERATIONS.md` | Operator manual (created in DASH-010) | Dashboard implementation session | Human Owner |

Evidence reports live outside this directory at `docs/reports/agentos-dashboard/` and never
define requirements.

Structural rules: Tier 1 documents are normative and must not restate one another; Tier 2
documents reference Tier 1 without redefining it; stage prompt files never reference one another
(stages stay independently authorizable); the Standard Stage Protocol exists only in
`stage-prompts/README.md` and is applied by reference; Tier 3 documents are append-only; every
document references this master plan; duplication discovered at review is a Major finding.

## 6. Cold-Start Reading Order

A fresh agent or reviewer with no prior context reads, in order:

1. `docs/AGENT_PROTOCOL.md`, `docs/CONTEXT.md`, `self-governance.yaml` (repository authority
   and fresh-session recovery).
2. `docs/PROJECT_STATE.md`, `docs/current_task.md`, and `docs/TASK_QUEUE.md` (live
   authoritative state).
3. This document (program entry point).
4. `MVP_SCOPE.md`, then `PRODUCT_SPEC.md` (what is being built and what is not).
5. `ARCHITECTURE.md` and `SECURITY_MODEL.md` (how, and under which controls).
6. `SOURCE_OF_TRUTH.md`, `DATA_MODEL.md`, `API_SPEC.md`, `UI_SPEC.md` (specification detail).
7. `TEST_STRATEGY.md` (verification obligations).
8. `STAGE_REGISTRY.md`, then `stage-prompts/README.md` and the single authorized
   `stage-prompts/DASH-00X.md` (current stage state and canonical execution text).
9. `DECISIONS.md`, `OPEN_QUESTIONS.md`, `CHANGELOG.md` (history and pending questions).

No document in this set substitutes for the repository authority chain in step 1.

## 7. Versioning and Status Lifecycle

- Every document carries the standard header block (Title, Purpose, Status, Version, Owner,
  Dependencies, Related Documents) plus the master-plan conformance pointer in Appendix A.
- Versions use `MAJOR.MINOR`: MINOR for clarifications with no normative change; MAJOR for any
  normative change, which requires the §8 change path.
- Stage prompt files are versioned independently. A MAJOR change to the Standard Stage Protocol
  in `stage-prompts/README.md` requires a recorded impact check against every stage file whose
  stage is not yet `COMPLETE`.
- Statuses: `Draft → Review → Approved → Deprecated`. A document's status can never be more
  advanced than the status of the task carrying it in `docs/TASK_QUEUE.md`. Deprecation is
  append-only: the header gains `Superseded by:`; content is never erased.
- The master plan version is the **set version**: a MAJOR bump in any Tier 1 document forces a
  MINOR bump here and a `CHANGELOG.md` entry.
- Git remains the byte-level history; document versions are semantic markers only.

## 8. Change Management

1. No out-of-band edits: every change to an Approved document travels inside an authorized
   task, per `docs/AGENT_PROTOCOL.md` (governance changes are recorded in
   `docs/DECISION_LOG.md` with their rationale).
2. Post-approval MAJOR changes require, in order: Human Owner authorization →
   `DECISIONS.md` entry → edit → `CHANGELOG.md` entry → re-approval by the §5 authority →
   handover manifest refresh (a human-gated step: `handover/PROJECT_CHECKSUM.md` is updated per
   its own instructions whenever `handover/PROJECT_HANDOVER.md` changes, and verified by
   `workflowctl check-handover`).
3. Reference-first: a change belongs in exactly one document; all others update links only.
4. Impact analysis: every affected document is updated in the same task or explicitly recorded
   as unaffected in the stage report.
5. Contradictions between documents are stop-and-report events per `docs/CONTEXT.md`; no agent
   silently selects a winner.
6. `CHANGELOG.md` is the audit spine: one appended entry per approved change.

## 9. Traceability

The mandatory trace chain, using the stable ID schemes defined in each document:

```text
MASTER_PLAN section → DR-### (PRODUCT_SPEC) → EP-## / EN-## / PG-## / SC-## / TR-##
    → DASH-0XX acceptance criterion (STAGE_REGISTRY / stage-prompts/DASH-00X.md)
    → TC-## (TEST_STRATEGY) → STAGE-XX completion report evidence → commit / merge SHA
```

Deferred capabilities receive `DR-###` identifiers with disposition `DEFERRED` so exclusion is
traceable. Open questions (`OD-D#`) name the IDs they block; `STAGE_REGISTRY.md` preconditions
cite them.

## 10. Decision References

- **DD-01** — Separate local control-plane package (Option 2); see `DECISIONS.md`.
- **DD-02** — Stage prompts as a directory; see `DECISIONS.md`.
- **DD-03** — DASH-001 recovery adaptation to `ai-workflow-engine`; see `DECISIONS.md`.
- Repository decisions binding on this program live in `docs/DECISION_LOG.md`; the
  repository-level enrollment decision for the DASH task family is recorded there during
  DASH-001 (2026-07-23 entry).

## 11. Open Questions

Registered and dispositioned in `OPEN_QUESTIONS.md`: OD-D1 (task-family authorization),
OD-D2 (Markdown rendering approach), OD-D3 (port), OD-D4 (package naming), OD-D5 (local
database), OD-D6 (handover manifest refresh deferral), OD-D7 (GitHub integration deferral),
OD-D8 (test-suite separation), OD-D9 (web-framework dependency — **open**, blocks DASH-004).
None may be resolved outside that register.

## 12. Future Revisions

- v1.x — conformance-pointer updates as Tier 1 documents evolve through DASH-002..010.
- v2.0 — only if the Human Owner approves a post-MVP direction change (for example, safe direct
  agent integration or a write-back authorization design); requires the full §8 path and a new
  architecture decision.

---

## Appendix A — Conformance Table

Maintained from DASH-001 onward; each row records the document, its current version, its status,
and the master-plan version it conforms to. Initial state: all documents at version 1.0, Draft,
conforming to master plan 1.0. Stage prompt files are listed individually.

| Document | Version | Status | Conforms to |
|---|---|---|---|
| `ARCHITECTURE.md` | 1.0 | Draft | 1.0 |
| `PRODUCT_SPEC.md` | 1.0 | Draft | 1.0 |
| `SECURITY_MODEL.md` | 1.0 | Draft | 1.0 |
| `SOURCE_OF_TRUTH.md` | 1.0 | Draft | 1.0 |
| `DATA_MODEL.md` | 1.0 | Draft | 1.0 |
| `API_SPEC.md` | 1.0 | Draft | 1.0 |
| `UI_SPEC.md` | 1.0 | Draft | 1.0 |
| `MVP_SCOPE.md` | 1.0 | Draft | 1.0 |
| `TEST_STRATEGY.md` | 1.0 | Draft | 1.0 |
| `STAGE_REGISTRY.md` | 1.0 | Draft | 1.0 |
| `stage-prompts/README.md` | 1.0 | Draft | 1.0 |
| `stage-prompts/DASH-001.md` … `DASH-010.md` | 1.0 each | Draft | 1.0 |
| `STAGE_REPORT_TEMPLATE.md` | 1.0 | Draft | 1.0 |
| `DECISIONS.md` | 1.0 | Draft | 1.0 |
| `OPEN_QUESTIONS.md` | 1.0 | Draft | 1.0 |
| `CHANGELOG.md` | 1.0 | Draft | 1.0 |

## Appendix B — Glossary

- **AgentOS** — this repository's self-governance layer: `self-governance.yaml`, the governance
  mirror documents under `docs/`, the deterministic `workflowctl` gates (check/verify, prompt,
  state, agent, commit/push), the handover pair under `handover/`, and the orchestration design
  package under `docs/implementation/orchestration/`.
- **Authoritative source** — a record that governs in case of conflict, per `SOURCE_OF_TRUTH.md`.
- **Control plane** — the `agentos_dashboard/` application; reads the repository, never governs it.
- **DASH-0XX** — one independently authorized implementation stage, delivered as one task in
  `docs/TASK_QUEUE.md`.
- **Draft record** — dashboard-local, non-authoritative data (runs, notes, draft approvals).
- **SSP** — Standard Stage Protocol, the mandatory execution preamble; canonical text lives only
  in `stage-prompts/README.md` and is applied by reference in every stage prompt.
- **Snapshot** — an immutable, staleness-tracked read of the repository built by the dashboard.
- **Stage report** — the mandatory completion evidence at
  `docs/reports/agentos-dashboard/STAGE-XX-completion.md`.
