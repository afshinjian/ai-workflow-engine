"""Engine execution provenance (T-307): classification, version reconciliation, and OD-1.

These tests exercise the *real* resolver. `tests/conftest.py`'s autouse seam substitutes the
name only inside consumer modules, never inside `ai_workflow_engine.provenance` itself, so
nothing here is stubbed out from under the assertions.
"""

import hashlib
import json
import subprocess
from importlib import metadata
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

import ai_workflow_engine
from ai_workflow_engine import provenance
from ai_workflow_engine.agents import runner as runner_module
from ai_workflow_engine.cli import app as cli_app
from ai_workflow_engine.prompt import context as context_module
from ai_workflow_engine.prompt.models import CanonicalEngineProvenance
from ai_workflow_engine.provenance import (
    EngineProvenanceError,
    _classify_direct_url,
    _classify_install_mode,
    _engine_worktree_root,
    _load_distribution,
    _resolve_version,
    resolve_engine_provenance,
)

VALID_URL = "file:///home/example/engine"
COMMIT = "a" * 40


def write_dist_info(root: Path, *, version: str = "9.9.9", direct_url: str | None = None) -> Path:
    """A synthetic `.dist-info` directory readable by `importlib.metadata.Distribution.at`."""
    dist_info = root / f"ai_workflow_engine-{version}.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: ai-workflow-engine\nVersion: {version}\n",
        encoding="utf-8",
    )
    if direct_url is not None:
        (dist_info / "direct_url.json").write_text(direct_url, encoding="utf-8")
    return dist_info


def distribution_at(path: Path) -> metadata.Distribution:
    return metadata.Distribution.at(path)


def git(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def engine_worktree(tmp_path: Path) -> Path:
    """A committed Git worktree containing a package directory, standing in for the engine."""
    root = tmp_path / "engine"
    package = root / "src" / "ai_workflow_engine"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('__version__ = "9.9.9"\n', encoding="utf-8")
    git(root.parent, "init", "-b", "main", str(root))
    git(root, "config", "user.email", "tests@example.invalid")
    git(root, "config", "user.name", "Workflow Tests")
    git(root, "add", ".")
    git(root, "commit", "-m", "initial")
    return root


def install_engine(
    monkeypatch: pytest.MonkeyPatch,
    *,
    worktree: Path | None,
    package_path: Path,
    distribution: metadata.Distribution | None,
    version: str = "9.9.9",
) -> None:
    """Point the resolver at a synthetic engine without touching the real installation."""
    monkeypatch.setattr(provenance, "_package_path", lambda: package_path.resolve())
    monkeypatch.setattr(provenance, "_load_distribution", lambda: distribution)
    monkeypatch.setattr(ai_workflow_engine, "__version__", version)
    if worktree is None:
        monkeypatch.setattr(provenance, "_engine_worktree_root", lambda _path: None)


# ---- Install-mode classification: the two metadata-absent cases (rows 1-2) -----


def test_absent_distribution_metadata_is_source() -> None:
    assert _classify_install_mode(None) == "source"


def test_distribution_without_direct_url_is_installed(tmp_path: Path) -> None:
    distribution = distribution_at(write_dist_info(tmp_path))
    assert _classify_install_mode(distribution) == "installed"


def test_distribution_direct_url_is_read_from_the_real_metadata_file(tmp_path: Path) -> None:
    payload = json.dumps({"url": VALID_URL, "dir_info": {"editable": True}})
    distribution = distribution_at(write_dist_info(tmp_path, direct_url=payload))
    assert _classify_install_mode(distribution) == "editable"


# ---- Valid direct_url records (rows 3-9) --------------------------------------

VALID_RECORDS: list[tuple[str, dict[str, Any], str]] = [
    ("editable dir_info", {"url": VALID_URL, "dir_info": {"editable": True}}, "editable"),
    (
        "non-editable dir_info",
        {"url": VALID_URL, "dir_info": {"editable": False}},
        "installed",
    ),
    ("bare dir_info", {"url": VALID_URL, "dir_info": {}}, "installed"),
    (
        "vcs_info",
        {"url": VALID_URL, "vcs_info": {"vcs": "git", "commit_id": COMMIT}},
        "installed",
    ),
    (
        "vcs_info with requested_revision",
        {
            "url": VALID_URL,
            "vcs_info": {"vcs": "git", "commit_id": COMMIT, "requested_revision": "main"},
        },
        "installed",
    ),
    (
        "archive_info with hashes",
        {"url": VALID_URL, "archive_info": {"hashes": {"sha256": "b" * 64}}},
        "installed",
    ),
    ("bare archive_info", {"url": VALID_URL, "archive_info": {}}, "installed"),
]


@pytest.mark.parametrize(
    ("document", "expected"),
    [(document, expected) for _label, document, expected in VALID_RECORDS],
    ids=[label for label, _document, _expected in VALID_RECORDS],
)
def test_valid_direct_url_records_classify(document: dict[str, Any], expected: str) -> None:
    assert _classify_direct_url(json.dumps(document)) == expected


def test_a_subdirectory_string_is_accepted() -> None:
    document = {"url": VALID_URL, "dir_info": {"editable": True}, "subdirectory": "src"}
    assert _classify_direct_url(json.dumps(document)) == "editable"


# ---- Invalid direct_url records (rows 10-26) ----------------------------------

INVALID_RAW_RECORDS: list[tuple[str, str, str]] = [
    ("truncated json", '{"url": "file:///x", "dir_info": {', "engine_direct_url_malformed"),
    (
        "trailing comma",
        '{"url": "file:///x", "dir_info": {},}',
        "engine_direct_url_malformed",
    ),
    ("empty document", "", "engine_direct_url_malformed"),
    ("top-level list", "[]", "engine_direct_url_not_object"),
    ("top-level string", '"x"', "engine_direct_url_not_object"),
    ("top-level number", "1", "engine_direct_url_not_object"),
    ("top-level bool", "true", "engine_direct_url_not_object"),
    ("top-level null", "null", "engine_direct_url_not_object"),
]

INVALID_DOCUMENTS: list[tuple[str, dict[str, Any], str]] = [
    ("no url", {"dir_info": {}}, "engine_direct_url_missing_url"),
    ("url is a number", {"url": 1, "dir_info": {}}, "engine_direct_url_invalid_url_type"),
    ("url is null", {"url": None, "dir_info": {}}, "engine_direct_url_invalid_url_type"),
    ("url is an object", {"url": {}, "dir_info": {}}, "engine_direct_url_invalid_url_type"),
    ("no descriptor", {"url": VALID_URL}, "engine_direct_url_no_source"),
    (
        "dir_info and vcs_info",
        {"url": VALID_URL, "dir_info": {}, "vcs_info": {"vcs": "git", "commit_id": COMMIT}},
        "engine_direct_url_multiple_sources",
    ),
    (
        "dir_info and archive_info",
        {"url": VALID_URL, "dir_info": {}, "archive_info": {}},
        "engine_direct_url_multiple_sources",
    ),
    (
        "vcs_info and archive_info",
        {
            "url": VALID_URL,
            "vcs_info": {"vcs": "git", "commit_id": COMMIT},
            "archive_info": {},
        },
        "engine_direct_url_multiple_sources",
    ),
    (
        "all three descriptors",
        {
            "url": VALID_URL,
            "dir_info": {},
            "vcs_info": {"vcs": "git", "commit_id": COMMIT},
            "archive_info": {},
        },
        "engine_direct_url_multiple_sources",
    ),
    (
        "dir_info is a list",
        {"url": VALID_URL, "dir_info": []},
        "engine_direct_url_invalid_dir_info",
    ),
    (
        "dir_info is a string",
        {"url": VALID_URL, "dir_info": "x"},
        "engine_direct_url_invalid_dir_info",
    ),
    (
        "dir_info is a number",
        {"url": VALID_URL, "dir_info": 1},
        "engine_direct_url_invalid_dir_info",
    ),
    (
        "editable is a string",
        {"url": VALID_URL, "dir_info": {"editable": "true"}},
        "engine_direct_url_invalid_editable",
    ),
    (
        "editable is 1",
        {"url": VALID_URL, "dir_info": {"editable": 1}},
        "engine_direct_url_invalid_editable",
    ),
    (
        "editable is 0",
        {"url": VALID_URL, "dir_info": {"editable": 0}},
        "engine_direct_url_invalid_editable",
    ),
    (
        "editable is null",
        {"url": VALID_URL, "dir_info": {"editable": None}},
        "engine_direct_url_invalid_editable",
    ),
    (
        "editable is a list",
        {"url": VALID_URL, "dir_info": {"editable": []}},
        "engine_direct_url_invalid_editable",
    ),
    (
        "vcs_info is a list",
        {"url": VALID_URL, "vcs_info": []},
        "engine_direct_url_invalid_vcs_info",
    ),
    (
        "vcs_info missing vcs",
        {"url": VALID_URL, "vcs_info": {"commit_id": COMMIT}},
        "engine_direct_url_invalid_vcs_field",
    ),
    (
        "vcs_info missing commit_id",
        {"url": VALID_URL, "vcs_info": {"vcs": "git"}},
        "engine_direct_url_invalid_vcs_field",
    ),
    (
        "vcs_info vcs is a number",
        {"url": VALID_URL, "vcs_info": {"vcs": 1, "commit_id": COMMIT}},
        "engine_direct_url_invalid_vcs_field",
    ),
    (
        "vcs_info commit_id is null",
        {"url": VALID_URL, "vcs_info": {"vcs": "git", "commit_id": None}},
        "engine_direct_url_invalid_vcs_field",
    ),
    (
        "vcs_info requested_revision is a number",
        {
            "url": VALID_URL,
            "vcs_info": {"vcs": "git", "commit_id": COMMIT, "requested_revision": 3},
        },
        "engine_direct_url_invalid_vcs_field",
    ),
    (
        "archive_info is a string",
        {"url": VALID_URL, "archive_info": "x"},
        "engine_direct_url_invalid_archive_info",
    ),
    (
        "archive_info hashes is a list",
        {"url": VALID_URL, "archive_info": {"hashes": []}},
        "engine_direct_url_invalid_archive_field",
    ),
    (
        "archive_info hash value is a number",
        {"url": VALID_URL, "archive_info": {"hashes": {"sha256": 1}}},
        "engine_direct_url_invalid_archive_field",
    ),
    (
        "archive_info legacy hash is a list",
        {"url": VALID_URL, "archive_info": {"hash": []}},
        "engine_direct_url_invalid_archive_field",
    ),
    (
        "subdirectory is a number",
        {"url": VALID_URL, "dir_info": {}, "subdirectory": 1},
        "engine_direct_url_invalid_subdirectory",
    ),
]

# Exclusivity is structural, so it must be reported as such whatever `editable` says.
EXCLUSIVITY_WITH_EDITABLE: list[tuple[str, dict[str, Any], str]] = [
    (
        f"dir_info(editable={flag}) and {other}",
        {
            "url": VALID_URL,
            "dir_info": {"editable": flag},
            other: ({"vcs": "git", "commit_id": COMMIT} if other == "vcs_info" else {}),
        },
        "engine_direct_url_multiple_sources",
    )
    for flag in (True, False)
    for other in ("vcs_info", "archive_info")
]

ALL_INVALID_DOCUMENTS = INVALID_DOCUMENTS + EXCLUSIVITY_WITH_EDITABLE


@pytest.mark.parametrize(
    ("raw", "code"),
    [(raw, code) for _label, raw, code in INVALID_RAW_RECORDS],
    ids=[label for label, _raw, _code in INVALID_RAW_RECORDS],
)
def test_unparseable_direct_url_fails_closed(raw: str, code: str) -> None:
    with pytest.raises(EngineProvenanceError) as excinfo:
        _classify_direct_url(raw)
    assert excinfo.value.code == code


@pytest.mark.parametrize(
    ("document", "code"),
    [(document, code) for _label, document, code in ALL_INVALID_DOCUMENTS],
    ids=[label for label, _document, _code in ALL_INVALID_DOCUMENTS],
)
def test_invalid_direct_url_document_fails_closed(document: dict[str, Any], code: str) -> None:
    with pytest.raises(EngineProvenanceError) as excinfo:
        _classify_direct_url(json.dumps(document))
    assert excinfo.value.code == code


def test_no_invalid_record_is_ever_downgraded_to_an_install_mode() -> None:
    """The sweep that matters: a refusal must never become the permissive `installed` branch."""
    payloads = [raw for _label, raw, _code in INVALID_RAW_RECORDS]
    payloads += [json.dumps(document) for _label, document, _code in ALL_INVALID_DOCUMENTS]
    assert len(payloads) == len(INVALID_RAW_RECORDS) + len(ALL_INVALID_DOCUMENTS)
    for raw in payloads:
        with pytest.raises(EngineProvenanceError):
            _classify_direct_url(raw)


def test_every_error_code_is_distinct_per_condition() -> None:
    codes = {code for _label, _raw, code in INVALID_RAW_RECORDS}
    codes |= {code for _label, _document, code in ALL_INVALID_DOCUMENTS}
    assert codes == {
        "engine_direct_url_malformed",
        "engine_direct_url_not_object",
        "engine_direct_url_missing_url",
        "engine_direct_url_invalid_url_type",
        "engine_direct_url_no_source",
        "engine_direct_url_multiple_sources",
        "engine_direct_url_invalid_dir_info",
        "engine_direct_url_invalid_editable",
        "engine_direct_url_invalid_vcs_info",
        "engine_direct_url_invalid_vcs_field",
        "engine_direct_url_invalid_archive_info",
        "engine_direct_url_invalid_archive_field",
        "engine_direct_url_invalid_subdirectory",
    }


# ---- Version reconciliation (§4.4) --------------------------------------------


def test_matching_versions_resolve_to_the_module_constant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ai_workflow_engine, "__version__", "9.9.9")
    distribution = distribution_at(write_dist_info(tmp_path, version="9.9.9"))
    assert _resolve_version(distribution) == "9.9.9"


def test_version_disagreement_fails_closed_naming_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ai_workflow_engine, "__version__", "9.9.9")
    distribution = distribution_at(write_dist_info(tmp_path, version="8.8.8"))
    with pytest.raises(EngineProvenanceError) as excinfo:
        _resolve_version(distribution)
    assert excinfo.value.code == "engine_version_mismatch"
    assert "9.9.9" in str(excinfo.value)
    assert "8.8.8" in str(excinfo.value)


def test_absent_distribution_metadata_raises_no_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai_workflow_engine, "__version__", "9.9.9")
    assert _resolve_version(None) == "9.9.9"


# ---- Engine worktree discovery ------------------------------------------------


def test_worktree_root_is_found_by_walking_parents(engine_worktree: Path) -> None:
    package = engine_worktree / "src" / "ai_workflow_engine"
    assert _engine_worktree_root(package) == engine_worktree


def test_worktree_root_is_none_outside_any_repository(tmp_path: Path) -> None:
    loose = tmp_path / "loose" / "ai_workflow_engine"
    loose.mkdir(parents=True)
    assert _engine_worktree_root(loose) is None


# ---- OD-1: editable clean permitted, editable dirty refused -------------------


def test_editable_clean_engine_is_permitted_and_records_provenance(
    engine_worktree: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = json.dumps({"url": VALID_URL, "dir_info": {"editable": True}})
    install_engine(
        monkeypatch,
        worktree=engine_worktree,
        package_path=engine_worktree / "src" / "ai_workflow_engine",
        distribution=distribution_at(write_dist_info(tmp_path, direct_url=payload)),
    )
    resolved = resolve_engine_provenance()
    assert isinstance(resolved, CanonicalEngineProvenance)
    assert resolved.engine_install_mode == "editable"
    assert resolved.engine_worktree_clean is True
    assert resolved.engine_version == "9.9.9"
    assert resolved.engine_head == git(engine_worktree, "rev-parse", "HEAD")
    assert resolved.engine_package_path.endswith("src/ai_workflow_engine")


@pytest.mark.parametrize("dirt", ["untracked", "modified", "staged"])
def test_editable_dirty_engine_is_refused(
    dirt: str, engine_worktree: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = engine_worktree / "src" / "ai_workflow_engine"
    if dirt == "untracked":
        (engine_worktree / "scratch.txt").write_text("x\n", encoding="utf-8")
    else:
        (package / "__init__.py").write_text('__version__ = "9.9.9"  # edited\n', encoding="utf-8")
        if dirt == "staged":
            git(engine_worktree, "add", "-A")
    payload = json.dumps({"url": VALID_URL, "dir_info": {"editable": True}})
    install_engine(
        monkeypatch,
        worktree=engine_worktree,
        package_path=package,
        distribution=distribution_at(write_dist_info(tmp_path, direct_url=payload)),
    )
    with pytest.raises(EngineProvenanceError) as excinfo:
        resolve_engine_provenance()
    assert excinfo.value.code == "engine_editable_worktree_dirty"


def test_a_dirty_engine_is_refused_with_no_bundle_involved(
    engine_worktree: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OD-1 is unconditional: nothing about bundle selection reaches the resolver at all."""
    (engine_worktree / "scratch.txt").write_text("x\n", encoding="utf-8")
    payload = json.dumps({"url": VALID_URL, "dir_info": {"editable": True}})
    install_engine(
        monkeypatch,
        worktree=engine_worktree,
        package_path=engine_worktree / "src" / "ai_workflow_engine",
        distribution=distribution_at(write_dist_info(tmp_path, direct_url=payload)),
    )
    with pytest.raises(EngineProvenanceError):
        resolve_engine_provenance()


# ---- Non-editable modes ------------------------------------------------------


def test_installed_engine_in_a_dirty_worktree_is_permitted(
    engine_worktree: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OD-1's refusal is bounded to `editable`; a non-editable install is not refused for dirt."""
    (engine_worktree / "scratch.txt").write_text("x\n", encoding="utf-8")
    payload = json.dumps({"url": VALID_URL, "dir_info": {"editable": False}})
    install_engine(
        monkeypatch,
        worktree=engine_worktree,
        package_path=engine_worktree / "src" / "ai_workflow_engine",
        distribution=distribution_at(write_dist_info(tmp_path, direct_url=payload)),
    )
    resolved = resolve_engine_provenance()
    assert resolved.engine_install_mode == "installed"
    assert resolved.engine_worktree_clean is False


def test_source_engine_without_distribution_metadata_is_permitted(
    engine_worktree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_engine(
        monkeypatch,
        worktree=engine_worktree,
        package_path=engine_worktree / "src" / "ai_workflow_engine",
        distribution=None,
    )
    resolved = resolve_engine_provenance()
    assert resolved.engine_install_mode == "source"
    assert resolved.engine_head == git(engine_worktree, "rev-parse", "HEAD")


def test_installed_engine_outside_a_worktree_records_an_empty_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "site-packages" / "ai_workflow_engine"
    package.mkdir(parents=True)
    install_engine(
        monkeypatch,
        worktree=None,
        package_path=package,
        distribution=distribution_at(write_dist_info(tmp_path)),
    )
    resolved = resolve_engine_provenance()
    assert resolved.engine_install_mode == "installed"
    assert resolved.engine_head == ""
    assert resolved.engine_worktree_clean is True


def test_editable_engine_outside_a_worktree_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "loose" / "ai_workflow_engine"
    package.mkdir(parents=True)
    payload = json.dumps({"url": VALID_URL, "dir_info": {"editable": True}})
    install_engine(
        monkeypatch,
        worktree=None,
        package_path=package,
        distribution=distribution_at(write_dist_info(tmp_path, direct_url=payload)),
    )
    with pytest.raises(EngineProvenanceError) as excinfo:
        resolve_engine_provenance()
    assert excinfo.value.code == "engine_editable_without_worktree"


def test_unresolvable_engine_head_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "empty-repo"
    package = root / "src" / "ai_workflow_engine"
    package.mkdir(parents=True)
    git(root.parent, "init", "-b", "main", str(root))
    install_engine(monkeypatch, worktree=root, package_path=package, distribution=None)
    with pytest.raises(EngineProvenanceError) as excinfo:
        resolve_engine_provenance()
    assert excinfo.value.code == "engine_head_unresolvable"


# ---- No production bypass ----------------------------------------------------


def test_the_resolver_takes_no_injection_parameter() -> None:
    """A bypass cannot exist if there is nothing to pass: the resolver takes no arguments."""
    import inspect

    assert inspect.signature(resolve_engine_provenance).parameters == {}


def test_the_live_installation_resolves_or_refuses_deterministically() -> None:
    """Whatever this checkout's state, the real resolver answers; it never returns a guess."""
    try:
        resolved = resolve_engine_provenance()
    except EngineProvenanceError as exc:
        assert exc.code
        return
    assert resolved.engine_install_mode in {"editable", "installed", "source"}
    assert resolved.engine_version == ai_workflow_engine.__version__


def test_the_live_distribution_is_resolvable() -> None:
    """Pins the environment this repository actually governs itself with."""
    assert _load_distribution() is not None


# ---- PR-007: the OD-1 boundary — non-governed commands never reach the resolver ----
#
# §4.3's refusal is bounded to the governed prompt/review/provenance surface. This is the
# positive half of that boundary: every command outside it must run its own native
# success/refusal logic without ever invoking `resolve_engine_provenance`, whether that
# invocation would have succeeded or raised. A resolver spy that fails the test if called is
# the mechanism; the assertion is never "the command succeeds" -- each command's own natural
# outcome (often a deterministic refusal from missing setup) is compared byte-for-byte between
# a run with the ordinary stub active and a run with the failing spy active. Equality is only
# possible if the spy path was never taken.

_od1_runner = CliRunner()


def _od1_git(repository: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repository), *args], check=True, capture_output=True, text=True
    )


@pytest.fixture
def _od1_repository(tmp_path: Path) -> Path:
    repo = tmp_path / "od1-repo"
    repo.mkdir()
    _od1_git(repo, "init", "-b", "main")
    _od1_git(repo, "config", "user.email", "tests@example.invalid")
    _od1_git(repo, "config", "user.name", "Workflow Tests")
    (repo / "docs").mkdir()
    (repo / "handover").mkdir()
    task_table = "| Task | Status |\n|---|---|\n| T-1 | Planned |\n"
    doc_names = ["PROJECT_STATE.md", "TASK_QUEUE.md", "current_task.md", "remain_task.md", "ctx.md"]
    for name in doc_names:
        (repo / "docs" / name).write_text(task_table + "Version: 1.0.0\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text('version = "1.0.0"\n', encoding="utf-8")
    (repo / "handover" / "PROJECT_HANDOVER.md").write_bytes(b"handover\n")
    sha = hashlib.sha256(b"handover\n").hexdigest()[:16]
    manifest = (
        "| Relative path | Size (bytes) | Last modified | SHA-256 (prefix) |\n"
        "|---|---|---|---|\n"
        f"| handover/PROJECT_HANDOVER.md | 9 | now | `{sha}…` |\n"
    )
    (repo / "handover" / "PROJECT_CHECKSUM.md").write_text(manifest, encoding="utf-8")
    _od1_git(repo, "add", ".")
    _od1_git(repo, "commit", "-m", "initial")
    return repo


@pytest.fixture
def _od1_config(tmp_path: Path, _od1_repository: Path) -> Path:
    raw = {
        "project": {
            "id": "od1-project",
            "repository": str(_od1_repository),
            "default_branch": "main",
            "timezone": "UTC",
            "conda_environment": "ai-workflow-engine",
        },
        "governance": {
            "project_state": "docs/PROJECT_STATE.md",
            "task_queue": "docs/TASK_QUEUE.md",
            "current_task": "docs/current_task.md",
            "remaining_tasks": "docs/remain_task.md",
            "context": "docs/ctx.md",
            "pyproject": "pyproject.toml",
            "facts": [
                {
                    "name": "version",
                    "paths": ["docs/PROJECT_STATE.md", "docs/ctx.md"],
                    "pattern": r"Version:\s*([0-9.]+)",
                    "required": True,
                }
            ],
        },
        "handover": {
            "manifest": "handover/PROJECT_CHECKSUM.md",
            "files": ["handover/PROJECT_HANDOVER.md", "handover/PROJECT_CHECKSUM.md"],
        },
    }
    path = tmp_path / "od1-config.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


def _spy_that_fails_if_called() -> CanonicalEngineProvenance:
    raise AssertionError("resolve_engine_provenance must not be invoked by a non-governed command")


def _install_spy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(context_module, "resolve_engine_provenance", _spy_that_fails_if_called)
    monkeypatch.setattr(runner_module, "resolve_engine_provenance", _spy_that_fails_if_called)


def _outcome(args: list[str]) -> tuple[int, str, str]:
    result = _od1_runner.invoke(cli_app, args)
    return result.exit_code, result.stdout, (result.stderr if result.stderr_bytes else "")


def _boundary_commands(config: Path, repository: Path, tmp_path: Path) -> dict[str, list[str]]:
    """One minimal, deterministic invocation per §4.3-enumerated command.

    None of these are asserted to succeed -- several fail on missing setup (a nonexistent
    approval file, an empty migration source, a config shape the milestone runner does not
    accept). That failure is itself the command's native semantics, and it is exactly what
    equality-under-the-spy proves was never touched by provenance enforcement.
    """
    config_str = str(config)
    return {
        "version": ["version"],
        "inspect": ["inspect", "--config", config_str],
        "check-git": ["check-git", "--config", config_str],
        "check-task-state": ["check-task-state", "--config", config_str],
        "check-governance": ["check-governance", "--config", config_str],
        "check-registries": ["check-registries", "--config", config_str],
        "check-handover": ["check-handover", "--config", config_str],
        "verify": ["verify", "--config", config_str],
        "state": ["state", "show", "--config", config_str, "--task-id", "T-1"],
        "commit": [
            "commit",
            "--config",
            config_str,
            "--approval",
            str(tmp_path / "no-such-approval.yaml"),
        ],
        "push": [
            "push",
            "--config",
            config_str,
            "--approval",
            str(tmp_path / "no-such-approval.yaml"),
        ],
        "apply-patch": [
            "apply-patch",
            "--config",
            config_str,
            "--task-id",
            "T-1",
            "--stage",
            "implementation",
            "--run-id",
            "0" * 16,
        ],
        "migrate": [
            "migrate",
            "inspect",
            "--to",
            "2.0.0",
            "--source",
            str(tmp_path / "empty-migration-source"),
        ],
        "auto": ["auto", "status", "--target-repo", str(repository)],
        "milestone-runner": [
            "milestone-runner",
            "doctor",
            "--config",
            str(tmp_path / "no-such-milestone-config.yaml"),
        ],
    }


def test_the_complete_non_governed_command_surface_never_reaches_the_resolver(
    _od1_config: Path, _od1_repository: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "empty-migration-source").mkdir()
    commands = _boundary_commands(_od1_config, _od1_repository, tmp_path)

    baseline = {name: _outcome(args) for name, args in commands.items()}

    _install_spy(monkeypatch)
    spied = {name: _outcome(args) for name, args in commands.items()}

    mismatches = {
        name: (baseline[name], spied[name]) for name in commands if baseline[name] != spied[name]
    }
    assert mismatches == {}, (
        "a command's outcome changed once the resolver spy was installed, which means it "
        f"reached `resolve_engine_provenance`: {mismatches}"
    )


def test_the_boundary_list_is_the_complete_contract_enumeration() -> None:
    """Pins the enumeration itself against §4.3's exact list, so a future command addition to
    either side (the contract text or this test) cannot silently drift out of sync."""
    assert set(_boundary_commands(Path("x"), Path("y"), Path("z"))) == {
        "inspect",
        "check-git",
        "check-task-state",
        "check-governance",
        "check-registries",
        "check-handover",
        "verify",
        "state",
        "commit",
        "push",
        "apply-patch",
        "migrate",
        "auto",
        "milestone-runner",
        "version",
    }
