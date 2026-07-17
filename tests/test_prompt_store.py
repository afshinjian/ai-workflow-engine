"""Artifact addressing, no-clobber publication, and verified load tests."""

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_workflow_engine.models import EngineConfig
from ai_workflow_engine.prompt.context import build_prompt_context
from ai_workflow_engine.prompt.models import PromptSuccess, StoredPromptPaths
from ai_workflow_engine.prompt.renderer import render_prompt
from ai_workflow_engine.prompt.store import PromptStorageError, load, save


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def _rendered(engine_config: EngineConfig, stage: str = "plan-review", task_id: str = "T-1"):
    context = build_prompt_context(engine_config, stage=stage, task_id=task_id)
    return render_prompt(context)


def _temp_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return [entry for entry in directory.iterdir() if entry.name.startswith(".")]


def _prompt_directory(rendered) -> Path:
    return (
        Path("~/.ai-workflow-engine/workflow-runs/prompts").expanduser()
        / rendered.context.config.project.id
        / rendered.context.stage
    )


def _artifact_paths_for(rendered) -> tuple[Path, Path]:
    directory = _prompt_directory(rendered)
    return directory / f"{rendered.prompt_id}.md", directory / f"{rendered.prompt_id}.json"


class _FaultyOS:
    """Injects synthetic os.open/os.write/os.fsync failures for a given temp-file suffix.

    fd -> suffix tracking means only file descriptors this instance itself opened for a
    `.md.tmp`/`.json.tmp` path are ever affected; every other os call (including pytest's
    own stdio) always falls through to the real implementation unchanged.
    """

    def __init__(self) -> None:
        self._real_open = os.open
        self._real_write = os.write
        self._real_fsync = os.fsync
        self._fd_suffix: dict[int, str] = {}
        self.fail_open_suffix: str | None = None
        self.fail_write_suffix: str | None = None
        self.zero_progress_suffix: str | None = None
        self.fail_fsync_suffix: str | None = None

    def open(self, path: object, flags: int, mode: int = 0o777) -> int:
        path_str = str(path)
        if self.fail_open_suffix and path_str.endswith(self.fail_open_suffix):
            raise OSError(f"synthetic open failure: {path_str}")
        fd = self._real_open(path, flags, mode)
        for suffix in (".md.tmp", ".json.tmp"):
            if path_str.endswith(suffix):
                self._fd_suffix[fd] = suffix
        return fd

    def write(self, fd: int, data: bytes) -> int:
        suffix = self._fd_suffix.get(fd)
        if suffix is not None and suffix == self.fail_write_suffix:
            raise OSError(f"synthetic write failure for suffix {suffix}")
        if suffix is not None and suffix == self.zero_progress_suffix:
            return 0
        return self._real_write(fd, data)

    def fsync(self, fd: int) -> None:
        suffix = self._fd_suffix.get(fd)
        if suffix is not None and suffix == self.fail_fsync_suffix:
            raise OSError(f"synthetic fsync failure for suffix {suffix}")
        self._real_fsync(fd)


@pytest.fixture
def faulty_os(monkeypatch: pytest.MonkeyPatch) -> _FaultyOS:
    faulty = _FaultyOS()
    monkeypatch.setattr(os, "open", faulty.open)
    monkeypatch.setattr(os, "write", faulty.write)
    monkeypatch.setattr(os, "fsync", faulty.fsync)
    return faulty


def test_save_and_load_round_trip(engine_config: EngineConfig) -> None:
    rendered = _rendered(engine_config)
    paths = save(rendered)
    assert paths.markdown.exists()
    assert paths.metadata.exists()
    loaded = load(rendered.context.config.project.id, rendered.context.stage, rendered.prompt_id)
    assert loaded == rendered


def test_save_location_is_under_expanded_home(
    engine_config: EngineConfig, _isolated_home: Path
) -> None:
    rendered = _rendered(engine_config)
    paths = save(rendered)
    expected_dir = (
        _isolated_home
        / ".ai-workflow-engine"
        / "workflow-runs"
        / "prompts"
        / rendered.context.config.project.id
        / rendered.context.stage
    )
    assert paths.markdown == (expected_dir / f"{rendered.prompt_id}.md").resolve()
    assert paths.metadata == (expected_dir / f"{rendered.prompt_id}.json").resolve()


def test_save_is_independent_of_current_working_directory(
    engine_config: EngineConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    rendered = _rendered(engine_config)
    paths = save(rendered)
    assert paths.markdown.exists()


def test_save_rejects_repository_containment(
    engine_config: EngineConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = engine_config.project.repository / "fake_home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    rendered = _rendered(engine_config)
    with pytest.raises(PromptStorageError, match="must not be inside the target repository"):
        save(rendered)


def test_save_leaves_no_temp_files_on_success(engine_config: EngineConfig) -> None:
    rendered = _rendered(engine_config)
    paths = save(rendered)
    assert _temp_files(paths.markdown.parent) == []


def test_temp_files_created_with_owner_only_mode(
    engine_config: EngineConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed_modes: list[int] = []
    real_open = os.open

    def spy_open(path: object, flags: int, mode: int = 0o777) -> int:
        if str(path).endswith(".tmp"):
            assert flags == (os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            observed_modes.append(mode)
        return real_open(path, flags, mode)

    monkeypatch.setattr(os, "open", spy_open)
    rendered = _rendered(engine_config)
    save(rendered)
    assert observed_modes == [0o600, 0o600]


def test_save_is_idempotent_for_identical_concurrent_saves(engine_config: EngineConfig) -> None:
    rendered = _rendered(engine_config)
    first = save(rendered)
    second = save(rendered)
    assert first == second
    assert first.markdown.read_bytes() == rendered.markdown.encode("utf-8")


def test_save_detects_differing_metadata_collision(engine_config: EngineConfig) -> None:
    rendered = _rendered(engine_config)
    paths = save(rendered)
    original_metadata = paths.metadata.read_bytes()
    tampered = original_metadata[:-2] + b" \n"  # still ends in one newline but differs
    paths.metadata.write_bytes(tampered)
    with pytest.raises(PromptStorageError, match="Metadata collision"):
        save(rendered)
    # Final files are never overwritten by a losing writer.
    assert paths.metadata.read_bytes() == tampered


def test_save_detects_differing_markdown_collision(engine_config: EngineConfig) -> None:
    rendered = _rendered(engine_config)
    paths = save(rendered)
    original_markdown = paths.markdown.read_bytes()
    # Simulate a same-ID writer whose Markdown final differs from ours, by hand-editing after
    # the fact (only reachable in practice via a hostile actor; exercises the comparison path).
    paths.markdown.write_bytes(original_markdown + b" ")
    with pytest.raises(PromptStorageError, match="Markdown collision"):
        save(rendered)
    assert paths.markdown.read_bytes() == original_markdown + b" "


def test_save_repairs_matching_legacy_markdown_only_partial(engine_config: EngineConfig) -> None:
    rendered = _rendered(engine_config)
    directory = (
        Path("~/.ai-workflow-engine/workflow-runs/prompts").expanduser()
        / rendered.context.config.project.id
        / rendered.context.stage
    )
    directory.mkdir(parents=True)
    markdown_final = directory / f"{rendered.prompt_id}.md"
    markdown_final.write_bytes(rendered.markdown.encode("utf-8"))
    paths = save(rendered)
    assert paths.metadata.exists()
    assert paths.markdown.read_bytes() == rendered.markdown.encode("utf-8")


def test_save_preserves_differing_legacy_markdown_only_partial(
    engine_config: EngineConfig,
) -> None:
    rendered = _rendered(engine_config)
    directory = (
        Path("~/.ai-workflow-engine/workflow-runs/prompts").expanduser()
        / rendered.context.config.project.id
        / rendered.context.stage
    )
    directory.mkdir(parents=True)
    markdown_final = directory / f"{rendered.prompt_id}.md"
    markdown_final.write_bytes(b"not the right markdown\n")
    with pytest.raises(PromptStorageError, match="Incomplete artifact collision"):
        save(rendered)
    assert markdown_final.read_bytes() == b"not the right markdown\n"
    assert not (directory / f"{rendered.prompt_id}.json").exists()


def test_load_requires_both_members(engine_config: EngineConfig) -> None:
    rendered = _rendered(engine_config)
    with pytest.raises(PromptStorageError, match="Incomplete prompt artifact"):
        load(rendered.context.config.project.id, rendered.context.stage, rendered.prompt_id)


@pytest.mark.parametrize("present_suffix", [".md", ".json"])
def test_load_rejects_a_mixed_pair_with_exactly_one_member_present(
    engine_config: EngineConfig, present_suffix: str
) -> None:
    rendered = _rendered(engine_config)
    paths = save(rendered)
    if present_suffix == ".md":
        paths.metadata.unlink()
    else:
        paths.markdown.unlink()
    with pytest.raises(PromptStorageError, match="Incomplete prompt artifact"):
        load(rendered.context.config.project.id, rendered.context.stage, rendered.prompt_id)


# --- Real concurrency (actual OS-thread races, not sequential simulation) --------


def test_real_concurrent_identical_saves_are_idempotent(engine_config: EngineConfig) -> None:
    rendered = _rendered(engine_config)
    worker_count = 8
    barrier = threading.Barrier(worker_count)

    def worker() -> StoredPromptPaths:
        barrier.wait()  # maximize actual overlap of the racing save() calls
        return save(rendered)

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        results = list(pool.map(lambda _: worker(), range(worker_count)))

    assert all(result == results[0] for result in results)
    assert results[0].markdown.read_bytes() == rendered.markdown.encode("utf-8")
    assert results[0].metadata.read_bytes() == rendered.metadata_bytes
    assert _temp_files(results[0].markdown.parent) == []


def test_real_concurrent_forced_same_address_writers_exactly_one_wins(
    engine_config: EngineConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Two independently valid, self-consistent renders (different task_id, therefore
    # different prompt_id/markdown/metadata) are forced to the same storage address by
    # patching the address resolver alone; each render remains internally consistent, so
    # `_verify_rendered` inside `save()` still accepts both individually.
    import ai_workflow_engine.prompt.store as store_module

    rendered_a = _rendered(engine_config, task_id="T-1")
    rendered_b = _rendered(engine_config, task_id="T-2")
    forced_markdown, forced_metadata = _artifact_paths_for(rendered_a)

    def fake_artifact_paths(project_id: str, stage: str, prompt_id: str) -> tuple[Path, Path]:
        return forced_markdown, forced_metadata

    monkeypatch.setattr(store_module, "_artifact_paths", fake_artifact_paths)

    barrier = threading.Barrier(2)
    outcomes: dict[str, object] = {}

    def worker(name: str, rendered: object) -> None:
        barrier.wait()
        try:
            outcomes[name] = save(rendered)
        except PromptStorageError as exc:
            outcomes[name] = exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        pool.submit(worker, "a", rendered_a)
        pool.submit(worker, "b", rendered_b)

    winners = [name for name, outcome in outcomes.items() if isinstance(outcome, StoredPromptPaths)]
    losers = [name for name, outcome in outcomes.items() if isinstance(outcome, PromptStorageError)]
    assert len(winners) == 1
    assert len(losers) == 1
    assert "collision" in str(outcomes[losers[0]]).lower()

    winning_rendered = rendered_a if winners[0] == "a" else rendered_b
    # No mixed pair: whichever writer's metadata was published, that writer's Markdown
    # (and only that writer's) is the one present at the shared final path.
    assert forced_metadata.read_bytes() == winning_rendered.metadata_bytes
    assert forced_markdown.read_bytes() == winning_rendered.markdown.encode("utf-8")
    assert _temp_files(forced_markdown.parent) == []


def test_differing_metadata_with_forced_identical_markdown_cannot_reach_storage(
    engine_config: EngineConfig,
) -> None:
    # The plan's race-safety argument for "differing metadata, identical Markdown" is that
    # it is unreachable: every payload field (including config fields absent from the
    # rendered text) feeds the embedded PROMPT_ID_SCALAR via the payload hash, so two
    # self-consistent renders can never share Markdown bytes while differing elsewhere.
    # `_verify_rendered` enforces this at the `save()` boundary: a hand-crafted RenderedPrompt
    # asserting a forced/mismatched identity is rejected before any file is touched, which is
    # the only way such a pair could otherwise reach the publication race.
    rendered = _rendered(engine_config)
    tampered = rendered.model_copy(update={"prompt_id": "f" * 16})
    with pytest.raises(PromptStorageError, match="does not match its recomputed values"):
        save(tampered)
    assert _temp_files(_prompt_directory(rendered)) == []


@pytest.mark.parametrize(
    ("project_id", "stage", "prompt_id"),
    [
        ("../escape", "plan-review", "0" * 16),
        ("", "plan-review", "0" * 16),
        ("test-project", "not-a-stage", "0" * 16),
        ("test-project", "plan-review", "not-hex"),
        ("test-project", "plan-review", "0" * 15),
        ("a/b", "plan-review", "0" * 16),
    ],
)
def test_load_rejects_invalid_address_components(
    project_id: str, stage: str, prompt_id: str
) -> None:
    with pytest.raises(PromptStorageError):
        load(project_id, stage, prompt_id)  # type: ignore[arg-type]


def test_load_rejects_duplicate_json_keys(engine_config: EngineConfig) -> None:
    rendered = _rendered(engine_config)
    paths = save(rendered)
    text = paths.metadata.read_text(encoding="utf-8")
    assert text.endswith("\n") and text.rstrip("\n").endswith("}")
    body_without_closing_brace = text.rstrip("\n")[:-1]
    duplicated = body_without_closing_brace + ',"schema_version":"1.0"}\n'
    paths.metadata.write_text(duplicated, encoding="utf-8")
    with pytest.raises(PromptStorageError, match="Duplicate JSON object key"):
        load(rendered.context.config.project.id, rendered.context.stage, rendered.prompt_id)


def test_load_rejects_noncanonical_json_formatting(engine_config: EngineConfig) -> None:
    rendered = _rendered(engine_config)
    paths = save(rendered)
    body = json.loads(paths.metadata.read_text(encoding="utf-8"))
    pretty = json.dumps(body, indent=2) + "\n"
    paths.metadata.write_text(pretty, encoding="utf-8")
    with pytest.raises(PromptStorageError):
        load(rendered.context.config.project.id, rendered.context.stage, rendered.prompt_id)


def test_load_rejects_extra_field_in_metadata(engine_config: EngineConfig) -> None:
    rendered = _rendered(engine_config)
    paths = save(rendered)
    body = json.loads(paths.metadata.read_text(encoding="utf-8"))
    body["unexpected_field"] = "x"
    paths.metadata.write_text(json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n")
    with pytest.raises(PromptStorageError):
        load(rendered.context.config.project.id, rendered.context.stage, rendered.prompt_id)


def test_load_rejects_missing_terminal_newline(engine_config: EngineConfig) -> None:
    rendered = _rendered(engine_config)
    paths = save(rendered)
    data = paths.metadata.read_bytes()
    paths.metadata.write_bytes(data[:-1])
    with pytest.raises(PromptStorageError, match="terminal newline"):
        load(rendered.context.config.project.id, rendered.context.stage, rendered.prompt_id)


def test_load_rejects_markdown_byte_tamper(engine_config: EngineConfig) -> None:
    rendered = _rendered(engine_config)
    paths = save(rendered)
    paths.markdown.write_bytes(rendered.markdown.encode("utf-8") + b" ")
    with pytest.raises(PromptStorageError, match="Markdown bytes"):
        load(rendered.context.config.project.id, rendered.context.stage, rendered.prompt_id)


def test_write_all_rejects_a_zero_progress_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_workflow_engine.prompt.store import _write_all

    probe = tmp_path / "probe"
    fd = os.open(probe, os.O_WRONLY | os.O_CREAT, 0o600)
    real_write = os.write

    def fake_write(target_fd: int, data: object) -> int:
        if target_fd == fd:
            return 0
        return real_write(target_fd, data)

    monkeypatch.setattr(os, "write", fake_write)
    try:
        with pytest.raises(OSError, match="zero progress"):
            _write_all(fd, b"data")
    finally:
        os.close(fd)


def test_create_temp_cleans_up_on_write_failure(tmp_path: Path, faulty_os: _FaultyOS) -> None:
    from ai_workflow_engine.prompt.store import _create_temp

    faulty_os.fail_write_suffix = ".md.tmp"
    with pytest.raises(OSError, match="synthetic write failure"):
        _create_temp(tmp_path, ".md.tmp", b"data")
    assert _temp_files(tmp_path) == []


def test_create_temp_cleans_up_on_fsync_failure(tmp_path: Path, faulty_os: _FaultyOS) -> None:
    from ai_workflow_engine.prompt.store import _create_temp

    faulty_os.fail_fsync_suffix = ".md.tmp"
    with pytest.raises(OSError, match="synthetic fsync failure"):
        _create_temp(tmp_path, ".md.tmp", b"data")
    assert _temp_files(tmp_path) == []


def test_create_temp_cleans_up_on_zero_progress_write(tmp_path: Path, faulty_os: _FaultyOS) -> None:
    from ai_workflow_engine.prompt.store import _create_temp

    faulty_os.zero_progress_suffix = ".md.tmp"
    with pytest.raises(OSError, match="zero progress"):
        _create_temp(tmp_path, ".md.tmp", b"data")
    assert _temp_files(tmp_path) == []


def test_create_temp_leaves_no_file_when_creation_collides_then_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A FileExistsError during creation itself (uuid collision) is a retry, not a failure:
    # nothing was created by the failed attempt, so there is nothing to clean up for it.
    from ai_workflow_engine.prompt.store import _create_temp

    real_open = os.open
    calls = {"count": 0}

    def flaky_open(path: object, flags: int, mode: int = 0o777) -> int:
        calls["count"] += 1
        if calls["count"] == 1:
            raise FileExistsError(str(path))
        return real_open(path, flags, mode)

    monkeypatch.setattr(os, "open", flaky_open)
    result = _create_temp(tmp_path, ".md.tmp", b"data")
    assert result.exists()
    assert _temp_files(tmp_path) == [result]


def test_save_raises_and_leaves_nothing_when_first_temp_creation_fails(
    engine_config: EngineConfig, faulty_os: _FaultyOS
) -> None:
    rendered = _rendered(engine_config)
    faulty_os.fail_open_suffix = ".md.tmp"
    with pytest.raises(OSError, match="synthetic open failure"):
        save(rendered)
    assert _temp_files(_prompt_directory(rendered)) == []


def test_save_raises_and_leaves_nothing_when_first_temp_write_fails(
    engine_config: EngineConfig, faulty_os: _FaultyOS
) -> None:
    rendered = _rendered(engine_config)
    faulty_os.fail_write_suffix = ".md.tmp"
    with pytest.raises(OSError, match="synthetic write failure"):
        save(rendered)
    assert _temp_files(_prompt_directory(rendered)) == []


def test_save_raises_and_leaves_nothing_when_first_temp_fsync_fails(
    engine_config: EngineConfig, faulty_os: _FaultyOS
) -> None:
    rendered = _rendered(engine_config)
    faulty_os.fail_fsync_suffix = ".md.tmp"
    with pytest.raises(OSError, match="synthetic fsync failure"):
        save(rendered)
    assert _temp_files(_prompt_directory(rendered)) == []


def test_save_cleans_up_first_temp_when_second_temp_creation_fails(
    engine_config: EngineConfig, faulty_os: _FaultyOS
) -> None:
    rendered = _rendered(engine_config)
    faulty_os.fail_open_suffix = ".json.tmp"
    with pytest.raises(OSError, match="synthetic open failure"):
        save(rendered)
    assert _temp_files(_prompt_directory(rendered)) == []


def test_save_cleans_up_first_temp_when_second_temp_write_fails(
    engine_config: EngineConfig, faulty_os: _FaultyOS
) -> None:
    rendered = _rendered(engine_config)
    faulty_os.fail_write_suffix = ".json.tmp"
    with pytest.raises(OSError, match="synthetic write failure"):
        save(rendered)
    assert _temp_files(_prompt_directory(rendered)) == []


def test_save_cleans_up_first_temp_when_second_temp_fsync_fails(
    engine_config: EngineConfig, faulty_os: _FaultyOS
) -> None:
    rendered = _rendered(engine_config)
    faulty_os.fail_fsync_suffix = ".json.tmp"
    with pytest.raises(OSError, match="synthetic fsync failure"):
        save(rendered)
    assert _temp_files(_prompt_directory(rendered)) == []


def test_save_cleans_up_first_temp_when_second_temp_zero_progress_write(
    engine_config: EngineConfig, faulty_os: _FaultyOS
) -> None:
    rendered = _rendered(engine_config)
    faulty_os.zero_progress_suffix = ".json.tmp"
    with pytest.raises(OSError, match="zero progress"):
        save(rendered)
    assert _temp_files(_prompt_directory(rendered)) == []


def test_save_handled_failure_removes_only_this_invocations_temp_files(
    engine_config: EngineConfig,
) -> None:
    rendered = _rendered(engine_config)
    directory = _prompt_directory(rendered)
    directory.mkdir(parents=True)
    leftover = directory / ".crash-left-over.md.tmp"
    leftover.write_bytes(b"stale")
    # A pre-existing, differing metadata final forces a handled "Metadata collision"
    # failure after this invocation's own two temp files have already been created.
    metadata_final = directory / f"{rendered.prompt_id}.json"
    metadata_final.write_bytes(b"not the right metadata\n")
    with pytest.raises(PromptStorageError, match="Metadata collision"):
        save(rendered)
    assert _temp_files(directory) == [leftover]
    assert leftover.read_bytes() == b"stale"


def test_stored_prompt_paths_rejects_wrong_type() -> None:
    with pytest.raises(ValidationError):
        StoredPromptPaths(markdown="not-a-path-instance", metadata=Path("x.json"))
    with pytest.raises(ValidationError):
        StoredPromptPaths(markdown=Path("x.md"), metadata=1)


def test_prompt_success_rejects_wrong_type(engine_config: EngineConfig) -> None:
    rendered = _rendered(engine_config)
    success = PromptSuccess(
        schema_version="1.0",
        stored=False,
        prompt_artifact=None,
        metadata_artifact=None,
        prompt=rendered.markdown,
        metadata=rendered.metadata,
    )
    dumped = success.model_dump()
    with pytest.raises(ValidationError):
        PromptSuccess(**{**dumped, "stored": 1})
    with pytest.raises(ValidationError):
        PromptSuccess(**{**dumped, "prompt": 1})
    with pytest.raises(ValidationError):
        PromptSuccess(**{**dumped, "metadata": "not-a-metadata-payload"})


def test_load_rejects_addressing_field_tamper(engine_config: EngineConfig) -> None:
    other = _rendered(engine_config, task_id="T-2")
    rendered = _rendered(engine_config, task_id="T-1")
    save(rendered)
    save(other)
    # Overwrite rendered's metadata with other's metadata bytes at rendered's own address.
    directory = (
        Path("~/.ai-workflow-engine/workflow-runs/prompts").expanduser()
        / rendered.context.config.project.id
        / rendered.context.stage
    )
    metadata_final = directory / f"{rendered.prompt_id}.json"
    other_metadata_final = directory / f"{other.prompt_id}.json"
    metadata_final.write_bytes(other_metadata_final.read_bytes())
    with pytest.raises(PromptStorageError):
        load(rendered.context.config.project.id, rendered.context.stage, rendered.prompt_id)
