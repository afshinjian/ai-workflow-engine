"""Append-only, no-clobber workflow-event storage and verified replay (task T-302).

Events live under ``~/.ai-workflow-engine/workflow-runs/state/<project_id>/<task_dir>/`` as
zero-padded ``<NNNNNNNN>.json`` files whose bytes are the Milestone 2 canonical JSON of the
event plus one terminal newline. Publication reuses the Milestone 2 atomic hard-link protocol;
load re-verifies canonical bytes, the sequence contiguity, the embedded identity, and the
parent-digest chain, then replays the transition table. See ``docs/milestone-3-plan.md``.
"""

import hashlib
import json
import os
import re
import uuid
from pathlib import Path

from pydantic import ValidationError

from ai_workflow_engine.git.client import GitClient
from ai_workflow_engine.models import EngineConfig
from ai_workflow_engine.prompt.context import normalize_text
from ai_workflow_engine.prompt.models import WorkflowStage
from ai_workflow_engine.prompt.renderer import canonical_json
from ai_workflow_engine.workflow.events import (
    VERDICT_STAGES,
    StateAction,
    Verdict,
    WorkflowEvent,
    WorkflowState,
    normalize_note,
)
from ai_workflow_engine.workflow.transitions import (
    WorkflowStateError,
    check_new_stage,
    check_outcome_kind,
    expected_stage,
)

_PROJECT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_FILENAME_RE = re.compile(r"[0-9]{8}\.json")


class SequenceConflict(WorkflowStateError):
    code = "sequence_conflict"


class StateCorrupt(WorkflowStateError):
    code = "state_corrupt"


class StateIdentityMismatch(WorkflowStateError):
    code = "state_identity_mismatch"


class StateAddressingError(WorkflowStateError):
    code = "state_addressing_error"


def _artifact_root() -> Path:
    return Path("~/.ai-workflow-engine/workflow-runs/state").expanduser()


def task_dir_name(task_id: str) -> str:
    """Collision-free directory name ``<readable>-<task_hash16>`` for a normalized task ID.

    The 16-hex SHA-256 prefix is the authoritative, collision-resistant component; the readable
    prefix is only for human legibility. Two distinct task IDs that sanitize to the same readable
    string still get different hashes, and the load-time identity check catches any residual
    conflation. See ``docs/milestone-3-plan.md``.
    """
    readable = re.sub(r"[^A-Za-z0-9._-]", "_", task_id)[:40]
    task_hash16 = hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:16]
    return f"{readable}-{task_hash16}"


def state_directory(project_id: str, task_id: str) -> Path:
    if not _PROJECT_ID_RE.fullmatch(project_id):
        raise StateAddressingError(f"Invalid project_id for state addressing: {project_id!r}")
    root = _artifact_root().resolve(strict=False)
    directory = (root / project_id / task_dir_name(task_id)).resolve(strict=False)
    if not directory.is_relative_to(root):
        raise StateAddressingError("State directory escapes the state root")
    return directory


def _reject_repository_containment(directory: Path, repository: str) -> None:
    repository_root = Path(repository).resolve(strict=False)
    if directory == repository_root or directory.is_relative_to(repository_root):
        raise StateAddressingError(
            f"State directory {directory} must not be inside the target repository "
            f"{repository_root}"
        )


def _event_bytes(event: WorkflowEvent) -> bytes:
    return canonical_json(event.model_dump(mode="json")) + b"\n"


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written == 0:
            raise OSError("os.write made zero progress while writing a state temporary file")
        view = view[written:]


def _create_temp(directory: Path, data: bytes) -> Path:
    while True:
        candidate = directory / f".{uuid.uuid4().hex}.json.tmp"
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


def append(event: WorkflowEvent, *, repository: str) -> Path:
    """Publish one event at its sequence path with the atomic no-clobber protocol."""
    directory = state_directory(event.project_id, event.task_id)
    _reject_repository_containment(directory, repository)
    final = directory / f"{event.sequence:08d}.json"
    data = _event_bytes(event)
    directory.mkdir(parents=True, exist_ok=True)

    temp: Path | None = None
    try:
        temp = _create_temp(directory, data)
        try:
            os.link(temp, final)
        except FileExistsError:
            existing = final.read_bytes()
            if existing != data:
                raise SequenceConflict(
                    f"Sequence {event.sequence} already exists at {final} with different bytes"
                ) from None
        if final.read_bytes() != data:
            raise StateCorrupt(f"State final does not match after publication: {final}")
        _fsync_directory(directory)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
    return final


def _parse_json_no_duplicate_keys(text: str) -> object:
    def hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise StateCorrupt(f"Duplicate JSON object key in stored event: {key!r}")
            result[key] = value
        return result

    return json.loads(text, object_pairs_hook=hook)


def load_history(project_id: str, task_id: str) -> list[WorkflowEvent]:
    """Load, fully verify, and replay a task's event history (empty if none)."""
    normalized_task = normalize_text(task_id)
    directory = state_directory(project_id, normalized_task)
    if not directory.exists():
        return []

    names = sorted(entry.name for entry in directory.iterdir() if entry.is_file())
    # Ignore this store's own crash-left unique temp files; anything else is corruption.
    names = [name for name in names if not name.endswith(".json.tmp")]
    if not names:
        return []
    for name in names:
        if not _FILENAME_RE.fullmatch(name):
            raise StateCorrupt(f"Foreign file in state directory: {name!r}")
    expected_names = [f"{index:08d}.json" for index in range(1, len(names) + 1)]
    if names != expected_names:
        raise StateCorrupt(f"State sequence is not the contiguous set 1..{len(names)}: {names!r}")

    history: list[WorkflowEvent] = []
    previous_bytes: bytes | None = None
    for index, name in enumerate(names, start=1):
        raw = (directory / name).read_bytes()
        if not raw.endswith(b"\n") or raw.count(b"\n") != 1:
            raise StateCorrupt(f"Stored event {name} must have exactly one terminal newline")
        try:
            body = raw[:-1].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise StateCorrupt(f"Stored event {name} is not valid UTF-8") from exc
        parsed = _parse_json_no_duplicate_keys(body)
        try:
            event = WorkflowEvent.model_validate(parsed)
        except ValidationError as exc:
            raise StateCorrupt(f"Stored event {name} is not a valid WorkflowEvent: {exc}") from exc
        if _event_bytes(event) != raw:
            raise StateCorrupt(f"Stored event {name} is not in canonical form")
        if event.sequence != index:
            raise StateCorrupt(
                f"Stored event {name} has sequence {event.sequence}, expected {index}"
            )
        if event.project_id != project_id or event.task_id != normalized_task:
            raise StateIdentityMismatch(
                f"Stored event {name} belongs to {event.project_id}/{event.task_id!r}, not "
                f"{project_id}/{normalized_task!r}"
            )
        expected_parent = (
            None if previous_bytes is None else hashlib.sha256(previous_bytes).hexdigest()
        )
        if event.parent_digest != expected_parent:
            raise StateCorrupt(f"Stored event {name} breaks the parent-digest chain")
        if event.stage != expected_stage(history):
            raise StateCorrupt(
                f"Stored event {name} stage {event.stage!r} violates the transition table"
            )
        history.append(event)
        previous_bytes = raw
    return history


def derive_state(project_id: str, task_id: str) -> WorkflowState:
    history = load_history(project_id, task_id)
    next_stage = expected_stage(history)
    terminal = bool(history) and next_stage is None
    return WorkflowState(
        project_id=project_id,
        task_id=normalize_text(task_id),
        events=history,
        next_stage=next_stage,
        terminal=terminal,
    )


def record_outcome(
    config: EngineConfig,
    task_id: str,
    *,
    stage: WorkflowStage,
    verdict: Verdict | None,
    prompt_id: str | None = None,
    agent_run_id: str | None = None,
    note: str = "",
) -> WorkflowEvent:
    """Validate against the transition table and verdict rules, then append one event."""
    normalized_task = normalize_text(task_id)
    project_id = config.project.id
    history = load_history(project_id, normalized_task)

    check_outcome_kind(stage, has_verdict=verdict is not None)
    check_new_stage(history, stage)

    sequence = len(history) + 1
    parent_digest = None if sequence == 1 else hashlib.sha256(_event_bytes(history[-1])).hexdigest()
    head = GitClient(config.project.repository).head()
    action: StateAction = "verdict" if stage in VERDICT_STAGES else "completed"
    event = WorkflowEvent(
        schema_version="1.0",
        project_id=project_id,
        task_id=normalized_task,
        sequence=sequence,
        parent_digest=parent_digest,
        stage=stage,
        action=action,
        verdict=verdict,
        prompt_id=prompt_id,
        agent_run_id=agent_run_id,
        head=head,
        note=normalize_note(note),
    )
    append(event, repository=str(config.project.repository))
    return event
