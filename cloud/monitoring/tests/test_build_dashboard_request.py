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
substitute_metric_name = _mod.substitute_metric_name
PLACEHOLDER_METRIC_NAME = _mod.PLACEHOLDER_METRIC_NAME
main = _mod.main

SAMPLE_DASHBOARD = {"uid": "wrack-ev3-health", "title": "Wrack EV3 Health", "panels": []}

SAMPLE_DASHBOARD_WITH_PLACEHOLDER = {
    "uid": "wrack-ev3-health",
    "title": "Wrack EV3 Health",
    "panels": [
        {
            "targets": [
                {"refId": "A", "expr": PLACEHOLDER_METRIC_NAME},
            ]
        }
    ],
}


class TestBuildRequest:
    def test_wraps_dashboard_with_overwrite_true(self):
        request = build_request(SAMPLE_DASHBOARD)
        assert request["dashboard"] == SAMPLE_DASHBOARD
        assert request["overwrite"] is True

    def test_includes_a_message(self):
        request = build_request(SAMPLE_DASHBOARD)
        assert request["message"]


class TestSubstituteMetricName:
    def test_replaces_placeholder_with_given_metric_name(self):
        dashboard = json.loads(json.dumps(SAMPLE_DASHBOARD_WITH_PLACEHOLDER))  # deep copy
        result = substitute_metric_name(dashboard, "wrack_device_status_percentage")
        assert result["panels"][0]["targets"][0]["expr"] == "wrack_device_status_percentage"

    def test_replaces_placeholder_in_every_matching_target(self):
        dashboard = {
            "panels": [
                {"targets": [{"expr": PLACEHOLDER_METRIC_NAME}, {"expr": PLACEHOLDER_METRIC_NAME}]},
                {"targets": [{"expr": PLACEHOLDER_METRIC_NAME}]},
            ]
        }
        result = substitute_metric_name(dashboard, "real_metric")
        exprs = [t["expr"] for p in result["panels"] for t in p["targets"]]
        assert exprs == ["real_metric", "real_metric", "real_metric"]

    def test_leaves_non_placeholder_targets_untouched(self):
        dashboard = {
            "panels": [
                {"targets": [{"expr": PLACEHOLDER_METRIC_NAME}, {"expr": "some_other_metric"}]},
            ]
        }
        result = substitute_metric_name(dashboard, "real_metric")
        exprs = [t["expr"] for t in result["panels"][0]["targets"]]
        assert exprs == ["real_metric", "some_other_metric"]

    def test_raises_when_placeholder_not_found(self):
        dashboard = {"panels": [{"targets": [{"expr": "already_a_real_metric"}]}]}
        with pytest.raises(ValueError, match=PLACEHOLDER_METRIC_NAME):
            substitute_metric_name(dashboard, "real_metric")

    def test_raises_on_dashboard_with_no_panels(self):
        with pytest.raises(ValueError):
            substitute_metric_name({"panels": []}, "real_metric")


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

    def test_metric_name_flag_substitutes_placeholder(self, tmp_path):
        dashboard_path = tmp_path / "dashboard.json"
        dashboard_path.write_text(json.dumps(SAMPLE_DASHBOARD_WITH_PLACEHOLDER))
        output_path = tmp_path / "request.json"

        rc = main([str(dashboard_path), str(output_path), "--metric-name", "wrack_device_status_percentage"])

        assert rc == 0
        written = json.loads(output_path.read_text())
        assert written["dashboard"]["panels"][0]["targets"][0]["expr"] == "wrack_device_status_percentage"

    def test_without_metric_name_flag_leaves_placeholder_untouched(self, tmp_path):
        dashboard_path = tmp_path / "dashboard.json"
        dashboard_path.write_text(json.dumps(SAMPLE_DASHBOARD_WITH_PLACEHOLDER))
        output_path = tmp_path / "request.json"

        rc = main([str(dashboard_path), str(output_path)])

        assert rc == 0
        written = json.loads(output_path.read_text())
        assert written["dashboard"]["panels"][0]["targets"][0]["expr"] == PLACEHOLDER_METRIC_NAME

    def test_exits_1_and_writes_nothing_when_placeholder_missing(self, tmp_path):
        dashboard_path = tmp_path / "dashboard.json"
        dashboard_path.write_text(json.dumps(SAMPLE_DASHBOARD))  # no panels/targets at all
        output_path = tmp_path / "request.json"

        rc = main([str(dashboard_path), str(output_path), "--metric-name", "real_metric"])

        assert rc == 1
        assert not output_path.exists()

    def test_exits_1_when_metric_name_flag_missing_its_value(self, tmp_path):
        dashboard_path = tmp_path / "dashboard.json"
        dashboard_path.write_text(json.dumps(SAMPLE_DASHBOARD))
        output_path = tmp_path / "request.json"

        rc = main([str(dashboard_path), str(output_path), "--metric-name"])

        assert rc == 1
