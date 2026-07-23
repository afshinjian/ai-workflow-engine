# DASH-007 — Stage Registry and Prompt Generation

| Field | Value |
|---|---|
| **Stage** | DASH-007 · Role: Dashboard implementation session |
| **Branch** | `feature/dash-007-prompt-generation` |
| **Commit message** | `feat(dashboard): add stage registry and gated prompt generation (DASH-007)` |
| **Report** | `docs/reports/agentos-dashboard/STAGE-07-completion.md` |
| **Status/Version** | Draft · 1.0 |

Apply the Standard Stage Protocol in `README.md` in full.

## Canonical Prompt

You are the **Dashboard implementation session** executing **DASH-007 — Stage registry and
prompt generation**. Preconditions: DASH-006 `COMPLETE`; recorded authorization; branch
`feature/dash-007-prompt-generation`.

**Allowed**: create `agentos_dashboard/prompt_templates/**`, prompt/stage services, routes
(EP-13, EP-14, EP-21), templates (PG-04), tests; SSP documentation updates.

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

**Acceptance**: generating a prompt for a stage whose predecessor is not COMPLETE is refused;
export bytes hash-match the preview.

Write the report, recommend the commit message above, then STOP per SSP.

## Stage-Specific Notes

Reference: DR-040..DR-043; SC-13..SC-20; `../STAGE_REGISTRY.md` §2 rule 10. The engine's
prompt subsystem (`src/ai_workflow_engine/prompt/`) is prior art for deterministic
hash-recorded prompt generation; never imported or modified.
