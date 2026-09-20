from novachrono.design import PANEL_SIZE
from novachrono.teams import TeamsSummary
from novachrono.widgets.teams import render_teams_panel


def test_render_teams_panel_returns_expected_image_properties() -> None:
    panel = render_teams_panel(TeamsSummary())

    assert panel.size == (PANEL_SIZE, PANEL_SIZE)
    assert panel.mode == "RGB"


def test_render_teams_panel_is_deterministic_for_given_input() -> None:
    teams = TeamsSummary(
        latest_sender="Alice",
        latest_message_preview="Hello",
    )

    first_panel = render_teams_panel(teams)
    second_panel = render_teams_panel(teams)

    assert first_panel.tobytes() == second_panel.tobytes()


def test_render_teams_panel_differs_between_no_activity_and_activity() -> None:
    no_activity_panel = render_teams_panel(TeamsSummary())
    activity_panel = render_teams_panel(
        TeamsSummary(
            latest_sender="Alice",
            latest_message_preview="Hello",
        )
    )

    assert no_activity_panel.tobytes() != activity_panel.tobytes()


def test_render_teams_panel_truncates_long_sender_and_preview() -> None:
    teams = TeamsSummary(
        latest_sender="A" * 200,
        latest_message_preview="B" * 200,
    )

    panel = render_teams_panel(teams)

    assert panel.size == (PANEL_SIZE, PANEL_SIZE)


def test_render_teams_panel_handles_missing_preview() -> None:
    panel = render_teams_panel(TeamsSummary(latest_sender="Alice"))

    assert panel.size == (PANEL_SIZE, PANEL_SIZE)
