"""
Regression test for edge/video-streamer/streamer.py encoder construction.

picamera2 is not installed in this environment (it ships as a Pi-only package
backed by system libcamera bindings), so streamer.py can't be imported directly
here. We inject fake picamera2 modules into sys.modules before import, mirroring
the real H264Encoder/LibavH264Encoder constructor signature (bitrate, repeat,
iperiod, framerate, qp, profile) so an invalid kwarg like the old `intra_period`
fails the same way it does on-device.
"""

import sys
import types

import pytest


_REAL_H264ENCODER_KWARGS = {"bitrate", "repeat", "iperiod", "framerate", "qp", "profile"}


class _FakeH264Encoder:
    def __init__(self, **kwargs):
        unexpected = set(kwargs) - _REAL_H264ENCODER_KWARGS
        if unexpected:
            raise TypeError(
                f"__init__() got an unexpected keyword argument {next(iter(unexpected))!r}"
            )
        self.kwargs = kwargs


class _FakePicamera2:
    def create_video_configuration(self, **kwargs):
        return {}

    def configure(self, config):
        pass

    def start(self):
        pass


@pytest.fixture
def fake_picamera2(monkeypatch):
    picamera2_module = types.ModuleType("picamera2")
    picamera2_module.Picamera2 = _FakePicamera2

    encoders_module = types.ModuleType("picamera2.encoders")
    encoders_module.H264Encoder = _FakeH264Encoder

    outputs_module = types.ModuleType("picamera2.outputs")
    outputs_module.FileOutput = object

    monkeypatch.setitem(sys.modules, "picamera2", picamera2_module)
    monkeypatch.setitem(sys.modules, "picamera2.encoders", encoders_module)
    monkeypatch.setitem(sys.modules, "picamera2.outputs", outputs_module)
    monkeypatch.delitem(sys.modules, "streamer", raising=False)

    yield

    monkeypatch.delitem(sys.modules, "streamer", raising=False)


def test_video_streamer_builds_encoder_with_valid_kwargs(fake_picamera2):
    import streamer

    stream = streamer.VideoStreamer(gop=45, bitrate=1_500_000, profile="main")
    assert stream.h264_encoder.kwargs["iperiod"] == 45
    assert "intra_period" not in stream.h264_encoder.kwargs
