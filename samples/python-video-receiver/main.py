#!/usr/bin/env python3
"""CLI entry-point for the UDP video receiver.

All implementation lives in :mod:`receiver.main`; this thin wrapper
keeps backwards-compatible ``python3 main.py`` invocation working.
"""

import sys
from receiver.main import main

if __name__ == "__main__":
    sys.exit(main())
