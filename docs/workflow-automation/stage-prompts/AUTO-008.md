# AUTO-008 — Engine CI Baseline: Packaging, Type-Checking, and Verified Blocker Fixes

| Field | Value |
|---|---|
| **Stage** | AUTO-008 · Role: Engine implementation session |
| **Branch** | `feature/auto-008-engine-ci-baseline` |
| **Commit message** | `fix(workflow): land the engine in CI, packaging, and type-checking (AUTO-008)` |
| **Report** | `docs/reports/workflow-automation/AUTO-008-completion-report.md` |
| **Status/Version** | Draft · 1.0 |

Apply the Standard Stage Protocol in `README.md` in full.

## Canonical Prompt

You are the **Engine implementation session** executing **AUTO-008 — Engine CI baseline**.

Preconditions: AUTO-001..AUTO-007 all `COMPLETE`; recorded Human Owner authorization naming
AUTO-008; branch `feature/auto-008-engine-ci-baseline` created from clean `main`.

**Context.** An architectural audit of this repository established that `agentos_workflow` —
the AUTO-001..007 orchestrator — is substantially complete and heavily unit-tested but has never
run as a program, and is not verified by any automated gate. Specifically: it has no
`cli.py`, no `.agentos/workflow.yaml`, is absent from `pyproject.toml`'s wheel `packages`, is not
importable outside the repository root, is not type-checked, and its 1,575 tests never execute in
CI. Its single end-to-end acceptance demonstration (`MVP_SCOPE.md` §4) fails on `main`.

This stage makes the existing engine verifiable. It builds no new capability.

**Allowed**: `pyproject.toml`, `.github/workflows/ci.yml`, `.pre-commit-config.yaml`,
`agentos_workflow/**`, `agentos_dashboard/tests/**`, plus SSP-required documentation and report
updates.

**Prohibited**: any new feature or public interface — no CLI command, flag, configuration field,
workflow state, agent capability, provider argv change, or skill binding. No change to
`src/ai_workflow_engine/**`. No change to `scripts/**`. No real Claude CLI, Codex CLI, or GitHub
invocation.

**Build**:

1. Bring `agentos_workflow` and `agentos_dashboard` under `pytest` `testpaths`, the wheel
   `packages` list, and `mypy`, so CI and pre-commit verify all three packages by one invocation.
2. Give `agentos_workflow` its own version, independent of the `ai-workflow-engine` distribution
   version. Reading the distribution version couples this engine's
   `HUMAN_AUTHORIZATION_MODEL.md` §2 item 11 binding to an unrelated package's release cadence,
   so a legacy-engine version bump silently invalidates every in-flight authorization under §4.
3. Resolve **OD-11**: `stage_contract_hash` is compared in one format by
   `PMOAgent.check_preconditions` and another by `LocalResumeObserver`, so no
   `AuthorizationRecord` value can satisfy both. Unify on one canonical format.
4. Resolve **OD-10**: forward `allowed_environment_variables` at every Git/GitHub Skill call site
   in `agents/git.py` and `agents/merge.py` whose Skill accepts it.
5. Correct `AuthorizationBindingDriftError`'s message, which reports the drift direction
   backwards.
6. Decouple the `agentos_dashboard` task-queue test from mutable live governance content.
7. Remove the test-only production workarounds in `tests/e2e/test_dry_run.py` that items 3 and 4
   made unnecessary. A workaround retained after its defect is fixed re-hides the defect.

**Tests**: a regression test per fix — cross-module hash-format equivalence for OD-11 (the two
implementations cannot import each other, so only a test that computes both can hold them
aligned), the rendered drift message, and the version decoupling. The end-to-end dry run must
pass with zero test-only production workarounds.

**Acceptance**: one `pytest` run collects and passes all three suites; `ruff`, `black`, and `mypy`
clean across all three packages; the wheel contains all three; all three importable from outside
the repository root; the end-to-end dry run green.

**Explicitly out of scope**, and to be reported rather than fixed: binding AUTO-006's eight
Git/GitHub Skills into `default_skill_registry()`; normalising the `expected`/`actual` parameter
convention across the drift raise sites; anything requiring a real CLI or real GitHub call.
