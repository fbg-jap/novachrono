import imaplib
from unittest.mock import patch

import pytest

from novachrono.mail import MailSummary
from novachrono.sources.imap_mail import MailError, fetch_mail_summary


class _FakeImap4Ssl:
    def __init__(
        self,
        *,
        login_status: str = "OK",
        select_status: str = "OK",
        search_status: str = "OK",
        search_data: bytes = b"",
        fetch_status: str = "OK",
        fetch_header: bytes | None = None,
    ) -> None:
        self._login_status = login_status
        self._select_status = select_status
        self._search_status = search_status
        self._search_data = search_data
        self._fetch_status = fetch_status
        self._fetch_header = fetch_header

    def login(self, username: str, password: str) -> tuple[str, list[bytes]]:
        return self._login_status, [b"Logged in"]

    def select(self, mailbox: str, readonly: bool = False) -> tuple[str, list[bytes]]:
        return self._select_status, [b"1"]

    def search(self, charset: None, criterion: str) -> tuple[str, list[bytes]]:
        return self._search_status, [self._search_data]

    def fetch(
        self,
        message_id: bytes,
        message_parts: str,
    ) -> tuple[str, list[tuple[bytes, bytes] | None]]:
        if self._fetch_header is None:
            return self._fetch_status, [None]

        return self._fetch_status, [(b"1 (BODY[HEADER])", self._fetch_header)]

    def logout(self) -> tuple[str, list[bytes]]:
        return "BYE", [b"Logging out"]

    def __enter__(self) -> _FakeImap4Ssl:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        self.logout()
        return False


def test_fetch_mail_summary_returns_count_and_latest_message() -> None:
    header = b"From: Alice <alice@example.com>\r\nSubject: Hello there\r\n\r\n"

    with patch("novachrono.sources.imap_mail.imaplib.IMAP4_SSL") as mocked_imap_class:
        mocked_imap_class.return_value = _FakeImap4Ssl(
            search_data=b"1 2 3",
            fetch_header=header,
        )

        summary = fetch_mail_summary(
            host="mail.example.com",
            port=993,
            username="user",
            password="pw",
            mailbox="INBOX",
        )

    assert summary == MailSummary(
        unread_count=3,
        latest_sender="Alice <alice@example.com>",
        latest_subject="Hello there",
    )


def test_fetch_mail_summary_with_no_unread_mail() -> None:
    with patch("novachrono.sources.imap_mail.imaplib.IMAP4_SSL") as mocked_imap_class:
        mocked_imap_class.return_value = _FakeImap4Ssl(search_data=b"")

        summary = fetch_mail_summary(
            host="mail.example.com",
            port=993,
            username="user",
            password="pw",
            mailbox="INBOX",
        )

    assert summary == MailSummary(
        unread_count=0,
        latest_sender=None,
        latest_subject=None,
    )


def test_fetch_mail_summary_decodes_encoded_headers() -> None:
    header = (
        b"From: =?UTF-8?B?TcO8bGxlcg==?= <mueller@example.com>\r\n"
        b"Subject: =?UTF-8?B?SGFsbG8h?=\r\n\r\n"
    )

    with patch("novachrono.sources.imap_mail.imaplib.IMAP4_SSL") as mocked_imap_class:
        mocked_imap_class.return_value = _FakeImap4Ssl(
            search_data=b"1",
            fetch_header=header,
        )

        summary = fetch_mail_summary(
            host="mail.example.com",
            port=993,
            username="user",
            password="pw",
            mailbox="INBOX",
        )

    assert summary.latest_sender == "Müller <mueller@example.com>"
    assert summary.latest_subject == "Hallo!"


def test_fetch_mail_summary_raises_on_login_failure() -> None:
    with patch("novachrono.sources.imap_mail.imaplib.IMAP4_SSL") as mocked_imap_class:
        mocked_imap_class.return_value = _FakeImap4Ssl(login_status="NO")

        with pytest.raises(MailError, match="login failed"):
            fetch_mail_summary(
                host="mail.example.com",
                port=993,
                username="user",
                password="pw",
                mailbox="INBOX",
            )


def test_fetch_mail_summary_raises_on_select_failure() -> None:
    with patch("novachrono.sources.imap_mail.imaplib.IMAP4_SSL") as mocked_imap_class:
        mocked_imap_class.return_value = _FakeImap4Ssl(select_status="NO")

        with pytest.raises(MailError, match="Could not open IMAP mailbox"):
            fetch_mail_summary(
                host="mail.example.com",
                port=993,
                username="user",
                password="pw",
                mailbox="INBOX",
            )


def test_fetch_mail_summary_raises_on_search_failure() -> None:
    with patch("novachrono.sources.imap_mail.imaplib.IMAP4_SSL") as mocked_imap_class:
        mocked_imap_class.return_value = _FakeImap4Ssl(search_status="NO")

        with pytest.raises(MailError, match="Could not search for unread mail"):
            fetch_mail_summary(
                host="mail.example.com",
                port=993,
                username="user",
                password="pw",
                mailbox="INBOX",
            )


def test_fetch_mail_summary_raises_on_fetch_failure() -> None:
    with patch("novachrono.sources.imap_mail.imaplib.IMAP4_SSL") as mocked_imap_class:
        mocked_imap_class.return_value = _FakeImap4Ssl(
            search_data=b"1",
            fetch_status="NO",
        )

        with pytest.raises(MailError, match="Could not fetch the latest unread message"):
            fetch_mail_summary(
                host="mail.example.com",
                port=993,
                username="user",
                password="pw",
                mailbox="INBOX",
            )


def test_fetch_mail_summary_wraps_connection_errors() -> None:
    with patch("novachrono.sources.imap_mail.imaplib.IMAP4_SSL") as mocked_imap_class:
        mocked_imap_class.side_effect = OSError("Connection refused")

        with pytest.raises(MailError, match="Could not retrieve mail from"):
            fetch_mail_summary(
                host="mail.example.com",
                port=993,
                username="user",
                password="pw",
                mailbox="INBOX",
            )


def test_fetch_mail_summary_wraps_imap_errors() -> None:
    with patch("novachrono.sources.imap_mail.imaplib.IMAP4_SSL") as mocked_imap_class:
        mocked_imap_class.side_effect = imaplib.IMAP4.error("boom")

        with pytest.raises(MailError, match="Could not retrieve mail from"):
            fetch_mail_summary(
                host="mail.example.com",
                port=993,
                username="user",
                password="pw",
                mailbox="INBOX",
            )


def test_fetch_mail_summary_rejects_non_positive_timeout() -> None:
    with pytest.raises(ValueError, match="IMAP timeout must be greater than zero"):
        fetch_mail_summary(
            host="mail.example.com",
            port=993,
            username="user",
            password="pw",
            mailbox="INBOX",
            timeout_seconds=0,
        )
