# Novachrono

Novachrono is a self-hosted dashboard renderer for the [Divoom Times Gate](https://divoom.com/).

It renders a consistent five-screen dashboard, generates local previews, and sends static or animated widgets to a Times Gate through its local network API.

> Novachrono is currently in an early development stage. Features, configuration, and architecture may change before the first stable release.

## Current Status

The following functionality is currently available:

- rendering of five 128 × 128 pixel panels
- shared custom HUD-style visual design
- unread-mail notifications widget using IMAP
- Microsoft Teams notifications widget using Microsoft Graph
- current weather widget using live Open-Meteo data
- animated rain and fog weather states
- Celsius and Fahrenheit display support
- German and English UI localization
- animated clock and date widget
- Pokémon GO raid boss widget using live ScrapedDuck data
- Pokémon name localization through PokeAPI
- rotating raid-boss display when multiple bosses are active
- combined local dashboard preview
- targeted static-image upload to individual Times Gate displays
- native multi-frame animation upload to individual Times Gate displays
- complete five-display dashboard upload
- local Times Gate connection check
- `.env`-based configuration
- local web GUI for editing configuration
- command-line interface powered by Typer
- automated tests with pytest
- formatting and linting with Ruff
- security checks with Bandit and pip-audit

The current display assignment is:

1. **Mail notifications**
2. **Current weather**
3. **Clock and date**
4. **Pokémon GO raids**
5. **Microsoft Teams notifications**

All panels use the same custom Novachrono design rather than reproducing the standard Divoom dashboard.

## Goals

Novachrono aims to provide:

- a coherent visual interface across all five Times Gate displays
- independently rendered 128 × 128 pixel widgets
- native device animations where they improve the display
- local previews without requiring a physical Times Gate
- configurable data sources and display settings
- resilient handling of unavailable APIs and network services
- simple deployment on a Raspberry Pi or another always-on device
- a small and understandable Python codebase
- clear separation between rendering, configuration, data retrieval, and device communication

## Non-Goals

Novachrono is not intended to be:

- a general-purpose home automation platform
- a replacement for the official Divoom application
- a network-attached storage solution
- an enterprise dashboard framework
- a universal plugin platform
- dependent on a specific hosting device

A Raspberry Pi may run Novachrono alongside other services, but those services are outside the scope of this repository.

## How It Works

Novachrono does not install applications directly on the Times Gate.

It runs on another device in the same local network:

```text
External data sources
        |
        v
   Novachrono
        |
        +-- loads configuration
        +-- retrieves and normalizes data
        +-- renders 128 x 128 pixel panels and animation frames
        +-- generates a local dashboard preview
        +-- sends static images or animations to the Times Gate
        |
        v
Divoom Times Gate
```

Each Times Gate display can be updated independently.

The current implementation can send individual rendered widgets, native multi-frame animations, or the complete dashboard.

Automatic scheduling, change detection, retries, and recovery behavior are planned.

## Architecture

The source tree separates the main responsibilities:

```text
src/novachrono/
├── __init__.py
├── __main__.py
├── cli.py
├── config.py
├── dashboard.py
├── i18n.py
├── mail.py
├── pokemon_go.py
├── preview.py
├── teams.py
├── units.py
├── weather.py
├── webconfig.py
├── design/
│   ├── __init__.py
│   ├── components.py
│   └── theme.py
├── outputs/
│   ├── __init__.py
│   └── times_gate.py
├── sources/
│   ├── __init__.py
│   ├── imap_mail.py
│   ├── ms_graph_teams.py
│   ├── open_meteo.py
│   ├── pokeapi.py
│   ├── pokemon_artwork.py
│   └── scraped_duck.py
└── widgets/
    ├── __init__.py
    ├── clock.py
    ├── mail/
    │   ├── __init__.py
    │   └── notifications.py
    ├── pokemon_go/
    │   ├── __init__.py
    │   └── raid_bosses.py
    ├── teams/
    │   ├── __init__.py
    │   └── notifications.py
    └── weather/
        ├── __init__.py
        ├── current.py
        └── icons.py
```

The main data flow is:

```text
External source
        |
        v
Source adapter
        |
        v
Normalized application model
        |
        v
Widget renderer
        |
        v
Pillow image / animation frames
        |
        +-- local preview
        |
        +-- Times Gate output
```

### Widgets

Widgets render 128 × 128 pixel Pillow images.

Some widgets can additionally render multiple frames for native Times Gate animations.

Widgets do not:

- perform network requests
- access environment variables
- communicate directly with the Times Gate

Current widgets:

- mail notifications
- current weather
- clock and date
- Pokémon GO raids
- Microsoft Teams notifications

Planned widgets include:

- GitHub status
- calendar information
- system status

### Mail Data

Unread-mail notifications are retrieved directly from a mail account over IMAP, using the standard library `imaplib`.

Novachrono retrieves:

- the number of unread messages in a configured mailbox
- the sender and subject of the most recently received unread message

The mailbox is opened read-only and messages are fetched with `BODY.PEEK`, so checking for unread mail never marks messages as read.

Mail is entirely optional. If host, username, or password are not configured, the mail widget renders a "no new mail" state without attempting a network connection.

If mail is configured but temporarily unreachable, `preview` and `send-dashboard` fall back to that same state instead of failing outright; `send-mail` reports the error directly, since it was asked for mail specifically.

### Microsoft Teams Data

The Teams widget shows the latest message posted in one configured Microsoft Teams channel, retrieved from [Microsoft Graph](https://learn.microsoft.com/en-us/graph/overview).

Novachrono retrieves:

- the sender of the most recent, non-deleted message in the configured channel
- a plain-text preview of that message's body

Authentication uses the OAuth 2.0 client credentials flow (app-only, no interactive login) via the [`msal`](https://pypi.org/project/msal/) library. Each command run requests a short-lived access token directly from Microsoft Entra ID using the configured tenant, client ID, and client secret; no token is cached or stored on disk.

Because this uses application permissions rather than delegated (per-user) permissions, Microsoft Graph has no concept of "unread" for this widget. It always shows the latest channel message, not an unread count.

#### Azure Setup

Using the Teams widget requires an Azure AD app registration you control:

1. In the [Azure Portal](https://portal.azure.com/), register a new application under **Microsoft Entra ID → App registrations**.
2. Under **API permissions**, add the **Microsoft Graph** **Application** permission `ChannelMessage.Read.All` and have a tenant administrator grant admin consent.
3. Under **Certificates & secrets**, create a client secret and copy its value immediately (it is not shown again).
4. Note the application's **Tenant ID** and **Client ID**, and the target **Team ID** and **Channel ID** (visible in the Teams "Get link to channel" URL).

`ChannelMessage.Read.All` grants read access to channel messages across the tenant, not just one channel; only configure this for a tenant you administer and trust.

Teams is entirely optional. If tenant ID, client ID, client secret, team ID, or channel ID are not configured, the Teams widget renders a "no recent messages" state without contacting Microsoft Graph.

If Teams is configured but temporarily unreachable, `preview` and `send-dashboard` fall back to that same state instead of failing outright; `send-teams` reports the error directly, since it was asked for Teams specifically.

### Weather Data

Current weather data is provided by [Open-Meteo](https://open-meteo.com/).

Novachrono retrieves:

- current temperature
- current weather condition
- daily high temperature
- daily low temperature
- maximum precipitation probability
- day/night information

Provider-specific weather codes are normalized into Novachrono's own weather model before they reach the widget renderer.

Rain and fog use native multi-frame animations on the Times Gate.

Other weather conditions currently render as static panels.

Open-Meteo data is provided under the [CC BY 4.0 license](https://creativecommons.org/licenses/by/4.0/).

### Pokémon GO Data

Current five-star and Mega raid data is provided by [ScrapedDuck](https://github.com/bigfoott/ScrapedDuck).

ScrapedDuck provides:

- raid boss names
- raid tiers
- shiny availability
- artwork URLs

Shadow raids and unrelated raid tiers are currently excluded from the dashboard.

PokeAPI is used as a best-effort source for localized Pokémon species names.

If localization fails, Novachrono keeps the original ScrapedDuck name.

Artwork downloads are also best-effort. A missing or unavailable image does not prevent the raid widget from rendering.

If multiple relevant raid bosses are active, Novachrono renders multiple frames and lets the Times Gate rotate through them natively.

### Design

The `design` package contains visual elements shared between widgets:

- common HUD frame
- widget headers
- colors
- panel dimensions
- reusable drawing primitives
- reusable design constants

Widget-specific geometry remains inside the corresponding widget unless it becomes genuinely reusable.

The visual design intentionally accounts for the physical Times Gate display, where very small bright pixels can appear stronger than they do in a desktop PNG preview.

### Dashboard

The dashboard renderer creates a static five-panel snapshot and assigns widgets to display positions according to the configured display order.

Default assignments:

```text
Panel index 0 -> mail
Panel index 1 -> weather
Panel index 2 -> clock
Panel index 3 -> pokemon_go
Panel index 4 -> teams
```

The physical displays are therefore numbered 1 through 5, while internal panel indices range from 0 through 4.

The assignment is configurable through `NOVACHRONO_DISPLAY_ORDER` (see [Display Arrangement](#display-arrangement)) and is resolved at runtime by `dashboard.panel_index_for()`, which every single-widget `send-*` command and the combined `send-dashboard` command use instead of a fixed index.

Animation delivery is handled separately by the CLI and Times Gate output adapter.

### Configuration

`config.py` loads application settings from:

1. `.env`
2. process environment variables

Process environment variables override values from `.env`.

Configuration is normalized into an immutable `AppConfig` before it is used by the application.

### Configuration GUI

`webconfig.py` provides a small local web GUI for editing the `.env` file.

It binds to `127.0.0.1` by default so the configuration, including the Times Gate token, is not exposed to the local network.

The GUI reuses the same validation rules as `config.py` and shows inline errors instead of writing an invalid `.env` file.

The GUI also renders a live-looking thumbnail of each widget and lets you drag them into a new display order. Thumbnails use fixed sample data (not your real weather, mail, or Teams data) so the page loads instantly and never makes an external network call just by being opened. Dragging updates a hidden field that is saved together with the rest of the form.

### Internationalization

Small UI strings are translated through `i18n.py`.

Currently supported locales:

```text
de_DE
en_US
```

The current localized widget text includes the weather title:

```text
de_DE -> WETTER
en_US -> WEATHER
```

The clock uses a numeric time and date representation and therefore does not currently require locale-specific date formatting.

Pokémon species names are localized separately through PokeAPI.

### Units

Temperatures are stored internally as Celsius values.

The display unit can be configured as:

```text
C
F
```

Fahrenheit values are converted during rendering.

Weather typography adapts to wider values such as negative temperatures and three-digit Fahrenheit temperatures.

### Preview

The preview module combines one static image for each of the five panels into a single PNG file for local inspection.

Animations are not represented as animated files in the dashboard preview. The preview uses the static panel representation of each widget.

This allows visual development and most automated testing without access to physical hardware.

### Output Adapters

Output adapters deliver rendered images to external destinations.

The Times Gate adapter:

- communicates through the local Times Gate HTTP API
- validates panel indices
- validates image dimensions
- encodes panel images as Base64 JPEG data
- sends static images to individual displays
- sends native multi-frame animations
- uses one Times Gate picture ID across the frames of an animation
- translates network and device errors into application-specific exceptions

Animations are executed by the Times Gate itself.

Novachrono does not keep a Python process in a sleep/update loop to simulate animation.

### Command-Line Interface

The CLI is implemented with Typer.

Current commands:

```text
configure
preview
check-device
send-clock
send-weather
send-mail
send-teams
send-pokemon
send-dashboard
```

## Requirements

- Python 3.14
- [uv](https://docs.astral.sh/uv/)
- a Divoom Times Gate connected to the same local network for device-related commands
- local API access enabled in the Divoom application
- a local Times Gate token

The project includes `tzdata` so that IANA time zones such as `Europe/Berlin` also work consistently on platforms such as Windows.

## Installation

Clone the repository:

```shell
git clone https://github.com/drachenpapa/novachrono.git
cd novachrono
```

Install the locked project and development dependencies:

```shell
uv sync --locked --all-groups
```

Verify the installation:

```shell
uv run novachrono --help
```

## Configuration

Novachrono automatically loads a `.env` file from the current working directory.

Create your local configuration from the provided example.

### PowerShell

```powershell
Copy-Item .env.example .env
```

### Bash or Zsh

```shell
cp .env.example .env
```

The currently supported settings are:

```dotenv
NOVACHRONO_LOCALE=de_DE
NOVACHRONO_TIMEZONE=Europe/Berlin
NOVACHRONO_TEMPERATURE_UNIT=C

NOVACHRONO_WEATHER_LATITUDE=53.04771
NOVACHRONO_WEATHER_LONGITUDE=8.80169

NOVACHRONO_MAIL_HOST=
NOVACHRONO_MAIL_PORT=993
NOVACHRONO_MAIL_USERNAME=
NOVACHRONO_MAIL_PASSWORD=
NOVACHRONO_MAIL_MAILBOX=INBOX

NOVACHRONO_TEAMS_TENANT_ID=
NOVACHRONO_TEAMS_CLIENT_ID=
NOVACHRONO_TEAMS_CLIENT_SECRET=
NOVACHRONO_TEAMS_TEAM_ID=
NOVACHRONO_TEAMS_CHANNEL_ID=

NOVACHRONO_DISPLAY_ORDER=mail,weather,clock,pokemon_go,teams

NOVACHRONO_TIMES_GATE_HOST=192.168.1.100
NOVACHRONO_TIMES_GATE_TOKEN=replace-me
```

### Locale

Supported values:

```text
de_DE
en_US
```

Default:

```text
de_DE
```

### Timezone

Use an IANA timezone name such as:

```text
Europe/Berlin
Europe/London
America/New_York
```

Default:

```text
Europe/Berlin
```

### Temperature Unit

Supported values:

```text
C
F
```

The configuration parser also accepts:

```text
CELSIUS
FAHRENHEIT
```

Values are case-insensitive.

Default:

```text
C
```

### Weather Location

Weather data is retrieved for the configured WGS84 coordinates:

```text
NOVACHRONO_WEATHER_LATITUDE
NOVACHRONO_WEATHER_LONGITUDE
```

Latitude and longitude must either both be configured or both be omitted.

Valid ranges are:

```text
latitude  -> -90 to 90
longitude -> -180 to 180
```

### Mail Notifications

The mail widget connects to a mailbox over IMAP to show the unread-message count and the latest unread message's sender and subject.

```text
NOVACHRONO_MAIL_HOST
NOVACHRONO_MAIL_PORT
NOVACHRONO_MAIL_USERNAME
NOVACHRONO_MAIL_PASSWORD
NOVACHRONO_MAIL_MAILBOX
```

Host, username, and password must either all be configured or all be omitted. Leaving them empty disables the widget without an error.

Default port:

```text
993
```

Default mailbox:

```text
INBOX
```

Most providers require an app-specific password rather than your regular account password for IMAP access. Do not commit a real mail password.

### Microsoft Teams Notifications

The Teams widget connects to Microsoft Graph using app-only (client credentials) authentication to show the latest message in one configured channel.

```text
NOVACHRONO_TEAMS_TENANT_ID
NOVACHRONO_TEAMS_CLIENT_ID
NOVACHRONO_TEAMS_CLIENT_SECRET
NOVACHRONO_TEAMS_TEAM_ID
NOVACHRONO_TEAMS_CHANNEL_ID
```

All five values must either be configured together or all be omitted. Leaving them empty disables the widget without an error.

Setting these up requires an Azure AD app registration with the Microsoft Graph `ChannelMessage.Read.All` application permission, admin-consented by a tenant administrator. See [Microsoft Teams Data](#microsoft-teams-data) for the full setup steps.

Do not commit a real client secret.

### Display Arrangement

```text
NOVACHRONO_DISPLAY_ORDER
```

A comma-separated list assigning each widget to a physical display, in order from display 1 to display 5. It must contain each of the following exactly once:

```text
mail
weather
clock
pokemon_go
teams
```

Default:

```text
mail,weather,clock,pokemon_go,teams
```

The easiest way to change this is the drag-and-drop arrangement UI in `novachrono configure`, which writes this value for you. Editing it by hand works too, as long as all five names are present exactly once.

### Times Gate Host

The host must contain only the local IP address or hostname.

Correct:

```text
192.168.1.100
times-gate.local
```

Do not include:

```text
http://
https://
:9000
/divoom_api
```

The local API currently uses:

```text
http://<host>:9000/divoom_api
```

### Times Gate Token

The local Times Gate token is required for commands that communicate with the physical device.

Do not commit a real token.

### Environment Overrides

Process environment variables override values from `.env`.

For example:

```powershell
$env:NOVACHRONO_TEMPERATURE_UNIT = "F"
uv run novachrono preview
```

The Times Gate host and token can additionally be overridden through command-line options:

```shell
uv run novachrono check-device --host 192.168.1.100 --token replace-me
```

Using `--token` regularly is discouraged because command-line arguments may be stored in shell history or exposed to other processes.

## Usage

### Show Available Commands

```shell
uv run novachrono --help
```

### Edit Configuration in a Browser

```shell
uv run novachrono configure
```

This starts a local web server on `http://127.0.0.1:8765/` and opens it in your default browser.

The form is pre-filled with the current `.env` values and writes changes back to the same file after validating them.

At the top of the page, a "Display Arrangement" section shows each widget as a draggable card with a sample-data thumbnail. Drag the cards to change which physical display (1 through 5) each widget appears on, then click **Save** along with the rest of the form.

Use `--port` to choose another port, and `--no-open-browser` to skip opening a browser automatically:

```shell
uv run novachrono configure --port 9000 --no-open-browser
```

`--host` can bind to a different interface, but this is discouraged because it can expose your configuration, including the Times Gate token, to other devices on the network:

```shell
uv run novachrono configure --host 0.0.0.0
```

Stop the server with `Ctrl+C`.

### Generate a Local Dashboard Preview

```shell
uv run novachrono preview
```

The default output is:

```text
output/dashboard-preview.png
```

Choose another destination with:

```shell
uv run novachrono preview --output output/custom-preview.png
```

or:

```shell
uv run novachrono preview -o output/custom-preview.png
```

A physical Times Gate is not required to generate previews.

### Check the Times Gate Connection

```shell
uv run novachrono check-device
```

This sends a read-only configuration request to the configured Times Gate.

### Send the Clock Widget

```shell
uv run novachrono send-clock
```

The clock is assigned to physical display 3.

It uses a native Times Gate animation for the horizontal Horizon sweep indicator.

The current animation uses:

```text
26 frames
250 ms per frame
```

### Send the Weather Widget

```shell
uv run novachrono send-weather
```

The weather widget is assigned to physical display 2.

Weather data is retrieved from Open-Meteo using the configured coordinates.

Rain uses a native three-frame animation.

Fog uses a native ten-frame animation.

Other weather conditions currently use a static image.

### Send the Mail Widget

```shell
uv run novachrono send-mail
```

The mail widget is assigned to physical display 1.

Unread-mail data is retrieved live over IMAP using the configured account.

Unlike `preview` and `send-dashboard`, this command requires mail to be configured and reports an error if the mailbox cannot be reached.

### Send the Teams Widget

```shell
uv run novachrono send-teams
```

The Teams widget is assigned to physical display 5.

The latest channel message is retrieved live from Microsoft Graph using the configured Azure AD app registration.

Unlike `preview` and `send-dashboard`, this command requires Teams to be configured and reports an error if Microsoft Graph cannot be reached.

### Send the Pokémon GO Widget

```shell
uv run novachrono send-pokemon
```

The Pokémon GO widget is assigned to physical display 4.

Raid data and artwork URLs are retrieved from ScrapedDuck.

PokeAPI is used to localize Pokémon names where possible.

Artwork downloads and name localization are best-effort and do not prevent the widget from rendering when an external request fails.

When multiple relevant raid bosses are active, the widget rotates through them using a native Times Gate animation.

### Send the Complete Dashboard

```shell
uv run novachrono send-dashboard
```

This renders all five panels and sends them to the Times Gate one after another.

Widgets with multiple frames are delivered as native Times Gate animations.

Currently this means:

- the clock is animated
- rain is animated
- fog is animated
- Pokémon GO raids are animated when multiple bosses are active
- the mail widget, the Teams widget, and all other weather states are static

If mail or Teams is configured but cannot be reached, the affected panel falls back to its "nothing to show" state instead of failing the whole dashboard; a warning is printed to explain why.

If one or more displays fail, Novachrono continues attempting the remaining displays and reports the affected display numbers afterward.

### Run as a Python Module

The package also supports:

```shell
uv run python -m novachrono preview
```

## Local Development

Install the project and all development dependencies:

```shell
uv sync --locked --all-groups
```

Format the source code:

```shell
uv run ruff format .
```

Check formatting without modifying files:

```shell
uv run ruff format --check .
```

Run linting:

```shell
uv run ruff check .
```

Run security linting:

```shell
uv run bandit -r src
```

Audit Python dependencies:

```shell
uv run pip-audit
```

Run the test suite:

```shell
uv run pytest
```

Generate a dashboard preview:

```shell
uv run novachrono preview
```

A typical complete local verification is:

```shell
uv run ruff format --check .
uv run ruff check .
uv run bandit -r src
uv run pip-audit
uv run pytest
uv run novachrono preview
```

Hardware-related changes should additionally be smoke-tested against a physical Times Gate when available:

```shell
uv run novachrono send-clock
uv run novachrono send-dashboard
```

Most automated tests do not require access to a physical Times Gate.

Network calls to external APIs and the device are mocked in the test suite.

## Testing

The test suite covers:

- CLI behavior and delivery routing
- application configuration
- Celsius and Fahrenheit conversion
- negative and three-digit temperatures
- internationalization
- dashboard composition
- mail rendering and unread-state handling
- IMAP request, response, and header-decoding handling
- Teams rendering and no-activity-state handling
- Microsoft Graph authentication, request, response, and message-parsing handling
- weather rendering and animation
- Open-Meteo request, response, and weather-code handling
- ScrapedDuck raid parsing
- PokeAPI name localization
- Pokémon artwork retrieval and normalization
- Pokémon GO raid rendering and rotation
- clock rendering and animation
- shared design invariants
- preview generation
- Times Gate static-image request generation
- Times Gate native-animation request generation
- Times Gate response and error handling

Renderer tests focus primarily on behavior and deterministic output instead of maintaining large fragile golden-image snapshots.

Small targeted pixel assertions are used only where they protect a specific visual invariant.

## Security

Never commit:

- Divoom local tokens
- GitHub personal access tokens
- IMAP mail passwords
- Microsoft Entra ID / Azure AD client secrets
- private calendar feed URLs
- credentials
- `.env`
- local configuration containing personal data

`.env.example` contains documentation values only and is intended to remain in version control.

If a real token is accidentally committed, revoke or replace it where possible.

Removing a token only from the latest source file does not remove it from Git history.

Potential security issues should be reported according to the [Security Policy](SECURITY.md).

## Roadmap

### Foundation

- [x] create Python project structure
- [x] render five 128 × 128 panels
- [x] create a shared Novachrono HUD design
- [x] generate a combined dashboard preview
- [x] add automated formatting, linting, testing, and security checks
- [x] add a Typer-based CLI
- [x] add `.env`-based configuration
- [x] add a local web GUI for editing configuration
- [x] add configurable display arrangement
- [x] add widget preview and drag-and-drop rearrangement to the configuration GUI
- [x] add basic internationalization
- [x] add configurable Celsius and Fahrenheit rendering

### Clock Widget

- [x] render current time and date
- [x] place the clock on display 3
- [x] refine typography and spacing for the physical display
- [x] integrate the shared HUD frame
- [x] add native Horizon sweep animation

### Weather Widget

- [x] create current-weather widget
- [x] render weather conditions with custom icons
- [x] render current temperature
- [x] render high and low temperatures
- [x] render precipitation probability
- [x] support Celsius and Fahrenheit
- [x] support localized widget title
- [x] refine layout for the physical display
- [x] connect a real weather data source
- [x] map provider weather conditions to the internal weather model
- [x] remove demo weather data
- [x] animate rain
- [x] animate fog

### Mail Notifications Widget

- [x] research a reliable, credential-light mail data source
- [x] retrieve the unread-mail count over IMAP
- [x] retrieve the latest unread message's sender and subject
- [x] render the mail notifications widget
- [x] place mail notifications on display 1
- [x] support disabling the widget when mail is not configured
- [x] treat mail as best-effort for the combined dashboard

### Microsoft Teams Notifications Widget

- [x] research a Microsoft Graph authentication approach appropriate for a headless CLI
- [x] retrieve the latest message in a configured Teams channel
- [x] render the Teams notifications widget
- [x] place Teams notifications on display 5
- [x] support disabling the widget when Teams is not configured
- [x] treat Teams as best-effort for the combined dashboard
- [x] document the required Azure AD app registration and Graph permission

### Times Gate Integration

- [x] connect through the local Times Gate API
- [x] authenticate with the local token
- [x] check device connectivity
- [x] send an image to an individual display
- [x] send native multi-frame animations
- [x] send the complete dashboard
- [ ] avoid sending unchanged images
- [ ] add retry and recovery behavior

### Pokémon GO Widget

- [x] research a reliable Pokémon GO raid data source
- [x] retrieve five-star and Mega raid bosses
- [x] exclude shadow and unrelated raid tiers
- [x] retrieve raid artwork
- [x] localize Pokémon names
- [x] render the Pokémon GO raid widget
- [x] support multiple simultaneous raid bosses
- [x] rotate multiple bosses using native animation

### Additional Widgets

- [ ] implement GitHub status data
- [ ] add configurable calendar information
- [ ] add system-status information

### Runtime and Deployment

- [ ] add scheduled dashboard updates
- [ ] make update intervals configurable
- [ ] avoid unnecessary unchanged updates
- [ ] add retry and recovery behavior
- [ ] add structured logging
- [ ] support graceful shutdown
- [ ] document Raspberry Pi installation
- [ ] provide a systemd service example
- [ ] optionally provide a container image

## Planned Configuration

Future configuration may include:

- GitHub repositories and token
- calendar feeds
- widget update intervals
- visual theme settings

The existing environment-variable configuration should remain small and understandable.

Additional structure should only be introduced when the project genuinely requires it.

## Contributing

Contributions are welcome.

Before contributing, please read:

- [Contributing Guidelines](CONTRIBUTING.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Support and Help](SUPPORT.md)

## Project Name

The name Novachrono is inspired by Julius Novachrono and his association with time magic in *Black Clover*.

The name also reflects the project's relationship with the Divoom Times Gate and its focus on time-based and contextual information.

## Trademarks and Third-Party Services

Novachrono is an independent hobby project.

It is not affiliated with, endorsed by, or sponsored by:

- Divoom
- Nintendo
- The Pokémon Company
- Niantic
- GitHub
- the creators or publishers of *Black Clover*

Product names, trademarks, logos, and other third-party assets belong to their respective owners.

Third-party images, fonts, icons, APIs, feeds, and other assets must only be included when their licenses and terms permit redistribution.

## Citation

Citation metadata is provided in [`CITATION.cff`](CITATION.cff).

## License

Novachrono is licensed under the [MIT License](LICENSE).
