# AgentOS Workflow Automation — Audit Model

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Audit Model |
| **Purpose** | State-transition and command-execution audit record schema, append-only guarantee, and its scope. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Documentation & Governance session (AUTO-001) · Human Owner (approval) |
| **Dependencies** | `WORKFLOW_STATES.md`, `SECURITY_MODEL.md` §1 |
| **Related Documents** | `CONFIGURATION_MODEL.md` (`audit_directory`), `SKILL_CONTRACTS.md` §6 |

## Table of Contents
1. What Is Recorded · 2. Command-Execution Record Schema · 3. State-Transition Record Schema ·
4. Append-Only Guarantee · 5. Storage Layout · 6. Decision References · 7. Open Questions ·
8. Future Revisions

## 1. What Is Recorded

Every state transition (`WORKFLOW_STATES.md` §3) and every executed command (every Skill or
Model Provider subprocess invocation) is recorded. Nothing that mutates target-repository or
GitHub state happens without a corresponding audit record.

## 2. Command-Execution Record Schema

Every executed command records:

| Field | Description |
|---|---|
| `normalized_command_identity` | The skill/provider name and a redacted, argument-shape description — never raw secret-bearing argv. |
| `start_time` | ISO-8601 timestamp. |
| `completion_time` | ISO-8601 timestamp. |
| `exit_code` | Process exit code, or `null` if killed by timeout. |
| `timeout_status` | Whether the command hit its configured timeout. |
| `stdout_ref` | Reference (file path under the audit directory) to sanitized stdout — never inlined. |
| `stderr_ref` | Reference to sanitized stderr — never inlined. |

Sanitization (secret redaction) happens before a reference file is written (`SECURITY_MODEL.md`
§1); the audit record itself never contains a raw credential, even in a referenced file.

## 3. State-Transition Record Schema

| Field | Description |
|---|---|
| `workflow_id` | Identifier for this workflow instance. |
| `target_repository` | Identity + path bound at authorization. |
| `stage_id` | Stage identifier. |
| `from_state` / `to_state` | The transition (`WORKFLOW_STATES.md` §2). |
| `timestamp` | ISO-8601 timestamp. |
| `actor` | `human` (authorization/cancellation only), `orchestrator`, or `agent:<Name>`. |
| `gate_evidence_ref` | Reference to the machine-gate evidence that justified the transition, where applicable (`MACHINE_GATES.md`). |

## 4. Append-Only Guarantee

Audit records are append-only **from the workflow engine's perspective**: the engine itself
never edits or deletes a previously written record. This does not claim protection against a
privileged external actor modifying the audit store directly — that is outside this program's
threat model (local, single-user MVP). Every state transition (§3) and every command execution
(§2) is a new, never-rewritten entry.

## 5. Storage Layout

Audit records are stored under the target repository's configured `audit_directory`
(`CONFIGURATION_MODEL.md`), local to the machine running the workflow engine. Exact file format
(e.g. one JSONL file per workflow, or per-day) is AUTO-002 implementation detail; the schema in
§2-3 is binding regardless of file layout.

## 6. Decision References
DD-04.

## 7. Open Questions
None blocking AUTO-001; storage file format is AUTO-002 scope.

## 8. Future Revisions
Adding a new record field is additive; removing a field from either schema is a MAJOR change
requiring explicit Human Owner review, since audit completeness is a safety property.
