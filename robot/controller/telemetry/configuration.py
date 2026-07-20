"""Runtime configuration helpers for the EV3 telemetry paths."""


def is_analytics_enabled(value):
    """Return whether analytics telemetry has been explicitly enabled.

    Analytics can buffer, retry, and persist overflow data.  It is therefore
    opt-in while the EV3 operates in the PEN-233 health-only baseline.
    Requiring the literal ``True`` keeps a missing, malformed, or legacy
    configuration value fail-safe.
    """
    return value is True
