from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from PIL import Image

from novachrono.dashboard import render_dashboard
from novachrono.design import PANEL_COUNT, PANEL_SIZE
from novachrono.mail import MailSummary
from novachrono.pokemon_go import RaidRoster
from novachrono.preview import (
    PREVIEW_GAP,
    PREVIEW_MARGIN,
    create_preview,
    save_preview,
)
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


@pytest.fixture
def dashboard(
    mail: MailSummary,
    weather: CurrentWeather,
    raid_roster: RaidRoster,
) -> tuple[Image.Image, ...]:
    return render_dashboard(
        FIXED_TIME,
        mail=mail,
        weather=weather,
        raid_roster=raid_roster,
    )


def test_create_preview_combines_all_panels(
    dashboard: tuple[Image.Image, ...],
) -> None:
    preview = create_preview(dashboard)

    expected_width = PREVIEW_MARGIN * 2 + PANEL_COUNT * PANEL_SIZE + (PANEL_COUNT - 1) * PREVIEW_GAP

    expected_height = PREVIEW_MARGIN * 2 + PANEL_SIZE

    assert preview.mode == "RGB"
    assert preview.size == (
        expected_width,
        expected_height,
    )


def test_create_preview_rejects_wrong_panel_count(
    dashboard: tuple[Image.Image, ...],
) -> None:
    panels = dashboard[:-1]

    with pytest.raises(
        ValueError,
        match=f"Expected {PANEL_COUNT} panels",
    ):
        create_preview(panels)


def test_create_preview_rejects_wrong_panel_size(
    dashboard: tuple[Image.Image, ...],
) -> None:
    panels = list(dashboard)

    panels[2] = Image.new(
        "RGB",
        (64, 64),
    )

    with pytest.raises(
        ValueError,
        match="Panel 2 has size",
    ):
        create_preview(panels)


def test_save_preview_creates_parent_directory_and_png(
    dashboard: tuple[Image.Image, ...],
    tmp_path: Path,
) -> None:
    preview = create_preview(dashboard)

    destination = tmp_path / "nested" / "dashboard-preview.png"

    save_preview(
        preview,
        destination,
    )

    assert destination.is_file()

    with Image.open(destination) as saved_image:
        assert saved_image.format == "PNG"
        assert saved_image.size == preview.size
