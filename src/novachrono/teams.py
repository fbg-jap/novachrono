from dataclasses import dataclass


@dataclass(frozen=True)
class TeamsSummary:
    """Normalized latest Microsoft Teams channel message."""

    latest_sender: str | None = None
    latest_message_preview: str | None = None
