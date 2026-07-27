# Current Task

Mirror of `docs/TASK_QUEUE.md`'s `Current` set. Must contain exactly the same task ID(s) at the
same status as the task queue — `workflowctl check-task-state` fails otherwise.

## AUTO-003 — Deterministic repository and validation skills

Status: Current

Authorized by the Human Owner on 2026-07-27 ("I authorize AUTO-003."). Branch:
`feature/auto-003-repository-validation-skills`, created from clean, synchronized `main` at
`87a5062`. Contract: `docs/workflow-automation/stage-prompts/AUTO-003.md`; Standard Stage
Protocol: `docs/workflow-automation/stage-prompts/README.md`.

Scope: implement the Repository (§2), Contract (§3), Validation (§4), and Reporting (§6) skill
families of `docs/workflow-automation/SKILL_CONTRACTS.md` in `agentos_workflow/skills/`, with
secret-redaction defense-in-depth resolving OD-2. GitHub-facing skills (AUTO-006), Model
Providers (AUTO-004), and Agents (AUTO-005) are out of scope.

The authorization explicitly prohibits commit, push, merge, and beginning AUTO-004. The stage
stops for Human Owner approval.
