import os
import sys

# Insert edge/vision/ (the parent of the events/ package) onto sys.path so
# tests can `import events` / `from events.lifecycle import ...` the same
# way a future edge/vision/ runtime would.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
