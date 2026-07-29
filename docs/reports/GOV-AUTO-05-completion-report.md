# GOV-AUTO-05 Completion Report

## Result

Implemented `GOV-AUTO-05 — Fix resolved-blocker false positives in authorization`. The
authorization parser now distinguishes a task's canonical status field from literal status text
inside its description, and it limits owner-decision gating to active structured entries in an
open-question register's `## Open` section. The implementation is complete, validated, and
uncommitted, stopped for separate Human Owner approval. GOV-AUTO-05 is the sole `Current` task.

## Human Owner governance exception

The Human Owner explicitly authorized this implementation on 2026-07-30 through a one-time
governance exception. The normal `scripts/workflow-authorize.sh` gate could not authorize
GOV-AUTO-05 because its broad task-section scan falsely interpreted the task contract's literal
examples—such as `` `Status: Blocked` still refuses ``—as the task's actual status. Applying the
fix before normal authorization was therefore the only way to repair the gate.

Under the exception, the task and mirrors record a manual `Planned → Current` transition without
an authorization-only commit. The exception authorizes only GOV-AUTO-05's registered scope. It
does not authorize another task, push, merge, branch creation or switching, rebase, reset, amend,
force/history rewriting, or stash operations.

## Implementation

### Canonical task status

`scripts/workflow-authorize.sh` now treats the first non-blank line after the matching task
heading as the only possible canonical status field. The line must be a complete `Status: VALUE`
field (or the already-supported complete emphasized field form); trailing prose is not accepted.
The status value is then handled explicitly:

- `Planned`, `READY`, or `Ready` may continue to normal authorization;
- `Current` and `Done` retain their existing refusals;
- canonical `Blocked` refuses with the precondition exit;
- unsupported or missing canonical status fails closed.

The former broad scan of the entire task section for `Status: Blocked`, `blocked on`, or
`authorization blocked` was removed. Quoted examples, Markdown emphasis in prose, acceptance
criteria, explanatory sentences, blockquotes, and fenced examples later in the section have no
lifecycle meaning. The same first-field discipline is used when detecting an existing Current
task.

### Active open questions

For a registry-governed task, `OPEN_QUESTIONS.md` is parsed by section and entry:

- only `## Open` is considered;
- each `###` entry is evaluated independently;
- an entry marked with a resolved disposition is ignored even if temporarily retained under
  `## Open`;
- an explicit authorization-blocking declaration or structured `Blocked:` field naming the task
  refuses;
- `## Resolved` is never scanned for blockers;
- negated or historical wording such as `no longer blocked`, `not blocked`, and `formerly
  blocked` does not refuse.

Predecessor, registry state, registered branch, dirty-tree, upstream, confirmation, staging,
commit, and stash-integrity checks were not changed.

## Tests

`tests/test_workflow_authorize_script.py` adds or strengthens coverage for:

- the exact GOV-AUTO-05 regression: canonical `Status: Planned` followed by inline-code,
  acceptance-criteria, blockquote, fenced, and emphasized literal `Status: Blocked` examples
  reaches the normal authorization prompt without mutation;
- a real canonical `Status: Blocked` refusal;
- historical task prose that says authorization was blocked;
- a registry `BLOCKED` refusal;
- an active `## Open` entry explicitly blocking DASH-004;
- resolved-section blocker text;
- resolved disposition retained under `## Open`;
- `no longer blocked` wording;
- historical `formerly blocked` wording.

All refusal and prompt-only regression cases assert that HEAD and the working tree remain
unchanged.

## Validation

- `bash -n scripts/workflow-authorize.sh` — PASS.
- `pytest -q tests/test_workflow_authorize_script.py` — **40 passed**.
- Broader workflow-specific regression set — **246 passed**.
- `ruff check --no-cache tests/test_workflow_authorize_script.py` — PASS.
- `black --check tests/test_workflow_authorize_script.py` — PASS.
- `git diff --check` — PASS.
- `shellcheck scripts/workflow-authorize.sh` — no warning/error findings; the unchanged dynamic
  library source produces informational SC1091 because ShellCheck cannot resolve the runtime
  path.
- `pytest -q tests agentos_workflow/tests` — **2736 passed** as part of the final combined run
  after the two approval-gate regression tests were added.
- `ruff check --no-cache .` — PASS.
- `black --check .` — PASS; 186 files unchanged.
- `mypy --no-incremental src` — PASS; 56 source files.
- `mypy --no-incremental agentos_workflow` — PASS; 63 source files.
- `workflowctl check-task-state --config self-governance.yaml` — PASS; exactly one Current task
  (GOV-AUTO-05), 36 Done, and 7 Planned.
- `workflowctl check-governance --config self-governance.yaml` — PASS.
- `workflowctl check-registries --config self-governance.yaml` — PASS; 17 stages across two
  registries, neither modified.
- `workflowctl check-handover --config self-governance.yaml` — PASS.
- `workflowctl verify --config self-governance.yaml` — PASS on git, task-state, governance,
  registries, and handover.

## Bounded self-review

- Scope is limited to the registered script, workflow-specific tests, workflow documentation,
  governance records, this report, and the handover pair.
- The exact regression test would fail against the previous broad task-section scan and checks
  for the normal authorization prompt, the absence of a blocked diagnostic, and zero repository
  mutation.
- Positive safety cases remain explicit: canonical task `Blocked`, registry `BLOCKED`, and an
  active unresolved open question all refuse without mutation.
- The diff adds no push, merge, reset, rebase, force, branch deletion, branch creation/switching,
  stash, or network operation. Existing branch preparation and all other authorization safety
  checks are untouched.

## Approval state

No implementation commit, push, merge, branch operation, reset, rebase, amend, force/history
rewrite, or stash operation was performed. The complete worktree diff is left for Human Owner
review and approval with the recommended commit message:

`fix(workflow): avoid resolved blocker false positives (GOV-AUTO-05)`.

## Implementation addendum — approval-gate canonical status parsing

The same defect was reproduced in `scripts/workflow-approve.sh` before Human Owner approval:
although GOV-AUTO-05's canonical field was `Status: Current`, the approval gate scanned the
entire task section for `Status: Blocked`, `blocked on`, or `authorization blocked`. Literal
examples in the task contract therefore caused:

```text
ERROR: task GOV-AUTO-05 is blocked — not closeable
```

This was fixed in the existing GOV-AUTO-05 scope before approval. The approval gate now applies
the same canonical-field rule as the authorization gate: the first non-blank whole-line status
field after a task heading is authoritative. Current-task discovery, the current-task mirror,
post-closeout status extraction, the guarded `Current → Done` replacement, and next-Planned
discovery all use whole canonical fields. The broad whole-section blocker scan was removed.

A true canonical `Status: Blocked` still refuses with `EXIT_NOT_CLOSEABLE` before any governance
mutation. Literal examples in explanatory prose, acceptance criteria, Markdown emphasis,
blockquotes, and fenced text are ignored. The guarded replacement changes only the canonical
Current field and preserves every heading, blank line, and explanatory example verbatim.

Two regression tests were added to `tests/test_workflow_approve_closeout.py`:

- canonical `Status: Current` plus all literal `Status: Blocked` example forms completes approval,
  creates exactly one implementation-plus-closeout commit, preserves the examples, and leaves the
  disposable repository clean;
- canonical `Status: Blocked` refuses with no new commit, no staged content, and byte-identical
  task queue, mirrors, project state, decision log, changelog, handover, and checksum.

The existing Git-safety test continues to prove successful approval does not push or merge and
does not change the branch or stash list. Focused approval tests are **32 passed**; the broader
workflow-specific regression set is **247 passed**. No branch, report, scope, confirmation,
closeout, staging, checksum, commit, push, merge, remote, or stash protection was changed.

The required combined command
`pytest tests agentos_workflow/tests agentos_dashboard/tests` collected 2,892 tests:
**2,891 passed and 1 failed**. The sole failure is
`agentos_dashboard/tests/test_parsing_task_queue.py::test_real_task_queue_parses_dash_003_as_current`,
which hardcodes that DASH-003 is Current although committed `HEAD` records DASH-003 as Done. The
same failure was reproduced from an isolated `git archive HEAD` with no GOV-AUTO-05 working-tree
changes (1 failed in 0.04s). No `agentos_dashboard/**` file is in GOV-AUTO-05's diff or current
allowed paths, so this pre-existing stale dashboard test was recorded and not changed. Every
other test in the required combined run passed.

Final addendum validation:

- `bash -n scripts/workflow-approve.sh` — PASS.
- `pytest tests/test_workflow_approve_closeout.py` — **32 passed**.
- broader workflow-specific regression set — **247 passed**.
- `ruff check --no-cache .` — PASS.
- `black --check .` — PASS; 186 files unchanged.
- `mypy --no-incremental src` — PASS; 56 source files.
- `mypy --no-incremental agentos_workflow` — PASS; 63 source files.
- `mypy --no-incremental agentos_dashboard` — PASS; 28 source files.
- `git diff --check` — PASS.
- `workflowctl verify --config self-governance.yaml` — PASS on git, task-state, governance,
  registries, and handover.

## Addendum — Human Owner approval and closure (2026-07-30)

The Human Owner reviewed this report and the implementation diff, typed the two exact `APPROVE`
confirmations required by `scripts/workflow-approve.sh`, and approved the Conventional Commit
message `fix(workflow): avoid resolved blocker false positives (GOV-AUTO-05)`. The script then performed the deterministic governance closeout
recorded in `docs/DECISION_LOG.md`'s matching entry and staged the approved implementation
together with the generated closeout records in one local commit. This commit's hash, and any
later publication or merge, are recorded separately — a commit cannot record its own hash.
