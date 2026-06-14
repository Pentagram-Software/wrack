#!/usr/bin/env python3
"""CLI entry-point for the LAN validation tool.

All implementation lives in :mod:`receiver.lan_validate`; this thin wrapper
keeps ``python3 lan_validate.py`` invocation working from the project root.

Usage::

    python3 lan_validate.py --server-ip 192.168.1.50 --duration 10

Exit codes: 0 = PASS, 1 = FAIL (targets missed), 2 = error.
"""

import sys
from receiver.lan_validate import main

if __name__ == "__main__":
    sys.exit(main())
