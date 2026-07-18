"""The only writable-Git surface (Milestone 4, task T-402).

`GitWriter` exposes typed methods only — there is no public method that runs a caller-supplied
argv. Each method builds one fixed argv template internally and fills only validated path or
message operands (always after a ``--`` separator where pathspecs apply), so forbidden forms
(force push, remote-branch deletion, ``reset``, ``commit --amend``/``-a``, ``add -A``/glob,
``clean``, history rewriting) are structurally unreachable — not denylisted. The read-only
``GitClient`` and its ``READ_ONLY_FORMS`` allowlist are untouched. See ``docs/milestone-4-plan.md``.
"""

import os
import subprocess
from pathlib import Path


class GitWriteError(ValueError):
    """A writable-Git operation failed. Module-local like PromptStorageError/SandboxError."""

    code = "git_write_error"


def _validate_paths(paths: list[str]) -> list[str]:
    if not paths:
        raise GitWriteError("no paths given to a writer path operation")
    for path in paths:
        if not path:
            raise GitWriteError("empty path operand")
        if path.startswith("-"):
            raise GitWriteError(f"path operand must not begin with '-': {path!r}")
        if "\x00" in path:
            raise GitWriteError(f"path operand must not contain NUL: {path!r}")
    return paths


class GitWriter:
    """Execute only fixed, audited writable operations against one repository working tree."""

    def __init__(self, repository: Path) -> None:
        self.repository = repository

    def _run(self, args: list[str], *, input_bytes: bytes | None = None) -> None:
        # Private: callers reach this only via the typed methods below, each of which supplies a
        # fixed leading subcommand. There is no public arbitrary-argv entry point.
        try:
            environment = os.environ.copy()
            environment["GIT_OPTIONAL_LOCKS"] = "0"
            process = subprocess.run(
                ["git", "-C", str(self.repository), *args],
                check=False,
                capture_output=True,
                env=environment,
                input=input_bytes,
            )
        except OSError as exc:
            raise GitWriteError(f"Unable to execute Git: {exc}") from exc
        if process.returncode:
            stderr = process.stderr.decode("utf-8", errors="replace")
            raise GitWriteError(f"git {args[0]} failed: {stderr.strip()}")

    def stage_paths(self, paths: list[str]) -> None:
        """Stage exactly ``paths`` (never ``-A``/glob; ``--`` makes each a literal pathspec)."""
        self._run(["add", "--", *_validate_paths(paths)])

    def unstage_paths(self, paths: list[str]) -> None:
        """Restore the index for ``paths`` only; never touches the working tree."""
        self._run(["restore", "--staged", "--", *_validate_paths(paths)])

    def commit(self, message: str) -> None:
        """Create one commit with ``message`` as the ``-m`` operand (never scanned)."""
        self._run(["commit", "-m", message])

    def push(self) -> None:
        """Publish once — argv is exactly ``["push"]``; no refspec, no force, no delete."""
        self._run(["push"])

    def apply_check(self, patch: bytes) -> bool:
        """Dry-run whether ``patch`` applies to the working tree; performs no write."""
        try:
            self._run(["apply", "--check", "-"], input_bytes=patch)
        except GitWriteError:
            return False
        return True

    def apply_patch(self, patch: bytes) -> None:
        """Apply ``patch`` to the working tree only (never ``--index``/``--cached``)."""
        self._run(["apply", "-"], input_bytes=patch)
