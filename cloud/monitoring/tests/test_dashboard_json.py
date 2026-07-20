"""
Structural validation for cloud/monitoring/dashboards/wrack-ev3-health.json (PEN-231).

This doesn't (and can't, in a sandbox with no live Grafana Cloud credentials
-- see docs/monitoring/ev3-health-dashboard.md) assert the dashboard actually
renders in Grafana Cloud. It only asserts the JSON is well-formed and matches
the v1 scope decided for PEN-231: exactly one time-series panel, querying the
EV3 battery-percentage metric, with the agreed default time range/refresh.

Run from workspace root:
    python -m pytest cloud/monitoring/tests/test_dashboard_json.py -v
"""
import json
from pathlib import Path

import pytest

DASHBOARD_PATH = (
    Path(__file__).parent.parent / "dashboards" / "wrack-ev3-health.json"
)

# Best-derived guess pending empirical confirmation in Grafana Cloud's Metrics
# Explorer (PEN-231 Manual steps) -- kept as one constant so re-pointing the
# query after verification only touches the dashboard JSON + this line.
EXPECTED_METRIC_NAME = "wrack_device_status_percentage"


@pytest.fixture()
def dashboard():
    return json.loads(DASHBOARD_PATH.read_text())


class TestDashboardFile:
    def test_file_exists(self):
        assert DASHBOARD_PATH.is_file()

    def test_is_valid_json(self):
        json.loads(DASHBOARD_PATH.read_text())  # must not raise


class TestDashboardMetadata:
    def test_has_title(self, dashboard):
        assert dashboard["title"]

    def test_has_stable_uid(self, dashboard):
        # A fixed uid makes /api/dashboards/db provisioning idempotent --
        # re-POSTing updates the same dashboard rather than creating a
        # duplicate each time.
        assert dashboard["uid"] == "wrack-ev3-health"

    def test_default_time_range_is_one_hour(self, dashboard):
        assert dashboard["time"] == {"from": "now-1h", "to": "now"}

    def test_auto_refresh_is_30s(self, dashboard):
        assert dashboard["refresh"] == "30s"

    def test_declares_a_prometheus_datasource_template_variable(self, dashboard):
        variables = dashboard["templating"]["list"]
        ds_vars = [v for v in variables if v.get("type") == "datasource"]
        assert len(ds_vars) == 1
        assert ds_vars[0]["query"] == "prometheus"
        assert ds_vars[0]["name"] == "DS_PROMETHEUS"


class TestDashboardPanels:
    def test_exactly_one_panel_in_v1(self, dashboard):
        """PEN-231 v1 scope is a single panel; PEN-200 adds more later."""
        assert len(dashboard["panels"]) == 1

    def test_panel_is_a_timeseries_panel(self, dashboard):
        panel = dashboard["panels"][0]
        assert panel["type"] == "timeseries"

    def test_panel_uses_the_templated_prometheus_datasource(self, dashboard):
        panel = dashboard["panels"][0]
        assert panel["datasource"] == {"type": "prometheus", "uid": "${DS_PROMETHEUS}"}

    def test_panel_unit_is_percent_with_0_to_100_range(self, dashboard):
        defaults = dashboard["panels"][0]["fieldConfig"]["defaults"]
        assert defaults["unit"] == "percent"
        assert defaults["min"] == 0
        assert defaults["max"] == 100

    def test_panel_has_exactly_one_target(self, dashboard):
        panel = dashboard["panels"][0]
        assert len(panel["targets"]) == 1

    def test_panel_target_queries_the_expected_metric_name(self, dashboard):
        target = dashboard["panels"][0]["targets"][0]
        assert target["expr"] == EXPECTED_METRIC_NAME

    def test_panel_target_uses_the_templated_prometheus_datasource(self, dashboard):
        target = dashboard["panels"][0]["targets"][0]
        assert target["datasource"] == {"type": "prometheus", "uid": "${DS_PROMETHEUS}"}
