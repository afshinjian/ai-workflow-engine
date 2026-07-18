# AI Workflow Engine

`ai-workflow-engine` is a reusable, local orchestration foundation for governed AI-assisted
software development. It never infers truth from an agent report: Git objects, file bytes,
hashes, and governance facts are independently inspected.

Implemented so far (see [docs/milestones.md](docs/milestones.md) for the full roadmap):

- **Milestone 1** — deterministic, read-only inspection of Git state, governance mirrors, task
  state, and handover checksums. No writable Git operations; no agent execution.
- **Milestone 2** — governed prompt generation: deterministic, canonically-hashed, byte-exact
  Markdown prompts for seven fixed workflow stages (`plan-review`, `implementation`,
  `implementation-review`, `remediation`, `governance-closeout`, `governance-review`, `push`),
  with structural validation and race-safe atomic storage under `~/.ai-workflow-engine/`.
  Normative specification: [docs/milestone-2-plan.md](docs/milestone-2-plan.md).
- **Milestone 3** (v0.2.0) — non-interactive agent execution: a persisted, hash-chained workflow
  state machine (`workflowctl state`), a configurable `agents` section with a strict report
  contract, a snapshot-sandbox runner with hard timeouts and isolation, and independent claim
  verification with tamper-evident run artifacts (`workflowctl agent run`). An agent's output is
  always verified against reality, never trusted. Normative specification:
  [docs/milestone-3-plan.md](docs/milestone-3-plan.md); demonstration:
  [docs/MILESTONE_3_VALIDATION.md](docs/MILESTONE_3_VALIDATION.md).
- **Milestone 4** (v0.3.0) — controlled commit and push: a separate typed writable-Git surface
  (the read-only inspection surface is provably untouched), per-invocation human approval
  artifacts pinning branch/HEAD/paths, and `workflowctl commit` / `push` / `apply-patch` gates. A
  commit can never quietly include an un-approved or protected change; a push mechanically
  re-checks the Milestone 2 push algorithm before a single `git push`. Normative specification:
  [docs/milestone-4-plan.md](docs/milestone-4-plan.md); demonstration:
  [docs/MILESTONE_4_VALIDATION.md](docs/MILESTONE_4_VALIDATION.md).

This repository also governs itself: `self-governance.yaml` points the tool at its own working
tree, and `docs/CONTEXT.md` gives a fresh session the exact read order to recover full project
state from repository files alone.

## Install

```bash
conda create -n ai-workflow-engine python=3.11 -y
conda activate ai-workflow-engine
python -m pip install --upgrade pip setuptools wheel
pip install -e ".[dev]"
workflowctl --help
workflowctl version
```

## Inspect and verify

```bash
workflowctl inspect --config examples/amozesh_konkur.yaml
workflowctl inspect --config examples/amozesh_konkur.yaml --output json
workflowctl check-git --config examples/amozesh_konkur.yaml --expected-branch main
workflowctl check-task-state --config examples/amozesh_konkur.yaml
workflowctl check-governance --config examples/amozesh_konkur.yaml
workflowctl check-handover --config examples/amozesh_konkur.yaml --source commit --commit HEAD
workflowctl verify --config examples/amozesh_konkur.yaml --output json

# Self-governance: run the same checks against this repository itself
workflowctl verify --config self-governance.yaml
```

## Generate governed prompts

```bash
workflowctl prompt plan-review --config self-governance.yaml --task-id T-102
workflowctl prompt implementation --config self-governance.yaml --task-id T-102 \
  --allowed-path docs/architecture.md --allowed-path README.md
workflowctl prompt remediation --config self-governance.yaml --task-id T-102 \
  --allowed-path README.md --finding "README omits the prompt commands"
workflowctl prompt governance-closeout --config self-governance.yaml --task-id T-102 --no-store
```

Every prompt command accepts `--output human|json` and `--store/--no-store` (default `--store`;
artifacts land under `~/.ai-workflow-engine/workflow-runs/prompts/`, never inside the target
repository). Prompt identity is the SHA-256 of the canonical JSON of the complete rendered
context — two renders of the same state are byte-identical.

## Workflow state and agent execution (Milestone 3)

```bash
# Persisted, hash-chained per-task workflow state
workflowctl state next --config self-governance.yaml --task-id T-1
workflowctl state record --config self-governance.yaml --task-id T-1 \
  --stage plan-review --verdict APPROVED
workflowctl state show --config self-governance.yaml --task-id T-1 --output json

# Run a configured agent against a stored prompt, in a sandbox, verifying its claims
workflowctl agent run --config <config> --agent <name> --task-id T-1 \
  --stage plan-review --prompt-id <16hex>

# Bind a state verdict to a verified agent run
workflowctl state record --config <config> --task-id T-1 --stage plan-review \
  --verdict APPROVED --agent-run <16hex>
```

Agents are declared in the config's `agents` section (see
[docs/configuration.md](docs/configuration.md)). An agent runs in a throwaway clone of the
repository, never touching the target working tree; its report is independently verified against
what actually changed in the sandbox, and the result is stored as a tamper-evident artifact.

## Controlled commit and push (Milestone 4)

Commits and pushes are bound to a per-invocation human **approval artifact** — a small YAML file
that pins exactly what is authorized. No commit or push happens without one, and a prior approval
never carries forward.

```yaml
# commit-approval.yaml
kind: commit
task_id: T-1
branch: main
head: <the exact parent HEAD the commit must build on>
allowed_paths: [src/feature.py]      # exactly the paths that may be staged
message: "add feature"
approved_by: you@example.com
```

```bash
workflowctl commit --config <config> --approval commit-approval.yaml
workflowctl push   --config <config> --approval push-approval.yaml   # kind: push
workflowctl apply-patch --config <config> --task-id T-1 \
  --stage implementation --run-id <16hex>   # apply a verified agent patch to the working tree
```

`commit` stages exactly the approved paths and refuses any un-approved or protected-path change;
`push` re-checks branch/HEAD/upstream and that the branch is a clean fast-forward before a single
`git push`. All writes go through a separate writable-Git surface; the read-only inspection
commands above cannot write. See [docs/configuration.md](docs/configuration.md) for the approval
fields and [docs/milestone-4-plan.md](docs/milestone-4-plan.md) for the gate algorithms.

`PASS` exits zero. `FAIL` and `ERROR` exit nonzero. Expected validation/configuration errors are
shown without a traceback; pass `--debug` before the command to include diagnostics.

The JSON result contract is documented in [docs/architecture.md](docs/architecture.md), and the
configuration schema in [docs/configuration.md](docs/configuration.md).

## Development

```bash
pytest -q
ruff check .
black --check .
mypy src
pre-commit run --all-files
workflowctl verify --config self-governance.yaml
```
