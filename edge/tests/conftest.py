import os
import sys

# edge/ is the package root for pi_telemetry_env.py
EDGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if EDGE_ROOT not in sys.path:
    sys.path.insert(0, EDGE_ROOT)
