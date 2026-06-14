"""Re-export all public symbols from the top-level main module.

This thin wrapper exists so that tests can import the public API as::

    from receiver import main as receiver_main
    receiver_main.UDPVideoClient(...)
"""
import sys
import os

# Ensure the parent directory (containing the real main.py) is on sys.path
_PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

from main import (  # noqa: E402, F401
    ReconnectConfig,
    compute_backoff_delay,
    DEFAULT_SETTINGS,
    VALID_MODES,
    VALID_STREAM_FORMATS,
    parse_args,
    load_config,
    validate_settings,
    resolve_runtime_settings,
    prompt_interactive_settings,
    print_effective_settings,
    ensure_h264_dependencies,
    H264FrameDecoder,
    UDPVideoClient,
    UDPBroadcastClient,
    main,
    cv2,
    pickle,
)
