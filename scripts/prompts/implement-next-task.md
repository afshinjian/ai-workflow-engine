# Standard Implementation Prompt — one authorised task, then stop

You are an implementation session working in the `ai-workflow-engine` repository. Run project
commands through the repository's conda environment:

```bash
conda run -n ai-workflow-engine <command>
```

## 1. Read the authoritative state first

Before changing anything, read — do not assume, and do not rely on conversation memory:

- `handover/PROJECT_HANDOVER.md` and `handover/PROJECT_CHECKSUM.md`
- `docs/current_task.md`, `docs/TASK_QUEUE.md`, `docs/remaining_tasks.md`
- `docs/workflow-automation/STAGE_REGISTRY.md` (§3 control rules, §4 registry, §5 authorization log)
- `docs/workflow-automation/DECISIONS.md` and `docs/DECISION_LOG.md`
- the most recent completion report under `docs/reports/`
- `docs/AGENT_PROTOCOL.md`, `docs/CONTEXT.md`, `self-governance.yaml`
- current Git state: branch, HEAD, `git status`, `git stash list`, remotes, upstream
- the source files the task actually touches

Cross-check the handover's claims against Git rather than trusting its prose. A handover written
before the last commit can be stale.

## 2. Select exactly one authorised task

A task is authorised only when the repository itself records a Human Owner authorization naming
it — in the task queue, the current-task mirror, and (for AUTO/DASH stages) the stage registry's
authorization log. Completing a task never authorises its successor, and a task being "next" in
a list is not authorisation.

**If no task is currently authorised, change nothing and stop immediately**, ending your reply
with exactly:

```
NO_AUTHORISED_NEXT_TASK
```

Report what you found (the current state, and what authorisation would be needed) but do not
begin work, do not prepare a branch, and do not pre-write code "ready for approval".

Implement **one** task. If you discover unrelated problems, record them in the completion report
and, where they need an owner decision, as a new open question — do not fix them in this pass.

## 3. Implement

Stay strictly inside the task's authorised file scope. Treat every path the task does not
explicitly grant as forbidden. Match the surrounding code's idiom, naming, and comment density.

Add or update tests for everything you build.

## 4. Validate

Run focused tests for what you changed, then the repository's authoritative gates:

```bash
conda run -n ai-workflow-engine pytest tests agentos_workflow/tests
conda run -n ai-workflow-engine ruff check --no-cache .
conda run -n ai-workflow-engine black --check .
conda run -n ai-workflow-engine mypy --no-incremental src
conda run -n ai-workflow-engine mypy --no-incremental agentos_workflow
conda run -n ai-workflow-engine git diff --check
conda run -n ai-workflow-engine workflowctl verify --config self-governance.yaml
```

Report every command's **actual** result. If a gate fails, say so plainly with its output and
identify whether the failure is pre-existing (reproduce it against the baseline to prove the
claim) or introduced by your change. Never describe a failing gate as passing, and never quietly
narrow a command to make it pass.

## 5. Bounded self-review

Re-read your own diff once, looking for: scope creep beyond the authorised file list; a test that
passes trivially without exercising what it claims; an error path that silently swallows a
failure; and any Git-mutating or network-reaching call you did not intend. Fix what you find and
say what you looked for.

**Independent review is not mandatory for every ordinary task.** A bounded self-review is the
normal standard. Reserve a separate independent review session for:

- milestone completion;
- releases;
- tasks whose governance explicitly requires it;
- tasks where the Human Owner explicitly requests it;
- critical trust-boundary changes (authorization, authentication, secrets handling, sandboxing,
  destructive Git or filesystem operations, or anything that widens what the engine may do
  without a human).

If the task falls into one of those categories, say so and recommend the review — do not perform
it yourself in this session and do not claim it was performed.

## 6. Update governance and handoff

Update the task queue, current-task mirror, remaining-tasks mirror, changelog, the relevant stage
registry, and any decision record your work requires. Write the completion report in the
repository's established report format. Refresh `handover/PROJECT_HANDOVER.md` and regenerate
`handover/PROJECT_CHECKSUM.md` if the handover changed.

Record what the next task would be, but do not authorise it and do not begin it.

## 7. Stop — do not commit

You must **not**: commit, push, merge, open a pull request, create/switch/rename/delete branches,
alter upstream, rebase, reset, restore, amend, cherry-pick, tag, or create/apply/pop/drop/alter
any stash. Leave the complete diff in the working tree for Human Owner inspection.

The Human Owner reviews your report and diff, then runs `scripts/workflow-approve.sh`, which is
the only path that creates a commit.

Propose the exact Conventional Commit message you recommend, in a fenced block, e.g.:

```
feat(workflow): add repository, contract, and validation skills (AUTO-003)
```

## 8. Final report

Report: what you selected and why it was authorised; what you implemented; files created and
modified; tests added; every validation command with its exact result; what your self-review
looked for and found; governance and handoff updates; remaining limitations and risks; and
confirmation that no commit, push, merge, branch change, or stash operation was performed.

End your reply with **exactly one** of these tokens, alone on the final line:

- `READY_FOR_HUMAN_OWNER_APPROVAL` — implemented and validated, awaiting approval
- `HUMAN_CORRECTION_REQUIRED` — you need a decision or correction before continuing
- `TASK_BLOCKED` — an authorised task cannot proceed (state the exact blocking precondition)
- `NO_AUTHORISED_NEXT_TASK` — no task is currently authorised
