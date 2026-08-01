# AUTO-012 — Configurable Approval Policy, Persistence, and Invalidation — Completion Report

| Field | Value |
|---|---|
| **Stage** | AUTO-012 |
| **Branch** | `feature/auto-012-approval-policy` |
| **Base** | `e2b069cd3d43132b806f78552d74bfb83a7d1506` (AUTO-011 publication merge) |
| **Contract** | `docs/workflow-automation/stage-prompts/AUTO-012.md` |
| **Status** | Implemented and fully validated; **uncommitted**, awaiting Human Owner approval |

## 0. Verdict in one paragraph

The engine has a reusable approval subsystem. `ApprovalService`
(`agentos_workflow/approvals.py`) resolves a strict typed policy across built-in, project, gate,
and run layers into an immutable snapshot; persists every step as append-only events through the
*existing* `StateStore` discipline; supports all three decisions and all five timeout actions;
binds four checksums and invalidates on any change; and evaluates deadlines lazily with **no
thread, timer, sleep, or scheduler anywhere** — a deadline is a fact on disk, proven to survive a
restart. `AUTO_APPROVE` is refused when inherited from a broad default and accepted only from the
gate or a per-run override. **No workflow state was added**, and the reason is documented (§13). The
governance prerequisite was met before implementation: `HUMAN_AUTHORIZATION_MODEL.md` moves to v2.0
with a new §5a recording the Human Owner's decision, which authorizes the subsystem only. Both
modified production files are **purely additive** (146 insertions, 0 deletions); every provider,
agent, skill, config, CLI, orchestrator-engine, `src/`, `scripts/`, and packaging path is
byte-identical to `e2b069c`, and six `workflowctl` invocations match a clean baseline worktree
exactly. **3,469 tests pass** (3,352 + 117); 25 live CLI tests pass with zero skips; `mypy --strict`
clean over 122 source files.

---

## 1. Baseline evidence

| Check | Required | Observed | Result |
|---|---|---|---|
| Branch | `main` | `main` | PASS |
| HEAD | `e2b069cd3d43132b806f78552d74bfb83a7d1506` | identical | PASS |
| `main` vs `origin/main` | equal | both `e2b069c`, 0/0 | PASS |
| Working tree | clean | clean | PASS |
| `workflowctl verify` | passes | **PASS** (all five checks) | PASS |
| `pytest -q` | 3,352 tests | **3,352 passed**, 25 deselected (153.47s) | PASS |
| `pytest -q -m live_cli -rs` | 25 passed, 0 skipped | **25 passed, 0 skipped** (305.41s) | PASS |
| AUTO-008..AUTO-011 merged and published | yes | PRs #6, #9, #10, #11 all merged | PASS |
| No AUTO-012 implementation exists | none | no branch, no `ApprovalService`/`ApprovalPolicy`/`approvals.jsonl` symbol, no registry row | PASS |

Baseline verification read `0 Current, 44 Done, 6 Planned` across 21 registry stages. Branch
`feature/auto-012-approval-policy` was then created from that clean, synchronized `main`.

## 2. Governance authorization and the Human Owner decision

The four documents the directive required be inspected first were read **before any
implementation**, and one of them blocked the stage as written.

`HUMAN_AUTHORIZATION_MODEL.md` v1.1 §1: *"The only human gate in this system is the
`CREATED → AUTHORIZED` transition… No other point in the workflow asks for or accepts human
approval."* §8: *"adding any second human-approval point[] is a MAJOR change requiring explicit
Human Owner sign-off, since it changes the core safety property this program is built around."*

Building an approval subsystem without that sign-off would have contradicted the governing document
while implementing the thing it forbade. The prerequisite was therefore satisfied as its own
governance act, ahead of the code:

* `HUMAN_AUTHORIZATION_MODEL.md` → **v2.0**. §1 amended from "the only human gate" to "the founding
  human gate", with the amendment stated in place rather than silently rewritten. New **§5a —
  Configurable Approval Gates (Human Owner decision, 2026-08-01)**. §6 and §8 updated.
* `docs/DECISION_LOG.md` — two dated entries: the governance decision (with alternatives
  considered and rejected) and the AUTO-012 stage authorization.
* `STAGE_REGISTRY.md` §5 — a dedicated authorization-log entry for the governance decision, plus
  the AUTO-012 authorization and preflight entries.

**What §5a authorizes:** the *subsystem* — typed policy, four-layer resolution, immutable snapshot,
durable append-only records, manual decisions, timeout decisions, checksum binding, invalidation.

**What it does not:** any specific Preparation, Reviewer, or Implementer workflow; the *placement*
of a gate at any particular point in any mode; AUTO-013 or any successor. Each needs its own
sign-off.

**Seven constraints restated normatively and explicitly not relaxed:** the founding gate and all
its bindings and invalidation conditions are unchanged and an approval is never a route to
`AUTHORIZED`; an approval is evidence, not authority (`AGENT_CONTRACTS.md` §1); an approval never
substitutes for a deterministic machine gate and no admin-bypass path is created
(`SECURITY_MODEL.md` §4); every approval is bound to the state it was granted against; an approval
is single-use and cannot be replayed for another workflow or gate; automatic approval is opt-in at
the point of use; no Model Provider, Agent, or Skill may grant, decide, extend, or consume an
approval.

Registration mirrors: `TASK_QUEUE.md`, `current_task.md`, `remaining_tasks.md`, `PROJECT_STATE.md`,
`DECISION_LOG.md`, `STAGE_REGISTRY.md` (row + three log entries), and the contract at
`stage-prompts/AUTO-012.md`. `workflowctl verify` after registration: `1 Current, 44 Done, 6
Planned`, 22 registry stages.

## 3. Approval architecture

```text
WorkflowService                          (5 new operations, delegating)
        │
        ▼
ApprovalService                          (agentos_workflow/approvals.py)
        ├── resolve_approval_policy      built_in → project → gate → run
        ├── request_approval             immutable snapshot + absolute deadline + 4 checksums
        ├── get_approval                 pure replay; evaluates nothing, writes nothing
        ├── evaluate_approval            lazy timeout; the whole timeout mechanism
        ├── decide_approval              manual APPROVE / REJECT / REQUEST_CHANGES
        ├── consume_approval             recompute checksums → CONSUMED or INVALIDATED
        └── list_approvals
        │
        ▼
StateStore.record_approval / read_approvals    (2 additive methods)
        │
        ▼
<state_directory>/<workflow_id>/approvals.jsonl
```

The module holds a `StateStore` and nothing else — no provider, no agent, no Skill, no lock, no
workflow session, no network client. An approval cannot cause work to happen; it records only that
permission was asked for, given, withheld, expired, or spent.

**Events, not a mutable record.** An approval is an append-only sequence of `ApprovalEvent`s
(`REQUESTED`, `DECIDED`, `TIMED_OUT`, `ESCALATED`, `EXTENDED`, `INVALIDATED`, `CONSUMED`), and the
current `ApprovalRequest` is derived by replay. "No decision is ever overwritten" is therefore a
property of the file format rather than a promise: there is no code path that rewrites a line,
because the only write is an append. This mirrors what `StateStore` already does for transitions.

## 4. Policy model

`ApprovalPolicyOverlay` (every field optional) is one configuration layer. `ApprovalPolicy` (frozen,
`extra="forbid"`) is the resolved snapshot.

| Field | Purpose |
|---|---|
| `required` | Whether the gate has an approval at all |
| `timeout_seconds` | `None` means no deadline and no expiry |
| `timeout_action` | One of the five actions |
| `channels` | Where a decision may arrive from; at least one required |
| `approvers` | Allowlist; empty means any named approver |
| `escalate_to` | Required non-empty when the action is `ESCALATE` |
| `escalation_extension_seconds` | The at-most-one extension; `None` means none |
| `escalation_fallback_action` | What follows escalation; **may not be `ESCALATE`** |
| `timeout_action_source` | Which layer chose the timeout action |
| `escalation_fallback_source` | Which layer chose the fallback |

The last four are additive beyond the six the contract named ("at least"). `escalate_to` alone does
not bound escalation — a fallback and an extension cap are what stop it becoming a loop — and the
two `*_source` fields exist because `AUTO_APPROVE`'s provenance is security-relevant and must remain
auditable after the fact.

Overlay and snapshot are distinct types on purpose: "unset" and "set to the default value" must be
distinguishable, and that difference is exactly what the `AUTO_APPROVE` opt-in rule turns on.

## 5. Precedence resolution

```text
built-in defaults → project configuration → per-gate configuration → per-run override
```

Each layer overrides only the fields it actually sets, so a project that widens a timeout does not
silently reset the channels a gate chose. The built-in floor is the most conservative policy
expressible: approval required, no timeout, `PAUSE` if a layer above adds a deadline without naming
an action, CLI only, no approvers.

**The snapshot is not retroactive.** The policy is a value, not a reference, so editing
configuration after a request exists cannot reach it. A test opens a request under a 60-second
`PAUSE` policy, re-resolves a 1-second `FAIL` policy, and asserts the open request still carries 60
seconds, `PAUSE`, and its original deadline.

**`AUTO_APPROVE` requires explicit opt-in.** Valid only from the `GATE` or `RUN` layer; refused with
`ApprovalPolicyError` when inherited from `BUILT_IN` or `PROJECT`. It **fails closed and loudly**
rather than silently downgrading to something safer — a downgrade would leave a configuration that
*says* `auto_approve` behaving as `pause`, which is a trap: the operator would believe automation is
enabled and discover otherwise only when a deadline passed, with nothing in the record explaining
why. Eight tests cover it, including that a gate participating in resolution does not launder a
project's choice (the gate must select it *itself*), and that the escalation fallback obeys the same
rule.

## 6. Timeout-action semantics

| Action | Result | Terminal? | Recorded |
|---|---|---|---|
| `AUTO_APPROVE` | `APPROVED` | no (consumable) | `manual_or_auto = AUTO`, `timeout_action_applied = AUTO_APPROVE`, `decision = APPROVE`, `approver = None` |
| `PAUSE` | `HUMAN_INTERVENTION_REQUIRED` | **no — resumable** | `timeout_action_applied = PAUSE` |
| `FAIL` | `FAILED` | yes | `timeout_action_applied = FAIL` |
| `CANCEL` | `CANCELLED` | yes | `timeout_action_applied = CANCEL` |
| `ESCALATE` | `ESCALATED` → optional one-time extension → bounded fallback | no, then per fallback | `ESCALATED` and `EXTENDED` events; fallback recorded on expiry |

`PAUSE` is non-terminal by design: nobody answering in time is not the same as an answer, so a later
manual decision is still accepted — asserted by a test that pauses, then approves, and gets
`APPROVED` with `manual_or_auto = MANUAL`.

**Escalation is bounded three ways:** `escalation_fallback_action` may not be `ESCALATE` (refused at
policy validation, so no configuration can express a loop); at most one extension is ever granted,
and `extension_granted` is replayed from the event history rather than counted in memory, so a
restart cannot hand out a second one; and evaluation is idempotent. A test evaluates at
t+11/40/100/1 000/10 000 and asserts exactly one `ESCALATED` and exactly one `EXTENDED` event in the
file, ending `CANCELLED`.

No branch or repository cleanup is performed for `CANCEL` — out of scope, as directed.

## 7. Persistent-deadline design

`deadline = requested_at + timedelta(seconds=timeout_seconds)`, an absolute timezone-aware UTC
instant written into the `REQUESTED` event. `timeout_seconds is None` means no deadline and no
expiry (tested at t+10 000 000).

Evaluation is **lazy**: `evaluate_approval` compares the persisted instant against an injected
clock. Nothing sleeps, no thread waits, no scheduler state lives in the process. A test parses the
module's syntax tree and asserts it references none of `sleep`, `Thread`, `Timer`, `threading`,
`asyncio`, `sched`, `signal`, `alarm`, `monotonic`, `perf_counter`.

**Restart survival is tested, not asserted:** one test opens a 30-second `FAIL` approval, then
constructs an entirely new `ApprovalService` over the same directory — as a fresh process would —
and evaluates at t+31, getting `FAILED`. An in-memory timer could not do that.

`get_approval` deliberately stays a pure read: an audit view or a test must be able to observe that
an approval is `PENDING` past its deadline without that observation itself deciding the outcome. A
test asserts exactly this split.

The future daemon may evaluate the same fact eagerly; nothing here changes when it does. The daemon
is not implemented.

## 8. Approval request and decision schemas

`ApprovalRequest` is derived by replay, never stored. Every field the contract named is present:

`approval_id`, `workflow_id`, `gate`, `requested_at`, `deadline`, `policy_snapshot`, `channels`,
`approvers`, `checksums` (carrying `repo_state`, `diff`, `agent_result`, `gate_result`), `status`,
`source`, `approver`, `decision`, `decided_at`, `manual_or_auto`, `timeout_action_applied`, plus
`escalated_at`, `extension_granted`, and `invalidated_checksums`.

`channels` and `approvers` appear at the top level because the record contract names them there,
and are cross-validated against the snapshot so the two can never drift — the same
can't-disagree pattern AUTO-011 used for `duration_seconds`.

The four checksums are grouped in an `ApprovalChecksums` model rather than four loose strings, so
one comparison method (`differences`) owns the whole binding and reports *every* changed kind in a
fixed order.

Decisions are `APPROVE`, `REJECT`, `REQUEST_CHANGES`, mapped to status through one table so no
branch can invent a different answer. Each records source channel, approver identity, timestamp,
origin, and the exact checksum bindings. Channel and approver allowlists are enforced at decision
time.

`required=False` **refuses** a request rather than auto-satisfying it: returning a pre-approved
record would be automatic approval without the explicit opt-in this same stage exists to enforce.

## 9. Checksum binding

| Requirement | How |
|---|---|
| Deterministic canonical serialization | `checksum_of_mapping` sorts keys and uses tight separators, so two callers building the same mapping in different orders agree |
| Stable hashing | SHA-256, labelled `sha256:` matching `CONTRACT_HASH_ALGORITHM_PREFIX`; shape validated (64 lowercase hex) |
| Canonical `AgentRunResult` used | `checksum_of_agent_result` hashes `result.to_canonical_json()` — AUTO-011's own bytes, so the checksum cannot drift from the contract it binds. **No second result contract exists**; a test asserts the module declares no `*RunResult` class |
| No secret leakage | Only digests are stored. A test puts a `ghp_…` token in the diff material and asserts the token appears nowhere in `approvals.jsonl` while its digest does |
| Same input → identical checksum | tested |
| Any changed input → invalidation | tested, per checksum |
| Recomputed immediately before consumption | `consume_approval` compares caller-recomputed checksums before spending |

Raw bytes are hashed, never normalized: a change altering only line endings still changes the state
that was approved — the same argument `calculate_contract_hash` makes for the contract binding.

## 10. Invalidation behaviour

On `consume_approval`, the deadline is evaluated first, the approval must be `APPROVED`, and then
the four checksums are compared. Any difference appends an `INVALIDATED` event recording **which**
kinds changed and what was observed, and the approval becomes `INVALIDATED` — terminal.

* Each of the four checksums independently invalidates (parametrized).
* An invalidated approval **cannot be consumed** (`ApprovalStateError`).
* It is **not silently recreated** — a test asserts still exactly one approval, still `INVALIDATED`.
* It is **never auto-approved** — a test lets `AUTO_APPROVE` fire, invalidates, then evaluates at
  t+10 000 and asserts the status stays `INVALIDATED`.
* A consumed approval **cannot be spent twice**.
* An undecided or rejected approval cannot be consumed at all.

## 11. Persistence and replay

`approvals.jsonl`, per workflow, under the state directory beside `transitions.jsonl`. Written
through `StateStore.record_approval`, which calls the **same** `_append_jsonl_line` the transition
history uses. Everything below is therefore inherited, not reimplemented — and each is exercised
through `ApprovalService`:

| Property | Test |
|---|---|
| Append-only | bytes after a decision start with the exact bytes after the request |
| No overwriting a decision | line 0 stays `REQUESTED`, line 1 is `DECIDED` |
| fsync | `os.fsync` is monkeypatched and observed firing ≥2 times (file + directory) |
| Duplicate-key rejection | a doubled `"gate"` key raises `StateStoreCorruptionError` |
| Monotonic ordering (write) | an out-of-order append raises `StateStoreOrderingError` |
| Monotonic ordering (read) | a tampered-in earlier record raises on read |
| Symlink refusal | a symlinked history raises `StateStorePathConfinementError` |
| Per-workflow confinement | two workflows get separate files |
| Restart-safe replay | a fresh service over the same directory recovers status, approver, decided-at, and deadline |
| Deterministic ordering | two reads return equal results |
| Identifier never reused | a duplicate `approval_id` raises |

Two additive `StateStore` methods, deliberately generic in the record type: the approval vocabulary
is built *on* the store, so naming it there would invert the dependency into an import cycle.

One consequence worth stating: because all approvals for a workflow share one file, timestamps must
be non-decreasing *across* approvals within that workflow. That is correct for an append-only audit
log and is covered by a test; it means a caller cannot create an approval "in the past" relative to
another approval's events.

An approvals file alone does not make a workflow appear in `list_workflow_ids` — membership is still
decided by the transition history. Tested.

## 12. WorkflowService boundary

Five operations, the smallest set the evidence supports — one to open, one to read, one to evaluate
time, one to decide, one to spend:

```python
request_approval(...)   get_approval(...)   evaluate_approval(...)
decide_approval(...)    consume_approval(...)
```

Every body is a delegation. `ApprovalService` shares the service's `StateStore`, so an approval and
the transition history it will one day gate live under one storage root and one confinement walk;
reaching it grants no ability to execute or transition anything, because `ApprovalService` holds no
provider, no lock, and no workflow session.

No workflow lifecycle verb was added — a test asserts `start`, `authorize`, `approve`, `reject`,
`resume`, `cancel`, `prepare`, `review`, `implement`, `commit`, `push`, `merge` are all still absent.
**No public CLI command was added**: the service and its tests were sufficient to validate the
boundary, so AUTO-009's D3 stays deferred. A test asserts `cli_auto.py` contains no "approval".

## 13. State-machine interaction — no workflow state was added

The directive permitted `AWAITING_APPROVAL`, `APPROVAL_TIMED_OUT`, and
`HUMAN_INTERVENTION_REQUIRED`, and preferred none if the subsystem could be built without them. It
can, so **none were added**, and the reasoning is:

1. **Nothing could produce them.** AUTO-012 implements no lifecycle, so any new state would be
   unreachable and any new edge in `ALLOWED_TRANSITIONS` untested — dead weight in the
   safety-critical core the same directive says not to refactor.
2. **Approval status belongs to the subsystem.** `ApprovalStatus` (ten values, including a
   non-terminal `HUMAN_INTERVENTION_REQUIRED`) lives in `approvals.py`, which satisfies the rule
   that workflow states must not duplicate policy logic — the policy and its statuses are in one
   place, not two.
3. **The stage that first consumes an approval has the evidence to choose correctly.** Guessing the
   states now would bind a future stage to a shape nothing has yet validated.

Consequently `WorkflowState` still has 19 members and `ALLOWED_TRANSITIONS` still 37 edges — both
asserted — and transition validation, actor validation, resume, locking, and the attempt journal are
untouched (`orchestrator/engine.py` is byte-identical to `e2b069c`).

## 14. Exact files changed

Fourteen files. **Both modified production files are purely additive: 146 insertions, 0 deletions.**

| File | Status | What |
|---|---|---|
| `agentos_workflow/approvals.py` | **new** | The whole subsystem |
| `agentos_workflow/tests/test_approvals.py` | **new** | 117 tests |
| `docs/workflow-automation/stage-prompts/AUTO-012.md` | **new** | Stage contract |
| `docs/reports/workflow-automation/AUTO-012-completion-report.md` | **new** | This report |
| `agentos_workflow/orchestrator/state_store.py` | modified (+44, −0) | `_APPROVALS_FILENAME`, `_approvals_path`, `record_approval`, `read_approvals` |
| `agentos_workflow/service.py` | modified (+102, −0) | Approval imports, `self._approvals`, five delegating operations |
| `agentos_workflow/tests/test_service.py` | modified | `APPROVED_OPERATIONS` extended by the five approval operations |
| `agentos_workflow/tests/test_results.py` | modified | One AUTO-011 surface pin generalized (§14.1) |
| `docs/workflow-automation/HUMAN_AUTHORIZATION_MODEL.md` | modified | **v1.1 → v2.0**, §1 amended, new §5a, §6 and §8 updated |
| `docs/TASK_QUEUE.md`, `docs/current_task.md`, `docs/remaining_tasks.md`, `docs/PROJECT_STATE.md`, `docs/DECISION_LOG.md`, `docs/workflow-automation/STAGE_REGISTRY.md` | modified | Registration and the governance decision |

Verified byte-identical to `e2b069c` (`git diff --stat` empty): `agentos_workflow/providers/**`,
`agentos_workflow/agents/**`, `agentos_workflow/skills/**`, `agentos_workflow/config/**`,
`agentos_workflow/cli_auto.py`, `agentos_workflow/results.py`,
`agentos_workflow/orchestrator/engine.py`, `agentos_workflow/orchestrator/lock.py`,
`agentos_workflow/tests/live/**`, `src/**`, `scripts/**`, `agentos_dashboard/**`, `pyproject.toml`,
`self-governance.yaml`.

### 14.1 Two test files were updated, and why

Three tests pinned `WorkflowService`'s surface as *exactly* five operations. This stage is
explicitly authorized to extend that surface, so those pins had to move. Both changes are disclosed
rather than quiet:

* `test_service.py` — `APPROVED_OPERATIONS` gains the five approval operations, with the comment
  extended to say what they are and that they still record no transition, take no lock, run no
  agent or provider, and mutate no repository.
* `test_results.py` — `test_the_workflow_service_surface_did_not_grow` became
  `test_the_workflow_service_operations_this_stage_relied_on_are_unchanged`, asserting the five
  AUTO-011 operations are all still present and unchanged. That is the enduring claim AUTO-011
  actually needs; "did not grow" was only correct while AUTO-011 was the newest stage.

No assertion was weakened: both files still fail if an operation is removed or renamed, and
`test_service.py` still fails on any *unapproved* addition.

## 15. Focused tests

`agentos_workflow/tests/test_approvals.py` — **117 tests, all passing.**

| Class | Tests | Covers |
|---|---|---|
| `TestPersistence` | 14 | append-only, no overwrite, restart replay, fsync, duplicate keys, ordering both ways, symlink refusal, confinement, determinism, identifier reuse |
| `TestPolicyResolution` | 13 | defaults, precedence, immutability, unknown fields, invalid enums, durations, channels, escalate_to, no-loop fallback |
| `TestInvalidation` | 12 | each checksum, unchanged validity, no re-consumption, no silent recreation, no auto-approval, no double-spend, recorded observation |
| `TestDecisions` | 10 | all three decisions, full recording, channel and approver allowlists, settled approvals, `required=False` |
| `TestCompatibility` | 10 | provider runtime, result contract, state machine, service surface, CLI, `StateStore` surface, workflow listing |
| `TestChecksums` | 10 | determinism, key-order independence, canonical `AgentRunResult`, labelling, malformed rejection, difference reporting, no secret persistence |
| `TestTimeoutActions` | 9 | all five actions, `PAUSE` resumability, bounded escalation, extension-free escalation, human decision after escalation |
| `TestEventRecords` | 8 | unknown fields, frozen, naive timestamps, per-kind shape rules, unreplayable history |
| `TestAutoApproveRequiresExplicitOptIn` | 8 | the security rule from every direction |
| `TestAuthorityBoundaries` | 8 | no agent/provider, no Git, no lock/session, no gate bypass, state binding, cross-workflow and cross-gate replay, no Telegram transport |
| `TestDeadlines` | 7 | absolute/aware, no-timeout, restart survival, laziness, not-yet-reached, idempotence, no timer dependency |
| `TestWorkflowServiceBoundary` | 3 | full lifecycle through the service, lazy evaluation, no lifecycle verb |
| `TestSnapshotIsNotRetroactive` | 3 | later config changes, no overlay reference, no channel/approver drift |

## 16. Full validation

| Command | Result |
|---|---|
| `pytest -q` | **3,469 passed**, 25 deselected (3,352 + 117) |
| `pytest -q -m live_cli -rs` | **25 passed, 0 skipped**, 3,469 deselected |
| `ruff check .` | All checks passed |
| `black --check .` | 224 files unchanged |
| `mypy --strict` | Success: no issues in **122** source files (baseline 121; +1) |
| `pre-commit run --all-files` | ruff Passed · black Passed · mypy Passed |
| `workflowctl verify` | `task-state`/`governance`/`registries`/`handover` **PASS**; `git` FAIL with exactly `["upstream_missing"]` |

`upstream_missing` is the expected pre-push finding; the branch has no remote tracking yet and
pushing is outside the stop condition. It clears at the push.

**Additional verification**

* **Wheel packaging** — `agentos_workflow/approvals.py` present, alongside `results.py`,
  `state_store.py`, `service.py`.
* **Out-of-tree imports** — `ApprovalService`, `ApprovalPolicy`, `resolve_approval_policy`,
  `ApprovalChecksums` all import cleanly from `/tmp`.
* **CLI unchanged** — six invocations byte-identical (MD5) between this branch and a clean
  `e2b069c` git worktree, which was removed afterwards.
* **No provider argv or runtime change** — `providers/**` byte-identical.
* **No live provider test change** — `tests/live/**` byte-identical.
* **No Git or GitHub mutation path added** — asserted structurally over the module's syntax tree.
* **Only AUTO-012 changes present** — `git status` shows exactly the fourteen files in §14.
* **Cleanliness** — no `TODO`, `FIXME`, `XXX`, `HACK`, `breakpoint(`, `pdb`, `xfail`,
  `pytest.mark.skip`, `pytest.skip`, or `NotImplementedError` in either new file.

## 17. Live-provider regression

```text
$ pytest -q -m live_cli -rs
25 passed, 3469 deselected in 264.96s
```

Zero skips, unchanged from AUTO-011's closing numbers, against the real installed CLIs. The live
suite file was not modified. The AUTO-010/AUTO-011 mocked suites plus `test_state_store.py` were
also run as a group: **454 passed**.

## 18. Blockers fixed

**None.** No defect blocked AUTO-012.

The one thing that *could* have blocked it was not a defect but a governance constraint — the
single-human-gate property in `HUMAN_AUTHORIZATION_MODEL.md`. It was resolved by obtaining and
recording the explicit Human Owner decision the document's own §8 demands (§2), not by working
around it and not by treating an approval gate as "not really a human gate".

## 19. Deferred findings

Recorded, classified, not implemented. No GOV stage was created for any of them.

### D-11 — `list_workflow_ids` cannot see an approvals-only workflow — `RECOMMENDED`

Workflow membership is decided by the presence of `transitions.jsonl`. A workflow with approvals but
no transitions — reachable today, since `request_approval` does not require a transition history —
is invisible to `list_workflow_ids` and therefore to `workflowctl auto list`. **Impact:** an
operator listing workflows would not see one that exists only as an approval. This is arguably
correct for AUTO-012 (an approval is not a workflow) and arguably wrong for the stage that wires
approvals into a lifecycle. **Defer to:** that stage, which will know which reading is right.
Deliberately not decided here, and a test pins the current behaviour so the change is visible when it
happens.

### D-12 — approvals share one per-workflow file, so timestamps must be non-decreasing across them — `OPTIONAL`

Because all approvals for a workflow append to one `approvals.jsonl`, opening approval B with a
timestamp earlier than approval A's last event is refused. Real clocks move forward, so this is a
non-issue in production, but it makes some test orderings and any future backfill awkward.
**Impact:** ordering constraint across otherwise-independent approvals. **Defer to:** a stage that
demonstrates a real need for per-approval files; splitting them now would trade one shared lock and
one ordered history for many, which is the worse default for an audit log.

### D-13 — the escalation fallback cannot itself be a *second* escalation target set — `OPTIONAL`

`escalate_to` names one set of escalation recipients and the fallback is a plain `TimeoutAction`;
there is no way to express "escalate to leads, then to directors, then fail". This is a deliberate
bound (§6), not an oversight, but it is a real expressiveness limit. **Impact:** multi-tier
escalation is not configurable. **Defer to:** a stage with a real requirement for it, which must
also bring its own bound on depth.

### Earlier findings — unchanged

**AUTO-011's D-8, D-9, D-10** and **AUTO-010's D-3 through D-6** and **AUTO-009's D1–D6** are all
confirmed untouched; none was fixed. AUTO-009's **D3** in particular remains deferred because no CLI
command was added, so it never became a blocker — the service boundary was validated by tests, which
the directive preferred.

## 20. Confirmation that no workflow mode was implemented

| Prohibited | Evidence |
|---|---|
| Preparation / Reviewer / Implementer Mode | no such module, class, or command; asserted |
| Claude / Codex execution changes, provider-runtime changes | `providers/**` byte-identical; `runtime.__all__` asserted unchanged |
| Canonical result changes | `results.py` byte-identical; `AgentRunResult` still 19 fields, asserted |
| Codex direct correction, Claude–Codex coordination | absent |
| Task scheduling, daemon, Telegram bot | no dependency, module, thread, timer, or network call — asserted over the syntax tree; `TELEGRAM` is a policy enum value only, and no other non-test module in `agentos_workflow` mentions Telegram |
| Workflow orchestration, lifecycle verbs | `WorkflowService` has none of the twelve, asserted |
| Git commit/push automation, PR creation, CI polling, merge, branch deletion | no Git or GitHub call in the new code; asserted structurally |
| Governance closeout automation, shell-script retirement | `scripts/` byte-identical |
| Workflow state transitions modified | `orchestrator/engine.py` byte-identical; 19 states, 37 edges, asserted |
| Git/GitHub skill registration modified | `skills/` byte-identical |
| Existing `workflowctl auto` behaviour/output | six invocations byte-identical to a clean `e2b069c` worktree |
| **AUTO-013 or any successor** | absent |

## 21. Proposed commit and publication plan

Nothing was committed, pushed, merged, or opened as a pull request. The complete diff is in the
working tree on `feature/auto-012-approval-policy` for Human Owner inspection.

Recommended commit message:

```text
feat(approvals): add the configurable approval policy, persistence, and invalidation subsystem (AUTO-012)
```

Proposed closeout sequence, **all of it requiring explicit Human Owner authorization**:

1. Human Owner reviews this report and the diff, with particular attention to §2 (the
   `HUMAN_AUTHORIZATION_MODEL.md` v2.0 §5a governance decision — the most consequential change in
   this stage), §13 (no workflow state added, and why), §14.1 (two test files updated), and §19
   (three new deferred findings, none fixed).
2. On approval, the closeout commit additionally updates `docs/CHANGELOG.md`,
   `docs/workflow-automation/CHANGELOG.md`, `handover/PROJECT_HANDOVER.md`, and
   `handover/PROJECT_CHECKSUM.md`, and moves the registry row `IN_PROGRESS → COMPLETE` with the task
   status `Current → Done`.
3. Publication: push `feature/auto-012-approval-policy`; PR and merge only if separately authorized.
   The `upstream_missing` finding clears at the push.
4. AUTO-013 remains unauthorized and must not begin.

**Confirmation:** no commit, push, merge, pull request, branch deletion, stash operation, or
successor-stage work was performed by this session. The temporary `e2b069c` worktree created for the
CLI byte-comparison was removed; `git worktree list` shows only the primary checkout.

---

# 22. Approval, closure, and publication (2026-08-01, append-only)

Sections 0–21 above are unchanged. This section records the Human Owner's approval, the closeout
performed under it, and the publication that followed.

## 22.1 Approval

The Human Owner approved AUTO-012 and, in the same directive, authorized publication — opening a
pull request for `feature/auto-012-approval-policy` against `main`, merging it under the
repository's established merge-commit policy, and retaining the branch.

## 22.2 A discrepancy in the publication directive, and how it was resolved

The directive stated that the pull request "must contain exactly the existing AUTO-012
implementation commit(s)" and instructed that no files be modified. **No such commit existed.**
§21's stop condition — imposed by the previous directive and observed in full — explicitly withheld
the implementation/closeout commit, so at the moment approval arrived the branch was at `e2b069c`
with fifteen uncommitted files and nothing to publish.

Publication therefore required first creating the commit that §21 step 2 describes and that
approval is the stated trigger for. That is what was done: one implementation-plus-closeout commit,
following the same pattern AUTO-010 and AUTO-011 used, containing the already-approved
implementation plus the governance closeout §21 step 2 enumerates. No implementation file was
reopened, no scope changed, and no deferred finding was fixed. The files the closeout touched are
listed in §22.3 and are all governance records.

This is recorded rather than glossed because the directive's premise was factually wrong, and
acting on it silently would have hidden that.

## 22.3 Closeout

| Document | Change |
|---|---|
| `docs/TASK_QUEUE.md` | `Status: Current -> Done`, closure paragraph appended |
| `docs/current_task.md` | Rewritten to the empty-`Current` state |
| `docs/remaining_tasks.md` | AUTO-012 recorded as approved and closed |
| `docs/PROJECT_STATE.md` | `Status: Current -> Done`, closure paragraph appended |
| `docs/workflow-automation/STAGE_REGISTRY.md` | Row `IN_PROGRESS -> COMPLETE`; approval/closure/publication log entry |
| `docs/CHANGELOG.md` | AUTO-012 under Added, and the `HUMAN_AUTHORIZATION_MODEL.md` v2.0 amendment under Changed |
| `docs/workflow-automation/CHANGELOG.md` | AUTO-012 implementation entry; version 2.19 -> 2.20 |
| `handover/PROJECT_HANDOVER.md` | AUTO-012 section |
| `handover/PROJECT_CHECKSUM.md` | Regenerated for the new handover bytes |

`workflowctl verify` after closeout: `task-state` **0 Current, 45 Done, 6 Planned**; `governance`,
`registries` (22 stages), and `handover` all PASS.

## 22.4 Provenance

The approval was given in conversation and the closeout performed **manually**, not through
`scripts/workflow-approve.sh`, whose two interactive `APPROVE` confirmations an agent must never
supply. No scripted confirmations were typed and none were supplied by this session.

## 22.5 Stop condition

Publication only. **AUTO-013 was not begun**, no deferred finding was implemented, and no scope was
changed.
