"""
Regression test for edge/video-streamer/streamer.py encoder construction and the
live H.264 encoding path (PEN-224).

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

import queue
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
    def __init__(self):
        self.started_encoders = []
        self.stopped_encoders = []

    def create_video_configuration(self, **kwargs):
        return {}

    def configure(self, config):
        pass

    def start(self):
        pass

    def start_encoder(self, encoder, output):
        self.started_encoders.append((encoder, output))

    def stop_encoder(self, encoder):
        self.stopped_encoders.append(encoder)


@pytest.fixture
def fake_picamera2(monkeypatch):
    picamera2_module = types.ModuleType("picamera2")
    picamera2_module.Picamera2 = _FakePicamera2

    encoders_module = types.ModuleType("picamera2.encoders")
    encoders_module.H264Encoder = _FakeH264Encoder

    outputs_module = types.ModuleType("picamera2.outputs")
    outputs_module.Output = object

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


# ---------------------------------------------------------------------------
# ChunkQueueOutput
# ---------------------------------------------------------------------------

def test_chunk_queue_output_drops_until_first_keyframe(fake_picamera2):
    import streamer

    output = streamer.ChunkQueueOutput()
    output.outputframe(b"p-frame-1", keyframe=False)
    output.outputframe(b"p-frame-2", keyframe=False)
    output.outputframe(b"idr", keyframe=True)
    output.outputframe(b"p-frame-3", keyframe=False)

    assert output.get(timeout=0) == b"idr"
    assert output.get(timeout=0) == b"p-frame-3"


def test_chunk_queue_output_drops_oldest_and_rearms_keyframe_gate(fake_picamera2):
    import streamer

    output = streamer.ChunkQueueOutput(maxsize=2)
    output.outputframe(b"idr-1", keyframe=True)
    output.outputframe(b"p-1", keyframe=False)
    output.outputframe(b"p-2", keyframe=False)  # queue full -> drops "idr-1", re-arms gate

    # Gate is re-armed: further non-keyframe chunks are dropped until the next keyframe.
    output.outputframe(b"p-3", keyframe=False)
    output.outputframe(b"idr-2", keyframe=True)

    remaining = []
    while True:
        try:
            remaining.append(output.get(timeout=0))
        except queue.Empty:
            break

    assert b"p-1" in remaining or b"p-2" in remaining
    assert b"p-3" not in remaining
    assert remaining[-1] == b"idr-2"


# ---------------------------------------------------------------------------
# VideoStreamer stream_format wiring
# ---------------------------------------------------------------------------

def test_jpeg_mode_does_not_start_encoder(fake_picamera2):
    import streamer

    stream = streamer.VideoStreamer()
    assert stream.stream_format == "jpeg"
    assert stream._h264_output is None
    assert stream.picam2.started_encoders == []


def test_h264_mode_starts_encoder_and_captures_chunks(fake_picamera2):
    import streamer

    stream = streamer.VideoStreamer(stream_format="h264")
    assert stream._h264_output is not None
    assert len(stream.picam2.started_encoders) == 1

    stream._h264_output.outputframe(b"idr", keyframe=True)
    assert stream.capture_encoded_frame(timeout=0.5) == b"idr"
    assert stream.capture_encoded_frame(timeout=0.01) is None


def test_stop_encoder_if_started_is_noop_in_jpeg_mode(fake_picamera2):
    import streamer

    stream = streamer.VideoStreamer()
    stream.stop_encoder_if_started()
    assert stream.picam2.stopped_encoders == []


def test_stop_encoder_if_started_stops_encoder_in_h264_mode(fake_picamera2):
    import streamer

    stream = streamer.VideoStreamer(stream_format="h264")
    stream.stop_encoder_if_started()
    assert stream.picam2.stopped_encoders == [stream.h264_encoder]


# ---------------------------------------------------------------------------
# UDP send path: h264 payloads are sent raw, not pickled
# ---------------------------------------------------------------------------

def test_udp_h264_mode_sends_raw_bytes_not_pickled(fake_picamera2, monkeypatch):
    import streamer

    stream = streamer.UDPVideoStreamer(port=0, stream_format="h264")
    stream.clients = {("127.0.0.1", 12345): 0.0}

    monkeypatch.setattr(stream, "capture_encoded_frame", lambda timeout=1.0: b"raw-h264-bytes")
    monkeypatch.setattr(stream, "_write_metrics", lambda fps_recent: None)

    sent = {}

    def fake_send(data, client_addr, frame_id):
        sent["data"] = data
        stream.running = False  # stop after the first loop iteration

    monkeypatch.setattr(stream, "send_frame_to_client", fake_send)

    stream.running = True
    stream.stream_to_clients()

    assert sent["data"] == b"raw-h264-bytes"


# ---------------------------------------------------------------------------
# TCP / HTTP reject h264 stream_format
# ---------------------------------------------------------------------------

def test_tcp_streamer_rejects_h264(fake_picamera2):
    import streamer

    with pytest.raises(ValueError):
        streamer.TCPVideoStreamer(stream_format="h264")


def test_http_streamer_rejects_h264(fake_picamera2):
    import streamer

    with pytest.raises(ValueError):
        streamer.HTTPVideoStreamer(stream_format="h264")
