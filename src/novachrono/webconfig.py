"""Local web GUI for editing the Novachrono ``.env`` configuration."""

import html
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Final
from urllib.parse import parse_qs

from dotenv import dotenv_values, set_key

from novachrono.config import (
    DEFAULT_ENV_FILENAME,
    DEFAULT_MAIL_MAILBOX,
    DEFAULT_MAIL_PORT,
    LOCALE_VARIABLE,
    MAIL_HOST_VARIABLE,
    MAIL_MAILBOX_VARIABLE,
    MAIL_PASSWORD_VARIABLE,
    MAIL_PORT_VARIABLE,
    MAIL_USERNAME_VARIABLE,
    TEMPERATURE_UNIT_VARIABLE,
    TIMES_GATE_HOST_VARIABLE,
    TIMES_GATE_TOKEN_VARIABLE,
    TIMEZONE_VARIABLE,
    WEATHER_LATITUDE_VARIABLE,
    WEATHER_LONGITUDE_VARIABLE,
    ConfigError,
    parse_temperature_unit,
    validate_locale,
    validate_mail_settings,
    validate_timezone,
    validate_weather_settings,
)
from novachrono.i18n import SUPPORTED_LOCALES

DEFAULT_CONFIG_SERVER_HOST: Final = "127.0.0.1"
DEFAULT_CONFIG_SERVER_PORT: Final = 8765

_TEMPERATURE_UNITS: Final = ("C", "F")


@dataclass(frozen=True)
class _Field:
    """A single editable configuration field."""

    variable: str
    label: str
    input_type: str = "text"
    choices: tuple[str, ...] | None = None
    help_text: str | None = None


_FIELDS: Final[tuple[_Field, ...]] = (
    _Field(LOCALE_VARIABLE, "Locale", choices=SUPPORTED_LOCALES),
    _Field(TIMEZONE_VARIABLE, "Timezone", help_text="An IANA timezone name, e.g. Europe/Berlin."),
    _Field(TEMPERATURE_UNIT_VARIABLE, "Temperature unit", choices=_TEMPERATURE_UNITS),
    _Field(
        WEATHER_LATITUDE_VARIABLE,
        "Weather latitude",
        help_text="-90 to 90. Leave both weather fields empty to disable weather.",
    ),
    _Field(WEATHER_LONGITUDE_VARIABLE, "Weather longitude", help_text="-180 to 180."),
    _Field(
        TIMES_GATE_HOST_VARIABLE,
        "Times Gate host",
        help_text="Local IP address or hostname only, e.g. 192.168.1.100.",
    ),
    _Field(TIMES_GATE_TOKEN_VARIABLE, "Times Gate token", input_type="password"),
    _Field(
        MAIL_HOST_VARIABLE,
        "Mail IMAP host",
        help_text="Leave host, username, and password empty to disable the mail widget.",
    ),
    _Field(MAIL_PORT_VARIABLE, "Mail IMAP port", help_text=f"Default: {DEFAULT_MAIL_PORT}."),
    _Field(MAIL_USERNAME_VARIABLE, "Mail username"),
    _Field(MAIL_PASSWORD_VARIABLE, "Mail password", input_type="password"),
    _Field(MAIL_MAILBOX_VARIABLE, "Mail mailbox", help_text=f"Default: {DEFAULT_MAIL_MAILBOX}."),
)


def run_config_server(
    *,
    host: str = DEFAULT_CONFIG_SERVER_HOST,
    port: int = DEFAULT_CONFIG_SERVER_PORT,
    env_file: Path | None = None,
    open_browser: bool = True,
) -> None:
    """Serve a local configuration form until interrupted."""

    resolved_env_file = env_file if env_file is not None else Path.cwd() / DEFAULT_ENV_FILENAME

    handler_class = _build_handler(resolved_env_file)
    server = HTTPServer((host, port), handler_class)

    if open_browser:
        webbrowser.open(f"http://{host}:{port}/")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _build_handler(env_file: Path) -> type[BaseHTTPRequestHandler]:
    class ConfigRequestHandler(BaseHTTPRequestHandler):
        server_version = "NovachronoConfig/1.0"

        def do_GET(self) -> None:
            current_values = dotenv_values(env_file) if env_file.is_file() else {}
            self._respond(current_values, errors=(), saved=False)

        def do_POST(self) -> None:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            submitted_values = {key: values[0] for key, values in parse_qs(body).items()}

            errors = _validate_submission(submitted_values)

            if not errors:
                _write_submission(env_file, submitted_values)

            self._respond(submitted_values, errors=errors, saved=not errors)

        def _respond(
            self,
            values: dict[str, str | None],
            *,
            errors: tuple[str, ...],
            saved: bool,
        ) -> None:
            page = _render_page(values, errors=errors, saved=saved).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)

        def log_message(self, format: str, *args: object) -> None:
            pass

    return ConfigRequestHandler


def _validate_submission(values: dict[str, str | None]) -> tuple[str, ...]:
    errors: list[str] = []

    locale = _clean(values.get(LOCALE_VARIABLE))
    if locale:
        try:
            validate_locale(locale)
        except ConfigError as error:
            errors.append(str(error))

    timezone_name = _clean(values.get(TIMEZONE_VARIABLE))
    if timezone_name:
        try:
            validate_timezone(timezone_name)
        except ConfigError as error:
            errors.append(str(error))

    try:
        parse_temperature_unit(_clean(values.get(TEMPERATURE_UNIT_VARIABLE)))
    except ConfigError as error:
        errors.append(str(error))

    latitude, latitude_error = _parse_optional_float(
        _clean(values.get(WEATHER_LATITUDE_VARIABLE)), WEATHER_LATITUDE_VARIABLE
    )
    longitude, longitude_error = _parse_optional_float(
        _clean(values.get(WEATHER_LONGITUDE_VARIABLE)), WEATHER_LONGITUDE_VARIABLE
    )

    for error in (latitude_error, longitude_error):
        if error:
            errors.append(error)

    if not latitude_error and not longitude_error:
        try:
            validate_weather_settings(latitude=latitude, longitude=longitude)
        except ConfigError as error:
            errors.append(str(error))

    mail_host = _clean(values.get(MAIL_HOST_VARIABLE))
    mail_username = _clean(values.get(MAIL_USERNAME_VARIABLE))
    mail_password = _clean(values.get(MAIL_PASSWORD_VARIABLE))
    mail_mailbox = _clean(values.get(MAIL_MAILBOX_VARIABLE)) or DEFAULT_MAIL_MAILBOX

    mail_port, mail_port_error = _parse_optional_int(
        _clean(values.get(MAIL_PORT_VARIABLE)), MAIL_PORT_VARIABLE
    )

    if mail_port_error:
        errors.append(mail_port_error)
    else:
        try:
            validate_mail_settings(
                host=mail_host,
                port=mail_port if mail_port is not None else DEFAULT_MAIL_PORT,
                username=mail_username,
                password=mail_password,
                mailbox=mail_mailbox,
            )
        except ConfigError as error:
            errors.append(str(error))

    return tuple(errors)


def _write_submission(env_file: Path, values: dict[str, str | None]) -> None:
    for field in _FIELDS:
        set_key(
            env_file,
            field.variable,
            _clean(values.get(field.variable)) or "",
            quote_mode="never",
        )


def _parse_optional_float(value: str | None, variable: str) -> tuple[float | None, str | None]:
    if value is None:
        return None, None

    try:
        return float(value), None
    except ValueError:
        return None, f"Invalid numeric value for {variable}: {value}"


def _parse_optional_int(value: str | None, variable: str) -> tuple[int | None, str | None]:
    if value is None:
        return None, None

    try:
        return int(value), None
    except ValueError:
        return None, f"Invalid numeric value for {variable}: {value}"


def _clean(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    return normalized or None


def _render_page(
    values: dict[str, str | None],
    *,
    errors: tuple[str, ...],
    saved: bool,
) -> str:
    fields_html = "\n".join(_render_field(field, values) for field in _FIELDS)

    banner_html = ""
    if saved:
        banner_html = '<p class="banner banner-success">Configuration saved.</p>'
    elif errors:
        items = "".join(f"<li>{html.escape(error)}</li>" for error in errors)
        banner_html = f'<div class="banner banner-error"><ul>{items}</ul></div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Novachrono Configuration</title>
<style>
  body {{ font-family: sans-serif; max-width: 40rem; margin: 2rem auto; padding: 0 1rem; }}
  label {{ display: block; margin-top: 1rem; font-weight: bold; }}
  input, select {{ width: 100%; padding: 0.4rem; box-sizing: border-box; }}
  .help {{ font-weight: normal; font-size: 0.85rem; color: #555; }}
  .banner-error {{ background: #fdecea; border: 1px solid #f5c6cb; padding: 0.75rem 1rem; }}
  .banner-success {{ background: #e6f4ea; border: 1px solid #b7dfb9; padding: 0.5rem 1rem; }}
  button {{ margin-top: 1.5rem; padding: 0.5rem 1.5rem; }}
</style>
</head>
<body>
<h1>Novachrono Configuration</h1>
<p>Changes are written to the local <code>.env</code> file.</p>
{banner_html}
<form method="post">
{fields_html}
<button type="submit">Save</button>
</form>
</body>
</html>
"""


def _render_field(field: _Field, values: dict[str, str | None]) -> str:
    current_value = values.get(field.variable) or ""
    escaped_value = html.escape(current_value)
    escaped_label = html.escape(field.label)

    help_html = (
        f' <span class="help">{html.escape(field.help_text)}</span>' if field.help_text else ""
    )

    if field.choices:
        options = "\n".join(
            f'<option value="{html.escape(choice)}"'
            f"{' selected' if choice == current_value else ''}>{html.escape(choice)}</option>"
            for choice in field.choices
        )
        input_html = f'<select name="{field.variable}">\n{options}\n</select>'
    else:
        input_html = (
            f'<input type="{field.input_type}" name="{field.variable}" value="{escaped_value}">'
        )

    return f"<label>{escaped_label}{help_html}\n{input_html}\n</label>"
