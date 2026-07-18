# Milestone 3 Validation Report

Evidence that Milestone 3 (non-interactive agent execution) works, produced by running the real
tool. Milestone 3 was built across tasks T-301..T-306, each passing an independent fresh review
(plan review took two rounds; every implementation review is recorded in `docs/CHANGELOG.md` and
`docs/DECISION_LOG.md`). Normative specification: `docs/milestone-3-plan.md`.

## What Milestone 3 delivered

- **Persisted workflow state machine** (`ai_workflow_engine.workflow`): an append-only,
  hash-chained per-task event log with a fixed transition table, verdict recording, next-stage
  computation, and collision-free tamper-evident storage. CLI: `workflowctl state show|next|record`.
- **Agent configuration + report contract** (`EngineConfig.agents`, `ai_workflow_engine.agents.models`):
  per-agent executable/mode/timeout/stages with mode-stage compatibility (`push` forbidden for
  any agent), and a strict `AgentReport` schema.
- **Snapshot-sandbox runner** (`ai_workflow_engine.agents.sandbox` + `.runner`): clones the repo
  at the prompt's recorded HEAD, runs the agent with a clean-tree precondition, a hard timeout
  (process-group kill), a scrubbed environment, and a before/after fingerprint that fails the run
  if the target repository changed at all.
- **Independent claim verification + tamper-evident artifacts** (`.verification`, `.artifacts`):
  every agent claim is checked against sandbox reality (claim equality, scope containment,
  protected paths, verification-command exit codes); results are stored as content-addressed,
  digest-verified `AgentRunRecord`s. CLI: `workflowctl agent run`.
- **Evidence binding**: `workflowctl state record --agent-run <id>` refuses to record a verdict
  unless a verified run artifact backs it.

## Suite and standing checks (run at version 0.2.0)

```
$ pytest -q                     -> 623 passed
$ FORCE_COLOR=3 pytest -q       -> 623 passed
$ ruff check .                  -> All checks passed
$ black --check .               -> 59 files unchanged
$ mypy src                      -> Success: no issues in 40 source files
$ workflowctl verify --config self-governance.yaml  -> Verdict: PASS (git, task-state, governance, handover)
```

## Full-cycle demonstration (real output)

An honest read-only agent, driven through the whole loop against a throwaway target repository
(verification commands stubbed to a trivial always-pass command so the demo doesn't run a full
sandbox pytest; every other step is the real code path):

```
1. Rendered + stored plan-review prompt. prompt_id = 50704998b35e0fc3
2. Ran stub agent 'reviewer' in sandbox. ok = True  reported verdict = APPROVED
3. Independent verification: PASS — changed-set claim matched, scope clean, commands passed
4. Stored tamper-evident artifact. run_id = 68a7c89712f59ffc
   Reloaded + re-verified artifact: run_id matches = True
5. Recorded state verdict citing the run. sequence = 1  next stage = implementation

Demonstration complete: prompt -> agent run -> independent verification -> artifact -> state,
all deterministic.
```

## The core property: a lying agent is caught mechanically

A **scoped-write agent that lies** — writes `b.txt` (outside its allowed-path list) while
reporting that it changed only `a.txt` — is rejected by independent verification, not trusted:

```
Agent claimed changed_paths=['a.txt']; actually wrote: ['b.txt']
Independent verification: FAIL
  - claim_mismatch: Reported changed_paths ['a.txt'] do not equal the actual sandbox change set
  - scope_violation: Changed path is outside the rendered allowed-path list [b.txt]
```

This is Milestone 1's founding rule carried all the way into agent execution: agent output is
evidence to verify, never an authority. The full lying-stub matrix (under-claim, over-claim,
out-of-scope, protected-path, read-only-that-writes, verification-command failure, malformed
path, timeout, non-UTF-8 / malformed / duplicate-key / extra-field reports, binding mismatches,
and target-repository mutation) is exercised in `tests/test_agent_verification.py` and
`tests/test_agent_runner.py`.

## Boundary honored

Milestone 3 never writes the target repository: all agent writes land in a throwaway sandbox
clone or under `~/.ai-workflow-engine/`. A scoped-write agent's verified patch is *stored*, not
applied — applying it to the working tree is Milestone 4's controlled-change responsibility.
`GitClient.READ_ONLY_FORMS` is unchanged; the sandbox uses a separate `SandboxGit` bound only to
directories the process created. No clock value enters any run identity or state event.

## Limitations / notes

- The demonstration stubs the verification commands; a real run executes
  `conda run -n <env> pytest ...` in the sandbox (the argv is proven byte-equal to the prompt's
  displayed commands by `test_agent_runner.py::test_verification_argv_matches_template`).
- No live Codex/OpenCode binary is wired in; the runner is agent-agnostic and configured via
  `EngineConfig.agents`, and is exercised entirely against stub executables.
- The `version` governance-fact regex still only matches `0.x.y`; 0.2.0 is fine, but the 1.0.0
  bump requires the regex fix scheduled as T-501.
