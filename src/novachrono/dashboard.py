from collections.abc import Mapping, Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from novachrono.config import DEFAULT_DISPLAY_ORDER, DEFAULT_TIMEZONE_NAME
from novachrono.design import (
    FRAME_ACCENT_COLOR,
    PANEL_COUNT,
    create_panel,
    draw_placeholder_header,
)
from novachrono.i18n import DEFAULT_LOCALE
from novachrono.mail import MailSummary
from novachrono.pokemon_go import RaidRoster
from novachrono.teams import TeamsSummary
from novachrono.units import TemperatureUnit
from novachrono.weather import CurrentWeather
from novachrono.widgets.clock import render_clock_panel
from novachrono.widgets.mail import render_mail_panel
from novachrono.widgets.pokemon_go import render_raid_panel
from novachrono.widgets.teams import render_teams_panel
from novachrono.widgets.weather import render_weather_panel

DEFAULT_TIMEZONE = ZoneInfo(DEFAULT_TIMEZONE_NAME)

MAIL_PANEL_INDEX = DEFAULT_DISPLAY_ORDER.index("mail")
WEATHER_PANEL_INDEX = DEFAULT_DISPLAY_ORDER.index("weather")
CLOCK_PANEL_INDEX = DEFAULT_DISPLAY_ORDER.index("clock")
POKEMON_GO_PANEL_INDEX = DEFAULT_DISPLAY_ORDER.index("pokemon_go")
TEAMS_PANEL_INDEX = DEFAULT_DISPLAY_ORDER.index("teams")


def panel_index_for(
    widget_name: str,
    *,
    display_order: Sequence[str] = DEFAULT_DISPLAY_ORDER,
) -> int:
    """Return the physical panel index currently assigned to a widget."""

    return tuple(display_order).index(widget_name)


def render_panel(index: int) -> Image.Image:
    """Render one static placeholder panel."""

    if not 0 <= index < PANEL_COUNT:
        raise ValueError(f"Panel index must be between 0 and {PANEL_COUNT - 1}")

    image = create_panel()
    draw = ImageDraw.Draw(image)

    draw_placeholder_header(
        draw,
        accent_color=FRAME_ACCENT_COLOR,
    )

    return image


def render_dashboard(
    now: datetime | None = None,
    *,
    mail: MailSummary,
    weather: CurrentWeather,
    raid_roster: RaidRoster,
    teams: TeamsSummary,
    raid_artwork: Mapping[str, Image.Image] | None = None,
    timezone: ZoneInfo = DEFAULT_TIMEZONE,
    locale: str = DEFAULT_LOCALE,
    temperature_unit: TemperatureUnit = TemperatureUnit.CELSIUS,
    display_order: Sequence[str] = DEFAULT_DISPLAY_ORDER,
) -> tuple[Image.Image, ...]:
    """Render all Times Gate panels, arranged according to ``display_order``."""

    current_time = now if now is not None else datetime.now(timezone)

    widget_panels = {
        "mail": render_mail_panel(
            mail,
            locale=locale,
        ),
        "weather": render_weather_panel(
            weather,
            locale=locale,
            temperature_unit=temperature_unit,
        ),
        "clock": render_clock_panel(current_time),
        "pokemon_go": render_raid_panel(
            raid_roster,
            artwork_by_url=raid_artwork,
        ),
        "teams": render_teams_panel(teams),
    }

    return tuple(widget_panels[name] for name in display_order)
