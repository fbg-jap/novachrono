from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from PIL import Image

from novachrono.dashboard import (
    CLOCK_PANEL_INDEX,
    MAIL_PANEL_INDEX,
    POKEMON_GO_PANEL_INDEX,
    TEAMS_PANEL_INDEX,
    WEATHER_PANEL_INDEX,
    render_dashboard,
    render_panel,
)
from novachrono.design import PANEL_COUNT, PANEL_SIZE
from novachrono.mail import MailSummary
from novachrono.pokemon_go import RaidRoster
from novachrono.teams import TeamsSummary
from novachrono.units import TemperatureUnit
from novachrono.weather import CurrentWeather

BERLIN = ZoneInfo("Europe/Berlin")

FIXED_TIME = datetime(
    2026,
    8,
    6,
    12,
    54,
    tzinfo=BERLIN,
)


def test_current_widgets_have_expected_positions() -> None:
    assert MAIL_PANEL_INDEX == 0
    assert WEATHER_PANEL_INDEX == 1
    assert CLOCK_PANEL_INDEX == 2
    assert POKEMON_GO_PANEL_INDEX == 3
    assert TEAMS_PANEL_INDEX == 4


def test_render_dashboard_returns_expected_panels(
    mail: MailSummary,
    weather: CurrentWeather,
    raid_roster: RaidRoster,
    teams: TeamsSummary,
) -> None:
    panels = render_dashboard(
        FIXED_TIME,
        mail=mail,
        weather=weather,
        raid_roster=raid_roster,
        teams=teams,
    )

    assert isinstance(panels, tuple)
    assert len(panels) == PANEL_COUNT

    for panel in panels:
        assert isinstance(panel, Image.Image)
        assert panel.size == (
            PANEL_SIZE,
            PANEL_SIZE,
        )
        assert panel.mode == "RGB"


@pytest.mark.parametrize(
    "index",
    [
        -1,
        PANEL_COUNT,
    ],
)
def test_render_panel_rejects_invalid_index(
    index: int,
) -> None:
    with pytest.raises(
        ValueError,
        match="Panel index must be between",
    ):
        render_panel(index)


@pytest.mark.parametrize(
    "panel_index",
    [
        MAIL_PANEL_INDEX,
        WEATHER_PANEL_INDEX,
        CLOCK_PANEL_INDEX,
        POKEMON_GO_PANEL_INDEX,
        TEAMS_PANEL_INDEX,
    ],
)
def test_dashboard_renders_widgets_on_configured_panels(
    mail: MailSummary,
    weather: CurrentWeather,
    raid_roster: RaidRoster,
    teams: TeamsSummary,
    panel_index: int,
) -> None:
    panels = render_dashboard(
        FIXED_TIME,
        mail=mail,
        weather=weather,
        raid_roster=raid_roster,
        teams=teams,
    )

    assert panels[panel_index].tobytes() != render_panel(panel_index).tobytes()


def test_dashboard_passes_artwork_to_pokemon_renderer(
    mail: MailSummary,
    weather: CurrentWeather,
    raid_roster: RaidRoster,
    teams: TeamsSummary,
) -> None:
    raid_artwork = {
        "https://example.com/artwork.png": Image.new(
            mode="RGBA",
            size=(1, 1),
        ),
    }

    with patch("novachrono.dashboard.render_raid_panel") as mocked_renderer:
        mocked_renderer.return_value = Image.new(
            mode="RGB",
            size=(PANEL_SIZE, PANEL_SIZE),
        )

        render_dashboard(
            FIXED_TIME,
            mail=mail,
            weather=weather,
            raid_roster=raid_roster,
            teams=teams,
            raid_artwork=raid_artwork,
        )

    mocked_renderer.assert_called_once_with(
        raid_roster,
        artwork_by_url=raid_artwork,
    )


def test_dashboard_is_deterministic_for_given_input(
    mail: MailSummary,
    weather: CurrentWeather,
    raid_roster: RaidRoster,
    teams: TeamsSummary,
) -> None:
    first_dashboard = render_dashboard(
        FIXED_TIME,
        mail=mail,
        weather=weather,
        raid_roster=raid_roster,
        teams=teams,
    )

    second_dashboard = render_dashboard(
        FIXED_TIME,
        mail=mail,
        weather=weather,
        raid_roster=raid_roster,
        teams=teams,
    )

    for first_panel, second_panel in zip(
        first_dashboard,
        second_dashboard,
        strict=True,
    ):
        assert first_panel.tobytes() == second_panel.tobytes()


def test_temperature_unit_changes_only_weather_panel(
    mail: MailSummary,
    weather: CurrentWeather,
    raid_roster: RaidRoster,
    teams: TeamsSummary,
) -> None:
    celsius_dashboard = render_dashboard(
        FIXED_TIME,
        mail=mail,
        weather=weather,
        raid_roster=raid_roster,
        teams=teams,
        temperature_unit=TemperatureUnit.CELSIUS,
    )

    fahrenheit_dashboard = render_dashboard(
        FIXED_TIME,
        mail=mail,
        weather=weather,
        raid_roster=raid_roster,
        teams=teams,
        temperature_unit=TemperatureUnit.FAHRENHEIT,
    )

    assert (
        celsius_dashboard[WEATHER_PANEL_INDEX].tobytes()
        != fahrenheit_dashboard[WEATHER_PANEL_INDEX].tobytes()
    )

    assert (
        celsius_dashboard[MAIL_PANEL_INDEX].tobytes()
        == fahrenheit_dashboard[MAIL_PANEL_INDEX].tobytes()
    )

    assert (
        celsius_dashboard[CLOCK_PANEL_INDEX].tobytes()
        == fahrenheit_dashboard[CLOCK_PANEL_INDEX].tobytes()
    )

    assert (
        celsius_dashboard[POKEMON_GO_PANEL_INDEX].tobytes()
        == fahrenheit_dashboard[POKEMON_GO_PANEL_INDEX].tobytes()
    )

    assert (
        celsius_dashboard[TEAMS_PANEL_INDEX].tobytes()
        == fahrenheit_dashboard[TEAMS_PANEL_INDEX].tobytes()
    )


def test_locale_changes_weather_and_mail_panels(
    mail: MailSummary,
    weather: CurrentWeather,
    raid_roster: RaidRoster,
    teams: TeamsSummary,
) -> None:
    german_dashboard = render_dashboard(
        FIXED_TIME,
        mail=mail,
        weather=weather,
        raid_roster=raid_roster,
        teams=teams,
        locale="de_DE",
    )

    english_dashboard = render_dashboard(
        FIXED_TIME,
        mail=mail,
        weather=weather,
        raid_roster=raid_roster,
        teams=teams,
        locale="en_US",
    )

    assert (
        german_dashboard[WEATHER_PANEL_INDEX].tobytes()
        != english_dashboard[WEATHER_PANEL_INDEX].tobytes()
    )

    assert (
        german_dashboard[MAIL_PANEL_INDEX].tobytes()
        != english_dashboard[MAIL_PANEL_INDEX].tobytes()
    )

    assert (
        german_dashboard[CLOCK_PANEL_INDEX].tobytes()
        == english_dashboard[CLOCK_PANEL_INDEX].tobytes()
    )

    assert (
        german_dashboard[POKEMON_GO_PANEL_INDEX].tobytes()
        == english_dashboard[POKEMON_GO_PANEL_INDEX].tobytes()
    )

    assert (
        german_dashboard[TEAMS_PANEL_INDEX].tobytes()
        == english_dashboard[TEAMS_PANEL_INDEX].tobytes()
    )


def test_mail_changes_only_mail_panel(
    weather: CurrentWeather,
    raid_roster: RaidRoster,
    teams: TeamsSummary,
) -> None:
    unread_dashboard = render_dashboard(
        FIXED_TIME,
        mail=MailSummary(
            unread_count=3,
            latest_sender="Alice",
            latest_subject="Hello",
        ),
        weather=weather,
        raid_roster=raid_roster,
        teams=teams,
    )

    no_mail_dashboard = render_dashboard(
        FIXED_TIME,
        mail=MailSummary(unread_count=0),
        weather=weather,
        raid_roster=raid_roster,
        teams=teams,
    )

    assert (
        unread_dashboard[MAIL_PANEL_INDEX].tobytes()
        != no_mail_dashboard[MAIL_PANEL_INDEX].tobytes()
    )

    assert (
        unread_dashboard[WEATHER_PANEL_INDEX].tobytes()
        == no_mail_dashboard[WEATHER_PANEL_INDEX].tobytes()
    )

    assert (
        unread_dashboard[CLOCK_PANEL_INDEX].tobytes()
        == no_mail_dashboard[CLOCK_PANEL_INDEX].tobytes()
    )

    assert (
        unread_dashboard[POKEMON_GO_PANEL_INDEX].tobytes()
        == no_mail_dashboard[POKEMON_GO_PANEL_INDEX].tobytes()
    )

    assert (
        unread_dashboard[TEAMS_PANEL_INDEX].tobytes()
        == no_mail_dashboard[TEAMS_PANEL_INDEX].tobytes()
    )


def test_teams_changes_only_teams_panel(
    mail: MailSummary,
    weather: CurrentWeather,
    raid_roster: RaidRoster,
) -> None:
    active_dashboard = render_dashboard(
        FIXED_TIME,
        mail=mail,
        weather=weather,
        raid_roster=raid_roster,
        teams=TeamsSummary(
            latest_sender="Alice",
            latest_message_preview="Hello",
        ),
    )

    no_activity_dashboard = render_dashboard(
        FIXED_TIME,
        mail=mail,
        weather=weather,
        raid_roster=raid_roster,
        teams=TeamsSummary(),
    )

    assert (
        active_dashboard[TEAMS_PANEL_INDEX].tobytes()
        != no_activity_dashboard[TEAMS_PANEL_INDEX].tobytes()
    )

    assert (
        active_dashboard[MAIL_PANEL_INDEX].tobytes()
        == no_activity_dashboard[MAIL_PANEL_INDEX].tobytes()
    )

    assert (
        active_dashboard[WEATHER_PANEL_INDEX].tobytes()
        == no_activity_dashboard[WEATHER_PANEL_INDEX].tobytes()
    )

    assert (
        active_dashboard[CLOCK_PANEL_INDEX].tobytes()
        == no_activity_dashboard[CLOCK_PANEL_INDEX].tobytes()
    )

    assert (
        active_dashboard[POKEMON_GO_PANEL_INDEX].tobytes()
        == no_activity_dashboard[POKEMON_GO_PANEL_INDEX].tobytes()
    )
