# Stage Prompts — Index and Standard Stage Protocol

| Field | Value |
|---|---|
| **Title** | Stage Prompts — Index and Standard Stage Protocol |
| **Purpose** | Directory index for the canonical DASH stage prompts and the sole canonical home of the Standard Stage Protocol (SSP). |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Documentation & Governance session · Human Owner (approval) |
| **Dependencies** | `../MASTER_PLAN.md`; `../STAGE_REGISTRY.md` |
| **Related Documents** | `DASH-001.md` … `DASH-010.md`; `../STAGE_REPORT_TEMPLATE.md` |

## Purpose of This Directory

Each `DASH-00X.md` file contains the canonical implementation prompt for exactly one stage,
plus stage-specific notes. Prompts are executed only under the SSP below and only after the
authorization procedure in `../STAGE_REGISTRY.md` §2.

## Standard Stage Protocol (SSP)

**SSP — mandatory for every DASH stage.** Act only in the role assigned to this stage. Before
any change: read `docs/AGENT_PROTOCOL.md`, `docs/CONTEXT.md`, `self-governance.yaml`,
`docs/PROJECT_STATE.md`, `docs/current_task.md`, `docs/TASK_QUEUE.md` (DASH section), and
`docs/agentos-dashboard/MASTER_PLAN.md`. Confirm the active stage is exactly this one and its
status is AUTHORIZED in `docs/agentos-dashboard/STAGE_REGISTRY.md`; verify all preconditions;
verify you are on the stage's named branch created from a clean `main`; verify `git status` is
clean before starting. Implement ONLY this stage; refuse unrelated work, even if discovered
(record it in the stage report and, where it needs an owner decision, as a new entry in
`../OPEN_QUESTIONS.md` instead). Stay strictly inside the stage's allowed files; treat `src/`,
`tests/`, `scripts/`, `examples/`, `pyproject.toml`, `.pre-commit-config.yaml`,
`self-governance.yaml`, `docs/implementation/orchestration/**`, `handover/**`, and all engine
behavior as forbidden unless the stage contract explicitly grants a path; the engine's behavior
and its default `pytest` collection (`testpaths=["tests"]`) must be provably unchanged. Add or
update tests for everything you build. Then run and record: focused stage tests;
`pytest agentos_dashboard/tests` (from DASH-002 on); `python -m pytest tests --collect-only -q`
(regression — collection count unchanged) and `pytest tests` (green); `ruff check .`;
`black --check .`; `mypy agentos_dashboard` (from DASH-002 on);
`pre-commit run --all-files` — warning: this repository's hooks auto-fix (`ruff --fix`,
`ruff-format`); if a hook mutates any file outside the stage's allowed list (notably the
frozen evidence scripts under `docs/implementation/orchestration/**`), restore those files
byte-exactly to HEAD and record the incident in the report, and identify any pre-existing
hook failure at HEAD as pre-existing rather than fixing it out of scope; `git diff --check`;
`workflowctl verify --config self-governance.yaml` (identifying any pre-existing failure as
pre-existing); a changed-file scope audit against the allowed list; and the stage's named
security checks. Write/update `docs/reports/agentos-dashboard/STAGE-XX-completion.md` using the
official template: list every created file, every modified file, every validation command with
its exact result, unresolved risks, deviations from plan, and a per-acceptance-criterion
PASS/FAIL statement. Recommend a commit message (do not commit). Then STOP: do not begin,
select, or prepare the next stage; do not commit, push, merge, tag, rename or delete branches,
or alter Git history — commit and push always require explicit per-invocation human approval
(`docs/AGENT_PROTOCOL.md`); do not promote any task.

## Prompt Usage Rules

1. A prompt may be executed only after the Human Owner's written authorization is recorded in
   the stage's task record and `../STAGE_REGISTRY.md` §4.
2. Prompts are applied verbatim with the SSP; the SSP is applied by reference and is never
   duplicated into stage files.
3. Live-fact substitution (see Placeholders) is performed by the DASH-007 generation engine
   once it exists; before then, the operator substitutes placeholders manually.
4. Executing any prompt out of order, or while another stage is active, is a governance
   violation (`../STAGE_REGISTRY.md` §2 rule 10).

## Naming Conventions

Files are `DASH-00X.md`, matching the stage ID; IDs are immutable. Reports are
`STAGE-XX-completion.md` under `docs/reports/agentos-dashboard/`.

## Stage Ordering

DASH-001 → DASH-010, strictly sequential, one stage at a time, each independently authorized.
Completion of a stage never authorizes its successor.

## Placeholder Substitution

`{{branch}}` current branch · `{{head_sha}}` current HEAD · `{{tree_state}}` `git status`
summary · `{{date}}` ISO date · `{{precondition_report}}` itemized precondition results.
Placeholders appear only in stage-specific note sections; canonical prompt text is stable.

## References

Stage states, preconditions, and control rules: `../STAGE_REGISTRY.md`. Report skeleton:
`../STAGE_REPORT_TEMPLATE.md`.
