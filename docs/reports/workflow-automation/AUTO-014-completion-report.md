# AUTO-014 — Completion Report

| Field | Value |
|---|---|
| Stage | AUTO-014 — CI, Merge, Repository Finalization, and Runtime Closeout |
| Branch | `feature/auto-014-merge-closeout` |
| Contract | `docs/workflow-automation/stage-prompts/AUTO-014.md` |
| Status | Approved, fully validated, governance-closed; ready for commit/push |

## Verdict

AUTO-014 is implemented as a resumable `WorkflowService` continuation through
`MergeCloseoutModeDriver`. It resumes only persisted AUTO-013 runtime histories, reconciles the
target PR, evaluates persisted validation/QA evidence, enables target-repository squash
auto-merge, polls required checks with a bounded budget, confirms the merge, updates the local
baseline fast-forward-only, applies branch retention/deletion policy, writes closeout evidence,
and reaches `DONE` through existing legal transitions. The corrected disposable live E2E completed
the full AUTO-013 → AUTO-014 provenance chain. AUTO-014 is fully validated and governance-closed;
the authorized commit and push are the remaining publication actions.

## Implementation completed

- Added `agentos_workflow/merge_closeout.py` and focused tests.
- Added the `workflowctl auto continue` CLI path and service delegation.
- Added target-repository branch-retention and bounded-polling configuration.
- Extended PR observation with base/head branch and mergeability evidence.
- Extended closeout reporting and safe branch-retention behavior.
- Added the direct security blocker preventing external/manual workflow records from attaching:
  AUTO-014 requires persisted completed AUTO-013 initial-execution attempts for commit, push, and
  PR creation, validated through the canonical engine history reader.
- Added a narrow fallback for installed legacy `gh` versions that reject `pr checks --json`.

No workflow state or transition was added. AUTO-014 remains limited to `PR_OPEN`,
`AUTO_MERGE_ENABLED`, `WAITING_FOR_CHECKS`, `MERGED`, `CLOSING`, and `DONE`.

## Validation

| Check | Result |
|---|---|
| Focused AUTO-014/service/CLI/approval/live-resume tests | PASS — 320 |
| GitHub Skill + AUTO-014 regression | PASS — 78 tests |
| Full `pytest -q` | PASS — 3,535 passed, 32 deselected |
| Ruff | PASS |
| Black `--check` | PASS |
| `git diff --check` | PASS |
| `workflowctl check-task-state --config self-governance.yaml` | PASS — 0 Current, 48 Done, 6 Planned |
| `workflowctl verify --config self-governance.yaml` | PARTIAL — task/governance/registries/handover PASS; Git fails only on `upstream_missing` |
| `pytest -q -m live_cli -rs` | PASS — 32 passed, no authentication skips (Human Owner verified environment) |
| `ruff check .` | PASS |
| `black --check .` | PASS |
| `mypy --strict` | PASS — no issues in 124 source files |
| `pre-commit run --all-files` | PASS |
| `python -m build --no-isolation` | PASS — wheel successfully built (Human Owner verified environment) |
| Wheel out-of-tree imports | PASS — prior AUTO-013 wheel/import evidence remains unchanged; no AUTO-014 packaging source changed |
| Forbidden destructive commands / commit / push on engine repository | PASS — none run |

## Live acceptance boundary

## Repository ledger

| Repository | Local historical conclusion | Evidence and disposition |
|---|---|---|
| `afshinjian/auto-014-disposable-1785759666` | Reported as the invalid manual-PR attempt; exact existence is not independently proven by surviving local artifacts | The report records PR `#1` as manually created/synthetic and invalid, but no surviving temporary clone, remote, workflow state, or shell-history entry was found. Treat as historical reported evidence only; not accepted and not reused. |
| `afshinjian/auto-014-disposable-1785775978` | Existence not independently proven; it appears only in cleanup reporting and may be a transcription error | No local clone remote, workflow state, PR artifact, commit reference, or shell-history entry was found. |
| `afshinjian/auto-014-disposable-1785776005` | Accepted repository | Temporary clone remotes and persisted AUTO-013 authorization/transitions identify this repository; workflow `auto014-real-provenance-live-8` reached `PR_OPEN`, PR `#2` references commit `ec93e6ceab4ba9de9147aaf26e7b2cdcc4e7edf1`, and local Git history records merge/baseline SHA `180481d2b6c3d6e5cddcbef428b9b97d1a6d263c`. AUTO-014 reached `DONE`. |

The accepted run was the only live acceptance used for completion evidence. Earlier disposable
runs that failed before PR creation (fixture ignore, Claude plan mode, audit-root setup, and Git
author setup) remain historical diagnostic evidence. The terminal AUTO-013-LIVE-7 run reached
genuine `PR_OPEN` but AUTO-014 initially failed because the repository did not allow auto-merge;
the repository policy was repaired and fresh AUTO-013-LIVE-8 was used. No manually created PR or
fabricated `PR_OPEN` record was used. No broader OAuth scope was requested.

## Deferred findings

No newly discovered non-blocking defect was implemented or promoted to a GOV stage. The stale
AUTO-013 publication wording already recorded in the registration remains deferred and outside
AUTO-014 scope. Cleanup was completed manually by the Human Owner; the missing `delete_repo`
permission did not affect the workflow lifecycle or its acceptance evidence.

## Stop condition

The working tree remains uncommitted. No commit or push was performed on the engine repository;
the only PR and merge were in the disposable acceptance repository. AUTO-015 was not begun.
Cleanup is complete according to the Human Owner, who manually deleted
`afshinjian/auto-014-disposable-1785759666` and
`afshinjian/auto-014-disposable-1785775978`; no broader OAuth scope was requested. The accepted
run recorded repository `afshinjian/auto-014-disposable-1785776005`, which differs from the
second repository name in the cleanup notice, so that identity discrepancy is preserved here
without rewriting the acceptance evidence. AUTO-014 is `COMPLETE`/`Done` and ready for the
authorized commit and push. AUTO-015 remains unauthorized and untouched.
