"""PG-07 — the Git page: rendering, read-only posture, and no mutation affordance (DASH-006)."""

from __future__ import annotations

from pathlib import Path

from agentos_dashboard.tests._asgi_client import AsgiTestClient
from agentos_dashboard.tests.conftest import git, write


def test_git_page_renders(client: AsgiTestClient) -> None:
    response = client.get("/git")
    assert response.status == 200
    assert "text/html" in (response.header("content-type") or "")
    assert "<h1>Git</h1>" in response.text


def test_git_page_has_primary_navigation_landmark(client: AsgiTestClient) -> None:
    response = client.get("/git")
    assert 'aria-label="Primary"' in response.text
    assert 'aria-current="page"' in response.text


def test_git_page_carries_security_headers(client: AsgiTestClient) -> None:
    response = client.get("/git")
    assert response.header("content-security-policy") is not None
    assert response.header("cache-control") == "no-store"


def test_git_page_has_no_mutation_affordance(client: AsgiTestClient) -> None:
    response = client.get("/git")
    assert "<button" not in response.text
    assert "<form" not in response.text
    assert "<input" not in response.text


def test_git_page_shows_healthy_empty_state_outside_a_repository(client: AsgiTestClient) -> None:
    response = client.get("/git")
    assert "Git status unavailable" in response.text
    assert "No commits" in response.text


def test_git_page_reflects_a_real_repository(git_client: AsgiTestClient) -> None:
    response = git_client.get("/git")
    assert response.status == 200
    assert "main" in response.text
    assert "first commit" in response.text


def test_git_page_shows_upstream_blocker(git_client: AsgiTestClient) -> None:
    response = git_client.get("/git")
    assert "BLOCKER" in response.text


def test_git_page_shows_merged_branch_badge(git_client: AsgiTestClient, git_repo: Path) -> None:
    git(git_repo, "checkout", "--quiet", "-b", "feature/unmerged")
    write(git_repo, "unmerged.txt", "x\n")
    git(git_repo, "add", "unmerged.txt")
    git(git_repo, "commit", "--quiet", "-m", "never merged")
    git(git_repo, "checkout", "--quiet", "main")

    response = git_client.get("/git")
    assert "MERGED" in response.text
    assert "UNMERGED" in response.text


def test_hostile_commit_subject_is_escaped(git_client: AsgiTestClient, git_repo: Path) -> None:
    write(git_repo, "x.txt", "x\n")
    git(git_repo, "add", "x.txt")
    git(git_repo, "commit", "--quiet", "-m", "<script>alert(1)</script>")
    response = git_client.get("/git")
    assert response.status == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text
