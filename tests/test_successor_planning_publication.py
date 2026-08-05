"""AUTO-015 section 17: content-addressed, atomic, no-clobber artifact publication.

Every fixture here is a real filesystem: real directories with real modes, real symlinks, real
inodes, real temp files and real threads racing for one content address. Nothing about the
behaviour under test is stubbed. The two places `os.rename` is replaced are not stand-ins for
publication logic -- they reproduce two OS-level events this process cannot otherwise cause on
demand: a platform whose `rename` refuses an existing destination (the lost-race branch section
17.2 names by `FileExistsError`), and corruption landing between the rename and the success
report (what section 17.2's post-publication verification exists to catch). Both delegate to the
real filesystem for everything else.

Every test publishes into an artifact root under `tmp_path`: the `artifact_home` fixture pins
`HOME` there and asserts the resolved root really is inside `tmp_path`, so no run of this suite
can write into the operator's own `~/.ai-workflow-engine/successor-proposals/`.
"""

import errno
import hashlib
import json
import os
import shutil
import stat
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from ai_workflow_engine.successor_planning import store as store_module
from ai_workflow_engine.successor_planning.models import (
    Candidate,
    CandidateBlocker,
    CandidateDependency,
    EligibilityDecision,
    EvidenceReference,
    GenerationMetadata,
    PredecessorRegistryEvidence,
    PredecessorStatusReconciliation,
    ProposalArtifact,
    ProposalBlocker,
    ProposalReadyOutcome,
    RepositoryIdentity,
    StaticCatalogSourceReference,
    canonical_payload_bytes,
)
from ai_workflow_engine.successor_planning.proposal import serialize_artifact
from ai_workflow_engine.successor_planning.snapshot import InvalidInvocationError
from ai_workflow_engine.successor_planning.store import (
    FILE_MODE,
    ROOT_MODE,
    ArtifactStore,
    PathEscape,
    PublicationConflict,
    PublicationFailure,
    SymlinkPolicyViolation,
    publish,
    resolve_artifact_root,
)

REPOSITORY_ID = "ai-workflow-engine--0123456789ab"
CATALOG_PATH = "docs/workflow-automation/successor-planning/AUTO-015-AUTHORITATIVE-CATALOG.yaml"
CANDIDATE_ID = "automatic-next-stage-computation"
PROMPT = "**PROPOSAL - NOT AUTHORIZED**\n\n# Successor proposal for AUTO-014\n"


# --------------------------------------------------------------------------------------
# Fixtures: a real repository directory, a real artifact home, real artifacts
# --------------------------------------------------------------------------------------


@pytest.fixture
def repository_root(tmp_path: Path) -> Path:
    """The repository the artifact root must stay outside of (section 17.2)."""
    root = tmp_path / "repo"
    root.mkdir()
    return root


@pytest.fixture
def artifact_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Pin `HOME` under `tmp_path`, and prove the operator's own artifact root stays untouched."""
    operator_root = Path(os.path.expanduser("~")) / ".ai-workflow-engine" / "successor-proposals"
    before = sorted(os.listdir(operator_root)) if operator_root.is_dir() else None

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("USERPROFILE", raising=False)
    assert Path.home() == home
    yield home

    after = sorted(os.listdir(operator_root)) if operator_root.is_dir() else None
    assert after == before


def repository_identity(repository_root: Path, **overrides: Any) -> RepositoryIdentity:
    fields: dict[str, Any] = {
        "configured_repository_root": str(repository_root),
        "resolved_repository_root": str(repository_root),
        "configured_repository_id": "ai-workflow-engine",
        "git_worktree_root": str(repository_root),
        "branch": "feature/auto-015-successor-planning",
        "head_sha": "a" * 40,
        "upstream_ref": None,
        "ahead": None,
        "behind": None,
        "modified_files": [],
        "staged_files": [],
        "untracked_files": [],
        "config_hash": "b" * 64,
    }
    fields.update(overrides)
    return RepositoryIdentity(**fields)


def candidate() -> Candidate:
    return Candidate(
        candidate_id=CANDIDATE_ID,
        schema_version="1.0",
        title="Automatic Next-Stage Computation and Prompt Generation",
        mission="Derive a candidate next capability from current repository evidence.",
        source_kind="static_catalog",
        source_reference=StaticCatalogSourceReference(
            catalog_path=CATALOG_PATH, catalog_version="1.0", entry_index=4
        ),
        mvp_relation="outside_deferred",
        dependencies=[
            CandidateDependency(
                dependency_id="GOV-AUTO-08", dependency_type="stage", status="COMPLETE"
            )
        ],
        blockers=[
            CandidateBlocker(blocker_id="OD-10", blocker_type="open_question", live_status="Open")
        ],
        required_owner_decisions=["Architecture option."],
        allowed_recommendation_status=True,
        evidence_references=[
            EvidenceReference(path="docs/TASK_QUEUE.md", sha256="c" * 64, size=1024)
        ],
        content_hash="e" * 64,
    )


def build_artifact(repository_root: Path, **overrides: Any) -> ProposalArtifact:
    """Build a valid artifact whose `proposal_id` is the digest of its own canonical payload.

    The digest is taken over the canonical payload, which excludes `proposal_id`,
    `proposal_hash` and `generation_metadata`, so the placeholder in the first pass cannot
    influence the digest computed from it.
    """
    prompt: str = overrides.pop("generated_prompt", PROMPT)
    fields: dict[str, Any] = {
        "proposal_id": "0" * 64,
        "repository_identity": repository_identity(repository_root),
        "predecessor_stage_id": "AUTO-014",
        "predecessor_registry_evidence": PredecessorRegistryEvidence(
            registry_reference=EvidenceReference(
                path="docs/workflow-automation/STAGE_REGISTRY.md", sha256="1" * 64, size=20480
            ),
            registry_status="COMPLETE",
        ),
        "predecessor_completion_evidence": [
            EvidenceReference(
                path="docs/reports/workflow-automation/AUTO-014-completion-report.md",
                sha256="2" * 64,
                size=8192,
            )
        ],
        "predecessor_status_reconciliation": PredecessorStatusReconciliation(
            registry_status="COMPLETE",
            task_queue_status="Done",
            mirror_status="Done",
            reconciled_status="COMPLETE",
            consistent=True,
        ),
        "evidence_manifest": [
            EvidenceReference(path="docs/TASK_QUEUE.md", sha256="3" * 64, size=1024)
        ],
        "normalized_evidence_hash": "4" * 64,
        "candidate_list": [candidate()],
        "eligibility_decisions": [
            EligibilityDecision(
                candidate_id=CANDIDATE_ID,
                lifecycle_status="eligible",
                rule_id="ELIGIBLE_PREDECESSOR_COMPLETE",
                reasons=["Predecessor AUTO-014 is COMPLETE in the queue and the registry."],
            )
        ],
        "blockers": [
            ProposalBlocker(
                blocker_id="OD-10",
                blocker_type="open_question",
                live_status="Open",
                candidate_id=CANDIDATE_ID,
            )
        ],
        "outcome": ProposalReadyOutcome(
            outcome_class="PROPOSAL_READY", result_variant="RECOMMENDATION_READY"
        ),
        "generated_prompt": prompt,
        "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "proposal_hash": "0" * 64,
        "warnings": [],
        "errors": [],
        "generation_metadata": GenerationMetadata(
            generated_at="2026-08-04T06:06:16Z", tool_version="1.0.0"
        ),
    }
    fields.update(overrides)
    draft = ProposalArtifact(**fields)
    digest = hashlib.sha256(canonical_payload_bytes(draft)).hexdigest()
    fields["proposal_id"] = digest
    fields["proposal_hash"] = digest
    return ProposalArtifact(**fields)


def mode_of(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


# --------------------------------------------------------------------------------------
# Section 17.2 -- root resolution, permissions, symlinks, containment
# --------------------------------------------------------------------------------------


def test_the_artifact_root_is_the_repository_scoped_external_directory(
    artifact_home: Path, repository_root: Path, tmp_path: Path
) -> None:
    root = resolve_artifact_root(REPOSITORY_ID, repository_root)

    assert root == artifact_home / ".ai-workflow-engine" / "successor-proposals" / REPOSITORY_ID
    assert root.is_dir()
    assert str(root).startswith(str(tmp_path))
    assert not root.is_relative_to(repository_root)


def test_every_directory_this_invocation_creates_is_restricted(
    artifact_home: Path, repository_root: Path
) -> None:
    root = resolve_artifact_root(REPOSITORY_ID, repository_root)

    assert mode_of(root) == ROOT_MODE
    assert mode_of(artifact_home / ".ai-workflow-engine") == ROOT_MODE
    assert mode_of(artifact_home / ".ai-workflow-engine" / "successor-proposals") == ROOT_MODE


def test_an_existing_permissive_root_is_tightened(
    artifact_home: Path, repository_root: Path
) -> None:
    root = artifact_home / ".ai-workflow-engine" / "successor-proposals" / REPOSITORY_ID
    root.mkdir(parents=True)
    os.chmod(root, 0o755)

    assert mode_of(resolve_artifact_root(REPOSITORY_ID, repository_root)) == ROOT_MODE


def test_a_root_resolving_inside_the_repository_is_refused(
    repository_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inside = repository_root / "home"
    inside.mkdir()
    monkeypatch.setenv("HOME", str(inside))

    with pytest.raises(PathEscape) as failure:
        resolve_artifact_root(REPOSITORY_ID, repository_root)

    assert failure.value.code == "PATH_ESCAPE"
    assert not (inside / ".ai-workflow-engine").exists()


def test_a_symlinked_root_component_is_refused(
    artifact_home: Path, repository_root: Path, tmp_path: Path
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (artifact_home / ".ai-workflow-engine").symlink_to(elsewhere, target_is_directory=True)

    with pytest.raises(SymlinkPolicyViolation) as failure:
        resolve_artifact_root(REPOSITORY_ID, repository_root)

    assert failure.value.code == "SYMLINK_POLICY_VIOLATION"
    assert list(elsewhere.iterdir()) == []


def test_a_symlinked_root_itself_is_refused(
    artifact_home: Path, repository_root: Path, tmp_path: Path
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    parent = artifact_home / ".ai-workflow-engine" / "successor-proposals"
    parent.mkdir(parents=True)
    (parent / REPOSITORY_ID).symlink_to(elsewhere, target_is_directory=True)

    with pytest.raises(SymlinkPolicyViolation):
        resolve_artifact_root(REPOSITORY_ID, repository_root)


def test_a_malformed_repository_id_never_reaches_the_filesystem(
    artifact_home: Path, repository_root: Path
) -> None:
    with pytest.raises(InvalidInvocationError):
        resolve_artifact_root("../escape", repository_root)

    assert not (artifact_home / ".ai-workflow-engine").exists()


# --------------------------------------------------------------------------------------
# Section 17.2 -- addressing
# --------------------------------------------------------------------------------------


def test_the_filename_is_the_full_untruncated_digest(
    artifact_home: Path, repository_root: Path
) -> None:
    artifact = build_artifact(repository_root)
    published = publish(artifact, REPOSITORY_ID)

    assert published.path.name == f"{artifact.proposal_id}.json"
    assert len(artifact.proposal_id) == 64
    assert published.proposal_id == artifact.proposal_id
    assert published.created is True


@pytest.mark.parametrize(
    "proposal_id",
    ["../../etc/passwd", "a" * 12, "A" * 64, "e" * 63, f"{'e' * 64}.json", ""],
)
def test_a_non_digest_identity_addresses_nothing(
    artifact_home: Path, repository_root: Path, proposal_id: str
) -> None:
    store = ArtifactStore.pin(REPOSITORY_ID, repository_root)

    with pytest.raises(PathEscape):
        store.path_for(proposal_id)


def test_the_published_file_and_root_are_not_readable_by_anyone_else(
    artifact_home: Path, repository_root: Path
) -> None:
    published = publish(build_artifact(repository_root), REPOSITORY_ID)

    assert mode_of(published.path) == FILE_MODE
    assert mode_of(published.path.parent) == ROOT_MODE


def test_the_published_bytes_are_the_canonical_document(
    artifact_home: Path, repository_root: Path
) -> None:
    artifact = build_artifact(repository_root)
    published = publish(artifact, REPOSITORY_ID)
    data = published.path.read_bytes()

    assert data == serialize_artifact(artifact)
    assert json.loads(data.decode("utf-8"))["authorization_status"] == "NOT_AUTHORIZED"
    assert (
        hashlib.sha256(
            canonical_payload_bytes(ProposalArtifact.model_validate(json.loads(data)))
        ).hexdigest()
        == artifact.proposal_id
    )


# --------------------------------------------------------------------------------------
# Section 18 -- idempotency and distinct addressing
# --------------------------------------------------------------------------------------


def test_a_repeated_invocation_converges_on_one_artifact(
    artifact_home: Path, repository_root: Path
) -> None:
    artifact = build_artifact(repository_root)

    first = publish(artifact, REPOSITORY_ID)
    inode = first.path.stat().st_ino
    second = publish(artifact, REPOSITORY_ID)

    assert first.path == second.path
    assert first.created is True
    assert second.created is False
    assert second.path.stat().st_ino == inode
    assert ArtifactStore.pin(REPOSITORY_ID, repository_root).published_artifact_paths() == [
        first.path
    ]


def test_republishing_identical_content_is_a_no_op_success(
    artifact_home: Path, repository_root: Path
) -> None:
    artifact = build_artifact(repository_root)
    document = serialize_artifact(artifact)
    store = ArtifactStore.pin(REPOSITORY_ID, repository_root)
    final = store.path_for(artifact.proposal_id)
    final.write_bytes(document)
    os.chmod(final, FILE_MODE)
    inode = final.stat().st_ino

    published = store.publish(artifact)

    assert published.created is False
    assert final.stat().st_ino == inode
    assert final.read_bytes() == document


def test_two_invocations_over_different_evidence_publish_two_artifacts(
    artifact_home: Path, repository_root: Path
) -> None:
    first = build_artifact(repository_root)
    second = build_artifact(
        repository_root, repository_identity=repository_identity(repository_root, head_sha="b" * 40)
    )
    assert first.proposal_id != second.proposal_id

    published = [publish(first, REPOSITORY_ID), publish(second, REPOSITORY_ID)]

    assert all(record.created for record in published)
    assert published[0].path.read_bytes() == serialize_artifact(first)
    assert published[1].path.read_bytes() == serialize_artifact(second)
    store = ArtifactStore.pin(REPOSITORY_ID, repository_root)
    assert sorted(store.published_artifact_paths()) == sorted(record.path for record in published)


# --------------------------------------------------------------------------------------
# Section 17.2 / 16.2 -- no-clobber and collision behaviour
# --------------------------------------------------------------------------------------


def test_a_corrupted_file_at_a_content_address_is_refused(
    artifact_home: Path, repository_root: Path
) -> None:
    artifact = build_artifact(repository_root)
    store = ArtifactStore.pin(REPOSITORY_ID, repository_root)
    final = store.path_for(artifact.proposal_id)
    final.write_bytes(b'{"hand": "edited"}')

    with pytest.raises(PublicationConflict) as failure:
        store.publish(artifact)

    assert failure.value.code == "PUBLICATION_CONFLICT"
    assert failure.value.digest_collision is False
    assert final.read_bytes() == b'{"hand": "edited"}'


def test_another_artifact_parked_at_this_address_is_refused(
    artifact_home: Path, repository_root: Path
) -> None:
    artifact = build_artifact(repository_root)
    other = build_artifact(repository_root, generated_prompt=f"{PROMPT}\nSecond evidence set.\n")
    store = ArtifactStore.pin(REPOSITORY_ID, repository_root)
    final = store.path_for(artifact.proposal_id)
    final.write_bytes(serialize_artifact(other))

    with pytest.raises(PublicationConflict) as failure:
        store.publish(artifact)

    assert failure.value.digest_collision is False
    assert other.proposal_id in str(failure.value)
    assert final.read_bytes() == serialize_artifact(other)


def test_a_republication_differing_only_in_the_unhashed_envelope_is_refused(
    artifact_home: Path, repository_root: Path
) -> None:
    """Section 17.2's no-clobber rule compares whole documents, byte for byte.

    Two invocations over identical evidence at different wall-clock times share one content
    address -- `generation_metadata` is excluded from the digest (section 16.3) -- yet their
    documents differ. The literal rule refuses that, never overwrites, and says exactly why.
    """
    first = build_artifact(repository_root)
    second = build_artifact(
        repository_root,
        generation_metadata=GenerationMetadata(
            generated_at="2026-08-05T07:07:17Z", tool_version="1.0.0"
        ),
    )
    assert first.proposal_id == second.proposal_id

    publish(first, REPOSITORY_ID)
    with pytest.raises(PublicationConflict) as failure:
        publish(second, REPOSITORY_ID)

    assert failure.value.digest_collision is False
    assert "generation_metadata" in str(failure.value)
    store = ArtifactStore.pin(REPOSITORY_ID, repository_root)
    assert store.path_for(first.proposal_id).read_bytes() == serialize_artifact(first)


# --------------------------------------------------------------------------------------
# Section 17.2 / 18 -- concurrency
# --------------------------------------------------------------------------------------


def test_concurrent_identical_invocations_converge_without_corruption(
    artifact_home: Path, repository_root: Path
) -> None:
    artifact = build_artifact(repository_root)
    resolve_artifact_root(REPOSITORY_ID, repository_root)

    with ThreadPoolExecutor(max_workers=8) as pool:
        records = [
            record.result()
            for record in [pool.submit(publish, artifact, REPOSITORY_ID) for _ in range(8)]
        ]

    store = ArtifactStore.pin(REPOSITORY_ID, repository_root)
    assert {record.path for record in records} == {store.path_for(artifact.proposal_id)}
    assert store.published_artifact_paths() == [store.path_for(artifact.proposal_id)]
    assert store.path_for(artifact.proposal_id).read_bytes() == serialize_artifact(artifact)


def test_a_lost_rename_race_is_handled_by_read_and_compare(
    artifact_home: Path, repository_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Section 17.2: the loser's rename fails with `FileExistsError` and it still succeeds.

    POSIX `rename` replaces its destination silently, so the only way to observe this branch on
    this platform is to reproduce the OS event itself: a concurrent invocation publishes the
    identical document first, and the rename refuses the now-existing destination.
    """
    artifact = build_artifact(repository_root)
    document = serialize_artifact(artifact)
    store = ArtifactStore.pin(REPOSITORY_ID, repository_root)
    final = store.path_for(artifact.proposal_id)

    def losing_rename(source: Any, destination: Any) -> None:
        Path(destination).write_bytes(document)
        raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), str(destination))

    monkeypatch.setattr(store_module.os, "rename", losing_rename)
    published = store.publish(artifact)

    assert published.created is False
    assert published.path == final
    assert final.read_bytes() == document
    assert [path.name for path in store.root.iterdir()] == [final.name]


def test_a_lost_race_against_different_content_is_still_refused(
    artifact_home: Path, repository_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = build_artifact(repository_root)
    store = ArtifactStore.pin(REPOSITORY_ID, repository_root)

    def losing_rename(source: Any, destination: Any) -> None:
        Path(destination).write_bytes(b'{"someone": "else"}')
        raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), str(destination))

    monkeypatch.setattr(store_module.os, "rename", losing_rename)
    with pytest.raises(PublicationConflict):
        store.publish(artifact)


def test_concurrent_conflicting_invocations_publish_two_distinct_artifacts(
    artifact_home: Path, repository_root: Path
) -> None:
    first = build_artifact(repository_root)
    second = build_artifact(repository_root, generated_prompt=f"{PROMPT}\nDifferent evidence.\n")
    assert first.proposal_id != second.proposal_id
    resolve_artifact_root(REPOSITORY_ID, repository_root)

    with ThreadPoolExecutor(max_workers=2) as pool:
        submitted = [
            pool.submit(publish, artifact, REPOSITORY_ID)
            for artifact in (first, second, first, second)
        ]
        records = [item.result() for item in submitted]

    store = ArtifactStore.pin(REPOSITORY_ID, repository_root)
    assert len(store.published_artifact_paths()) == 2
    assert {record.path for record in records} == set(store.published_artifact_paths())
    assert store.path_for(first.proposal_id).read_bytes() == serialize_artifact(first)
    assert store.path_for(second.proposal_id).read_bytes() == serialize_artifact(second)


# --------------------------------------------------------------------------------------
# Section 17.2 -- interruption, orphan temp files, recovery
# --------------------------------------------------------------------------------------


def test_a_crash_between_fsync_and_rename_leaves_nothing_at_the_final_path(
    artifact_home: Path, repository_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = build_artifact(repository_root)
    store = ArtifactStore.pin(REPOSITORY_ID, repository_root)
    final = store.path_for(artifact.proposal_id)

    def crash(source: Any, destination: Any) -> None:
        raise RuntimeError("simulated crash between fsync and rename")

    monkeypatch.setattr(store_module.os, "rename", crash)
    with pytest.raises(RuntimeError):
        store.publish(artifact)

    assert not final.exists()
    assert store.published_artifact_paths() == []

    monkeypatch.undo()
    published = store.publish(artifact)

    assert published.created is True
    assert final.read_bytes() == serialize_artifact(artifact)


def test_a_failed_rename_reports_a_publication_failure(
    artifact_home: Path, repository_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = build_artifact(repository_root)
    store = ArtifactStore.pin(REPOSITORY_ID, repository_root)

    def refuse(source: Any, destination: Any) -> None:
        raise OSError(errno.EACCES, os.strerror(errno.EACCES), str(destination))

    monkeypatch.setattr(store_module.os, "rename", refuse)
    with pytest.raises(PublicationFailure) as failure:
        store.publish(artifact)

    assert failure.value.code == "PUBLICATION_FAILURE"
    assert store.published_artifact_paths() == []


def test_an_orphan_temp_file_is_never_mistaken_for_an_artifact(
    artifact_home: Path, repository_root: Path
) -> None:
    artifact = build_artifact(repository_root)
    store = ArtifactStore.pin(REPOSITORY_ID, repository_root)
    orphan = store.root / f".{artifact.proposal_id}.0123456789abcdef.tmp"
    orphan.write_bytes(serialize_artifact(artifact))

    assert store.published_artifact_paths() == []

    published = store.publish(artifact)

    assert published.created is True
    assert store.published_artifact_paths() == [published.path]
    assert orphan.exists()


def test_a_partial_orphan_does_not_block_the_next_invocation(
    artifact_home: Path, repository_root: Path
) -> None:
    """Section 17.2: an interruption after fsync but before rename is fully recoverable."""
    artifact = build_artifact(repository_root)
    document = serialize_artifact(artifact)
    store = ArtifactStore.pin(REPOSITORY_ID, repository_root)
    partial = store.root / f".{artifact.proposal_id}.fedcba9876543210.tmp"
    partial.write_bytes(document[: len(document) // 2])

    published = store.publish(artifact)

    assert published.created is True
    assert published.path.read_bytes() == document
    assert store.published_artifact_paths() == [published.path]


def test_a_temp_file_is_created_inside_the_same_root(
    artifact_home: Path, repository_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The temp file shares the artifact root, which is what makes the rename same-filesystem."""
    artifact = build_artifact(repository_root)
    store = ArtifactStore.pin(REPOSITORY_ID, repository_root)
    observed: list[Path] = []
    real_rename = os.rename

    def observing_rename(source: Any, destination: Any) -> None:
        observed.append(Path(source))
        real_rename(source, destination)

    monkeypatch.setattr(store_module.os, "rename", observing_rename)
    store.publish(artifact)

    assert len(observed) == 1
    assert observed[0].parent == store.root
    assert mode_of(store.path_for(artifact.proposal_id)) == FILE_MODE


# --------------------------------------------------------------------------------------
# Section 17.2 -- root identity pinning and post-publication verification
# --------------------------------------------------------------------------------------


def test_a_root_replaced_underneath_the_invocation_is_path_escape(
    artifact_home: Path, repository_root: Path
) -> None:
    artifact = build_artifact(repository_root)
    store = ArtifactStore.pin(REPOSITORY_ID, repository_root)
    impostor = repository_root.parent / "impostor"
    impostor.mkdir(mode=ROOT_MODE)
    shutil.rmtree(store.root)
    # A genuinely different directory moved into the pinned path: same path, different inode.
    os.rename(impostor, store.root)

    with pytest.raises(PathEscape) as failure:
        store.publish(artifact)

    assert failure.value.code == "PATH_ESCAPE"
    assert store.published_artifact_paths() == []


def test_a_root_removed_underneath_the_invocation_is_path_escape(
    artifact_home: Path, repository_root: Path
) -> None:
    artifact = build_artifact(repository_root)
    store = ArtifactStore.pin(REPOSITORY_ID, repository_root)
    shutil.rmtree(store.root)

    with pytest.raises(PathEscape):
        store.publish(artifact)


def test_a_root_swapped_for_a_symlink_is_refused(
    artifact_home: Path, repository_root: Path, tmp_path: Path
) -> None:
    artifact = build_artifact(repository_root)
    store = ArtifactStore.pin(REPOSITORY_ID, repository_root)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    shutil.rmtree(store.root)
    store.root.symlink_to(elsewhere, target_is_directory=True)

    with pytest.raises(SymlinkPolicyViolation):
        store.publish(artifact)

    assert list(elsewhere.iterdir()) == []


def test_a_symlinked_publication_path_is_refused(
    artifact_home: Path, repository_root: Path, tmp_path: Path
) -> None:
    artifact = build_artifact(repository_root)
    store = ArtifactStore.pin(REPOSITORY_ID, repository_root)
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"untouched\n")
    store.path_for(artifact.proposal_id).symlink_to(outside)

    with pytest.raises(SymlinkPolicyViolation) as failure:
        store.publish(artifact)

    assert failure.value.code == "SYMLINK_POLICY_VIOLATION"
    assert outside.read_bytes() == b"untouched\n"


def test_post_publication_verification_catches_corruption_after_the_rename(
    artifact_home: Path, repository_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Section 17.2: success is reported only after the published file re-derives correctly."""
    artifact = build_artifact(repository_root)
    store = ArtifactStore.pin(REPOSITORY_ID, repository_root)
    real_rename = os.rename

    def corrupting_rename(source: Any, destination: Any) -> None:
        real_rename(source, destination)
        Path(destination).write_bytes(b'{"corrupted": "after the rename"}')

    monkeypatch.setattr(store_module.os, "rename", corrupting_rename)
    with pytest.raises(PublicationFailure) as failure:
        store.publish(artifact)

    assert failure.value.code == "PUBLICATION_FAILURE"
    assert artifact.proposal_id in str(failure.value)


def test_an_envelope_level_corruption_after_the_rename_is_caught(
    artifact_home: Path, repository_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A corruption the digest cannot see is caught by the byte comparison beside it."""
    artifact = build_artifact(repository_root)
    tampered = serialize_artifact(
        build_artifact(
            repository_root,
            generation_metadata=GenerationMetadata(
                generated_at="2026-08-05T07:07:17Z", tool_version="1.0.0"
            ),
        )
    )
    store = ArtifactStore.pin(REPOSITORY_ID, repository_root)
    real_rename = os.rename

    def corrupting_rename(source: Any, destination: Any) -> None:
        real_rename(source, destination)
        Path(destination).write_bytes(tampered)

    monkeypatch.setattr(store_module.os, "rename", corrupting_rename)
    with pytest.raises(PublicationFailure):
        store.publish(artifact)


def test_a_mis_addressed_artifact_is_refused_before_anything_is_written(
    artifact_home: Path, repository_root: Path
) -> None:
    artifact = build_artifact(repository_root)
    misaddressed = artifact.model_copy(update={"proposal_id": "f" * 64, "proposal_hash": "f" * 64})
    store = ArtifactStore.pin(REPOSITORY_ID, repository_root)

    with pytest.raises(PublicationFailure):
        store.publish(misaddressed)

    assert list(store.root.iterdir()) == []


def test_an_artifact_bound_to_another_repository_is_refused(
    artifact_home: Path, repository_root: Path, tmp_path: Path
) -> None:
    other = tmp_path / "other-repo"
    other.mkdir()
    artifact = build_artifact(other)
    store = ArtifactStore.pin(REPOSITORY_ID, repository_root)

    with pytest.raises(PathEscape):
        store.publish(artifact)

    assert list(store.root.iterdir()) == []
