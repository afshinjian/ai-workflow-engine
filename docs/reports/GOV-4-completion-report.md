# GOV-4 — Completion Report

**Isolate Claude live-test configuration per attempt and add bounded test-only format retries**

Registered and authorized by the Human Owner on 2026-08-02, as an ordinary (non-AUTO/GOV-AUTO-
family) engine task record following the GOV-2/GOV-3 precedent. This is a pre-AUTO-013 baseline-
verification correction to the `agentos_workflow` live acceptance test harness, discovered while
verifying the AUTO-013 baseline required by `docs/workflow-automation/stage-prompts/AUTO-013.md`.
It is not AUTO-013, does not authorize AUTO-013, and does not implement any workflow mode.

## 1. Baseline evidence that surfaced the defects

Verifying the AUTO-013 baseline (`pytest -q -m live_cli -rs` required 25 passed / 0 skipped)
against the account directory then in use for live Claude runs reproduced a real, contract-
violating failure: `TestLiveClaude::test_the_prompt_arrives_through_stdin` returned `FAILED` with
Claude reasoning that a genuine `<system-reminder>` showed "Plan mode is active" and refusing the
auto-mode JSON-only contract, then writing a plan file — the same signature the account directory
had accumulated over many unrelated interactive sessions.

## 2. Defect 1 — test-to-test/session-to-session configuration isolation

`agentos_workflow/tests/live/test_live_providers.py`'s `selected_account` fixture (session-scoped,
autouse) forwarded the configured Claude account's real, long-lived `CLAUDE_CONFIG_DIR` to every
invocation in the entire suite and across separate suite runs. Claude Code's own client-side
continuity state — `.claude.json`, `projects/`, `plans/`, session JSONL — accumulated there
unchecked. Comparing two full-suite runs against the same (then-isolated) directory, hours apart,
showed 100% contract compliance on the first (freshly provisioned) run and the identical
plan-mode-refusal signature reappearing on the second, correlated with the directory's growth
(`.claude.json` 36,124 → 44,872 bytes; 21 accumulated `projects/` entries; 3 `plans/` files).

**Fix:** `_stage_ephemeral_claude_config_dir(root)`. The configured account directory
(`CLAUDE_CONFIG_DIR_A`) is now a **read-only authentication template**, never itself assigned to
`CLAUDE_CONFIG_DIR`. Every invocation gets a fresh directory under its own `tmp_path`, containing
only the allowlisted `.credentials.json` — confirmed sufficient by direct, controlled probe (a
bare, otherwise-empty 0700 directory with only that file, 0600, authenticated and completed a
full real turn; no `.claude.json` field is required). Everything the CLI itself subsequently
creates lives and dies with that `tmp_path`, never carried into the next invocation.
`selected_account` no longer forwards `CLAUDE_CONFIG_DIR` at session scope at all (Codex's
`CODEX_HOME` forwarding is unaffected).

## 3. Defect 2 — non-deterministic first-attempt format compliance

Independent of Defect 1: two full `live_cli` suite runs performed *after* the isolation fix each
produced exactly one failure — a different test each time, always the same shape (`is_error:
false`, clean exit, no plan-mode reasoning) — a short prose sentence followed by a fenced JSON
block instead of the required bare object, under both `plan` and `acceptEdits` permission modes,
on the first invocation of brand-new ephemeral directories. `unfenced()` in
`agentos_workflow/providers/base.py` only strips a fence wrapping the model's *entire* answer, so
prose outside it is correctly never recognized as fenced, and the run is correctly classified
`FAILED`/`MALFORMED_OUTPUT`. This is real-model formatting variance, not an isolation symptom and
not an engine defect.

**Fix:** `run_live_claude_with_bounded_format_repair`, a test-only helper. Retries **only**
`FAILED` + `failure.kind is MALFORMED_OUTPUT`; every other outcome (timeout, spawn failure, a
genuine `BLOCKED`, any other `FAILED` kind, authentication/sandbox/environment/output-limit/
process-cleanup/scope/secret/mutation failures) is accepted on attempt one and returned unchanged.
Attempt limit: **3** (`CLAUDE_FORMAT_REPAIR_ATTEMPT_LIMIT`). Each attempt gets its own fresh
ephemeral `CLAUDE_CONFIG_DIR`, session directory, and disposable git repository (a `tmp_path`
subdirectory per attempt), so an abandoned attempt's possible partial edit is never inspected or
reused. Same prompt and permission mode preserved across attempts. Stops immediately at the first
non-format-failure result. Retains sanitized evidence per attempt (`LiveAttemptRecord`: attempt
number, status, failure kind, artifact **paths** only, never content) and emits a `UserWarning`
naming every attempt's status whenever more than one was needed, so a repair is never silent even
on a passing run.

Applied to the five Claude tests whose pass/fail depends on model-produced structured output
(structured-result, stdin-token, planning-mode, controlled-write, ambiguous-task). Codex's
ambiguous-task test still calls the original, unmodified helper directly — no Codex evidence of
this failure mode exists, so no Codex retry policy was added.

Deterministic, single-attempt rejection of malformed output is preserved and reinforced: new test
`test_prose_before_a_fenced_report_is_rejected_not_normalized` (mocked, `test_provider_runtime.py`,
no retry involved) pins the exact observed live failure shape against the unmodified parser,
alongside the pre-existing `test_a_fenced_report_is_still_read`, `test_a_question_is_not_a_result`,
and the parametrized `test_malformed_or_incomplete_output_is_rejected_never_defaulted`.

## 4. Scope

Test-only. No production code (`agentos_workflow/providers/`, `agentos_workflow/agents/`,
`agentos_workflow/orchestrator/`, `agentos_workflow/config/`, `results.py`, `service.py`, or any
other production path) is touched. No parser change, no permission-mode change, no provider argv
change, no new workflow state, no `workflowctl` change. Files changed:
`agentos_workflow/tests/live/test_live_providers.py`,
`agentos_workflow/tests/test_provider_runtime.py`.

## 5. Validation

- 3 solo re-runs of the originally-failing test: 3/3 passed.
- 4 targeted Claude tests × 3 iterations: all passed; one iteration showed a real repair in
  action (`test_planning_mode_writes_nothing`, attempt 1 `failed` → attempt 2 `blocked`, stopped
  correctly at the first non-format-failure result).
- Full live suite, run 1: **32 passed, 0 failed, 0 skipped** (one visible repair:
  `test_write_enabled_mode_writes_exactly_the_one_allowed_file`, `#1=failed → #2=completed`).
- Full live suite, run 2: **32 passed, 0 failed, 0 skipped** (one visible repair:
  `test_planning_mode_writes_nothing`, `#1=failed → #2=blocked`).
- Authentication template (`.credentials.json`): file count, SHA-256, and mtime_ns identical
  before vs. after every live run performed across both defect fixes.
- Interactive `.claude-A` directory: zero diffs under `plans/` or `projects/` (the only markers
  that would indicate live-test bleed) across the whole session.
- Every attempt verified to use a unique ephemeral config/session/repository directory —
  structurally proven in `TestLiveSuiteGuards` and observed directly in the repair-triggering
  runs above.
- Malformed output never normalized into success: confirmed both by the new deterministic mocked
  test and by every observed live repair, where the failing attempt's classification was preserved
  in the diagnostic warning rather than discarded.
- Full repository validation, all clean: `pytest -q` (3,470 passed, 32 deselected — +1 for the new
  deterministic mocked test), `ruff check .`, `black --check .`, `mypy` (project's configured
  scope, `agentos_workflow/tests/` excluded per `pyproject.toml`; 122 source files, matching
  AUTO-012's baseline count exactly), `pre-commit run --all-files`, `workflowctl verify
  --config self-governance.yaml` (full PASS).

## 6. Deferred findings

None newly discovered beyond the two defects this task resolves. No unrelated finding was fixed.

## 7. Confirmation

AUTO-013 is not registered, authorized, branched, or implemented by this task. This closure
authorizes no successor.
