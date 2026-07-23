# Decision Log

Architectural decisions for `ai-workflow-engine`, newest first. Each entry records what was
decided, what alternatives were considered, and why — so a fresh session can understand *why*
the code looks the way it does, not just what it does.

## 2026-07-23 — DASH-001 closed out; AgentOS Workflow Automation program (AUTO) enrolled with AUTO-001 current

**Decision:** Before starting AUTO-001, the AUTO-001 stage prompt's own precondition check
("no conflicting task is active") found that DASH-001 was still recorded `Status: Current` in
`docs/TASK_QUEUE.md` and its mirrors, even though its PR (#1, `5f82996`) had already merged into
`main` — the formal flip-to-`Done` closeout step had not yet run. `self-governance.yaml` sets
`workflow.maximum_current_tasks: 1`, enforced by `workflowctl check-task-state`, so starting a
second `Current` task would have broken that invariant. Presented with the conflict, the Human
Owner chose "close out DASH-001 first, then proceed with AUTO-001." DASH-001 was flipped to
`Done` in `docs/TASK_QUEUE.md`, `docs/current_task.md`, `docs/remaining_tasks.md`, and
`docs/PROJECT_STATE.md` (prose only; the `Current Version:` fact line untouched), and the new
**AgentOS Workflow Automation program** (AUTO-001..AUTO-007, entry point
`docs/workflow-automation/README.md`) was enrolled in the same edit: AUTO-001 as the sole
`Current` task and AUTO-002..AUTO-007 as `Planned`, mirroring exactly how the DASH program was
enrolled at DASH-001. `workflowctl check-task-state --config self-governance.yaml` re-run after
the edit to confirm exactly 1 `Current` task.

**Alternatives considered:** (a) Leaving DASH-001 marked `Current` and treating AUTO-001 as
exempt from `docs/TASK_QUEUE.md` tracking, since AUTO-001's own file scope
(`docs/workflow-automation/`) never overlaps DASH-001's — rejected: this repository's
`maximum_current_tasks: 1` rule is a whole-repository invariant, not a per-program one (DASH-001's
own stage prompt encoded the same precondition: "no other `Current` task anywhere in
`docs/TASK_QUEUE.md`"), and a program-private state file (the option taken for the read-only
`docs/implementation/orchestration/` ORCH package) was rejected for DASH-001 on the grounds that
"DASH stages are ordinary tasks and belong under the existing `check-task-state` discipline" —
the same reasoning applies to AUTO. (b) Stopping entirely and asking the Human Owner to close out
DASH-001 in a separate session first — rejected as the Human Owner's explicit choice, given they
authorized the closeout in the same turn as being asked. (c) Leaving AUTO-002..AUTO-007
unenrolled (only adding AUTO-001) since the AUTO-001 authorization text did not explicitly
request `TASK_QUEUE.md` changes — rejected for internal consistency: the DASH precedent enrolls a
program's full known roadmap as `Planned` at its first authorized stage, and AUTO-001's own
required deliverables already define all seven stages' scope in
`docs/workflow-automation/stage-prompts/`.

**Rationale:** Recorded here because `docs/AGENT_PROTOCOL.md` requires governance changes to be
logged with their rationale, and because promotion of AUTO-001 to `Current` needs the recorded
owner approval (`self-governance.yaml` `require_designer_approval_for_promotion`). The Human
Owner's 2026-07-23 authorization ("I authorize AUTO-001.") plus the explicit "close out DASH-001
first" choice made when presented with the conflict are that approval for both actions. This
entry, and the `docs/TASK_QUEUE.md`/mirror edits it describes, are governance/task-state changes
required by repository governance to satisfy AUTO-001's own preconditions — not part of
AUTO-001's documentation deliverable set, which remains scoped to `docs/workflow-automation/`.
No commit, push, PR, merge, or branch deletion was performed for either the closeout or the
AUTO-001 work.

## 2026-07-23 — AgentOS Dashboard program enrolled; DASH-001 recovered from a mis-targeted execution

**Decision:** Adopt the ten-stage AgentOS Dashboard program (DASH-001..DASH-010) as post-1.0
work, enrolled in `docs/TASK_QUEUE.md` with DASH-001 as the sole `Current` task, and complete
DASH-001 by **recovery**: the first execution was mistakenly performed in a different
repository (`amozesh_konkur`), and its documentation output — copied here as untracked
candidate material — was rewritten in place so every assumption matches this repository's
actual governance (authority chain per `docs/AGENT_PROTOCOL.md` + `self-governance.yaml`;
Current/Planned/Done task lifecycle with `workflowctl` mirror checks; branches from `main`;
handover pair verified by `workflowctl check-handover`; upstream check instead of a baseline
tag; this single decision log; the orchestration package treated as read-only observed state).
The program is documentation-first, and the dashboard itself will be a separate top-level
package (`agentos_dashboard/`) with read-only repository access — it never gains commit, push,
or governance-mutation authority.

**Alternatives considered:** (a) Discarding the copied material and re-planning from scratch —
rejected as wasteful: the product/security/test design is repository-agnostic and sound; only
its governance bindings were wrong. (b) Keeping the copied files verbatim and reconciling later
— rejected: they cited nonexistent files (`CONSTITUTION.md`, `governance/`, root `AGENTS.md`,
`scripts/create_handover.py`), a nonexistent base branch (`recovery/project-baseline`), a
nonexistent baseline tag, foreign decision IDs (CTO-xxx/D-xxx/ISS-xxx), and a false "zero new
dependencies (FastAPI)" claim, so leaving them in place would have created a second, false
authority. (c) Enrolling the DASH stages outside `docs/TASK_QUEUE.md` in a program-private
state file, like the ORCH package — rejected: unlike ORCH (a reviewed design package with its
own session protocol), DASH stages are ordinary tasks and belong under the existing
`check-task-state` discipline.

**Rationale:** Recorded here because `docs/AGENT_PROTOCOL.md` requires governance changes to be
logged with their rationale, and because promotion of DASH-001 to `Current` needs the recorded
owner approval (`self-governance.yaml` `require_designer_approval_for_promotion`). The Human
Owner's 2026-07-23 recovery directive ("I authorize recovery and correct execution of DASH-001
in the ai-workflow-engine repository") is that approval. The known dependency gap (this
repository pins no web framework) is deliberately not decided here; it is held open as OD-D9 in
`docs/agentos-dashboard/OPEN_QUESTIONS.md` and blocks DASH-004, not DASH-001..003. Full
correction inventory: `docs/agentos-dashboard/DECISIONS.md` DD-03 and
`docs/reports/agentos-dashboard/DASH-001-recovery-report.md`.

## 2026-07-18 — `state` CLI emits a deterministic bespoke payload, not a timestamped CheckResult (T-302)

**Decision:** `workflowctl state show|next|record` success output is a purpose-built canonical-JSON
object (`{status, command, ...}`) written Rich-free to stdout, rather than a `CheckResult` routed
through `render_json`. Failures carry `{status: "FAIL", command, finding: {code, message}}` and
exit 1; success exits 0; usage/unexpected errors exit 2 via `_protected`.

**Alternatives considered:** Emitting a `CheckResult(check_name="state", ...)` exactly as
`docs/milestone-3-plan.md` loosely worded it ("CheckResult-style PASS"). Rejected because
`CheckResult` carries a wall-clock `timestamp`, which would make identical state queries produce
different bytes — at odds with this project's determinism principle and with the timestamp-free
canonical outputs used everywhere else in the workflow layer. `show`/`next` are also queries, not
pass/fail checks, so the `CheckResult` shape fits them poorly.

**Rationale:** The Milestone 2 prompt CLI set the precedent of a bespoke success payload
(`PromptSuccess`) with `CheckResult` reserved for validation *failures*; the state CLI follows the
same pattern. Recorded here because it is a conscious, reviewer-flagged (T-302 review, finding N1)
deviation from the plan's literal wording, kept for a determinism reason rather than an oversight.
`docs/current_task.md`'s T-302 acceptance criteria describe the CLI contract without `check_name`,
consistent with this decision.

## 2026-07-18 — Milestone 4 writer is typed-methods-only; push gate reads live, not recorded (T-401)

**Decision:** In the `docs/milestone-4-plan.md` contracts, (a) the writable-Git surface
`GitWriter` exposes only typed methods (`stage_paths`, `unstage_paths`, `commit`, `push`,
`apply_check`, `apply_patch`), each emitting one fixed argv template — there is no method that
runs a caller-supplied argv, so dangerous forms (force push, remote-branch deletion, `reset`,
`commit --amend`/`-a`, `add -A`) are structurally unreachable rather than blocked by a denylist;
and (b) the push gate reads live Git state and decides on `behind == 0` computed by the exact
Milestone 2 `rev-list --left-right --count @{upstream}...HEAD` command, without carrying
recorded ahead/behind counts in the `PushApproval`.

**Alternatives considered (all from round-1 plan-review findings):** an allowlist that runs
arbitrary argv and scans it for denylisted tokens (rejected — B2/B3: it both false-rejects
operand data like a commit message containing "reset" and misses real dangers like
`push --delete`); carrying recorded ahead/behind in the approval to mirror M-2's cross-check
(rejected — B5: M-2 needed that only because its prompt was a snapshot that could drift from
execution; the M-4 gate reads live state, so the live computation is itself authoritative).

**Rationale:** An independent round-1 plan review REJECTED the first draft with five blocking
findings; the typed-writer redesign resolves three of them (B1 self-contradictory unstage,
B2 operand-scanning, B3 non-airtight allowlist) at once and is a stronger safety posture for the
project's first writable-Git milestone. The live-read push gate (B5) and the read-only `GitClient`
extension using already-allowlisted forms (B4) are the other two. Recorded here because these are
genuine safety-architecture choices, not typo fixes. Full history in `docs/milestone-4-plan.md`'s
status and disposition sections.

## 2026-07-18 — `AgentRunRecord` stores the agent's stdout bytes, not a re-parsed `AgentReport` (T-305)

**Decision:** The stored `AgentRunRecord` does not carry a structured `AgentReport` field. The
agent's report is preserved byte-exactly as `stdout_b64` under a committed `stdout_sha256`, and
its material claims (verdict, changed-path judgement) live in the `verification` snapshot's
`evidence`. The `docs/milestone-3-plan.md` "Run artifacts" wording listed "the full AgentReport"
as a member.

**Alternatives considered:** Adding a parsed `AgentReport` field alongside the raw stdout
(rejected — it duplicates data already recoverable from `stdout_b64`, and a separately-stored
parse could drift from the bytes that were actually digested, weakening tamper-evidence);
storing only the report and discarding raw stdout (rejected — then non-report stdout noise and
the exact bytes an operator saw would be lost, and a malformed-report run would have nothing to
store).

**Rationale:** Storing the exact bytes under a digest is strictly more tamper-evident than a
re-parsed copy, and it also covers the failure cases where there is no valid report at all
(`agent_report_invalid`, timeout). Downstream Milestone 4 consumes the verified verdict and
patch, both already present. Recorded per the T-305 review's non-blocking finding N3 so a future
session sees this as a conscious choice, not an omission.

## 2026-07-18 — Machine-readable CLI output must bypass Rich entirely (T-104)

**Decision:** All of `workflowctl`'s machine-readable stdout — every `--output json` payload and
the `version` string — is written as plain bytes via a `_write_stdout` helper, never through
Rich's `Console`.

**Alternatives considered:** Configuring the Rich `Console` with `no_color=True` /
`force_terminal=False` (rejected — `FORCE_COLOR` overrides those, and Rich still owns
soft-wrapping and other transforms); leaving it and documenting "unset FORCE_COLOR" (rejected —
a governance tool whose JSON is meant for CI consumption must not emit invalid JSON under a
common env var).

**Rationale:** Discovered during T-301's round-2 plan review: with `FORCE_COLOR` set, Rich
injected ANSI codes into `verify --output json`, producing unparseable JSON and violating the
stable 1.0 schema contract in `docs/architecture.md`. This is the same Rich-corruption class the
2026-07-17 `_protected` decision fixed for stderr; T-104 extends the same bytes-not-Rich
principle to the stdout machine paths that were missed. Human output and the Rich summary tables
are unchanged. Also hardens the `conda run ... pytest` verification path Milestone 3 re-executes.

## 2026-07-17 — Milestone 3 plan: two boundary decisions surfaced by round-1 plan review

**Decision:** In the `docs/milestone-3-plan.md` contracts, (a) Milestone 3 makes **no** change
to the target repository at all — a scoped-write agent's output is captured as a verified patch
artifact and applying it to the working tree is deferred to Milestone 4 (the earlier `agent
apply` verb was cut); and (b) `agent run` requires a **clean** target working tree at the
recorded HEAD before running, so the committed-HEAD sandbox faithfully reproduces the prompt's
working-tree-derived evidence.

**Alternatives considered:** Keeping `agent apply` in M-3 (rejected — it sat adjacent to
Milestone 4's controlled-change scope and added a third, un-allowlisted writable-Git surface on
the real repository); building the sandbox from the dirty working tree instead of committed HEAD
(rejected — it would make run inputs non-deterministic and diverge from the governance principle
that committed state is the source of truth).

**Rationale:** An independent round-1 plan review (fresh session, no memory of the drafting)
returned REJECTED with three blocking findings (missing `renderer.py` in the file list;
unspecified/non-deterministic verification-command re-execution; a task-ID slug collision hole)
and two substantive ones (sandbox-vs-dirty-tree tension; an unverifiable lossy-stderr digest).
All were remediated in a round-2 revision; the two items above were genuine scope/architecture
choices worth recording, not mere typo fixes. This is the same independent-review discipline
that caught a real regression in Milestone 2 (see the 2026-07-16 entry).

## 2026-07-17 — Master roadmap to 1.0 approved; local-commit and CI decisions

**Decision:** The human approved `docs/MASTER_ROADMAP.md` as written: Stage 0 (GOV-1 closeout,
documentation sync, plus a lightweight CI task the human opted into), then Milestone 3, then
Milestone 4, then the 1.0.0 release. The human additionally approved creating **one local git
commit** before Milestone 3 begins, to preserve the validated M-2 + GOV-1 working tree —
explicitly no push and no remote branch. Versioning follows Semantic Versioning; intermediate
versions are recommended by the engine's maintainer session at each milestone closeout
(suggested 0.2.0 after M-3, 0.3.0 after M-4).

**Alternatives considered:** Leaving the working tree uncommitted until 1.0 (rejected — largest
recoverability risk in the gap analysis); skipping CI (rejected by the human — a minimal
workflow improves reliability at negligible complexity).

**Rationale:** Recorded here because commit approval and roadmap approval are exactly the class
of human decisions `docs/AGENT_PROTOCOL.md` says must not be inferred from prior context by a
future session.

## 2026-07-17 — Self-governance: extend the existing engine rather than build a parallel system

**Decision:** Point this project's own tooling at its own repository (new governance documents
+ `self-governance.yaml` config), rather than building a second, differently-shaped governance
system under `docs/governance/` with new file names, a new task-lifecycle model, and new CLI
verbs.

**Alternatives considered:** A from-scratch system with an 8-file `docs/governance/` tree, a
7-state task lifecycle (`BACKLOG → PLANNED → APPROVED → IMPLEMENTING → VALIDATING → COMPLETED →
HANDED_OVER`) with timestamped/evidenced transitions, and new `governance status/validate/
handover/closeout` CLI commands running alongside the existing `check-*`/`verify`/`prompt`
surface.

**Rationale:** The existing `EngineConfig` schema, `governance`/`handover` validators, and
`prompt` module already cover nearly everything a from-scratch system would provide, under
different names, and had already been through two full milestone review cycles. Building a
parallel system would create two incompatible vocabularies describing the same repository
(`Current/Done/Planned` vs. a 7-state machine; `check-governance` vs. `governance validate`).
The genuinely new task-lifecycle/multi-agent-execution/push-gate capabilities the alternative
implied were already scoped as Milestones 3 and 4 in `docs/milestones.md` — pulling them forward
under new names would fork the roadmap rather than extend it. Full reasoning:
[`docs/GOVERNANCE_AUDIT.md`](GOVERNANCE_AUDIT.md).

## 2026-07-17 — `_protected` CLI error output bypasses Rich's `Console` entirely

**Decision:** `_protected()` in `src/ai_workflow_engine/cli.py` writes `ERROR: <message>\n`
directly to `sys.stderr` rather than through Rich's `Console.print`.

**Alternatives considered:** `Console.print(..., markup=False)` (insufficient — Rich's automatic
repr-highlighter still bolds bracketed substrings with ANSI codes even with markup parsing off);
`Console.print(..., markup=False, highlight=False)` (insufficient — Rich still soft-wraps text
to the console's line width, splicing a spurious newline into any message near or past ~80
columns, even when not attached to a TTY).

**Rationale:** Milestone 2's plan requires `_protected`'s stderr output to be the exact bytes
`ERROR: <message>` in every mode. Two independent fresh implementation-reviews each found one of
the above defects in turn; bypassing Rich's console formatting layer entirely was the only fix
that satisfied the byte-exact contract for arbitrary message content (brackets, tabs, length).
This also silently fixed the same latent defect for every pre-existing Milestone 1 command that
shares `_protected`.

## 2026-07-16 — Three-round independent fresh-review discipline for Milestone 2

**Decision:** After every remediation pass, dispatch a new reviewer with *no memory of the prior
session's fixes* rather than self-certifying that a fix resolved a prior review's findings.

**Rationale:** A reviewer that already knows "these four things were fixed" is anchored on that
frame and is structurally prone to missing anything new. Milestone 2 went through three such
rounds; round 2 caught a real regression-adjacent bug (the wrapping defect above) that round 1's
own fix had introduced by not going far enough. Self-certification would have missed it.

## Milestone 2 plan — Prompt generation is read-only and stateless

**Decision:** `ai_workflow_engine.prompt` renders, validates, and optionally stores a prompt for
an operator-specified stage. It does not persist workflow state, record verdicts, enforce stage
transitions, or compute the next stage automatically.

**Alternatives considered:** Coupling prompt rendering to a live workflow state machine tracking
which stage a task is "in."

**Rationale:** No state machine had been designed yet at the time Milestone 2 was scoped.
Building one implicitly, as a side effect of prompt generation, would have made Milestone 2's
correctness depend on an undesigned, untested state model. Deferred explicitly to Milestone 3;
see `docs/milestone-2-plan.md`.

## Milestone 2 plan — Prompt identity is a pinned, canonical, byte-exact hash

**Decision:** Every rendered prompt's identity (`prompt_id`) is the first 16 hex characters of
the SHA-256 of a canonical JSON serialization of its complete context (config, git status, task
snapshot, check evidence, template content/version/digest — everything). Canonical JSON uses
NFC-normalized, sorted-key, no-float, signed-64-bit-int-only serialization with a golden test
vector. All seven built-in templates are pinned to fixed byte counts and SHA-256 digests.

**Rationale:** Free-form or non-deterministic prompt generation would make two renders of "the
same" prompt potentially differ, breaking the atomic no-clobber storage protocol's core
assumption (two writers at the same address must be writing the same bytes) and making stored
prompts unverifiable without the exact code version that produced them. Byte-exact canonical
identity makes verification independent of the installed template registry.

## Milestone 1 — Governance/task-state parsing is conservative, with one authoritative source

**Decision:** Task states come only from explicit Markdown headings (`## TASK-ID` + a `Status:`
field) or table rows containing a task-ID-shaped token and a status word — no fuzzy inference.
Exactly one configured document (`governance.task_queue`) is authoritative; every other
configured document is a mirror that must agree with it, checked by `check_task_state` and
`check_governance`.

**Rationale:** A governance tool whose job is to catch documentation drift must not itself
introduce ambiguity about what a document says. Treating one document as authoritative and
everything else as a verified mirror turns "these two docs quietly disagree" into a detectable
`FAIL` instead of a silent inconsistency an agent (or a human) could act on incorrectly.
