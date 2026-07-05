"""
Regression test for edge/video-streamer/streamer.py encoder construction.

Neither picamera2 nor opencv-python (cv2) are installed in CI (see
.github/workflows/ci-edge.yml, which installs only pytest — this test suite is
expected to run without Pi-only hardware bindings). We inject fake picamera2
and cv2 modules into sys.modules before import so streamer.py can be imported
at all. The fake H264Encoder mirrors the real H264Encoder/LibavH264Encoder
constructor signature (bitrate, repeat, iperiod, framerate, qp, profile) so an
invalid kwarg like the old `intra_period` fails the same way it does on-device.
cv2 is only referenced inside VideoStreamer.capture_frame, never during
construction, so a bare stub module is enough here.
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

    cv2_module = types.ModuleType("cv2")
    cv2_module.COLOR_RGB2BGR = 4
    cv2_module.cvtColor = lambda frame, code: frame

    monkeypatch.setitem(sys.modules, "picamera2", picamera2_module)
    monkeypatch.setitem(sys.modules, "picamera2.encoders", encoders_module)
    monkeypatch.setitem(sys.modules, "picamera2.outputs", outputs_module)
    monkeypatch.setitem(sys.modules, "cv2", cv2_module)
    monkeypatch.delitem(sys.modules, "streamer", raising=False)

    yield

    monkeypatch.delitem(sys.modules, "streamer", raising=False)


def test_video_streamer_builds_encoder_with_valid_kwargs(fake_picamera2):
    import streamer

    stream = streamer.VideoStreamer(gop=45, bitrate=1_500_000, profile="main")
    assert stream.h264_encoder.kwargs["iperiod"] == 45
    assert "intra_period" not in stream.h264_encoder.kwargs
