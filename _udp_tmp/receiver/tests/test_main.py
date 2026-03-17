"""Unit tests for receiver runtime/config and decode routing."""

import argparse
import builtins

import pytest

from receiver import main as receiver_main


def test_load_config_returns_empty_when_implicit_missing(tmp_path):
    """Verify missing implicit config resolves to empty settings.

    Purpose: Ensure optional config file absence does not raise.
    Inputs: missing path and explicit=False.
    Outputs: Empty dict.
    """
    assert receiver_main.load_config(tmp_path / "missing.json", explicit=False) == {}


def test_load_config_raises_when_explicit_missing(tmp_path):
    """Verify explicit config path must exist.

    Purpose: Ensure explicit --config failures are surfaced.
    Inputs: missing path and explicit=True.
    Outputs: ValueError.
    """
    with pytest.raises(ValueError, match="Config file not found"):
        receiver_main.load_config(tmp_path / "missing.json", explicit=True)


def test_resolve_runtime_settings_cli_overrides_config(tmp_path):
    """Validate CLI > config > defaults precedence.

    Purpose: Confirm runtime settings precedence is implemented correctly.
    Inputs: config file values and CLI overrides.
    Outputs: Resolved settings dict reflecting precedence order.
    """
    config_path = tmp_path / "config.json"
    config_path.write_text(
        (
            '{"mode":"broadcast","stream_format":"jpeg","server_ip":"10.0.0.5",'
            '"server_port":9000,"client_port":9001,"listen_port":9002}'
        ),
        encoding="utf-8",
    )

    args = argparse.Namespace(
        config=str(config_path),
        mode="client_server",
        stream_format="h264",
        server_ip="192.168.1.216",
        server_port=9999,
        client_port=9998,
        listen_port=None,
    )
    resolved = receiver_main.resolve_runtime_settings(args)

    assert resolved["mode"] == "client_server"
    assert resolved["stream_format"] == "h264"
    assert resolved["server_ip"] == "192.168.1.216"
    assert resolved["server_port"] == 9999
    assert resolved["client_port"] == 9998
    # From config because no CLI override
    assert resolved["listen_port"] == 9002


def test_validate_settings_rejects_invalid_stream_format():
    """Reject unsupported stream_format values.

    Purpose: Ensure invalid modes are blocked early.
    Inputs: settings with invalid stream_format.
    Outputs: ValueError.
    """
    settings = dict(receiver_main.DEFAULT_SETTINGS)
    settings.update(
        {
            "mode": "client_server",
            "stream_format": "vp9",
            "server_port": 9999,
            "client_port": 9999,
            "listen_port": 9999,
        }
    )
    with pytest.raises(ValueError, match="Invalid stream_format"):
        receiver_main.validate_settings(settings)


def test_process_frame_data_routes_to_jpeg_handler():
    """Route JPEG payloads to legacy decode path.

    Purpose: Prevent regressions in stream-format routing.
    Inputs: client-like object with stream_format='jpeg'.
    Outputs: JPEG handler called once.
    """
    client = receiver_main.UDPVideoClient.__new__(receiver_main.UDPVideoClient)
    client.stream_format = "jpeg"
    client.decode_failures = 0
    calls = {"jpeg": 0, "h264": 0}

    client.process_pickled_frame = lambda _: calls.__setitem__("jpeg", calls["jpeg"] + 1)
    client.process_h264_frame = lambda _: calls.__setitem__("h264", calls["h264"] + 1)

    receiver_main.UDPVideoClient.process_frame_data(client, b"payload")
    assert calls == {"jpeg": 1, "h264": 0}


def test_process_frame_data_routes_to_h264_handler():
    """Route H.264 payloads to H.264 decode path.

    Purpose: Ensure H.264 option is wired to new handler.
    Inputs: client-like object with stream_format='h264'.
    Outputs: H.264 handler called once.
    """
    client = receiver_main.UDPVideoClient.__new__(receiver_main.UDPVideoClient)
    client.stream_format = "h264"
    client.decode_failures = 0
    calls = {"jpeg": 0, "h264": 0}

    client.process_pickled_frame = lambda _: calls.__setitem__("jpeg", calls["jpeg"] + 1)
    client.process_h264_frame = lambda _: calls.__setitem__("h264", calls["h264"] + 1)

    receiver_main.UDPVideoClient.process_frame_data(client, b"payload")
    assert calls == {"jpeg": 0, "h264": 1}


def test_ensure_h264_dependencies_raises_when_pyav_missing(monkeypatch):
    """Report actionable dependency error when PyAV is unavailable.

    Purpose: Validate Step 8 check for missing H.264 dependency.
    Inputs: Monkeypatched import behavior for module 'av'.
    Outputs: ValueError with install guidance.
    """
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "av":
            raise ImportError("No module named 'av'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ValueError, match="requires PyAV"):
        receiver_main.ensure_h264_dependencies()


def test_process_h264_frame_decode_failure_increments_counter():
    """Keep client running when H.264 decode fails.

    Purpose: Ensure decode failures are counted and handled gracefully.
    Inputs: client-like object with failing decoder.
    Outputs: decode_failures incremented; no exception propagated.
    """
    client = receiver_main.UDPVideoClient.__new__(receiver_main.UDPVideoClient)
    client.h264_decoder = type("FailingDecoder", (), {"decode_to_bgr": lambda *_: (_ for _ in ()).throw(RuntimeError("decode failed"))})()
    client.decode_failures = 0
    client.frames_received = 0
    client.running = True

    receiver_main.UDPVideoClient.process_h264_frame(client, b"payload")
    assert client.decode_failures == 1
    assert client.frames_received == 0


def test_process_pickled_frame_success_keeps_jpeg_path(monkeypatch):
    """Verify JPEG decode path still increments frames on success.

    Purpose: Non-regression test for legacy JPEG processing.
    Inputs: pickled payload and patched cv2 display side effects.
    Outputs: frames_received increments without decode_failures.
    """
    client = receiver_main.UDPVideoClient.__new__(receiver_main.UDPVideoClient)
    client.decode_failures = 0
    client.frames_received = 0
    client.running = True

    monkeypatch.setattr(receiver_main.cv2, "imdecode", lambda *_: object())
    monkeypatch.setattr(receiver_main.cv2, "putText", lambda *args, **kwargs: None)
    monkeypatch.setattr(receiver_main.cv2, "imshow", lambda *args, **kwargs: None)
    monkeypatch.setattr(receiver_main.cv2, "waitKey", lambda *_: -1)

    # Valid pickled bytes object so np.frombuffer path runs.
    payload = receiver_main.pickle.dumps(b"jpeg-bytes")
    receiver_main.UDPVideoClient.process_pickled_frame(client, payload)

    assert client.frames_received == 1
    assert client.decode_failures == 0
