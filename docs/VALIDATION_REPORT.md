# Governance Validation Report

Evidence that the self-governance layer added for task `GOV-1` actually works, produced by
running the real tool against this real repository — not by assertion. Every command output
below is what actually ran during this task, not a hypothetical example.

## Files created

Documentation and configuration only — no source code under `src/` was touched by this task.

| File | Purpose |
|---|---|
| `docs/GOVERNANCE_AUDIT.md` | Phase 1 audit; records the Option A vs. Option B decision. |
| `docs/PROJECT_STATE.md` | `governance.project_state` mirror + `version` fact source. |
| `docs/TASK_QUEUE.md` | `governance.task_queue` — authoritative task states. |
| `docs/current_task.md` | `governance.current_task` mirror. |
| `docs/remaining_tasks.md` | `governance.remaining_tasks` mirror. |
| `docs/CONTEXT.md` | `governance.context`; fresh-session recovery read-order. |
| `docs/DECISION_LOG.md` | Architectural decisions + rejected alternatives + reasons. |
| `docs/CHANGELOG.md` | Keep-a-Changelog-style history, grounded in real commit dates. |
| `docs/AGENT_PROTOCOL.md` | Claude/Codex/OpenCode/Human role rules; review discipline. |
| `handover/PROJECT_HANDOVER.md` | Narrative handover; checksum-verified deliverable. |
| `handover/PROJECT_CHECKSUM.md` | `governance.handover.manifest`. |
| `self-governance.yaml` | `EngineConfig` pointing `workflowctl` at this repository. |

## Commands tested

All run against `self-governance.yaml`, i.e. against `ai-workflow-engine`'s own working tree.

### `verify` — clean state

```
$ workflowctl verify --config self-governance.yaml
                    Verification: ai-workflow-engine
┏━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Check      ┃ Status ┃ Summary                                         ┃
┡━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ git        │ PASS   │ Git state satisfies configured invariants       │
│ task-state │ PASS   │ Detected 1 Current, 2 Done, and 2 Planned tasks │
│ governance │ PASS   │ Governance mirrors are consistent               │
│ handover   │ PASS   │ Verified 1 manifest record(s) from working-tree │
└────────────┴────────┴─────────────────────────────────────────────────┘
Verdict: PASS
```
Exit code: 0.

### `prompt governance-closeout` — real prompt for this repository

```
$ workflowctl prompt governance-closeout --config self-governance.yaml --task-id GOV-1 --no-store
Prompt ID: 89fae33b826e8b17
Stage: governance-closeout
Stored: no
...
## Role
Act as the read-only governance closeout assessor for the requested task.
...
```
Exit code: 0. Full evidence (git status, task snapshot, all four check results) rendered into
the prompt body, generated from this repository's actual current state at the moment it ran.

### Full local test suite (unrelated to this task's file changes, run as a sanity check)

```
$ pytest -q
448 passed
```

## Failure scenarios tested

Each was a real, temporary mutation with a backup taken first and a `diff` confirming exact
restoration afterward — not a hypothetical description.

**1. Task-state mirror desync.** Changed `docs/current_task.md`'s `GOV-1` status from `Current`
to `Done` while `docs/TASK_QUEUE.md` still said `Current`:
```
FAIL task-state: Detected 1 Current, 2 Done, and 2 Planned tasks
  - current_task_mismatch (docs/current_task.md): Task queue Current set ['GOV-1'] differs
    from current-task mirror []
  - task_state_mismatch (docs/current_task.md): GOV-1 is Done here but Current in task queue
```
Exit code 1. Restored; re-ran `check-task-state` → `PASS`, exit 0.

**2. Governance fact drift.** Changed `docs/PROJECT_STATE.md`'s version line to `9.9.9` while
`pyproject.toml` still said `0.1.0`:
```
FAIL governance: Found 1 governance inconsistency(s)
  - governance_fact_missing: Required fact 'version' is missing
```
Exit code 1. (Reported as *missing* rather than *mismatched* — the configured extraction pattern
only matches `0.x.y`-shaped versions, inherited from `examples/amozesh_konkur.yaml`; `9.9.9`
simply fails to extract at all. Still a genuine, correctly-caught inconsistency; noted here
rather than mischaracterized as a mismatch I didn't actually observe.) Restored; re-ran
`check-governance` → `PASS`, exit 0.

**3. Handover tamper.** Appended a line to `handover/PROJECT_HANDOVER.md` without updating the
manifest:
```
FAIL handover: Verified 1 manifest record(s) from working-tree
  - size_mismatch (handover/PROJECT_HANDOVER.md): Expected 3112 bytes, got 3121
  - checksum_mismatch (handover/PROJECT_HANDOVER.md): SHA-256 digest does not match
```
Exit code 1. Restored; re-ran `check-handover` → `PASS`, exit 0.

## Fresh-session recovery — the actual scenario

**A completely new AI session opens this repository with no memory of any prior conversation.
Here is exactly how it recovers context from repository files alone**, per the read order
`docs/CONTEXT.md` specifies:

1. Read `docs/AGENT_PROTOCOL.md` → learns: only Claude Code currently operates here; nothing
   destructive happens without explicit human approval; every review round after the first uses
   an independent reviewer with no memory of prior fixes.
2. Read `docs/PROJECT_STATE.md` → learns: Milestone 1 shipped 2026-07-16; Milestone 2 is
   approved but uncommitted; this self-governance task is in progress; no blockers.
3. Read `docs/current_task.md` → learns the exact active task (`GOV-1`), its objective, scope,
   and acceptance criteria — no ambiguity about what "the current task" means.
4. Read `docs/TASK_QUEUE.md` → learns the full backlog and dependency order (`M-3` needs `GOV-1`
   and `M-2` closed first; `M-4` needs `M-3`).
5. Read `handover/PROJECT_HANDOVER.md` → learns the narrative detail of what changed most
   recently and why, with its integrity checksum-verified against tampering.
6. Runs `git status`, `git log --oneline -10`, and the test suite → confirms the documents'
   claims against actual repository state, per `docs/CONTEXT.md`'s explicit instruction to trust
   observation over documentation if the two ever disagree.
7. Optionally runs `workflowctl verify --config self-governance.yaml` → gets the same four-check
   PASS/FAIL table shown above, mechanically, without needing to re-derive it by hand.

No step in that sequence depends on this conversation, or any other prior conversation, having
happened.

## Remaining limitations

- The `version` governance fact's extraction pattern only matches versions shaped `0.x.y` (see
  failure scenario 2). It will need updating — in both `self-governance.yaml` and
  `examples/amozesh_konkur.yaml`, since both inherited the same pattern — whenever this project
  reaches `1.0.0`.
- `docs/TASK_QUEUE.md` currently models workstreams at milestone granularity (`M-1`..`M-4`,
  `GOV-1`), not fine-grained per-PR tasks. That granularity was sufficient to validate the
  mechanism; a finer breakdown can be introduced later without any schema change.
- No CI runs `workflowctl verify --config self-governance.yaml` automatically — there is no CI
  configuration in this repository at all yet (confirmed in `docs/GOVERNANCE_AUDIT.md`). Today,
  self-verification is a manual step a session should run, not an enforced gate.
- Per the Option A decision, this task deliberately did **not** implement Phase 3's 7-state task
  lifecycle, Phase 4's live multi-agent execution, Phase 6's new CLI verbs, or Phase 7's
  automated push gate. Those remain scoped to Milestones 3 and 4, unbuilt, by design — see
  `docs/GOVERNANCE_AUDIT.md` §3 for the reasoning and `docs/TASK_QUEUE.md` for their current
  `Planned` status.
- This report, and every governance document it references, is itself uncommitted. Nothing has
  been staged, committed, or pushed — that decision is left to the human, per
  `docs/AGENT_PROTOCOL.md`.
