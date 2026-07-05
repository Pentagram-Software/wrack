import argparse
import json
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class StreamConfig:
    width: int
    height: int
    fps: int
    bitrate: int
    gop: int
    profile: str
    stream_format: str

    @property
    def resolution(self) -> tuple[int, int]:
        return (self.width, self.height)


def parse_stream_config(argv: list[str] | None = None) -> StreamConfig:
    parser = argparse.ArgumentParser(description="Raspberry Pi camera streaming server")
    parser.add_argument(
        "--config",
        type=str,
        default="config/config.json",
        help="Path to JSON config file",
    )
    parser.add_argument("--width", type=int, default=None, help="Video width in pixels")
    parser.add_argument("--height", type=int, default=None, help="Video height in pixels")
    parser.add_argument("--fps", type=int, default=None, help="Frames per second")
    parser.add_argument("--bitrate", type=int, default=None, help="H.264 bitrate (bps)")
    parser.add_argument("--gop", type=int, default=None, help="H.264 GOP/keyframe interval")
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="H.264 profile (baseline, main, high)",
    )
    parser.add_argument(
        "--stream-format",
        type=str,
        default=None,
        help="Streaming payload format (jpeg, h264)",
    )
    args = parser.parse_args(argv)

    # Start with defaults
    width = 640
    height = 480
    fps = 30
    bitrate = 2_000_000
    gop = 30
    profile = "baseline"
    stream_format = "jpeg"

    # Override with JSON config if provided and exists
    if args.config and os.path.exists(args.config):
        with open(args.config, "r", encoding="utf-8") as config_file:
            config_data = json.load(config_file)
        width = int(config_data.get("width", width))
        height = int(config_data.get("height", height))
        fps = int(config_data.get("fps", fps))
        bitrate = int(config_data.get("bitrate", bitrate))
        gop = int(config_data.get("gop", gop))
        profile = str(config_data.get("profile", profile))
        stream_format = str(config_data.get("stream_format", stream_format))

    # Override with CLI args if explicitly provided (highest priority)
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
    if args.stream_format is not None:
        stream_format = args.stream_format

    if width <= 0 or height <= 0 or fps <= 0 or bitrate <= 0 or gop <= 0:
        raise ValueError("width, height, fps, bitrate, and gop must be positive integers")

    allowed_profiles = {"baseline", "main", "high"}
    if profile not in allowed_profiles:
        raise ValueError("profile must be one of: baseline, main, high")

    allowed_stream_formats = {"jpeg", "h264"}
    if stream_format not in allowed_stream_formats:
        raise ValueError("stream_format must be one of: jpeg, h264")

    return StreamConfig(
        width=width,
        height=height,
        fps=fps,
        bitrate=bitrate,
        gop=gop,
        profile=profile,
        stream_format=stream_format,
    )
