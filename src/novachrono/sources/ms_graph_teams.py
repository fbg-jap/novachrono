import html
import json
import re
from typing import Any, Final
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import msal

from novachrono.teams import TeamsSummary

GRAPH_API_BASE_URL: Final = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE: Final = "https://graph.microsoft.com/.default"
DEFAULT_TIMEOUT_SECONDS: Final = 8.0
MESSAGE_PAGE_SIZE: Final = 50

_HTML_TAG_PATTERN: Final = re.compile(r"<[^>]+>")


class TeamsError(RuntimeError):
    """Raised when Teams data cannot be retrieved from Microsoft Graph."""


def fetch_teams_summary(
    *,
    tenant_id: str,
    client_id: str,
    client_secret: str,
    team_id: str,
    channel_id: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> TeamsSummary:
    """Retrieve and normalize the latest Microsoft Teams channel message."""

    if timeout_seconds <= 0:
        raise ValueError("Microsoft Graph timeout must be greater than zero")

    access_token = _acquire_access_token(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
    )

    messages = _fetch_channel_messages(
        access_token=access_token,
        team_id=team_id,
        channel_id=channel_id,
        timeout_seconds=timeout_seconds,
    )

    return _summarize_latest_message(messages)


def _acquire_access_token(
    *,
    tenant_id: str,
    client_id: str,
    client_secret: str,
) -> str:
    application = msal.ConfidentialClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        client_credential=client_secret,
    )

    result = application.acquire_token_for_client(scopes=[GRAPH_SCOPE])

    access_token = result.get("access_token")

    if not isinstance(access_token, str) or not access_token:
        description = result.get("error_description") or result.get("error") or "unknown error"
        raise TeamsError(f"Could not authenticate with Microsoft Graph: {description}")

    return access_token


def _fetch_channel_messages(
    *,
    access_token: str,
    team_id: str,
    channel_id: str,
    timeout_seconds: float,
) -> list[Any]:
    url = (
        f"{GRAPH_API_BASE_URL}/teams/{team_id}/channels/{channel_id}/messages"
        f"?$top={MESSAGE_PAGE_SIZE}"
    )

    request = Request(
        url=url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        },
        method="GET",
    )

    try:
        with urlopen(  # nosec B310 - fixed Microsoft Graph HTTPS endpoint
            request,
            timeout=timeout_seconds,
        ) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as error:
        raise TeamsError(_format_http_error(error)) from error
    except URLError as error:
        raise TeamsError(f"Could not reach Microsoft Graph: {error.reason}") from error
    except TimeoutError as error:
        raise TeamsError("Connection to Microsoft Graph timed out") from error
    except UnicodeDecodeError as error:
        raise TeamsError("Microsoft Graph returned an invalid UTF-8 response") from error

    try:
        response_data = json.loads(response_body)
    except json.JSONDecodeError as error:
        raise TeamsError("Microsoft Graph returned invalid JSON") from error

    if not isinstance(response_data, dict):
        raise TeamsError("Microsoft Graph returned an unexpected response")

    messages = response_data.get("value")

    if not isinstance(messages, list):
        raise TeamsError("Microsoft Graph response is missing 'value'")

    return messages


def _summarize_latest_message(messages: list[Any]) -> TeamsSummary:
    active_messages = [
        message
        for message in messages
        if isinstance(message, dict) and message.get("deletedDateTime") is None
    ]

    if not active_messages:
        return TeamsSummary()

    latest_message = max(
        active_messages,
        key=lambda message: message.get("createdDateTime") or "",
    )

    return TeamsSummary(
        latest_sender=_extract_sender(latest_message),
        latest_message_preview=_extract_preview(latest_message),
    )


def _extract_sender(message: dict[str, Any]) -> str | None:
    sender = message.get("from")

    if not isinstance(sender, dict):
        return None

    for participant_key in ("user", "application"):
        participant = sender.get(participant_key)

        if isinstance(participant, dict):
            display_name = participant.get("displayName")

            if isinstance(display_name, str) and display_name.strip():
                return display_name.strip()

    return None


def _extract_preview(message: dict[str, Any]) -> str | None:
    body = message.get("body")

    if not isinstance(body, dict):
        return None

    content = body.get("content")

    if not isinstance(content, str):
        return None

    plain_text = _strip_html(content).strip()

    return plain_text or None


def _strip_html(content: str) -> str:
    without_tags = _HTML_TAG_PATTERN.sub(" ", content)

    return html.unescape(" ".join(without_tags.split()))


def _format_http_error(error: HTTPError) -> str:
    try:
        response_body = error.read().decode("utf-8")
        response_data = json.loads(response_body)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        response_data = None

    if isinstance(response_data, dict):
        error_info = response_data.get("error")

        if isinstance(error_info, dict):
            message = error_info.get("message")

            if isinstance(message, str) and message:
                return f"Microsoft Graph returned HTTP {error.code}: {message}"

    return f"Microsoft Graph returned HTTP {error.code}: {error.reason}"
