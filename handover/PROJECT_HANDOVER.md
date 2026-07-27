# Project Handover

Narrative context transfer between sessions. This file is checksum-verified by
`handover/PROJECT_CHECKSUM.md`; cross-check its claims against Git and the configured validation
commands.

## Where things stand (2026-07-27)

The released `ai-workflow-engine` 1.0.0 roadmap is complete. In the post-1.0 programs:

- DASH-001 is `Done`; DASH-002..DASH-010 remain `Planned`.
- AUTO-001 is `Done`.
- AUTO-002 is `Done` and registry `COMPLETE`. It delivered the `agentos_workflow/` orchestrator,
  19-state workflow state machine, authorization capture and replay, append-only state/audit
  persistence, repository locking, retry/attempt accounting, configuration, and narrowly scoped
  local resume/evidence observation. It also includes the Human-Owner-approved security and
  correctness remediation recorded in `docs/workflow-automation/DECISIONS.md` DD-15..DD-31.
- AUTO-003..AUTO-007 remain `Planned`/`NOT_STARTED`. None is authorized by AUTO-002 closure.
- GOV-2 remains `Planned`.

There is no active `Current` task. The Human Owner reviewed AUTO-002's implementation and
validation report on 2026-07-27, accepted it as sufficient, explicitly waived another independent
review, and authorized one local Conventional Commit. Push and merge were explicitly prohibited.

## AUTO-002 validation and integrity

Before closure:

- `pytest -q tests agentos_workflow/tests -p no:cacheprovider`: 1,982 passed.
- Focused remediation/evidence suite: 134 passed.
- Ruff, Black, mypy for both `agentos_workflow` and `src`, and `git diff --check`: passed.
- Governance, task-state, and handover checks: passed.
- `workflowctl verify --config self-governance.yaml` reported only `upstream_missing`, the
  pre-existing condition for the local AUTO-002 branch. No upstream was created.

Git inspection showed AUTO-002 began at `163bcee` on
`feature/auto-002-orchestrator-state-machine`. Before the authorized closure commit, no
intervening commit, push, merge, branch switch, upstream change, or stash mutation had occurred.
The two pre-existing recovery stashes remained untouched.

## Future work

Future work does not reopen AUTO-002:

- AUTO-003 may implement deterministic repository/validation Skills and the first infrastructure
  retry accounting when an authorized operation actually needs it.
- Remote/GitHub reconciliation belongs to the later GitHub integration stages.
- Portability beyond the current explicit POSIX `fcntl`/`dir_fd`/`O_NOFOLLOW` boundary is a
  project-backlog improvement.
- GOV-2 may extend lifecycle/governance consistency checking.

Every item above requires its own task authorization. Do not begin AUTO-003 merely because its
predecessor is complete.

## Next session

1. Verify `git status`, recent history, and this handover checksum.
2. Confirm no task is `Current`.
3. Wait for an explicit Human Owner authorization naming the next task.
4. Create or use only that task's governed branch and scope.

Do not push or merge the AUTO-002 commit without a separate Human Owner instruction.
