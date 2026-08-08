"""Read-only Git evidence for the AUTO-016 milestone runner.

Contract: `docs/workflow-automation/stage-prompts/AUTO-016.md` (Revision 4) section 20 surface 1
of 2, section 4 entry conditions 1-5, section 11 (repository identity), section 15 (branch, HEAD
and identity are re-read at each gate) and section 22 invariants 4, 8 and 13.

This module is one of the two Git surfaces the contract admits, and it is the read-only one. It
observes a worktree and reports what it saw; it changes nothing about that worktree, and it has
no code path that could. The gated surface is a separate module owned by a separate milestone,
and nothing here reaches it.

Argv shapes, not policy comments
--------------------------------
`SECURITY_MODEL.md` section 2 requires "argv shapes that make the forbidden operations
unreachable, not merely policy comments", and section 20 requires the same of this module
specifically. :data:`_ARGV_FORMS` is therefore a closed tuple of **complete** argument vectors,
and :meth:`GitReadOnlyInspector._run` accepts a vector only if it is one of them verbatim. There
is no caller-supplied subcommand, no caller-supplied flag and no interpolated argument anywhere
in the surface: a state-changing operation is not something this module refuses, it is something
this module has no vector for. :data:`READ_ONLY_GIT_SUBCOMMANDS` is derived from those vectors
rather than declared beside them, so the two can never disagree.

This is the structural half of the correction of prototype defect P-5, where the state-changing
operations called the raw subprocess helper directly and bypassed the allowlisted wrapper
entirely, leaving the guarantee resting on configuration defaults rather than on structure.

Repository identity
-------------------
`<repository-id>` is derived exactly as AUTO-015 fixed it (DEC-002/DEC-010): the normalized
repository name, the `--` separator, and the first twelve hexadecimal characters of SHA-256 over
the canonical, credential-free primary remote identity. The derivation is reproduced here rather
than imported: contract section 24 permits `successor_planning` to be read for pattern reuse and
imported in exactly one case, `redaction.redact_text`, and this is not that case. Deriving from
the remote and never from a local filesystem path is what makes two working copies of one
repository share one identity, and one directory renamed on disk keep it.
"""

import hashlib
import os
import re
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar, Final
from urllib.parse import urlsplit

from pydantic import Field, field_validator

from ai_workflow_engine.exceptions import WorkflowEngineError
from ai_workflow_engine.milestone_runner.models import (
    MAX_IDENTIFIER_CHARS,
    MAX_ROOT_PATH_CHARS,
    MilestoneRunnerModel,
    StopReason,
    normalize_repository_path,
)

#: Every argument vector this module can build, in full. Each is a fixed tuple: no element is
#: interpolated, no element comes from a caller, and the set is closed. A vector that is not
#: literally one of these is refused by :meth:`GitReadOnlyInspector._run` before a process is
#: started, so the read-only guarantee is a property of the shapes rather than of a review of the
#: call sites.
_ARGV_FORMS: Final[tuple[tuple[str, ...], ...]] = (
    ("rev-parse", "--is-inside-work-tree"),
    ("rev-parse", "--show-toplevel"),
    ("rev-parse", "--verify", "HEAD"),
    ("symbolic-ref", "--quiet", "--short", "HEAD"),
    ("status", "--porcelain=v1", "-z", "--untracked-files=all"),
    ("config", "--get", "remote.origin.url"),
)

#: The read-only subcommand allowlist of section 20, derived from :data:`_ARGV_FORMS` so it
#: describes what this module can actually run rather than what someone once intended it to run.
#: Membership here is necessary and never sufficient: `--get` is what makes the `config` vector a
#: read, and the vector -- not the subcommand -- is the authority.
READ_ONLY_GIT_SUBCOMMANDS: frozenset[str] = frozenset(form[0] for form in _ARGV_FORMS)

#: The largest output any vector above is expected to produce. A worktree carrying more changed
#: paths than this is not something to guess about.
MAX_GIT_OUTPUT_BYTES: Final = 8 << 20

#: The largest governing contract this module will digest.
MAX_CONTRACT_BYTES: Final = 8 << 20

#: How long any single observation may take. Bounded because every observation is taken at a
#: gate, and a gate that can hang forever is not a gate.
DEFAULT_OBSERVATION_TIMEOUT_SECONDS: Final = 60

#: The first twelve hexadecimal digest characters of DEC-010's identity, and the separator that
#: joins them to the normalized name.
_IDENTITY_DIGEST_CHARS: Final = 12
_IDENTITY_SEPARATOR: Final = "--"

_MAX_REMOTE_URL_CHARS: Final = 2_048
_MAX_NORMALIZED_NAME_CHARS: Final = 100

_SCP_LIKE_RE = re.compile(r"(?:(?P<user>[^@/]+)@)?(?P<host>[^:/@]+):(?P<path>.+)")
_REMOTE_PATH_SEGMENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_NORMALIZED_NAME_SUBSTITUTION_RE = re.compile(r"[^a-z0-9]+")
_OBJECT_ID_RE = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_SHA256_HEX_RE = re.compile(r"[0-9a-f]{64}")
_IDENTITY_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*--[0-9a-f]{12}")

#: Scheme-default ports, dropped from the canonical identity so `https://host:443/o/r` and
#: `https://host/o/r` are one repository rather than two.
_DEFAULT_PORTS: Final[dict[str, int]] = {"https": 443, "http": 80, "ssh": 22, "git": 9418}


class GitInspectionError(WorkflowEngineError):
    """A read-only observation could not be taken, or its result was unusable."""


class RepositoryIdentityError(GitInspectionError):
    """The canonical repository identity could not be derived from the primary remote.

    Fails closed rather than falling back to a local filesystem path: an identity derived from
    wherever a working copy happens to live is not an identity, and section 11 binds the external
    artifact root to this value.
    """

    stop_reason: ClassVar[StopReason] = StopReason.REPOSITORY_IDENTITY_MISMATCH


class ContractPinMismatch(GitInspectionError):
    """The governing contract's digest differs from the pin the configuration records.

    Section 4 item 1 pins the contract by SHA-256 precisely so the document the runner reads is
    provably the document that was authorized. The contract names no stop code for this
    condition, so none is invented: the failure is typed by this class and left uncoded.
    """


def normalized_repository_name(name: str) -> str:
    """Return the lowercase, dash-joined form of a repository name (DEC-010).

    Runs of characters outside `[a-z0-9]` collapse to a single `-`, so the normalized name can
    never itself contain the `--` separator that joins it to the digest.
    """
    normalized = _NORMALIZED_NAME_SUBSTITUTION_RE.sub("-", name.lower()).strip("-")
    if not normalized:
        raise RepositoryIdentityError(f"The repository name {name!r} normalizes to nothing")
    if len(normalized) > _MAX_NORMALIZED_NAME_CHARS:
        raise RepositoryIdentityError(
            f"The normalized repository name exceeds {_MAX_NORMALIZED_NAME_CHARS} characters"
        )
    return normalized


def canonical_remote_identity(remote_url: str) -> str:
    """Return `<authority>/<owner>/<name>` for `remote_url`, credential-free (DEC-010).

    Any userinfo is dropped, the host is lowercased, a scheme-default port is dropped and a
    trailing `.git` is removed, so every spelling of one remote yields one identity. A remote
    naming no host -- a bare local path, or a `file://` URL -- is ambiguous identity and is
    refused rather than silently bound to wherever this working copy happens to live.
    """
    value = remote_url.strip()
    if not value:
        raise RepositoryIdentityError("The primary remote identity must not be empty")
    if len(value) > _MAX_REMOTE_URL_CHARS:
        raise RepositoryIdentityError(
            f"The primary remote identity exceeds {_MAX_REMOTE_URL_CHARS} characters"
        )
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise RepositoryIdentityError(
            "The primary remote identity must not contain a control character"
        )

    scheme = ""
    port: int | None = None
    if "://" in value:
        parsed = urlsplit(value)
        scheme = parsed.scheme.lower()
        if scheme == "file":
            raise RepositoryIdentityError(
                "A file:// remote names a local filesystem path, which never participates in "
                "the canonical repository identity"
            )
        host = (parsed.hostname or "").lower()
        try:
            port = parsed.port
        except ValueError as exc:
            raise RepositoryIdentityError(
                f"The primary remote identity has an unusable port: {exc}"
            ) from exc
        raw_path = parsed.path
    else:
        scp_like = _SCP_LIKE_RE.fullmatch(value)
        if scp_like is None:
            raise RepositoryIdentityError(
                "The primary remote identity is neither a URL nor an scp-like Git address, so "
                "it names a local filesystem path and cannot yield a repository identity"
            )
        host = scp_like.group("host").lower()
        raw_path = scp_like.group("path")

    if not host:
        raise RepositoryIdentityError(
            "The primary remote identity names no host, so it is a local filesystem path"
        )
    if port is not None and _DEFAULT_PORTS.get(scheme) == port:
        port = None

    segments = [segment for segment in raw_path.split("/") if segment]
    if segments and segments[-1].endswith(".git"):
        segments[-1] = segments[-1][: -len(".git")]
    if len(segments) < 2:
        raise RepositoryIdentityError(
            "The primary remote identity must name both an owner and a repository name"
        )
    for segment in segments:
        if _REMOTE_PATH_SEGMENT_RE.fullmatch(segment) is None:
            raise RepositoryIdentityError(
                f"The primary remote identity has an unusable path segment {segment!r}"
            )

    authority = host if port is None else f"{host}:{port}"
    return f"{authority}/{'/'.join(segments)}"


def derive_repository_identity(remote_url: str) -> str:
    """Return `<normalized-name>--<first 12 hex of SHA-256(canonical identity)>` (DEC-010).

    This is the single identity derivation section 11 fixes, and the one both the plan root and
    the run root are addressed by, so plan input and run output land under one directory that one
    containment check governs.
    """
    identity = canonical_remote_identity(remote_url)
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:_IDENTITY_DIGEST_CHARS]
    name = normalized_repository_name(identity.rsplit("/", 1)[-1])
    return f"{name}{_IDENTITY_SEPARATOR}{digest}"


class RepositoryEvidence(MilestoneRunnerModel):
    """One independent observation of the worktree, taken at one moment.

    `MACHINE_GATES.md` section 2a is why this is a record of what was *observed* rather than a
    restatement of what was configured: observations are obtained independently, and
    "caller-copied authorization strings are never live evidence". Every field here came from a
    vector in :data:`_ARGV_FORMS`.

    `changed_paths` counts untracked files as changed paths, and a renamed path contributes both
    sides, because section 15's guard has to see the whole of what a provider did.
    """

    repository_root: str
    repository_identity: str
    branch: str
    head_sha: str
    changed_paths: list[str] = Field(default_factory=list)

    @field_validator("repository_root")
    @classmethod
    def _validate_repository_root(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("repository_root must be an absolute POSIX path")
        if len(value) > MAX_ROOT_PATH_CHARS:
            raise ValueError(f"repository_root must be at most {MAX_ROOT_PATH_CHARS} characters")
        return value

    @field_validator("repository_identity")
    @classmethod
    def _validate_repository_identity(cls, value: str) -> str:
        if _IDENTITY_RE.fullmatch(value) is None:
            raise ValueError("repository_identity must be a canonical DEC-010 repository id")
        return value

    @field_validator("branch")
    @classmethod
    def _validate_branch(cls, value: str) -> str:
        if not value or len(value) > MAX_IDENTIFIER_CHARS:
            raise ValueError("branch must be a bounded, non-empty ref name")
        return value

    @field_validator("head_sha")
    @classmethod
    def _validate_head_sha(cls, value: str) -> str:
        if _OBJECT_ID_RE.fullmatch(value) is None:
            raise ValueError("head_sha must be a 40- or 64-character lowercase Git object id")
        return value

    @field_validator("changed_paths")
    @classmethod
    def _validate_changed_paths(cls, value: list[str]) -> list[str]:
        normalized = sorted(
            {
                normalize_repository_path(item, f"changed_paths[{index}]")
                for index, item in enumerate(value)
            },
            key=lambda item: item.encode("utf-8"),
        )
        return normalized


class RepositoryDrift(MilestoneRunnerModel):
    """One difference between what the run was pinned to and what the worktree now shows.

    Each aspect is a distinct typed failure with its own stop code -- section 4 items 2, 3 and 4
    -- so an operator reading a stop record can tell "someone changed branch" from "HEAD moved"
    from "this is a different repository". They are reported together rather than one at a time,
    because all three are observed in one pass.
    """

    aspect: str
    stop_reason: StopReason
    expected: str
    observed: str


class GitReadOnlyInspector:
    """Section 20 surface 1: every read-only observation the runner is allowed to take.

    Used by every state, gate and coordinator. It holds a worktree path and an observation
    timeout, and it can run exactly the six vectors of :data:`_ARGV_FORMS`. It never writes to
    the worktree, never touches the object database, never reaches the network and constructs no
    argument vector from caller input.
    """

    def __init__(
        self,
        repository_root: Path,
        *,
        timeout_seconds: int = DEFAULT_OBSERVATION_TIMEOUT_SECONDS,
    ) -> None:
        if timeout_seconds <= 0:
            raise GitInspectionError("The observation timeout must be a positive number of seconds")
        self.repository_root = repository_root
        self.timeout_seconds = timeout_seconds

    # -- the single process boundary ----------------------------------------------------

    def _run(self, argv: tuple[str, ...]) -> str:
        """Run one vector from :data:`_ARGV_FORMS` and return its stdout.

        The membership test is on the whole vector, not on its first element, which is what makes
        the surface closed: a vector this module did not declare is refused before a process
        exists. No shell is involved -- the argument list is passed to `subprocess.run` as a list,
        and there is no `shell=True` path in this package at all (invariant 3).
        """
        if argv not in _ARGV_FORMS:
            raise GitInspectionError(
                f"{list(argv)!r} is not one of this inspector's declared read-only vectors"
            )
        environment = os.environ.copy()
        # The observations below never need a lock, and taking one would let a read perturb a
        # worktree the runner is guarding.
        environment["GIT_OPTIONAL_LOCKS"] = "0"
        try:
            process = subprocess.run(
                ["git", "--no-optional-locks", "-C", str(self.repository_root), *argv],
                check=False,
                capture_output=True,
                env=environment,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise GitInspectionError(
                f"git {argv[0]} exceeded {self.timeout_seconds}s in {self.repository_root}"
            ) from exc
        except OSError as exc:
            raise GitInspectionError(f"Unable to execute Git: {exc}") from exc
        if process.returncode != 0:
            raise GitInspectionError(
                f"git {argv[0]} failed in {self.repository_root}: {process.stderr.strip()}"
            )
        if len(process.stdout.encode("utf-8")) > MAX_GIT_OUTPUT_BYTES:
            raise GitInspectionError(
                f"git {argv[0]} produced more than {MAX_GIT_OUTPUT_BYTES} bytes"
            )
        return process.stdout

    # -- individual observations ---------------------------------------------------------

    def is_worktree(self) -> bool:
        """Whether the configured root resolves to a real Git worktree (section 4 item 2)."""
        try:
            return self._run(("rev-parse", "--is-inside-work-tree")).strip() == "true"
        except GitInspectionError:
            return False

    def worktree_root(self) -> Path:
        """The worktree's own top-level directory, as Git reports it."""
        return Path(self._run(("rev-parse", "--show-toplevel")).strip())

    def branch(self) -> str | None:
        """The branch `HEAD` names, or `None` when `HEAD` names no branch.

        `None` is a real answer rather than an error: section 4 item 3 requires the branch to
        equal the configured one exactly, and "there is no branch" is one of the ways that fails.
        """
        try:
            value = self._run(("symbolic-ref", "--quiet", "--short", "HEAD")).strip()
        except GitInspectionError:
            return None
        return value or None

    def head_sha(self) -> str:
        """The object id `HEAD` currently resolves to (section 4 item 4)."""
        value = self._run(("rev-parse", "--verify", "HEAD")).strip()
        if _OBJECT_ID_RE.fullmatch(value) is None:
            raise GitInspectionError(f"HEAD resolved to an unusable object id {value!r}")
        return value

    def primary_remote_url(self) -> str:
        """The primary remote's configured URL, read with `--get` and nothing else."""
        value = self._run(("config", "--get", "remote.origin.url")).strip()
        if not value:
            raise RepositoryIdentityError(
                f"{self.repository_root} declares no primary remote, so it has no canonical "
                "repository identity"
            )
        return value

    def repository_identity(self) -> str:
        """The canonical DEC-010 repository identity of this worktree (section 11)."""
        return derive_repository_identity(self.primary_remote_url())

    def changed_paths(self) -> list[str]:
        """Every repository-relative path the worktree currently differs on (section 15).

        Untracked files count -- `--untracked-files=all` lists them individually rather than
        collapsing a directory -- and a renamed or copied entry contributes **both** sides, so a
        path that left one location and a path that arrived at another are two changed paths and
        neither hides behind the other.

        The `-z` form is used because a path may contain any byte but NUL; the human-readable
        form quotes and escapes, and parsing that back is how a guard mis-reads a hostile
        filename.
        """
        raw = self._run(("status", "--porcelain=v1", "-z", "--untracked-files=all"))
        records = raw.split("\0")
        paths: list[str] = []
        index = 0
        while index < len(records):
            record = records[index]
            index += 1
            if not record:
                continue
            if len(record) < 4 or record[2] != " ":
                raise GitInspectionError(f"Unparseable status record {record!r}")
            flags, path = record[:2], record[3:]
            paths.append(path)
            if "R" in flags or "C" in flags:
                # The second field of a rename or copy record is the other side of it.
                if index >= len(records) or not records[index]:
                    raise GitInspectionError(f"Status record {record!r} names no second path")
                paths.append(records[index])
                index += 1
        return sorted(
            {normalize_repository_path(path, "changed_path") for path in paths},
            key=lambda item: item.encode("utf-8"),
        )

    def evidence(self) -> RepositoryEvidence:
        """Take one complete, independent observation of the worktree.

        Every field is read now. Nothing is carried over from a previous observation and nothing
        is copied from configuration, because a gate that compares configuration against itself
        proves nothing.
        """
        branch = self.branch()
        if branch is None:
            raise GitInspectionError(
                f"HEAD in {self.repository_root} names no branch, so there is no branch to "
                "compare against the configured one"
            )
        return RepositoryEvidence(
            repository_root=str(self.worktree_root()),
            repository_identity=self.repository_identity(),
            branch=branch,
            head_sha=self.head_sha(),
            changed_paths=self.changed_paths(),
        )

    def detect_drift(
        self,
        *,
        expected_identity: str,
        expected_branch: str,
        expected_head_sha: str,
    ) -> tuple[RepositoryDrift, ...]:
        """Report every difference between the pinned expectation and a fresh observation.

        Three independent aspects, three distinct stop codes, one pass: identity
        (`REPOSITORY_IDENTITY_MISMATCH`), branch (`BRANCH_MISMATCH`) and `HEAD`
        (`HEAD_DRIFT`). An empty tuple means all three matched at the moment of observation --
        section 15 requires this to be re-taken at every gate rather than remembered.
        """
        drifts: list[RepositoryDrift] = []

        try:
            observed_identity = self.repository_identity()
        except RepositoryIdentityError as exc:
            observed_identity = f"<undeterminable: {exc}>"
        if observed_identity != expected_identity:
            drifts.append(
                RepositoryDrift(
                    aspect="repository_identity",
                    stop_reason=StopReason.REPOSITORY_IDENTITY_MISMATCH,
                    expected=expected_identity,
                    observed=observed_identity,
                )
            )

        observed_branch = self.branch()
        if observed_branch != expected_branch:
            drifts.append(
                RepositoryDrift(
                    aspect="branch",
                    stop_reason=StopReason.BRANCH_MISMATCH,
                    expected=expected_branch,
                    observed=observed_branch if observed_branch is not None else "<no branch>",
                )
            )

        try:
            observed_head = self.head_sha()
        except GitInspectionError as exc:
            observed_head = f"<unreadable: {exc}>"
        if observed_head != expected_head_sha:
            drifts.append(
                RepositoryDrift(
                    aspect="head_sha",
                    stop_reason=StopReason.HEAD_DRIFT,
                    expected=expected_head_sha,
                    observed=observed_head,
                )
            )

        return tuple(drifts)

    # -- the pinned governing contract ---------------------------------------------------

    def contract_digest(self, relative_path: str) -> str:
        """SHA-256 over the governing contract at `relative_path` inside the worktree.

        Every component of the path is opened with `O_NOFOLLOW` after an explicit link check, so
        a symlinked component is refused rather than followed (invariant 8), and the read is
        bounded. The file is read and hashed; it is never opened for writing, and the contract is
        never writable surface (`config.RunnerConfig` refuses a configuration that says it is).
        """
        normalized = normalize_repository_path(relative_path, "contract_path")
        root = self.worktree_root()
        target = root / normalized
        _reject_symlink_components(target, root, "The governing contract")
        try:
            descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError as exc:
            raise GitInspectionError(f"Cannot read the governing contract {target}: {exc}") from exc
        try:
            with os.fdopen(descriptor, "rb") as handle:
                payload = handle.read(MAX_CONTRACT_BYTES + 1)
        except OSError as exc:
            raise GitInspectionError(f"Cannot read the governing contract {target}: {exc}") from exc
        if len(payload) > MAX_CONTRACT_BYTES:
            raise GitInspectionError(
                f"The governing contract {target} exceeds {MAX_CONTRACT_BYTES} bytes"
            )
        return hashlib.sha256(payload).hexdigest()

    def verify_contract_pin(self, relative_path: str, expected_sha256: str) -> str:
        """Verify the governing contract against its configured pin (section 4 item 1).

        Returns the digest it computed, so a caller can record the value it actually verified
        rather than the value it expected. A difference raises :class:`ContractPinMismatch`: the
        runner never authorizes the stage it implements, so a contract that is not byte-for-byte
        the pinned one is not evidence of anything.
        """
        if _SHA256_HEX_RE.fullmatch(expected_sha256) is None:
            raise GitInspectionError(
                "The expected contract digest must be 64 lowercase hexadecimal characters"
            )
        digest = self.contract_digest(relative_path)
        if digest != expected_sha256:
            raise ContractPinMismatch(
                f"The governing contract {relative_path} digests to {digest}, not to the pinned "
                f"{expected_sha256}"
            )
        return digest


def _reject_symlink_components(target: Path, root: Path, label: str) -> None:
    """Refuse `target` if any component at or below `root` is a symbolic link (invariant 8).

    Checked from `root` downwards with `lstat`, so no component is followed to decide whether it
    should have been followed. A component that does not exist yet is not a link, and the open
    that follows this check reports its absence.
    """
    relative = Path(os.path.relpath(target, root))
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise GitInspectionError(f"{label} path component {current} is a symbolic link")


def read_only_subcommands() -> Sequence[str]:
    """The sorted read-only subcommand allowlist, for a caller that wants to display it."""
    return sorted(READ_ONLY_GIT_SUBCOMMANDS)
