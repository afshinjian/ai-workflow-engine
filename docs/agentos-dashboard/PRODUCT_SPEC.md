# AgentOS Dashboard — Product Specification

| Field | Value |
|---|---|
| **Title** | AgentOS Dashboard — Product Specification |
| **Purpose** | Master requirement register (DR-###) for every dashboard capability, the human-controlled interaction model, and the deferred-capability register. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Dashboard implementation session · Human Owner (approval and scope) |
| **Dependencies** | `MASTER_PLAN.md` §2; `ARCHITECTURE.md`; `SECURITY_MODEL.md` |
| **Related Documents** | `MVP_SCOPE.md`, `UI_SPEC.md`, `API_SPEC.md` |

## Table of Contents
1. User Definition · 2. Interaction Model · 3. Requirement Register · 4. Deferred Register ·
5. Decision References · 6. Open Questions · 7. Future Revisions

## 1. User Definition

Single user: the local **Human Owner** — one trusted operator on one machine, with full visual
access and no automatic authority beyond what repository governance already grants. There are no
accounts, roles, or remote users in the MVP.

## 2. Interaction Model (normative)

1. Dashboard reads the repository. 2. Dashboard explains the current state. 3. Dashboard
generates an approved stage prompt. 4. Human copies or exports the prompt. 5. Human runs it in
an approved agent tool. 6. Human returns with the execution result. 7. Dashboard records or
verifies the result. 8. Human authorizes the next lifecycle action. Nothing advances
automatically; one stage never starts the next.

## 3. Requirement Register

All DRs are MVP scope unless marked otherwise. Verification: `TEST_STRATEGY.md` TC mapping.

### Overview (DR-010..)
| ID | Requirement |
|---|---|
| DR-010 | Display PROJECT_STATE summary and version, the current task, and task-queue counts per status (Current / Planned / Done) |
| DR-011 | Display blockers, ORCH stage blockers by severity, and last recorded gate results labeled *as-recorded, not re-run* |
| DR-012 | Display working-tree status, current branch, upstream/ahead-behind badge, handover checksum status, last recorded workflow event |
| DR-013 | Healthy-empty states are explicit (e.g., "No Current task — expected between authorized tasks") |

### Workflow board (DR-020..)
| ID | Requirement |
|---|---|
| DR-020 | Queue lanes for the three `docs/TASK_QUEUE.md` statuses (Planned / Current / Done), a per-task workflow-stage strip driven by the engine's seven workflow stages, and a visually distinct program lane for ORCH stages read from `implementation-state.yaml` |
| DR-021 | Cards show ID, title, program, dependencies, status, allowed/blocked next workflow transitions with reasons, evidence-completeness |
| DR-022 | Unknown statuses render in an "unclassified" lane and raise a ConsistencyFinding |
| DR-023 | Board is read-only; no mutation affordance exists |

### Task detail (DR-030..)
| ID | Requirement |
|---|---|
| DR-030 | Full task-record display: scope, allowed/forbidden files where recorded, required validation, acceptance criteria, documentation updates, rollback |
| DR-031 | Lifecycle history parsed from queue prose and, where present, the engine's persisted workflow events, including returns/rejections |
| DR-032 | Git provenance badges: every doc-named commit resolved against Git; unresolvable SHAs flagged |
| DR-033 | Links to related decisions, reports, validation documents; raw Markdown source toggle |

### Stage prompt generator (DR-040..)
| ID | Requirement |
|---|---|
| DR-040 | Only an authorized task+stage is selectable; assigned role displayed |
| DR-041 | Precondition panel with live pass/fail; generation **refused** with itemized unmet preconditions |
| DR-042 | Rendered prompt embeds live repo facts, required validation, report path, explicit stop conditions |
| DR-043 | Preview, copy, export to `.md`; SHA-256 hash recorded; generation and refusal audited |

### Run record (DR-050..)
| ID | Requirement |
|---|---|
| DR-050 | Manual records: stage, prompt hash, tool, start/end, reported result, report path, validation summary, findings, notes, external reference |
| DR-051 | Report-path existence verified; verified fields visually separated from user claims |
| DR-052 | Record schema is forward-compatible with future safe direct integration (same fields, automated population) |

### Review and approval (DR-060..)
| ID | Requirement |
|---|---|
| DR-060 | Visual review of the repository's review layers (implementation review, independent fresh-session review, human approval — `docs/AGENT_PROTOCOL.md`) with findings by severity (Blocker/Major/Minor/Observation) |
| DR-061 | Draft approvals recorded locally only; reconciliation tracked against later authoritative records; divergence raises a finding |
| DR-062 | The dashboard never writes authoritative repository state |

### Evidence and validation (DR-070..)
| ID | Requirement |
|---|---|
| DR-070 | Display focused/regression/full tests, lint/format/typing, pre-commit, changed-file audit, diff check, checksums, provenance, timestamps, commands |
| DR-071 | Tri-state PASS/FAIL/UNKNOWN; repo-verified vs user-entered hard split |

### Repository and Git (DR-080..)
| ID | Requirement |
|---|---|
| DR-080 | Branch, tracking, ahead/behind, tree state, modified/staged/untracked, recent commits, tags, merged/unmerged branches |
| DR-081 | Upstream check mirroring `workflowctl check-git` semantics (default branch `main`, upstream presence and ahead/behind); a violation is a Blocker-severity finding |
| DR-082 | PR references from documentation, labeled unverified in MVP (OD-D7) |
| DR-083 | No destructive Git affordance exists anywhere |

### Governance viewer (DR-090..)
| ID | Requirement |
|---|---|
| DR-090 | Render `README.md`, `self-governance.yaml`, `docs/AGENT_PROTOCOL.md`, `docs/CONTEXT.md`, the governance mirrors (`docs/PROJECT_STATE.md`, `docs/TASK_QUEUE.md`, `docs/current_task.md`, `docs/remaining_tasks.md`), `docs/DECISION_LOG.md`, `docs/GOVERNANCE_AUDIT.md`, and the orchestration package documents (read-only) |
| DR-091 | Full-text search; repo-relative cross-reference resolution |

### Handover viewer (DR-100..)
| ID | Requirement |
|---|---|
| DR-100 | Display the handover pair (`PROJECT_HANDOVER.md`, `PROJECT_CHECKSUM.md`); recompute and compare the checksum manifest exactly as `workflowctl check-handover` defines it; MISSING rows surfaced |
| DR-101 | Stale warning when the handover narrative is older than the governance mirrors it summarizes |
| DR-102 | Manifest refresh presented as a documented manual procedure only (OD-D6) |

### Audit timeline (DR-110..)
| ID | Requirement |
|---|---|
| DR-110 | Merged stream of local audit events and repo-derived lifecycle events with actor, timestamp, hashes, findings, Git evidence |
| DR-111 | Contradictions and reconciliation events appear in the timeline |

### Cross-cutting (DR-120..)
| ID | Requirement |
|---|---|
| DR-120 | Consistency detection across mirrored records; contradictions always surfaced, never auto-resolved |
| DR-121 | Snapshot staleness banner on every page |
| DR-122 | Every parsed value links to its file+line; raw fallback on parse failure |
| DR-123 | English operator UI (developer/PM content) |

## 4. Deferred Register (disposition DEFERRED)

DR-900 direct Claude API execution · DR-901 direct Codex execution · DR-902 terminal access ·
DR-903 automatic state mutation · DR-904 automatic task selection · DR-905 automatic
commit/push/PR/merge/issue-closure · DR-906 handover manifest refresh action (OD-D6) · DR-907
`gh` integration (OD-D7) · DR-908 remote access / multi-user / cloud · DR-909 webhooks,
background workers, unattended operation · DR-910 live websocket updates · DR-911 write-back of
approvals to authoritative documents (requires separate authorization design) · DR-912 invoking
`workflowctl` subprocesses from the dashboard (MVP re-implements read-only checks in-process;
execution of engine commands stays human-run in a terminal).

## 5. Decision References
DD-01, DD-03.

## 6. Open Questions
OD-D6, OD-D7 gate DR-906/DR-907; OD-D9 gates the serving layer for all page-rendering DRs.

## 7. Future Revisions
Deferred DRs are promoted only via `MASTER_PLAN.md` §8 change management.
