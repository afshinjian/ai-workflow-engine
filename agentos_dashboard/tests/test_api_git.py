"""EP-09/EP-10 (`API_SPEC.md` §2) — the Git status/commits/branches/tags/upstream JSON routes
(DASH-006)."""

from __future__ import annotations

from pathlib import Path

from agentos_dashboard.tests._asgi_client import AsgiTestClient
from agentos_dashboard.tests.conftest import git, write


def test_git_status_envelope_shape(client: AsgiTestClient) -> None:
    response = client.get("/dash/api/v1/git/status")
    assert response.status == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    for key in (
        "head",
        "branch",
        "staged",
        "modified",
        "untracked",
        "pr_references",
        "commit_badges",
        "findings",
    ):
        assert key in data


def test_git_status_outside_a_repository_reports_unavailable(client: AsgiTestClient) -> None:
    data = client.get("/dash/api/v1/git/status").json()["data"]
    assert data["branch"] is None
    assert data["clean"] is None


def test_git_commits_reflects_a_real_repository(git_client: AsgiTestClient) -> None:
    response = git_client.get("/dash/api/v1/git/commits")
    assert response.status == 200
    data = response.json()["data"]
    assert len(data["commits"]) == 1
    assert data["commits"][0]["subject"] == "first commit"
    assert data["truncated"] is False


def test_git_branches_reports_merged_flag(git_client: AsgiTestClient, git_repo: Path) -> None:
    git(git_repo, "checkout", "--quiet", "-b", "feature/unmerged")
    write(git_repo, "unmerged.txt", "x\n")
    git(git_repo, "add", "unmerged.txt")
    git(git_repo, "commit", "--quiet", "-m", "never merged")
    git(git_repo, "checkout", "--quiet", "main")

    data = git_client.get("/dash/api/v1/git/branches").json()["data"]
    by_name = {b["name"]: b for b in data["branches"]}
    assert by_name["main"]["merged"] is True
    assert by_name["feature/unmerged"]["merged"] is False


def test_git_tags_lists_tags(git_client: AsgiTestClient, git_repo: Path) -> None:
    git(git_repo, "tag", "v1.0.0")
    data = git_client.get("/dash/api/v1/git/tags").json()["data"]
    assert [t["name"] for t in data["tags"]] == ["v1.0.0"]


def test_git_upstream_violation_when_none_configured(git_client: AsgiTestClient) -> None:
    data = git_client.get("/dash/api/v1/git/upstream").json()["data"]
    assert data["default_branch"] == "main"
    assert data["violation"] is True
    assert data["findings"][0]["rule"] == "upstream_missing"


def test_git_upstream_passes_when_configured(
    git_client: AsgiTestClient, tmp_path: Path, git_repo: Path
) -> None:
    remote = tmp_path / "remote.git"
    git(git_repo, "clone", "--quiet", "--bare", str(git_repo), str(remote))
    git(git_repo, "remote", "add", "origin", str(remote))
    git(git_repo, "fetch", "--quiet", "origin")
    git(git_repo, "branch", "--set-upstream-to=origin/main", "main")

    data = git_client.get("/dash/api/v1/git/upstream").json()["data"]
    assert data["violation"] is False
    assert data["upstream"] == "origin/main"


def test_no_repository_write_in_git_module() -> None:
    """SC-06/TR-08: `services.git`/`api.git` never construct a repository write path."""
    import ast
    from pathlib import Path

    package_root = Path(__file__).resolve().parents[1]
    for relative in ("services/git.py", "api/git.py"):
        source = (package_root / relative).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in {
                "write_text",
                "write_bytes",
                "unlink",
            }:
                raise AssertionError(f"{relative} calls a write method: {node.attr}")
