import hashlib
import io
import json
import socket
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Final
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image

from novachrono.design import PANEL_COUNT, PANEL_SIZE

DEFAULT_API_PORT: Final = 80
DEFAULT_API_PATH: Final = "/post"
DEFAULT_TIMEOUT_SECONDS: Final = 8.0
DEFAULT_FETCH_TIMEOUT_SECONDS: Final = 20.0

LOCAL_API_SCHEME: Final = "http"


class TimesGateError(RuntimeError):
    """Raised when communication with the Times Gate fails."""


@dataclass(frozen=True)
class TimesGateConfig:
    """Connection settings for a Times Gate."""

    host: str
    local_token: str
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    fetch_timeout_seconds: float = DEFAULT_FETCH_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        normalized_host = self.host.strip()

        if not normalized_host:
            raise ValueError("Times Gate host must not be empty")

        if (
            "://" in normalized_host
            or any(character in normalized_host for character in (":", "/", "?", "#"))
            or any(character.isspace() for character in normalized_host)
        ):
            raise ValueError("Times Gate host must contain only the hostname or IP address")

        if not self.local_token.strip():
            raise ValueError("Times Gate local token must not be empty")

        if self.timeout_seconds <= 0:
            raise ValueError("Times Gate timeout must be greater than zero")

        if self.fetch_timeout_seconds <= 0:
            raise ValueError("Times Gate fetch timeout must be greater than zero")

        object.__setattr__(
            self,
            "host",
            normalized_host,
        )

        object.__setattr__(
            self,
            "local_token",
            self.local_token.strip(),
        )

    @property
    def api_url(self) -> str:
        """Return the local Times Gate API URL."""

        # The Times Gate local API is intentionally accessed over HTTP.
        return (  # NOSONAR(S5332)
            f"{LOCAL_API_SCHEME}://{self.host}:{DEFAULT_API_PORT}{DEFAULT_API_PATH}"
        )


class TimesGateClient:
    """Communicate with a Divoom Times Gate over the local network.

    The Times Gate firmware accepts pushed image data (`Draw/SendHttpGif`) but
    does not actually draw it; it only shows a picture it downloads itself via
    `Device/PlayGif`. Every send therefore runs a short-lived local HTTP server
    that serves one GIF and waits for the device to fetch it, rather than
    pushing pixels directly.
    """

    def __init__(
        self,
        config: TimesGateConfig,
    ) -> None:
        self._config = config

    @property
    def config(
        self,
    ) -> TimesGateConfig:
        """Return the client configuration."""

        return self._config

    def get_configuration(
        self,
    ) -> dict[str, Any]:
        """Retrieve the current Times Gate configuration."""

        return self._post(
            {
                "Command": "Channel/GetAllConf",
                "LocalToken": self._config.local_token,
            }
        )

    def send_image(
        self,
        panel_index: int,
        image: Image.Image,
    ) -> dict[str, Any]:
        """Show one static image on one Times Gate display."""

        _validate_panel_index(panel_index)
        _validate_image_size(image)

        return self._play(
            panel_index,
            encode_gif((image,)),
        )

    def send_animation(
        self,
        panel_index: int,
        images: Sequence[Image.Image],
        *,
        frame_duration_ms: int,
    ) -> dict[str, Any]:
        """Show a native multi-frame animation on one Times Gate display."""

        _validate_panel_index(panel_index)

        _validate_animation(
            images,
            frame_duration_ms=frame_duration_ms,
        )

        return self._play(
            panel_index,
            encode_gif(
                images,
                frame_duration_ms=frame_duration_ms,
            ),
        )

    def _play(
        self,
        panel_index: int,
        gif_bytes: bytes,
    ) -> dict[str, Any]:
        device_address = self._resolve_device_address()

        with _FrameServer(
            gif_bytes,
            allowed_client=device_address,
        ) as server:
            local_host = self._local_address(device_address)
            url = f"http://{local_host}:{server.port}{server.path}"

            response = self._post(
                {
                    "Command": "Device/PlayGif",
                    "LocalToken": self._config.local_token,
                    "LcdArray": _create_lcd_array(panel_index),
                    "FileName": [url],
                }
            )

            if not server.wait_for_fetch(self._config.fetch_timeout_seconds):
                raise TimesGateError(f"Times Gate did not fetch the frame from {url} in time")

        return response

    def _resolve_device_address(
        self,
    ) -> str:
        try:
            return socket.gethostbyname(self._config.host)
        except OSError as error:
            raise TimesGateError(
                f"Could not resolve Times Gate host {self._config.host!r}: {error}"
            ) from error

    def _local_address(
        self,
        device_address: str,
    ) -> str:
        """Return the local address the Times Gate can reach us at."""

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            try:
                probe.connect((device_address, DEFAULT_API_PORT))
            except OSError as error:
                raise TimesGateError(
                    f"Could not determine a local address reachable from {device_address}: {error}"
                ) from error

            return probe.getsockname()[0]

    def _post(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        request = Request(
            url=self._config.api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(  # nosec B310 - URL is limited to the local device API
                request,
                timeout=self._config.timeout_seconds,
            ) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as error:
            raise TimesGateError(
                f"Times Gate returned HTTP {error.code}: {error.reason}"
            ) from error
        except URLError as error:
            raise TimesGateError(
                f"Could not reach Times Gate at {self._config.api_url}: {error.reason}"
            ) from error
        except TimeoutError as error:
            raise TimesGateError(
                f"Connection to Times Gate at {self._config.api_url} timed out"
            ) from error
        except UnicodeDecodeError as error:
            raise TimesGateError("Times Gate returned an invalid UTF-8 response") from error

        try:
            response_data = json.loads(response_body)
        except json.JSONDecodeError as error:
            raise TimesGateError(f"Times Gate returned invalid JSON: {response_body!r}") from error

        if not isinstance(
            response_data,
            dict,
        ):
            raise TimesGateError("Times Gate returned an unexpected response")

        _raise_for_api_error(response_data)

        return response_data


class _FrameServer:
    """A short-lived local HTTP server that serves exactly one frame.

    The Times Gate downloads a frame by URL in a separate request after
    `Device/PlayGif` returns, so the server must stay up until that request
    arrives (or the wait times out), and it answers only the configured
    device so a frame meant for one screen cannot be read by another device
    on the network.
    """

    def __init__(
        self,
        gif_bytes: bytes,
        *,
        allowed_client: str,
    ) -> None:
        self._path = f"/{_frame_path(gif_bytes)}"
        self._fetched = threading.Event()

        handler_class = _build_frame_handler(
            path=self._path,
            body=gif_bytes,
            allowed_client=allowed_client,
            fetched=self._fetched,
        )
        self._httpd = HTTPServer(("0.0.0.0", 0), handler_class)  # nosec B104 - device must reach this server
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    @property
    def port(
        self,
    ) -> int:
        """The port the frame is served on."""

        return self._httpd.server_address[1]

    @property
    def path(
        self,
    ) -> str:
        """The path the frame is served at."""

        return self._path

    def __enter__(
        self,
    ) -> _FrameServer:
        self._thread.start()
        return self

    def __exit__(
        self,
        *exc_info: object,
    ) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=2)

    def wait_for_fetch(
        self,
        timeout_seconds: float,
    ) -> bool:
        """Wait until the device has fetched the frame."""

        return self._fetched.wait(timeout_seconds)


def _build_frame_handler(
    *,
    path: str,
    body: bytes,
    allowed_client: str,
    fetched: threading.Event,
) -> type[BaseHTTPRequestHandler]:
    class _FrameRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.client_address[0] != allowed_client or self.path != path:
                self.send_response(404)
                self.end_headers()
                return

            self.send_response(200)
            self.send_header("Content-Type", "image/gif")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

            fetched.set()

        def log_message(
            self,
            format: str,
            *args: object,
        ) -> None:
            # The device polling this server is not worth logging.
            pass

    return _FrameRequestHandler


def encode_gif(
    images: Sequence[Image.Image],
    *,
    frame_duration_ms: int | None = None,
) -> bytes:
    """Encode one or more Pillow images as a GIF the Times Gate can display."""

    buffer = io.BytesIO()

    first_frame, *remaining_frames = (image.convert("RGB") for image in images)

    if remaining_frames:
        first_frame.save(
            buffer,
            format="GIF",
            save_all=True,
            append_images=remaining_frames,
            duration=frame_duration_ms,
            loop=0,
        )
    else:
        first_frame.save(
            buffer,
            format="GIF",
        )

    return buffer.getvalue()


def _frame_path(
    gif_bytes: bytes,
) -> str:
    # The hash is part of the file name so an unchanged frame keeps its link
    # and a changed one is never mistaken for the previous frame.
    digest = hashlib.sha256(gif_bytes).hexdigest()[:16]

    return f"frame-{digest}.gif"


def _create_lcd_array(
    panel_index: int,
) -> list[int]:
    lcd_array = [0] * PANEL_COUNT
    lcd_array[panel_index] = 1

    return lcd_array


def _validate_panel_index(
    panel_index: int,
) -> None:
    if not 0 <= panel_index < PANEL_COUNT:
        raise ValueError(f"Panel index must be between 0 and {PANEL_COUNT - 1}")


def _validate_image_size(
    image: Image.Image,
) -> None:
    expected_size = (
        PANEL_SIZE,
        PANEL_SIZE,
    )

    if image.size != expected_size:
        raise ValueError(f"Image has size {image.size}; expected {expected_size}")


def _validate_animation(
    images: Sequence[Image.Image],
    *,
    frame_duration_ms: int,
) -> None:
    if not images:
        raise ValueError("Animation must contain at least one image")

    if frame_duration_ms <= 0:
        raise ValueError("Frame duration must be greater than zero")

    for image in images:
        _validate_image_size(image)


def _raise_for_api_error(
    response_data: dict[str, Any],
) -> None:
    return_code = response_data.get(
        "ReturnCode",
        response_data.get("error_code"),
    )

    if return_code in (
        None,
        0,
    ):
        return

    message = response_data.get(
        "ReturnMessage",
        response_data.get(
            "error_message",
            "unknown error",
        ),
    )

    raise TimesGateError(f"Times Gate rejected the request with code {return_code}: {message}")
