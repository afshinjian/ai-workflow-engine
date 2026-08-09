"""Content-addressed, atomic, no-clobber publication of the proposal artifact (AUTO-015).

Contract: `docs/workflow-automation/stage-prompts/AUTO-015.md` (Revision 4) sections 17.1
(the single canonical artifact), 17.2 (the complete publication protocol), 18 (idempotency,
resume and concurrency), 16.2 (collision behavior) and 22 invariants 1, 6, 7 and 17.

This module publishes bytes. It assembles nothing, renders nothing, validates no candidate and
reads no governance document: section 15's structural validation and section 16.4's load-time
re-verification both live in `proposal.py`, and the artifact arriving here is already final.

One file, one root
------------------
Section 17.1 fixes a single-file artifact with the rendered prompt embedded inside it, so there
is no torn pair to commit in two phases and no manifest-first protocol to get right. The root is
the external, repository-scoped directory DEC-002/DEC-010 fixes,
`~/.ai-workflow-engine/successor-proposals/<repository-id>/`, which must resolve outside
`resolved_repository_root` entirely -- and therefore outside every authoritative governance path,
since all of them live inside the repository. Nothing published here is ever added to Git.

Why `os.rename` and not `os.link`
---------------------------------
`prompt/store.py` publishes with `os.link` because it stages temp files in a location not
guaranteed to share a filesystem with its destination. That constraint does not exist here: the
temp file is always created *inside the same artifact root* as the final path, so a
same-filesystem rename is always available and is atomic on every POSIX filesystem this
repository targets. Section 17.2 therefore makes `os.rename` the only publication method, and
the hardlink primitive is deliberately not reused -- only its no-clobber read-and-compare idea
is, which is reproduced here rather than imported.

No lock, and why that is still safe
-----------------------------------
Section 18 takes no OS-level lock. Safety comes from content addressing instead: the filename is
the full 64-character `proposal_sha256`, so two invocations contend for one path only when they
produced byte-identical hashed payloads, and the loser's read-and-compare finds exactly what it
was about to write. Two invocations over genuinely different evidence address two different
files and never contend at all.

Residual race, stated honestly
------------------------------
POSIX `rename(2)` replaces its destination silently and stdlib exposes no `RENAME_NOREPLACE`, so
no-clobber here is a check-then-rename, not one atomic no-clobber step. The window between the
check and the rename is real. It is benign rather than closed: reaching it at all requires a
concurrent invocation that computed the same content address, which means it is writing the same
bytes, so the worst outcome is that identical content overwrites identical content. A platform
whose `rename` *does* refuse an existing destination raises `FileExistsError`, and that is routed
into the same read-and-compare path, so both behaviors converge on the same result. This module
must not be described as holding an atomic no-clobber guarantee it does not have.

Orphan temp files
-----------------
A crash between the temp write and the rename leaves a temp file behind. It is inert: it lives at
a namespaced, dot-prefixed `.tmp` name that can never match the content-addressed
`<64-hex>.json` grammar :func:`ArtifactStore.published_artifact_paths` filters on, so no reader
mistakes it for an artifact, and nothing partial is ever visible at a final path. Cleanup is
best-effort housekeeping on every failure path this process can observe, never a correctness
requirement -- a hard kill leaves the orphan, and that is fine.
"""

import errno
import hashlib
import json
import os
import re
import stat as stat_module
import uuid
from pathlib import Path
from typing import ClassVar, Final

from pydantic import ValidationError

from ai_workflow_engine.exceptions import WorkflowEngineError
from ai_workflow_engine.successor_planning.catalog import safe_message
from ai_workflow_engine.successor_planning.models import (
    FailureCode,
    ProposalArtifact,
    canonical_payload_bytes,
)
from ai_workflow_engine.successor_planning.proposal import serialize_artifact
from ai_workflow_engine.successor_planning.snapshot import (
    MAX_EVIDENCE_BYTES,
    AuthoritativeSourceError,
    SymlinkPolicyViolationError,
    artifact_root_for,
    read_evidence_bytes,
)

#: Section 17.2 root ownership and permissions. Nothing here is executable and nothing is
#: group- or world-readable: the root holds one operator's own planning evidence.
ROOT_MODE: Final = 0o700
FILE_MODE: Final = 0o600

#: A published artifact is addressed by its full, untruncated `proposal_sha256` (section 16.1).
#: A display form is never a filename, so this grammar admits nothing shorter.
_DIGEST_RE = re.compile(r"[0-9a-f]{64}")
_ARTIFACT_NAME_RE = re.compile(r"[0-9a-f]{64}\.json")

#: The same read ceiling the snapshot protocol applies to evidence (section 22 invariant 14),
#: reused rather than restated so one number governs every bounded read in this package.
MAX_ARTIFACT_BYTES: Final = MAX_EVIDENCE_BYTES


# --------------------------------------------------------------------------------------
# Typed, fail-closed errors (section 13 codes)
# --------------------------------------------------------------------------------------


class PublicationError(WorkflowEngineError):
    """Base fail-closed publication failure, tagged with its section 13 failure code.

    Never raised directly. This hierarchy is deliberately separate from `snapshot.SnapshotError`
    even where the code is shared: an identical code means the same thing to a caller building a
    refusal record, but the phase that produced it does not, and collapsing the two would make
    "the snapshot rejected a symlinked input" indistinguishable from "publication rejected a
    symlinked artifact root".
    """

    code: ClassVar[FailureCode]


class PathEscape(PublicationError):
    """Section 17.2: the root escaped its allowed location or changed underneath us."""

    code: ClassVar[FailureCode] = "PATH_ESCAPE"


class SymlinkPolicyViolation(PublicationError):
    """Section 17.2: a component of the root or the publication path is a symlink."""

    code: ClassVar[FailureCode] = "SYMLINK_POLICY_VIOLATION"


class PublicationConflict(PublicationError):
    """Section 17.2/16.2: a content address already holds genuinely different content.

    `digest_collision` carries section 16.2's distinct, more severe marker. It is `True` only
    when the file already at this address is itself a valid artifact that re-derives to this very
    address while carrying a *different* canonical payload -- that is a true SHA-256 collision and
    a cryptographic anomaly worth surfacing loudly, rather than the ordinary case of a corrupted
    or hand-edited file. Neither case is ever resolved by overwriting.
    """

    code: ClassVar[FailureCode] = "PUBLICATION_CONFLICT"

    def __init__(self, message: str, *, digest_collision: bool = False) -> None:
        self.digest_collision = digest_collision
        super().__init__(message)


class PublicationFailure(PublicationError):
    """Section 13: the publish step itself failed -- I/O error, permission failure, disk full."""

    code: ClassVar[FailureCode] = "PUBLICATION_FAILURE"


# --------------------------------------------------------------------------------------
# Section 17.2 -- root resolution, symlink refusal, permissions
# --------------------------------------------------------------------------------------


def _components(path: Path) -> list[Path]:
    """Return every component of `path`, filesystem root first, `path` itself last."""
    return [*reversed(path.parents), path]


def _reject_symlink_components(path: Path, label: str) -> None:
    """Section 17.2: refuse `path` if any component of it is a symlink.

    Every component is checked, not just the last one, because a symlinked *parent* redirects the
    publication just as effectively as a symlinked final name -- and because the root is under the
    operator's home directory, where a swapped component is the cheapest available attack. A
    component that does not exist yet is not a symlink and is not refused here.
    """
    for component in _components(path):
        if component.is_symlink():
            raise SymlinkPolicyViolation(
                f"{label} component {component} is a symlink, which section 17.2 forbids"
            )


def _reject_repository_containment(root: Path, repository_root: Path) -> None:
    """Section 17.2: the artifact root is never inside the repository.

    This is `prompt/store.py`'s `_reject_repository_containment` check reused as the enforcement
    mechanism, widened only in that it compares fully realized paths on both sides. Because every
    authoritative governance path (section 8) lives inside the repository, refusing containment in
    the repository refuses containment in all of them at once.
    """
    real_repository = os.path.realpath(repository_root)
    real_root = os.path.realpath(root)
    if real_root == real_repository or real_root.startswith(real_repository + os.sep):
        raise PathEscape(
            f"The artifact root {real_root} must not be inside the repository {real_repository}: "
            "DEC-002 fixes an external, repository-scoped root that is never part of Git"
        )


def _create_root(root: Path) -> None:
    """Create every missing component of `root` with restrictive permissions.

    Each component this invocation creates is created `0o700` directly, so no window exists in
    which a broader mode is visible. An ancestor that already exists is left alone -- its mode is
    the operator's own choice and `~/.ai-workflow-engine` is shared with the prompt store -- but
    the repository-scoped root itself is tightened to `0o700` unconditionally, because section
    17.2 states its permissions and nothing else owns that directory.
    """
    for component in _components(root):
        if component.exists():
            continue
        try:
            os.mkdir(component, ROOT_MODE)
        except FileExistsError:
            # A concurrent invocation created it first; section 18 takes no lock and this is
            # exactly the benign outcome that permits it.
            continue
        except OSError as exc:
            raise PublicationFailure(
                f"The artifact root component {component} could not be created: {safe_message(exc)}"
            ) from exc
    try:
        os.chmod(root, ROOT_MODE)
    except OSError as exc:
        raise PublicationFailure(
            f"The artifact root {root} could not be restricted to {ROOT_MODE:#o}: "
            f"{safe_message(exc)}"
        ) from exc


def resolve_artifact_root(repository_id: str, repository_root: Path) -> Path:
    """Resolve, verify and create the section 17.2 artifact root for `repository_id`.

    Returns `~/.ai-workflow-engine/successor-proposals/<repository-id>/` after refusing a
    symlinked component, refusing a root that resolves inside `repository_root`, creating every
    missing component `0o700`, and confirming the created root resolves to itself. A malformed
    repository ID never reaches the filesystem: `artifact_root_for` refuses it as
    `INVALID_INVOCATION`, because a repository ID comes from validated configuration and a
    malformed one is a bad invocation rather than a publication failure.
    """
    root = artifact_root_for(repository_id)
    _reject_symlink_components(root, "The artifact root")
    _reject_repository_containment(root, repository_root)
    _create_root(root)
    # Re-checked after creation: a component created between the check above and now could have
    # been created as a symlink by someone else.
    _reject_symlink_components(root, "The artifact root")
    resolved = Path(os.path.realpath(root))
    if resolved != root:
        raise PathEscape(f"The artifact root {root} resolves to {resolved} rather than to itself")
    return root


# --------------------------------------------------------------------------------------
# Section 17.2 -- the published record
# --------------------------------------------------------------------------------------


class PublishedArtifact:
    """Where one artifact is published, and whether this invocation is what put it there.

    `created` is `False` on the idempotent path -- an identical artifact was already at this
    address, so nothing was written. Both values are a success; section 18 requires a repeated
    invocation over unchanged evidence to converge on one artifact rather than to fail.
    """

    def __init__(self, path: Path, proposal_id: str, *, created: bool) -> None:
        self.path = path
        self.proposal_id = proposal_id
        self.created = created

    def __repr__(self) -> str:
        return (
            f"PublishedArtifact(path={self.path!s}, proposal_id={self.proposal_id}, "
            f"created={self.created})"
        )


# --------------------------------------------------------------------------------------
# Section 17.2 -- the publication protocol
# --------------------------------------------------------------------------------------


def _write_all(descriptor: int, data: bytes) -> None:
    """Write every byte of `data`, mirroring `prompt/store.py`'s partial-write discipline."""
    view = memoryview(data)
    while view:
        written = os.write(descriptor, view)
        if written == 0:
            # A zero-byte write makes no progress; looping again would hang forever.
            raise OSError("os.write made zero progress while writing a proposal temporary file")
        view = view[written:]


def _fsync_directory(directory: Path) -> None:
    """Fsync `directory` where the platform supports it (section 17.2's parent-directory fsync).

    A platform that refuses to open or fsync a directory is not an error: the rename itself is
    already atomic, and this only shortens the window in which a completed rename is not yet
    durable across a power loss.
    """
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _read_published(path: Path, label: str) -> bytes:
    """Read one file inside the artifact root, bounded and no-follow.

    Reuses the snapshot protocol's read discipline verbatim -- `O_NOFOLLOW` where the platform has
    it, a regular-file check on the opened descriptor, and an explicit byte ceiling applied before
    anything is pulled into memory -- and only re-tags its refusals with this phase's codes.
    """
    try:
        data, _ = read_evidence_bytes(path, label, ceiling=MAX_ARTIFACT_BYTES)
    except SymlinkPolicyViolationError as exc:
        raise SymlinkPolicyViolation(str(exc)) from exc
    except AuthoritativeSourceError as exc:
        raise PublicationFailure(str(exc)) from exc
    return data


def _parse_artifact(document: bytes) -> ProposalArtifact | None:
    """Return the artifact `document` encodes, or `None` if it is not a re-derivable one.

    `None` means "this document cannot be re-derived at all" -- unreadable, unparsable, or failing
    the closed section 16.1 schema -- which is the corrupted/hand-edited case, not a collision.
    """
    try:
        parsed = json.loads(document.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    try:
        return ProposalArtifact.model_validate(parsed)
    except ValidationError:
        return None


class ArtifactStore:
    """A pinned artifact root and the section 17.2 publication protocol over it.

    The root is resolved and its identity captured once, through :meth:`pin`, and re-verified
    immediately before every atomic publish: a root that no longer exists, no longer resolves to
    the same path, became a symlink, or is now a different directory at the same path is
    `PATH_ESCAPE` and publishes nothing.
    """

    def __init__(self, root: Path, repository_root: Path, *, device: int, inode: int) -> None:
        """Construct through :meth:`pin`, which is what captures a verified root identity."""
        self.root = root
        self.repository_root = repository_root
        self._device = device
        self._inode = inode

    @classmethod
    def pin(cls, repository_id: str, repository_root: Path) -> "ArtifactStore":
        """Resolve the root for `repository_id` and pin its identity (section 17.2)."""
        root = resolve_artifact_root(repository_id, repository_root)
        try:
            metadata = os.stat(root, follow_symlinks=False)
        except OSError as exc:
            raise PublicationFailure(
                f"The artifact root {root} could not be inspected: {safe_message(exc)}"
            ) from exc
        return cls(
            root,
            Path(os.path.realpath(repository_root)),
            device=metadata.st_dev,
            inode=metadata.st_ino,
        )

    # -- addressing --------------------------------------------------------------------

    def path_for(self, proposal_id: str) -> Path:
        """Return the content address of `proposal_id` inside this root.

        The filename is the full 64-character digest and nothing else, so a traversal-shaped or
        truncated identity has no representable path here at all rather than one that has to be
        confined after the fact.
        """
        if _DIGEST_RE.fullmatch(proposal_id) is None:
            raise PathEscape(
                f"{proposal_id!r} is not a full 64-character proposal digest and therefore "
                "addresses nothing inside the artifact root"
            )
        return self.root / f"{proposal_id}.json"

    def published_artifact_paths(self) -> list[Path]:
        """Return every published artifact in this root, in canonical name order.

        Only a regular file whose name is exactly `<64-hex>.json` counts. An orphan temp file, a
        symlink, or any other stray entry is not an artifact and is never returned -- which is the
        property that makes an interrupted publication inert rather than recoverable state.
        """
        try:
            names = os.listdir(self.root)
        except OSError as exc:
            raise PublicationFailure(
                f"The artifact root {self.root} could not be listed: {safe_message(exc)}"
            ) from exc
        published: list[Path] = []
        for name in sorted(names, key=lambda entry: entry.encode("utf-8")):
            if _ARTIFACT_NAME_RE.fullmatch(name) is None:
                continue
            candidate = self.root / name
            try:
                metadata = os.lstat(candidate)
            except OSError:
                continue
            if stat_module.S_ISREG(metadata.st_mode):
                published.append(candidate)
        return published

    # -- root identity pinning ---------------------------------------------------------

    def _verify_pinned_root(self) -> None:
        """Re-verify the pinned root: same path, same directory, still not a symlink.

        The device+inode pair detects a *different* directory at the pinned path. It cannot
        detect a delete-and-recreate that the filesystem happens to satisfy by reusing the same
        inode number, which is a residual gap of inode identity rather than of this check --
        stated here rather than left to be discovered. Nothing is published into such a root
        without the post-publication verification still re-reading and re-deriving what landed.
        """
        _reject_symlink_components(self.root, "The artifact root")
        try:
            metadata = os.stat(self.root, follow_symlinks=False)
        except OSError as exc:
            raise PathEscape(
                f"The pinned artifact root {self.root} is no longer readable: {safe_message(exc)}"
            ) from exc
        if not stat_module.S_ISDIR(metadata.st_mode):
            raise PathEscape(f"The pinned artifact root {self.root} is no longer a directory")
        if (metadata.st_dev, metadata.st_ino) != (self._device, self._inode):
            raise PathEscape(
                f"The pinned artifact root {self.root} is a different directory than the one "
                "pinned at the start of this invocation"
            )
        resolved = Path(os.path.realpath(self.root))
        if resolved != self.root:
            raise PathEscape(f"The pinned artifact root {self.root} now resolves to {resolved}")

    # -- publication -------------------------------------------------------------------

    def publish(self, artifact: ProposalArtifact) -> PublishedArtifact:
        """Publish `artifact` at its own content address, atomically and without clobbering.

        Idempotent by construction: an identical artifact already at this address is a no-op
        success, a genuinely different one is `PUBLICATION_CONFLICT`, and nothing is overwritten
        in either case.
        """
        document = serialize_artifact(artifact)
        digest = hashlib.sha256(canonical_payload_bytes(artifact)).hexdigest()
        if digest != artifact.proposal_id:
            # Section 15 owns this re-derivation and must have run before publication; checking
            # it again here keeps a mis-bound artifact from being published under a name its own
            # payload does not produce, which the post-publication check could only catch after
            # the file was already visible.
            raise PublicationFailure(
                f"The artifact is addressed {artifact.proposal_id} but its canonical payload "
                f"re-derives to {digest}"
            )

        recorded_root = os.path.realpath(artifact.repository_identity.resolved_repository_root)
        if recorded_root != str(self.repository_root):
            raise PathEscape(
                f"The artifact is bound to the repository {recorded_root} but this store is "
                f"pinned to {self.repository_root}"
            )

        self._verify_pinned_root()
        final = self.path_for(artifact.proposal_id)
        if final.is_symlink():
            raise SymlinkPolicyViolation(
                f"The publication path {final} is a symlink, which section 17.2 forbids"
            )

        if os.path.lexists(final):
            return self._reconcile_existing(final, document, artifact)

        temp = self._create_temp(artifact.proposal_id, document)
        renamed = False
        try:
            # Section 17.2's identity pinning: re-verified immediately before the one atomic
            # step, so a root swapped underneath this invocation refuses instead of publishing.
            self._verify_pinned_root()
            if os.path.lexists(final):
                # No-clobber: `os.rename` would replace the destination silently, so the
                # destination is checked first and the refusal is raised in the OS's own
                # vocabulary, which is the same vocabulary a no-replace platform's rename uses.
                raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), str(final))
            os.rename(temp, final)
            renamed = True
        except FileExistsError:
            # Section 17.2's concurrent-identical case: whoever won the race published either the
            # same bytes (success) or different ones (conflict), and read-and-compare says which.
            return self._reconcile_existing(final, document, artifact)
        except OSError as exc:
            raise PublicationFailure(
                f"The proposal could not be published to {final}: {safe_message(exc)}"
            ) from exc
        finally:
            if not renamed:
                # Best-effort housekeeping only. An orphan temp file is inert (see the module
                # docstring), so failing to remove one is never a correctness problem.
                temp.unlink(missing_ok=True)

        _fsync_directory(self.root)
        return self._verify_published(final, document, artifact, created=True)

    def _create_temp(self, proposal_id: str, document: bytes) -> Path:
        """Create, write and fsync one temp file inside this same root (section 17.2).

        The temp file shares the root precisely so the rename below is a same-filesystem rename.
        Its name is namespaced and dot-prefixed so it can never match the content-addressed
        grammar, and `O_CREAT | O_EXCL` means this invocation owns the name it got.
        """
        while True:
            candidate = self.root / f".{proposal_id}.{uuid.uuid4().hex}.tmp"
            try:
                descriptor = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
            except FileExistsError:
                continue
            except OSError as exc:
                raise PublicationFailure(
                    f"A temporary file could not be created in {self.root}: {safe_message(exc)}"
                ) from exc
            break
        try:
            try:
                # `os.open`'s mode is masked by the process umask; an explicit `fchmod` makes the
                # published permissions exactly `0o600` regardless of the operator's umask.
                os.fchmod(descriptor, FILE_MODE)
                _write_all(descriptor, document)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except BaseException:
            # This invocation owns `candidate` alone, so cleaning it up here cannot touch another
            # invocation's temp file.
            candidate.unlink(missing_ok=True)
            raise
        return candidate

    def _reconcile_existing(
        self, final: Path, document: bytes, artifact: ProposalArtifact
    ) -> PublishedArtifact:
        """Section 17.2's no-clobber decision: byte-for-byte compare, then success or conflict."""
        existing = _read_published(final, f"The artifact already published at {final}")
        if existing == document:
            return self._verify_published(final, document, artifact, created=False)

        published = _parse_artifact(existing)
        if published is None:
            raise PublicationConflict(
                f"{final} already holds a document that is not a re-derivable proposal artifact; "
                "refusing to overwrite a corrupted or hand-edited file at a content address"
            )
        payload = canonical_payload_bytes(published)
        rederived = hashlib.sha256(payload).hexdigest()
        if rederived != artifact.proposal_id:
            raise PublicationConflict(
                f"{final} already holds an artifact that re-derives to {rederived} rather than to "
                f"its own address {artifact.proposal_id}; refusing to overwrite it"
            )
        # The file at this address re-derives to this address, so its hashed payload is either
        # identical to ours -- differing only in the explicitly non-canonical
        # `generation_metadata` envelope (section 16.3), which section 18 requires this
        # invocation to converge on as a no-op success rather than refuse -- or genuinely
        # different, which for a 64-character digest is a SHA-256 collision and gets section
        # 16.2's severe marker.
        collision = payload != canonical_payload_bytes(artifact)
        if not collision:
            # Idempotent republish across a `generation_metadata` boundary: the already-published
            # file is left untouched and re-verified as itself -- never against this invocation's
            # own freshly stamped, non-canonical envelope bytes, which is what made this a false
            # conflict in the first place.
            return self._verify_published(final, existing, artifact, created=False)
        raise PublicationConflict(
            f"{final} already holds different bytes at the same content address with a "
            "genuinely different canonical payload: this is a SHA-256 collision; refusing to "
            "overwrite it",
            digest_collision=True,
        )

    def _verify_published(
        self,
        final: Path,
        document: bytes,
        artifact: ProposalArtifact,
        *,
        created: bool,
    ) -> PublishedArtifact:
        """Section 17.2's post-publication verification, before success is ever reported.

        The published file is re-read from disk -- never trusted from the buffer that produced it
        -- its canonical payload digest is re-derived and compared against `proposal_sha256`, and
        its exact bytes are compared against what was meant to be there. The digest check catches
        corruption inside the hashed payload; the byte check additionally catches corruption in
        the unhashed envelope, which no digest would ever notice.
        """
        data = _read_published(final, f"The published artifact {final}")
        published = _parse_artifact(data)
        rederived = (
            None
            if published is None
            else hashlib.sha256(canonical_payload_bytes(published)).hexdigest()
        )
        if rederived != artifact.proposal_id:
            raise PublicationFailure(
                f"The published artifact at {final} re-derives to {rederived} rather than to its "
                f"address {artifact.proposal_id}"
            )
        if data != document:
            raise PublicationFailure(
                f"The published artifact at {final} does not match the bytes this invocation "
                "published"
            )
        return PublishedArtifact(final, artifact.proposal_id, created=created)


def publish(artifact: ProposalArtifact, repository_id: str) -> PublishedArtifact:
    """Pin the artifact root for `repository_id` and publish `artifact` into it (section 17.2).

    The repository root is taken from the artifact's own hash-bound `repository_identity`, so the
    containment rule is always enforced against the repository the artifact was actually built
    for rather than against whatever root a caller happens to pass separately. `repository_id` is
    the DEC-010 canonical identifier, which is derived from the primary remote and is deliberately
    not part of `RepositoryIdentity`.
    """
    store = ArtifactStore.pin(
        repository_id, Path(artifact.repository_identity.resolved_repository_root)
    )
    return store.publish(artifact)
