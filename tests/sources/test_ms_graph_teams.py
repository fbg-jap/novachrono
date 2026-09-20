import json
from typing import Any
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

from novachrono.sources.ms_graph_teams import TeamsError, fetch_teams_summary
from novachrono.teams import TeamsSummary

_VALID_TOKEN_RESULT = {"access_token": "test-token"}


def _messages_response(messages: list[dict[str, Any]]) -> MagicMock:
    response = MagicMock()
    response.read.return_value = json.dumps({"value": messages}).encode("utf-8")
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


def _message(
    *,
    sender: str | None = "Alice",
    subject_content: str | None = "<p>Hello <b>there</b></p>",
    created_at: str = "2026-01-01T10:00:00Z",
    deleted: bool = False,
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "createdDateTime": created_at,
        "deletedDateTime": "2026-01-02T10:00:00Z" if deleted else None,
    }

    if sender is not None:
        message["from"] = {"user": {"displayName": sender}}

    if subject_content is not None:
        message["body"] = {"contentType": "html", "content": subject_content}

    return message


@patch("novachrono.sources.ms_graph_teams.urlopen")
@patch("novachrono.sources.ms_graph_teams.msal.ConfidentialClientApplication")
def test_fetch_teams_summary_returns_latest_message(
    mocked_app_class: MagicMock,
    mocked_urlopen: MagicMock,
) -> None:
    mocked_app_class.return_value.acquire_token_for_client.return_value = _VALID_TOKEN_RESULT
    mocked_urlopen.return_value = _messages_response(
        [
            _message(
                sender="Alice",
                subject_content="<p>Older message</p>",
                created_at="2026-01-01T09:00:00Z",
            ),
            _message(
                sender="Bob",
                subject_content="<p>Newer message</p>",
                created_at="2026-01-01T10:00:00Z",
            ),
        ]
    )

    summary = fetch_teams_summary(
        tenant_id="tenant",
        client_id="client",
        client_secret="secret",
        team_id="team",
        channel_id="channel",
    )

    assert summary == TeamsSummary(
        latest_sender="Bob",
        latest_message_preview="Newer message",
    )


@patch("novachrono.sources.ms_graph_teams.urlopen")
@patch("novachrono.sources.ms_graph_teams.msal.ConfidentialClientApplication")
def test_fetch_teams_summary_ignores_deleted_messages(
    mocked_app_class: MagicMock,
    mocked_urlopen: MagicMock,
) -> None:
    mocked_app_class.return_value.acquire_token_for_client.return_value = _VALID_TOKEN_RESULT
    mocked_urlopen.return_value = _messages_response(
        [
            _message(
                sender="Bob",
                subject_content="<p>Deleted</p>",
                created_at="2026-01-01T11:00:00Z",
                deleted=True,
            ),
            _message(
                sender="Alice",
                subject_content="<p>Still here</p>",
                created_at="2026-01-01T09:00:00Z",
            ),
        ]
    )

    summary = fetch_teams_summary(
        tenant_id="tenant",
        client_id="client",
        client_secret="secret",
        team_id="team",
        channel_id="channel",
    )

    assert summary.latest_sender == "Alice"
    assert summary.latest_message_preview == "Still here"


@patch("novachrono.sources.ms_graph_teams.urlopen")
@patch("novachrono.sources.ms_graph_teams.msal.ConfidentialClientApplication")
def test_fetch_teams_summary_with_no_messages(
    mocked_app_class: MagicMock,
    mocked_urlopen: MagicMock,
) -> None:
    mocked_app_class.return_value.acquire_token_for_client.return_value = _VALID_TOKEN_RESULT
    mocked_urlopen.return_value = _messages_response([])

    summary = fetch_teams_summary(
        tenant_id="tenant",
        client_id="client",
        client_secret="secret",
        team_id="team",
        channel_id="channel",
    )

    assert summary == TeamsSummary()


@patch("novachrono.sources.ms_graph_teams.msal.ConfidentialClientApplication")
def test_fetch_teams_summary_raises_on_authentication_failure(
    mocked_app_class: MagicMock,
) -> None:
    mocked_app_class.return_value.acquire_token_for_client.return_value = {
        "error": "invalid_client",
        "error_description": "Invalid client secret",
    }

    with pytest.raises(TeamsError, match="Could not authenticate with Microsoft Graph"):
        fetch_teams_summary(
            tenant_id="tenant",
            client_id="client",
            client_secret="wrong-secret",
            team_id="team",
            channel_id="channel",
        )


@patch("novachrono.sources.ms_graph_teams.urlopen")
@patch("novachrono.sources.ms_graph_teams.msal.ConfidentialClientApplication")
def test_fetch_teams_summary_wraps_http_errors(
    mocked_app_class: MagicMock,
    mocked_urlopen: MagicMock,
) -> None:
    mocked_app_class.return_value.acquire_token_for_client.return_value = _VALID_TOKEN_RESULT

    error_body = json.dumps({"error": {"message": "Forbidden"}}).encode("utf-8")
    http_error = HTTPError(
        url="https://graph.microsoft.com",
        code=403,
        msg="Forbidden",
        hdrs=None,
        fp=None,
    )
    http_error.read = lambda: error_body  # type: ignore[method-assign]
    mocked_urlopen.side_effect = http_error

    with pytest.raises(TeamsError, match="Microsoft Graph returned HTTP 403: Forbidden"):
        fetch_teams_summary(
            tenant_id="tenant",
            client_id="client",
            client_secret="secret",
            team_id="team",
            channel_id="channel",
        )


@patch("novachrono.sources.ms_graph_teams.urlopen")
@patch("novachrono.sources.ms_graph_teams.msal.ConfidentialClientApplication")
def test_fetch_teams_summary_wraps_connection_errors(
    mocked_app_class: MagicMock,
    mocked_urlopen: MagicMock,
) -> None:
    mocked_app_class.return_value.acquire_token_for_client.return_value = _VALID_TOKEN_RESULT
    mocked_urlopen.side_effect = URLError("Connection refused")

    with pytest.raises(TeamsError, match="Could not reach Microsoft Graph"):
        fetch_teams_summary(
            tenant_id="tenant",
            client_id="client",
            client_secret="secret",
            team_id="team",
            channel_id="channel",
        )


def test_fetch_teams_summary_rejects_non_positive_timeout() -> None:
    with pytest.raises(ValueError, match="Microsoft Graph timeout must be greater than zero"):
        fetch_teams_summary(
            tenant_id="tenant",
            client_id="client",
            client_secret="secret",
            team_id="team",
            channel_id="channel",
            timeout_seconds=0,
        )
