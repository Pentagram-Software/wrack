import os
import sys

# Insert edge/monitoring/ (the parent of system_metrics_collector.py) onto
# sys.path so tests can `import system_metrics_collector` directly, and
# insert edge/vision/ so system_metrics_collector's own `import telemetry`
# resolves the same way it does at runtime — mirrors
# edge/vision/telemetry/tests/conftest.py and
# edge/video-streamer/tests/conftest.py.
MONITORING_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if MONITORING_ROOT not in sys.path:
    sys.path.insert(0, MONITORING_ROOT)

VISION_ROOT = os.path.join(os.path.dirname(MONITORING_ROOT), "vision")
if VISION_ROOT not in sys.path:
    sys.path.insert(0, VISION_ROOT)
