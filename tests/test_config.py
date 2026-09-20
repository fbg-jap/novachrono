from pathlib import Path

import pytest

from novachrono.config import (
    DEFAULT_DISPLAY_ORDER,
    WIDGET_NAMES,
    ConfigError,
    load_config,
    validate_display_order,
)
from novachrono.units import TemperatureUnit

CONFIG_ENVIRONMENT_VARIABLES = (
    "NOVACHRONO_TIMEZONE",
    "NOVACHRONO_LOCALE",
    "NOVACHRONO_TEMPERATURE_UNIT",
    "NOVACHRONO_WEATHER_LATITUDE",
    "NOVACHRONO_WEATHER_LONGITUDE",
    "NOVACHRONO_TIMES_GATE_HOST",
    "NOVACHRONO_TIMES_GATE_TOKEN",
    "NOVACHRONO_MAIL_HOST",
    "NOVACHRONO_MAIL_PORT",
    "NOVACHRONO_MAIL_USERNAME",
    "NOVACHRONO_MAIL_PASSWORD",
    "NOVACHRONO_MAIL_MAILBOX",
    "NOVACHRONO_TEAMS_TENANT_ID",
    "NOVACHRONO_TEAMS_CLIENT_ID",
    "NOVACHRONO_TEAMS_CLIENT_SECRET",
    "NOVACHRONO_TEAMS_TEAM_ID",
    "NOVACHRONO_TEAMS_CHANNEL_ID",
    "NOVACHRONO_DISPLAY_ORDER",
)


@pytest.fixture(autouse=True)
def clear_config_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for variable in CONFIG_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)


def test_load_config_uses_defaults(tmp_path: Path) -> None:
    config = load_config(tmp_path / ".env")

    assert config.timezone.key == "Europe/Berlin"
    assert config.locale == "de_DE"
    assert config.temperature_unit is TemperatureUnit.CELSIUS

    assert config.weather.latitude is None
    assert config.weather.longitude is None

    assert config.times_gate.host is None
    assert config.times_gate.local_token is None

    assert config.mail.host is None
    assert config.mail.port == 993
    assert config.mail.username is None
    assert config.mail.password is None
    assert config.mail.mailbox == "INBOX"

    assert config.teams.tenant_id is None
    assert config.teams.client_id is None
    assert config.teams.client_secret is None
    assert config.teams.team_id is None
    assert config.teams.channel_id is None

    assert config.display_order == DEFAULT_DISPLAY_ORDER


def test_load_config_reads_dotenv(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"

    _write_env(
        env_file,
        "NOVACHRONO_TIMEZONE=Europe/Berlin",
        "NOVACHRONO_LOCALE=en_US",
        "NOVACHRONO_TEMPERATURE_UNIT=F",
        "NOVACHRONO_WEATHER_LATITUDE=53.04771",
        "NOVACHRONO_WEATHER_LONGITUDE=8.80169",
        "NOVACHRONO_TIMES_GATE_HOST=192.168.178.50",
        "NOVACHRONO_TIMES_GATE_TOKEN=secret",
        "NOVACHRONO_MAIL_HOST=imap.example.com",
        "NOVACHRONO_MAIL_PORT=143",
        "NOVACHRONO_MAIL_USERNAME=user@example.com",
        "NOVACHRONO_MAIL_PASSWORD=mail-secret",
        "NOVACHRONO_MAIL_MAILBOX=Archive",
        "NOVACHRONO_TEAMS_TENANT_ID=tenant-id",
        "NOVACHRONO_TEAMS_CLIENT_ID=client-id",
        "NOVACHRONO_TEAMS_CLIENT_SECRET=teams-secret",
        "NOVACHRONO_TEAMS_TEAM_ID=team-id",
        "NOVACHRONO_TEAMS_CHANNEL_ID=channel-id",
    )

    config = load_config(env_file)

    assert config.timezone.key == "Europe/Berlin"
    assert config.locale == "en_US"
    assert config.temperature_unit is TemperatureUnit.FAHRENHEIT

    assert config.weather.latitude == pytest.approx(53.04771)
    assert config.weather.longitude == pytest.approx(8.80169)

    assert config.times_gate.host == "192.168.178.50"
    assert config.times_gate.local_token == "secret"

    assert config.mail.host == "imap.example.com"
    assert config.mail.port == 143
    assert config.mail.username == "user@example.com"
    assert config.mail.password == "mail-secret"
    assert config.mail.mailbox == "Archive"

    assert config.teams.tenant_id == "tenant-id"
    assert config.teams.client_id == "client-id"
    assert config.teams.client_secret == "teams-secret"
    assert config.teams.team_id == "team-id"
    assert config.teams.channel_id == "channel-id"


def test_environment_overrides_dotenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"

    _write_env(
        env_file,
        "NOVACHRONO_LOCALE=de_DE",
        "NOVACHRONO_TEMPERATURE_UNIT=C",
        "NOVACHRONO_WEATHER_LATITUDE=1",
        "NOVACHRONO_WEATHER_LONGITUDE=2",
        "NOVACHRONO_TIMES_GATE_HOST=192.168.1.100",
        "NOVACHRONO_TIMES_GATE_TOKEN=file-token",
    )

    monkeypatch.setenv("NOVACHRONO_LOCALE", "en_US")
    monkeypatch.setenv("NOVACHRONO_TEMPERATURE_UNIT", "F")
    monkeypatch.setenv("NOVACHRONO_WEATHER_LATITUDE", "53.04771")
    monkeypatch.setenv("NOVACHRONO_WEATHER_LONGITUDE", "8.80169")
    monkeypatch.setenv("NOVACHRONO_TIMES_GATE_HOST", "192.168.178.50")
    monkeypatch.setenv("NOVACHRONO_TIMES_GATE_TOKEN", "environment-token")

    config = load_config(env_file)

    assert config.locale == "en_US"
    assert config.temperature_unit is TemperatureUnit.FAHRENHEIT

    assert config.weather.latitude == pytest.approx(53.04771)
    assert config.weather.longitude == pytest.approx(8.80169)

    assert config.times_gate.host == "192.168.178.50"
    assert config.times_gate.local_token == "environment-token"


def test_blank_weather_values_become_none(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"

    _write_env(
        env_file,
        "NOVACHRONO_WEATHER_LATITUDE=",
        "NOVACHRONO_WEATHER_LONGITUDE=",
    )

    config = load_config(env_file)

    assert config.weather.latitude is None
    assert config.weather.longitude is None


@pytest.mark.parametrize(
    "configured_variable",
    [
        "NOVACHRONO_WEATHER_LATITUDE=53.04771",
        "NOVACHRONO_WEATHER_LONGITUDE=8.80169",
    ],
)
def test_weather_coordinates_must_be_configured_together(
    configured_variable: str,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    _write_env(env_file, configured_variable)

    with pytest.raises(
        ConfigError,
        match="latitude and longitude must be configured together",
    ):
        load_config(env_file)


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (-90, -180),
        (-90, 180),
        (90, -180),
        (90, 180),
    ],
)
def test_weather_coordinates_accept_boundary_values(
    latitude: int,
    longitude: int,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"

    _write_env(
        env_file,
        f"NOVACHRONO_WEATHER_LATITUDE={latitude}",
        f"NOVACHRONO_WEATHER_LONGITUDE={longitude}",
    )

    config = load_config(env_file)

    assert config.weather.latitude == latitude
    assert config.weather.longitude == longitude


@pytest.mark.parametrize(
    ("variable", "value", "message"),
    [
        (
            "NOVACHRONO_WEATHER_LATITUDE",
            "91",
            "latitude must be between",
        ),
        (
            "NOVACHRONO_WEATHER_LATITUDE",
            "-91",
            "latitude must be between",
        ),
        (
            "NOVACHRONO_WEATHER_LONGITUDE",
            "181",
            "longitude must be between",
        ),
        (
            "NOVACHRONO_WEATHER_LONGITUDE",
            "-181",
            "longitude must be between",
        ),
    ],
)
def test_weather_coordinates_reject_out_of_range_values(
    variable: str,
    value: str,
    message: str,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"

    values = {
        "NOVACHRONO_WEATHER_LATITUDE": "53.04771",
        "NOVACHRONO_WEATHER_LONGITUDE": "8.80169",
    }
    values[variable] = value

    _write_env(
        env_file,
        *(f"{name}={configured_value}" for name, configured_value in values.items()),
    )

    with pytest.raises(
        ConfigError,
        match=message,
    ):
        load_config(env_file)


def test_invalid_weather_coordinate_raises_config_error(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"

    _write_env(
        env_file,
        "NOVACHRONO_WEATHER_LATITUDE=not-a-number",
        "NOVACHRONO_WEATHER_LONGITUDE=8.80169",
    )

    with pytest.raises(
        ConfigError,
        match="Invalid numeric value",
    ):
        load_config(env_file)


def test_blank_times_gate_values_become_none(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"

    _write_env(
        env_file,
        "NOVACHRONO_TIMES_GATE_HOST=",
        "NOVACHRONO_TIMES_GATE_TOKEN=",
    )

    config = load_config(env_file)

    assert config.times_gate.host is None
    assert config.times_gate.local_token is None


def test_invalid_timezone_raises_config_error(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"

    _write_env(
        env_file,
        "NOVACHRONO_TIMEZONE=Definitely/Not-A-Timezone",
    )

    with pytest.raises(
        ConfigError,
        match="Unknown timezone",
    ):
        load_config(env_file)


def test_invalid_locale_raises_config_error(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"

    _write_env(
        env_file,
        "NOVACHRONO_LOCALE=xx_XX",
    )

    with pytest.raises(
        ConfigError,
        match="Unsupported locale",
    ):
        load_config(env_file)


@pytest.mark.parametrize(
    ("configured_value", "expected_unit"),
    [
        (
            "C",
            TemperatureUnit.CELSIUS,
        ),
        (
            "c",
            TemperatureUnit.CELSIUS,
        ),
        (
            "CELSIUS",
            TemperatureUnit.CELSIUS,
        ),
        (
            "celsius",
            TemperatureUnit.CELSIUS,
        ),
        (
            "F",
            TemperatureUnit.FAHRENHEIT,
        ),
        (
            "f",
            TemperatureUnit.FAHRENHEIT,
        ),
        (
            "FAHRENHEIT",
            TemperatureUnit.FAHRENHEIT,
        ),
        (
            "fahrenheit",
            TemperatureUnit.FAHRENHEIT,
        ),
    ],
)
def test_temperature_unit_accepts_supported_values(
    configured_value: str,
    expected_unit: TemperatureUnit,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"

    _write_env(
        env_file,
        f"NOVACHRONO_TEMPERATURE_UNIT={configured_value}",
    )

    config = load_config(env_file)

    assert config.temperature_unit is expected_unit


def test_invalid_temperature_unit_raises_config_error(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"

    _write_env(
        env_file,
        "NOVACHRONO_TEMPERATURE_UNIT=K",
    )

    with pytest.raises(
        ConfigError,
        match="Unsupported temperature unit",
    ):
        load_config(env_file)


@pytest.mark.parametrize(
    "configured_variable",
    [
        "NOVACHRONO_MAIL_HOST=imap.example.com",
        "NOVACHRONO_MAIL_USERNAME=user@example.com",
        "NOVACHRONO_MAIL_PASSWORD=secret",
    ],
)
def test_mail_settings_must_be_configured_together(
    configured_variable: str,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    _write_env(env_file, configured_variable)

    with pytest.raises(
        ConfigError,
        match="Mail host, username, and password must be configured together",
    ):
        load_config(env_file)


@pytest.mark.parametrize(
    "port",
    [
        "0",
        "65536",
        "-1",
    ],
)
def test_mail_port_rejects_out_of_range_values(
    port: str,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"

    _write_env(
        env_file,
        f"NOVACHRONO_MAIL_PORT={port}",
    )

    with pytest.raises(
        ConfigError,
        match="Mail port must be between",
    ):
        load_config(env_file)


def test_invalid_mail_port_raises_config_error(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"

    _write_env(
        env_file,
        "NOVACHRONO_MAIL_PORT=not-a-number",
    )

    with pytest.raises(
        ConfigError,
        match="Invalid numeric value",
    ):
        load_config(env_file)


def test_blank_mail_values_use_defaults(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"

    _write_env(
        env_file,
        "NOVACHRONO_MAIL_HOST=",
        "NOVACHRONO_MAIL_USERNAME=",
        "NOVACHRONO_MAIL_PASSWORD=",
        "NOVACHRONO_MAIL_PORT=",
        "NOVACHRONO_MAIL_MAILBOX=",
    )

    config = load_config(env_file)

    assert config.mail.host is None
    assert config.mail.username is None
    assert config.mail.password is None
    assert config.mail.port == 993
    assert config.mail.mailbox == "INBOX"


@pytest.mark.parametrize(
    "configured_variable",
    [
        "NOVACHRONO_TEAMS_TENANT_ID=tenant-id",
        "NOVACHRONO_TEAMS_CLIENT_ID=client-id",
        "NOVACHRONO_TEAMS_CLIENT_SECRET=secret",
        "NOVACHRONO_TEAMS_TEAM_ID=team-id",
        "NOVACHRONO_TEAMS_CHANNEL_ID=channel-id",
    ],
)
def test_teams_settings_must_be_configured_together(
    configured_variable: str,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    _write_env(env_file, configured_variable)

    with pytest.raises(
        ConfigError,
        match="Teams tenant ID, client ID, client secret, team ID, and channel ID",
    ):
        load_config(env_file)


def test_blank_teams_values_become_none(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"

    _write_env(
        env_file,
        "NOVACHRONO_TEAMS_TENANT_ID=",
        "NOVACHRONO_TEAMS_CLIENT_ID=",
        "NOVACHRONO_TEAMS_CLIENT_SECRET=",
        "NOVACHRONO_TEAMS_TEAM_ID=",
        "NOVACHRONO_TEAMS_CHANNEL_ID=",
    )

    config = load_config(env_file)

    assert config.teams.tenant_id is None
    assert config.teams.client_id is None
    assert config.teams.client_secret is None
    assert config.teams.team_id is None
    assert config.teams.channel_id is None


def test_load_config_reads_custom_display_order(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"

    _write_env(
        env_file,
        "NOVACHRONO_DISPLAY_ORDER=teams,pokemon_go,clock,weather,mail",
    )

    config = load_config(env_file)

    assert config.display_order == (
        "teams",
        "pokemon_go",
        "clock",
        "weather",
        "mail",
    )


def test_validate_display_order_accepts_a_permutation_of_widget_names() -> None:
    shuffled = tuple(reversed(WIDGET_NAMES))

    assert validate_display_order(shuffled) == shuffled


@pytest.mark.parametrize(
    "order",
    [
        ("mail", "weather", "clock", "pokemon_go"),
        ("mail", "weather", "clock", "pokemon_go", "teams", "mail"),
        ("mail", "mail", "clock", "pokemon_go", "teams"),
        ("mail", "weather", "clock", "pokemon_go", "unknown_widget"),
        (),
    ],
)
def test_validate_display_order_rejects_invalid_permutations(
    order: tuple[str, ...],
) -> None:
    with pytest.raises(
        ConfigError,
        match="Display order must contain each of",
    ):
        validate_display_order(order)


def test_display_order_must_be_a_valid_permutation_in_dotenv(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"

    _write_env(
        env_file,
        "NOVACHRONO_DISPLAY_ORDER=mail,weather,clock",
    )

    with pytest.raises(
        ConfigError,
        match="Display order must contain each of",
    ):
        load_config(env_file)


def _write_env(
    destination: Path,
    *lines: str,
) -> None:
    destination.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )
