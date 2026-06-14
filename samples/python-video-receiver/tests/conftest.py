"""pytest configuration for the python-video-receiver test suite."""
import sys
import os

# Add the package root to sys.path so `receiver` is importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
