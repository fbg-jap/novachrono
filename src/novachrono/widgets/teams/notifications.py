from typing import Final

from PIL import Image, ImageDraw, ImageFont
from PIL.ImageFont import BaseImageFont

from novachrono.design import (
    CONTENT_LEFT,
    CONTENT_RIGHT,
    FRAME_ACCENT_COLOR,
    FRAME_DIM_COLOR,
    MUTED_TEXT_COLOR,
    PANEL_SIZE,
    TEXT_COLOR,
    create_panel,
    draw_centered_text,
    draw_widget_header,
    text_width,
)
from novachrono.teams import TeamsSummary

TEAMS_TITLE: Final = "TEAMS"

BUBBLE_SIZE: Final = 30
BUBBLE_TOP: Final = 36
BUBBLE_LEFT: Final = (PANEL_SIZE - BUBBLE_SIZE) // 2

DETAIL_SEPARATOR_Y: Final = 74
SENDER_Y: Final = 80
PREVIEW_Y: Final = 96
BOTTOM_ACCENT_Y: Final = 104

ELLIPSIS: Final = "…"


def render_teams_panel(
    teams: TeamsSummary,
) -> Image.Image:
    """Render the latest Microsoft Teams channel activity."""

    image = create_panel()
    draw = ImageDraw.Draw(image)

    draw_widget_header(
        draw,
        title=TEAMS_TITLE,
        font_size=10,
    )

    _draw_chat_bubble_icon(
        draw,
        left=BUBBLE_LEFT,
        top=BUBBLE_TOP,
        size=BUBBLE_SIZE,
    )

    _draw_detail_separator(draw)

    if teams.latest_sender is not None or teams.latest_message_preview is not None:
        _draw_latest_message(draw, teams)
    else:
        _draw_no_activity_state(draw)

    _draw_bottom_accent(draw)

    return image


def _draw_chat_bubble_icon(
    draw: ImageDraw.ImageDraw,
    *,
    left: int,
    top: int,
    size: int,
) -> None:
    """Draw a simple chat-bubble icon."""

    right = left + size - 1
    bottom = top + size - 8

    draw.rounded_rectangle(
        (left, top, right, bottom),
        radius=6,
        outline=FRAME_ACCENT_COLOR,
        width=2,
    )

    tail_left = left + 6

    draw.polygon(
        (
            (tail_left, bottom - 1),
            (tail_left + 6, bottom - 1),
            (tail_left, bottom + 6),
        ),
        fill=FRAME_ACCENT_COLOR,
    )

    dot_y = top + (bottom - top) // 2
    dot_radius = 2
    center_x = left + size // 2

    for offset_x in (-8, 0, 8):
        dot_center_x = center_x + offset_x

        draw.ellipse(
            (
                dot_center_x - dot_radius,
                dot_y - dot_radius,
                dot_center_x + dot_radius,
                dot_y + dot_radius,
            ),
            fill=FRAME_ACCENT_COLOR,
        )


def _draw_detail_separator(
    draw: ImageDraw.ImageDraw,
) -> None:
    """Draw the separator between the chat bubble and the latest message."""

    draw.line(
        (17, DETAIL_SEPARATOR_Y, 111, DETAIL_SEPARATOR_Y),
        fill=FRAME_DIM_COLOR,
        width=1,
    )

    draw.line(
        (46, DETAIL_SEPARATOR_Y, 82, DETAIL_SEPARATOR_Y),
        fill=FRAME_ACCENT_COLOR,
        width=1,
    )


def _draw_latest_message(
    draw: ImageDraw.ImageDraw,
    teams: TeamsSummary,
) -> None:
    """Draw the latest channel message's sender and preview."""

    sender_font = ImageFont.load_default(size=11)
    preview_font = ImageFont.load_default(size=9)

    available_width = CONTENT_RIGHT - CONTENT_LEFT

    sender_text = _truncate_to_width(
        draw,
        text=teams.latest_sender or "",
        font=sender_font,
        maximum_width=available_width,
    )

    preview_text = _truncate_to_width(
        draw,
        text=teams.latest_message_preview or "",
        font=preview_font,
        maximum_width=available_width,
    )

    draw.text(
        (CONTENT_LEFT, SENDER_Y),
        sender_text,
        font=sender_font,
        fill=TEXT_COLOR,
    )

    draw.text(
        (CONTENT_LEFT, PREVIEW_Y),
        preview_text,
        font=preview_font,
        fill=MUTED_TEXT_COLOR,
    )


def _draw_no_activity_state(
    draw: ImageDraw.ImageDraw,
) -> None:
    draw_centered_text(
        draw,
        y=86,
        text="NO RECENT MESSAGES",
        font=ImageFont.load_default(size=8),
        fill=FRAME_DIM_COLOR,
    )


def _draw_bottom_accent(
    draw: ImageDraw.ImageDraw,
) -> None:
    draw.line(
        (24, BOTTOM_ACCENT_Y, 104, BOTTOM_ACCENT_Y),
        fill=FRAME_DIM_COLOR,
        width=1,
    )

    draw.line(
        (54, BOTTOM_ACCENT_Y, 74, BOTTOM_ACCENT_Y),
        fill=FRAME_ACCENT_COLOR,
        width=1,
    )


def _truncate_to_width(
    draw: ImageDraw.ImageDraw,
    *,
    text: str,
    font: BaseImageFont,
    maximum_width: int,
) -> str:
    """Truncate text with an ellipsis so it fits within the given width."""

    if text_width(draw, text=text, font=font) <= maximum_width:
        return text

    truncated = text

    while truncated and text_width(draw, text=truncated + ELLIPSIS, font=font) > maximum_width:
        truncated = truncated[:-1]

    return f"{truncated}{ELLIPSIS}" if truncated else ELLIPSIS
