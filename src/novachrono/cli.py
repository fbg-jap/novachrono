import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Final, NoReturn

import typer
from PIL import Image

from novachrono.config import (
    MAIL_HOST_VARIABLE,
    MAIL_PASSWORD_VARIABLE,
    MAIL_USERNAME_VARIABLE,
    TEAMS_CHANNEL_ID_VARIABLE,
    TEAMS_CLIENT_ID_VARIABLE,
    TEAMS_CLIENT_SECRET_VARIABLE,
    TEAMS_TEAM_ID_VARIABLE,
    TEAMS_TENANT_ID_VARIABLE,
    TIMES_GATE_HOST_VARIABLE,
    TIMES_GATE_TOKEN_VARIABLE,
    WEATHER_LATITUDE_VARIABLE,
    WEATHER_LONGITUDE_VARIABLE,
    AppConfig,
    ConfigError,
    load_config,
)
from novachrono.dashboard import (
    CLOCK_PANEL_INDEX,
    MAIL_PANEL_INDEX,
    POKEMON_GO_PANEL_INDEX,
    TEAMS_PANEL_INDEX,
    WEATHER_PANEL_INDEX,
    render_dashboard,
)
from novachrono.mail import MailSummary
from novachrono.outputs.times_gate import (
    TimesGateClient,
    TimesGateConfig,
    TimesGateError,
)
from novachrono.pokemon_go import RaidRoster
from novachrono.preview import create_preview, save_preview
from novachrono.sources.imap_mail import MailError, fetch_mail_summary
from novachrono.sources.ms_graph_teams import TeamsError, fetch_teams_summary
from novachrono.sources.open_meteo import (
    OpenMeteoError,
    fetch_current_weather,
)
from novachrono.sources.pokeapi import localize_raid_roster
from novachrono.sources.pokemon_artwork import fetch_raid_artwork
from novachrono.sources.scraped_duck import (
    ScrapedDuckError,
    fetch_raid_roster,
)
from novachrono.teams import TeamsSummary
from novachrono.weather import CurrentWeather, WeatherCondition
from novachrono.webconfig import (
    DEFAULT_CONFIG_SERVER_HOST,
    DEFAULT_CONFIG_SERVER_PORT,
    run_config_server,
)
from novachrono.widgets.clock import render_clock_animation
from novachrono.widgets.mail import render_mail_panel
from novachrono.widgets.pokemon_go import render_raid_animation
from novachrono.widgets.teams import render_teams_panel
from novachrono.widgets.weather import render_weather_animation

CLOCK_FRAME_DURATION_MS: Final = 250
POKEMON_GO_FRAME_DURATION_MS: Final = 10_000
RAIN_FRAME_DURATION_MS: Final = 350
FOG_FRAME_DURATION_MS: Final = 500

app = typer.Typer(
    name="novachrono",
    help="Render and send dashboards to a Divoom Times Gate.",
    no_args_is_help=True,
    add_completion=False,
)

HostOption = Annotated[
    str | None,
    typer.Option(
        "--host",
        help="Override the Times Gate host configured with NOVACHRONO_TIMES_GATE_HOST.",
        metavar="HOST",
    ),
]

TokenOption = Annotated[
    str | None,
    typer.Option(
        "--token",
        help="Override the Times Gate token configured with NOVACHRONO_TIMES_GATE_TOKEN.",
        metavar="TOKEN",
    ),
]


@app.command()
def configure(
    host: Annotated[
        str,
        typer.Option(
            "--host",
            help="Interface to bind the local configuration server to.",
            metavar="HOST",
        ),
    ] = DEFAULT_CONFIG_SERVER_HOST,
    port: Annotated[
        int,
        typer.Option(
            "--port",
            help="Port for the local configuration server.",
        ),
    ] = DEFAULT_CONFIG_SERVER_PORT,
    open_browser: Annotated[
        bool,
        typer.Option(
            "--open-browser/--no-open-browser",
            help="Automatically open the configuration page in a browser.",
        ),
    ] = True,
) -> None:
    """Start a local web GUI for editing the .env configuration."""

    if host != DEFAULT_CONFIG_SERVER_HOST:
        typer.echo(
            f"Warning: binding to {host} may expose your configuration, "
            "including the Times Gate token, to other devices on the network.",
            err=True,
        )

    typer.echo(f"Serving configuration at http://{host}:{port}/ (press Ctrl+C to stop) ...")

    run_config_server(
        host=host,
        port=port,
        open_browser=open_browser,
    )


@app.command()
def preview(
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Destination for the generated dashboard preview.",
            dir_okay=False,
        ),
    ] = Path("output/dashboard-preview.png"),
) -> None:
    """Render the complete dashboard preview."""

    config = _load_app_config()

    mail = _load_mail_summary_best_effort(config)
    teams = _load_teams_summary_best_effort(config)
    weather = _load_current_weather(config)
    raid_roster = _load_raid_roster(config)
    raid_artwork = fetch_raid_artwork(raid_roster)

    panels = render_dashboard(
        mail=mail,
        weather=weather,
        raid_roster=raid_roster,
        teams=teams,
        raid_artwork=raid_artwork,
        timezone=config.timezone,
        locale=config.locale,
        temperature_unit=config.temperature_unit,
    )

    dashboard_preview = create_preview(panels)

    save_preview(
        dashboard_preview,
        output,
    )

    typer.echo(f"Dashboard preview written to {output}")


@app.command(name="check-device")
def check_device(
    host: HostOption = None,
    token: TokenOption = None,
) -> None:
    """Check the configured Times Gate connection."""

    app_config = _load_app_config()

    client = _create_times_gate_client(
        app_config=app_config,
        host=host,
        local_token=token,
    )

    typer.echo(f"Connecting to {client.config.api_url} ...")

    try:
        response = client.get_configuration()
    except TimesGateError as error:
        _exit_with_error(str(error))

    typer.echo("Connection successful.")

    typer.echo(
        json.dumps(
            response,
            indent=2,
            ensure_ascii=False,
        )
    )


@app.command(name="send-clock")
def send_clock(
    host: HostOption = None,
    token: TokenOption = None,
) -> None:
    """Render and send the clock panel."""

    app_config = _load_app_config()

    client = _create_times_gate_client(
        app_config=app_config,
        host=host,
        local_token=token,
    )

    frames = render_clock_animation(datetime.now(app_config.timezone))

    _send_widget_frames(
        client=client,
        panel_index=CLOCK_PANEL_INDEX,
        frames=frames,
        frame_duration_ms=CLOCK_FRAME_DURATION_MS,
        name="Clock",
    )


@app.command(name="send-weather")
def send_weather(
    host: HostOption = None,
    token: TokenOption = None,
) -> None:
    """Retrieve, render, and send the weather panel."""

    app_config = _load_app_config()

    client = _create_times_gate_client(
        app_config=app_config,
        host=host,
        local_token=token,
    )

    weather = _load_current_weather(app_config)

    frames = render_weather_animation(
        weather,
        locale=app_config.locale,
        temperature_unit=app_config.temperature_unit,
    )

    _send_widget_frames(
        client=client,
        panel_index=WEATHER_PANEL_INDEX,
        frames=frames,
        frame_duration_ms=_weather_frame_duration_ms(weather.condition),
        name="Weather",
    )


@app.command(name="send-mail")
def send_mail(
    host: HostOption = None,
    token: TokenOption = None,
) -> None:
    """Retrieve and send the mail notifications panel."""

    app_config = _load_app_config()

    client = _create_times_gate_client(
        app_config=app_config,
        host=host,
        local_token=token,
    )

    mail = _load_mail_summary(app_config)

    frame = render_mail_panel(
        mail,
        locale=app_config.locale,
    )

    _send_widget_frames(
        client=client,
        panel_index=MAIL_PANEL_INDEX,
        frames=(frame,),
        frame_duration_ms=None,
        name="Mail",
    )


@app.command(name="send-teams")
def send_teams(
    host: HostOption = None,
    token: TokenOption = None,
) -> None:
    """Retrieve and send the Microsoft Teams notifications panel."""

    app_config = _load_app_config()

    client = _create_times_gate_client(
        app_config=app_config,
        host=host,
        local_token=token,
    )

    teams = _load_teams_summary(app_config)

    frame = render_teams_panel(teams)

    _send_widget_frames(
        client=client,
        panel_index=TEAMS_PANEL_INDEX,
        frames=(frame,),
        frame_duration_ms=None,
        name="Teams",
    )


@app.command(name="send-pokemon")
def send_pokemon(
    host: HostOption = None,
    token: TokenOption = None,
) -> None:
    """Retrieve, render, and send the Pokémon GO raid panel."""

    app_config = _load_app_config()

    client = _create_times_gate_client(
        app_config=app_config,
        host=host,
        local_token=token,
    )

    raid_roster = _load_raid_roster(app_config)
    raid_artwork = fetch_raid_artwork(raid_roster)

    frames = render_raid_animation(
        raid_roster,
        artwork_by_url=raid_artwork,
    )

    _send_widget_frames(
        client=client,
        panel_index=POKEMON_GO_PANEL_INDEX,
        frames=frames,
        frame_duration_ms=POKEMON_GO_FRAME_DURATION_MS,
        name="Pokémon GO",
    )


@app.command(name="send-dashboard")
def send_dashboard(
    host: HostOption = None,
    token: TokenOption = None,
) -> None:
    """Retrieve, render, and send all five dashboard panels."""

    app_config = _load_app_config()

    client = _create_times_gate_client(
        app_config=app_config,
        host=host,
        local_token=token,
    )

    mail = _load_mail_summary_best_effort(app_config)
    teams = _load_teams_summary_best_effort(app_config)
    weather = _load_current_weather(app_config)
    raid_roster = _load_raid_roster(app_config)
    raid_artwork = fetch_raid_artwork(raid_roster)

    panels = render_dashboard(
        mail=mail,
        weather=weather,
        raid_roster=raid_roster,
        teams=teams,
        raid_artwork=raid_artwork,
        timezone=app_config.timezone,
        locale=app_config.locale,
        temperature_unit=app_config.temperature_unit,
    )

    clock_frames = render_clock_animation(datetime.now(app_config.timezone))

    weather_frames = render_weather_animation(
        weather,
        locale=app_config.locale,
        temperature_unit=app_config.temperature_unit,
    )

    pokemon_frames = render_raid_animation(
        raid_roster,
        artwork_by_url=raid_artwork,
    )

    panel_frames: dict[
        int,
        tuple[
            tuple[Image.Image, ...],
            int | None,
        ],
    ] = {
        CLOCK_PANEL_INDEX: (
            clock_frames,
            CLOCK_FRAME_DURATION_MS,
        ),
        WEATHER_PANEL_INDEX: (
            weather_frames,
            _weather_frame_duration_ms(weather.condition),
        ),
        POKEMON_GO_PANEL_INDEX: (
            pokemon_frames,
            POKEMON_GO_FRAME_DURATION_MS,
        ),
    }

    failed_displays: list[int] = []

    typer.echo(f"Sending dashboard to {len(panels)} displays at {client.config.api_url} ...")

    for panel_index, panel in enumerate(panels):
        display_number = panel_index + 1

        typer.echo(f"Sending display {display_number}/{len(panels)} ...")

        frames, frame_duration_ms = panel_frames.get(
            panel_index,
            ((panel,), None),
        )

        try:
            _deliver_frames(
                client=client,
                panel_index=panel_index,
                frames=frames,
                frame_duration_ms=frame_duration_ms,
            )
        except TimesGateError as error:
            failed_displays.append(display_number)

            typer.echo(
                f"Display {display_number} failed: {error}",
                err=True,
            )

            continue

        typer.echo(f"Display {display_number} sent successfully.")

    if failed_displays:
        formatted_displays = ", ".join(str(display_number) for display_number in failed_displays)

        _exit_with_error(f"Dashboard delivery failed for display(s): {formatted_displays}")

    typer.echo("Dashboard sent successfully.")


def _send_widget_frames(
    *,
    client: TimesGateClient,
    panel_index: int,
    frames: tuple[Image.Image, ...],
    frame_duration_ms: int | None,
    name: str,
) -> None:
    display_number = panel_index + 1

    typer.echo(f"Sending {name.lower()} to display {display_number} ...")

    try:
        responses = _deliver_frames(
            client=client,
            panel_index=panel_index,
            frames=frames,
            frame_duration_ms=frame_duration_ms,
        )
    except TimesGateError as error:
        _exit_with_error(str(error))

    typer.echo(f"{name} sent successfully with {len(frames)} frame(s).")

    response_output: object
    response_output = responses[0] if len(responses) == 1 else responses

    typer.echo(
        json.dumps(
            response_output,
            indent=2,
            ensure_ascii=False,
        )
    )


def _deliver_frames(
    *,
    client: TimesGateClient,
    panel_index: int,
    frames: tuple[Image.Image, ...],
    frame_duration_ms: int | None,
) -> tuple[dict[str, Any], ...]:
    if len(frames) == 1:
        response = client.send_image(
            panel_index=panel_index,
            image=frames[0],
        )

        return (response,)

    if frame_duration_ms is None:
        raise ValueError("Animated panel requires a frame duration")

    return client.send_animation(
        panel_index=panel_index,
        images=frames,
        frame_duration_ms=frame_duration_ms,
    )


def _weather_frame_duration_ms(
    condition: WeatherCondition,
) -> int | None:
    match condition:
        case WeatherCondition.RAIN:
            return RAIN_FRAME_DURATION_MS

        case WeatherCondition.FOG:
            return FOG_FRAME_DURATION_MS

        case _:
            return None


def _load_current_weather(
    app_config: AppConfig,
) -> CurrentWeather:
    latitude = app_config.weather.latitude
    longitude = app_config.weather.longitude

    if latitude is None or longitude is None:
        missing_variables: list[str] = []

        if latitude is None:
            missing_variables.append(WEATHER_LATITUDE_VARIABLE)

        if longitude is None:
            missing_variables.append(WEATHER_LONGITUDE_VARIABLE)

        joined_variables = ", ".join(missing_variables)

        _exit_with_error(f"Missing required weather configuration: {joined_variables}")

    try:
        return fetch_current_weather(
            latitude=latitude,
            longitude=longitude,
            timezone=app_config.timezone,
        )
    except OpenMeteoError as error:
        _exit_with_error(str(error))


def _load_mail_summary(
    app_config: AppConfig,
) -> MailSummary:
    """Load the mail summary, exiting with an error if mail is not usable."""

    if not _mail_settings_configured(app_config):
        missing_variables = ", ".join(
            (
                MAIL_HOST_VARIABLE,
                MAIL_USERNAME_VARIABLE,
                MAIL_PASSWORD_VARIABLE,
            )
        )

        _exit_with_error(f"Missing required mail configuration: {missing_variables}")

    try:
        return _fetch_configured_mail_summary(app_config)
    except MailError as error:
        _exit_with_error(str(error))


def _load_mail_summary_best_effort(
    app_config: AppConfig,
) -> MailSummary:
    """Load the mail summary without failing the whole dashboard on error."""

    if not _mail_settings_configured(app_config):
        return MailSummary(unread_count=0)

    try:
        return _fetch_configured_mail_summary(app_config)
    except MailError as error:
        typer.echo(f"Warning: could not retrieve mail: {error}", err=True)
        return MailSummary(unread_count=0)


def _mail_settings_configured(
    app_config: AppConfig,
) -> bool:
    mail = app_config.mail

    return mail.host is not None and mail.username is not None and mail.password is not None


def _fetch_configured_mail_summary(
    app_config: AppConfig,
) -> MailSummary:
    return fetch_mail_summary(
        host=app_config.mail.host,
        port=app_config.mail.port,
        username=app_config.mail.username,
        password=app_config.mail.password,
        mailbox=app_config.mail.mailbox,
    )


def _load_teams_summary(
    app_config: AppConfig,
) -> TeamsSummary:
    """Load the Teams summary, exiting with an error if Teams is not usable."""

    if not _teams_settings_configured(app_config):
        missing_variables = ", ".join(
            (
                TEAMS_TENANT_ID_VARIABLE,
                TEAMS_CLIENT_ID_VARIABLE,
                TEAMS_CLIENT_SECRET_VARIABLE,
                TEAMS_TEAM_ID_VARIABLE,
                TEAMS_CHANNEL_ID_VARIABLE,
            )
        )

        _exit_with_error(f"Missing required Teams configuration: {missing_variables}")

    try:
        return _fetch_configured_teams_summary(app_config)
    except TeamsError as error:
        _exit_with_error(str(error))


def _load_teams_summary_best_effort(
    app_config: AppConfig,
) -> TeamsSummary:
    """Load the Teams summary without failing the whole dashboard on error."""

    if not _teams_settings_configured(app_config):
        return TeamsSummary()

    try:
        return _fetch_configured_teams_summary(app_config)
    except TeamsError as error:
        typer.echo(f"Warning: could not retrieve Teams messages: {error}", err=True)
        return TeamsSummary()


def _teams_settings_configured(
    app_config: AppConfig,
) -> bool:
    teams = app_config.teams

    return (
        teams.tenant_id is not None
        and teams.client_id is not None
        and teams.client_secret is not None
        and teams.team_id is not None
        and teams.channel_id is not None
    )


def _fetch_configured_teams_summary(
    app_config: AppConfig,
) -> TeamsSummary:
    return fetch_teams_summary(
        tenant_id=app_config.teams.tenant_id,
        client_id=app_config.teams.client_id,
        client_secret=app_config.teams.client_secret,
        team_id=app_config.teams.team_id,
        channel_id=app_config.teams.channel_id,
    )


def _load_raid_roster(
    app_config: AppConfig,
) -> RaidRoster:
    try:
        roster = fetch_raid_roster()
    except ScrapedDuckError as error:
        _exit_with_error(str(error))

    return localize_raid_roster(
        roster,
        locale=app_config.locale,
    )


def _load_app_config() -> AppConfig:
    try:
        return load_config()
    except ConfigError as error:
        _exit_with_error(str(error))


def _create_times_gate_client(
    *,
    app_config: AppConfig,
    host: str | None,
    local_token: str | None,
) -> TimesGateClient:
    resolved_host = _resolve_value(
        override=host,
        configured=app_config.times_gate.host,
    )

    resolved_token = _resolve_value(
        override=local_token,
        configured=app_config.times_gate.local_token,
    )

    if resolved_host is None or resolved_token is None:
        missing_variables: list[str] = []

        if resolved_host is None:
            missing_variables.append(TIMES_GATE_HOST_VARIABLE)

        if resolved_token is None:
            missing_variables.append(TIMES_GATE_TOKEN_VARIABLE)

        joined_variables = ", ".join(missing_variables)

        _exit_with_error(f"Missing required configuration: {joined_variables}")

    try:
        times_gate_config = TimesGateConfig(
            host=resolved_host,
            local_token=resolved_token,
        )
    except ValueError as error:
        _exit_with_error(str(error))

    return TimesGateClient(times_gate_config)


def _resolve_value(
    *,
    override: str | None,
    configured: str | None,
) -> str | None:
    if override is None:
        return configured

    normalized_override = override.strip()

    if normalized_override:
        return normalized_override

    return configured


def _exit_with_error(
    message: str,
) -> NoReturn:
    typer.echo(
        f"Error: {message}",
        err=True,
    )

    raise typer.Exit(code=1)
