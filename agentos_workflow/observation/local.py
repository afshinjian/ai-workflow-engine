"""Fixed-argv local observations used exclusively by AUTO-002 resume validation."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path, PurePosixPath
from typing import Protocol
from urllib.parse import urlparse

from agentos_workflow.config.schema import WorkflowConfig

_DEVELOPMENT_VERSION = "0.1.0"
_GIT_TIMEOUT_SECONDS = 10
_SHA_RE = re.compile(r"[0-9a-f]{40}")


class ResumeObservationError(Exception):
    """A local fact required for resume could not be observed safely."""

    def __init__(self, field: str, detail: str) -> None:
        self.field = field
        self.detail = detail
        super().__init__(f"Unable to observe {field}: {detail}")


@dataclass(frozen=True)
class WorktreeChange:
    """One raw porcelain-v1 record."""

    index_status: str
    worktree_status: str
    path: str
    original_path: str | None = None

    @property
    def is_untracked(self) -> bool:
        return self.index_status == "?" and self.worktree_status == "?"

    @property
    def is_staged(self) -> bool:
        return self.index_status not in {" ", "?", "!"}

    @property
    def is_deleted(self) -> bool:
        return "D" in {self.index_status, self.worktree_status}

    @property
    def is_renamed(self) -> bool:
        return "R" in {self.index_status, self.worktree_status}


@dataclass(frozen=True)
class ResumeObservation:
    """Raw local facts.  This type intentionally carries no validity/verdict field."""

    canonical_repository_path: str
    repository_exists: bool
    is_git_repository: bool
    observed_repository_identity: str | None
    current_branch: str | None
    head_sha: str | None
    baseline_sha: str | None
    planned_branch_sha: str | None
    baseline_is_ancestor_of_planned: bool | None
    worktree_changes: tuple[WorktreeChange, ...]
    canonical_contract_path: str
    contract_exists: bool
    contract_hash: str | None
    engine_version: str


class ResumeObserver(Protocol):
    """Test seams return raw facts only; the Orchestrator still decides."""

    def observe(
        self,
        *,
        stage_contract_path: str,
        baseline_branch: str,
        planned_branch: str,
    ) -> ResumeObservation: ...


def running_engine_version() -> str:
    """Canonical runtime version with one deterministic editable-source fallback."""

    try:
        return version("ai-workflow-engine")
    except PackageNotFoundError:
        return _DEVELOPMENT_VERSION


def canonical_repository_identity(value: str) -> str:
    """Normalize common local remote spellings to ``host/path`` without network access."""

    candidate = value.strip()
    if "://" in candidate:
        parsed = urlparse(candidate)
        host = (parsed.hostname or "").lower()
        path = parsed.path.lstrip("/")
        candidate = f"{host}/{path}"
    elif re.match(r"^[^/@:]+@[^:]+:.+", candidate):
        _, remainder = candidate.split("@", 1)
        host, path = remainder.split(":", 1)
        candidate = f"{host.lower()}/{path}"
    candidate = candidate.rstrip("/")
    if candidate.endswith(".git"):
        candidate = candidate[:-4]
    return candidate


def _validate_ref_component(value: str, field: str) -> str:
    forbidden = ("..", "@{", "\\", " ", "~", "^", ":", "?", "*", "[")
    if (
        not value
        or value.startswith(("-", ".", "/"))
        or value.endswith((".", "/", ".lock"))
        or "//" in value
        or any(token in value for token in forbidden)
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ResumeObservationError(field, f"unsafe Git ref name {value!r}")
    return value


class LocalResumeObserver:
    """Obtain only the fixed local facts needed by resume."""

    def __init__(self, config: WorkflowConfig) -> None:
        self._config = config
        self._repository = config.repository_path.resolve()

    def _git(
        self,
        args: tuple[str, ...],
        *,
        field: str,
        allowed_returncodes: frozenset[int] = frozenset({0}),
    ) -> subprocess.CompletedProcess[bytes]:
        environment = {
            "LC_ALL": "C",
            "LANG": "C",
            "GIT_OPTIONAL_LOCKS": "0",
            "PATH": os.environ.get("PATH", ""),
        }
        try:
            process = subprocess.run(
                ["git", "--no-optional-locks", "-C", str(self._repository), *args],
                check=False,
                capture_output=True,
                timeout=_GIT_TIMEOUT_SECONDS,
                env=environment,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ResumeObservationError(field, str(exc)) from exc
        if process.returncode not in allowed_returncodes:
            detail = process.stderr.decode("utf-8", errors="replace").strip()
            raise ResumeObservationError(
                field, f"git returned {process.returncode}: {detail or 'no diagnostic'}"
            )
        return process

    def _ref_sha(self, branch: str, field: str) -> str | None:
        safe_branch = _validate_ref_component(branch, field)
        process = self._git(
            ("show-ref", "--verify", "--hash", f"refs/heads/{safe_branch}"),
            field=field,
            # Git returns 1 or 128 (version-dependent) for a syntactically valid missing ref.
            # The ref component was independently validated above, so either means "absent."
            allowed_returncodes=frozenset({0, 1, 128}),
        )
        if process.returncode != 0:
            return None
        value = process.stdout.decode("ascii", errors="strict").strip()
        if not _SHA_RE.fullmatch(value):
            raise ResumeObservationError(field, f"unexpected SHA output {value!r}")
        return value

    def _worktree(self) -> tuple[WorktreeChange, ...]:
        output = self._git(
            ("status", "--porcelain=v1", "-z", "--untracked-files=all"),
            field="working_tree",
        ).stdout
        fields = output.decode("utf-8", errors="surrogateescape").split("\0")
        changes: list[WorktreeChange] = []
        index = 0
        while index < len(fields):
            record = fields[index]
            index += 1
            if not record:
                continue
            if len(record) < 4 or record[2] != " ":
                raise ResumeObservationError("working_tree", f"malformed porcelain {record!r}")
            x, y, path = record[0], record[1], record[3:]
            original: str | None = None
            if x in {"R", "C"} or y in {"R", "C"}:
                if index >= len(fields) or not fields[index]:
                    raise ResumeObservationError(
                        "working_tree", f"missing rename source for {record!r}"
                    )
                original = fields[index]
                index += 1
            changes.append(WorktreeChange(x, y, path, original))
        return tuple(changes)

    def observe(
        self,
        *,
        stage_contract_path: str,
        baseline_branch: str,
        planned_branch: str,
    ) -> ResumeObservation:
        repository_exists = self._repository.is_dir()
        if not repository_exists:
            return ResumeObservation(
                canonical_repository_path=str(self._repository),
                repository_exists=False,
                is_git_repository=False,
                observed_repository_identity=None,
                current_branch=None,
                head_sha=None,
                baseline_sha=None,
                planned_branch_sha=None,
                baseline_is_ancestor_of_planned=None,
                worktree_changes=(),
                canonical_contract_path="",
                contract_exists=False,
                contract_hash=None,
                engine_version=running_engine_version(),
            )

        is_git = (
            self._git(
                ("rev-parse", "--is-inside-work-tree"),
                field="git_repository",
                allowed_returncodes=frozenset({0, 128}),
            ).stdout.strip()
            == b"true"
        )
        if not is_git:
            return ResumeObservation(
                canonical_repository_path=str(self._repository),
                repository_exists=True,
                is_git_repository=False,
                observed_repository_identity=None,
                current_branch=None,
                head_sha=None,
                baseline_sha=None,
                planned_branch_sha=None,
                baseline_is_ancestor_of_planned=None,
                worktree_changes=(),
                canonical_contract_path="",
                contract_exists=False,
                contract_hash=None,
                engine_version=running_engine_version(),
            )

        remote_name = _validate_ref_component(self._config.remote_name, "remote_name")
        remote_process = self._git(
            ("config", "--get", f"remote.{remote_name}.url"),
            field="repository_identity",
            allowed_returncodes=frozenset({0, 1}),
        )
        remote = (
            remote_process.stdout.decode("utf-8", errors="strict").strip()
            if remote_process.returncode == 0
            else None
        )
        branch_process = self._git(
            ("symbolic-ref", "--quiet", "--short", "HEAD"),
            field="current_branch",
            allowed_returncodes=frozenset({0, 1}),
        )
        current_branch = (
            branch_process.stdout.decode("utf-8", errors="strict").strip()
            if branch_process.returncode == 0
            else None
        )
        head = (
            self._git(("rev-parse", "--verify", "HEAD^{commit}"), field="head_sha")
            .stdout.decode("ascii", errors="strict")
            .strip()
        )
        if not _SHA_RE.fullmatch(head):
            raise ResumeObservationError("head_sha", f"unexpected SHA output {head!r}")

        baseline_sha = self._ref_sha(baseline_branch, "baseline_commit_sha")
        planned_sha = self._ref_sha(planned_branch, "planned_stage_branch")
        ancestor: bool | None = None
        if baseline_sha is not None and planned_sha is not None:
            ancestry = self._git(
                ("merge-base", "--is-ancestor", baseline_sha, planned_sha),
                field="planned_branch_ancestry",
                allowed_returncodes=frozenset({0, 1}),
            )
            ancestor = ancestry.returncode == 0

        contract_directory = (self._repository / self._config.stage_contract_directory).resolve()
        relative = PurePosixPath(stage_contract_path)
        contract_path = (self._repository / Path(relative)).resolve()
        if relative.is_absolute() or ".." in relative.parts:
            raise ResumeObservationError(
                "stage_contract_path", f"unsafe contract path {stage_contract_path!r}"
            )
        if not contract_path.is_relative_to(contract_directory):
            raise ResumeObservationError(
                "stage_contract_path",
                f"{contract_path} is outside configured contract directory {contract_directory}",
            )
        exists = contract_path.is_file()
        digest = f"sha256:{sha256(contract_path.read_bytes()).hexdigest()}" if exists else None
        return ResumeObservation(
            canonical_repository_path=str(self._repository),
            repository_exists=True,
            is_git_repository=True,
            observed_repository_identity=remote,
            current_branch=current_branch,
            head_sha=head,
            baseline_sha=baseline_sha,
            planned_branch_sha=planned_sha,
            baseline_is_ancestor_of_planned=ancestor,
            worktree_changes=self._worktree(),
            canonical_contract_path=str(contract_path),
            contract_exists=exists,
            contract_hash=digest,
            engine_version=running_engine_version(),
        )
