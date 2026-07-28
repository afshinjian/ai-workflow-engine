"""Tests for the Git and GitHub Skills (`SKILL_CONTRACTS.md` §5).

`git` invocations run against real temporary repositories with a local (`file://`-style) remote,
the same technique `test_skills_repository.py` already established — no test reaches the network.
`gh` invocations are mocked at the process boundary per the stage contract's own instruction: a
fake `gh` executable is placed first on `PATH` for the duration of a test, and its canned
responses are supplied through an environment variable that is explicitly passed as this module's
own `allowed_environment_variables` — never by patching this module's internals. The fake also
appends every invocation's argv to a log file, so a test can assert not just *what* a Skill
returned but *whether* (and in what order) it actually called `gh`.
"""

from __future__ import annotations

import ast
import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

from agentos_workflow.skills import FailureKind, RetryClassification
from agentos_workflow.skills.git_github import (
    create_commit,
    create_pull_request,
    enable_automatic_squash_merge,
    push_stage_branch,
    read_pull_request_state,
    read_required_checks,
    verify_head_sha,
    verify_merge_completion,
)

BASELINE = "main"
STAGE_BRANCH = "feature/example"
GH_ENV = ("FAKE_GH_STATE", "FAKE_GH_LOG")


def git(repo: Path, *args: str) -> str:
    """Direct Git for fixture setup only — never the code under test."""
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env={
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(repo),
            "LC_ALL": "C",
            "GIT_AUTHOR_NAME": "Fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "Fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        },
    )
    return result.stdout.strip()


def write(repo: Path, relative: str, content: str) -> None:
    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository on `feature/example`, branched from one commit on `main` with an `origin`
    remote pointing at a local bare clone."""
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", BASELINE, str(origin)], check=True, capture_output=True
    )
    work = tmp_path / "work"
    work.mkdir()
    git(work, "init", "-b", BASELINE)
    git(work, "config", "user.name", "Fixture")
    git(work, "config", "user.email", "fixture@example.invalid")
    write(work, "README.md", "baseline\n")
    git(work, "add", "README.md")
    git(work, "commit", "-m", "initial")
    git(work, "remote", "add", "origin", str(origin))
    git(work, "push", "-u", "origin", BASELINE)
    git(work, "checkout", "-b", STAGE_BRANCH)
    return work


FAKE_GH_SCRIPT = """#!/usr/bin/env python3
import json
import os
import sys

state_path = os.environ.get("FAKE_GH_STATE")
responses = {}
if state_path and os.path.exists(state_path):
    with open(state_path) as handle:
        responses = json.load(handle)

args = sys.argv[1:]
key = " ".join(args[:2])
entry = responses.get(key)
if entry is None:
    entry = responses.get(
        args[0] if args else "", {"exit_code": 1, "stdout": "", "stderr": "no fixture for " + key}
    )

log_path = os.environ.get("FAKE_GH_LOG")
if log_path:
    with open(log_path, "a") as handle:
        handle.write(json.dumps(args) + "\\n")

sys.stdout.write(entry.get("stdout", ""))
sys.stderr.write(entry.get("stderr", ""))
sys.exit(entry.get("exit_code", 0))
"""


@pytest.fixture
def fake_gh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Install a fake `gh` first on `PATH` and return the path its JSON responses are read from."""
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir(exist_ok=True)
    script = bin_dir / "gh"
    script.write_text(FAKE_GH_SCRIPT, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    state_path = tmp_path / "gh-state.json"
    state_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("FAKE_GH_STATE", str(state_path))
    log_path = tmp_path / "gh-calls.jsonl"
    monkeypatch.setenv("FAKE_GH_LOG", str(log_path))
    return state_path


def set_gh_responses(state_path: Path, responses: dict[str, Any]) -> None:
    state_path.write_text(json.dumps(responses), encoding="utf-8")


def gh_calls(state_path: Path) -> list[list[str]]:
    log_path = state_path.with_name("gh-calls.jsonl")
    if not log_path.exists():
        return []
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line]


# --------------------------------------------------------------------------------------------
# create_commit
# --------------------------------------------------------------------------------------------


class TestCreateCommit:
    def test_commits_the_working_trees_diff(self, repo: Path) -> None:
        head = git(repo, "rev-parse", "HEAD")
        write(repo, "new.txt", "content\n")
        result = create_commit(
            repo, branch=STAGE_BRANCH, message="feat: add file", expected_head_sha=head
        )
        assert result.ok is True
        assert result.value is not None
        assert result.value.branch == STAGE_BRANCH
        assert result.value.commit_sha != head
        assert git(repo, "log", "-1", "--format=%s") == "feat: add file"
        assert git(repo, "status", "--porcelain") == ""

    def test_is_idempotent_on_repeat(self, repo: Path) -> None:
        head = git(repo, "rev-parse", "HEAD")
        write(repo, "new.txt", "content\n")
        first = create_commit(
            repo, branch=STAGE_BRANCH, message="feat: add file", expected_head_sha=head
        )
        assert first.ok is True

        # A retried call still names the *original* expected_head_sha — the caller does not know
        # the commit already happened.
        second = create_commit(
            repo, branch=STAGE_BRANCH, message="feat: add file", expected_head_sha=head
        )
        assert second.ok is True
        assert second.value is not None
        assert first.value is not None
        assert second.value.commit_sha == first.value.commit_sha

    def test_refuses_blank_message(self, repo: Path) -> None:
        head = git(repo, "rev-parse", "HEAD")
        result = create_commit(repo, branch=STAGE_BRANCH, message="   ", expected_head_sha=head)
        assert result.ok is False
        assert result.error is not None
        assert result.error.kind is FailureKind.UNSAFE_INPUT
        assert result.error.retry_classification is RetryClassification.NON_RETRYABLE

    def test_refuses_when_branch_has_moved(self, repo: Path) -> None:
        write(repo, "new.txt", "content\n")
        stale_sha = "a" * 40
        result = create_commit(
            repo, branch=STAGE_BRANCH, message="feat: x", expected_head_sha=stale_sha
        )
        assert result.ok is False
        assert result.error is not None
        assert result.error.kind is FailureKind.PRECONDITION
        assert result.error.retry_classification is RetryClassification.PROVEN_PRE_SIDE_EFFECT
        # Nothing should have been staged or committed.
        assert git(repo, "status", "--porcelain") == "?? new.txt"

    def test_refuses_when_nothing_to_commit(self, repo: Path) -> None:
        head = git(repo, "rev-parse", "HEAD")
        result = create_commit(repo, branch=STAGE_BRANCH, message="feat: x", expected_head_sha=head)
        assert result.ok is False
        assert result.error is not None
        assert result.error.kind is FailureKind.PRECONDITION
        assert result.error.retry_classification is RetryClassification.NON_RETRYABLE

    def test_refuses_wrong_current_branch(self, repo: Path) -> None:
        head = git(repo, "rev-parse", "HEAD")
        result = create_commit(
            repo, branch="some-other-branch", message="feat: x", expected_head_sha=head
        )
        assert result.ok is False
        assert result.error is not None
        assert result.error.kind is FailureKind.PRECONDITION
        assert result.error.retry_classification is RetryClassification.PROVEN_PRE_SIDE_EFFECT


# --------------------------------------------------------------------------------------------
# push_stage_branch
# --------------------------------------------------------------------------------------------


class TestPushStageBranch:
    def test_pushes_new_branch(self, repo: Path) -> None:
        head = git(repo, "rev-parse", "HEAD")
        result = push_stage_branch(
            repo, branch=STAGE_BRANCH, remote="origin", expected_head_sha=head
        )
        assert result.ok is True
        assert result.value is not None
        assert result.value.head_sha == head
        assert result.value.remote_ref == f"refs/heads/{STAGE_BRANCH}"
        remote_sha = git(repo, "ls-remote", "origin", f"refs/heads/{STAGE_BRANCH}").split()[0]
        assert remote_sha == head

    def test_is_idempotent_when_remote_already_matches(self, repo: Path) -> None:
        head = git(repo, "rev-parse", "HEAD")
        first = push_stage_branch(
            repo, branch=STAGE_BRANCH, remote="origin", expected_head_sha=head
        )
        assert first.ok is True
        second = push_stage_branch(
            repo, branch=STAGE_BRANCH, remote="origin", expected_head_sha=head
        )
        assert second.ok is True
        assert second.value is not None
        assert second.value.head_sha == head

    def test_refuses_when_local_branch_moved(self, repo: Path) -> None:
        stale_sha = "b" * 40
        result = push_stage_branch(
            repo, branch=STAGE_BRANCH, remote="origin", expected_head_sha=stale_sha
        )
        assert result.ok is False
        assert result.error is not None
        assert result.error.kind is FailureKind.PRECONDITION
        assert result.error.retry_classification is RetryClassification.PROVEN_PRE_SIDE_EFFECT

    def test_refuses_unsafe_remote_name(self, repo: Path) -> None:
        head = git(repo, "rev-parse", "HEAD")
        result = push_stage_branch(
            repo, branch=STAGE_BRANCH, remote="--upload-pack=x", expected_head_sha=head
        )
        assert result.ok is False
        assert result.error is not None
        assert result.error.kind is FailureKind.UNSAFE_INPUT


# --------------------------------------------------------------------------------------------
# verify_head_sha
# --------------------------------------------------------------------------------------------


class TestVerifyHeadSha:
    def test_matches(self, repo: Path) -> None:
        head = git(repo, "rev-parse", "HEAD")
        result = verify_head_sha(repo, branch=STAGE_BRANCH, expected_head_sha=head)
        assert result.ok is True
        assert result.value is True

    def test_mismatches(self, repo: Path) -> None:
        result = verify_head_sha(repo, branch=STAGE_BRANCH, expected_head_sha="c" * 40)
        assert result.ok is True
        assert result.value is False

    def test_missing_branch(self, repo: Path) -> None:
        result = verify_head_sha(repo, branch="does-not-exist", expected_head_sha="c" * 40)
        assert result.ok is False
        assert result.error is not None
        assert result.error.kind is FailureKind.NOT_FOUND
        assert result.error.retry_classification is RetryClassification.NOT_APPLICABLE


# --------------------------------------------------------------------------------------------
# create_pull_request
# --------------------------------------------------------------------------------------------


class TestCreatePullRequest:
    def test_creates_new_pull_request(self, repo: Path, fake_gh: Path) -> None:
        head_sha = "d" * 40
        set_gh_responses(
            fake_gh,
            {
                "pr list": {"exit_code": 0, "stdout": "[]"},
                "pr create": {
                    "exit_code": 0,
                    "stdout": "https://github.invalid/example/repo/pull/42\n",
                },
                "pr view": {
                    "exit_code": 0,
                    "stdout": json.dumps(
                        {
                            "number": 42,
                            "url": "https://github.invalid/example/repo/pull/42",
                            "headRefOid": head_sha,
                        }
                    ),
                },
            },
        )
        result = create_pull_request(
            repo,
            branch=STAGE_BRANCH,
            baseline_branch=BASELINE,
            title="t",
            body="b",
            head_sha=head_sha,
            allowed_environment_variables=GH_ENV,
        )
        assert result.ok is True
        assert result.value is not None
        assert result.value.number == 42
        assert result.value.head_sha == head_sha
        calls = gh_calls(fake_gh)
        assert calls[0][:2] == ["pr", "list"]
        assert calls[1][:2] == ["pr", "create"]
        assert calls[2][:2] == ["pr", "view"]

    def test_reuses_existing_open_pull_request(self, repo: Path, fake_gh: Path) -> None:
        head_sha = "e" * 40
        set_gh_responses(
            fake_gh,
            {
                "pr list": {
                    "exit_code": 0,
                    "stdout": json.dumps(
                        [
                            {
                                "number": 7,
                                "url": "https://github.invalid/example/repo/pull/7",
                                "headRefOid": head_sha,
                            }
                        ]
                    ),
                },
                "pr create": {"exit_code": 1, "stdout": "", "stderr": "should never be called"},
            },
        )
        result = create_pull_request(
            repo,
            branch=STAGE_BRANCH,
            baseline_branch=BASELINE,
            title="t",
            body="b",
            head_sha=head_sha,
            allowed_environment_variables=GH_ENV,
        )
        assert result.ok is True
        assert result.value is not None
        assert result.value.number == 7
        calls = gh_calls(fake_gh)
        assert [call[:2] for call in calls] == [["pr", "list"]]

    def test_refuses_baseline_target(self, repo: Path, fake_gh: Path) -> None:
        result = create_pull_request(
            repo,
            branch=BASELINE,
            baseline_branch=BASELINE,
            title="t",
            body="b",
            head_sha="f" * 40,
            allowed_environment_variables=GH_ENV,
        )
        assert result.ok is False
        assert result.error is not None
        assert result.error.kind is FailureKind.PERMANENT
        assert gh_calls(fake_gh) == []

    def test_refuses_blank_title(self, repo: Path, fake_gh: Path) -> None:
        result = create_pull_request(
            repo,
            branch=STAGE_BRANCH,
            baseline_branch=BASELINE,
            title="  ",
            body="b",
            head_sha="f" * 40,
            allowed_environment_variables=GH_ENV,
        )
        assert result.ok is False
        assert result.error is not None
        assert result.error.kind is FailureKind.UNSAFE_INPUT
        assert gh_calls(fake_gh) == []

    def test_reports_malformed_gh_output(self, repo: Path, fake_gh: Path) -> None:
        set_gh_responses(fake_gh, {"pr list": {"exit_code": 0, "stdout": "not json"}})
        result = create_pull_request(
            repo,
            branch=STAGE_BRANCH,
            baseline_branch=BASELINE,
            title="t",
            body="b",
            head_sha="f" * 40,
            allowed_environment_variables=GH_ENV,
        )
        assert result.ok is False
        assert result.error is not None
        assert result.error.kind is FailureKind.MALFORMED_OUTPUT


# --------------------------------------------------------------------------------------------
# read_pull_request_state
# --------------------------------------------------------------------------------------------


class TestReadPullRequestState:
    def test_open(self, repo: Path, fake_gh: Path) -> None:
        set_gh_responses(
            fake_gh,
            {
                "pr view": {
                    "exit_code": 0,
                    "stdout": json.dumps(
                        {"number": 1, "state": "OPEN", "headRefOid": "a" * 40, "mergedAt": None}
                    ),
                }
            },
        )
        result = read_pull_request_state(
            repo, pull_request_number=1, allowed_environment_variables=GH_ENV
        )
        assert result.ok is True
        assert result.value is not None
        assert result.value.state == "open"
        assert result.value.merged is False

    def test_merged(self, repo: Path, fake_gh: Path) -> None:
        set_gh_responses(
            fake_gh,
            {
                "pr view": {
                    "exit_code": 0,
                    "stdout": json.dumps(
                        {
                            "number": 1,
                            "state": "MERGED",
                            "headRefOid": "a" * 40,
                            "mergedAt": "2026-07-28T00:00:00Z",
                        }
                    ),
                }
            },
        )
        result = read_pull_request_state(
            repo, pull_request_number=1, allowed_environment_variables=GH_ENV
        )
        assert result.ok is True
        assert result.value is not None
        assert result.value.merged is True

    def test_rejects_invalid_pr_number(self, repo: Path, fake_gh: Path) -> None:
        result = read_pull_request_state(
            repo, pull_request_number=0, allowed_environment_variables=GH_ENV
        )
        assert result.ok is False
        assert result.error is not None
        assert result.error.kind is FailureKind.UNSAFE_INPUT
        assert gh_calls(fake_gh) == []


# --------------------------------------------------------------------------------------------
# read_required_checks
# --------------------------------------------------------------------------------------------


class TestReadRequiredChecks:
    def test_all_passed(self, repo: Path, fake_gh: Path) -> None:
        set_gh_responses(
            fake_gh,
            {
                "pr checks": {
                    "exit_code": 0,
                    "stdout": json.dumps(
                        [{"name": "ci/tests", "state": "SUCCESS", "bucket": "pass"}]
                    ),
                }
            },
        )
        result = read_required_checks(
            repo, pull_request_number=1, allowed_environment_variables=GH_ENV
        )
        assert result.ok is True
        assert result.value is not None
        assert result.value.all_passed is True

    def test_failed_check_blocks(self, repo: Path, fake_gh: Path) -> None:
        set_gh_responses(
            fake_gh,
            {
                "pr checks": {
                    "exit_code": 8,
                    "stdout": json.dumps(
                        [{"name": "ci/tests", "state": "FAILURE", "bucket": "fail"}]
                    ),
                }
            },
        )
        result = read_required_checks(
            repo, pull_request_number=1, allowed_environment_variables=GH_ENV
        )
        assert result.ok is True
        assert result.value is not None
        assert result.value.all_passed is False
        assert result.value.failed == ("ci/tests",)

    def test_pending_check(self, repo: Path, fake_gh: Path) -> None:
        set_gh_responses(
            fake_gh,
            {
                "pr checks": {
                    "exit_code": 8,
                    "stdout": json.dumps(
                        [{"name": "ci/tests", "state": "PENDING", "bucket": "pending"}]
                    ),
                }
            },
        )
        result = read_required_checks(
            repo, pull_request_number=1, allowed_environment_variables=GH_ENV
        )
        assert result.ok is True
        assert result.value is not None
        assert result.value.pending == ("ci/tests",)
        assert result.value.all_passed is False

    def test_no_checks_reported(self, repo: Path, fake_gh: Path) -> None:
        set_gh_responses(
            fake_gh,
            {
                "pr checks": {
                    "exit_code": 1,
                    "stdout": "",
                    "stderr": "no checks reported on the 'feature/example' branch",
                }
            },
        )
        result = read_required_checks(
            repo, pull_request_number=1, allowed_environment_variables=GH_ENV
        )
        assert result.ok is True
        assert result.value is not None
        assert result.value.all_passed is True


# --------------------------------------------------------------------------------------------
# enable_automatic_squash_merge
# --------------------------------------------------------------------------------------------


class TestEnableAutomaticSquashMerge:
    def test_refuses_on_head_mismatch(self, repo: Path, fake_gh: Path) -> None:
        set_gh_responses(
            fake_gh,
            {
                "pr view": {
                    "exit_code": 0,
                    "stdout": json.dumps({"headRefOid": "a" * 40, "state": "OPEN"}),
                }
            },
        )
        result = enable_automatic_squash_merge(
            repo,
            pull_request_number=1,
            expected_head_sha="b" * 40,
            allowed_environment_variables=GH_ENV,
        )
        assert result.ok is False
        assert result.error is not None
        assert result.error.kind is FailureKind.PRECONDITION
        assert result.error.retry_classification is RetryClassification.NON_RETRYABLE
        calls = gh_calls(fake_gh)
        assert [call[:2] for call in calls] == [["pr", "view"]]

    def test_enables_when_head_matches(self, repo: Path, fake_gh: Path) -> None:
        sha = "c" * 40
        set_gh_responses(
            fake_gh,
            {
                "pr view": {
                    "exit_code": 0,
                    "stdout": json.dumps({"headRefOid": sha, "state": "OPEN"}),
                },
                "pr merge": {"exit_code": 0, "stdout": "auto-merge enabled\n"},
            },
        )
        result = enable_automatic_squash_merge(
            repo, pull_request_number=1, expected_head_sha=sha, allowed_environment_variables=GH_ENV
        )
        assert result.ok is True
        calls = gh_calls(fake_gh)
        merge_call = next(call for call in calls if call[:2] == ["pr", "merge"])
        assert "--auto" in merge_call
        assert "--squash" in merge_call
        assert "--admin" not in merge_call

    def test_idempotent_when_already_enabled(self, repo: Path, fake_gh: Path) -> None:
        sha = "d" * 40
        set_gh_responses(
            fake_gh,
            {
                "pr view": {
                    "exit_code": 0,
                    "stdout": json.dumps({"headRefOid": sha, "state": "OPEN"}),
                },
                "pr merge": {
                    "exit_code": 1,
                    "stdout": "",
                    "stderr": "Pull request already has auto-merge enabled",
                },
            },
        )
        result = enable_automatic_squash_merge(
            repo, pull_request_number=1, expected_head_sha=sha, allowed_environment_variables=GH_ENV
        )
        assert result.ok is True


# --------------------------------------------------------------------------------------------
# verify_merge_completion
# --------------------------------------------------------------------------------------------


class TestVerifyMergeCompletion:
    def test_confirms_merge(self, repo: Path, fake_gh: Path) -> None:
        merge_sha = "e" * 40
        set_gh_responses(
            fake_gh,
            {
                "pr view": {
                    "exit_code": 0,
                    "stdout": json.dumps(
                        {
                            "state": "MERGED",
                            "headRefName": STAGE_BRANCH,
                            "mergeCommit": {"oid": merge_sha},
                        }
                    ),
                }
            },
        )
        result = verify_merge_completion(
            repo,
            pull_request_number=1,
            branch=STAGE_BRANCH,
            allowed_environment_variables=GH_ENV,
        )
        assert result.ok is True
        assert result.value is not None
        assert result.value.merge_commit_sha == merge_sha
        assert result.value.branch == STAGE_BRANCH

    def test_refuses_when_not_merged(self, repo: Path, fake_gh: Path) -> None:
        set_gh_responses(
            fake_gh,
            {
                "pr view": {
                    "exit_code": 0,
                    "stdout": json.dumps(
                        {"state": "OPEN", "headRefName": STAGE_BRANCH, "mergeCommit": None}
                    ),
                }
            },
        )
        result = verify_merge_completion(
            repo,
            pull_request_number=1,
            branch=STAGE_BRANCH,
            allowed_environment_variables=GH_ENV,
        )
        assert result.ok is False
        assert result.error is not None
        assert result.error.kind is FailureKind.PRECONDITION

    def test_refuses_wrong_branch(self, repo: Path, fake_gh: Path) -> None:
        set_gh_responses(
            fake_gh,
            {
                "pr view": {
                    "exit_code": 0,
                    "stdout": json.dumps(
                        {
                            "state": "MERGED",
                            "headRefName": "some-other-branch",
                            "mergeCommit": {"oid": "e" * 40},
                        }
                    ),
                }
            },
        )
        result = verify_merge_completion(
            repo,
            pull_request_number=1,
            branch=STAGE_BRANCH,
            allowed_environment_variables=GH_ENV,
        )
        assert result.ok is False
        assert result.error is not None
        assert result.error.kind is FailureKind.PRECONDITION


# --------------------------------------------------------------------------------------------
# Structural security properties, asserted over the module's own source (`repository.py`'s own
# `test_no_forbidden_argv_tokens` technique).
# --------------------------------------------------------------------------------------------


def _module_source_path() -> Path:
    import agentos_workflow.skills.git_github as module

    assert module.__file__ is not None
    return Path(module.__file__)


def _string_constants() -> list[str]:
    tree = ast.parse(_module_source_path().read_text(encoding="utf-8"))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


class TestStructuralSecurityProperties:
    def test_no_forbidden_argv_tokens(self) -> None:
        forbidden = (
            "--admin",
            "--force",
            "--force-with-lease",
            "-f",
            "reset",
            "rebase",
            "--amend",
            "filter-branch",
            "--repo",
        )
        constants = _string_constants()
        for token in forbidden:
            assert (
                token not in constants
            ), f"forbidden argv token {token!r} appears in git_github.py"

    def test_exactly_one_merge_enabling_call_site(self) -> None:
        """Exactly one *tuple literal* — not merely one textual mention — passes `("pr", "merge",
        ...)` to `_gh`. AST tuple nodes exclude module/function docstrings, which are `Expr`
        statements, not arguments to `_gh`."""
        tree = ast.parse(_module_source_path().read_text(encoding="utf-8"))
        merge_tuples = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Tuple)
            and len(node.elts) >= 2
            and all(isinstance(element, ast.Constant) for element in node.elts[:2])
            and node.elts[0].value == "pr"  # type: ignore[attr-defined]
            and node.elts[1].value == "merge"  # type: ignore[attr-defined]
        ]
        assert len(merge_tuples) == 1
