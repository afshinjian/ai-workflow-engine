# AgentOS Dashboard — Data Model

| Field | Value |
|---|---|
| **Title** | AgentOS Dashboard — Data Model |
| **Purpose** | Canonical entity catalogue (EN-##), stored-vs-derived status, mutability and audit rules, and the local database schema. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Dashboard implementation session · Human Owner via independent review (approval) |
| **Dependencies** | `SOURCE_OF_TRUTH.md`; `ARCHITECTURE.md` |
| **Related Documents** | `API_SPEC.md`, `SECURITY_MODEL.md` SC-22..SC-24 |

## Table of Contents
1. Modeling Rules · 2. Entity Catalogue · 3. Local Database Schema · 4. Append-Only
Enforcement · 5. Future Entities · 6. Decision References · 7. Open Questions · 8. Future Revisions

## 1. Modeling Rules

Prefer derived data over duplicate persistence. Stored entities exist only where restart
survival is required (runs, prompts, drafts, notes, audit, finding history). All stored
entities carry `created_at` and audit linkage. Mutability: **A** append-only, **I** immutable,
**D** derived (recomputed per snapshot).

## 2. Entity Catalogue

| ID | Entity | Purpose / key fields | Source of truth | Stored? | Mut. | MVP |
|---|---|---|---|---|---|---|
| EN-01 | Project | name, repo root, authority-chain doc list | repo (`self-governance.yaml`) | D | D | ✔ |
| EN-02 | RepositorySnapshot | fingerprint, generated_at, HEAD, mtimes, confidence | repo | D (memory cache) | D | ✔ |
| EN-03 | RepositoryFile | path, size, mtime, hash, truncated flag | filesystem | D | D | ✔ |
| EN-04 | UpstreamStatus | branch, upstream presence, ahead/behind, tree state | Git | D | D | ✔ |
| EN-05 | Task | id, title, program, status (Current/Planned/Done), deps, file+line | `docs/TASK_QUEUE.md` | D | D | ✔ |
| EN-06 | TaskRecordDetail | scope, validation, acceptance criteria, rollback (as recorded in queue prose) | `docs/TASK_QUEUE.md` | D | D | ✔ |
| EN-07 | WorkflowState | the engine's seven workflow stages and fixed transition table | coded constants mirrored from the engine's workflow model, cross-checked | D | D | ✔ |
| EN-08 | StateTransition | from, to, kind, authority, reason | engine transition table + queue prose | D | D | ✔ |
| EN-09 | AgentRole | name, purpose, allowed/forbidden, escalation | `docs/AGENT_PROTOCOL.md` | D | D | ✔ |
| EN-10 | StageDefinition | DASH id, objective, role, preconditions, report path | `STAGE_REGISTRY.md` | D | D | ✔ |
| EN-11 | StageRun | uuid, stage, prompt_hash, tool, times, result, report path, verified flags | **dashboard.db** | S | A | ✔ |
| EN-12 | PromptTemplate | stage id, version, template, placeholders | `agentos_dashboard/prompt_templates/` | D | I/version | ✔ |
| EN-13 | GeneratedPrompt | uuid, template version, hash, precondition results, export path | **dashboard.db** (hash mandatory) | S | I | ✔ |
| EN-14 | Approval | uuid, layer, verdict, target hash/commit, reconciled | draft: dashboard.db; authoritative: repo docs | S (draft only) | A | ✔ |
| EN-15 | Finding | severity, text, disposition | repo reports (verified) or dashboard.db (draft), labeled | both | A | ✔ |
| EN-16 | ValidationRun | command, result, counts, timestamp, origin | reports / user entry | S (user-entered) | A | ✔ |
| EN-17 | TestResult | suite, counts, source ref | reports | D/S | A | ✔ |
| EN-18 | FileChange | path, type, in-scope | Git `diff --stat` | D | D | ✔ |
| EN-19 | GitBranch | name, tracking, ahead/behind, merged | Git | D | D | ✔ |
| EN-20 | GitCommit | sha, subject, author, date, role | Git | D | D | ✔ |
| EN-21 | PullRequest | number, URL, doc source, verified=false (MVP) | GitHub (deferred) / docs | D | D | ✔ refs |
| EN-22 | Decision | date/heading, context, decision | `docs/DECISION_LOG.md` + program `DECISIONS.md` (labeled) | D | D | ✔ |
| EN-23 | Blocker | text, level, source | `docs/PROJECT_STATE.md` Blockers section | D | D | ✔ |
| EN-24 | OrchStage | ORCH id, status, prerequisites, blockers, evidence paths | `docs/implementation/orchestration/implementation-state.yaml` | D | D | ✔ |
| EN-25 | HandoverArtifact | path, checksum rows, verify result | `handover/` pair | D | D | ✔ |
| EN-26 | AuditEvent | uuid, ts, actor, kind, payload hash refs | **dashboard.db + JSONL** | S | A | ✔ |
| EN-27 | ExecutionLock | pidfile, acquired_at | local FS | S | I | ✔ |
| EN-28 | ConsistencyFinding | rule id, severity, sources (file+line), first/last seen, reconciled | derived; seen-history in dashboard.db | D + S | A | ✔ |
| EN-29 | UserNote | uuid, target ref, text (escaped on render) | **dashboard.db** | S | A | ✔ |

## 3. Local Database Schema

`data/agentos_dashboard/dashboard.db` (gitignored; OD-D5 — note `data/` does not exist in this
repository yet; DASH-008 creates it and verifies/adds the narrowest `.gitignore` rule). Stdlib
`sqlite3`; foreign keys ON; `PRAGMA user_version = 1`; schema created by code, no Alembic.
Tables: `stage_runs`, `generated_prompts`, `approvals`, `findings`, `validation_runs`,
`user_notes`, `consistency_history`, `audit_events` (+ JSONL mirror under
`data/agentos_dashboard/logs/`).

## 4. Append-Only Enforcement

No UPDATE or DELETE statement targeting `audit_events` exists anywhere in the codebase
(verified by source-scan test and behavioral test, `TEST_STRATEGY.md`). Idempotent POSTs use
client UUIDs; replays return the original row (SC-23).

## 5. Future Entities

AgentSession, RemoteRun, UserAccount — deferred with DR-900-series capabilities.

## 6. Decision References
DD-01, DD-03; OD-D5 disposition.

## 7. Open Questions
None specific; schema evolution beyond `user_version 1` follows `MASTER_PLAN.md` §8.

## 8. Future Revisions
`user_version` increments require a documented in-code migration path and a CHANGELOG entry.
