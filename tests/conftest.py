import hashlib
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml


def git(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def manifest_line(path: str, data: bytes) -> str:
    return f"| `{path}` | {len(data)} | now | `{hashlib.sha256(data).hexdigest()[:16]}…` |"


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "tests@example.invalid")
    git(repo, "config", "user.name", "Workflow Tests")
    (repo / "docs").mkdir()
    (repo / "handover").mkdir()
    task_table = "| Task | Status |\n|---|---|\n| T-1 | Planned |\n"
    for name in [
        "PROJECT_STATE.md",
        "TASK_QUEUE.md",
        "current_task.md",
        "remain_task.md",
        "CHATGPT_CONTEXT.md",
    ]:
        (repo / "docs" / name).write_text(task_table + "Version: 1.0.0\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text('version = "1.0.0"\n', encoding="utf-8")
    handover_files = {
        "handover/PROJECT_HANDOVER.md": b"handover\n",
        "handover/BOOTSTRAP_PROMPT.md": b"bootstrap\n",
    }
    for name, data in handover_files.items():
        (repo / name).write_bytes(data)
    manifest = "\n".join(
        [
            "| Relative path | Size (bytes) | Last modified | SHA-256 (prefix) |",
            "|---|---|---|---|",
            *(manifest_line(name, data) for name, data in handover_files.items()),
        ]
    )
    (repo / "handover/PROJECT_CHECKSUM.md").write_text(manifest + "\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial")
    return repo


@pytest.fixture
def config_factory(tmp_path: Path) -> Callable[[Path], Path]:
    def factory(repository: Path) -> Path:
        raw = {
            "project": {
                "id": "test-project",
                "repository": str(repository),
                "default_branch": "main",
                "timezone": "UTC",
            },
            "governance": {
                "project_state": "docs/PROJECT_STATE.md",
                "task_queue": "docs/TASK_QUEUE.md",
                "current_task": "docs/current_task.md",
                "remaining_tasks": "docs/remain_task.md",
                "context": "docs/CHATGPT_CONTEXT.md",
                "pyproject": "pyproject.toml",
                "facts": [
                    {
                        "name": "version",
                        "paths": ["docs/PROJECT_STATE.md", "docs/CHATGPT_CONTEXT.md"],
                        "pattern": r"Version:\s*([0-9.]+)",
                        "required": True,
                    }
                ],
            },
            "handover": {
                "manifest": "handover/PROJECT_CHECKSUM.md",
                "files": [
                    "handover/PROJECT_HANDOVER.md",
                    "handover/BOOTSTRAP_PROMPT.md",
                    "handover/PROJECT_CHECKSUM.md",
                ],
            },
            "protected_paths": {
                "never_stage": ["docs/planning/plans/*_plan_recovery_*.md"],
                "never_commit": ["docs/planning/plans/*_plan_recovery_*.md"],
            },
            "workflow": {
                "maximum_current_tasks": 1,
                "require_designer_approval_for_promotion": True,
                "allow_automatic_commit": False,
                "allow_automatic_push": False,
            },
        }
        path = tmp_path / f"{repository.name}.yaml"
        path.write_text(yaml.safe_dump(raw), encoding="utf-8")
        return path

    return factory
