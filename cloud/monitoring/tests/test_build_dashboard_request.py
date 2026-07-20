"""
Unit tests for cloud/monitoring/build_dashboard_request.py

Run from workspace root:
    python -m pytest cloud/monitoring/tests/test_build_dashboard_request.py -v
"""
import importlib.util
import json
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).parent.parent / "build_dashboard_request.py"
_spec = importlib.util.spec_from_file_location("build_dashboard_request", _MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

build_request = _mod.build_request
main = _mod.main

SAMPLE_DASHBOARD = {"uid": "wrack-ev3-health", "title": "Wrack EV3 Health", "panels": []}


class TestBuildRequest:
    def test_wraps_dashboard_with_overwrite_true(self):
        request = build_request(SAMPLE_DASHBOARD)
        assert request["dashboard"] == SAMPLE_DASHBOARD
        assert request["overwrite"] is True

    def test_includes_a_message(self):
        request = build_request(SAMPLE_DASHBOARD)
        assert request["message"]


class TestMain:
    def test_writes_wrapped_request_to_output_path(self, tmp_path):
        dashboard_path = tmp_path / "dashboard.json"
        dashboard_path.write_text(json.dumps(SAMPLE_DASHBOARD))
        output_path = tmp_path / "request.json"

        rc = main([str(dashboard_path), str(output_path)])

        assert rc == 0
        written = json.loads(output_path.read_text())
        assert written["dashboard"] == SAMPLE_DASHBOARD
        assert written["overwrite"] is True

    def test_exits_1_on_missing_dashboard_file(self, tmp_path):
        rc = main([str(tmp_path / "missing.json"), str(tmp_path / "out.json")])
        assert rc == 1
        assert not (tmp_path / "out.json").exists()

    def test_exits_1_on_invalid_json(self, tmp_path):
        dashboard_path = tmp_path / "dashboard.json"
        dashboard_path.write_text("{not valid json")
        rc = main([str(dashboard_path), str(tmp_path / "out.json")])
        assert rc == 1

    def test_exits_1_on_wrong_arg_count(self):
        assert main([]) == 1
        assert main(["only-one-arg"]) == 1
