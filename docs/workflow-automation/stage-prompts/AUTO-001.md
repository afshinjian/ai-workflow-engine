# AUTO-001 — Architecture and Governance Contracts

| Field | Value |
|---|---|
| **Stage** | AUTO-001 · Role: Documentation & Governance session |
| **Branch** | `governance/auto-001-workflow-automation-planning` |
| **Commit message** | `docs(governance): define AgentOS workflow automation architecture (AUTO-001)` |
| **Report** | `docs/reports/workflow-automation/AUTO-001-completion-report.md` |
| **Status/Version** | Draft · 1.0 |

Apply the Standard Stage Protocol in `README.md` in full.

## Canonical Prompt

You are the **Documentation & Governance session** executing **AUTO-001 — Architecture and
governance contracts**. Preconditions: repository is `ai-workflow-engine`; branch
`governance/auto-001-workflow-automation-planning` from clean `main`; no other `Current` task in
`docs/TASK_QUEUE.md` (close out any stale `Current` task first, recording the closeout decision,
if this precondition otherwise fails); recorded authorization "I authorize AUTO-001."

**Allowed (create)**: `docs/workflow-automation/{README.md, ARCHITECTURE.md,
WORKFLOW_STATES.md, AGENT_CONTRACTS.md, SKILL_CONTRACTS.md, MODEL_PROVIDER_CONTRACTS.md,
HUMAN_AUTHORIZATION_MODEL.md, MACHINE_GATES.md, SECURITY_MODEL.md, FAILURE_RECOVERY.md,
AUDIT_MODEL.md, CONFIGURATION_MODEL.md, TARGET_REPOSITORY_MODEL.md, CLI_SPEC.md, MVP_SCOPE.md,
STAGE_REGISTRY.md, TEST_STRATEGY.md, DECISIONS.md, OPEN_QUESTIONS.md, CHANGELOG.md,
STAGE_REPORT_TEMPLATE.md}`, `docs/workflow-automation/stage-prompts/{README.md,
AUTO-001.md … AUTO-007.md}`, `docs/reports/workflow-automation/AUTO-001-completion-report.md`.
**Allowed (modify, only as required by repository governance)**: `docs/TASK_QUEUE.md`,
`docs/current_task.md`, `docs/remaining_tasks.md`, `docs/PROJECT_STATE.md` (prose only —
`Current Version:` fact line byte-identical), `docs/DECISION_LOG.md`, `docs/CHANGELOG.md`.

**Forbidden**: everything else — no code, no `src/`, `tests/`, `scripts/`, `examples/`; no
dependency or configuration change; no `handover/**` change; no
`docs/implementation/orchestration/**` or `docs/agentos-dashboard/**` change beyond what
governance requires (e.g. flipping a stale `Current` task to `Done`); no successor promotion
beyond enrollment-as-`Planned`.

**Content requirements**: define the required architectural model (Human → CLI → Orchestrator
→ State Store + Lock → Agents → Skills/Providers → Target Repository/Git/GitHub/Claude/Codex);
the six Agents (`PMOAgent`, `ImplementationAgent`, `QAAgent`, `GitAgent`, `MergeAgent`,
`CloseoutAgent`); the three provider abstractions (`ClaudeCLIProvider`, `CodexCLIProvider`,
`MockProvider`); all five skill groups; all 19 runtime workflow states with exact allowed
transitions, forbidden transitions, retry behavior, interruption recovery, and idempotency;
the single human gate (`CREATED → AUTHORIZED`) and its authorization binding; every machine
gate; the security, failure-recovery, audit, configuration, and target-repository models; the
CLI surface; MVP scope; the AUTO-001..007 stage registry; the test strategy; decisions and open
questions.

**Validation**: documentation gates only — every required document exists; every
AUTO-001..AUTO-007 stage prompt exists; internal links/references resolve; state, agent, skill,
and CLI terminology consistent across all documents; the only human gate documented anywhere is
stage authorization; automatic-merge safety rules consistently documented; `main` documented
only as `ai-workflow-engine`'s own baseline, never a global default; `git diff --check`; a
changed-file inventory and validation summary produced; no runtime implementation added.

**Acceptance criteria**: (1) all required documents exist and are mutually consistent; (2) all
seven stage prompts exist; (3) state/agent/skill/CLI terminology consistent; (4) only human gate
is stage authorization; (5) merge-safety rules consistently documented; (6) `main` never treated
as a global default; (7) zero runtime implementation; (8) validation commands run and recorded.

Write the report, recommend the commit message above, then STOP per SSP.

## Stage-Specific Notes

Preconditions: verify no conflicting `Current` task exists in `docs/TASK_QUEUE.md` before
writing any AUTO document — if one exists (as it did here: DASH-001), resolve it explicitly
(with Human Owner direction) and record the resolution in `docs/DECISION_LOG.md` and this
program's own `../DECISIONS.md` before proceeding. Do not commit, push, open a pull request, merge,
or delete any branch as part of this stage.
