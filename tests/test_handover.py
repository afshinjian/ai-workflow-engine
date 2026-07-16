import hashlib
from pathlib import Path

import pytest
from conftest import git, manifest_line

from ai_workflow_engine.config import load_config
from ai_workflow_engine.exceptions import ManifestParseError
from ai_workflow_engine.handover.manifest import parse_manifest
from ai_workflow_engine.handover.validators import HandoverSource, check_handover
from ai_workflow_engine.result import Status


def rewrite_manifest(repository: Path, content: bytes) -> None:
    text = "| Relative path | Size (bytes) | SHA-256 (prefix) |\n|---|---|---|\n"
    digest = hashlib.sha256(content).hexdigest()
    text += f"| `handover/PROJECT_HANDOVER.md` | {len(content)} | `{digest}` |\n"
    (repository / "handover/PROJECT_CHECKSUM.md").write_text(text)


def test_working_tree_checksum(repository: Path, config_factory: object) -> None:
    config = load_config(config_factory(repository))  # type: ignore[operator]
    assert check_handover(config).status == Status.PASS


def test_staged_blobs_not_working_tree(repository: Path, config_factory: object) -> None:
    path = repository / "handover/PROJECT_HANDOVER.md"
    staged = b"staged bytes\n"
    path.write_bytes(staged)
    rewrite_manifest(repository, staged)
    git(repository, "add", "handover/PROJECT_HANDOVER.md", "handover/PROJECT_CHECKSUM.md")
    path.write_bytes(b"different working bytes\n")
    config = load_config(config_factory(repository))  # type: ignore[operator]
    assert check_handover(config, source=HandoverSource.STAGED).status == Status.PASS
    assert check_handover(config, source=HandoverSource.WORKING_TREE).status == Status.FAIL


def test_staged_verification_when_working_tree_files_are_deleted(
    repository: Path, config_factory: object
) -> None:
    path = repository / "handover/PROJECT_HANDOVER.md"
    staged = b"staged without a working-tree copy\n"
    path.write_bytes(staged)
    rewrite_manifest(repository, staged)
    git(repository, "add", "handover/PROJECT_HANDOVER.md", "handover/PROJECT_CHECKSUM.md")
    path.unlink()
    (repository / "handover/PROJECT_CHECKSUM.md").unlink()

    config = load_config(config_factory(repository))  # type: ignore[operator]
    assert check_handover(config, source=HandoverSource.STAGED).status == Status.PASS


def test_committed_blobs_and_dirty_tree_mismatch(repository: Path, config_factory: object) -> None:
    path = repository / "handover/PROJECT_HANDOVER.md"
    committed = b"committed bytes\n"
    path.write_bytes(committed)
    rewrite_manifest(repository, committed)
    git(repository, "add", "handover/PROJECT_HANDOVER.md", "handover/PROJECT_CHECKSUM.md")
    git(repository, "commit", "-m", "valid manifest")
    path.write_bytes(b"dirty bytes\n")
    config = load_config(config_factory(repository))  # type: ignore[operator]
    assert check_handover(config, source=HandoverSource.COMMIT, commit="HEAD").status == Status.PASS
    assert check_handover(config, source=HandoverSource.WORKING_TREE).status == Status.FAIL


def test_committed_verification_when_working_tree_files_are_deleted(
    repository: Path, config_factory: object
) -> None:
    path = repository / "handover/PROJECT_HANDOVER.md"
    committed = b"committed without a working-tree copy\n"
    path.write_bytes(committed)
    rewrite_manifest(repository, committed)
    git(repository, "add", "handover/PROJECT_HANDOVER.md", "handover/PROJECT_CHECKSUM.md")
    git(repository, "commit", "-m", "commit handover blobs")
    path.unlink()
    (repository / "handover/PROJECT_CHECKSUM.md").unlink()

    config = load_config(config_factory(repository))  # type: ignore[operator]
    result = check_handover(config, source=HandoverSource.COMMIT, commit="HEAD")
    assert result.status == Status.PASS


def test_missing_working_tree_handover_file_is_reported(
    repository: Path, config_factory: object
) -> None:
    (repository / "handover/PROJECT_HANDOVER.md").unlink()
    config = load_config(config_factory(repository))  # type: ignore[operator]
    result = check_handover(config, source=HandoverSource.WORKING_TREE)
    assert result.status == Status.FAIL
    assert "manifest_file_missing" in {finding.code for finding in result.findings}


def test_explicit_byte_size_mismatch(repository: Path, config_factory: object) -> None:
    data = (repository / "handover/PROJECT_HANDOVER.md").read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    manifest = (
        "| Relative path | Size (bytes) | SHA-256 (prefix) |\n"
        "|---|---|---|\n"
        f"| `handover/PROJECT_HANDOVER.md` | {len(data) + 1} | `{digest}` |\n"
    )
    (repository / "handover/PROJECT_CHECKSUM.md").write_text(manifest)
    result = check_handover(load_config(config_factory(repository)))  # type: ignore[operator]
    assert result.status == Status.FAIL
    assert {finding.code for finding in result.findings} == {"size_mismatch"}


def test_full_digest_is_supported() -> None:
    data = b"x"
    digest = hashlib.sha256(data).hexdigest()
    records = parse_manifest(f"| `x` | 1 | `{digest}` |\n".encode())
    assert records[0].digest == digest


def test_duplicate_manifest_entry() -> None:
    row = manifest_line("x", b"x")
    with pytest.raises(ManifestParseError, match="Duplicate"):
        parse_manifest(f"{row}\n{row}\n".encode())


def test_canonical_duplicate_manifest_entry() -> None:
    first = manifest_line("handover/x", b"x")
    duplicate = manifest_line("handover/./x", b"x")
    with pytest.raises(ManifestParseError, match="Duplicate"):
        parse_manifest(f"{first}\n{duplicate}\n".encode())


def test_manifest_path_cannot_escape_repository() -> None:
    with pytest.raises(ManifestParseError, match="escapes repository"):
        parse_manifest(f"{manifest_line('../outside', b'x')}\n".encode())


def test_malformed_manifest_record() -> None:
    with pytest.raises(ManifestParseError, match="Malformed"):
        parse_manifest(b"| `x` | not-a-size | `deadbeef` |\n")
