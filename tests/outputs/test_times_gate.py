import io
import json
import threading
from collections.abc import Callable
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest
from PIL import Image

from novachrono.design import PANEL_COUNT, PANEL_SIZE
from novachrono.outputs.times_gate import (
    TimesGateClient,
    TimesGateConfig,
    TimesGateError,
    _FrameServer,
    encode_gif,
)

HOST = "127.0.0.1"
TOKEN = "secret"
API_URL = "http://127.0.0.1:80/post"


def _create_panel(
    color: str = "#17132F",
) -> Image.Image:
    return Image.new(
        mode="RGB",
        size=(PANEL_SIZE, PANEL_SIZE),
        color=color,
    )


def _create_client(
    fetch_timeout_seconds: float = 2.0,
) -> TimesGateClient:
    return TimesGateClient(
        TimesGateConfig(
            host=HOST,
            local_token=TOKEN,
            fetch_timeout_seconds=fetch_timeout_seconds,
        )
    )


def _create_response(
    payload: object,
) -> MagicMock:
    return _create_raw_response(json.dumps(payload))


def _create_raw_response(
    body: str,
) -> MagicMock:
    return _create_bytes_response(body.encode("utf-8"))


def _create_bytes_response(
    body: bytes,
) -> MagicMock:
    response = MagicMock()
    response.read.return_value = body

    context_manager = MagicMock()
    context_manager.__enter__.return_value = response
    context_manager.__exit__.return_value = False

    return context_manager


def _respond_and_fetch_frame(
    success_payload: object,
) -> Callable[[Request, float], MagicMock]:
    """Answer the command instantly, then fetch the served frame in the background.

    Mirrors how a real Times Gate behaves: `Device/PlayGif` returns right
    away while the picture is downloaded in a separate request.
    """

    def side_effect(
        request: Request,
        timeout: float,
    ) -> MagicMock:
        payload = json.loads(request.data.decode("utf-8"))
        url = payload["FileName"][0]

        threading.Thread(
            target=urlopen,
            args=(url,),
            daemon=True,
        ).start()

        return _create_response(success_payload)

    return side_effect


def test_config_creates_expected_api_url() -> None:
    config = TimesGateConfig(
        host=HOST,
        local_token=TOKEN,
    )

    assert config.api_url == API_URL


def test_config_strips_host_and_token() -> None:
    config = TimesGateConfig(
        host=f" {HOST} ",
        local_token=f" {TOKEN} ",
    )

    assert config.host == HOST
    assert config.local_token == TOKEN


@pytest.mark.parametrize(
    "host",
    [
        "",
        "   ",
        "http://192.168.178.50",
        "https://192.168.178.50",
        f"{HOST}:9000",
        f"{HOST}/divoom_api",
        f"{HOST}?mode=test",
        f"{HOST}#fragment",
        "times gate.local",
    ],
)
def test_config_rejects_invalid_host(
    host: str,
) -> None:
    with pytest.raises(ValueError):
        TimesGateConfig(
            host=host,
            local_token=TOKEN,
        )


def test_config_rejects_empty_token() -> None:
    with pytest.raises(
        ValueError,
        match="local token must not be empty",
    ):
        TimesGateConfig(
            host=HOST,
            local_token=" ",
        )


def test_config_rejects_invalid_timeout() -> None:
    with pytest.raises(
        ValueError,
        match="timeout must be greater than zero",
    ):
        TimesGateConfig(
            host=HOST,
            local_token=TOKEN,
            timeout_seconds=0,
        )


def test_config_rejects_invalid_fetch_timeout() -> None:
    with pytest.raises(
        ValueError,
        match="fetch timeout must be greater than zero",
    ):
        TimesGateConfig(
            host=HOST,
            local_token=TOKEN,
            fetch_timeout_seconds=0,
        )


def test_encode_gif_returns_single_frame_gif() -> None:
    gif_bytes = encode_gif((_create_panel(),))

    with Image.open(io.BytesIO(gif_bytes)) as image:
        assert image.format == "GIF"
        assert image.size == (PANEL_SIZE, PANEL_SIZE)
        assert getattr(image, "n_frames", 1) == 1


def test_encode_gif_returns_multi_frame_gif() -> None:
    gif_bytes = encode_gif(
        (
            _create_panel("#FF0000"),
            _create_panel("#00FF00"),
            _create_panel("#0000FF"),
        ),
        frame_duration_ms=5_000,
    )

    with Image.open(io.BytesIO(gif_bytes)) as image:
        assert image.format == "GIF"
        assert image.n_frames == 3


@pytest.mark.parametrize(
    "panel_index",
    [-1, PANEL_COUNT],
)
def test_send_image_rejects_invalid_panel_index(
    panel_index: int,
) -> None:
    client = _create_client()

    with pytest.raises(
        ValueError,
        match="Panel index must be between",
    ):
        client.send_image(
            panel_index=panel_index,
            image=_create_panel(),
        )


def test_send_image_rejects_invalid_image_size() -> None:
    client = _create_client()

    invalid_image = Image.new(
        mode="RGB",
        size=(64, 64),
    )

    with pytest.raises(
        ValueError,
        match="Image has size",
    ):
        client.send_image(
            panel_index=2,
            image=invalid_image,
        )


@pytest.mark.parametrize(
    "panel_index",
    [-1, PANEL_COUNT],
)
def test_send_animation_rejects_invalid_panel_index(
    panel_index: int,
) -> None:
    client = _create_client()

    with pytest.raises(
        ValueError,
        match="Panel index must be between",
    ):
        client.send_animation(
            panel_index=panel_index,
            images=(
                _create_panel(),
                _create_panel(),
            ),
            frame_duration_ms=10_000,
        )


def test_send_animation_rejects_empty_animation() -> None:
    client = _create_client()

    with pytest.raises(
        ValueError,
        match="at least one image",
    ):
        client.send_animation(
            panel_index=2,
            images=(),
            frame_duration_ms=10_000,
        )


def test_send_animation_rejects_invalid_frame_duration() -> None:
    client = _create_client()

    with pytest.raises(
        ValueError,
        match="Frame duration must be greater than zero",
    ):
        client.send_animation(
            panel_index=2,
            images=(
                _create_panel(),
                _create_panel(),
            ),
            frame_duration_ms=0,
        )


@patch("novachrono.outputs.times_gate.urlopen")
def test_send_animation_validates_all_images_before_upload(
    mocked_urlopen: MagicMock,
) -> None:
    invalid_image = Image.new(
        mode="RGB",
        size=(64, 64),
    )

    with pytest.raises(
        ValueError,
        match="Image has size",
    ):
        _create_client().send_animation(
            panel_index=2,
            images=(
                _create_panel(),
                invalid_image,
            ),
            frame_duration_ms=10_000,
        )

    mocked_urlopen.assert_not_called()


@patch("novachrono.outputs.times_gate.urlopen")
def test_get_configuration_sends_expected_request(
    mocked_urlopen: MagicMock,
) -> None:
    mocked_urlopen.return_value = _create_response(
        {
            "Command": "Channel/GetAllConf",
            "ReturnCode": 0,
            "ReturnMessage": "",
        }
    )

    response = _create_client().get_configuration()

    assert response["ReturnCode"] == 0

    request = mocked_urlopen.call_args.args[0]
    payload = json.loads(request.data.decode("utf-8"))

    assert request.full_url == API_URL

    assert payload == {
        "Command": "Channel/GetAllConf",
        "LocalToken": TOKEN,
    }


@patch("novachrono.outputs.times_gate.urlopen")
def test_send_image_asks_the_device_to_play_a_gif_it_downloads_itself(
    mocked_urlopen: MagicMock,
) -> None:
    mocked_urlopen.side_effect = _respond_and_fetch_frame({"ReturnCode": 0})

    response = _create_client().send_image(
        panel_index=2,
        image=_create_panel(),
    )

    assert response["ReturnCode"] == 0

    request = mocked_urlopen.call_args.args[0]
    payload = json.loads(request.data.decode("utf-8"))

    assert payload["Command"] == "Device/PlayGif"
    assert payload["LocalToken"] == TOKEN
    assert payload["LcdArray"] == [0, 0, 1, 0, 0]
    assert len(payload["FileName"]) == 1
    assert payload["FileName"][0].endswith(".gif")


@patch("novachrono.outputs.times_gate.urlopen")
def test_send_animation_serves_one_multi_frame_gif(
    mocked_urlopen: MagicMock,
) -> None:
    mocked_urlopen.side_effect = _respond_and_fetch_frame({"ReturnCode": 0})

    response = _create_client().send_animation(
        panel_index=3,
        images=(
            _create_panel("#FF0000"),
            _create_panel("#00FF00"),
            _create_panel("#0000FF"),
        ),
        frame_duration_ms=10_000,
    )

    assert response["ReturnCode"] == 0
    assert mocked_urlopen.call_count == 1

    request = mocked_urlopen.call_args.args[0]
    payload = json.loads(request.data.decode("utf-8"))

    assert payload["Command"] == "Device/PlayGif"
    assert payload["LcdArray"] == [0, 0, 0, 1, 0]


@patch("novachrono.outputs.times_gate.urlopen")
def test_send_image_raises_when_device_never_fetches_the_frame(
    mocked_urlopen: MagicMock,
) -> None:
    mocked_urlopen.return_value = _create_response({"ReturnCode": 0})

    client = _create_client(fetch_timeout_seconds=0.05)

    with pytest.raises(
        TimesGateError,
        match="did not fetch the frame",
    ):
        client.send_image(
            panel_index=0,
            image=_create_panel(),
        )


@patch("novachrono.outputs.times_gate.urlopen")
def test_send_image_raises_when_the_command_fails(
    mocked_urlopen: MagicMock,
) -> None:
    mocked_urlopen.side_effect = URLError("Connection refused")

    with pytest.raises(
        TimesGateError,
        match="Could not reach Times Gate",
    ):
        _create_client().send_image(
            panel_index=0,
            image=_create_panel(),
        )


def test_frame_server_serves_the_frame_only_to_the_allowed_client() -> None:
    gif_bytes = encode_gif((_create_panel(),))

    with _FrameServer(gif_bytes, allowed_client="203.0.113.1") as server:
        url = f"http://127.0.0.1:{server.port}{server.path}"

        with pytest.raises(HTTPError) as excinfo:
            urlopen(url, timeout=2)

        assert excinfo.value.code == 404
        assert not server.wait_for_fetch(0.05)


def test_frame_server_serves_the_frame_to_the_allowed_client() -> None:
    gif_bytes = encode_gif((_create_panel(),))

    with _FrameServer(gif_bytes, allowed_client="127.0.0.1") as server:
        url = f"http://127.0.0.1:{server.port}{server.path}"

        with urlopen(url, timeout=2) as response:
            assert response.status == 200
            assert response.headers["Content-Type"] == "image/gif"
            assert response.read() == gif_bytes

        assert server.wait_for_fetch(2)


@patch("novachrono.outputs.times_gate.urlopen")
def test_api_error_raises_times_gate_error(
    mocked_urlopen: MagicMock,
) -> None:
    mocked_urlopen.return_value = _create_response(
        {
            "ReturnCode": 7,
            "ReturnMessage": "Invalid token",
        }
    )

    with pytest.raises(
        TimesGateError,
        match="Invalid token",
    ):
        _create_client().get_configuration()


@patch("novachrono.outputs.times_gate.urlopen")
def test_http_error_raises_times_gate_error(
    mocked_urlopen: MagicMock,
) -> None:
    mocked_urlopen.side_effect = HTTPError(
        url=API_URL,
        code=401,
        msg="Unauthorized",
        hdrs=None,
        fp=None,
    )

    with pytest.raises(
        TimesGateError,
        match="HTTP 401",
    ):
        _create_client().get_configuration()


@patch("novachrono.outputs.times_gate.urlopen")
def test_connection_error_raises_times_gate_error(
    mocked_urlopen: MagicMock,
) -> None:
    mocked_urlopen.side_effect = URLError("Connection refused")

    with pytest.raises(
        TimesGateError,
        match="Could not reach Times Gate",
    ):
        _create_client().get_configuration()


@patch("novachrono.outputs.times_gate.urlopen")
def test_timeout_raises_times_gate_error(
    mocked_urlopen: MagicMock,
) -> None:
    mocked_urlopen.side_effect = TimeoutError()

    with pytest.raises(
        TimesGateError,
        match="timed out",
    ):
        _create_client().get_configuration()


@patch("novachrono.outputs.times_gate.urlopen")
def test_invalid_utf8_raises_times_gate_error(
    mocked_urlopen: MagicMock,
) -> None:
    mocked_urlopen.return_value = _create_bytes_response(b"\xff")

    with pytest.raises(
        TimesGateError,
        match="invalid UTF-8 response",
    ):
        _create_client().get_configuration()


@patch("novachrono.outputs.times_gate.urlopen")
def test_invalid_json_raises_times_gate_error(
    mocked_urlopen: MagicMock,
) -> None:
    mocked_urlopen.return_value = _create_raw_response("definitely not json")

    with pytest.raises(
        TimesGateError,
        match="invalid JSON",
    ):
        _create_client().get_configuration()


@patch("novachrono.outputs.times_gate.urlopen")
def test_unexpected_json_structure_raises_times_gate_error(
    mocked_urlopen: MagicMock,
) -> None:
    mocked_urlopen.return_value = _create_response(
        [
            {
                "ReturnCode": 0,
            }
        ]
    )

    with pytest.raises(
        TimesGateError,
        match="unexpected response",
    ):
        _create_client().get_configuration()
