from pathlib import Path
from unittest.mock import patch

from conftest import git

from ai_workflow_engine.config import load_config
from ai_workflow_engine.git.client import GitClient
from ai_workflow_engine.git.validators import check_git, matching_paths
from ai_workflow_engine.result import Status


def test_status_distinguishes_modified_staged_and_untracked(repository: Path) -> None:
    (repository / "docs/PROJECT_STATE.md").write_text("modified")
    (repository / "docs/current_task.md").write_text("staged")
    git(repository, "add", "docs/current_task.md")
    (repository / "new.txt").write_text("new")
    state = GitClient(repository).status()
    assert state.modified_files == ["docs/PROJECT_STATE.md"]
    assert state.staged_files == ["docs/current_task.md"]
    assert state.untracked_files == ["new.txt"]


def test_protected_path_matching_is_case_sensitive() -> None:
    paths = [
        "docs/planning/plans/T-1_plan_recovery_now.md",
        "DOCS/planning/plans/x_plan_recovery_x.md",
    ]
    assert matching_paths(paths, ["docs/planning/plans/*_plan_recovery_*.md"]) == [paths[0]]


def test_exact_branch_and_head_validation(repository: Path, config_factory: object) -> None:
    config = load_config(config_factory(repository))  # type: ignore[operator]
    head = git(repository, "rev-parse", "HEAD")
    assert check_git(config, expected_branch="main", expected_head=head).status == Status.PASS
    failed = check_git(config, expected_branch="wrong", expected_head="0" * 40)
    assert failed.status == Status.FAIL
    assert {finding.code for finding in failed.findings} == {"branch_mismatch", "head_mismatch"}


def test_staged_protected_path_is_reported(repository: Path, config_factory: object) -> None:
    path = repository / "docs/planning/plans/T-2_plan_recovery_now.md"
    path.parent.mkdir(parents=True)
    path.write_text("protected")
    git(repository, "add", str(path.relative_to(repository)))
    result = check_git(load_config(config_factory(repository)))  # type: ignore[operator]
    assert result.status == Status.FAIL
    assert "protected_path_staged" in {finding.code for finding in result.findings}


def test_status_reports_staged_rename_only(repository: Path) -> None:
    (repository / "x.txt").write_text("hello world\nsecond line\nthird line\n")
    git(repository, "add", "x.txt")
    git(repository, "commit", "-m", "add x")
    git(repository, "mv", "x.txt", "new file.txt")
    state = GitClient(repository).status()
    assert state.staged_files == ["new file.txt"]
    assert state.modified_files == []
    assert "x.txt" not in state.staged_files + state.modified_files + state.untracked_files


def test_status_reports_unstaged_rename_only(repository: Path) -> None:
    (repository / "orig.txt").write_text("hello world\nsecond line\nthird line\n")
    git(repository, "add", "orig.txt")
    git(repository, "commit", "-m", "add orig")
    (repository / "orig.txt").rename(repository / "renamed.txt")
    git(repository, "add", "-N", "renamed.txt")
    state = GitClient(repository).status()
    assert state.modified_files == ["renamed.txt"]
    assert state.staged_files == []
    assert "orig.txt" not in state.staged_files + state.modified_files + state.untracked_files


def test_status_reports_staged_rename_with_unstaged_modification(repository: Path) -> None:
    (repository / "orig2.txt").write_text("hello world\nsecond line\nthird line\n")
    git(repository, "add", "orig2.txt")
    git(repository, "commit", "-m", "add orig2")
    git(repository, "mv", "orig2.txt", "renamed2.txt")
    (repository / "renamed2.txt").write_text("hello world\nsecond line\nthird line\nappended\n")
    state = GitClient(repository).status()
    assert state.staged_files == ["renamed2.txt"]
    assert state.modified_files == ["renamed2.txt"]
    assert "orig2.txt" not in state.staged_files + state.modified_files + state.untracked_files


def test_porcelain_parses_staged_copy_only(repository: Path) -> None:
    with patch.object(GitClient, "_run", return_value="C  copy.txt\0orig.txt\0"):
        modified, staged, untracked = GitClient(repository).porcelain()
    assert staged == ["copy.txt"]
    assert modified == []
    assert untracked == []


def test_porcelain_parses_unstaged_copy_only(repository: Path) -> None:
    with patch.object(GitClient, "_run", return_value=" C copy.txt\0orig.txt\0"):
        modified, staged, untracked = GitClient(repository).porcelain()
    assert modified == ["copy.txt"]
    assert staged == []
    assert untracked == []


def test_git_subprocess_disables_optional_locks(repository: Path) -> None:
    with patch("ai_workflow_engine.git.client.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = "a" * 40 + "\n"
        run.return_value.stderr = ""
        GitClient(repository).head()

    command = run.call_args.args[0]
    kwargs = run.call_args.kwargs
    assert command[:2] == ["git", "--no-optional-locks"]
    assert kwargs["env"]["GIT_OPTIONAL_LOCKS"] == "0"
