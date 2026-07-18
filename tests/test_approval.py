from pathlib import Path

import pytest
import yaml

from ai_workflow_engine.git.approval import (
    ApprovalError,
    CommitApproval,
    PushApproval,
    approval_digest,
    load_commit_approval,
    load_push_approval,
)

_HEAD = "a" * 40


def _commit_dict(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "kind": "commit",
        "task_id": "T-1",
        "branch": "main",
        "head": _HEAD,
        "allowed_paths": ["src/a.py"],
        "message": "do the thing",
        "approved_by": "human@example.invalid",
    }
    base.update(overrides)
    return base


def _push_dict(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "kind": "push",
        "task_id": "T-1",
        "branch": "main",
        "head": _HEAD,
        "upstream": "origin/main",
        "approved_by": "human@example.invalid",
    }
    base.update(overrides)
    return base


def test_valid_commit_approval() -> None:
    approval = CommitApproval.model_validate(_commit_dict())
    assert approval.kind == "commit"
    assert approval.allowed_paths == ["src/a.py"]


def test_valid_push_approval() -> None:
    approval = PushApproval.model_validate(_push_dict())
    assert approval.upstream == "origin/main"


def test_extra_field_rejected() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CommitApproval.model_validate(_commit_dict(unexpected="x"))


@pytest.mark.parametrize("head", ["ABCDEF", "xyz", "a" * 39, ""])
def test_bad_head_rejected(head: str) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CommitApproval.model_validate(_commit_dict(head=head))


def test_load_commit_approval_wrong_kind(tmp_path: Path) -> None:
    path = tmp_path / "ap.yaml"
    path.write_text(yaml.safe_dump(_push_dict()), encoding="utf-8")
    with pytest.raises(ApprovalError, match="Expected a commit approval"):
        load_commit_approval(path)


def test_load_push_approval_wrong_kind(tmp_path: Path) -> None:
    path = tmp_path / "ap.yaml"
    path.write_text(yaml.safe_dump(_commit_dict()), encoding="utf-8")
    with pytest.raises(ApprovalError, match="Expected a push approval"):
        load_push_approval(path)


def test_load_commit_approval_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "ap.yaml"
    path.write_text(yaml.safe_dump(_commit_dict()), encoding="utf-8")
    approval = load_commit_approval(path)
    assert approval.task_id == "T-1"


def test_load_non_mapping_rejected(tmp_path: Path) -> None:
    path = tmp_path / "ap.yaml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ApprovalError, match="must be a YAML mapping"):
        load_commit_approval(path)


def test_approval_digest_is_file_sha256(tmp_path: Path) -> None:
    import hashlib

    path = tmp_path / "ap.yaml"
    data = b"kind: commit\n"
    path.write_bytes(data)
    assert approval_digest(path) == hashlib.sha256(data).hexdigest()
