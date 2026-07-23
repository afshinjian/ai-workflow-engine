# AUTO-005 — PMO, Implementation, QA, Git, Merge, and Closeout Agents

| Field | Value |
|---|---|
| **Stage** | AUTO-005 · Role: Engine implementation session |
| **Branch** | `feature/auto-005-agents` |
| **Commit message** | `feat(workflow): add PMO, implementation, QA, git, merge, and closeout agents (AUTO-005)` |
| **Report** | `docs/reports/workflow-automation/AUTO-005-completion-report.md` |
| **Status/Version** | Draft · 1.0 |

Apply the Standard Stage Protocol in `README.md` in full.

## Canonical Prompt

You are the **Engine implementation session** executing **AUTO-005 — PMO, implementation, QA,
Git, merge, and closeout agents**. Preconditions: AUTO-002, AUTO-003, and AUTO-004 `COMPLETE`;
recorded authorization "I authorize AUTO-005"; branch `feature/auto-005-agents` from clean
`main`.

**Allowed**: create `agentos_workflow/agents/{__init__.py, pmo.py, implementation.py, qa.py,
git.py, merge.py, closeout.py}`, `agentos_workflow/tests/**`, plus SSP-required
documentation/report updates.

**Build**: all six Agents exactly per `../AGENT_CONTRACTS.md` §2-7 — each restricted to its
listed Skills/Providers, each returning a structured result for the Orchestrator to act on, none
deciding its own resulting state transition. Wire the Orchestrator's `VALIDATING` step (§3 of
`../MACHINE_GATES.md`) as an Orchestrator-owned sequence of Validation Skills, not a seventh
Agent, per `../AGENT_CONTRACTS.md` §8. Implement the repair loop
(`../FAILURE_RECOVERY.md` §1-2): `ImplementationAgent` repair invocation receiving the latest
QA/validation-failure report; full re-run of deterministic validation and QA after every
attempt; hard stop at 3 attempts.

**Tests**: each Agent restricted-skill-set enforcement (an Agent cannot invoke a Skill/Provider
outside its contract); full repair-loop test with `MockProvider` failing twice then passing,
asserting exactly 3 total implementation attempts max and a full re-validation after each;
repair-loop exhaustion test asserting `FAILED` with a failure report; `MergeAgent` refuses to
proceed when `verify_head_sha` returns a mismatch; `CloseoutAgent` refuses branch deletion
without an independently confirmed merge.

**Out of scope**: real GitHub PR/merge integration — AUTO-006 provides the underlying
GitHub-facing Skills these Agents call; this stage may use fixtures/mocks for those Skills if
AUTO-006 has not yet landed, clearly marked as provisional and revisited when AUTO-006 lands.

Write the report, recommend the commit message above, then STOP per SSP.

## Stage-Specific Notes

Reference: `../AGENT_CONTRACTS.md` (all sections), `../FAILURE_RECOVERY.md`,
`../MACHINE_GATES.md` §2-4.
