# Decision Log

Architectural decisions for `ai-workflow-engine`, newest first. Each entry records what was
decided, what alternatives were considered, and why — so a fresh session can understand *why*
the code looks the way it does, not just what it does.

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
