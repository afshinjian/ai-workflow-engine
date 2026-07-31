# Current Task

Mirror of docs/TASK_QUEUE.md's Current set. Must contain exactly the same task ID(s) at
the same status as the task queue — workflowctl check-task-state fails otherwise.

## No task is currently active

AUTO-010 — Real Non-Interactive Provider Runtime was closed `Current -> Done` on 2026-07-31 by
explicit Human Owner approval, after a required fourteen-point scope, runtime, and safety
verification that passed in full. The approved implementation was committed together with this
closeout in one local commit, which was then pushed. **No PR was opened and no merge was
performed.**

The engine can now really run Claude Code and Codex non-interactively:

    WorkflowService.invoke_provider -> ProviderRuntime.invoke -> Claude CLI / Codex CLI

Both providers are live-validated against the real installed CLIs on all ten acceptance criteria
each — 25 live tests, zero skipped — not by mocks. All three never-ask layers are enforced: the
prompt contract cannot be omitted (the public request has a `task`, never a `prompt`), the process
has no TTY and no controlling terminal and receives exactly one prompt on stdin before EOF, and
every execution terminates in one of four typed statuses. `bypassPermissions` and
`danger-full-access` are absent from the closed enums that configuration is typed to, so neither is
expressible anywhere in the engine.

The Current set is therefore empty. Under self-governance.yaml's maximum_current_tasks: 1
this is a legal state — the maximum is a ceiling, not a quota.

Every remaining task (docs/remaining_tasks.md) is Planned and requires its own fresh
written Human Owner authorization naming it before it may become Current. Closing AUTO-010
authorizes no successor: AUTO-011, the four non-blocking defects AUTO-010 deferred (D-3 through
D-6), the six AUTO-009 deferred (D1-D6), and every later roadmap phase all remain unauthorized.
