# Implementation Gap Analysis

Date: 2026-07-17. Produced by a fresh session following `docs/CONTEXT.md`'s read order, after
reading every source, test, documentation, and governance file in the repository and running
every available validation command. Nothing below is taken from prior conversation history.

## 1. Verified current state (observed, not asserted)

All commands run in the `ai-workflow-engine` conda environment against the actual working tree:

| Command | Result |
|---|---|
| `pytest -q` | 448 passed |
| `ruff check .` | clean |
| `black --check .` | 42 files unchanged |
| `mypy src` (strict) | no issues in 31 source files |
| `workflowctl verify --config self-governance.yaml` | PASS on all four checks (git, task-state, governance, handover), exit 0 |
| `git status` | branch `main` tracking `origin/main`; M-2 + GOV-1 work present and **uncommitted** |
| `git log --oneline` | 2 commits: project init, Milestone 1 (v0.1.0) |

## 2. Implemented features

- **Milestone 1 (committed, v0.1.0):** strict `EngineConfig` loading with repository-bound path
  defense; read-only `GitClient` with a fixed command allowlist; task-state parsing and mirror
  checks; regex fact-consistency checks; checksum-manifest handover verification from working
  tree/index/commit; protected-path matching; stable `CheckResult`/`VerificationReport` 1.0
  schema; `workflowctl` CLI (`version`, `inspect`, `check-*`, `verify`) with human/JSON output.
- **Milestone 2 (implemented + approved via three independent fresh reviews, uncommitted):**
  `ai_workflow_engine.prompt` — deterministic, canonically-hashed prompt rendering for seven
  fixed workflow stages, structural validation, race-safe atomic no-clobber storage under
  `~/.ai-workflow-engine/`, and the `workflowctl prompt <stage>` CLI surface. Implementation was
  cross-checked against `docs/milestone-2-plan.md`'s normative contracts (templates registry,
  canonical JSON, store protocol, validator checks) and matches; 249 prompt-specific tests pin
  the golden bytes/digests.
- **GOV-1 (in working tree, status `Current`):** the self-governance layer — five governance
  documents, three pure-documentation files, checksum-verified handover pair, and
  `self-governance.yaml`. Every acceptance criterion in `docs/current_task.md` is demonstrated in
  `docs/VALIDATION_REPORT.md`, and I independently re-verified the headline claims (verify PASS,
  test suite green).

## 3. Incomplete / remaining work

| Item | Status | Notes |
|---|---|---|
| GOV-1 closeout | Substantively complete, not closed | All acceptance criteria met; needs the formal status flip to `Done` (queue + mirrors), a handover refresh, and re-verification. |
| M-3 — Non-interactive agent execution | Not started | Also inherits everything Milestone 2 explicitly deferred: persisted workflow state, verdict recording, transition enforcement, reachability checks, automatic next-stage computation (`docs/milestone-2-plan.md`, `docs/DECISION_LOG.md`). |
| M-4 — Controlled commit and push | Not started | Depends on M-3. |
| Commit of M-2 + GOV-1 work | Blocked on human approval | Per `docs/AGENT_PROTOCOL.md`; not technically blocked. |

## 4. Documentation discrepancies found

1. **`docs/milestone-2-plan.md` line 3 is stale:** it still reads
   "Status: REVISED DRAFT, awaiting a fresh Plan Review. Not implemented." — but Milestone 2 is
   implemented, reviewed three times, and approved (per `docs/PROJECT_STATE.md`,
   `docs/TASK_QUEUE.md`, `docs/CHANGELOG.md`). Harmless to the parsers (only configured
   governance documents are parsed for task state) but misleading to a fresh reader.
2. **`README.md` describes only Milestone 1:** "Version 0.1.0 implements Milestone 1…", and its
   usage section omits the entire `workflowctl prompt` command surface that now exists.
3. **`docs/architecture.md` covers only the Milestone 1 pipeline:** the prompt subsystem's
   architecture lives solely in the (mis-labeled) plan document.
4. **Minor count drift:** `handover/PROJECT_HANDOVER.md` and `docs/GOVERNANCE_AUDIT.md` say
   "438 tests"; the suite now has 448 (both self-qualify with "at last check"/"as of this
   audit" — drift, not contradiction).

None of these is a mirror-check failure; `workflowctl verify` passes. They are prose drift in
unconfigured documents, to be fixed in a documentation-sync task.

## 5. Technical debt and architectural risks

1. **Uncommitted work on `main` is the single largest risk.** Milestone 2 and GOV-1 — thousands
   of lines including 249 tests — exist only in the working tree. Any accidental
   `git checkout`/`clean` destroys them unrecoverably. Committing requires explicit human
   approval per `docs/AGENT_PROTOCOL.md`, so this is surfaced here as the top-priority human
   decision, not silently acted on.
2. **The `version` governance fact regex only matches `0.x.y`** (`self-governance.yaml`,
   inherited from `examples/amozesh_konkur.yaml`). Reaching version 1.0.0 will make the required
   fact unextractable and turn `check-governance` into a FAIL. Already flagged in
   `docs/VALIDATION_REPORT.md`'s limitations; must be fixed before any 1.0.0 version bump.
3. **No CI.** `pre-commit` exists locally, but nothing runs `pytest`/`ruff`/`mypy`/
   `workflowctl verify --config self-governance.yaml` automatically. Known limitation
   (`docs/GOVERNANCE_AUDIT.md`, `docs/VALIDATION_REPORT.md`).
4. **Handover digest verification accepts prefixes** (`actual_digest.startswith(record.digest)`,
   minimum 8 hex chars per the manifest row regex). Deliberate, documented manifest format;
   noted because `self-governance.yaml`'s own manifest uses full 64-char digests, which is the
   stronger practice to keep.
5. **`workflow/` package is nearly empty** (a summary model only). This is by design — it is the
   documented extension point where Milestone 3's state model will live.

## 6. Missing tests

No gaps found against the currently approved scope. The M-2 plan's exhaustive testing-strategy
checklist is covered by the 448-test suite (golden bytes, identity-sensitivity matrices, store
concurrency, CLI byte-exactness, read-only regression guards). New capabilities in M-3/M-4 will
require their own suites, scoped in the roadmap.

## 7. Governance consistency

`workflowctl check-task-state` and `check-governance` pass: `docs/TASK_QUEUE.md` (authoritative)
agrees with `docs/current_task.md` and `docs/remaining_tasks.md`; the `version` fact agrees
between `docs/PROJECT_STATE.md` and `pyproject.toml`; the handover checksum verifies. The one
structural observation: GOV-1's acceptance criteria are all demonstrably met, so its `Current`
status is a pending-closeout state, not an inconsistency.

## 8. Conclusion

The repository is healthy, internally consistent, and exactly where its own governance documents
say it is: Milestones 1–2 done, GOV-1 ready to close, Milestones 3–4 unbuilt. The path to 1.0 is
the master roadmap's remaining work: close GOV-1, fix the documentation drift above, implement
Milestone 3 (agent execution + the deferred workflow state machine), implement Milestone 4
(controlled commit/push), then release 1.0.0 with the version-fact regex fix.
