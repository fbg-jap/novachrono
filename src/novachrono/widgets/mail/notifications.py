from typing import Final

from PIL import Image, ImageDraw, ImageFont
from PIL.ImageFont import BaseImageFont

from novachrono.design import (
    CONTENT_LEFT,
    CONTENT_RIGHT,
    FRAME_ACCENT_COLOR,
    FRAME_DIM_COLOR,
    MUTED_TEXT_COLOR,
    TEXT_COLOR,
    create_panel,
    draw_centered_text,
    draw_widget_header,
    find_font_that_fits,
    text_width,
)
from novachrono.i18n import DEFAULT_LOCALE, translate
from novachrono.mail import MailSummary

MAIL_ICON_ORIGIN: Final = (16, 34)
MAIL_ICON_SIZE: Final = 32
ENVELOPE_TOP_INSET: Final = 6

COUNT_REGION_LEFT: Final = 55
COUNT_REGION_RIGHT: Final = 113
COUNT_REGION_Y: Final = 36
MAX_DISPLAYED_COUNT: Final = 99

DETAIL_SEPARATOR_Y: Final = 74
SENDER_Y: Final = 80
SUBJECT_Y: Final = 96
BOTTOM_ACCENT_Y: Final = 104

ELLIPSIS: Final = "…"


def render_mail_panel(
    mail: MailSummary,
    *,
    locale: str = DEFAULT_LOCALE,
) -> Image.Image:
    """Render the current unread-mail summary."""

    image = create_panel()
    draw = ImageDraw.Draw(image)

    draw_widget_header(
        draw,
        title=translate(
            "mail.title",
            locale=locale,
        ),
        font_size=10,
    )

    _draw_envelope_icon(
        draw,
        origin=MAIL_ICON_ORIGIN,
        size=MAIL_ICON_SIZE,
    )

    _draw_unread_count(draw, mail.unread_count)

    _draw_detail_separator(draw)

    if mail.unread_count > 0:
        _draw_latest_message(draw, mail)
    else:
        _draw_no_mail_state(draw)

    _draw_bottom_accent(draw)

    return image


def _draw_envelope_icon(
    draw: ImageDraw.ImageDraw,
    *,
    origin: tuple[int, int],
    size: int,
) -> None:
    """Draw a simple envelope icon."""

    left, top = origin
    envelope_top = top + ENVELOPE_TOP_INSET
    right = left + size - 1
    bottom = top + size - 1
    center_x = left + size // 2
    flap_bottom = envelope_top + (bottom - envelope_top) // 2

    draw.rounded_rectangle(
        (left, envelope_top, right, bottom),
        radius=3,
        outline=FRAME_ACCENT_COLOR,
        width=2,
    )

    draw.line(
        (
            left + 2,
            envelope_top + 2,
            center_x,
            flap_bottom,
            right - 2,
            envelope_top + 2,
        ),
        fill=FRAME_ACCENT_COLOR,
        width=2,
    )


def _draw_unread_count(
    draw: ImageDraw.ImageDraw,
    unread_count: int,
) -> None:
    text = str(unread_count) if unread_count <= MAX_DISPLAYED_COUNT else f"{MAX_DISPLAYED_COUNT}+"

    font = find_font_that_fits(
        draw,
        text=text,
        maximum_width=COUNT_REGION_RIGHT - COUNT_REGION_LEFT,
        font_sizes=(31, 29, 27, 25, 23, 21, 19),
    )

    _draw_centered_in_region(
        draw,
        left=COUNT_REGION_LEFT,
        right=COUNT_REGION_RIGHT,
        y=COUNT_REGION_Y,
        text=text,
        font=font,
        fill=TEXT_COLOR,
    )


def _draw_detail_separator(
    draw: ImageDraw.ImageDraw,
) -> None:
    """Draw the separator between the unread count and the latest message."""

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
    mail: MailSummary,
) -> None:
    """Draw the latest unread message's sender and subject."""

    sender_font = ImageFont.load_default(size=11)
    subject_font = ImageFont.load_default(size=9)

    available_width = CONTENT_RIGHT - CONTENT_LEFT

    sender_text = _truncate_to_width(
        draw,
        text=mail.latest_sender or "",
        font=sender_font,
        maximum_width=available_width,
    )

    subject_text = _truncate_to_width(
        draw,
        text=mail.latest_subject or "",
        font=subject_font,
        maximum_width=available_width,
    )

    draw.text(
        (CONTENT_LEFT, SENDER_Y),
        sender_text,
        font=sender_font,
        fill=TEXT_COLOR,
    )

    draw.text(
        (CONTENT_LEFT, SUBJECT_Y),
        subject_text,
        font=subject_font,
        fill=MUTED_TEXT_COLOR,
    )


def _draw_no_mail_state(
    draw: ImageDraw.ImageDraw,
) -> None:
    draw_centered_text(
        draw,
        y=86,
        text="NO NEW MAIL",
        font=ImageFont.load_default(size=10),
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


def _draw_centered_in_region(
    draw: ImageDraw.ImageDraw,
    *,
    left: int,
    right: int,
    y: int,
    text: str,
    font: BaseImageFont,
    fill: str,
) -> None:
    """Draw text horizontally centered inside a region."""

    bounding_box = draw.textbbox(
        (0, 0),
        text,
        font=font,
    )

    rendered_text_width = bounding_box[2] - bounding_box[0]
    region_width = right - left

    x = left + (region_width - rendered_text_width) // 2 - bounding_box[0]

    draw.text(
        (x, y),
        text,
        font=font,
        fill=fill,
    )
