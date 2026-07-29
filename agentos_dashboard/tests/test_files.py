"""TC-03/TC-09 — the read-only file adapter: caps, tolerant decoding, and typed refusals."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

from agentos_dashboard.core import DEFAULT_MAX_READ_BYTES
from agentos_dashboard.core.files import (
    FileAccessError,
    FileRefusal,
    digest_file,
    read_head_tail,
    read_text,
    stat_file,
)
from agentos_dashboard.core.paths import PathRefusal, PathRefusedError, RepositoryRoot

from .conftest import write


def test_read_text_returns_whole_small_file(root: RepositoryRoot, workspace: Path) -> None:
    write(workspace, "docs/TASK_QUEUE.md", "# Task Queue\n\nbody\n")
    result = read_text(root, "docs/TASK_QUEUE.md")
    assert result.text == "# Task Queue\n\nbody\n"
    assert result.path == "docs/TASK_QUEUE.md"
    assert result.truncated is False
    assert result.decoded_with_replacement is False
    assert result.read_bytes == result.size_bytes == len("# Task Queue\n\nbody\n")


def test_read_text_truncates_at_the_cap_and_says_so(root: RepositoryRoot, workspace: Path) -> None:
    write(workspace, "big.md", "x" * 5000)
    result = read_text(root, "big.md", max_bytes=1000)
    assert result.truncated is True
    assert result.read_bytes == 1000
    assert result.size_bytes == 5000
    assert result.text == "x" * 1000


def test_read_text_at_exactly_the_cap_is_not_truncated(
    root: RepositoryRoot, workspace: Path
) -> None:
    write(workspace, "exact.md", "y" * 128)
    result = read_text(root, "exact.md", max_bytes=128)
    assert result.truncated is False
    assert result.read_bytes == 128


def test_default_cap_is_the_documented_two_megabytes(root: RepositoryRoot, workspace: Path) -> None:
    """TC-09: a 5 MB document renders capped rather than whole, with the flag set."""
    (workspace / "huge.log").write_bytes(b"z" * (5 * 1024 * 1024))
    result = read_text(root, "huge.log")
    assert DEFAULT_MAX_READ_BYTES == 2 * 1024 * 1024
    assert result.read_bytes == DEFAULT_MAX_READ_BYTES
    assert result.truncated is True


def test_read_text_decodes_invalid_utf8_without_raising(
    root: RepositoryRoot, workspace: Path
) -> None:
    (workspace / "latin1.md").write_bytes(b"caf\xe9 governance\n")
    result = read_text(root, "latin1.md")
    assert result.decoded_with_replacement is True
    assert "governance" in result.text
    assert "�" in result.text


def test_read_text_rejects_a_non_positive_cap(root: RepositoryRoot, workspace: Path) -> None:
    write(workspace, "a.md", "a\n")
    with pytest.raises(FileAccessError) as caught:
        read_text(root, "a.md", max_bytes=0)
    assert caught.value.refusal is FileRefusal.INVALID_LIMIT


def test_missing_file_is_a_typed_refusal(root: RepositoryRoot) -> None:
    with pytest.raises(FileAccessError) as caught:
        read_text(root, "docs/absent.md")
    assert caught.value.refusal is FileRefusal.NOT_FOUND


def test_directory_is_a_typed_refusal(root: RepositoryRoot, workspace: Path) -> None:
    (workspace / "docs").mkdir()
    with pytest.raises(FileAccessError) as caught:
        read_text(root, "docs")
    assert caught.value.refusal is FileRefusal.NOT_A_FILE


def test_fifo_is_a_typed_refusal_rather_than_a_blocking_read(
    root: RepositoryRoot, workspace: Path
) -> None:
    import os

    os.mkfifo(workspace / "pipe")
    with pytest.raises(FileAccessError) as caught:
        read_text(root, "pipe")
    assert caught.value.refusal is FileRefusal.NOT_A_FILE


@pytest.mark.parametrize("relative", ["../outside.txt", "/etc/passwd", ".env", ".git/config"])
def test_the_file_api_enforces_path_refusals(root: RepositoryRoot, relative: str) -> None:
    with pytest.raises(PathRefusedError):
        read_text(root, relative)


def test_deny_list_is_enforced_even_when_the_file_exists(
    root: RepositoryRoot, workspace: Path
) -> None:
    write(workspace, ".env", "TOKEN=ghp_secretvaluevaluevalue\n")
    with pytest.raises(PathRefusedError) as caught:
        read_text(root, ".env")
    assert caught.value.refusal is PathRefusal.DENIED


def test_stat_file_reports_size_and_mtime(root: RepositoryRoot, workspace: Path) -> None:
    target = write(workspace, "docs/CONTEXT.md", "context\n")
    facts = stat_file(root, "docs/CONTEXT.md")
    assert facts.path == "docs/CONTEXT.md"
    assert facts.size_bytes == len("context\n")
    assert facts.mtime_ns == target.stat().st_mtime_ns


def test_stat_file_refuses_a_missing_file(root: RepositoryRoot) -> None:
    with pytest.raises(FileAccessError) as caught:
        stat_file(root, "docs/absent.md")
    assert caught.value.refusal is FileRefusal.NOT_FOUND


def test_head_tail_of_a_large_file_omits_the_middle(root: RepositoryRoot, workspace: Path) -> None:
    payload = ("head" * 100) + ("middle" * 1000) + ("tail" * 100)
    write(workspace, "large.log", payload)
    result = read_head_tail(root, "large.log", head_bytes=400, tail_bytes=400)
    assert result.head == payload[:400]
    assert result.tail == payload[-400:]
    assert result.omitted_bytes == len(payload) - 800
    assert result.truncated is True


def test_head_tail_of_a_small_file_returns_everything_once(
    root: RepositoryRoot, workspace: Path
) -> None:
    write(workspace, "small.log", "only a little\n")
    result = read_head_tail(root, "small.log", head_bytes=1024, tail_bytes=1024)
    assert result.head == "only a little\n"
    assert result.tail == ""
    assert result.omitted_bytes == 0
    assert result.truncated is False


def test_head_tail_rejects_a_non_positive_window(root: RepositoryRoot, workspace: Path) -> None:
    write(workspace, "a.log", "a\n")
    with pytest.raises(FileAccessError) as caught:
        read_head_tail(root, "a.log", head_bytes=10, tail_bytes=-1)
    assert caught.value.refusal is FileRefusal.INVALID_LIMIT


def test_head_tail_tolerates_a_split_multibyte_character(
    root: RepositoryRoot, workspace: Path
) -> None:
    # Slicing by bytes can cut a UTF-8 sequence in half; that must degrade to a replacement
    # character with the flag set, never raise.
    (workspace / "utf8.log").write_bytes("é".encode() * 200)
    result = read_head_tail(root, "utf8.log", head_bytes=101, tail_bytes=101)
    assert result.decoded_with_replacement is True
    assert result.omitted_bytes == 400 - 202


def test_digest_file_matches_sha256_of_the_bytes(root: RepositoryRoot, workspace: Path) -> None:
    payload = b"governance\n" * 10_000
    (workspace / "digest.bin").write_bytes(payload)
    assert digest_file(root, "digest.bin") == hashlib.sha256(payload).hexdigest()


def test_digest_file_refuses_a_denied_path(root: RepositoryRoot, workspace: Path) -> None:
    write(workspace, ".git/config", "[core]\n")
    with pytest.raises(PathRefusedError):
        digest_file(root, ".git/config")


def test_module_contains_no_write_path() -> None:
    """TR-08 as a source property: the file adapter has no way to write, not a guarded one.

    Checked over the parsed syntax tree rather than the raw text, so prose in a docstring that
    happens to mention `"w"` cannot fail the test and, more importantly, a real write cannot
    pass it by being spelled differently.
    """
    module = Path(__file__).resolve().parents[1] / "core" / "files.py"
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))

    mutating_methods = {
        "write",
        "writelines",
        "write_text",
        "write_bytes",
        "unlink",
        "rmdir",
        "mkdir",
        "touch",
        "rename",
        "replace",
        "chmod",
        "symlink_to",
        "hardlink_to",
    }
    opens = 0
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in mutating_methods:
            offenders.append(f"{node.lineno}: .{node.attr}(")
        if isinstance(node, ast.Import | ast.ImportFrom):
            names = [alias.name for alias in node.names]
            if any(name.split(".")[0] in {"shutil", "tempfile"} for name in names):
                offenders.append(f"{node.lineno}: import {names}")
        if isinstance(node, ast.Call):
            func = node.func
            is_open = (isinstance(func, ast.Name) and func.id == "open") or (
                isinstance(func, ast.Attribute) and func.attr == "open"
            )
            if not is_open:
                continue
            opens += 1
            # `Path.open("rb")` puts the mode first, builtin `open(path, "rb")` puts it second,
            # so every string constant in the call is checked and exactly one — `rb` — is
            # tolerated.
            modes = [
                argument.value
                for argument in [*node.args, *(kw.value for kw in node.keywords)]
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
            ]
            if modes != ["rb"]:
                offenders.append(f"{node.lineno}: open(mode={modes})")

    assert opens >= 1, "the scan found no open() call at all — it would pass vacuously"
    assert not offenders, f"the file adapter must contain no write path: {offenders}"
