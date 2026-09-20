import imaplib
from email.header import decode_header, make_header
from email.parser import BytesHeaderParser
from typing import Final

from novachrono.mail import MailSummary

DEFAULT_TIMEOUT_SECONDS: Final = 8.0


class MailError(RuntimeError):
    """Raised when mail data cannot be retrieved over IMAP."""


def fetch_mail_summary(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    mailbox: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> MailSummary:
    """Retrieve and normalize the unread-mail summary over IMAP."""

    if timeout_seconds <= 0:
        raise ValueError("IMAP timeout must be greater than zero")

    try:
        with imaplib.IMAP4_SSL(host, port, timeout=timeout_seconds) as connection:
            _login(connection, username=username, password=password)
            unread_ids = _search_unread(connection, mailbox=mailbox)
            latest_sender, latest_subject = _fetch_latest_headers(connection, unread_ids)
    except MailError:
        raise
    except (imaplib.IMAP4.error, OSError, TimeoutError) as error:
        raise MailError(f"Could not retrieve mail from {host}: {error}") from error

    return MailSummary(
        unread_count=len(unread_ids),
        latest_sender=latest_sender,
        latest_subject=latest_subject,
    )


def _login(
    connection: imaplib.IMAP4_SSL,
    *,
    username: str,
    password: str,
) -> None:
    status, _ = connection.login(username, password)

    if status != "OK":
        raise MailError(f"IMAP login failed for {username}")


def _search_unread(
    connection: imaplib.IMAP4_SSL,
    *,
    mailbox: str,
) -> tuple[bytes, ...]:
    status, _ = connection.select(mailbox, readonly=True)

    if status != "OK":
        raise MailError(f"Could not open IMAP mailbox: {mailbox}")

    status, data = connection.search(None, "UNSEEN")

    if status != "OK" or not data:
        raise MailError("Could not search for unread mail")

    return tuple(data[0].split())


def _fetch_latest_headers(
    connection: imaplib.IMAP4_SSL,
    unread_ids: tuple[bytes, ...],
) -> tuple[str | None, str | None]:
    if not unread_ids:
        return None, None

    status, data = connection.fetch(
        unread_ids[-1],
        "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])",
    )

    if status != "OK" or not data or not isinstance(data[0], tuple):
        raise MailError("Could not fetch the latest unread message")

    message = BytesHeaderParser().parsebytes(data[0][1])

    return (
        _decode_header_value(message.get("From")),
        _decode_header_value(message.get("Subject")),
    )


def _decode_header_value(value: str | None) -> str | None:
    if value is None:
        return None

    decoded = str(make_header(decode_header(value))).strip()

    return decoded or None
