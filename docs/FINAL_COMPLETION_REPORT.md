# Final Completion Report — ai-workflow-engine v1.0.0

Date: 2026-07-18. This report is produced at the completion of the human-approved
`docs/MASTER_ROADMAP.md`: all four milestones of `docs/milestones.md` are implemented, validated,
and governance-reviewed, and the project is at version 1.0.0. Nothing has been committed or pushed
as part of this work beyond the single human-approved preservation commit of 2026-07-17 — see
"Repository status" at the end.

## Completed milestones

| Milestone | Version | What it delivers |
|---|---|---|
| **M-1 — Deterministic inspection** | 0.1.0 (committed) | Read-only Git inspection, governance/task-state mirror checks, source-aware handover checksum verification, protected paths, structured `CheckResult`/JSON results, the `workflowctl` CLI. |
| **M-2 — Governed prompt generation** | (in preservation commit) | Deterministic, canonically-hashed, byte-exact Markdown prompts for seven fixed workflow stages; structural validation; race-safe atomic no-clobber storage; `workflowctl prompt <stage>`. |
| **GOV-1 — Self-governance** | — | The engine governs its own repository: five governance documents, decision log, changelog, agent protocol, checksum-verified handover pair, `self-governance.yaml`. |
| **M-3 — Non-interactive agent execution** | 0.2.0 | A persisted, hash-chained workflow state machine (`workflowctl state`); the `agents` config + strict report contract; a snapshot-sandbox runner with hard timeouts and isolation; independent claim verification with tamper-evident run artifacts (`workflowctl agent run`). |
| **M-4 — Controlled commit and push** | 0.3.0 → 1.0.0 | A separate typed writable-Git surface; per-invocation human approval artifacts; `workflowctl commit` / `push` / `apply-patch` gates with protected-path enforcement and remote/upstream checks. |

## Completed tasks

Every task was individually implemented and independently reviewed. Both milestone plans went
through plan review (M-4's took two rounds; the M-3 plan one round after a first rejection); each
milestone closeout went through governance review.

- **Stage 0:** T-101 (GOV-1 closeout), T-102 (documentation sync), T-103 (lightweight CI),
  T-104 (a real `FORCE_COLOR` JSON-corruption bug found during review, fixed).
- **Milestone 3:** T-301 (normative plan), T-302 (state machine), T-303 (agent config + report
  schemas + prompt-payload schema bump), T-304 (sandbox + runner), T-305 (verification +
  artifacts + CLI), T-306 (closeout, v0.2.0).
- **Milestone 4:** T-401 (normative plan), T-402 (writer + commit gate), T-403 (push gate +
  apply-patch), T-404 (closeout, v0.3.0).
- **Release:** T-501 (version-fact regex fix, 1.0.0 bump, this report).

## Architecture summary

The engine is a one-way, deterministic pipeline layered milestone by milestone on a shared
result/invariant core (`CheckResult`/`Status`, canonical JSON, the atomic no-clobber storage
protocol):

```text
config → read-only inspection (M-1)
       → governed prompts (M-2)
       → agent execution: sandbox runner + independent verification + state machine (M-3)
       → approval-gated commit/push (M-4)
```

Founding principle, preserved end-to-end: **an agent's output is evidence to verify, never an
authority.** M-1 inspects Git/file/hash facts directly; M-3 verifies every agent claim against
the sandbox reality it observed (a lying agent is caught mechanically); M-4 refuses any commit
outside its human approval and re-verifies the commit it made. Safety boundaries: the read-only
`GitClient.READ_ONLY_FORMS` allowlist is byte-unchanged across all four milestones; the M-3
sandbox and the M-4 writer are separate surfaces; the target repository is never written except
through an M-4 gate bound to a human approval (the one exception, `apply-patch`, is bound to a
verified M-3 artifact and writes the working tree only). No clock value enters any identity or
gate decision, so every prompt, run, and gate is reproducible.

## Validation summary

At version 1.0.0, run in the `ai-workflow-engine` conda environment:

```
pytest -q                     -> 684 passed
FORCE_COLOR=3 pytest -q       -> 684 passed
ruff check .                  -> All checks passed
black --check .               -> 69 files unchanged
mypy src                      -> Success: no issues in 44 source files
workflowctl verify --config self-governance.yaml  -> Verdict: PASS (git, task-state, governance, handover)
```

The suite grew from 448 tests (M-1) to 684. Each milestone has a demonstration produced by
running the real tool: `docs/VALIDATION_REPORT.md` (GOV-1), `docs/MILESTONE_3_VALIDATION.md`
(incl. lying-agent detection), `docs/MILESTONE_4_VALIDATION.md` (incl. an un-approved-change
refusal, then a real commit and push to a `file://` remote).

## Test results

684 passing, both with and without `FORCE_COLOR` set (the T-104 regression guard ensures the
machine-readable JSON contract is never corrupted by ANSI colour). Coverage includes: golden
byte/digest pins for the seven prompt templates; identity-sensitivity matrices; store-concurrency
threads; the full workflow transition table; the agent lying-stub matrix; the commit/push gate
refusal cases against disposable temp repos and a `file://` remote; and read-only regression
guards proving `READ_ONLY_FORMS` is unchanged and no writable Git reaches the target repo outside
an M-4 gate.

## Known limitations

- **Approval artifacts are a local-operator control, not authentication.** M-4 approvals carry no
  signature/crypto; the gate records the file's SHA-256 and `approved_by` for the audit trail.
- **`apply-patch` is the one writable op not bound to a human approval** (it is bound to a
  verified M-3 run artifact + a live-HEAD match + clean-tree + dry-run). Flagged for the human in
  `docs/milestone-4-plan.md`; retained per the approved plan.
- **Isolation is a correctness boundary, not a security sandbox.** M-3 runs agents in a snapshot
  clone with a scrubbed environment and a before/after target-repo fingerprint; a malicious agent
  with absolute-path write access is *detected* (the run fails), not *prevented*.
- **No live Codex/OpenCode integration.** The agent runner is agent-agnostic and configured via
  `EngineConfig.agents`; it is exercised entirely against stub executables. Wiring a real agent
  binary is configuration, not code.
- **CI runs the repository-content checks, not `check-git`.** `actions/checkout` yields a detached
  HEAD with no upstream, which `check-git` correctly refuses — an environment artifact.

## Future improvements (not in the completed scope)

These are explicitly *not* part of the delivered roadmap; they are candidates for a future
roadmap, listed to separate them from completed work:

- Signed/authenticated approval artifacts, if the tool moves beyond a single trusted local
  operator.
- A live agent-binary integration (Codex/OpenCode) plus an end-to-end multi-stage workflow driver
  that chains prompt → agent run → verification → state transition automatically.
- Stronger sandbox isolation (containers/namespaces) if the threat model changes from "detect" to
  "prevent".
- A `workflowctl state`-driven orchestrator that computes the next stage and generates its prompt
  in one step.

## Repository status and recommended next actions

All work beyond the single human-approved preservation commit of 2026-07-17 is **uncommitted** in
the working tree; `main` is one commit ahead of `origin/main` and **nothing has been pushed**.
Per `docs/AGENT_PROTOCOL.md` and the project mission, committing and pushing require explicit
human approval — which the Milestone 4 gates this project now provides are designed to mediate.

The recommended next action is a human decision on committing (and, separately, pushing) the
completed 1.0.0 work. A concrete recommendation and a proposed commit message accompany this
report in the session summary.
