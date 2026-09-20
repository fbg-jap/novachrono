import threading
from collections.abc import Iterator
from http.server import HTTPServer
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import pytest
from dotenv import dotenv_values

from novachrono.webconfig import _build_handler


@pytest.fixture
def running_server(tmp_path: Path) -> Iterator[tuple[HTTPServer, Path]]:
    env_file = tmp_path / ".env"
    handler_class = _build_handler(env_file)
    httpd = HTTPServer(("127.0.0.1", 0), handler_class)

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    try:
        yield httpd, env_file
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def test_get_returns_configuration_form(
    running_server: tuple[HTTPServer, Path],
) -> None:
    httpd, _ = running_server

    with urlopen(_server_url(httpd)) as response:
        body = response.read().decode("utf-8")

        assert response.status == 200

    assert "Novachrono Configuration" in body
    assert "NOVACHRONO_LOCALE" in body
    assert "NOVACHRONO_TIMES_GATE_TOKEN" in body


def test_post_valid_values_writes_env_file(
    running_server: tuple[HTTPServer, Path],
) -> None:
    httpd, env_file = running_server

    with urlopen(_server_url(httpd), data=_encode(_VALID_SUBMISSION)) as response:
        body = response.read().decode("utf-8")

        assert response.status == 200

    assert "Configuration saved." in body

    values = dotenv_values(env_file)
    assert values["NOVACHRONO_LOCALE"] == "en_US"
    assert values["NOVACHRONO_TIMEZONE"] == "Europe/Berlin"
    assert values["NOVACHRONO_TEMPERATURE_UNIT"] == "F"
    assert values["NOVACHRONO_WEATHER_LATITUDE"] == "53.04771"
    assert values["NOVACHRONO_WEATHER_LONGITUDE"] == "8.80169"
    assert values["NOVACHRONO_TIMES_GATE_HOST"] == "192.168.1.100"
    assert values["NOVACHRONO_TIMES_GATE_TOKEN"] == "secret-token"


def test_post_invalid_timezone_does_not_write_env_file(
    running_server: tuple[HTTPServer, Path],
) -> None:
    httpd, env_file = running_server

    submission = dict(_VALID_SUBMISSION, NOVACHRONO_TIMEZONE="Not/AZone")

    with urlopen(_server_url(httpd), data=_encode(submission)) as response:
        body = response.read().decode("utf-8")

        assert response.status == 200

    assert "Unknown timezone" in body
    assert not env_file.exists()


def test_post_incomplete_weather_coordinates_reports_error(
    running_server: tuple[HTTPServer, Path],
) -> None:
    httpd, env_file = running_server

    submission = dict(_VALID_SUBMISSION, NOVACHRONO_WEATHER_LONGITUDE="")

    with urlopen(_server_url(httpd), data=_encode(submission)) as response:
        body = response.read().decode("utf-8")

    assert "latitude and longitude must be configured together" in body
    assert not env_file.exists()


def test_post_allows_blank_optional_fields(
    running_server: tuple[HTTPServer, Path],
) -> None:
    httpd, env_file = running_server

    submission = dict(
        _VALID_SUBMISSION,
        NOVACHRONO_WEATHER_LATITUDE="",
        NOVACHRONO_WEATHER_LONGITUDE="",
        NOVACHRONO_TIMES_GATE_HOST="",
        NOVACHRONO_TIMES_GATE_TOKEN="",
    )

    with urlopen(_server_url(httpd), data=_encode(submission)) as response:
        body = response.read().decode("utf-8")

    assert "Configuration saved." in body

    values = dotenv_values(env_file)
    assert values["NOVACHRONO_WEATHER_LATITUDE"] == ""
    assert values["NOVACHRONO_WEATHER_LONGITUDE"] == ""
    assert values["NOVACHRONO_TIMES_GATE_HOST"] == ""
    assert values["NOVACHRONO_TIMES_GATE_TOKEN"] == ""


_VALID_SUBMISSION = {
    "NOVACHRONO_LOCALE": "en_US",
    "NOVACHRONO_TIMEZONE": "Europe/Berlin",
    "NOVACHRONO_TEMPERATURE_UNIT": "F",
    "NOVACHRONO_WEATHER_LATITUDE": "53.04771",
    "NOVACHRONO_WEATHER_LONGITUDE": "8.80169",
    "NOVACHRONO_TIMES_GATE_HOST": "192.168.1.100",
    "NOVACHRONO_TIMES_GATE_TOKEN": "secret-token",
}


def _server_url(httpd: HTTPServer, path: str = "/") -> str:
    port = httpd.server_address[1]
    return f"http://127.0.0.1:{port}{path}"


def _encode(values: dict[str, str]) -> bytes:
    return urlencode(values).encode("utf-8")
