"""EP-13 (`API_SPEC.md` §2): `GET /dash/api/v1/stages`."""

from __future__ import annotations

from agentos_dashboard.prompt_templates.schema import STAGE_SCHEMA
from agentos_dashboard.tests._asgi_client import AsgiTestClient


def test_stages_envelope_shape(client: AsgiTestClient) -> None:
    response = client.get("/dash/api/v1/stages")
    assert response.status == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert "stages" in data
    assert "findings" in data
    assert [s["stage_id"] for s in data["stages"]] == [s.stage_id for s in STAGE_SCHEMA]


def test_stages_precondition_report_present_for_every_stage(client: AsgiTestClient) -> None:
    data = client.get("/dash/api/v1/stages").json()["data"]
    for stage in data["stages"]:
        report = stage["precondition_report"]
        assert report is not None
        assert report["stage_id"] == stage["stage_id"]
        names = {r["name"] for r in report["results"]}
        assert names == {
            "owner_authorization_recorded",
            "registry_schema_consistent",
            "predecessor_complete",
            "clean_tree",
            "correct_branch",
            "sole_active_invariant",
            "blocking_open_questions_resolved",
            "prompt_sources_available",
        }
