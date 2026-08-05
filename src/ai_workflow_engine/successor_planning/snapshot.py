"""Repository identity, Git evidence, and the AUTO-015 evidence-snapshot protocol.

Contract: `docs/workflow-automation/stage-prompts/AUTO-015.md` (Revision 4) sections 7.1
(repository identity typed binding), 7.1a (canonical repository identifier and artifact
root, DEC-010), 7.2 (validation rules), 7.3 (the thirteen-step snapshot sequence), 7.4
(threat model and residual risk), 7.5 (`O_NOFOLLOW` platform note), 8 items 8-10
(configuration, Git evidence and handover evidence as required inputs), 16.2
(absolute-path normalization, filesystem-traversal sorting, locale-independent Git
parsing) and 22 invariants 1, 12, 14 and 16.

This module reads and hashes **bytes**. It parses no document: a typed reader for any
governance document, the candidate catalog, eligibility, rendering and publication all live
elsewhere. Everything here is side-effect-free apart from the process-environment override
described below.

Git access
----------
Every Git read goes through the existing read-only `GitClient` allowlist
(`src/ai_workflow_engine/git/client.py`) and the existing `check_git` validator
(`src/ai_workflow_engine/git/validators.py`), both reused unmodified. No new Git access
path is opened here, and no mutating Git subcommand appears anywhere in this module --
section 22 invariant 12, asserted structurally at the AST level by this module's test file.

`GitClient` already pins `GIT_OPTIONAL_LOCKS=0`, but section 16.2 additionally requires
Git output to be parsed independently of the invoking operator's display locale. `GitClient`
builds its child environment from `os.environ`, and `src/ai_workflow_engine/git/**` is a
forbidden surface for this stage, so the only available mechanism is to pin
`LC_ALL`/`LANG`/`LANGUAGE` in this process's own environment for the duration of the Git
reads (:func:`fixed_git_environment`). That override is scoped, restored on every exit path,
and deliberately narrow -- but it mutates process-global state and is therefore not
thread-safe, which is stated here rather than left to be discovered.

Repository identity versus repository ID
----------------------------------------
Section 7.1's `RepositoryIdentity` record and section 7.1a's canonical repository **ID** are
two separate things, and this module keeps them separate. `RepositoryIdentity` binds the
configured root, the resolved root, the Git worktree root, the Git baseline and the active
configuration's hash. The canonical repository ID is derived purely from the primary remote
identity (DEC-010) and never from a local filesystem path, so it is computed by a pure
function over a remote URL string supplied by the caller from validated configuration
(section 4 item 8's "repository identity policy"). Reading the remote URL out of Git is not
possible here: `GitClient.READ_ONLY_FORMS` admits neither `git remote` nor `git config`, and
widening that allowlist would be exactly the new, independently-audited Git access path
section 7.1 forbids.

Threats addressed, and residual risk (section 7.4, reproduced as required)
-------------------------------------------------------------------------
* **File replacement** (different content at the same path between read and publication):
  detected by re-hashing in step 11.
* **Symlink swap** (a file replaced with a symlink, or vice versa, between read and
  publication): detected by re-checking symlink status in steps 3/11, plus the device+inode
  identity check in step 4/11 catching a same-path-different-inode substitution even when
  the new target is not itself a symlink.
* **Branch/HEAD/worktree change**: detected by step 12's re-read against step 8's original
  capture.
* **Configuration change**: the active configuration's hash is part of the evidence
  (`RepositoryIdentity.config_hash`) and is re-verified in steps 11/13 like any other
  authoritative source.
* **Candidate catalog / handover / completion-report change**: all are named authoritative
  sources under section 8 and therefore covered by the same re-hash-and-compare discipline.
* **What this protocol does *not* claim.** This is **not** an OS-level atomic snapshot (no
  filesystem-level point-in-time isolation is taken; no lock is held across the read
  window). A sufficiently precisely-timed concurrent writer could in principle alter a file
  *between* an individual file's own read (step 5) and its own hash (step 7) within a single
  pass, or between two different files' reads within the same pass, producing a read that is
  individually self-consistent per file but not perfectly atomic *across* files at the same
  instant. The mitigation is not perfection but **fail-closed detection at the boundary that
  matters**: the full re-snapshot immediately before publication (steps 11-13) guarantees
  that whatever was actually published is provably identical, byte-for-byte and
  field-for-field, to a state that existed at two distinct, individually-hashed points in
  time (initial read and pre-publication check) -- it does not guarantee no third,
  intermediate state existed that neither snapshot observed. This residual risk is judged
  acceptable because (a) AUTO-015 is a local, single-operator, read-only advisory tool with
  no security boundary between the invoking operator and the repository, and (b) the
  fail-closed re-check makes exploiting the residual window require winning a race against a
  re-hash that happens immediately before the one write AUTO-015 ever performs -- not a
  standing window an attacker can probe repeatedly. This is not perfect isolation and must
  never be described as such.

`O_NOFOLLOW` platform note (section 7.5)
----------------------------------------
`O_NOFOLLOW` is a POSIX facility. Where the running platform exposes it, step 2's open is
atomically no-follow. Where it does not, this module degrades to "explicitly check
`Path.is_symlink()`, then open", which is check-then-use rather than atomically no-follow
and is a genuine residual TOCTOU gap in that narrow case -- named here as one, not silently
presented as equivalent. :data:`HAS_ATOMIC_NO_FOLLOW` reports which of the two is in force.
The same honesty applies to the containment re-check in :func:`take_snapshot`: resolving a
path and then opening it is check-then-use, and a symlinked *parent directory component* is
outside `O_NOFOLLOW`'s reach entirely (it guards only the final component). That residual
case is caught after the fact by the device+inode and content comparison of
:func:`compare_snapshots`, not before the fact by the open.
"""

import errno
import hashlib
import os
import re
import stat as stat_module
import unicodedata
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlsplit

from pydantic import field_validator, model_validator

from ai_workflow_engine.exceptions import GitCommandError, WorkflowEngineError
from ai_workflow_engine.git.client import GitClient
from ai_workflow_engine.git.models import GitStatus
from ai_workflow_engine.git.validators import check_git
from ai_workflow_engine.models import EngineConfig

# The section 14.2 field grammar lives once, in this package's typed foundation. These are
# module-private there and imported here deliberately: a second, independently maintained
# copy of the path and digest grammar inside this module would be free to drift away from
# the grammar the artifact models actually enforce, which is a worse outcome than a
# same-package private import. `models.py` is not an allowed surface for this milestone, so
# promoting them to public names is not available.
from ai_workflow_engine.successor_planning.models import (
    EvidenceReference,
    FailureCode,
    RepositoryIdentity,
    SuccessorPlanningModel,
    _hex64,
    _int64,
    _relative_path,
    _require_sorted_unique,
)

# --------------------------------------------------------------------------------------
# Section 7.3 step 5 / section 22 invariant 14 -- explicit read ceilings
# --------------------------------------------------------------------------------------

# Mirrors `agentos_workflow/skills/contract.py`'s `_MAX_CONTRACT_BYTES` ceiling exactly. The
# ceiling is applied to the size reported by `fstat` on the already-opened descriptor *and*
# again to the bytes actually returned, so a file that grows between the two fails the read
# instead of being truncated or read unboundedly.
MAX_EVIDENCE_BYTES = 4 * 1024 * 1024

# An expanded directory input is bounded too: a directory holding an unreasonable number of
# entries fails the listing rather than producing an unbounded evidence set.
MAX_DIRECTORY_ENTRIES = 4096

_NO_FOLLOW = getattr(os, "O_NOFOLLOW", 0)
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)

#: Whether step 2's open is atomically no-follow on this platform (section 7.5).
HAS_ATOMIC_NO_FOLLOW = _NO_FOLLOW != 0

# Section 16.2: Git output must not vary with the invoking operator's display locale.
# `GIT_OPTIONAL_LOCKS` repeats `GitClient`'s own discipline so a caller that inherits a
# hostile environment cannot weaken it before the child process is built.
_FIXED_GIT_ENVIRONMENT: dict[str, str] = {
    "LC_ALL": "C",
    "LANG": "C",
    "LANGUAGE": "C",
    "GIT_OPTIONAL_LOCKS": "0",
}


# --------------------------------------------------------------------------------------
# Typed, fail-closed errors (section 13 codes)
# --------------------------------------------------------------------------------------


class SnapshotError(WorkflowEngineError):
    """Base fail-closed snapshot failure, tagged with its section 13 failure code.

    Never raised directly; every concrete subclass declares exactly one `code`, so a caller
    maps an exception to a failure record without re-deriving the classification from a
    message string.
    """

    code: ClassVar[FailureCode]


class InvalidInvocationError(SnapshotError):
    """Section 7.2 rule 2: the configured repository root does not resolve."""

    code: ClassVar[FailureCode] = "INVALID_INVOCATION"


class RepositoryIdentityMismatchError(SnapshotError):
    """Section 7.2 rule 1 and DEC-010: identity does not reconcile unambiguously.

    The tool refuses to guess which of two disagreeing roots, or which of several possible
    remote identities, is authoritative.
    """

    code: ClassVar[FailureCode] = "REPOSITORY_IDENTITY_MISMATCH"


class SymlinkPolicyViolationError(SnapshotError):
    """Section 7.3 step 3: an authoritative input is a symlink and no exception exists."""

    code: ClassVar[FailureCode] = "SYMLINK_POLICY_VIOLATION"


class PathEscapeError(SnapshotError):
    """Section 22 invariant 1: a resolved path fell outside its allowed root."""

    code: ClassVar[FailureCode] = "PATH_ESCAPE"


class AuthoritativeSourceError(SnapshotError):
    """Section 13: a required document is absent, unreadable, or over its byte ceiling.

    Section 13 gives `AUTHORITATIVE_SOURCE_MISSING` the meaning "absent, unreadable, or
    fails file-level schema parsing", and section 16.2 routes a source that cannot be read
    as text at all to the same code. An over-ceiling source is unreadable *under policy*,
    which is the narrowest available reading: section 13 defines no separate size code, and
    inventing one would broaden the failure taxonomy this module is not permitted to widen.
    """

    code: ClassVar[FailureCode] = "AUTHORITATIVE_SOURCE_MISSING"


class DirtyBaselineError(SnapshotError):
    """Section 7.2 rule 4: a branch/HEAD mismatch or protected-path dirtiness finding."""

    code: ClassVar[FailureCode] = "DIRTY_BASELINE"


class UpstreamPolicyError(SnapshotError):
    """Section 7.2 rule 4: `upstream_missing` outside its one precedented tolerance."""

    code: ClassVar[FailureCode] = "UPSTREAM_POLICY_FAILURE"


class SnapshotDriftError(SnapshotError):
    """Section 7.3 step 13: the pre-publication snapshot disagrees with the initial one.

    Carries every difference found, not just the first, because the refusal record is the
    only evidence a Human Owner gets about what actually moved underneath the invocation.
    """

    code: ClassVar[FailureCode] = "INPUT_DRIFT"

    def __init__(self, differences: Sequence[str]) -> None:
        self.differences: tuple[str, ...] = tuple(differences)
        super().__init__(
            "Authoritative evidence changed between the initial and pre-publication "
            f"snapshots ({len(self.differences)} difference(s)): " + "; ".join(self.differences)
        )


# --------------------------------------------------------------------------------------
# Section 7.1a / DEC-010 -- canonical repository identifier and artifact root
# --------------------------------------------------------------------------------------

_REMOTE_PATH_SEGMENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_SCP_LIKE_RE = re.compile(r"(?:(?P<user>[^@/]+)@)?(?P<host>[A-Za-z0-9.-]+):(?P<path>[^\s].*)")
_REPOSITORY_ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*--[0-9a-f]{12}")
_NORMALIZED_NAME_SUBSTITUTION_RE = re.compile(r"[^a-z0-9]+")

# Default ports are dropped so an SSH and an HTTPS identity for the same repository, and an
# explicit `:22` against an implicit one, all normalize to the same canonical string. A
# non-default port is retained, because it genuinely names a different endpoint.
_DEFAULT_PORTS: dict[str, int] = {
    "ssh": 22,
    "git+ssh": 22,
    "ssh+git": 22,
    "git": 9418,
    "http": 80,
    "https": 443,
}

_REPOSITORY_ID_DIGEST_CHARS = 12
_MAX_REMOTE_URL_CHARS = 2048
_MAX_NORMALIZED_NAME_CHARS = 64


def canonical_remote_identity(remote_url: str) -> str:
    """Return the canonical primary-remote identity of `remote_url` (section 7.1a).

    Credentials, tokens, query parameters and fragments are excluded; equivalent SSH and
    HTTPS forms and host casing are normalized; an optional `.git` suffix is dropped; the
    repository owner and name are retained. The local filesystem path never participates, so
    a remote naming no host -- a bare local path, or a `file://` URL -- is ambiguous identity
    and fails closed rather than silently binding an identity to wherever this checkout
    happens to live.
    """
    value = remote_url.strip()
    if not value:
        raise RepositoryIdentityMismatchError("The primary remote identity must not be empty")
    if len(value) > _MAX_REMOTE_URL_CHARS:
        raise RepositoryIdentityMismatchError(
            f"The primary remote identity exceeds {_MAX_REMOTE_URL_CHARS} characters"
        )
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise RepositoryIdentityMismatchError(
            "The primary remote identity must not contain a control character"
        )

    scheme = ""
    port: int | None = None
    if "://" in value:
        parsed = urlsplit(value)
        scheme = parsed.scheme.lower()
        if scheme == "file":
            raise RepositoryIdentityMismatchError(
                "A file:// remote names a local filesystem path, which never participates "
                "in the canonical repository identity"
            )
        host = (parsed.hostname or "").lower()
        try:
            port = parsed.port
        except ValueError as exc:
            raise RepositoryIdentityMismatchError(
                f"The primary remote identity has an unusable port: {exc}"
            ) from exc
        raw_path = parsed.path
    else:
        scp_like = _SCP_LIKE_RE.fullmatch(value)
        if scp_like is None:
            raise RepositoryIdentityMismatchError(
                "The primary remote identity is neither a URL nor an scp-like Git address, "
                "so it names a local filesystem path and cannot yield a repository identity"
            )
        host = scp_like.group("host").lower()
        raw_path = scp_like.group("path")

    if not host:
        raise RepositoryIdentityMismatchError(
            "The primary remote identity names no host, so it is a local filesystem path"
        )
    if port is not None and _DEFAULT_PORTS.get(scheme) == port:
        port = None

    segments = [segment for segment in raw_path.split("/") if segment]
    if segments and segments[-1].endswith(".git"):
        segments[-1] = segments[-1][: -len(".git")]
    if len(segments) < 2:
        raise RepositoryIdentityMismatchError(
            "The primary remote identity must name both an owner and a repository name"
        )
    for segment in segments:
        if _REMOTE_PATH_SEGMENT_RE.fullmatch(segment) is None:
            raise RepositoryIdentityMismatchError(
                f"The primary remote identity has an unusable path segment {segment!r}"
            )

    authority = host if port is None else f"{host}:{port}"
    return f"{authority}/{'/'.join(segments)}"


def normalized_repository_name(name: str) -> str:
    """Return the lowercase, dash-joined form of a repository name (section 7.1a).

    Runs of characters outside `[a-z0-9]` collapse to a single `-`, so the normalized name
    can never itself contain the `--` separator that joins it to the digest.
    """
    normalized = _NORMALIZED_NAME_SUBSTITUTION_RE.sub("-", name.lower()).strip("-")
    if not normalized:
        raise RepositoryIdentityMismatchError(
            f"The repository name {name!r} normalizes to an empty identifier"
        )
    if len(normalized) > _MAX_NORMALIZED_NAME_CHARS:
        raise RepositoryIdentityMismatchError(
            f"The normalized repository name exceeds {_MAX_NORMALIZED_NAME_CHARS} characters"
        )
    return normalized


def canonical_repository_id(remote_url: str) -> str:
    """Return `<normalized-name>--<first-12-hex-of-SHA256(remote identity)>` (DEC-010).

    The digest is taken over :func:`canonical_remote_identity`'s output, so two spellings of
    the same remote produce the same ID and no local filesystem path can influence it.
    """
    identity = canonical_remote_identity(remote_url)
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:_REPOSITORY_ID_DIGEST_CHARS]
    name = normalized_repository_name(identity.rsplit("/", 1)[-1])
    return f"{name}--{digest}"


def artifact_root_for(repository_id: str) -> Path:
    """Return `~/.ai-workflow-engine/successor-proposals/<repository-id>/` (DEC-002/DEC-010).

    Pure derivation: nothing is created, resolved or verified here. The root-ownership,
    permission, containment and symlink checks of section 17.2 belong to publication, which
    is a separate concern from the snapshot protocol.
    """
    if _REPOSITORY_ID_RE.fullmatch(repository_id) is None:
        raise InvalidInvocationError(
            f"{repository_id!r} is not a canonical repository ID of the form "
            "<normalized-name>--<12 hexadecimal characters>"
        )
    return Path.home() / ".ai-workflow-engine" / "successor-proposals" / repository_id


# --------------------------------------------------------------------------------------
# Section 7.3 steps 2-7 -- the read discipline
# --------------------------------------------------------------------------------------


def sorted_directory_entries(directory: Path, label: str) -> list[str]:
    """Return `directory`'s entry names sorted byte-wise on their UTF-8 encoding.

    Section 16.2: any directory listing performed while resolving authoritative sources is
    sorted by name before use, never trusted in raw `readdir` order, which is
    filesystem-and-OS-dependent and would make an evidence set non-deterministic.
    """
    try:
        names = os.listdir(directory)
    except OSError as exc:
        raise AuthoritativeSourceError(f"{label} could not be listed: {exc}") from exc
    if len(names) > MAX_DIRECTORY_ENTRIES:
        raise AuthoritativeSourceError(
            f"{label} holds {len(names)} entries, over the {MAX_DIRECTORY_ENTRIES}-entry ceiling"
        )
    return sorted(names, key=lambda name: name.encode("utf-8"))


def read_evidence_bytes(
    path: Path,
    label: str,
    *,
    ceiling: int = MAX_EVIDENCE_BYTES,
) -> tuple[bytes, os.stat_result]:
    """Open `path` no-follow, verify it, and return its bytes with its own `fstat`.

    Implements section 7.3 steps 2-5 for one file: no-follow open, symlink refusal, stable
    identity capture from the *opened descriptor* rather than from a second path lookup, and
    an explicit byte ceiling enforced before any content is read into memory.
    """
    if not HAS_ATOMIC_NO_FOLLOW and path.is_symlink():
        # Section 7.5: the degraded, check-then-use path. Named as a residual TOCTOU gap.
        raise SymlinkPolicyViolationError(f"{label} is a symlink, which policy forbids")
    try:
        descriptor = os.open(path, os.O_RDONLY | _NO_FOLLOW | _CLOEXEC)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.EMLINK}:
            raise SymlinkPolicyViolationError(
                f"{label} is a symlink, which policy forbids"
            ) from exc
        raise AuthoritativeSourceError(f"{label} could not be opened: {exc}") from exc
    # Both checks run on the descriptor before any wrapper is built around it: a directory
    # opens cleanly for reading and only fails when it is wrapped, and the byte ceiling has to
    # be decided before a single byte is pulled into memory (section 22 invariant 14).
    metadata = os.fstat(descriptor)
    refusal: str | None = None
    if not stat_module.S_ISREG(metadata.st_mode):
        refusal = f"{label} is not a regular file"
    elif metadata.st_size > ceiling:
        refusal = f"{label} is {metadata.st_size} bytes, over the {ceiling}-byte ceiling"
    if refusal is not None:
        os.close(descriptor)
        raise AuthoritativeSourceError(refusal)
    with os.fdopen(descriptor, "rb", closefd=True) as handle:
        # One byte past the ceiling, so a file that grew between `fstat` and this read fails
        # the read instead of being silently truncated to the ceiling.
        data = handle.read(ceiling + 1)
    if len(data) > ceiling:
        raise AuthoritativeSourceError(
            f"{label} exceeded the {ceiling}-byte ceiling while being read"
        )
    return data, metadata


def normalize_evidence_text(data: bytes, label: str) -> str:
    """Return `data`'s canonical text form (section 7.3 step 6, section 16.2).

    Strict UTF-8 decode, CRLF folded to LF, then NFC. A source that cannot be decoded at all
    is `AUTHORITATIVE_SOURCE_MISSING` per section 16.2. A **bare** CR survives the fold and
    is refused rather than silently rewritten, which is how section 16.2's two halves --
    "normalized to `\\n` before hashing" and "a source containing `\\r` fails validation
    rather than being silently rewritten" -- reconcile: CRLF is a line ending and is
    normalized; a lone CR is not, and fails.
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuthoritativeSourceError(f"{label} is not valid UTF-8: {exc}") from exc
    text = text.replace("\r\n", "\n")
    if "\r" in text:
        raise AuthoritativeSourceError(
            f"{label} contains a bare carriage return outside a CRLF line ending"
        )
    return unicodedata.normalize("NFC", text)


# --------------------------------------------------------------------------------------
# Section 7.3 step 4 -- per-file stable identity
# --------------------------------------------------------------------------------------


class FileIdentity(SuccessorPlanningModel):
    """One authoritative file's stable identity and its two hashes (section 7.3 steps 4/7).

    `path` is stored relative to `resolved_repository_root`, never absolute: section 16.2's
    absolute-path normalization rule makes the evidence manifest, and therefore the proposal
    hash, independent of where the repository happens to be checked out. Step 4's "absolute
    resolved path" is reconstructible from this path and the snapshot's own
    `RepositoryIdentity.resolved_repository_root`, so nothing is lost by not storing it
    twice in a machine-dependent form.

    `device`/`inode` detect *replacement* -- a different file swapped in at the same path --
    and are never a substitute for content hashing, which is why both hashes are here too.
    `original_sha256` is the tamper/identity evidence over the exact bytes on disk;
    `normalized_sha256` is over the section 16.2 canonical text and is the digest bound into
    the evidence manifest.

    `is_symlink` is always `False` in any snapshot :func:`take_snapshot` returns, because
    section 7.3 step 3 refuses a symlinked authoritative input outright. It is recorded and
    compared anyway so the step 13 comparison is total over every attribute observed: if the
    narrow allowlisted exception section 7.3 step 3 leaves room for is ever defined, a swap
    in either direction is drift on this field rather than a silently equal record.
    """

    path: str
    device: int
    inode: int
    size: int
    mtime_ns: int
    is_symlink: bool
    original_sha256: str
    normalized_sha256: str

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        return _relative_path(value, "evidence path")

    @field_validator("device", "inode", "mtime_ns")
    @classmethod
    def _validate_identity_numbers(cls, value: int) -> int:
        if value < 0:
            raise ValueError("stable-identity metadata must not be negative")
        return _int64(value, "stable-identity metadata")

    @field_validator("size")
    @classmethod
    def _validate_size(cls, value: int) -> int:
        if value < 0:
            raise ValueError("evidence size must not be negative")
        return _int64(value, "evidence size")

    @field_validator("original_sha256", "normalized_sha256")
    @classmethod
    def _validate_digest(cls, value: str) -> str:
        return _hex64(value, "evidence digest")


class EvidenceSnapshot(SuccessorPlanningModel):
    """One internally consistent pass over the repository identity and every input file.

    Two snapshots are taken per invocation -- one at the start, one immediately before
    publication -- and compared field-for-field by :func:`compare_snapshots`.
    """

    identity: RepositoryIdentity
    files: list[FileIdentity]

    @model_validator(mode="after")
    def _validate_ordering(self) -> "EvidenceSnapshot":
        # Section 16.2 evidence ordering: sorted by path, byte-wise on the UTF-8 encoding.
        _require_sorted_unique([item.path for item in self.files], "snapshot files", "path")
        return self

    def evidence_manifest(self) -> list[EvidenceReference]:
        """Return this snapshot's `{path, sha256, size}` manifest in canonical order.

        The digest is the normalized one: section 7.3 step 7 makes the normalized hash the
        canonical evidence-manifest hash actually bound into the proposal, while the original
        hash stays in :class:`FileIdentity` as tamper evidence.
        """
        return [
            EvidenceReference(path=item.path, sha256=item.normalized_sha256, size=item.size)
            for item in self.files
        ]


# --------------------------------------------------------------------------------------
# Section 7.1 / 7.2 -- repository identity and Git evidence
# --------------------------------------------------------------------------------------


@contextmanager
def fixed_git_environment() -> Iterator[None]:
    """Pin a locale-independent environment around every Git read (section 16.2).

    Process-global and therefore not thread-safe; every entry is restored on exit, including
    on an exception path. See this module's docstring for why the override lives here rather
    than inside `GitClient`.
    """
    previous = {name: os.environ.get(name) for name in _FIXED_GIT_ENVIRONMENT}
    os.environ.update(_FIXED_GIT_ENVIRONMENT)
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


# Findings that fail closed as `DIRTY_BASELINE` (section 7.2 rule 4). `unexpected_staged_path`
# is deliberately absent: it fires for *any* staged path, and section 7.2 rule 4 states that
# AUTO-015 does not require a clean working tree to run -- it is a read-only reporting tool,
# not a stage-implementation session. Only a branch/HEAD mismatch, or dirtiness against the
# protected paths the checks are scoped to, fails closed.
_DIRTY_BASELINE_FINDINGS = frozenset(
    {
        "branch_mismatch",
        "head_mismatch",
        "protected_path_staged",
        "protected_path_would_commit",
    }
)


def _resolve_configured_root(config: EngineConfig) -> Path:
    """Section 7.3 step 1 plus section 7.2 rule 2: no-follow, then resolve strictly."""
    configured = config.project.repository
    if configured.is_symlink():
        raise SymlinkPolicyViolationError(
            f"The configured repository root {configured} is a symlink, which policy forbids"
        )
    try:
        resolved = configured.resolve(strict=True)
    except OSError as exc:
        raise InvalidInvocationError(
            f"The configured repository root {configured} does not resolve: {exc}"
        ) from exc
    if not resolved.is_dir():
        raise InvalidInvocationError(
            f"The configured repository root {configured} is not a directory"
        )
    return resolved


def _read_git_worktree_root(client: GitClient) -> Path:
    """Section 7.1: `rev-parse --show-toplevel`, through the existing read-only allowlist.

    `GitClient` exposes no public accessor for the worktree root and
    `src/ai_workflow_engine/git/**` is a forbidden surface for this stage, so the allowlisted
    runner is called directly. `rev-parse` is on `GitClient.READ_ONLY_FORMS`, so the call is
    audited by the same guard every other Git read in this repository passes through.
    """
    try:
        value = client._run(["rev-parse", "--show-toplevel"])
    except GitCommandError as exc:
        raise InvalidInvocationError(
            f"The configured repository root is not a Git worktree: {exc}"
        ) from exc
    assert isinstance(value, str)
    return Path(value.strip())


def _apply_baseline_policy(config: EngineConfig, branch: str, findings: Sequence[str]) -> None:
    """Section 7.2 rule 4: classify the reused `check_git` findings, failing closed.

    `upstream_missing` is tolerated only under the one documented, precedented condition
    every other `workflowctl verify` caller already tolerates it under: a local-only,
    intentionally unpushed working branch, which this repository's own history records as
    "a freshly created, not-yet-pushed stage branch". The configured default branch having no
    upstream is not that condition -- it is a misconfigured repository -- so it fails closed.
    `branch` is the one already observed in this capture, threaded through rather than read a
    second time, because section 7.3 step 8 permits exactly one status pass.
    """
    dirty = sorted(set(findings) & _DIRTY_BASELINE_FINDINGS)
    if dirty:
        raise DirtyBaselineError(f"The Git baseline is unusable: {', '.join(dirty)}")
    if "upstream_missing" in findings and branch == config.project.default_branch:
        raise UpstreamPolicyError(
            "The configured default branch has no upstream, which is outside the one "
            "documented tolerance for a local-only, intentionally unpushed working branch"
        )


def resolve_repository_identity(config: EngineConfig, config_path: Path) -> RepositoryIdentity:
    """Capture section 7.1's typed repository binding, failing closed on section 7.2.

    Order matters and follows section 7.2: the root resolves (rule 2), the Git worktree root
    equals it (rule 1), the Git baseline is captured verbatim (rule 3), and only then is the
    clean-tree/upstream policy applied (rule 4). `config_path` is hashed over its exact bytes
    as read, which is what binds the active configuration into the evidence (section 8 item
    8) and what makes a configuration change detectable as drift.
    """
    resolved_root = _resolve_configured_root(config)
    client = GitClient(resolved_root)

    with fixed_git_environment():
        worktree_root = _read_git_worktree_root(client)
        # Section 7.3 step 8: exactly one synchronous status pass, taken through the existing
        # `check_git` validator so the evidence and the policy findings describe the same
        # observation rather than two reads that could disagree with each other.
        git_result = check_git(config)

    if worktree_root != resolved_root:
        raise RepositoryIdentityMismatchError(
            f"The Git worktree root {worktree_root} is not the resolved repository root "
            f"{resolved_root}; the tool refuses to guess which of the two is authoritative"
        )

    state = GitStatus.model_validate(git_result.evidence)
    _apply_baseline_policy(config, state.branch, [finding.code for finding in git_result.findings])

    config_bytes, _ = read_evidence_bytes(config_path, f"The configuration {config_path}")

    return RepositoryIdentity(
        configured_repository_root=str(config.project.repository),
        resolved_repository_root=str(resolved_root),
        configured_repository_id=config.project.id,
        git_worktree_root=str(worktree_root),
        branch=state.branch,
        head_sha=state.head,
        upstream_ref=state.upstream,
        ahead=state.ahead,
        behind=state.behind,
        modified_files=state.modified_files,
        staged_files=state.staged_files,
        untracked_files=state.untracked_files,
        config_hash=hashlib.sha256(config_bytes).hexdigest(),
    )


# --------------------------------------------------------------------------------------
# Section 7.3 steps 1-8 -- one snapshot pass
# --------------------------------------------------------------------------------------


def _confine(root: Path, relative: str) -> Path:
    """Section 22 invariant 1: refuse a path that resolves outside `root`.

    `_relative_path` has already refused an absolute path and any `.`/`..` segment, so this
    guard exists for the one case the grammar cannot see: a symlinked *parent directory*
    component redirecting the path out of the repository. It is check-then-use by
    construction -- `O_NOFOLLOW` guards only the final component -- so it narrows the window
    rather than closing it, and a swap that stays inside the root is caught after the fact by
    :func:`compare_snapshots` instead.
    """
    candidate = root / relative
    real_root = os.path.realpath(root)
    real_candidate = os.path.realpath(candidate)
    if real_candidate != real_root and not real_candidate.startswith(real_root + os.sep):
        raise PathEscapeError(
            f"The authoritative input {relative!r} resolves to {real_candidate}, "
            f"outside the repository root {real_root}"
        )
    return candidate


def _expand_inputs(root: Path, relative_paths: Sequence[str]) -> list[str]:
    """Return every input as a repository-relative file path, in canonical order.

    An input naming a directory expands to that directory's own entries, one level deep and
    sorted by name (section 16.2). The expansion is strict: every entry must be a regular
    file, so a symlink or a nested directory inside an authoritative source directory fails
    closed rather than being silently skipped.
    """
    collected: set[str] = set()
    for relative in relative_paths:
        # The section 14.2 path grammar signals a violation with `ValueError`, which is the
        # right contract for a Pydantic validator and the wrong one for a caller that must map
        # every refusal to a section 13 code, so it is re-raised as the typed failure here.
        try:
            _relative_path(relative, "authoritative input path")
        except ValueError as exc:
            raise InvalidInvocationError(
                f"The authoritative input {relative!r} is not a usable repository-relative "
                f"path: {exc}"
            ) from exc
        target = _confine(root, relative)
        try:
            metadata = os.lstat(target)
        except OSError as exc:
            raise AuthoritativeSourceError(
                f"The authoritative input {relative!r} could not be inspected: {exc}"
            ) from exc
        if stat_module.S_ISLNK(metadata.st_mode):
            raise SymlinkPolicyViolationError(
                f"The authoritative input {relative!r} is a symlink, which policy forbids"
            )
        if stat_module.S_ISDIR(metadata.st_mode):
            for name in sorted_directory_entries(target, f"The input directory {relative!r}"):
                child = f"{relative}/{name}"
                try:
                    child_metadata = os.lstat(_confine(root, child))
                except OSError as exc:
                    raise AuthoritativeSourceError(
                        f"The input {child!r} could not be inspected: {exc}"
                    ) from exc
                if stat_module.S_ISLNK(child_metadata.st_mode):
                    raise SymlinkPolicyViolationError(
                        f"The input {child!r} is a symlink, which policy forbids"
                    )
                if not stat_module.S_ISREG(child_metadata.st_mode):
                    raise AuthoritativeSourceError(f"The input {child!r} is not a regular file")
                collected.add(child)
            continue
        collected.add(relative)
    return sorted(collected, key=lambda value: value.encode("utf-8"))


def _capture_file(root: Path, relative: str) -> FileIdentity:
    """Run section 7.3 steps 2-7 for one authoritative file."""
    label = f"The authoritative input {relative!r}"
    target = _confine(root, relative)
    data, metadata = read_evidence_bytes(target, label)
    normalized = normalize_evidence_text(data, label)
    return FileIdentity(
        path=relative,
        device=metadata.st_dev,
        inode=metadata.st_ino,
        size=metadata.st_size,
        mtime_ns=metadata.st_mtime_ns,
        is_symlink=False,
        original_sha256=hashlib.sha256(data).hexdigest(),
        normalized_sha256=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
    )


def take_snapshot(
    config: EngineConfig,
    config_path: Path,
    *,
    inputs: Sequence[str] = (),
) -> EvidenceSnapshot:
    """Take one internally consistent evidence pass (section 7.3 steps 1-8).

    The handover manifest and every handover file are always included, because section 8 item
    10 makes handover evidence a required input whenever the active configuration configures
    it, never an optional or corroborating one. The active configuration itself (item 8) is
    bound through `RepositoryIdentity.config_hash` rather than through the file list, since
    the configuration may legitimately live outside the repository root and section 16.2
    requires every manifest path to be repository-relative. Git evidence (item 9) is bound
    through the rest of `RepositoryIdentity`.

    Every other authoritative source of section 8 is supplied by the caller in `inputs`, as
    repository-relative paths; this module resolves, reads and hashes them but parses none of
    them.

    Called twice per invocation: once at step 1, and again at steps 11-12 immediately before
    publication. The two results are compared by :func:`compare_snapshots`.
    """
    identity = resolve_repository_identity(config, config_path)
    root = Path(identity.resolved_repository_root)
    required = [config.handover.manifest, *config.handover.files, *inputs]
    files = [_capture_file(root, relative) for relative in _expand_inputs(root, required)]
    return EvidenceSnapshot(identity=identity, files=files)


# --------------------------------------------------------------------------------------
# Section 7.3 step 13 -- drift detection
# --------------------------------------------------------------------------------------


def _identity_differences(initial: RepositoryIdentity, final: RepositoryIdentity) -> list[str]:
    differences: list[str] = []
    for name in RepositoryIdentity.model_fields:
        before = getattr(initial, name)
        after = getattr(final, name)
        if before != after:
            differences.append(f"repository_identity.{name}: {before!r} -> {after!r}")
    return differences


def _file_differences(initial: EvidenceSnapshot, final: EvidenceSnapshot) -> list[str]:
    before_by_path = {item.path: item for item in initial.files}
    after_by_path = {item.path: item for item in final.files}
    differences: list[str] = []
    for path in sorted(set(before_by_path) | set(after_by_path)):
        before = before_by_path.get(path)
        after = after_by_path.get(path)
        if before is None:
            differences.append(f"evidence {path}: appeared between the two snapshots")
            continue
        if after is None:
            differences.append(f"evidence {path}: disappeared between the two snapshots")
            continue
        for name in FileIdentity.model_fields:
            if name == "path":
                continue
            left = getattr(before, name)
            right = getattr(after, name)
            if left != right:
                # " field " rather than a dot, because a path already contains dots and the
                # refusal record is read by a person deciding what moved underneath them.
                differences.append(f"evidence {path} field {name}: {left!r} -> {right!r}")
    return differences


def compare_snapshots(initial: EvidenceSnapshot, final: EvidenceSnapshot) -> None:
    """Section 7.3 step 13: refuse publication on any difference between two snapshots.

    Compares byte-for-byte and field-for-field -- every hash, every stable-identity tuple and
    the full `RepositoryIdentity` record -- never by a heuristic "looks unchanged" check. An
    mtime that moved while the content stayed identical is still reported, because a file
    that was rewritten is precisely what this protocol exists to notice.

    Returns `None` on agreement and raises :class:`SnapshotDriftError` otherwise; there is no
    boolean result, so a caller cannot ignore drift by discarding a return value.
    """
    differences = _identity_differences(initial.identity, final.identity)
    differences.extend(_file_differences(initial, final))
    if differences:
        raise SnapshotDriftError(differences)
