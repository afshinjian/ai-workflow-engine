# AUTO-012 — Configurable Approval Policy, Persistence, and Invalidation

| Field | Value |
|---|---|
| **Stage** | AUTO-012 |
| **Title** | Configurable Approval Policy, Persistence, and Invalidation |
| **Role** | Engine implementation session |
| **Branch** | `feature/auto-012-approval-policy` |
| **Predecessor** | AUTO-011 (`COMPLETE`) |
| **Report** | `docs/reports/workflow-automation/AUTO-012-completion-report.md` |

## 1. Mission

Implement a configurable, durable approval subsystem for future workflow gates. The target
architecture for this stage is only:

```text
WorkflowService
        │
        ▼
ApprovalService
        │
        ├── policy resolution
        ├── request persistence
        ├── manual decisions
        ├── timeout decisions
        ├── checksum binding
        └── invalidation
```

AUTO-012 implements no Preparation, Reviewer, or Implementer Mode, and executes neither Claude nor
Codex as part of an approval workflow. It builds only the reusable subsystem future modes consume.

## 2. Governance prerequisite

`HUMAN_AUTHORIZATION_MODEL.md` v1.1 §1 declared a single human gate and §8 made any second
human-approval point a MAJOR change requiring explicit Human Owner sign-off. That sign-off is
recorded as §5a of that document (v2.0) and authorizes the *subsystem only* — never a specific
mode, never a placement, and never AUTO-013.

## 3. Required policy

A strict typed policy with at least `required`, `timeout_seconds`, `timeout_action`, `channels`,
`approvers`, `escalate_to`. Timeout actions: `AUTO_APPROVE`, `PAUSE`, `FAIL`, `CANCEL`, `ESCALATE`.
Channels: `CLI`, `TELEGRAM` — Telegram is a policy value only; no transport or networking.

Resolution order: built-in defaults → project configuration → per-gate configuration → per-run
override. The resolved policy is persisted as an immutable snapshot, and configuration changed
after a request exists never retroactively changes that request.

`AUTO_APPROVE` requires explicit opt-in at the specific gate or per-run override, and must not
become active because a broad inherited default enables it.

## 4. Required records

A strict typed approval request carrying at least `workflow_id`, `gate`, `requested_at`,
`deadline`, `policy_snapshot`, `channels`, `approvers`, `source`, `approver`, `decision`,
`decided_at`, `manual_or_auto`, `timeout_action_applied`, `repo_state_checksum`, `diff_checksum`,
`agent_result_checksum`, `gate_result_checksum`. `agent_result_checksum` binds the canonical
AUTO-011 result; no second result contract is introduced.

Decisions: `APPROVE`, `REJECT`, `REQUEST_CHANGES`, each recording source, approver identity,
timestamp, manual-or-automatic origin, and the exact checksum bindings.

## 5. Deadlines and timeouts

An absolute timezone-aware UTC deadline is persisted. No `sleep`, in-memory timer, running
terminal, background thread, or process-local scheduler state; the deadline survives process and
machine restart. Timeout evaluation is lazy in foreground mode. The daemon is not implemented.

`AUTO_APPROVE` approves automatically and records `manual_or_auto = AUTO` with
`timeout_action_applied = AUTO_APPROVE`. `PAUSE` yields a resumable human-intervention state.
`FAIL` and `CANCEL` are terminal, with no branch or repository cleanup in this stage. `ESCALATE`
records an escalation, grants at most one optional extension, then applies a bounded fallback —
never an unbounded loop.

## 6. Checksum binding and invalidation

Every request binds `repo_state`, `diff`, `agent_result`, and `gate_result` checksums with
deterministic canonical serialization, stable hashing, and no secret leakage. Checksums are
recomputed immediately before consumption; any difference invalidates the approval, blocks the
action, records which checksum changed, and neither silently recreates the request nor
auto-approves it.

## 7. Persistence

Reuse the existing AgentOS persistence and path-confinement discipline. Preferred artifact
`approvals.jsonl`: append-only, fsync'd, duplicate-key rejecting, monotonically ordered, symlink
refusing, per-workflow confined, never overwriting a previous decision or mutating a historical
record, restart-safe on replay. No second persistence framework.

## 8. Boundaries

`WorkflowService` is extended through a narrow approval boundary using the smallest surface
supported by evidence. No workflow lifecycle command, no Preparation/Reviewer/Implementer verb, no
Telegram handler, no provider execution, no Git mutation. No public approval CLI command unless
strictly required to validate the service boundary; AUTO-009's D3 remains deferred unless proven to
block.

The state machine may gain only the minimum approval-related states and transition metadata the
subsystem actually requires; if the subsystem can be implemented without adding workflow states,
that is preferred and must be documented. Existing transition validation, actor validation, resume,
locking, and attempt-journal machinery remain structurally intact; tables and enums are extended,
never refactored.

## 9. Strictly prohibited

Preparation/Reviewer/Implementer Mode; Claude or Codex execution changes; provider-runtime changes;
canonical result changes; Codex direct correction; task scheduling; workflow orchestration; Git
commit or push automation; PR creation; CI polling; merge; branch deletion; governance closeout
automation; daemon; Telegram bot; shell-script retirement; AUTO-013 or successor behaviour.
Git/GitHub skill registration must not be modified. Deferred findings must not be fixed unless they
directly block AUTO-012.

## 10. Newly discovered defect policy

A newly discovered defect that does not directly block AUTO-012 is recorded, classified, added to
the completion report's Deferred Findings, and left unimplemented. No GOV stage is created. A
defect may be fixed only when it directly prevents completion, no scope-preserving workaround
exists, the fix is minimal, and it is documented explicitly as an AUTO-012 blocker.

## 11. Stop condition

After implementation and validation: no implementation/closeout commit, no push, no pull request,
no merge, and no AUTO-013 work. The stage stops at the Human Owner approval gate with a complete
completion report.
