"""Fixed-argv, read-only local observations used exclusively to independently verify AUTO-002
reconciliation evidence (AUTO002-F07; Human Owner decision 2026-07-27, "AUTO002-F07 evidence
verification scope").

This narrowly extends the same DD-14 local-observation boundary `observation/local.py` already
established for resume: only local Git facts and local filesystem facts a caller could not
simply assert are ever consulted, and only through this fixed, allowlisted set of read-only
operations. No arbitrary subprocess API is added, no mutable Git command is authorized, and no
network or GitHub access is performed here — remote-ref and pull-request evidence are not locally
observable at all and are rejected by the caller (`engine.py`) before this module is even
consulted for them.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

_GIT_TIMEOUT_SECONDS = 10
_SHA_RE = re.compile(r"[0-9a-f]{40}")
_PATH_COMPONENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


class LocalEvidenceObservationError(Exception):
    """A local fact required to independently verify reconciliation evidence could not be safely
    observed — the repository is missing or not a Git repository, a Git invocation failed or
    timed out, or an evidence-artifact reference is unsafe or does not resolve to an existing
    regular file. Distinct from evidence simply failing verification once observed (a normal,
    expected outcome, not an observation error).
    """

    def __init__(self, field: str, detail: str) -> None:
        self.field = field
        self.detail = detail
        super().__init__(f"Unable to observe {field}: {detail}")


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
        raise LocalEvidenceObservationError(field, f"unsafe Git ref name {value!r}")
    return value


def _validate_path_component(value: str, field: str) -> str:
    if not _PATH_COMPONENT_RE.fullmatch(value):
        raise LocalEvidenceObservationError(field, f"{value!r} is not a safe single path component")
    return value


class LocalEvidenceObserver:
    """Fixed, allowlisted, read-only local Git operations used exclusively to independently
    verify AUTO-002 reconciliation evidence — never to collect it, never to mutate the
    repository, and never to reach the network."""

    def __init__(self, repository_path: Path) -> None:
        self._repository = repository_path.resolve()

    def _git(
        self,
        args: tuple[str, ...],
        *,
        field: str,
        allowed_returncodes: frozenset[int] = frozenset({0}),
    ) -> subprocess.CompletedProcess[bytes]:
        if not self._repository.is_dir():
            raise LocalEvidenceObservationError(
                field, f"{self._repository} does not exist or is not a directory"
            )
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
            raise LocalEvidenceObservationError(field, str(exc)) from exc
        if process.returncode not in allowed_returncodes:
            detail = process.stderr.decode("utf-8", errors="replace").strip()
            raise LocalEvidenceObservationError(
                field, f"git returned {process.returncode}: {detail or 'no diagnostic'}"
            )
        return process

    def commit_exists(self, commit_sha: str) -> bool:
        """Whether `commit_sha` names a real, locally-present commit object — never trusted from
        a caller's claim alone."""
        if not _SHA_RE.fullmatch(commit_sha):
            return False
        process = self._git(
            ("cat-file", "-e", f"{commit_sha}^{{commit}}"),
            field="commit_exists",
            allowed_returncodes=frozenset({0, 1, 128}),
        )
        return process.returncode == 0

    def tree_sha(self, commit_sha: str) -> str | None:
        """The commit's actual tree SHA, independently recomputed by Git — `None` if the commit
        does not exist locally. Never the caller-supplied value echoed back."""
        if not self.commit_exists(commit_sha):
            return None
        process = self._git(
            ("rev-parse", "--verify", f"{commit_sha}^{{tree}}"),
            field="tree_sha",
            allowed_returncodes=frozenset({0, 128}),
        )
        if process.returncode != 0:
            return None
        value = process.stdout.decode("ascii", errors="strict").strip()
        if not _SHA_RE.fullmatch(value):
            raise LocalEvidenceObservationError("tree_sha", f"unexpected output {value!r}")
        return value

    def commit_reachable_from_branch(self, *, commit_sha: str, branch: str) -> bool:
        """Whether `commit_sha` is `branch`'s tip or an ancestor of it, per local history —
        independently observed, never assumed from the caller's `stage_branch` label alone."""
        if not _SHA_RE.fullmatch(commit_sha):
            return False
        safe_branch = _validate_ref_component(branch, "stage_branch")
        process = self._git(
            ("merge-base", "--is-ancestor", commit_sha, f"refs/heads/{safe_branch}"),
            field="stage_branch",
            allowed_returncodes=frozenset({0, 1, 128}),
        )
        return process.returncode == 0

    def branch_tip(self, branch: str) -> str | None:
        """Return the exact local branch tip, or ``None`` when the branch does not exist."""
        safe_branch = _validate_ref_component(branch, "stage_branch")
        process = self._git(
            ("rev-parse", "--verify", f"refs/heads/{safe_branch}^{{commit}}"),
            field="stage_branch",
            allowed_returncodes=frozenset({0, 128}),
        )
        if process.returncode != 0:
            return None
        value = process.stdout.decode("ascii", errors="strict").strip()
        if not _SHA_RE.fullmatch(value):
            raise LocalEvidenceObservationError("stage_branch", f"unexpected output {value!r}")
        return value

    def changed_paths(self, *, baseline_sha: str, head_sha: str) -> tuple[str, ...]:
        """Return the exact sorted path set changed between two locally present commits."""
        if not _SHA_RE.fullmatch(baseline_sha) or not _SHA_RE.fullmatch(head_sha):
            raise LocalEvidenceObservationError("changed_paths", "malformed commit SHA")
        process = self._git(
            ("diff", "--name-only", "-z", baseline_sha, head_sha, "--"),
            field="changed_paths",
        )
        paths = process.stdout.decode("utf-8", errors="surrogateescape").split("\0")
        return tuple(sorted(path for path in paths if path))


def read_evidence_artifact(
    *, audit_root: Path, workflow_id: str, operation_id: str, artifact_name: str
) -> bytes:
    """Read one exact workflow/operation artifact through an ``O_NOFOLLOW`` descriptor walk."""
    for field, value in (
        ("workflow_id", workflow_id),
        ("operation_id", operation_id),
        ("artifact_name", artifact_name),
    ):
        _validate_path_component(value, field)
    root = audit_root.resolve()
    try:
        current_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    except OSError as exc:
        raise LocalEvidenceObservationError("audit_root", str(exc)) from exc
    try:
        for field, component in (
            ("workflow_id", workflow_id),
            ("evidence_directory", "evidence"),
            ("operation_id", operation_id),
        ):
            try:
                next_fd = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=current_fd,
                )
            except OSError as exc:
                raise LocalEvidenceObservationError(
                    field, f"unsafe or missing directory component {component!r}"
                ) from exc
            os.close(current_fd)
            current_fd = next_fd
        try:
            artifact_fd = os.open(artifact_name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=current_fd)
        except OSError as exc:
            raise LocalEvidenceObservationError(
                "artifact_name", f"unsafe or missing artifact {artifact_name!r}"
            ) from exc
        try:
            status = os.fstat(artifact_fd)
            if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
                raise LocalEvidenceObservationError(
                    "artifact_name",
                    "artifact must be a regular, single-link file owned by this exact workflow "
                    "and operation",
                )
            chunks: list[bytes] = []
            while chunk := os.read(artifact_fd, 65536):
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            os.close(artifact_fd)
    finally:
        os.close(current_fd)


def resolve_evidence_artifact(
    *, audit_root: Path, workflow_id: str, operation_id: str, artifact_name: str
) -> Path:
    """Resolve and independently verify a workflow-owned local evidence artifact at
    `<audit_root>/<workflow_id>/evidence/<operation_id>/<artifact_name>`.

    Each of `workflow_id`/`operation_id`/`artifact_name` is validated as a single safe path
    component (no separators, no traversal token, no leading `.`/`-`) before being used to build
    a path at all — a caller-supplied path is never taken at face value. Each directory and the
    final artifact is opened descriptor-relative with `O_NOFOLLOW`; the artifact must be a
    regular, single-link file. Raises `LocalEvidenceObservationError` on any failure and returns
    the lexical confined path only after that descriptor-based verification succeeds.
    """
    read_evidence_artifact(
        audit_root=audit_root,
        workflow_id=workflow_id,
        operation_id=operation_id,
        artifact_name=artifact_name,
    )
    return audit_root.resolve() / workflow_id / "evidence" / operation_id / artifact_name
