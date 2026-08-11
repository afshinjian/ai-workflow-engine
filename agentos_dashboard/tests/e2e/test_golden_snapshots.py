"""TC-10 (`TEST_STRATEGY.md`): golden-file snapshots of key pages rendered from the fixture
repository.

The fixture repository's one Git commit is fully reproducible byte-for-byte: `tests/conftest.py`'s
`git()` helper pins `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE`/name/email in `GIT_FIXTURE_ENV`, and the
commit's tree, message, and parent are identical on every run, so its SHA — and therefore every
HEAD-derived string these two pages render — is deterministic across machines and runs. Neither
golden page displays an absolute filesystem path (the fixture's `tmp_path` root), which is the one
value that would otherwise vary run to run. A future template or fixture-content change that
alters either page's rendered bytes must update the corresponding file in `golden/` deliberately,
not by surprise.
"""

from __future__ import annotations

import difflib
from pathlib import Path

from agentos_dashboard.tests._asgi_client import AsgiTestClient

_GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


def _assert_matches_golden(actual: str, golden_name: str) -> None:
    trailing_whitespace_lines = [
        line_number
        for line_number, line in enumerate(actual.splitlines(), start=1)
        if line.endswith((" ", "\t"))
    ]
    assert trailing_whitespace_lines == [], (
        f"{golden_name} canonical rendering has trailing whitespace on lines "
        f"{trailing_whitespace_lines}"
    )
    expected = (_GOLDEN_DIR / golden_name).read_text(encoding="utf-8")
    if actual != expected:
        diff = "".join(
            difflib.unified_diff(
                expected.splitlines(keepends=True),
                actual.splitlines(keepends=True),
                fromfile=f"golden/{golden_name}",
                tofile="rendered",
            )
        )
        raise AssertionError(
            f"{golden_name} rendered output no longer matches the stored golden file — if this "
            "change is intentional, update agentos_dashboard/tests/e2e/golden/ deliberately.\n"
            f"{diff}"
        )


def test_board_page_matches_its_golden_snapshot(e2e_client: AsgiTestClient) -> None:
    response = e2e_client.get("/board")
    assert response.status == 200
    _assert_matches_golden(response.text, "board.html")


def test_handover_page_matches_its_golden_snapshot(e2e_client: AsgiTestClient) -> None:
    response = e2e_client.get("/handover")
    assert response.status == 200
    _assert_matches_golden(response.text, "handover.html")


def test_golden_snapshots_are_reproducible_across_two_independent_apps(
    e2e_client: AsgiTestClient, e2e_repo: Path
) -> None:
    """A second app instance built over the same fixture repository must render byte-identical
    output — proving the golden match above is not an artifact of one warm cache."""
    from agentos_dashboard.main import create_app
    from agentos_dashboard.settings import DashboardSettings

    settings = DashboardSettings.from_env({"AWED_REPO_ROOT": str(e2e_repo)})
    second_client = AsgiTestClient(create_app(settings))

    first = e2e_client.get("/board")
    second = second_client.get("/board")
    assert first.text == second.text
