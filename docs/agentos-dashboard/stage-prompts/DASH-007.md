# DASH-007 — Stage Registry and Prompt Generation

| Field | Value |
|---|---|
| **Stage** | DASH-007 · Role: Dashboard implementation session |
| **Branch** | `feature/dash-007-prompt-generation` |
| **Commit message** | `feat(dashboard): add stage registry and gated prompt generation (DASH-007)` |
| **Report** | `docs/reports/agentos-dashboard/STAGE-07-completion.md` |
| **Status/Version** | Draft · 1.1 |

Apply the Standard Stage Protocol in `README.md` in full.

## Canonical Prompt

You are the **Dashboard implementation session** executing **DASH-007 — Stage registry and
prompt generation**. Preconditions: DASH-006 `COMPLETE`; recorded authorization; branch
`feature/dash-007-prompt-generation`.

**Allowed**: create `agentos_dashboard/prompt_templates/**`, prompt/stage/governance services,
routes (EP-13, EP-14, EP-21, **EP-07, EP-08**), templates (PG-04, **PG-08**), tests; SSP
documentation updates.

**Build**: stage-registry loader reading `docs/agentos-dashboard/STAGE_REGISTRY.md` and the
`docs/agentos-dashboard/stage-prompts/` directory, cross-checked against a coded schema
(divergence = finding); precondition engine (owner authorization recorded, predecessor
COMPLETE, clean tree, correct branch pattern, sole-active invariant, blocking OD-D# resolved);
prompt renderer substituting live repo facts into the tracked SSP + stage templates; SHA-256
hash of every rendered prompt (the engine's `workflowctl prompt` canonical-hash discipline is
the model); preview/copy/export-to-file endpoints; refusal path returning itemized unmet
preconditions (422) and auditing both success and refusal (in-memory audit until DASH-008).
Prompt text must embed quoted repository content only inside delimited data blocks marked as
data (SC-20).

**Build — Governance browser/search (DR-090, DR-091; EP-07, EP-08; PG-08), added by PLAN-001
(documentation only — not implemented by this correction):** a strictly read-only Governance
service and `/governance` page over a fixed, coded allowlist of governance/orchestration
documents (`README.md`, `self-governance.yaml`, `docs/AGENT_PROTOCOL.md`, `docs/CONTEXT.md`, the
governance mirrors, `docs/DECISION_LOG.md`, `docs/GOVERNANCE_AUDIT.md`, and the orchestration
package documents — the exact DR-090 list). Each allowlisted document has a stable identifier
independent of filesystem layout; the document list and detail (EP-07) render the rendered
Markdown view with a raw-source fallback where rendering fails, an authority label (e.g.
authoritative mirror vs. informational), in-page anchors, and repository-relative cross-reference
resolution scoped to the same allowlist. Full-text search (EP-08) is bounded: query length capped
at `q <= 200` chars (matching `../API_SPEC.md` EP-08), a bounded result count, and escaped output
(SC-04). An unknown document identifier returns a typed 404; malformed document content degrades
to the raw escaped fallback plus a finding (SC-34), never a crash; any traversal-shaped input
(path separators, `..`, an identifier outside the fixed allowlist) is refused outright, the same
posture `core/paths.py` already enforces elsewhere in this package. This is **not** an arbitrary
repository browser: no path outside the fixed allowlist is ever reachable, there is no arbitrary
filesystem access, no database, no search index, no dependency on DASH-008's persistence layer,
no governance-document mutation, no agent execution, and no Git mutation — zero repository writes.
Baseline security for this surface (escaping, allowlist enforcement, traversal refusal, query
bounds) is this stage's own responsibility; DASH-009 separately owns the mandatory independent
adversarial security reconciliation across the whole dashboard, including this surface, and is not
duplicated or pre-empted here.

**Acceptance**: generating a prompt for a stage whose predecessor is not COMPLETE is refused;
export bytes hash-match the preview. Governance browser/search: an unknown document identifier is
refused (404), a traversal-shaped identifier or query is refused without touching the filesystem
outside the allowlist, a `q` over 200 chars is refused, and a search against hostile
(script-injection-shaped) document content renders as inert escaped text.

Write the report, recommend the commit message above, then STOP per SSP.

## Stage-Specific Notes

Reference: DR-040..DR-043, **DR-090, DR-091**; SC-13..SC-20; **EP-07, EP-08; PG-08**;
`../STAGE_REGISTRY.md` §2 rule 10. The engine's prompt subsystem
(`src/ai_workflow_engine/prompt/`) is prior art for deterministic hash-recorded prompt
generation; never imported or modified. The Governance browser/search clause above was added by
PLAN-001 (2026-08-10, governance/documentation-only correction) as a **contract amendment only**
— no code for it exists yet and none was written by that correction; it is scoped for this
stage's own future authorized implementation session.
