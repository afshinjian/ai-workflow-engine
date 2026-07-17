"""Artifact addressing, race-safe no-clobber publication, and verified prompt load."""

import json
import os
import re
import uuid
from pathlib import Path

from pydantic import ValidationError

from ai_workflow_engine.prompt.models import (
    WORKFLOW_STAGES,
    PromptMetadata,
    RenderedPrompt,
    StoredPromptPaths,
    WorkflowStage,
)
from ai_workflow_engine.prompt.renderer import render_prompt

_PROJECT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_PROMPT_ID_RE = re.compile(r"[0-9a-f]{16}")


class PromptStorageError(ValueError):
    """A publication or load-time addressing, collision, or tamper error."""


def _artifact_root() -> Path:
    return Path("~/.ai-workflow-engine/workflow-runs/prompts").expanduser()


def _validate_project_id(project_id: str) -> str:
    if not _PROJECT_ID_RE.fullmatch(project_id):
        raise PromptStorageError(f"Invalid project_id for storage addressing: {project_id!r}")
    return project_id


def _validate_stage(stage: str) -> WorkflowStage:
    for candidate in WORKFLOW_STAGES:
        if stage == candidate:
            return candidate
    raise PromptStorageError(f"Invalid stage for storage addressing: {stage!r}")


def _validate_prompt_id(prompt_id: str) -> str:
    if not _PROMPT_ID_RE.fullmatch(prompt_id):
        raise PromptStorageError(f"Invalid prompt_id for storage addressing: {prompt_id!r}")
    return prompt_id


def _artifact_paths(project_id: str, stage: str, prompt_id: str) -> tuple[Path, Path]:
    _validate_project_id(project_id)
    _validate_stage(stage)
    _validate_prompt_id(prompt_id)
    root = _artifact_root().resolve(strict=False)
    directory = (root / project_id / stage).resolve(strict=False)
    if not directory.is_relative_to(root):
        raise PromptStorageError("Artifact directory escapes the artifact root")
    markdown = (directory / f"{prompt_id}.md").resolve(strict=False)
    metadata = (directory / f"{prompt_id}.json").resolve(strict=False)
    if not markdown.is_relative_to(root) or not metadata.is_relative_to(root):
        raise PromptStorageError("Artifact path escapes the artifact root")
    return markdown, metadata


def _reject_repository_containment(directory: Path, repository: str) -> None:
    repository_root = Path(repository).resolve(strict=False)
    if directory == repository_root or directory.is_relative_to(repository_root):
        raise PromptStorageError(
            f"Artifact directory {directory} must not be inside the target repository "
            f"{repository_root}"
        )


def _verify_rendered(rendered: RenderedPrompt) -> RenderedPrompt:
    recomputed = render_prompt(rendered.context)
    if recomputed != rendered:
        raise PromptStorageError("RenderedPrompt does not match its recomputed values")
    return recomputed


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written == 0:
            # A zero-byte write makes no progress; looping again would hang forever.
            raise OSError("os.write made zero progress while writing a prompt temporary file")
        view = view[written:]


def _create_temp(directory: Path, suffix: str, data: bytes) -> Path:
    while True:
        candidate = directory / f".{uuid.uuid4().hex}{suffix}"
        try:
            fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        break
    try:
        try:
            _write_all(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
    except BaseException:
        # This invocation owns `candidate` alone; a write or fsync failure must not
        # leak it. A creation failure above never reaches here (nothing was created).
        candidate.unlink(missing_ok=True)
        raise
    return candidate


def _fsync_directory(directory: Path) -> None:
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def save(rendered: RenderedPrompt) -> StoredPromptPaths:
    """Race-safe, atomic, no-clobber publication of one rendered prompt."""
    rendered = _verify_rendered(rendered)
    context = rendered.context

    markdown_final, metadata_final = _artifact_paths(
        context.config.project.id, context.stage, rendered.prompt_id
    )
    directory = markdown_final.parent
    _reject_repository_containment(directory, context.config.project.repository)

    markdown_bytes = rendered.markdown.encode("utf-8", errors="strict")
    metadata_bytes = rendered.metadata_bytes

    directory.mkdir(parents=True, exist_ok=True)

    markdown_temp: Path | None = None
    metadata_temp: Path | None = None
    try:
        markdown_temp = _create_temp(directory, ".md.tmp", markdown_bytes)
        metadata_temp = _create_temp(directory, ".json.tmp", metadata_bytes)

        if markdown_final.exists() and not metadata_final.exists():
            existing_markdown = markdown_final.read_bytes()
            if existing_markdown != markdown_bytes:
                raise PromptStorageError(
                    f"Incomplete artifact collision at {markdown_final}: existing Markdown-only "
                    "partial does not match this save"
                )

        try:
            os.link(metadata_temp, metadata_final)
        except FileExistsError:
            existing_metadata = metadata_final.read_bytes()
            if existing_metadata != metadata_bytes:
                raise PromptStorageError(
                    f"Metadata collision at {metadata_final}: existing metadata differs"
                ) from None

        try:
            os.link(markdown_temp, markdown_final)
        except FileExistsError:
            existing_markdown = markdown_final.read_bytes()
            if existing_markdown != markdown_bytes:
                raise PromptStorageError(
                    f"Markdown collision at {markdown_final}: existing Markdown differs"
                ) from None

        if metadata_final.read_bytes() != metadata_bytes:
            raise PromptStorageError("Metadata final does not match after publication")
        if markdown_final.read_bytes() != markdown_bytes:
            raise PromptStorageError("Markdown final does not match after publication")
        _fsync_directory(directory)
    finally:
        # Cleanup ownership is scoped to exactly the temp files this invocation created
        # (each is None until its own successful _create_temp call, which never leaks
        # its own candidate on failure); no other invocation's temps are ever touched.
        if markdown_temp is not None:
            markdown_temp.unlink(missing_ok=True)
        if metadata_temp is not None:
            metadata_temp.unlink(missing_ok=True)

    return StoredPromptPaths(markdown=markdown_final, metadata=metadata_final)


def _parse_json_no_duplicate_keys(text: str) -> object:
    def hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise PromptStorageError(f"Duplicate JSON object key in metadata: {key!r}")
            result[key] = value
        return result

    return json.loads(text, object_pairs_hook=hook)


def load(project_id: str, stage: WorkflowStage, prompt_id: str) -> RenderedPrompt:
    """Verified load: reconstructs a RenderedPrompt solely from the embedded artifact pair."""
    markdown_final, metadata_final = _artifact_paths(project_id, stage, prompt_id)
    if not markdown_final.exists() or not metadata_final.exists():
        raise PromptStorageError(
            f"Incomplete prompt artifact for {project_id}/{stage}/{prompt_id}: both files "
            "must exist"
        )

    metadata_bytes = metadata_final.read_bytes()
    try:
        text = metadata_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise PromptStorageError(f"Metadata is not valid UTF-8: {exc}") from exc
    if not text.endswith("\n") or text.endswith("\n\n"):
        raise PromptStorageError("Metadata must end with exactly one terminal newline")

    try:
        raw = _parse_json_no_duplicate_keys(text[:-1])
    except json.JSONDecodeError as exc:
        raise PromptStorageError(f"Metadata is not valid JSON: {exc}") from exc

    try:
        metadata = PromptMetadata.model_validate(raw)
    except ValidationError as exc:
        raise PromptStorageError(f"Metadata does not match PromptMetadata: {exc}") from exc

    if (
        metadata.project_id != project_id
        or metadata.stage != stage
        or metadata.prompt_id != prompt_id
    ):
        raise PromptStorageError(
            "Metadata addressing fields do not match the requested load address"
        )

    rendered = render_prompt(metadata.payload)

    markdown_bytes = markdown_final.read_bytes()
    if markdown_bytes != rendered.markdown.encode("utf-8", errors="strict"):
        raise PromptStorageError("Markdown bytes do not match the recomputed rendering")

    if rendered.metadata != metadata:
        raise PromptStorageError("Recomputed metadata does not match stored metadata")

    if rendered.metadata_bytes != metadata_bytes:
        raise PromptStorageError(
            "Recomputed canonical metadata bytes do not match stored metadata bytes"
        )

    return rendered
