"""Tests for safe EV3 telemetry runtime defaults."""

from telemetry.configuration import is_analytics_enabled


def test_analytics_is_disabled_when_config_value_is_missing():
    assert is_analytics_enabled(None) is False


def test_analytics_requires_explicit_true_opt_in():
    assert is_analytics_enabled(True) is True


def test_analytics_rejects_non_boolean_config_values():
    assert is_analytics_enabled(False) is False
    assert is_analytics_enabled("true") is False
    assert is_analytics_enabled(1) is False
