"""Small Git adapter whose command surface is deliberately read-only."""

import os
import subprocess
from pathlib import Path
from typing import cast

from ai_workflow_engine.exceptions import GitCommandError
from ai_workflow_engine.git.models import GitStatus


class GitClient:
    """Execute only fixed, audited read operations against one worktree."""

    READ_ONLY_FORMS = (
        ("rev-parse",),
        ("status",),
        ("symbolic-ref",),
        ("rev-list",),
        ("show",),
        ("diff",),
        ("ls-files",),
        ("cat-file",),
    )

    def __init__(self, repository: Path) -> None:
        self.repository = repository

    def _run(self, args: list[str], *, text: bool = True) -> str | bytes:
        if not args or not any(tuple(args[: len(form)]) == form for form in self.READ_ONLY_FORMS):
            raise GitCommandError(f"Git command is not on the read-only allowlist: {args!r}")
        try:
            environment = os.environ.copy()
            environment["GIT_OPTIONAL_LOCKS"] = "0"
            process = subprocess.run(
                ["git", "--no-optional-locks", "-C", str(self.repository), *args],
                check=False,
                capture_output=True,
                env=environment,
                text=text,
            )
        except OSError as exc:
            raise GitCommandError(f"Unable to execute Git: {exc}") from exc
        if process.returncode:
            stderr = process.stderr if text else process.stderr.decode(errors="replace")
            raise GitCommandError(f"git {args[0]} failed: {stderr.strip()}")
        return cast(str | bytes, process.stdout)

    def branch(self) -> str:
        value = self._run(["symbolic-ref", "--quiet", "--short", "HEAD"])
        assert isinstance(value, str)
        return value.strip()

    def is_worktree(self) -> bool:
        value = self._run(["rev-parse", "--is-inside-work-tree"])
        assert isinstance(value, str)
        return value.strip() == "true"

    def head(self) -> str:
        value = self._run(["rev-parse", "--verify", "HEAD^{commit}"])
        assert isinstance(value, str)
        return value.strip()

    def upstream(self) -> str | None:
        try:
            value = self._run(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"])
        except GitCommandError:
            return None
        assert isinstance(value, str)
        return value.strip()

    def ahead_behind(self, upstream: str) -> tuple[int, int]:
        value = self._run(["rev-list", "--left-right", "--count", f"HEAD...{upstream}"])
        assert isinstance(value, str)
        ahead, behind = (int(item) for item in value.split())
        return ahead, behind

    def porcelain(self) -> tuple[list[str], list[str], list[str]]:
        output = self._run(["status", "--porcelain=v1", "-z", "--untracked-files=all"])
        assert isinstance(output, str)
        records = output.split("\0")
        modified: set[str] = set()
        staged: set[str] = set()
        untracked: set[str] = set()
        index = 0
        while index < len(records):
            record = records[index]
            index += 1
            if not record:
                continue
            if len(record) < 4:
                raise GitCommandError(f"Malformed porcelain status record: {record!r}")
            x, y, path = record[0], record[1], record[3:]
            if x == "?" and y == "?":
                untracked.add(path)
                continue
            if x not in {" ", "?", "!"}:
                staged.add(path)
            if y not in {" ", "?", "!"}:
                modified.add(path)
            if (x in {"R", "C"} or y in {"R", "C"}) and index < len(records):
                # In -z output a second NUL-delimited field carries the original path
                # whenever the index (X) or worktree (Y) status is a rename/copy. It is
                # consumed here and discarded; only the current (target) path in `path`
                # is ever recorded, per the X/Y classification above.
                index += 1
        return sorted(modified), sorted(staged), sorted(untracked)

    def status(self) -> GitStatus:
        branch = self.branch()
        head = self.head()
        upstream = self.upstream()
        ahead: int | None = None
        behind: int | None = None
        if upstream:
            ahead, behind = self.ahead_behind(upstream)
        modified, staged, untracked = self.porcelain()
        return GitStatus(
            branch=branch,
            head=head,
            upstream=upstream,
            ahead=ahead,
            behind=behind,
            modified_files=modified,
            staged_files=staged,
            untracked_files=untracked,
        )

    def read_index_blob(self, path: str) -> bytes:
        value = self._run(["show", f":{path}"], text=False)
        assert isinstance(value, bytes)
        return value

    def read_commit_blob(self, commit: str, path: str) -> bytes:
        # --end-of-options prevents a commit supplied by the caller from becoming an option.
        value = self._run(
            ["show", "--no-ext-diff", "--end-of-options", f"{commit}:{path}"], text=False
        )
        assert isinstance(value, bytes)
        return value

    def resolve_commit(self, commit: str) -> str:
        value = self._run(["rev-parse", "--verify", f"{commit}^{{commit}}"])
        assert isinstance(value, str)
        return value.strip()
