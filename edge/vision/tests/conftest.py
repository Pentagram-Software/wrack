import os
import sys

# Insert edge/vision/ itself onto sys.path so tests can `import pipeline`
# and `import detection` / `import events` / `import identification` /
# `import telemetry` as the sibling top-level packages pipeline.py imports.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
