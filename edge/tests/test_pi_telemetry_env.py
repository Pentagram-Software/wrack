"""Unit tests for edge/pi_telemetry_env.py."""

import os

import pytest

from pi_telemetry_env import (
    ensure_telemetry_endpoint,
    load_pi_telemetry_env,
    parse_env_file,
)


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    path = tmp_path / "system-metrics.env"
    path.write_text(
        "# comment\n"
        "TELEMETRY_ENDPOINT=https://example.test/unifiedIngress\n"
        "TELEMETRY_DEVICE_TOKEN=secret-token\n"
        "RPI_DEVICE_ID=rpi-camera-01\n"
    )
    # Clear relevant env so load results are deterministic.
    for key in ("TELEMETRY_ENDPOINT", "TELEMETRY_DEVICE_TOKEN", "RPI_DEVICE_ID", "PI_TELEMETRY_ENV_FILE"):
        monkeypatch.delenv(key, raising=False)
    return str(path)


class TestParseEnvFile:
    def test_parses_assignments(self, env_file):
        values = parse_env_file(env_file)
        assert values["TELEMETRY_ENDPOINT"] == "https://example.test/unifiedIngress"
        assert values["TELEMETRY_DEVICE_TOKEN"] == "secret-token"
        assert values["RPI_DEVICE_ID"] == "rpi-camera-01"

    def test_strips_quotes(self, tmp_path):
        path = tmp_path / "quoted.env"
        path.write_text('TELEMETRY_ENDPOINT="https://quoted.example/fn"\n')
        assert parse_env_file(str(path))["TELEMETRY_ENDPOINT"] == "https://quoted.example/fn"

    def test_does_not_execute_shell(self, tmp_path):
        marker = tmp_path / "pwned"
        path = tmp_path / "evil.env"
        path.write_text(f"EVIL=$(touch {marker})\nTELEMETRY_ENDPOINT=https://x\n")
        values = parse_env_file(str(path))
        assert values["EVIL"] == f"$(touch {marker})"
        assert not marker.exists()

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_env_file(str(tmp_path / "missing.env"))


class TestLoadPiTelemetryEnv:
    def test_loads_into_environ(self, env_file, monkeypatch):
        loaded = load_pi_telemetry_env(env_file)
        assert loaded == env_file
        assert os.environ["TELEMETRY_ENDPOINT"] == "https://example.test/unifiedIngress"
        assert os.environ["TELEMETRY_DEVICE_TOKEN"] == "secret-token"

    def test_does_not_overwrite_existing(self, env_file, monkeypatch):
        monkeypatch.setenv("TELEMETRY_ENDPOINT", "https://already.set/fn")
        load_pi_telemetry_env(env_file)
        assert os.environ["TELEMETRY_ENDPOINT"] == "https://already.set/fn"
        assert os.environ["TELEMETRY_DEVICE_TOKEN"] == "secret-token"

    def test_missing_file_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TELEMETRY_ENDPOINT", raising=False)
        assert load_pi_telemetry_env(str(tmp_path / "nope.env")) is None


class TestEnsureTelemetryEndpoint:
    def test_returns_endpoint_after_load(self, env_file, monkeypatch):
        assert (
            ensure_telemetry_endpoint(env_file)
            == "https://example.test/unifiedIngress"
        )

    def test_raises_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TELEMETRY_ENDPOINT", raising=False)
        with pytest.raises(ValueError, match="TELEMETRY_ENDPOINT is not set"):
            ensure_telemetry_endpoint(str(tmp_path / "missing.env"))
