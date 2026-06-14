import argparse
import json
import logging
import os
from dataclasses import dataclass

ALLOWED_TRANSPORTS = {"udp", "tcp", "http"}
ALLOWED_PROFILES = {"baseline", "main", "high"}
ALLOWED_LOG_LEVELS = {"debug", "info", "warning", "error", "critical"}

_MIN_PORT = 1
_MAX_PORT = 65535


@dataclass(frozen=True)
class StreamConfig:
    # Camera / encoder
    width: int
    height: int
    fps: int
    bitrate: int
    gop: int
    profile: str

    # Transport
    transport: str
    host: str
    udp_port: int
    tcp_port: int
    http_port: int

    # Logging
    log_level: str
    log_path: str

    @property
    def resolution(self) -> tuple[int, int]:
        return (self.width, self.height)

    @property
    def port(self) -> int:
        """Return the active port for the configured transport."""
        return {"udp": self.udp_port, "tcp": self.tcp_port, "http": self.http_port}[
            self.transport
        ]


def parse_stream_config(argv: list[str] | None = None) -> StreamConfig:
    parser = argparse.ArgumentParser(description="Raspberry Pi camera streaming server")

    # Config file
    parser.add_argument(
        "--config",
        type=str,
        default="config/config.json",
        help="Path to JSON config file (default: config/config.json)",
    )

    # Camera / encoder flags
    parser.add_argument("--width", type=int, default=None, help="Video width in pixels")
    parser.add_argument("--height", type=int, default=None, help="Video height in pixels")
    parser.add_argument("--fps", type=int, default=None, help="Frames per second")
    parser.add_argument("--bitrate", type=int, default=None, help="H.264 bitrate (bps)")
    parser.add_argument("--gop", type=int, default=None, help="H.264 GOP/keyframe interval")
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="H.264 profile: baseline, main, or high",
    )

    # Transport flags
    parser.add_argument(
        "--transport",
        type=str,
        default=None,
        help="Streaming transport: udp, tcp, or http (default: udp)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Bind address for the streaming server (default: 0.0.0.0)",
    )
    parser.add_argument("--udp-port", type=int, default=None, help="UDP server port (default: 9999)")
    parser.add_argument("--tcp-port", type=int, default=None, help="TCP server port (default: 8888)")
    parser.add_argument(
        "--http-port", type=int, default=None, help="HTTP/MJPEG server port (default: 8080)"
    )

    # Logging flags
    parser.add_argument(
        "--log-level",
        type=str,
        default=None,
        help="Logging level: debug, info, warning, error, or critical (default: info)",
    )
    parser.add_argument(
        "--log-path",
        type=str,
        default=None,
        help="Log file path (default: logs/streamer.log)",
    )

    args = parser.parse_args(argv)

    # ── Hardcoded defaults ──────────────────────────────────────────────────
    width = 640
    height = 480
    fps = 30
    bitrate = 2_000_000
    gop = 30
    profile = "baseline"
    transport = "udp"
    host = "0.0.0.0"
    udp_port = 9999
    tcp_port = 8888
    http_port = 8080
    log_level = "info"
    log_path = "logs/streamer.log"

    # ── JSON config (overrides defaults) ────────────────────────────────────
    if args.config and os.path.exists(args.config):
        with open(args.config, "r", encoding="utf-8") as config_file:
            data = json.load(config_file)
        width = int(data.get("width", width))
        height = int(data.get("height", height))
        fps = int(data.get("fps", fps))
        bitrate = int(data.get("bitrate", bitrate))
        gop = int(data.get("gop", gop))
        profile = str(data.get("profile", profile))
        transport = str(data.get("transport", transport))
        host = str(data.get("host", host))
        udp_port = int(data.get("udp_port", udp_port))
        tcp_port = int(data.get("tcp_port", tcp_port))
        http_port = int(data.get("http_port", http_port))
        log_level = str(data.get("log_level", log_level))
        log_path = str(data.get("log_path", log_path))

    # ── CLI flags (highest priority) ────────────────────────────────────────
    if args.width is not None:
        width = args.width
    if args.height is not None:
        height = args.height
    if args.fps is not None:
        fps = args.fps
    if args.bitrate is not None:
        bitrate = args.bitrate
    if args.gop is not None:
        gop = args.gop
    if args.profile is not None:
        profile = args.profile
    if args.transport is not None:
        transport = args.transport
    if args.host is not None:
        host = args.host
    if args.udp_port is not None:
        udp_port = args.udp_port
    if args.tcp_port is not None:
        tcp_port = args.tcp_port
    if args.http_port is not None:
        http_port = args.http_port
    if args.log_level is not None:
        log_level = args.log_level
    if args.log_path is not None:
        log_path = args.log_path

    # ── Validation ──────────────────────────────────────────────────────────
    if width <= 0 or height <= 0 or fps <= 0 or bitrate <= 0 or gop <= 0:
        raise ValueError("width, height, fps, bitrate, and gop must be positive integers")

    if profile not in ALLOWED_PROFILES:
        raise ValueError(f"profile must be one of: {', '.join(sorted(ALLOWED_PROFILES))}")

    if transport not in ALLOWED_TRANSPORTS:
        raise ValueError(f"transport must be one of: {', '.join(sorted(ALLOWED_TRANSPORTS))}")

    for port_name, port_val in (
        ("udp_port", udp_port),
        ("tcp_port", tcp_port),
        ("http_port", http_port),
    ):
        if not (_MIN_PORT <= port_val <= _MAX_PORT):
            raise ValueError(
                f"{port_name} must be between {_MIN_PORT} and {_MAX_PORT}, got {port_val}"
            )

    if log_level not in ALLOWED_LOG_LEVELS:
        raise ValueError(
            f"log_level must be one of: {', '.join(sorted(ALLOWED_LOG_LEVELS))}"
        )

    return StreamConfig(
        width=width,
        height=height,
        fps=fps,
        bitrate=bitrate,
        gop=gop,
        profile=profile,
        transport=transport,
        host=host,
        udp_port=udp_port,
        tcp_port=tcp_port,
        http_port=http_port,
        log_level=log_level,
        log_path=log_path,
    )


def get_log_level_constant(log_level: str) -> int:
    """Convert a log-level string to the corresponding :mod:`logging` constant."""
    return getattr(logging, log_level.upper())
