"""Throwaway sandbox clones and a sandbox-only Git surface (Milestone 3, task T-304).

A sandbox is a fresh ``git clone`` of the target repository in a temporary directory, checked out
detached at the prompt's recorded HEAD. All writable Git operations a run needs go through
:class:`SandboxGit`, which refuses to operate on any directory this process did not create as a
sandbox — the read-only :class:`~ai_workflow_engine.git.client.GitClient` and its allowlist are
never touched, and the target repository is never written. See ``docs/milestone-3-plan.md``.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from ai_workflow_engine.exceptions import GitCommandError

# Resolved sandbox paths this process created. Membership is what makes a directory a legitimate
# SandboxGit target; it is never populated from caller input.
_MANAGED: set[str] = set()


class SandboxError(ValueError):
    code = "sandbox_error"


class SnapshotUnavailable(SandboxError):
    code = "snapshot_unavailable"


def _git(
    args: list[str], *, cwd: Path | None, text: bool = True, input_bytes: bytes | None = None
) -> str | bytes:
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    command = ["git"]
    if cwd is not None:
        command += ["-C", str(cwd)]
    command += args
    try:
        process = subprocess.run(
            command, capture_output=True, env=env, input=input_bytes, text=text
        )
    except OSError as exc:  # pragma: no cover - defensive
        raise GitCommandError(f"Unable to execute Git: {exc}") from exc
    if process.returncode:
        stderr = process.stderr if text else process.stderr.decode("utf-8", errors="replace")
        raise GitCommandError(f"git {args[0]} failed: {stderr.strip()}")
    stdout: str | bytes = process.stdout
    return stdout


class SandboxGit:
    """Writable Git bound to one managed sandbox directory — never the target repository."""

    def __init__(self, path: Path) -> None:
        resolved = path.resolve()
        if str(resolved) not in _MANAGED:
            raise SandboxError(f"Not a managed sandbox directory: {path}")
        self.path = resolved

    def stage_all(self) -> None:
        _git(["add", "-A"], cwd=self.path)

    def changed_paths(self) -> list[str]:
        """Repo-relative POSIX paths that differ from HEAD (call after :meth:`stage_all`)."""
        output = _git(["diff", "--cached", "--name-only", "-z"], cwd=self.path)
        assert isinstance(output, str)
        return sorted(path for path in output.split("\0") if path)

    def diff_cached_binary(self) -> bytes:
        output = _git(["diff", "--cached", "--binary"], cwd=self.path, text=False)
        assert isinstance(output, bytes)
        return output

    def apply_check(self, patch: bytes) -> None:
        _git(["apply", "--check", "-"], cwd=self.path, text=False, input_bytes=patch)

    def apply(self, patch: bytes) -> None:
        _git(["apply", "-"], cwd=self.path, text=False, input_bytes=patch)


def create_sandbox(repository: Path, repository_head: str) -> Path:
    """Clone ``repository`` into a temp dir and detach-checkout ``repository_head``.

    Raises :class:`SnapshotUnavailable` if the recorded commit is not present, so a prompt
    rendered against state that no longer exists is never executed against different state.
    """
    parent = Path(tempfile.mkdtemp(prefix="awe-sandbox-"))
    sandbox = parent / "sandbox"
    try:
        _git(
            [
                "clone",
                "--quiet",
                "--no-local",
                "--no-hardlinks",
                repository.resolve().as_uri(),
                str(sandbox),
            ],
            cwd=None,
        )
    except GitCommandError:
        shutil.rmtree(parent, ignore_errors=True)
        raise
    _MANAGED.add(str(sandbox.resolve()))
    try:
        _git(["checkout", "--quiet", "--detach", repository_head], cwd=sandbox)
    except GitCommandError as exc:
        teardown(sandbox)
        raise SnapshotUnavailable(
            f"Recorded head {repository_head} is unavailable in the sandbox: {exc}"
        ) from exc
    return sandbox


def teardown(sandbox: Path) -> None:
    """Remove a sandbox and its temp parent, and unregister it. Idempotent."""
    resolved = sandbox.resolve()
    _MANAGED.discard(str(resolved))
    shutil.rmtree(resolved.parent, ignore_errors=True)


def is_managed(path: Path) -> bool:
    return str(path.resolve()) in _MANAGED
