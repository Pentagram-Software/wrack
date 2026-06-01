import json
import logging

import pytest

from config import (
    ALLOWED_LOG_LEVELS,
    ALLOWED_PROFILES,
    ALLOWED_TRANSPORTS,
    StreamConfig,
    get_log_level_constant,
    parse_stream_config,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _write_json(path, data):
    path.write_text(json.dumps(data))


# ── Default values ────────────────────────────────────────────────────────────


def test_defaults_used_when_no_args_and_no_config(tmp_path):
    config = parse_stream_config(["--config", str(tmp_path / "missing.json")])
    assert config.width == 640
    assert config.height == 480
    assert config.fps == 30
    assert config.bitrate == 2_000_000
    assert config.gop == 30
    assert config.profile == "baseline"
    assert config.transport == "udp"
    assert config.host == "0.0.0.0"
    assert config.udp_port == 9999
    assert config.tcp_port == 8888
    assert config.http_port == 8080
    assert config.log_level == "info"
    assert config.log_path == "logs/streamer.log"


# ── JSON config loading ───────────────────────────────────────────────────────


def test_json_config_camera_fields(tmp_path):
    cfg_path = tmp_path / "config.json"
    _write_json(
        cfg_path,
        {"width": 1280, "height": 720, "fps": 25, "bitrate": 3_000_000, "gop": 60, "profile": "main"},
    )
    config = parse_stream_config(["--config", str(cfg_path)])
    assert config.width == 1280
    assert config.height == 720
    assert config.fps == 25
    assert config.bitrate == 3_000_000
    assert config.gop == 60
    assert config.profile == "main"


def test_json_config_transport_fields(tmp_path):
    cfg_path = tmp_path / "config.json"
    _write_json(
        cfg_path,
        {
            "transport": "tcp",
            "host": "192.168.1.100",
            "udp_port": 5000,
            "tcp_port": 5001,
            "http_port": 5002,
        },
    )
    config = parse_stream_config(["--config", str(cfg_path)])
    assert config.transport == "tcp"
    assert config.host == "192.168.1.100"
    assert config.udp_port == 5000
    assert config.tcp_port == 5001
    assert config.http_port == 5002


def test_json_config_log_fields(tmp_path):
    cfg_path = tmp_path / "config.json"
    _write_json(cfg_path, {"log_level": "debug", "log_path": "/tmp/test.log"})
    config = parse_stream_config(["--config", str(cfg_path)])
    assert config.log_level == "debug"
    assert config.log_path == "/tmp/test.log"


def test_json_config_partial_fields_fall_back_to_defaults(tmp_path):
    """Fields absent from JSON should retain hardcoded defaults."""
    cfg_path = tmp_path / "config.json"
    _write_json(cfg_path, {"width": 1920})
    config = parse_stream_config(["--config", str(cfg_path)])
    assert config.width == 1920
    assert config.height == 480  # default
    assert config.transport == "udp"  # default


# ── CLI flag overrides ────────────────────────────────────────────────────────


def test_cli_overrides_json_camera(tmp_path):
    cfg_path = tmp_path / "config.json"
    _write_json(
        cfg_path,
        {"width": 1280, "height": 720, "fps": 25, "bitrate": 3_000_000, "gop": 60, "profile": "main"},
    )
    config = parse_stream_config(
        [
            "--config", str(cfg_path),
            "--width", "1920",
            "--fps", "60",
            "--bitrate", "5000000",
            "--gop", "120",
            "--profile", "high",
        ]
    )
    assert config.width == 1920
    assert config.height == 720  # from JSON, not overridden
    assert config.fps == 60
    assert config.bitrate == 5_000_000
    assert config.gop == 120
    assert config.profile == "high"


def test_cli_overrides_json_transport(tmp_path):
    cfg_path = tmp_path / "config.json"
    _write_json(cfg_path, {"transport": "tcp", "tcp_port": 9000})
    config = parse_stream_config(
        ["--config", str(cfg_path), "--transport", "http", "--http-port", "8181"]
    )
    assert config.transport == "http"
    assert config.http_port == 8181
    assert config.tcp_port == 9000  # from JSON, not overridden


def test_cli_overrides_json_host(tmp_path):
    cfg_path = tmp_path / "config.json"
    _write_json(cfg_path, {"host": "10.0.0.1"})
    config = parse_stream_config(["--config", str(cfg_path), "--host", "127.0.0.1"])
    assert config.host == "127.0.0.1"


def test_cli_overrides_json_log(tmp_path):
    cfg_path = tmp_path / "config.json"
    _write_json(cfg_path, {"log_level": "warning", "log_path": "/old/path.log"})
    config = parse_stream_config(
        ["--config", str(cfg_path), "--log-level", "error", "--log-path", "/new/path.log"]
    )
    assert config.log_level == "error"
    assert config.log_path == "/new/path.log"


def test_cli_sets_udp_port_without_config(tmp_path):
    config = parse_stream_config(
        ["--config", str(tmp_path / "missing.json"), "--udp-port", "12345"]
    )
    assert config.udp_port == 12345


def test_cli_sets_tcp_port_without_config(tmp_path):
    config = parse_stream_config(
        ["--config", str(tmp_path / "missing.json"), "--tcp-port", "12346"]
    )
    assert config.tcp_port == 12346


# ── resolution property ───────────────────────────────────────────────────────


def test_resolution_property(tmp_path):
    config = parse_stream_config(
        ["--config", str(tmp_path / "missing.json"), "--width", "640", "--height", "480"]
    )
    assert config.resolution == (640, 480)


# ── port property ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "transport, flag, port_val, expected_port",
    [
        ("udp", "--udp-port", "5001", 5001),
        ("tcp", "--tcp-port", "5002", 5002),
        ("http", "--http-port", "5003", 5003),
    ],
)
def test_port_property_reflects_active_transport(tmp_path, transport, flag, port_val, expected_port):
    config = parse_stream_config(
        [
            "--config", str(tmp_path / "missing.json"),
            "--transport", transport,
            flag, port_val,
        ]
    )
    assert config.port == expected_port


# ── All three transports accepted ─────────────────────────────────────────────


@pytest.mark.parametrize("transport", sorted(ALLOWED_TRANSPORTS))
def test_all_transports_accepted(tmp_path, transport):
    config = parse_stream_config(
        ["--config", str(tmp_path / "missing.json"), "--transport", transport]
    )
    assert config.transport == transport


# ── All log levels accepted ────────────────────────────────────────────────────


@pytest.mark.parametrize("level", sorted(ALLOWED_LOG_LEVELS))
def test_all_log_levels_accepted(tmp_path, level):
    config = parse_stream_config(
        ["--config", str(tmp_path / "missing.json"), "--log-level", level]
    )
    assert config.log_level == level


# ── All profiles accepted ─────────────────────────────────────────────────────


@pytest.mark.parametrize("profile", sorted(ALLOWED_PROFILES))
def test_all_profiles_accepted(tmp_path, profile):
    config = parse_stream_config(
        ["--config", str(tmp_path / "missing.json"), "--profile", profile]
    )
    assert config.profile == profile


# ── Validation errors — camera/encoder ────────────────────────────────────────


@pytest.mark.parametrize(
    "args",
    [
        ["--width", "0"],
        ["--height", "0"],
        ["--fps", "0"],
        ["--bitrate", "0"],
        ["--gop", "0"],
        ["--width", "-1"],
        ["--height", "-1"],
        ["--fps", "-1"],
        ["--bitrate", "-1"],
        ["--gop", "-1"],
    ],
)
def test_invalid_camera_values_raise(args):
    with pytest.raises(ValueError):
        parse_stream_config(args)


def test_invalid_profile_raises():
    with pytest.raises(ValueError, match="profile"):
        parse_stream_config(["--profile", "unsupported"])


# ── Validation errors — transport ─────────────────────────────────────────────


def test_invalid_transport_raises():
    with pytest.raises(ValueError, match="transport"):
        parse_stream_config(["--transport", "ftp"])


# ── Validation errors — ports ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "flag, value",
    [
        ("--udp-port", "0"),
        ("--tcp-port", "0"),
        ("--http-port", "0"),
        ("--udp-port", "-1"),
        ("--tcp-port", "-1"),
        ("--http-port", "-1"),
        ("--udp-port", "65536"),
        ("--tcp-port", "65536"),
        ("--http-port", "65536"),
    ],
)
def test_invalid_port_raises(flag, value):
    with pytest.raises(ValueError, match="port"):
        parse_stream_config([flag, value])


# ── Validation errors — log level ─────────────────────────────────────────────


def test_invalid_log_level_raises():
    with pytest.raises(ValueError, match="log_level"):
        parse_stream_config(["--log-level", "verbose"])


# ── get_log_level_constant ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "level_str, expected",
    [
        ("debug", logging.DEBUG),
        ("info", logging.INFO),
        ("warning", logging.WARNING),
        ("error", logging.ERROR),
        ("critical", logging.CRITICAL),
    ],
)
def test_get_log_level_constant(level_str, expected):
    assert get_log_level_constant(level_str) == expected


def test_get_log_level_constant_uppercase():
    assert get_log_level_constant("INFO") == logging.INFO


# ── StreamConfig is immutable (frozen dataclass) ──────────────────────────────


def test_stream_config_is_frozen(tmp_path):
    config = parse_stream_config(["--config", str(tmp_path / "missing.json")])
    with pytest.raises(Exception):
        config.width = 999  # type: ignore[misc]
