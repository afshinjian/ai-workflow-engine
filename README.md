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
