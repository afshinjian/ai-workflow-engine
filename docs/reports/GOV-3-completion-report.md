# GOV-3 Completion Report

## Result

Implemented GOV-3 — "Attempt-aware report artifact naming in the Reporting Skills" — exactly as
its authorized "Recommended shape" describes: the four `_generate_report` callers in
`agentos_workflow/skills/reporting.py` take an optional, validated `sequence`, so one workflow's
own audit directory holds `reports/qa.1.json`, `reports/qa.2.json`, … ; the content-hash
idempotency and differing-content refusal are unchanged per artifact; and
`QAAgent._report_scope`'s derived-identifier workaround was removed in the same change so the two
cannot drift. The implementation is complete and validated; it is **uncommitted**, stopped for
Human Owner approval per the standard workflow. Task status remains `Current`.

## The defect, and what changed

`_generate_report` wrote to a fixed `<audit_root>/<workflow_id>/reports/<kind>.json` — one
artifact per workflow per kind — and correctly refused to overwrite an existing artifact whose
content differed (`AUDIT_MODEL.md`'s append-only semantics). A single workflow, however,
legitimately produces several genuinely different reports of the same kind: the bounded repair
loop (`FAILURE_RECOVERY.md` §1) runs one implementation attempt and one QA round per repair, each
with its own verdict, findings, and diff. The second round therefore failed on the *artifact*
rather than on the code under review.

AUTO-005 could not touch `agentos_workflow/skills/**` and worked around it by deriving a
per-attempt audit scope (`<workflow_id>.qa<N>`) inside `QAAgent`. Every artifact stayed inside the
audit root, but the rounds lived in sibling directories rather than in the workflow's own — not
what `AUDIT_MODEL.md` intends, and, as the task record put it, not a shape to build on.

Now: `sequence=None` (every existing caller) produces the byte-identical `<kind>.json` artifact it
always did; `sequence=N` produces `<kind>.N.json` inside that workflow's own `reports/` directory,
beside its `audit.jsonl`.

## Delivered

`agentos_workflow/skills/reporting.py`:
- `_validate_sequence` — mirrors the existing `_validate_component` shape and rejects anything
  that is not an integer in `1..9999`, `bool` explicitly excluded (it is a subclass of `int` and
  would otherwise name an artifact `qa.True.json`). Because the sequence is a validated integer
  rather than a caller-supplied string, everything `_validate_component` refuses for an identifier
  is unreachable in a filename by construction.
- `_generate_report` takes `sequence: int | None = None`, validates it before any path is built,
  names the artifact accordingly, and records `report_sequence` in the document when a sequence is
  supplied — so an artifact read on its own says which round produced it. When no sequence is
  supplied, no `report_sequence` key is added and the serialized bytes are unchanged.
- `generate_stage_report`, `generate_qa_report`, `generate_failure_report`, and
  `generate_closeout_report` each expose the optional `sequence` and forward it.

`agentos_workflow/agents/qa.py`: `_report_scope` deleted; `review` now passes the real
`workflow_id` together with `sequence=attempt_number`.

Documentation: `docs/workflow-automation/SKILL_CONTRACTS.md` §6 records the additive contract
change and that idempotency stays **per artifact** (Version 1.2 → 1.3, MINOR — an added optional
input, no existing behaviour removed or renamed); `docs/workflow-automation/DECISIONS.md` DD-40
records the rationale (Version 1.10 → 1.11); `docs/workflow-automation/OPEN_QUESTIONS.md` OD-12
records the caller-side round-numbering question described below (Version 1.5 → 1.6).

## Scope decision

Two things were deliberately **not** done.

1. **Who assigns QA round numbers (new: OD-12).** The Orchestrator runs a QA round with
   `attempt_number=1` before the repair loop starts, and `run_repair_loop` then numbers its own
   internal rounds from 1 as well — so the loop's first round reuses a number already consumed.
   Both rounds are real reviews with different content, so the second write is refused, and the
   loop's attempt 1 fails on the artifact rather than on the code. Sequencing does not fix this
   and should not: two reports claiming the same round number *ought* to collide, or the
   append-only model would be silently relaxed. The fix is to give the round number a single
   owner (e.g. a `first_attempt_number` threaded through `run_repair_loop`), which changes
   `agentos_workflow/agents/**` and the Orchestrator sequence that drives the pre-loop round —
   outside the naming change GOV-3 authorizes, and a design decision rather than a mechanical
   edit. Recorded as OD-12, not fixed here. It costs one repair attempt out of a budget of three
   on every workflow that repairs.
2. **Sequencing the other three generators' call sites.** The parameter is available on all four
   generators (the task's recommended shape says "the four `_generate_report` callers"), but only
   `QAAgent` is changed to pass it, because only the QA round has a caller that demonstrably
   produces more than one report per workflow today. `CloseoutAgent`'s single closeout report and
   the failure/stage reports keep their existing unsequenced names, unchanged.

## Validation

All commands run via `conda run -n ai-workflow-engine`.

- `pytest agentos_workflow/tests/test_skills_reporting.py
  agentos_workflow/tests/test_agents_implementation_qa.py
  agentos_workflow/tests/test_agents_repair_loop.py` → **95 passed**.
- `pytest tests agentos_workflow/tests` → **2697 passed, 1 failed**. The single failure,
  `agentos_workflow/tests/e2e/test_dry_run.py::test_full_workflow_created_to_done_with_one_repair_and_one_interruption`,
  is **pre-existing and unrelated to this change**: it raises `AuthorizationBindingDriftError` on
  `engine_version` because `running_engine_version()` resolves the editable install's `1.0.0`
  while the test hardcodes `0.1.0`. Reproduced identically against a clean `HEAD` (`58ed4f6`)
  tree extracted with `git archive`, with none of this change present, failing at the same
  assertion (`test_dry_run.py:407`) — which is *before* the repair-loop section this change
  touches. Same failure GOV-2's report documented.
- `ruff check --no-cache .` → **All checks passed!**
- `black --check .` → **156 files would be left unchanged.**
- `mypy --no-incremental src` → **Success: no issues found in 56 source files.**
- `mypy --no-incremental agentos_workflow` → **Success: no issues found in 63 source files.**
- `git diff --check` → clean.
- `workflowctl verify --config self-governance.yaml` → **Verdict: PASS** (git, task-state,
  governance, registries, handover).

## Tests Added or Updated

`agentos_workflow/tests/test_skills_reporting.py` — six new tests: the sequenced artifact lands
inside the *same* workflow directory for all four generators (parametrized); three successive
rounds do not collide; an omitted sequence keeps the unsequenced name and adds no
`report_sequence` key; the same kind *and* sequence still refuses differing content; an identical
sequenced regeneration is still idempotent; and unsafe sequences (`0`, `-1`, `10000`, `"1"`,
`1.0`, `True`, `"../escape"`) are rejected as `UNSAFE_INPUT`/`NON_RETRYABLE` with nothing written.

`agentos_workflow/tests/test_agents_implementation_qa.py` — two new tests: every QA round's
artifact is exactly `<audit_root>/<workflow_id>/reports/qa.<attempt>.json` with the audit log
beside it and no sibling directory left in the audit root (this is the assertion that would fail
if the `_report_scope` workaround came back); and the artifact records the round that produced it.
The pre-existing `test_each_qa_round_writes_its_own_artifact` is unchanged and still passes.

`agentos_workflow/tests/e2e/test_dry_run.py` — comment only: the note at the repair-loop
assertion named `QAAgent._report_scope` and `<workflow_id>.qa1`, neither of which exists after
this change. Rewritten to name OD-12 and `reports/qa.1.json`. No assertion, fixture, or code path
changed; the `repair_attempts_used == 2` expectation is unaffected, because the collision it
describes is caused by the reused round number, not by the artifact name.

## Self-review

Re-read the whole diff once, looking for the four things the task workflow names.

- **Scope creep.** The runtime change is confined to `skills/reporting.py` and `agents/qa.py`,
  the two files the task's recommended shape names. Three documentation files under
  `docs/workflow-automation/` and the e2e comment were touched only because they *describe* the
  mechanism this change alters; each is recorded above. Nothing under `src/`, `tests/`,
  `scripts/`, or the dependency declarations was touched.
- **A test that passes trivially.** `test_unsafe_sequences_are_rejected` asserts the reports
  directory does not exist afterwards, so it fails if validation ever moved after the write.
  `test_every_qa_round_stays_in_the_workflows_own_audit_directory` asserts the audit root contains
  exactly one entry, which is what makes it a real regression guard against the removed workaround
  rather than a restatement of the path. Verified empirically rather than argued: both new test
  files were copied onto the clean `HEAD` (`58ed4f6`) tree and run there — **16 of the 17 new
  tests fail** against the unmodified source, and all 61 pre-existing tests in those two files
  still pass. The one new test that passes on both is
  `test_an_omitted_sequence_keeps_the_unsequenced_name`, which is exactly the test asserting the
  behaviour this change leaves alone.
- **A silently swallowed failure.** `_validate_sequence` returns a typed `SkillFailure` on every
  rejection path, following the file's existing `if problem := …: return problem` idiom; there is
  no new `except`, no new default, and no path where an invalid sequence falls through to a write.
- **Unintended Git or network calls.** None. The diff adds no subprocess, no network call, and no
  Git invocation.

Found and fixed during this pass: nothing requiring a code change. The e2e comment update above
was identified here as a dangling reference to the deleted `_report_scope` and corrected.

This is an ordinary engine task — not a milestone, release, or trust-boundary change — so a
bounded self-review is the standard and no independent review is mandated. The change does not
widen what the engine may do without a human: it only names artifacts inside the audit root that
were already being written there.

## Limitations and follow-ups

- **OD-12** (new): the pre-loop QA round and the repair loop's first internal round are both
  numbered attempt 1, so one repair attempt is still wasted on an artifact collision. See "Scope
  decision".
- `_MAX_REPORT_SEQUENCE` is 9999; a workflow needing more reports of one kind would be refused.
  That is far above the repair loop's ceiling of 3.
- Sequenced and unsequenced artifacts of the same kind can coexist in one workflow directory
  (`qa.json` and `qa.1.json`). No caller does this today; nothing prevents it.
- The pre-existing `test_dry_run.py` environment failure (engine version `1.0.0` vs `0.1.0`) is
  untouched and still open.

## Unrelated observation — the handover names two stashes that no longer exist

Not touched by this task, recorded for a Human Owner decision rather than fixed.
`handover/PROJECT_HANDOVER.md`'s "Current Git state" table (written 2026-07-28) lists
`stash@{0}` and `stash@{1}` as "untouched since before AUTO-002", and its "Next session" section
says never to delete either. The repository has **no stashes at all**: `git stash list` is empty,
`refs/stash` does not exist, and there is no stash reflog. This was already true at the first
command of this session, before any change was made here; no stash operation was performed by
this session. Whether the stashes were intentionally dropped and the handover not updated, or
lost, is not something this session can determine from the repository — it needs the Human
Owner's knowledge, and the handover's historical text was deliberately left unedited.

## Review and Git

No commit, push, merge, branch change, or stash operation was performed; the complete diff is
left in the working tree for Human Owner inspection.

## Addendum — Human Owner approval and closure (2026-07-29)

The Human Owner reviewed this report and the implementation diff, typed the two exact `APPROVE`
confirmations required by `scripts/workflow-approve.sh`, and approved the Conventional Commit
message `feat(workflow): add attempt-aware report artifact naming to the Reporting Skills (GOV-3)`. The script then performed the deterministic governance closeout
recorded in `docs/DECISION_LOG.md`'s matching entry and staged the approved implementation
together with the generated closeout records in one local commit. This commit's hash, and any
later publication or merge, are recorded separately — a commit cannot record its own hash.
