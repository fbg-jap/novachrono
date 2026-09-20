from dataclasses import dataclass


@dataclass(frozen=True)
class MailSummary:
    """Normalized unread-mail summary."""

    unread_count: int
    latest_sender: str | None = None
    latest_subject: str | None = None
