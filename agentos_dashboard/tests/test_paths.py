"""TC-03 — root confinement, traversal, symlink escape, and the deny-list (SC-06..SC-08).

Every case runs against a real temporary directory tree: the property under test is what the
filesystem does with the path, which a mocked filesystem could not demonstrate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentos_dashboard.core.paths import (
    DENIED_PREFIXES,
    PathRefusal,
    PathRefusedError,
    RepositoryRoot,
    RepositoryRootError,
    is_denied,
)

from .conftest import write


def refusal(root: RepositoryRoot, relative: str) -> PathRefusal:
    with pytest.raises(PathRefusedError) as caught:
        root.resolve(relative)
    return caught.value.refusal


def test_resolves_an_ordinary_relative_path(root: RepositoryRoot, workspace: Path) -> None:
    write(workspace, "docs/TASK_QUEUE.md", "queue\n")
    assert root.resolve("docs/TASK_QUEUE.md") == workspace / "docs" / "TASK_QUEUE.md"


def test_resolves_a_path_that_does_not_exist(root: RepositoryRoot, workspace: Path) -> None:
    # Existence is the file adapter's concern; refusing here would leak which files exist
    # through the choice of exception.
    assert root.resolve("docs/absent.md") == workspace / "docs" / "absent.md"


def test_redundant_current_directory_segments_are_dropped(
    root: RepositoryRoot, workspace: Path
) -> None:
    write(workspace, "docs/CONTEXT.md", "context\n")
    assert root.resolve("./docs/./CONTEXT.md") == workspace / "docs" / "CONTEXT.md"


@pytest.mark.parametrize(
    ("relative", "expected"),
    [
        ("", PathRefusal.EMPTY),
        ("   ", PathRefusal.EMPTY),
        (".", PathRefusal.EMPTY),
        ("/etc/passwd", PathRefusal.ABSOLUTE),
        ("\\etc\\passwd", PathRefusal.ABSOLUTE),
        ("../outside.txt", PathRefusal.TRAVERSAL),
        ("docs/../../outside.txt", PathRefusal.TRAVERSAL),
        ("docs/..", PathRefusal.TRAVERSAL),
        ("docs/\x00secret", PathRefusal.NUL_BYTE),
    ],
)
def test_refuses_malformed_and_traversing_paths(
    root: RepositoryRoot, relative: str, expected: PathRefusal
) -> None:
    assert refusal(root, relative) is expected


def test_traversal_is_refused_even_when_the_target_does_not_exist(root: RepositoryRoot) -> None:
    # Lexical rejection, before any filesystem access: the refusal must not depend on whether
    # the escape happens to hit a real file.
    assert refusal(root, "../definitely/not/here.txt") is PathRefusal.TRAVERSAL


def test_percent_encoded_traversal_is_not_decoded(root: RepositoryRoot, workspace: Path) -> None:
    """An encoded `../` is an ordinary filename here, never a traversal.

    The adapter deliberately performs no decoding, so a future HTTP layer cannot smuggle a
    traversal past it by encoding one — and cannot rely on this layer to decode either.
    """
    (workspace.parent / "outside.txt").write_text("secret\n", encoding="utf-8")
    resolved = root.resolve("%2e%2e/outside.txt")
    assert resolved.is_relative_to(workspace)
    assert not resolved.exists()


def test_symlink_escaping_the_root_is_refused(root: RepositoryRoot, workspace: Path) -> None:
    outside = workspace.parent / "outside.txt"
    outside.write_text("secret\n", encoding="utf-8")
    (workspace / "escape.txt").symlink_to(outside)
    assert refusal(root, "escape.txt") is PathRefusal.SYMLINK_ESCAPE


def test_symlinked_directory_escaping_the_root_is_refused(
    root: RepositoryRoot, workspace: Path
) -> None:
    outside_dir = workspace.parent / "outside"
    outside_dir.mkdir()
    (outside_dir / "secret.txt").write_text("secret\n", encoding="utf-8")
    (workspace / "linked").symlink_to(outside_dir, target_is_directory=True)
    assert refusal(root, "linked/secret.txt") is PathRefusal.SYMLINK_ESCAPE


def test_symlink_inside_the_root_is_allowed(root: RepositoryRoot, workspace: Path) -> None:
    write(workspace, "docs/real.md", "real\n")
    (workspace / "alias.md").symlink_to(workspace / "docs" / "real.md")
    assert root.resolve("alias.md") == workspace / "docs" / "real.md"


def test_symlink_into_a_denied_directory_is_refused(root: RepositoryRoot, workspace: Path) -> None:
    """The second deny-list check, against the resolved target, is what catches this."""
    write(workspace, ".git/config", "[core]\n")
    (workspace / "innocuous.txt").symlink_to(workspace / ".git" / "config")
    assert refusal(root, "innocuous.txt") is PathRefusal.DENIED


def test_symlink_loop_is_refused_without_raising_oserror(
    root: RepositoryRoot, workspace: Path
) -> None:
    (workspace / "loop_a").symlink_to(workspace / "loop_b")
    (workspace / "loop_b").symlink_to(workspace / "loop_a")
    assert refusal(root, "loop_a") in {PathRefusal.UNREADABLE, PathRefusal.SYMLINK_ESCAPE}


@pytest.mark.parametrize(
    "relative",
    [
        ".env",
        ".env.local",
        ".envrc",
        "config/.env",
        "config/.env.production",
        ".git/config",
        ".git/refs/heads/main",
        "submodule/.git/config",
        "data/agentos_dashboard/dashboard.db",
        "data/agentos_dashboard/logs/dashboard.log",
    ],
)
def test_deny_list_paths_are_refused(root: RepositoryRoot, relative: str) -> None:
    assert refusal(root, relative) is PathRefusal.DENIED


@pytest.mark.parametrize(
    "relative",
    [
        "data/other/file.txt",
        "docs/environment.md",
        "gitignore.md",
        "src/data/agentos_dashboard.md",
    ],
)
def test_deny_list_does_not_overreach(root: RepositoryRoot, relative: str) -> None:
    assert root.resolve(relative).is_relative_to(root.path)


def test_is_denied_matches_the_documented_prefixes() -> None:
    assert DENIED_PREFIXES == ((".git",), ("data", "agentos_dashboard"))
    assert is_denied((".git", "config"))
    assert is_denied(("data", "agentos_dashboard", "dashboard.db"))
    assert not is_denied(("data", "other"))


def test_relative_of_returns_posix_form(root: RepositoryRoot, workspace: Path) -> None:
    write(workspace, "docs/reports/report.md", "x\n")
    assert root.relative_of(root.resolve("docs/reports/report.md")) == "docs/reports/report.md"


def test_root_must_exist(tmp_path: Path) -> None:
    with pytest.raises(RepositoryRootError):
        RepositoryRoot.from_path(tmp_path / "absent")


def test_root_must_be_a_directory(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("x\n", encoding="utf-8")
    with pytest.raises(RepositoryRootError):
        RepositoryRoot.from_path(target)


def test_root_is_fully_resolved_so_a_symlinked_root_still_contains_its_own_files(
    tmp_path: Path,
) -> None:
    real = tmp_path / "real_repo"
    real.mkdir()
    write(real, "docs/PROJECT_STATE.md", "state\n")
    link = tmp_path / "linked_repo"
    link.symlink_to(real, target_is_directory=True)

    root = RepositoryRoot.from_path(link)
    assert root.path == real
    assert root.resolve("docs/PROJECT_STATE.md") == real / "docs" / "PROJECT_STATE.md"
