from novachrono.design import PANEL_SIZE
from novachrono.mail import MailSummary
from novachrono.widgets.mail import render_mail_panel


def test_render_mail_panel_returns_expected_image_properties() -> None:
    panel = render_mail_panel(MailSummary(unread_count=2))

    assert panel.size == (PANEL_SIZE, PANEL_SIZE)
    assert panel.mode == "RGB"


def test_render_mail_panel_is_deterministic_for_given_input() -> None:
    mail = MailSummary(
        unread_count=3,
        latest_sender="Alice",
        latest_subject="Hello",
    )

    first_panel = render_mail_panel(mail)
    second_panel = render_mail_panel(mail)

    assert first_panel.tobytes() == second_panel.tobytes()


def test_render_mail_panel_differs_between_no_mail_and_unread_mail() -> None:
    no_mail_panel = render_mail_panel(MailSummary(unread_count=0))
    unread_panel = render_mail_panel(
        MailSummary(
            unread_count=1,
            latest_sender="Alice",
            latest_subject="Hello",
        )
    )

    assert no_mail_panel.tobytes() != unread_panel.tobytes()


def test_render_mail_panel_differs_by_unread_count() -> None:
    two_unread = render_mail_panel(MailSummary(unread_count=2))
    five_unread = render_mail_panel(MailSummary(unread_count=5))

    assert two_unread.tobytes() != five_unread.tobytes()


def test_render_mail_panel_caps_displayed_count() -> None:
    panel = render_mail_panel(MailSummary(unread_count=250))

    assert panel.size == (PANEL_SIZE, PANEL_SIZE)


def test_render_mail_panel_truncates_long_sender_and_subject() -> None:
    mail = MailSummary(
        unread_count=1,
        latest_sender="A" * 200,
        latest_subject="B" * 200,
    )

    panel = render_mail_panel(mail)

    assert panel.size == (PANEL_SIZE, PANEL_SIZE)


def test_render_mail_panel_handles_missing_sender_and_subject() -> None:
    panel = render_mail_panel(MailSummary(unread_count=1))

    assert panel.size == (PANEL_SIZE, PANEL_SIZE)


def test_render_mail_panel_differs_by_locale() -> None:
    mail = MailSummary(unread_count=2)

    german_panel = render_mail_panel(mail, locale="de_DE")
    english_panel = render_mail_panel(mail, locale="en_US")

    assert german_panel.tobytes() != english_panel.tobytes()
