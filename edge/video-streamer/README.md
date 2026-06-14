# edge/video-streamer

Raspberry Pi 5 camera streaming server.  Captures live video via
[Picamera2](https://github.com/raspberrypi/picamera2), encodes it with
H.264/AVC, and delivers it over multiple transports.

---

## Directory layout

```
edge/video-streamer/
├── streamer.py        # Legacy UDP/TCP/HTTP-MJPEG streaming (JPEG frames)
├── config.py          # StreamConfig dataclass + JSON/CLI config parser
├── hls/               # LL-HLS pipeline (new, PEN-52)
│   ├── __init__.py
│   ├── segment.py     # PartialSegment + Segment data models
│   ├── store.py       # Thread-safe sliding-window SegmentStore
│   ├── muxer.py       # Minimal MPEG-TS muxer (PAT + PMT + H.264 PES)
│   ├── segmenter.py   # H.264 Annex B IDR detection + segment/part flushing
│   ├── playlist.py    # LL-HLS M3U8 playlist generator
│   └── server.py      # HTTP server with blocking playlist reload
├── config/
│   └── config.json    # Default encoding settings
├── tests/
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_segmenter.py  # HLSSegmenter + NAL-unit helpers
│   ├── test_store.py      # SegmentStore ring-buffer + blocking reload
│   └── test_playlist.py   # PlaylistGenerator M3U8 format
└── requirements.txt
```

---

## Running

### Legacy (UDP/JPEG)

```bash
cd edge/video-streamer
python streamer.py                         # interactive mode selection
python streamer.py --config config/config.json
```

### LL-HLS pipeline (Pi)

Wire the `hls` package into your camera capture loop:

```python
from pathlib import Path
from hls import HLSSegmenter, SegmentStore, PlaylistGenerator, LLHLSServer

store     = SegmentStore(max_segments=5)
segmenter = HLSSegmenter(output_dir=Path("/tmp/hls"), store=store,
                          target_duration=2.0, part_target=0.25)
generator = PlaylistGenerator(target_duration=2.0, part_target=0.25)
server    = LLHLSServer(store, generator, output_dir=Path("/tmp/hls"), port=8888)
server.start()

# Inside the Picamera2 output callback:
def on_h264_data(data: bytes):
    segmenter.feed(data)
```

Clients can then play the stream via:

```
http://<pi-ip>:8888/index.m3u8    ← master playlist
http://<pi-ip>:8888/stream.m3u8   ← media playlist (LL-HLS blocking reload)
```

---

## LL-HLS pipeline (hls/)

The pipeline targets [RFC 8216bis](https://datatracker.ietf.org/doc/draft-pantos-hls-rfc8216bis/)
(Low-Latency HLS).  End-to-end latency goal: **2–4 s** (LAN).

### Components

| Module | Role |
|--------|------|
| `segment.py` | `PartialSegment` (sub-second part) and `Segment` (full segment) data classes |
| `store.py` | `SegmentStore` – bounded deque of completed segments + pending parts.  `wait_for_part(msn, part_index)` implements the blocking-reload wait. |
| `muxer.py` | `mux_h264_to_ts()` – wraps raw H.264 Annex B bytes in MPEG-TS packets (PAT + PMT + PES, 188-byte packets). |
| `segmenter.py` | `HLSSegmenter` – detects IDR (keyframe) NAL units, accumulates frames, flushes partial segments every `part_target` s, and finalises full segments at IDR boundaries after `target_duration` s have elapsed.  Also exposes `contains_idr()` and `find_nal_boundaries()` as standalone utilities. |
| `playlist.py` | `PlaylistGenerator` – produces standards-compliant M3U8 text with all required LL-HLS tags (`#EXT-X-VERSION:9`, `#EXT-X-SERVER-CONTROL`, `#EXT-X-PART-INF`, `#EXT-X-PART`, `#EXT-X-PRELOAD-HINT`). |
| `server.py` | `LLHLSServer` – threaded `HTTPServer` serving playlists and `.ts` files.  Holds the `stream.m3u8` response until the requested `_HLS_msn` / `_HLS_part` is available (LL-HLS blocking reload). |

### Playlist format

**Media playlist** example (`stream.m3u8`):

```m3u8
#EXTM3U
#EXT-X-VERSION:9
#EXT-X-TARGETDURATION:3
#EXT-X-PART-INF:PART-TARGET=0.250
#EXT-X-SERVER-CONTROL:CAN-BLOCK-RELOAD=YES,PART-HOLD-BACK=0.750
#EXT-X-MEDIA-SEQUENCE:0

#EXT-X-PART:DURATION=0.25000,URI="part0_0.ts",INDEPENDENT=YES
#EXT-X-PART:DURATION=0.25000,URI="part0_1.ts"
#EXT-X-PART:DURATION=0.25000,URI="part0_2.ts"
#EXT-X-PART:DURATION=0.25000,URI="part0_3.ts"
#EXTINF:2.00000,
seg0.ts

#EXT-X-PART:DURATION=0.22000,URI="part1_0.ts",INDEPENDENT=YES
#EXT-X-PRELOAD-HINT:TYPE=PART,URI="part1_1.ts"
```

---

## Configuration

All camera and encoding parameters are configurable via JSON or CLI:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `width` | 640 | Video width (pixels) |
| `height` | 480 | Video height (pixels) |
| `fps` | 30 | Frame rate |
| `bitrate` | 2000000 | H.264 bitrate (bps) |
| `gop` | 30 | Keyframe interval (frames) |
| `profile` | `baseline` | H.264 profile (`baseline`, `main`, `high`) |

```bash
python streamer.py --width 1280 --height 720 --fps 30 --bitrate 3000000
```

---

## Tests

```bash
# All tests (131 total: 14 config + 117 LL-HLS)
cd edge/video-streamer
python -m pytest tests/ -v

# LL-HLS tests only
python -m pytest tests/test_segmenter.py tests/test_store.py tests/test_playlist.py -v
```

The LL-HLS tests cover:
- **`test_segmenter.py`** (36 tests) – NAL boundary detection, IDR detection, SPS/PPS extraction, `HLSSegmenter` segment/part creation, timing, file writing, MPEG-TS packet alignment.
- **`test_store.py`** (32 tests) – `SegmentStore` ring-buffer, eviction, media-sequence tracking, snapshot atomicity, `wait_for_part` blocking/timeout, concurrent access.
- **`test_playlist.py`** (49 tests) – All required LL-HLS M3U8 tags (`#EXT-X-VERSION`, `#EXT-X-SERVER-CONTROL`, `#EXT-X-PART-INF`, `#EXT-X-PART`, `#EXT-X-PRELOAD-HINT`, `#EXTINF`), master playlist format.

All tests run on the development machine without Raspberry Pi hardware (no `picamera2` import in the `hls/` package).
