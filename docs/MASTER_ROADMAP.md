# Master Implementation Roadmap — to Version 1.0

Status: DRAFT, awaiting human approval. No implementation task in this roadmap begins until the
roadmap itself is approved. Produced 2026-07-17 from the verified repository state recorded in
`docs/IMPLEMENTATION_GAP_ANALYSIS.md`.

Scope discipline: this roadmap implements exactly the approved four-milestone roadmap in
`docs/milestones.md` (M-1 and M-2 already done), plus the closeout/synchronization work the
governance layer itself requires, plus the 1.0.0 release mechanics. It invents no new
milestones. Task IDs use the `T-<milestone><nn>` shape (e.g. `T-301`) so the existing
governance parser recognizes them; they are added to `docs/TASK_QUEUE.md` as each becomes
Current.

Standing rules for every task below (stated once, not repeated per task):

- Validation always includes, at minimum: `pytest -q`, `ruff check .`, `black --check .`,
  `mypy src`, and `workflowctl verify --config self-governance.yaml` — all green before a task
  is Done. Tasks list only their *additional* validation.
- Every task updates `docs/TASK_QUEUE.md` + mirrors, `docs/CHANGELOG.md`, and (when detail
  changed) `handover/PROJECT_HANDOVER.md` + regenerated `handover/PROJECT_CHECKSUM.md` at
  completion.
- No `git commit`/`git push` without explicit human approval, per `docs/AGENT_PROTOCOL.md`.
- Architectural decisions and rejected alternatives are recorded in `docs/DECISION_LOG.md`.

---

## Stage 0 — Governance closeout and documentation synchronization

### Objective
Close GOV-1 formally and eliminate the documentation drift found in the gap analysis, so
Milestone 3 starts from a fully synchronized repository.

### Purpose
The governance layer is this project's operating system; M-3 changes the `workflow/` package and
CLI, and must not start while any governance mirror or prose document misstates reality.

- Dependencies: none.
- Estimated complexity: low (documentation only; no `src/` changes).
- Affected components: governance documents, README, architecture docs, handover pair.
- Risks: none material; every edit is mechanically re-checked by `workflowctl verify`.

### T-101 — Close out GOV-1
- **Objective:** Flip `GOV-1` to `Done` in `docs/TASK_QUEUE.md` and both mirrors; record the
  closeout in `docs/PROJECT_STATE.md` and `docs/CHANGELOG.md`; refresh
  `handover/PROJECT_HANDOVER.md` + checksum manifest.
- **Dependencies:** roadmap approval.
- **Deliverables:** updated five governance documents, handover pair.
- **Validation commands:** standing set (in particular `workflowctl check-task-state`,
  `check-governance`, `check-handover` must PASS with 0 Current tasks).
- **Completion criteria:** `verify` PASS; no document names GOV-1 as in progress.

### T-102 — Documentation synchronization
- **Objective:** Fix the four discrepancies in the gap analysis: mark
  `docs/milestone-2-plan.md` as implemented/approved (status line only — the normative contract
  text is immutable history), extend `README.md` with the `prompt` command surface and current
  milestone state, extend `docs/architecture.md` with the prompt pipeline (summary +
  pointer to the plan), refresh stale test counts.
- **Dependencies:** T-101.
- **Deliverables:** updated `docs/milestone-2-plan.md` (status line), `README.md`,
  `docs/architecture.md`, `docs/GOVERNANCE_AUDIT.md`/`handover` count refresh.
- **Validation commands:** standing set.
- **Completion criteria:** no document claims Milestone 2 is unimplemented; README documents
  every existing CLI command.

---

## Milestone 3 — Non-interactive agent execution

### Objective
Per `docs/milestones.md`: "Codex read-only review and scoped OpenCode writes, strict report
schemas, isolation, timeouts, and independent claim verification." Plus the capabilities
Milestone 2 explicitly deferred here: persisted workflow state, verdict recording, transition
enforcement, and next-stage computation.

### Purpose
Today the engine renders governed prompts but a human must carry them to an agent and carry the
result back. M-3 lets the engine hand a stored prompt to a configured, non-interactive agent
process and — critically — *verify the agent's claims against the repository* instead of
trusting its report, preserving the Milestone 1 rule that agent output is evidence, not
authority.

- Dependencies: Stage 0 complete.
- Estimated complexity: high — the largest remaining milestone.
- Affected components: new `workflow/` state machine, new `agents/` package, `models.py`
  (config schema extension), `cli.py`, governance docs, tests.
- Affected files (planned closed list, finalized in T-301): add
  `src/ai_workflow_engine/workflow/{state_machine,store,transitions}.py`,
  `src/ai_workflow_engine/agents/{__init__,models,runner,isolation,verification}.py`; modify
  `src/ai_workflow_engine/models.py`, `cli.py`, `workflow/__init__.py`; add
  `tests/test_workflow_state.py`, `tests/test_agent_models.py`, `tests/test_agent_runner.py`,
  `tests/test_agent_verification.py`; extend `tests/test_cli.py`; modify `docs/configuration.md`,
  `docs/architecture.md`, `examples/amozesh_konkur.yaml`, `self-governance.yaml`.
- Validation strategy: unit + integration tests using **stub agent executables** (small scripts
  the tests create), never a live Codex/OpenCode dependency; timeout/isolation tests with
  deliberately misbehaving stubs; claim-verification tests where the stub lies and must be
  caught; read-only regression guard that `GitClient.READ_ONLY_FORMS` is byte-unchanged.
- Acceptance criteria: an operator can run a full plan-review→…→governance-review cycle for a
  task where each stage's prompt is generated, executed by a configured non-interactive agent,
  its report parsed against a strict schema, its claims independently verified, and the verdict
  recorded in persisted state with enforced transitions — with every failure mode (timeout,
  malformed report, out-of-scope write, false claim) deterministically detected and reported.
- Risks: (1) design surface is large — mitigated by a normative plan document reviewed before
  code, exactly as M-2 did; (2) sandboxing/isolation guarantees on a local machine are
  best-effort (temporary worktree + path allowlist verification + env scrubbing), and the plan
  must state honestly what is and is not guaranteed; (3) live agent CLIs are unavailable/
  non-deterministic — mitigated by making the agent command fully configurable and testing
  exclusively against stubs.

### T-301 — Milestone 3 normative architecture plan
- **Objective:** Write `docs/milestone-3-plan.md` at the same rigor as `docs/milestone-2-plan.md`:
  exact state-machine model (states, verdict-bearing transitions, evidence records, storage
  protocol reusing the M-2 atomic no-clobber approach), exact `agents` config schema, exact
  report schema, runner/timeout/isolation semantics, claim-verification algorithms, CLI surface,
  closed file list, and testing strategy.
- **Dependencies:** T-102.
- **Deliverables:** `docs/milestone-3-plan.md`.
- **Validation commands:** standing set (docs only); then a **fresh plan review** per
  `docs/AGENT_PROTOCOL.md` before any T-302+ work.
- **Completion criteria:** plan review returns APPROVED.

### T-302 — Persisted workflow state machine
- **Objective:** Implement the state model deferred from M-2: per-task stage state, verdict
  recording, transition enforcement with evidence, and next-stage computation, persisted
  atomically under `~/.ai-workflow-engine/workflow-runs/state/` per the T-301 plan; CLI verbs
  (`workflowctl state show|record-verdict|next-stage` or as the plan names them).
- **Dependencies:** T-301 approved.
- **Deliverables:** `workflow/` modules, CLI integration, `tests/test_workflow_state.py`, docs.
- **Validation commands:** standing set + new state tests, including crash/concurrency cases.
- **Completion criteria:** transitions outside the approved graph are rejected with FAIL;
  state survives process restart; implementation review APPROVED.

### T-303 — Agent configuration schema and strict report models
- **Objective:** Extend `EngineConfig` with the `agents` section (per-role executable, args
  template, timeout, mode read-only|scoped-write) and implement strict Pydantic report models
  (verdict token, findings, claimed changed paths, transcript digest) that reject any
  out-of-schema output.
- **Dependencies:** T-301 approved (may proceed in parallel with T-302).
- **Deliverables:** `agents/models.py`, `models.py` changes, config docs/examples, tests.
- **Validation commands:** standing set + `tests/test_agent_models.py`.
- **Completion criteria:** malformed/extra-field/verdict-hedging reports all rejected; config
  round-trips through `load_config` with the same path/strictness defenses as existing sections.

### T-304 — Non-interactive agent runner with isolation and timeouts
- **Objective:** Execute a configured agent against a stored prompt: subprocess with hard
  timeout, working-directory isolation (read-only roles run against the repo with no write
  expectation; scoped-write roles run in a dedicated temporary Git worktree), environment
  scrubbing, captured transcript, and deterministic failure taxonomy (timeout, nonzero exit,
  schema-invalid output).
- **Dependencies:** T-302, T-303.
- **Deliverables:** `agents/runner.py`, `agents/isolation.py`, tests with stub agents.
- **Validation commands:** standing set + `tests/test_agent_runner.py` (timeout kill, hung
  stub, garbage output, worktree cleanup).
- **Completion criteria:** no runner code path can invoke a writable Git operation on the real
  repository; `READ_ONLY_FORMS` unchanged; implementation review APPROVED.

### T-305 — Independent claim verification
- **Objective:** Verify agent reports against reality: actual diff of the isolated worktree vs.
  claimed changed paths, allowed-path containment, protected-path enforcement, verification
  command re-execution, and exact single-token verdict extraction. A false or unverifiable claim
  is a FAIL finding, never a warning.
- **Dependencies:** T-304.
- **Deliverables:** `agents/verification.py`, CLI (`workflowctl agent run <stage>` or per plan),
  `tests/test_agent_verification.py` including lying-stub cases.
- **Validation commands:** standing set + the new suite.
- **Completion criteria:** every lying-stub scenario in the plan's test matrix is caught.

### T-306 — Milestone 3 closeout
- **Objective:** Fresh implementation review + remediation rounds until APPROVED; governance
  closeout: M-3 → Done, changelog, decision log, architecture doc, handover refresh; version
  bump per plan (e.g. 0.2.0) with the version fact staying consistent.
- **Dependencies:** T-302..T-305.
- **Deliverables:** synchronized governance layer; `docs/VALIDATION_REPORT.md`-style evidence
  appended or a new M-3 validation report.
- **Validation commands:** standing set; full-cycle demonstration on this repository itself
  using a stub agent.
- **Completion criteria:** `verify` PASS; review APPROVED; roadmap updated.

---

## Milestone 4 — Controlled commit and push

### Objective
Per `docs/milestones.md`: "Approval-bound staging allowlists, commit verification,
protected-path enforcement, remote/upstream checks, and explicit push gates."

### Purpose
Completes the workflow loop: after M-3 verifies work, M-4 lets the engine stage, commit, and
push it — but only through explicit, evidence-checked, human-approval-bound gates, replacing
"agent promises it committed the right thing" with mechanical verification.

- Dependencies: Milestone 3 complete (per `docs/TASK_QUEUE.md` dependency order).
- Estimated complexity: medium-high.
- Affected components: new `git/writer.py` (separate from the read-only `GitClient`, whose
  allowlist stays byte-unchanged), `models.py` approval/allowlist schema, `cli.py`, workflow
  state integration, governance docs, tests.
- Affected files (planned, finalized in T-401): add `src/ai_workflow_engine/git/writer.py`,
  `src/ai_workflow_engine/git/approval.py`, `tests/test_git_writer.py`,
  `tests/test_commit_push_gates.py`; modify `models.py`, `cli.py`, `docs/configuration.md`,
  `docs/architecture.md`, `self-governance.yaml`, `examples/amozesh_konkur.yaml`.
- Validation strategy: all write-path tests run against disposable temp repositories with local
  file:// remotes; tests prove refusal-by-default (no approval artifact → no write), staging
  allowlist containment, protected-path refusal, upstream/ahead-behind gate math, and that the
  single authorized push is the only remote-mutating operation.
- Acceptance criteria: `workflowctl` can stage exactly an approved allowlist, verify the staged
  set byte-for-byte, create a commit whose contents are re-verified post-hoc, and push only
  when live branch/HEAD/upstream/counts match the approval artifact — each step individually
  gated, logged, and refused on any mismatch; `allow_automatic_commit`/`allow_automatic_push`
  remain false and are never consulted to bypass a gate.
- Risks: this milestone touches real Git state — mitigated by keeping every write behind an
  explicit per-invocation approval artifact (no ambient approval), a separate writer class so
  the read-only client is provably unchanged, and temp-repo-only tests.

### T-401 — Milestone 4 normative architecture plan
- **Objective:** `docs/milestone-4-plan.md`: approval-artifact format (what a human signs off,
  how it binds branch/HEAD/paths), exact staging/commit/push gate algorithms, CLI surface,
  closed file list, test matrix.
- **Dependencies:** T-306.
- **Deliverables:** the plan document; fresh plan review APPROVED.
- **Validation commands:** standing set.
- **Completion criteria:** plan review APPROVED.

### T-402 — Approval-bound staging and commit verification
- **Objective:** Implement the staging allowlist + commit path per plan: stage exactly the
  approved paths, refuse protected paths, verify the staged index against the allowlist before
  commit, verify the created commit's tree afterward.
- **Dependencies:** T-401.
- **Deliverables:** `git/writer.py`, `git/approval.py`, CLI, `tests/test_git_writer.py`.
- **Validation commands:** standing set + new suite.
- **Completion criteria:** refusal-by-default proven; implementation review APPROVED.

### T-403 — Push gates
- **Objective:** Implement the push gate per plan (live-state equality with the approval
  artifact: branch, HEAD, upstream, behind == 0, clean tree) and the single authorized push,
  mirroring the M-2 `push` prompt's algorithm mechanically.
- **Dependencies:** T-402.
- **Deliverables:** push gate code, CLI, `tests/test_commit_push_gates.py` with file:// remotes.
- **Validation commands:** standing set + new suite.
- **Completion criteria:** every mismatch case refuses without side effects; review APPROVED.

### T-404 — Milestone 4 closeout
- **Objective:** Fresh review/remediation to APPROVED; governance closeout (M-4 → Done),
  changelog, decision log, architecture/config docs, handover refresh; version bump per plan
  (e.g. 0.3.0).
- **Dependencies:** T-402, T-403.
- **Deliverables:** synchronized governance layer + validation evidence.
- **Validation commands:** standing set + full demonstration cycle.
- **Completion criteria:** `verify` PASS; review APPROVED.

---

## Release — Version 1.0.0

### Objective
Declare the approved roadmap complete and release 1.0.0.

- Dependencies: Milestone 4 complete.
- Estimated complexity: low.
- Risks: the `version` fact regex (`0\.\d+\.\d+`) breaks at 1.0.0 — fixing it is an explicit
  task deliverable, not a footnote.

### T-501 — 1.0.0 release readiness
- **Objective:** Update the `version` fact pattern in `self-governance.yaml` (and note the same
  limitation for `examples/amozesh_konkur.yaml`) to accept `\d+\.\d+\.\d+`; bump
  `pyproject.toml` and `docs/PROJECT_STATE.md` to 1.0.0; finalize `docs/CHANGELOG.md`; write
  `docs/FINAL_COMPLETION_REPORT.md` (completed milestones/tasks, architecture summary,
  validation summary, test results, known limitations, future improvements).
- **Dependencies:** T-404.
- **Deliverables:** version bump, regex fix, final report, fully synchronized governance layer.
- **Validation commands:** standing set at version 1.0.0.
- **Completion criteria:** `workflowctl verify --config self-governance.yaml` PASS at 1.0.0;
  final report present; repository presented to the human with recommended commit message and
  next actions — no commit/push performed.

---

## Sequencing summary

```text
approval → T-101 → T-102 → T-301 → (T-302 ∥ T-303) → T-304 → T-305 → T-306
        → T-401 → T-402 → T-403 → T-404 → T-501 → 1.0.0
```

## Open decisions the human should settle at approval time

1. **Commit cadence for existing uncommitted work.** M-2 + GOV-1 (and this roadmap/gap
   analysis) are uncommitted on `main` — the largest current risk. Recommended: approve a
   commit of the current working tree before T-301 begins. This roadmap does not assume it.
2. **CI.** Adding a minimal CI workflow (pytest/ruff/mypy/self-verify) is *not* in the approved
   milestone roadmap and is therefore not scheduled. Say the word and it becomes a small task in
   Stage 0; otherwise it stays a documented limitation.
3. **Intermediate version numbers** for M-3/M-4 closeouts (suggested 0.2.0/0.3.0) — cosmetic,
   but the plans will pin whatever is chosen.
