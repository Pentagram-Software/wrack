import subprocess
import pytest

from config import parse_stream_config
from security import TLSConfig


# ── Fixture for a self-signed cert pair ─────────────────────────────────────


@pytest.fixture(scope="module")
def tls_certs(tmp_path_factory):
    cert_dir = tmp_path_factory.mktemp("cfg_certs")
    cert_file = cert_dir / "server.crt"
    key_file = cert_dir / "server.key"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(key_file),
            "-out", str(cert_file),
            "-days", "1", "-nodes",
            "-subj", "/CN=localhost",
        ],
        check=True,
        capture_output=True,
    )
    return cert_file, key_file


def test_defaults_used_when_no_args_and_no_config(tmp_path):
    config = parse_stream_config(["--config", str(tmp_path / "missing.json")])
    assert config.width == 640
    assert config.height == 480
    assert config.fps == 30
    assert config.bitrate == 2_000_000
    assert config.gop == 30
    assert config.profile == "baseline"


def test_json_config_used_when_present(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        '{"width": 1280, "height": 720, "fps": 25, "bitrate": 3000000, "gop": 60, "profile": "main"}'
    )
    config = parse_stream_config(["--config", str(config_path)])
    assert config.width == 1280
    assert config.height == 720
    assert config.fps == 25
    assert config.bitrate == 3_000_000
    assert config.gop == 60
    assert config.profile == "main"


def test_cli_overrides_json(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        '{"width": 1280, "height": 720, "fps": 25, "bitrate": 3000000, "gop": 60, "profile": "main"}'
    )
    config = parse_stream_config(
        [
            "--config",
            str(config_path),
            "--width",
            "1920",
            "--fps",
            "60",
            "--bitrate",
            "5000000",
            "--gop",
            "120",
            "--profile",
            "high",
        ]
    )
    assert config.width == 1920
    assert config.height == 720
    assert config.fps == 60
    assert config.bitrate == 5_000_000
    assert config.gop == 120
    assert config.profile == "high"


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
def test_invalid_values_raise(args):
    with pytest.raises(ValueError):
        parse_stream_config(args)


def test_invalid_profile_raises():
    with pytest.raises(ValueError):
        parse_stream_config(["--profile", "unsupported"])


# ── TLS config integration in parse_stream_config() ─────────────────────────


def test_tls_is_none_when_no_args(tmp_path):
    config = parse_stream_config(["--config", str(tmp_path / "missing.json")])
    assert config.tls is None


def test_tls_config_built_from_cli(tls_certs):
    cert, key = tls_certs
    config = parse_stream_config(
        [
            "--tls-cert", str(cert),
            "--tls-key", str(key),
        ]
    )
    assert isinstance(config.tls, TLSConfig)
    assert config.tls.cert_path == str(cert)
    assert config.tls.key_path == str(key)
    assert config.tls.min_tls_version == "TLSv1.2"


def test_tls_min_version_override(tls_certs):
    cert, key = tls_certs
    config = parse_stream_config(
        [
            "--tls-cert", str(cert),
            "--tls-key", str(key),
            "--tls-min-version", "TLSv1.3",
        ]
    )
    assert config.tls is not None
    assert config.tls.min_tls_version == "TLSv1.3"


def test_only_cert_without_key_raises(tls_certs):
    cert, _ = tls_certs
    with pytest.raises((ValueError, SystemExit)):
        parse_stream_config(["--tls-cert", str(cert)])


def test_only_key_without_cert_raises(tls_certs):
    _, key = tls_certs
    with pytest.raises((ValueError, SystemExit)):
        parse_stream_config(["--tls-key", str(key)])
