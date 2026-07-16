# AI Workflow Engine

`ai-workflow-engine` is a reusable, local orchestration foundation for governed AI-assisted
software development. Version 0.1.0 implements Milestone 1: deterministic, read-only inspection
of Git state, governance mirrors, task state, and handover checksums.

It never infers truth from an agent report. Git objects, file bytes, hashes, and governance facts
are independently inspected. Milestone 1 has no writable Git operations and does not run agents.

## Install

```bash
conda create -n ai-workflow-engine python=3.11 -y
conda activate ai-workflow-engine
python -m pip install --upgrade pip setuptools wheel
pip install -e ".[dev]"
workflowctl --help
workflowctl version
```

## Use

```bash
workflowctl inspect --config examples/amozesh_konkur.yaml
workflowctl inspect --config examples/amozesh_konkur.yaml --output json
workflowctl check-git --config examples/amozesh_konkur.yaml --expected-branch main
workflowctl check-handover --config examples/amozesh_konkur.yaml --source commit --commit HEAD
workflowctl verify --config examples/amozesh_konkur.yaml --output json
```

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
```
