import pytest

from config import parse_stream_config


def test_defaults_used_when_no_args_and_no_config(tmp_path):
    config = parse_stream_config(["--config", str(tmp_path / "missing.json")])
    assert config.width == 640
    assert config.height == 480
    assert config.fps == 30
    assert config.bitrate == 2_000_000
    assert config.gop == 30
    assert config.profile == "baseline"


def test_json_config_used_when_present(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        '{"width": 1280, "height": 720, "fps": 25, "bitrate": 3000000, "gop": 60, "profile": "main"}'
    )
    config = parse_stream_config(["--config", str(config_path)])
    assert config.width == 1280
    assert config.height == 720
    assert config.fps == 25
    assert config.bitrate == 3_000_000
    assert config.gop == 60
    assert config.profile == "main"


def test_cli_overrides_json(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        '{"width": 1280, "height": 720, "fps": 25, "bitrate": 3000000, "gop": 60, "profile": "main"}'
    )
    config = parse_stream_config(
        [
            "--config",
            str(config_path),
            "--width",
            "1920",
            "--fps",
            "60",
            "--bitrate",
            "5000000",
            "--gop",
            "120",
            "--profile",
            "high",
        ]
    )
    assert config.width == 1920
    assert config.height == 720
    assert config.fps == 60
    assert config.bitrate == 5_000_000
    assert config.gop == 120
    assert config.profile == "high"


@pytest.mark.parametrize(
    "args",
    [
        ["--width", "0"],
        ["--height", "0"],
        ["--fps", "0"],
        ["--bitrate", "0"],
        ["--gop", "0"],
        ["--width", "-1"],
        ["--height", "-1"],
        ["--fps", "-1"],
        ["--bitrate", "-1"],
        ["--gop", "-1"],
    ],
)
def test_invalid_values_raise(args):
    with pytest.raises(ValueError):
        parse_stream_config(args)


def test_invalid_profile_raises():
    with pytest.raises(ValueError):
        parse_stream_config(["--profile", "unsupported"])
