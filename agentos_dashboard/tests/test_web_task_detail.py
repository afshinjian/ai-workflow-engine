"""PG-03 — the Task detail page: rendering, the raw-source toggle, read-only posture, and
escape-first XSS proof (`SECURITY_MODEL.md` SC-04/SC-05; `TEST_STRATEGY.md` TC-06)."""

from __future__ import annotations

from pathlib import Path

from agentos_dashboard.tests._asgi_client import AsgiTestClient
from agentos_dashboard.tests.conftest import write


def test_task_detail_page_renders(workspace: Path, client: AsgiTestClient) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## FIX-001 — do the thing\n\nStatus: Done\n\nDid the thing carefully.\n\n",
    )
    response = client.get("/tasks/FIX-001")
    assert response.status == 200
    assert "text/html" in (response.header("content-type") or "")
    assert "FIX-001" in response.text
    assert "do the thing" in response.text


def test_task_detail_page_unknown_id_is_a_typed_404(client: AsgiTestClient) -> None:
    response = client.get("/tasks/NOPE-1")
    assert response.status == 404
    assert "Task not found" in response.text
    assert "NOPE-1" in response.text


def test_task_detail_page_carries_security_headers(workspace: Path, client: AsgiTestClient) -> None:
    write(workspace, "docs/TASK_QUEUE.md", "## FIX-001 — a\n\nStatus: Planned\n\nBody.\n\n")
    response = client.get("/tasks/FIX-001")
    assert response.header("content-security-policy") is not None
    assert response.header("cache-control") == "no-store"


def test_task_detail_page_has_a_raw_source_toggle(workspace: Path, client: AsgiTestClient) -> None:
    write(workspace, "docs/TASK_QUEUE.md", "## FIX-001 — a\n\nStatus: Planned\n\nBody text.\n\n")
    response = client.get("/tasks/FIX-001")
    assert "<details>" in response.text
    assert "Raw Markdown source" in response.text
    assert "Body text." in response.text


def test_task_detail_page_has_no_mutation_affordance(
    workspace: Path, client: AsgiTestClient
) -> None:
    write(workspace, "docs/TASK_QUEUE.md", "## FIX-001 — a\n\nStatus: Planned\n\nBody.\n\n")
    response = client.get("/tasks/FIX-001")
    assert "<button" not in response.text
    assert "<form" not in response.text
    # The disabled acceptance-criteria checkboxes are the one `<input>` on this page, and they
    # are `disabled` (unusable) precisely because DR-023 forbids any real mutation affordance.
    for line in response.text.splitlines():
        if "<input" in line:
            assert "disabled" in line


def test_task_detail_page_shows_git_provenance(workspace: Path, client: AsgiTestClient) -> None:
    from agentos_dashboard.tests.conftest import git

    write(workspace, "README.md", "hello\n")
    git(workspace, "init", "--quiet", "--initial-branch=main")
    git(workspace, "add", "README.md")
    git(workspace, "commit", "--quiet", "-m", "first commit")
    sha = git(workspace, "rev-parse", "HEAD")
    short = sha[:7]
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        f"## FIX-001 — has a commit\n\nStatus: Done\n\nCommitted as `{short}`.\n\n",
    )
    response = client.get("/tasks/FIX-001")
    assert short in response.text
    assert "VERIFIED" in response.text


def test_hostile_prose_is_escaped_not_executed(workspace: Path, client: AsgiTestClient) -> None:
    write(
        workspace,
        "docs/TASK_QUEUE.md",
        "## XSS-001 — <img src=x onerror=alert(1)>\n\nStatus: Current\n\n"
        "<script>alert('xss')</script>\n",
    )
    response = client.get("/tasks/XSS-001")
    assert response.status == 200
    assert "<script>alert" not in response.text
    assert "<img src=x onerror" not in response.text
    assert "&lt;script&gt;alert" in response.text


def test_dash_task_stage_contract_is_shown() -> None:
    from agentos_dashboard.core.paths import RepositoryRoot
    from agentos_dashboard.main import create_app
    from agentos_dashboard.settings import DashboardSettings

    real_root = RepositoryRoot.from_path(Path(__file__).resolve().parents[2])
    settings = DashboardSettings.from_env({"AWED_REPO_ROOT": str(real_root.path)})
    app = create_app(settings)
    client = AsgiTestClient(app)
    response = client.get("/tasks/DASH-001")
    assert response.status == 200
    assert "stage-prompts/DASH-001.md" in response.text
