"""EP-07/EP-08 (`API_SPEC.md` §2): `GET /governance/docs`, `/governance/docs/{name}`, and
`/governance/search`."""

from __future__ import annotations

from pathlib import Path

from agentos_dashboard.services.governance import GOVERNANCE_DOCUMENTS, MAX_QUERY_LENGTH
from agentos_dashboard.tests._asgi_client import AsgiTestClient
from agentos_dashboard.tests.conftest import write


def test_list_documents(client: AsgiTestClient) -> None:
    response = client.get("/dash/api/v1/governance/docs")
    assert response.status == 200
    data = response.json()["data"]
    assert len(data["documents"]) == len(GOVERNANCE_DOCUMENTS)


def test_unknown_document_is_404(client: AsgiTestClient) -> None:
    response = client.get("/dash/api/v1/governance/docs/not-a-real-doc")
    assert response.status == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_traversal_shaped_identifier_is_404_not_500(client: AsgiTestClient) -> None:
    """Acceptance: a traversal-shaped identifier is refused, never a crash or a filesystem read
    outside the allowlist."""
    for hostile in ("..%2f..%2fetc%2fpasswd", "....//....//etc/passwd"):
        response = client.get(f"/dash/api/v1/governance/docs/{hostile}")
        assert response.status == 404


def test_known_document_renders(client: AsgiTestClient, workspace: Path) -> None:
    write(workspace, "README.md", "# Hi\n\nSome text.\n")
    response = client.get("/dash/api/v1/governance/docs/readme")
    assert response.status == 200
    data = response.json()["data"]
    assert data["doc_id"] == "readme"
    assert "<h1" in (data["rendered_html"] or "")


def test_search_query_too_long_is_422(client: AsgiTestClient) -> None:
    response = client.get(f"/dash/api/v1/governance/search?q={'x' * (MAX_QUERY_LENGTH + 1)}")
    assert response.status == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_search_traversal_shaped_query_is_422(client: AsgiTestClient) -> None:
    response = client.get("/dash/api/v1/governance/search?q=../../etc/passwd")
    assert response.status == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_search_query_at_limit_is_accepted(client: AsgiTestClient) -> None:
    response = client.get(f"/dash/api/v1/governance/search?q={'x' * MAX_QUERY_LENGTH}")
    assert response.status == 200


def test_search_finds_hostile_content_only_as_plain_text(
    client: AsgiTestClient, workspace: Path
) -> None:
    """Acceptance: a search against hostile (script-injection-shaped) document content renders
    as inert escaped text — proven end-to-end via the server-rendered HTML page, where any
    unescaped payload would show up literally as executable markup."""
    write(workspace, "README.md", "before <script>alert(1)</script> needle after\n")
    response = client.get("/dash/api/v1/governance/search?q=needle")
    assert response.status == 200
    results = response.json()["data"]["results"]
    assert len(results) == 1
    # The JSON transport carries the raw (unescaped) snippet; escaping is the HTML page's job.
    assert "<script>" in results[0]["snippet"]


def test_search_response_surfaces_incomplete_allowlist(client: AsgiTestClient) -> None:
    response = client.get("/dash/api/v1/governance/search?q=needle")
    assert response.status == 200
    findings = response.json()["data"]["findings"]
    assert any(finding["rule"] == "document_missing" for finding in findings)
