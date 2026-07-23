# AUTO-002 — Orchestrator, State Machine, Locking, and Persistence

| Field | Value |
|---|---|
| **Stage** | AUTO-002 · Role: Engine implementation session |
| **Branch** | `feature/auto-002-orchestrator-state-machine` |
| **Commit message** | `feat(workflow): add orchestrator, state machine, locking, and persistence (AUTO-002)` |
| **Report** | `docs/reports/workflow-automation/AUTO-002-completion-report.md` |
| **Status/Version** | Draft · 1.0 |

Apply the Standard Stage Protocol in `README.md` in full.

## Canonical Prompt

You are the **Engine implementation session** executing **AUTO-002 — Orchestrator, state
machine, locking, and persistence**. Preconditions: AUTO-001 `COMPLETE`; recorded authorization
"I authorize AUTO-002"; branch `feature/auto-002-orchestrator-state-machine` from clean `main`.

**Allowed**: create `agentos_workflow/{__init__.py, orchestrator/__init__.py,
orchestrator/engine.py, orchestrator/state_store.py, orchestrator/lock.py, config/__init__.py,
config/schema.py, config/loader.py}`, `agentos_workflow/tests/**`, plus SSP-required
documentation/report updates. No new third-party dependency without a new `../OPEN_QUESTIONS.md`
entry and Human Owner disposition.

**Build**: (a) the 19-state machine from `../WORKFLOW_STATES.md` §2-4 with exact allowed
transitions enforced and every forbidden transition rejected; (b) the persistent state store
(`../AUDIT_MODEL.md` §3) with append-only transition and command-execution records; (c) the
per-target-repository lock (`../OPEN_QUESTIONS.md` OD-3 resolved here); (d) the authorization
capture/validation path (`../HUMAN_AUTHORIZATION_MODEL.md`) — the human gate only, no
Skills/Agents/Providers wired yet; (e) the configuration loader/schema
(`../CONFIGURATION_MODEL.md`).

**Tests**: every allowed/forbidden transition from `../WORKFLOW_STATES.md` §3-4; resume after
simulated interruption re-verifies preconditions and detects authorization drift
(`../WORKFLOW_STATES.md` §6); lock prevents a second concurrent workflow against the same
target; idempotent re-entry of every implemented transition (`../WORKFLOW_STATES.md` §7);
engine-suite collection unchanged.

**Out of scope**: Agents, Skills, Model Providers, Git/GitHub integration — those are
AUTO-003..006. This stage's state machine transitions past `PRECONDITIONS_CHECKED` are tested
with stub/no-op step functions only.

Write the report, recommend the commit message above, then STOP per SSP.

## Stage-Specific Notes

Reference contracts: `../ARCHITECTURE.md` §4 (package layout), `../HUMAN_AUTHORIZATION_MODEL.md`
(binding fields), `../AUDIT_MODEL.md` (record schemas). Resolves `../OPEN_QUESTIONS.md` OD-3 and
OD-5 as implementation decisions, recorded in `../DECISIONS.md`.
