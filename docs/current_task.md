# Current Task

Mirror of `docs/TASK_QUEUE.md`'s `Current` set. Must contain exactly the same task ID(s) at the
same status as the task queue — `workflowctl check-task-state` fails otherwise.

## AUTO-005 — PMO, implementation, QA, Git, merge, and closeout agents

Status: Current

Authorized by the Human Owner on 2026-07-28, in the same written decision that approved AUTO-004,
closed it `Current → Done` / `IN_PROGRESS → COMPLETE`, and authorized its publication. The
AUTO-005 half of that decision was explicitly conditioned on the AUTO-004 integration succeeding
first — "after AUTO-004 is successfully merged and all closure checks pass, I authorize AUTO-005".
It did: `main` carries the merge (`4721f9a`), local and remote `main` agree, and the four
configured checks (`git`, `task-state`, `governance`, `handover`) all PASS. Registry state
`NOT_STARTED → AUTHORIZED → IN_PROGRESS` (`docs/workflow-automation/STAGE_REGISTRY.md` §4, §5).

Branch `feature/auto-005-agents`, created from that clean, synchronized `main`. AUTO-005 is the
single `Current` task under `maximum_current_tasks: 1`.

Scope — create only: `agentos_workflow/agents/{__init__.py, pmo.py, implementation.py, qa.py,
git.py, merge.py, closeout.py}`, `agentos_workflow/tests/**`, plus the SSP-required
documentation/report/governance/handoff files. `src/`, `tests/`, `scripts/`, `examples/`,
`pyproject.toml`, and `self-governance.yaml` are untouched; the engine's default `pytest`
collection must be provably unchanged. No dependencies added.

Objective: implement the six Agents of `docs/workflow-automation/AGENT_CONTRACTS.md` §2-7, each
restricted to the Skills and Provider roles its own contract lists, each returning a structured
result for the Orchestrator to act on, and none deciding its own resulting workflow-state
transition (§1). The `VALIDATING` step (`MACHINE_GATES.md` §3) is wired as an Orchestrator-owned
sequence of Validation Skills rather than a seventh Agent (§8), as is the bounded repair loop of
`FAILURE_RECOVERY.md` §1-2: repair invocation receiving the latest QA/validation failure report,
a full re-run of deterministic validation and QA after every attempt, and a hard stop at the
configured attempt limit.

Out of scope: real GitHub pull-request and merge integration (AUTO-006), which delivers the
GitHub-facing Skills `GitAgent` and `MergeAgent` call. Commit, push, merge, and beginning AUTO-006
are explicitly prohibited; the stage stops for Human Owner approval.
