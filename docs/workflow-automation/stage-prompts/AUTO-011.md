# AUTO-011 — Unified Provider and Agent Result Contract

| Field | Value |
|---|---|
| **Stage** | AUTO-011 |
| **Title** | Unified Provider and Agent Result Contract |
| **Role** | Engine implementation session |
| **Branch** | `feature/auto-011-agent-result-contract` |
| **Predecessor** | AUTO-010 (`COMPLETE`) |
| **Report** | `docs/reports/workflow-automation/AUTO-011-completion-report.md` |

## 1. Mission

Create one canonical typed result contract for provider and agent execution. The target
architecture for this stage is only:

```text
WorkflowService
        │
        ▼
Provider Runtime
        │
        ▼
Canonical AgentRunResult
```

AUTO-011 standardizes execution *results*. It implements no workflow mode and no workflow
lifecycle. Nothing in this stage decides *when* an execution happens or what its outcome means for
a workflow — those belong to the Orchestrator and to stages after this one.

## 2. Primary goal

Introduce one canonical result model, `AgentRunResult`, which becomes the canonical result contract
for future Claude execution, Codex execution, internal agents, Preparation Mode, Reviewer Mode, and
Implementer Mode. AUTO-011 must not implement any of those future modes.

## 3. Required canonical fields

The canonical result must represent at least: `workflow_id`, `mode`, `agent`, `provider`, `status`,
`summary`, `assumptions`, `blocking_issues`, `changed_files`, `artifacts`, `tests_run`,
`started_at`, `completed_at`, `duration`, `exit_code`, `failure`, `final_verdict`,
`recommended_next_state`.

Repository terminology and existing models are used wherever they exist. No field is added merely
because it may be useful later: every field must have a concrete execution-contract purpose, stated
field by field in the completion report.

## 4. Status contract

Exactly four terminal execution statuses, reusing AUTO-010's `ProviderRunStatus` rather than
declaring a second enum with the same members:

```text
COMPLETED
COMPLETED_WITH_ASSUMPTIONS
BLOCKED
FAILED
```

Enforced invariants:

* `COMPLETED_WITH_ASSUMPTIONS` requires at least one assumption;
* `BLOCKED` requires at least one concrete blocking issue;
* `FAILED` requires a typed failure;
* `COMPLETED` must carry no contradictory blocking or failure data;
* unknown statuses are rejected;
* agents cannot invent workflow transitions through the result.

## 5. Authority rule

`recommended_next_state` is advisory only. It must never mutate workflow state, authorize a
transition, bypass the Orchestrator, or substitute for deterministic validation. Tests must prove
that no state transition depends only on this field.

## 6. Strict scope

AUTO-011 may implement only:

1. one canonical `AgentRunResult` model;
2. typed result validation and its status invariants;
3. deterministic, strict serialization and round-trip parsing;
4. adapters mapping existing provider results into the canonical model;
5. artifact references and failure preservation;
6. tests for all of the above.

## 7. Compatibility

AUTO-010's Provider Runtime must continue to work unchanged. Adapters are introduced instead of
breaking existing interfaces. The provider process runner is not rewritten. Real Claude and Codex
invocation behaviour is unchanged, and specifically none of the following is altered: provider
argv; permission modes; sandbox modes; environment allowlists; timeout behaviour; output limits;
process-group cleanup; session layout; live CLI tests.

No legacy result model is deleted in this stage. Legacy `AgentReport` under `src/ai_workflow_engine`
remains unchanged.

## 8. Strictly prohibited

Preparation Mode; Reviewer Mode; Implementer Mode; workflow authorization; workflow approval;
approval timeout; task scheduling; workflow start; workflow resume; workflow cancellation;
Claude–Codex coordination; Codex direct correction; Git commit automation; Git push automation; PR
creation; CI polling; merge; branch cleanup; Python governance closeout; daemon; Telegram; AUTO-012
or any successor behaviour.

Workflow state transitions must not be modified. Git/GitHub skill registration must not be
modified. Shell scripts must not be retired or modified. Existing `workflowctl auto
status|list|audit|report` behaviour and output are unchanged, and no new public CLI command is
added unless a direct blocker is proven.

## 9. Newly discovered defect policy

A newly discovered defect that does not directly block AUTO-011 is recorded, classified, added to
the completion report's Deferred Findings section, and left unimplemented. No GOV stage is created
for it. A defect may be fixed only when it directly prevents completion of AUTO-011, no
scope-preserving workaround exists, the fix is minimal, and it is documented explicitly as an
AUTO-011 blocker.

## 10. Stop condition

After implementation and validation: no implementation/closeout commit, no push, no pull request,
no merge, and no AUTO-012 work. The stage stops at the Human Owner approval gate with a complete
completion report.
