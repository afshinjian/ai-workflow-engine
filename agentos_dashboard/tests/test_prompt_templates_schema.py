"""EN-10/EN-12: the coded DASH-001..010 stage schema."""

from __future__ import annotations

import re

from agentos_dashboard.prompt_templates.schema import STAGE_SCHEMA, STAGE_SCHEMA_BY_ID

_STAGE_ID_RE = re.compile(r"\ADASH-\d{3}\Z")


def test_schema_has_exactly_ten_stages_in_order() -> None:
    assert [s.stage_id for s in STAGE_SCHEMA] == [f"DASH-{n:03d}" for n in range(1, 11)]


def test_every_stage_id_is_well_formed() -> None:
    for stage in STAGE_SCHEMA:
        assert _STAGE_ID_RE.match(stage.stage_id)


def test_first_stage_has_no_prerequisite() -> None:
    assert STAGE_SCHEMA[0].prerequisite is None


def test_every_other_stage_prerequisite_is_its_immediate_predecessor() -> None:
    for index, stage in enumerate(STAGE_SCHEMA[1:], start=1):
        assert stage.prerequisite == STAGE_SCHEMA[index - 1].stage_id


def test_prompt_paths_and_report_paths_are_unique() -> None:
    assert len({s.prompt_path for s in STAGE_SCHEMA}) == len(STAGE_SCHEMA)
    assert len({s.report_path for s in STAGE_SCHEMA}) == len(STAGE_SCHEMA)
    assert len({s.branch for s in STAGE_SCHEMA}) == len(STAGE_SCHEMA)


def test_by_id_index_matches_the_tuple() -> None:
    assert STAGE_SCHEMA_BY_ID == {s.stage_id: s for s in STAGE_SCHEMA}


def test_dash_007_matches_the_live_stage_prompt_contract() -> None:
    schema = STAGE_SCHEMA_BY_ID["DASH-007"]
    assert schema.title == "Stage registry and prompt generation"
    assert schema.branch == "feature/dash-007-prompt-generation"
    assert schema.prompt_path == "stage-prompts/DASH-007.md"
    assert schema.prerequisite == "DASH-006"
