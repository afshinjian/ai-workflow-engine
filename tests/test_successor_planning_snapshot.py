"""AUTO-015 section 7: repository identity, Git evidence and the snapshot protocol.

Every fixture here is a real Git repository on a real filesystem with real files, real
symlinks and real inodes. Nothing about the behaviour under test is mocked: a drift test
actually rewrites a file between two passes, a symlink test actually creates a symlink, and
an inode-substitution test actually replaces a file with `os.replace` so the content is
byte-identical while the inode is not. A stub standing in for any of those would prove only
that the stub behaved as written.

The AST assertions at the end are section 22 invariant 12's structural half: no mutating Git
subcommand and no independent subprocess surface anywhere in `snapshot.py`.
"""

import ast
import hashlib
import os
import re
import subprocess
import unicodedata
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
import yaml

from ai_workflow_engine.config import load_config
from ai_workflow_engine.git.client import GitClient
from ai_workflow_engine.models import EngineConfig
from ai_workflow_engine.successor_planning import snapshot as snapshot_module
from ai_workflow_engine.successor_planning.snapshot import (
    MAX_EVIDENCE_BYTES,
    AuthoritativeSourceError,
    DirtyBaselineError,
    EvidenceSnapshot,
    FileIdentity,
    InvalidInvocationError,
    PathEscapeError,
    RepositoryIdentityMismatchError,
    SnapshotDriftError,
    SymlinkPolicyViolationError,
    UpstreamPolicyError,
    artifact_root_for,
    canonical_remote_identity,
    canonical_repository_id,
    compare_snapshots,
    fixed_git_environment,
    normalize_evidence_text,
    read_evidence_bytes,
    resolve_repository_identity,
    sorted_directory_entries,
    take_snapshot,
)

SNAPSHOT_SOURCE = Path(snapshot_module.__file__)

# Section 22 invariant 12 names these explicitly; the rest are every other Git subcommand
# that writes to the repository, the index, the working tree or a remote.
MUTATING_GIT_SUBCOMMANDS = (
    "push",
    "commit",
    "checkout",
    "reset",
    "clean",
    "fetch",
    "pull",
    "clone",
    "merge",
    "rebase",
    "restore",
    "switch",
    "stash",
    "cherry-pick",
    "revert",
    "apply",
    "am",
    "init",
    "gc",
    "prune",
    "mv",
    "rm",
)


def git(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def config_path(repository: Path, config_factory: Callable[[Path], Path]) -> Path:
    return config_factory(repository)


@pytest.fixture
def config(config_path: Path) -> EngineConfig:
    return load_config(config_path)


def reconfigure(config_path: Path, section: str, **overrides: object) -> EngineConfig:
    """Rewrite the fixture configuration on disk and reload it through `load_config`."""
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    raw[section].update(overrides)
    config_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return load_config(config_path)


def rebind_root(config: EngineConfig, root: Path) -> EngineConfig:
    """Point a loaded configuration at `root` without going back through `load_config`.

    `load_config` resolves the configured root and refuses one that is absent, is not a
    directory, or is not a Git worktree, so every one of section 7.2's own root failures is
    unreachable through it. Rebinding the already-validated model is the only way to hand the
    snapshot protocol the inputs its rules exist to refuse -- and it is exactly the state a
    root that changed *after* configuration load would produce.
    """
    config.project.repository = root
    return config


def evidence_dir(repository: Path, *files: tuple[str, str]) -> str:
    """Create `docs/evidence/` holding `files` and return its repository-relative path."""
    directory = repository / "docs" / "evidence"
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in files:
        (directory / name).write_text(content, encoding="utf-8")
    return "docs/evidence"


# --------------------------------------------------------------------------------------
# Section 7.1a / DEC-010 -- the canonical repository identifier
# --------------------------------------------------------------------------------------

EQUIVALENT_REMOTES = (
    "https://github.com/afshin-jian/ai-workflow-engine.git",
    "https://github.com/afshin-jian/ai-workflow-engine",
    "https://GitHub.COM/afshin-jian/ai-workflow-engine.git",
    "https://token:x-oauth-basic@github.com/afshin-jian/ai-workflow-engine.git",
    "https://github.com:443/afshin-jian/ai-workflow-engine.git",
    "https://github.com/afshin-jian/ai-workflow-engine.git?depth=1#readme",
    "ssh://git@github.com/afshin-jian/ai-workflow-engine.git",
    "ssh://git@github.com:22/afshin-jian/ai-workflow-engine",
    "git@github.com:afshin-jian/ai-workflow-engine.git",
    "git@GITHUB.com:afshin-jian/ai-workflow-engine",
    "https://github.com/afshin-jian/ai-workflow-engine/",
)


def test_repository_id_is_the_normalized_name_and_a_twelve_hex_digest() -> None:
    identity = canonical_remote_identity(EQUIVALENT_REMOTES[0])
    assert identity == "github.com/afshin-jian/ai-workflow-engine"

    expected = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    assert canonical_repository_id(EQUIVALENT_REMOTES[0]) == f"ai-workflow-engine--{expected}"
    assert re.fullmatch(r"ai-workflow-engine--[0-9a-f]{12}", f"ai-workflow-engine--{expected}")


@pytest.mark.parametrize("remote", EQUIVALENT_REMOTES)
def test_equivalent_remote_spellings_normalize_to_one_identity(remote: str) -> None:
    assert canonical_remote_identity(remote) == "github.com/afshin-jian/ai-workflow-engine"
    assert canonical_repository_id(remote) == canonical_repository_id(EQUIVALENT_REMOTES[0])


def test_credentials_query_and_fragment_never_reach_the_identity() -> None:
    identity = canonical_remote_identity(
        "https://alice:s3cr3t-value@github.com/afshin-jian/ai-workflow-engine.git?a=b#c"
    )
    assert "s3cr3t-value" not in identity
    assert "alice" not in identity
    assert "?" not in identity and "#" not in identity


@pytest.mark.parametrize(
    "remote",
    [
        "file:///srv/git/ai-workflow-engine.git",
        "/srv/git/ai-workflow-engine.git",
        "../sibling-checkout",
        "./ai-workflow-engine",
        "",
        "   ",
    ],
)
def test_local_filesystem_paths_never_yield_a_repository_identity(remote: str) -> None:
    with pytest.raises(RepositoryIdentityMismatchError) as caught:
        canonical_repository_id(remote)
    assert caught.value.code == "REPOSITORY_IDENTITY_MISMATCH"


def test_a_non_default_port_names_a_different_endpoint() -> None:
    default = canonical_repository_id("ssh://git@example.test/owner/repo.git")
    other = canonical_repository_id("ssh://git@example.test:2222/owner/repo.git")
    assert default != other
    assert canonical_remote_identity("ssh://git@example.test:2222/owner/repo.git") == (
        "example.test:2222/owner/repo"
    )


@pytest.mark.parametrize(
    "remote",
    [
        "https://github.com/repo-with-no-owner.git",
        "https://github.com/",
        "git@github.com:repo.git",
        "https://github.com/owner/../escape.git",
    ],
)
def test_ambiguous_remote_identity_fails_closed(remote: str) -> None:
    with pytest.raises(RepositoryIdentityMismatchError):
        canonical_repository_id(remote)


def test_a_control_character_in_a_remote_fails_closed() -> None:
    with pytest.raises(RepositoryIdentityMismatchError):
        canonical_repository_id("https://github.com/owner/re\x00po.git")


def test_artifact_root_is_repository_scoped_and_outside_git(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    repository_id = canonical_repository_id(EQUIVALENT_REMOTES[0])
    root = artifact_root_for(repository_id)
    assert root == home / ".ai-workflow-engine" / "successor-proposals" / repository_id
    # Pure derivation: section 17.2 owns creation, permissions and containment, not this.
    assert not root.exists()


@pytest.mark.parametrize(
    "repository_id",
    [
        "ai-workflow-engine",
        "ai-workflow-engine--0123456789ab0",
        "ai-workflow-engine--0123456789A B",
        "Ai-Workflow-Engine--0123456789ab",
        "--0123456789ab",
        "../../etc--0123456789ab",
    ],
)
def test_artifact_root_refuses_a_non_canonical_repository_id(repository_id: str) -> None:
    with pytest.raises(InvalidInvocationError) as caught:
        artifact_root_for(repository_id)
    assert caught.value.code == "INVALID_INVOCATION"


# --------------------------------------------------------------------------------------
# Section 7.1 / 7.2 -- repository identity binding and its validation rules
# --------------------------------------------------------------------------------------


def test_identity_binds_root_baseline_and_configuration(
    repository: Path, config: EngineConfig, config_path: Path
) -> None:
    identity = resolve_repository_identity(config, config_path)

    assert identity.resolved_repository_root == str(repository.resolve())
    assert identity.git_worktree_root == identity.resolved_repository_root
    assert identity.configured_repository_id == "test-project"
    assert identity.branch == "main"
    assert identity.head_sha == git(repository, "rev-parse", "HEAD")
    assert identity.upstream_ref is None
    assert identity.ahead is None and identity.behind is None
    assert identity.config_hash == hashlib.sha256(config_path.read_bytes()).hexdigest()


def test_worktree_mismatch_fails_closed_without_guessing_between_two_roots(
    repository: Path, config: EngineConfig, config_path: Path
) -> None:
    # A subdirectory of the worktree resolves fine and is a legitimate Git working directory,
    # so the only thing that catches it is section 7.2 rule 1's equality requirement.
    rebind_root(config, repository / "docs")

    with pytest.raises(RepositoryIdentityMismatchError) as caught:
        resolve_repository_identity(config, config_path)

    assert caught.value.code == "REPOSITORY_IDENTITY_MISMATCH"
    message = str(caught.value)
    assert str(repository.resolve()) in message
    assert str((repository / "docs").resolve()) in message
    assert "refuses to guess" in message


def test_a_configured_root_that_does_not_resolve_is_invalid_invocation(
    tmp_path: Path, config: EngineConfig, config_path: Path
) -> None:
    rebind_root(config, tmp_path / "absent")
    with pytest.raises(InvalidInvocationError) as caught:
        resolve_repository_identity(config, config_path)
    assert caught.value.code == "INVALID_INVOCATION"


def test_a_symlinked_configured_root_is_refused(
    repository: Path, tmp_path: Path, config: EngineConfig, config_path: Path
) -> None:
    link = tmp_path / "repo-link"
    link.symlink_to(repository, target_is_directory=True)
    rebind_root(config, link)

    with pytest.raises(SymlinkPolicyViolationError) as caught:
        resolve_repository_identity(config, config_path)
    assert caught.value.code == "SYMLINK_POLICY_VIOLATION"


def test_a_configured_root_outside_any_worktree_is_invalid_invocation(
    tmp_path: Path, config: EngineConfig, config_path: Path
) -> None:
    outside = tmp_path / "not-a-worktree"
    outside.mkdir()
    rebind_root(config, outside)
    with pytest.raises(InvalidInvocationError):
        resolve_repository_identity(config, config_path)


def test_a_dirty_working_tree_alone_does_not_stop_the_invocation(
    repository: Path, config: EngineConfig, config_path: Path
) -> None:
    # Section 7.2 rule 4: AUTO-015 is a read-only reporting tool, not a stage-implementation
    # session, so ordinary dirtiness is captured as evidence rather than refused.
    (repository / "docs" / "PROJECT_STATE.md").write_text("changed\n", encoding="utf-8")
    (repository / "docs" / "scratch.md").write_text("scratch\n", encoding="utf-8")
    git(repository, "add", "docs/scratch.md")

    identity = resolve_repository_identity(config, config_path)

    assert "docs/PROJECT_STATE.md" in identity.modified_files
    assert "docs/scratch.md" in identity.staged_files


def test_protected_path_dirtiness_fails_closed_as_a_dirty_baseline(
    repository: Path, config_path: Path
) -> None:
    config = reconfigure(
        config_path,
        "protected_paths",
        never_stage=["docs/secret-*.md"],
        never_commit=["docs/secret-*.md"],
    )
    (repository / "docs" / "secret-notes.md").write_text("protected\n", encoding="utf-8")
    git(repository, "add", "docs/secret-notes.md")

    with pytest.raises(DirtyBaselineError) as caught:
        resolve_repository_identity(config, config_path)
    assert caught.value.code == "DIRTY_BASELINE"


def test_upstream_missing_on_the_default_branch_fails_closed(
    config_path: Path,
) -> None:
    config = reconfigure(config_path, "project", require_upstream=True)
    with pytest.raises(UpstreamPolicyError) as caught:
        resolve_repository_identity(config, config_path)
    assert caught.value.code == "UPSTREAM_POLICY_FAILURE"


def test_upstream_missing_on_a_local_only_working_branch_is_tolerated(
    repository: Path, config_path: Path
) -> None:
    # The one documented, precedented tolerance: a freshly created, not-yet-pushed branch.
    git(repository, "branch", "feature/local-only")
    git(repository, "symbolic-ref", "HEAD", "refs/heads/feature/local-only")
    config = reconfigure(config_path, "project", require_upstream=True)

    identity = resolve_repository_identity(config, config_path)

    assert identity.branch == "feature/local-only"
    assert identity.upstream_ref is None


def test_upstream_and_ahead_behind_are_captured_when_present(
    repository_with_remote: Path, config_factory: Callable[[Path], Path]
) -> None:
    path = config_factory(repository_with_remote)
    config = load_config(path)

    identity = resolve_repository_identity(config, path)

    assert identity.upstream_ref == "origin/main"
    assert identity.ahead == 0
    assert identity.behind == 0


# --------------------------------------------------------------------------------------
# Section 16.2 -- locale-independent Git parsing
# --------------------------------------------------------------------------------------


def test_fixed_git_environment_pins_and_then_restores_the_locale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LC_ALL", "tr_TR.UTF-8")
    monkeypatch.delenv("LANGUAGE", raising=False)

    with fixed_git_environment():
        assert os.environ["LC_ALL"] == "C"
        assert os.environ["LANG"] == "C"
        assert os.environ["LANGUAGE"] == "C"
        assert os.environ["GIT_OPTIONAL_LOCKS"] == "0"

    assert os.environ["LC_ALL"] == "tr_TR.UTF-8"
    assert "LANGUAGE" not in os.environ


def test_fixed_git_environment_restores_on_an_exception_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LC_ALL", "tr_TR.UTF-8")
    with pytest.raises(RuntimeError):
        with fixed_git_environment():
            raise RuntimeError("boom")
    assert os.environ["LC_ALL"] == "tr_TR.UTF-8"


@pytest.mark.parametrize("locale", ["tr_TR.UTF-8", "de_DE.UTF-8"])
def test_identity_is_identical_under_two_display_locales(
    monkeypatch: pytest.MonkeyPatch,
    config: EngineConfig,
    config_path: Path,
    locale: str,
) -> None:
    baseline = resolve_repository_identity(config, config_path)
    monkeypatch.setenv("LC_ALL", locale)
    monkeypatch.setenv("LANG", locale)
    assert resolve_repository_identity(config, config_path) == baseline


# --------------------------------------------------------------------------------------
# Section 7.3 steps 2-7 -- the read discipline
# --------------------------------------------------------------------------------------


def test_a_symlinked_authoritative_input_is_refused(
    repository: Path, config: EngineConfig, config_path: Path
) -> None:
    target = repository / "handover" / "PROJECT_HANDOVER.md"
    decoy = repository / "handover" / "decoy.md"
    decoy.write_text("decoy\n", encoding="utf-8")
    target.unlink()
    target.symlink_to(decoy)

    with pytest.raises(SymlinkPolicyViolationError) as caught:
        take_snapshot(config, config_path)
    assert caught.value.code == "SYMLINK_POLICY_VIOLATION"


def test_a_symlink_is_refused_by_the_read_primitive_itself(tmp_path: Path) -> None:
    real = tmp_path / "real.md"
    real.write_text("real\n", encoding="utf-8")
    link = tmp_path / "link.md"
    link.symlink_to(real)

    with pytest.raises(SymlinkPolicyViolationError):
        read_evidence_bytes(link, "the input")


def test_the_posix_read_path_is_atomically_no_follow() -> None:
    # Section 7.5: this platform has `O_NOFOLLOW`, so the refusal above came from the atomic
    # open rather than from the degraded check-then-use fallback. The fallback still exists,
    # and the module names it as a residual TOCTOU gap rather than presenting the two as
    # equivalent -- asserted below by
    # `test_the_residual_risk_statement_is_reproduced_in_the_module`.
    assert os.name == "posix"
    assert snapshot_module.HAS_ATOMIC_NO_FOLLOW is True
    assert os.O_NOFOLLOW != 0


def test_a_per_file_ceiling_fails_the_read_instead_of_truncating(tmp_path: Path) -> None:
    oversized = tmp_path / "oversized.md"
    oversized.write_bytes(b"x" * 512)

    with pytest.raises(AuthoritativeSourceError) as caught:
        read_evidence_bytes(oversized, "the input", ceiling=256)
    assert caught.value.code == "AUTHORITATIVE_SOURCE_MISSING"
    assert "256" in str(caught.value)

    # Exactly at the ceiling still reads, so the boundary is inclusive and not off by one.
    data, _ = read_evidence_bytes(oversized, "the input", ceiling=512)
    assert len(data) == 512


def test_the_default_ceiling_stops_an_oversized_authoritative_input(
    repository: Path, config: EngineConfig, config_path: Path
) -> None:
    target = repository / "handover" / "PROJECT_HANDOVER.md"
    target.write_bytes(b"x" * (MAX_EVIDENCE_BYTES + 1))

    with pytest.raises(AuthoritativeSourceError) as caught:
        take_snapshot(config, config_path)
    assert str(MAX_EVIDENCE_BYTES) in str(caught.value)


def test_a_non_regular_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(AuthoritativeSourceError):
        read_evidence_bytes(tmp_path, "the input")


def test_an_absent_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(AuthoritativeSourceError):
        read_evidence_bytes(tmp_path / "absent.md", "the input")


def test_both_the_original_and_the_normalized_hash_are_recorded(
    repository: Path, config: EngineConfig, config_path: Path
) -> None:
    raw = b"first line\r\nsecond line\r\n"
    (repository / "handover" / "PROJECT_HANDOVER.md").write_bytes(raw)

    taken = take_snapshot(config, config_path)
    record = next(item for item in taken.files if item.path == "handover/PROJECT_HANDOVER.md")

    assert record.original_sha256 == hashlib.sha256(raw).hexdigest()
    assert record.normalized_sha256 == hashlib.sha256(b"first line\nsecond line\n").hexdigest()
    assert record.original_sha256 != record.normalized_sha256
    assert record.size == len(raw)


def test_a_bare_carriage_return_is_refused_rather_than_rewritten() -> None:
    with pytest.raises(AuthoritativeSourceError) as caught:
        normalize_evidence_text(b"one\rtwo\n", "the input")
    assert "carriage return" in str(caught.value)


def test_undecodable_content_is_refused() -> None:
    with pytest.raises(AuthoritativeSourceError):
        normalize_evidence_text(b"\xff\xfe not utf-8", "the input")


def test_normalization_applies_nfc_before_hashing() -> None:
    decomposed = "évidence\n"
    assert normalize_evidence_text(decomposed.encode("utf-8"), "the input") == (
        unicodedata.normalize("NFC", decomposed)
    )


# --------------------------------------------------------------------------------------
# Section 16.2 -- manifest paths, evidence ordering and directory traversal
# --------------------------------------------------------------------------------------


def test_evidence_manifest_paths_are_stored_relative_to_the_resolved_root(
    repository: Path, config: EngineConfig, config_path: Path
) -> None:
    taken = take_snapshot(config, config_path, inputs=["docs/TASK_QUEUE.md"])
    root = Path(taken.identity.resolved_repository_root)

    for reference in taken.evidence_manifest():
        assert not reference.path.startswith("/")
        assert str(repository) not in reference.path
        assert (root / reference.path).is_file()

    manifest = {reference.path: reference for reference in taken.evidence_manifest()}
    assert "docs/TASK_QUEUE.md" in manifest
    assert "handover/PROJECT_CHECKSUM.md" in manifest
    assert manifest["docs/TASK_QUEUE.md"].sha256 == next(
        item.normalized_sha256 for item in taken.files if item.path == "docs/TASK_QUEUE.md"
    )


def test_handover_evidence_is_a_required_input_not_an_optional_one(
    config: EngineConfig, config_path: Path
) -> None:
    paths = {item.path for item in take_snapshot(config, config_path).files}
    assert paths == {
        "handover/BOOTSTRAP_PROMPT.md",
        "handover/PROJECT_CHECKSUM.md",
        "handover/PROJECT_HANDOVER.md",
    }


def test_snapshot_files_are_sorted_bytewise_by_path(
    repository: Path, config: EngineConfig, config_path: Path
) -> None:
    directory = evidence_dir(repository, ("zeta.md", "z\n"), ("alpha.md", "a\n"))
    inputs = [f"{directory}/zeta.md", "docs/TASK_QUEUE.md"]
    taken = take_snapshot(config, config_path, inputs=inputs)

    paths = [item.path for item in taken.files]
    assert paths == sorted(paths, key=lambda value: value.encode("utf-8"))


def test_directory_listings_are_sorted_by_name_before_use(
    repository: Path, config: EngineConfig, config_path: Path
) -> None:
    # Created in deliberately reverse order so a raw `readdir` order would very likely differ
    # from the required one on at least one filesystem.
    directory = evidence_dir(
        repository,
        ("zeta.md", "z\n"),
        ("mid.md", "m\n"),
        ("Alpha.md", "A\n"),
        ("alpha.md", "a\n"),
    )
    names = sorted_directory_entries(repository / directory, "the directory")
    assert names == ["Alpha.md", "alpha.md", "mid.md", "zeta.md"]

    taken = take_snapshot(config, config_path, inputs=[directory])
    expanded = [item.path for item in taken.files if item.path.startswith(f"{directory}/")]
    assert expanded == [
        f"{directory}/Alpha.md",
        f"{directory}/alpha.md",
        f"{directory}/mid.md",
        f"{directory}/zeta.md",
    ]


def test_a_symlink_inside_an_expanded_directory_fails_closed(
    repository: Path, config: EngineConfig, config_path: Path
) -> None:
    directory = evidence_dir(repository, ("real.md", "real\n"))
    (repository / directory / "link.md").symlink_to(repository / directory / "real.md")

    with pytest.raises(SymlinkPolicyViolationError):
        take_snapshot(config, config_path, inputs=[directory])


def test_a_path_escaping_the_repository_root_is_refused(
    repository: Path, tmp_path: Path, config: EngineConfig, config_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "planted.md").write_text("planted\n", encoding="utf-8")
    (repository / "docs" / "escape").symlink_to(outside, target_is_directory=True)

    with pytest.raises(PathEscapeError) as caught:
        take_snapshot(config, config_path, inputs=["docs/escape/planted.md"])
    assert caught.value.code == "PATH_ESCAPE"


@pytest.mark.parametrize("bad", ["/etc/passwd", "docs/../../escape.md", "docs//x.md", ""])
def test_a_non_repository_relative_input_is_invalid_invocation(
    config: EngineConfig, config_path: Path, bad: str
) -> None:
    with pytest.raises(InvalidInvocationError):
        take_snapshot(config, config_path, inputs=[bad])


# --------------------------------------------------------------------------------------
# Section 7.3 steps 11-13 -- pre-publication re-snapshot and drift detection
# --------------------------------------------------------------------------------------


def test_two_unchanged_passes_agree(config: EngineConfig, config_path: Path) -> None:
    initial = take_snapshot(config, config_path)
    final = take_snapshot(config, config_path)
    assert compare_snapshots(initial, final) is None
    assert initial == final


def test_a_changed_hash_is_drift(repository: Path, config: EngineConfig, config_path: Path) -> None:
    initial = take_snapshot(config, config_path)
    (repository / "handover" / "PROJECT_HANDOVER.md").write_text("tampered\n", encoding="utf-8")
    final = take_snapshot(config, config_path)

    with pytest.raises(SnapshotDriftError) as caught:
        compare_snapshots(initial, final)
    assert caught.value.code == "INPUT_DRIFT"
    assert any("normalized_sha256" in difference for difference in caught.value.differences)


def test_a_changed_inode_at_the_same_path_is_drift(
    repository: Path, config: EngineConfig, config_path: Path
) -> None:
    target = repository / "handover" / "PROJECT_HANDOVER.md"
    original = target.read_bytes()
    initial = take_snapshot(config, config_path)

    # Byte-identical content, brand-new inode: only the stable-identity tuple can see this.
    replacement = repository / "handover" / ".substitute"
    replacement.write_bytes(original)
    os.replace(replacement, target)
    final = take_snapshot(config, config_path)

    initial_record = next(i for i in initial.files if i.path == "handover/PROJECT_HANDOVER.md")
    final_record = next(i for i in final.files if i.path == "handover/PROJECT_HANDOVER.md")
    assert initial_record.normalized_sha256 == final_record.normalized_sha256
    assert initial_record.inode != final_record.inode

    with pytest.raises(SnapshotDriftError) as caught:
        compare_snapshots(initial, final)
    assert any("inode" in difference for difference in caught.value.differences)


def test_a_symlink_swap_of_an_input_is_refused_on_the_second_pass(
    repository: Path, config: EngineConfig, config_path: Path
) -> None:
    take_snapshot(config, config_path)

    target = repository / "handover" / "PROJECT_HANDOVER.md"
    decoy = repository / "handover" / "decoy.md"
    decoy.write_text("decoy\n", encoding="utf-8")
    target.unlink()
    target.symlink_to(decoy)

    with pytest.raises(SymlinkPolicyViolationError):
        take_snapshot(config, config_path)


def test_a_symlink_swap_of_a_parent_component_is_drift(
    repository: Path, config: EngineConfig, config_path: Path
) -> None:
    # `O_NOFOLLOW` guards only the final component, so a swapped *directory* component is
    # exactly the residual case the module documents as caught after the fact instead.
    directory = repository / "docs" / "evidence"
    directory.mkdir(parents=True)
    (directory / "report.md").write_text("original\n", encoding="utf-8")
    initial = take_snapshot(config, config_path, inputs=["docs/evidence/report.md"])

    substitute = repository / "docs" / "evidence-substitute"
    substitute.mkdir()
    (substitute / "report.md").write_text("substituted\n", encoding="utf-8")
    (directory / "report.md").unlink()
    directory.rmdir()
    (repository / "docs" / "evidence").symlink_to(substitute, target_is_directory=True)

    final = take_snapshot(config, config_path, inputs=["docs/evidence/report.md"])

    with pytest.raises(SnapshotDriftError) as caught:
        compare_snapshots(initial, final)
    assert any("inode" in difference for difference in caught.value.differences)
    assert any("normalized_sha256" in difference for difference in caught.value.differences)


def test_compare_detects_a_symlink_status_change(config: EngineConfig, config_path: Path) -> None:
    initial = take_snapshot(config, config_path)
    swapped = initial.files[0].model_copy(update={"is_symlink": True})
    final = initial.model_copy(update={"files": [swapped, *initial.files[1:]]})

    with pytest.raises(SnapshotDriftError) as caught:
        compare_snapshots(initial, final)
    assert caught.value.code == "INPUT_DRIFT"
    assert any("is_symlink" in difference for difference in caught.value.differences)


def test_a_branch_change_is_drift(
    repository: Path, config: EngineConfig, config_path: Path
) -> None:
    initial = take_snapshot(config, config_path)
    git(repository, "branch", "feature/drift")
    git(repository, "symbolic-ref", "HEAD", "refs/heads/feature/drift")
    final = take_snapshot(config, config_path)

    with pytest.raises(SnapshotDriftError) as caught:
        compare_snapshots(initial, final)
    assert any("repository_identity.branch" in item for item in caught.value.differences)


def test_a_head_change_is_drift(repository: Path, config: EngineConfig, config_path: Path) -> None:
    initial = take_snapshot(config, config_path)
    (repository / "docs" / "PROJECT_STATE.md").write_text(
        "| Task | Status |\n|---|---|\n| T-1 | Planned |\nVersion: 1.0.1\n", encoding="utf-8"
    )
    git(repository, "add", "docs/PROJECT_STATE.md")
    git(repository, "commit", "-m", "second")
    final = take_snapshot(config, config_path)

    with pytest.raises(SnapshotDriftError) as caught:
        compare_snapshots(initial, final)
    assert any("repository_identity.head_sha" in item for item in caught.value.differences)


def test_a_dirty_tree_change_is_drift(
    repository: Path, config: EngineConfig, config_path: Path
) -> None:
    initial = take_snapshot(config, config_path)
    (repository / "docs" / "scratch.md").write_text("scratch\n", encoding="utf-8")
    final = take_snapshot(config, config_path)

    with pytest.raises(SnapshotDriftError) as caught:
        compare_snapshots(initial, final)
    assert any("untracked_files" in item for item in caught.value.differences)


def test_a_configuration_change_is_drift(config: EngineConfig, config_path: Path) -> None:
    initial = take_snapshot(config, config_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8") + "# an inert trailing comment\n",
        encoding="utf-8",
    )
    final = take_snapshot(config, config_path)

    with pytest.raises(SnapshotDriftError) as caught:
        compare_snapshots(initial, final)
    assert any("repository_identity.config_hash" in item for item in caught.value.differences)


def test_added_and_removed_evidence_are_both_drift(
    repository: Path, config: EngineConfig, config_path: Path
) -> None:
    directory = evidence_dir(repository, ("one.md", "one\n"))
    initial = take_snapshot(config, config_path, inputs=[directory])

    (repository / directory / "two.md").write_text("two\n", encoding="utf-8")
    added = take_snapshot(config, config_path, inputs=[directory])
    with pytest.raises(SnapshotDriftError) as caught:
        compare_snapshots(initial, added)
    assert any("appeared" in item for item in caught.value.differences)

    with pytest.raises(SnapshotDriftError) as caught:
        compare_snapshots(added, initial)
    assert any("disappeared" in item for item in caught.value.differences)


def test_drift_reports_every_difference_not_only_the_first(
    repository: Path, config: EngineConfig, config_path: Path
) -> None:
    initial = take_snapshot(config, config_path)
    (repository / "handover" / "PROJECT_HANDOVER.md").write_text("one\n", encoding="utf-8")
    (repository / "handover" / "BOOTSTRAP_PROMPT.md").write_text("two\n", encoding="utf-8")
    final = take_snapshot(config, config_path)

    with pytest.raises(SnapshotDriftError) as caught:
        compare_snapshots(initial, final)
    prefixes = {"evidence handover/PROJECT_HANDOVER.md ", "evidence handover/BOOTSTRAP_PROMPT.md "}
    for prefix in prefixes:
        assert any(item.startswith(prefix) for item in caught.value.differences)


def placeholder_identity() -> dict[str, object]:
    return {
        "configured_repository_root": "/repo",
        "resolved_repository_root": "/repo",
        "configured_repository_id": "test-project",
        "git_worktree_root": "/repo",
        "branch": "main",
        "head_sha": "0" * 40,
        "upstream_ref": None,
        "ahead": None,
        "behind": None,
        "modified_files": [],
        "staged_files": [],
        "untracked_files": [],
        "config_hash": "c" * 64,
    }


def placeholder_file(path: str) -> dict[str, object]:
    return FileIdentity(
        path=path,
        device=1,
        inode=2,
        size=3,
        mtime_ns=4,
        is_symlink=False,
        original_sha256="a" * 64,
        normalized_sha256="b" * 64,
    ).model_dump()


def test_an_out_of_order_snapshot_cannot_be_constructed() -> None:
    # Section 16.2 evidence ordering is enforced at the model layer, so a caller cannot hand
    # `compare_snapshots` two differently-ordered manifests and have them look unequal.
    with pytest.raises(ValueError, match="sorted by path"):
        EvidenceSnapshot.model_validate(
            {
                "identity": placeholder_identity(),
                "files": [placeholder_file("b.md"), placeholder_file("a.md")],
            }
        )


# --------------------------------------------------------------------------------------
# Section 22 invariant 12 -- structural, AST-level Git and subprocess assertions
# --------------------------------------------------------------------------------------


def module_tree() -> ast.Module:
    return ast.parse(SNAPSHOT_SOURCE.read_text(encoding="utf-8"))


def docstring_nodes(tree: ast.Module) -> set[int]:
    """Identify every string constant that is a module/class/function docstring."""
    identifiers: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                identifiers.add(id(first.value))
    return identifiers


def string_constants(tree: ast.Module) -> Iterator[str]:
    """Every string constant in the module except its prose docstrings."""
    docstrings = docstring_nodes(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                yield node.value


def test_no_mutating_git_subcommand_appears_in_the_module() -> None:
    pattern = re.compile(r"\b(" + "|".join(MUTATING_GIT_SUBCOMMANDS) + r")\b")
    offenders = [value for value in string_constants(module_tree()) if pattern.search(value)]
    assert offenders == []


def test_every_git_argument_list_is_on_the_read_only_allowlist() -> None:
    allowed = {form[0] for form in GitClient.READ_ONLY_FORMS}
    subcommand = re.compile(r"[a-z][a-z-]*")
    for node in ast.walk(module_tree()):
        if not isinstance(node, ast.List | ast.Tuple):
            continue
        elements = node.elts
        if not elements:
            continue
        head = elements[0]
        if not (isinstance(head, ast.Constant) and isinstance(head.value, str)):
            continue
        if subcommand.fullmatch(head.value) is None:
            continue
        if not all(
            isinstance(item, ast.Constant) and isinstance(item.value, str) for item in elements[1:]
        ):
            continue
        # A fully literal list of lowercase words is argv-shaped; the only such list this
        # module may contain is an allowlisted Git read.
        assert head.value in allowed, f"{head.value!r} is not an allowlisted Git read"


def test_no_independent_subprocess_or_shell_surface_exists() -> None:
    tree = module_tree()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] != "subprocess"
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] != "subprocess"
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                assert keyword.arg != "shell"
            if isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"system", "popen", "execv", "spawnv"}


def test_the_module_never_imports_the_agentos_workflow_package() -> None:
    tree = module_tree()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(not alias.name.startswith("agentos_workflow") for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("agentos_workflow")


def test_the_residual_risk_statement_is_reproduced_in_the_module() -> None:
    # Section 7.4 requires a future implementation to state the residual-risk paragraph in
    # its own design notes and forbids describing the protocol as perfect isolation.
    # Whitespace-collapsed, because the paragraph is line-wrapped in the source.
    text = " ".join((snapshot_module.__doc__ or "").split())
    assert "OS-level atomic snapshot" in text
    assert "fail-closed detection at the boundary that matters" in text
    assert "This is not perfect isolation and must never be described as such" in text
    assert "residual TOCTOU gap" in text
