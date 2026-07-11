"""
Unit tests for cloud/monitoring/write_credentials.py

Run from workspace root:
    python -m pytest cloud/monitoring/tests/test_write_credentials.py -v
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

# Load the module under test without it needing to be in a Python package
_MODULE_PATH = Path(__file__).parent.parent / "write_credentials.py"
_spec = importlib.util.spec_from_file_location("write_credentials", _MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

build_credentials = _mod.build_credentials
missing_env_vars = _mod.missing_env_vars
main = _mod.main

FULL_ENV = {
    "OTLP_ENDPOINT": "https://otlp-gateway-prod-xx-xxxx.grafana.net/otlp",
    "INSTANCE_ID": "123456",
    "TOKEN": "glc_faketoken",
}


# ── build_credentials ────────────────────────────────────────────────────────

class TestBuildCredentials:
    def test_maps_env_vars_to_expected_json_keys(self):
        creds = build_credentials(FULL_ENV)
        assert creds == {
            "otlp_endpoint": FULL_ENV["OTLP_ENDPOINT"],
            "instance_id": FULL_ENV["INSTANCE_ID"],
            "token": FULL_ENV["TOKEN"],
        }

    def test_preserves_special_characters_that_would_break_string_interpolation(self):
        """Values with quotes/backslashes must survive unescaped by json.dump,
        not corrupt the output or execute as injected Python."""
        tricky_env = {
            "OTLP_ENDPOINT": "https://example.com/otlp",
            "INSTANCE_ID": "123",
            "TOKEN": """glc_' + __import__('os').system('touch /tmp/pwned') + '""",
        }
        creds = build_credentials(tricky_env)
        assert creds["token"] == tricky_env["TOKEN"]
        # Round-tripping through json must not choke on the payload either.
        assert json.loads(json.dumps(creds))["token"] == tricky_env["TOKEN"]


# ── missing_env_vars ──────────────────────────────────────────────────────────

class TestMissingEnvVars:
    def test_none_missing_when_all_present(self):
        assert missing_env_vars(FULL_ENV) == []

    def test_reports_each_missing_var(self):
        assert missing_env_vars({"TOKEN": "x"}) == ["OTLP_ENDPOINT", "INSTANCE_ID"]

    def test_treats_empty_string_as_missing(self):
        env = dict(FULL_ENV)
        env["TOKEN"] = ""
        assert missing_env_vars(env) == ["TOKEN"]


# ── main() CLI ────────────────────────────────────────────────────────────────

class TestMain:
    def test_writes_json_file_when_path_given(self, tmp_path, monkeypatch):
        for key, value in FULL_ENV.items():
            monkeypatch.setenv(key, value)

        out_file = tmp_path / "creds.json"
        rc = main([str(out_file)])

        assert rc == 0
        written = json.loads(out_file.read_text())
        assert written == {
            "otlp_endpoint": FULL_ENV["OTLP_ENDPOINT"],
            "instance_id": FULL_ENV["INSTANCE_ID"],
            "token": FULL_ENV["TOKEN"],
        }

    def test_prints_to_stdout_when_no_path_given(self, capsys, monkeypatch):
        for key, value in FULL_ENV.items():
            monkeypatch.setenv(key, value)

        rc = main([])

        assert rc == 0
        printed = json.loads(capsys.readouterr().out)
        assert printed["token"] == FULL_ENV["TOKEN"]

    def test_exits_1_when_env_vars_missing(self, monkeypatch, capsys):
        monkeypatch.delenv("OTLP_ENDPOINT", raising=False)
        monkeypatch.delenv("INSTANCE_ID", raising=False)
        monkeypatch.delenv("TOKEN", raising=False)

        rc = main([])

        assert rc == 1
        assert "OTLP_ENDPOINT" in capsys.readouterr().err

    def test_does_not_write_file_when_env_vars_missing(self, tmp_path, monkeypatch):
        monkeypatch.delenv("OTLP_ENDPOINT", raising=False)
        monkeypatch.delenv("INSTANCE_ID", raising=False)
        monkeypatch.delenv("TOKEN", raising=False)

        out_file = tmp_path / "creds.json"
        rc = main([str(out_file)])

        assert rc == 1
        assert not out_file.exists()
