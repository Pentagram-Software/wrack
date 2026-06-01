# WAN Validation Runbook — M2-5

This document describes how to validate UDP video stream playback and latency
over a wide-area network (WAN) connection.  It covers the tooling, test
procedures, expected results, and pass/fail criteria.

---

## 1. Overview

**Goal:** Confirm that the `UDPVideoStreamer` on the Raspberry Pi delivers
acceptable frame quality and latency to a remote client over a real or
simulated WAN path.

**Success criteria (defaults; override via CLI):**

| Metric | Pass threshold |
|--------|---------------|
| p95 frame-assembly latency | ≤ 200 ms |
| Frame loss | ≤ 5 % |
| Mean received FPS | ≥ 20 FPS |
| Mean inter-frame jitter | ≤ 50 ms |

---

## 2. Components

| File | Purpose |
|------|---------|
| `samples/python-video-receiver/wan_validator.py` | CLI validation tool – measures latency, frame loss, jitter |
| `samples/python-video-receiver/latency_metrics.py` | Metrics primitives: `FrameLatencyTracker`, `LatencyStats`, validation logic |
| `samples/python-video-receiver/network_sim.py` | WAN simulation via `tc netem` (Linux, root required) |
| `samples/python-video-receiver/main.py` | Live receiver with latency stats in periodic output |

---

## 3. Prerequisites

### Streaming server (Raspberry Pi)

```bash
cd edge/video-streamer
python3 streamer.py   # choose option 1 (UDP)
```

Ensure UDP port 9999 is reachable from the validator host:

```bash
# On router: forward UDP 9999 → Pi's LAN IP
# On Pi firewall:
sudo ufw allow 9999/udp
```

### Validator host (macOS / Linux)

```bash
cd samples/python-video-receiver
pip install -r requirements.txt
```

Required Python packages: `opencv-python` (headless OK), `numpy`.  
Optional for H.264 mode: `pip install av`.

---

## 4. Basic WAN Validation

Run the validator against the streaming server.  Replace `<PI_PUBLIC_IP>` with
the Pi's public IP address (or its local IP for LAN tests):

```bash
python3 wan_validator.py --server-ip <PI_PUBLIC_IP>
```

Default parameters: 30 s measurement window, 9999 UDP port, 30 FPS expected.

**Example output:**

```
Measuring RTT to 203.0.113.10:9999 … 48.2 ms

Receiving frames from 203.0.113.10:9999 for 30 s …
  Registered with server 203.0.113.10:9999

─────────────────────────────────────
  Latency & Quality Metrics
─────────────────────────────────────
  Frames received:        891
  Duration:               30.0 s
  Mean FPS:               29.7
  Frame loss:             1.0 %
  Assembly latency p50:   12.4 ms
  Assembly latency p95:   38.1 ms
  Assembly latency p99:   61.2 ms
  Max assembly latency:   98.0 ms
  Mean jitter:            9.3 ms
  Network RTT:            48.2 ms
─────────────────────────────────────

RESULT: PASS
```

---

## 5. Customising the Measurement

### Longer window and stricter thresholds

```bash
python3 wan_validator.py \
  --server-ip <PI_PUBLIC_IP> \
  --duration 120 \
  --max-p95-ms 150 \
  --max-loss-pct 2 \
  --min-fps 25 \
  --max-jitter-ms 30
```

### Save a JSON report

```bash
python3 wan_validator.py \
  --server-ip <PI_PUBLIC_IP> \
  --duration 60 \
  --json-report /tmp/wan_report.json

cat /tmp/wan_report.json
```

The report contains `server`, `wan_preset`, `thresholds`, `stats`, and
`validation` keys suitable for CI artefact storage or trend analysis.

---

## 6. Simulated WAN Testing

The `--wan-preset` flag applies traffic-shaping rules via `tc netem` on the
**validator host** before the measurement window.  Root privileges are required
on Linux.

Available presets:

| Preset | Latency | Jitter | Loss | Bandwidth |
|--------|---------|--------|------|-----------|
| `ideal_lan` | 0 ms | 0 ms | 0% | unlimited |
| `good_wan` | 20 ms | 5 ms | 0.1% | 10 Mbps |
| `typical_wan` | 50 ms | 15 ms | 0.5% | 5 Mbps |
| `poor_wan` | 120 ms | 30 ms | 2% | 2 Mbps |
| `mobile_4g` | 80 ms | 20 ms | 1% | 3 Mbps |
| `mobile_3g` | 200 ms | 50 ms | 3% | 1 Mbps |

**Run with simulation (requires root, Linux only):**

```bash
sudo python3 wan_validator.py \
  --server-ip <PI_LAN_IP> \
  --wan-preset typical_wan \
  --interface eth0
```

The tool automatically removes the `tc` rules on exit (including on error).

**Dry run (preview tc commands without executing):**

```bash
python3 wan_validator.py \
  --server-ip <PI_LAN_IP> \
  --wan-preset typical_wan \
  --dry-run-sim
```

### Programmatic use from Python

```python
from network_sim import NetworkSimulator, WAN_PRESETS

sim = NetworkSimulator(interface="eth0")
with sim.apply_context(WAN_PRESETS["typical_wan"]):
    # run your own receiver / test code here
    pass
# tc rules removed automatically
```

---

## 7. Live Receiver with Latency Display

The standard `main.py` receiver now prints latency stats alongside FPS every
5 seconds:

```
--- Video Stats ---
Frames received: 150
Decode failures: 0
Runtime: 5.0s
Average FPS: 29.9
Assembly latency p50/p95: 11.2 / 35.4 ms
Frame loss (est): 0.3%
Jitter (mean): 8.7 ms
------------------
```

Final session summary on exit also includes p99 latency:

```
=== Final Statistics ===
Total frames received: 897
Decode failures: 0
Total runtime: 30.1s
Average FPS: 29.8
Assembly latency p50/p95/p99: 11.2 / 36.1 / 58.4 ms
Frame loss (est): 0.7%
Jitter (mean): 8.9 ms
========================
```

---

## 8. Interpreting Results

### Assembly latency

"Assembly latency" is the time from when the first UDP chunk of a frame is
received until all chunks have arrived and the frame is fully reassembled.
This measures **network delivery time per frame** (not capture-to-display E2E).

Expected ranges under common conditions:

| Condition | p50 | p95 |
|-----------|-----|-----|
| LAN | < 5 ms | < 15 ms |
| Good WAN (< 100 km) | 10–30 ms | 30–80 ms |
| Intercontinental WAN | 50–150 ms | 100–250 ms |
| Mobile 4G | 30–100 ms | 80–200 ms |

### Frame loss

Frame loss is estimated by comparing completed frames against the expected
frame count (`duration × expected_fps`).  Values below 2 % are normal on
typical WAN paths.  Values above 5 % indicate network congestion or NAT issues.

### Jitter

High jitter (> 50 ms) causes visible stutter.  It can be reduced by:
- Increasing UDP socket receive buffer (`SO_RCVBUF`)
- Using a jitter buffer at the client
- Switching to TCP or HTTP transport when UDP quality is poor

---

## 9. Troubleshooting

| Symptom | Likely cause | Suggested fix |
|---------|-------------|---------------|
| RTT measurement fails | Firewall blocking UDP 9999 | Open UDP 9999 inbound on Pi |
| No frames received | NAT port-forward missing | Forward UDP 9999 on router |
| High frame loss (> 10%) | MTU mismatch / IP fragmentation | Verify chunk size ≤ 1200 B |
| High jitter on 4G | Variable mobile latency | Expected; adjust thresholds |
| `tc` commands fail | Not root / no `tc` binary | Run as root; `apt install iproute2` |

---

## 10. Automated Testing

Unit tests for all validation logic:

```bash
cd samples/python-video-receiver
python3 -m pytest tests/test_latency_metrics.py tests/test_network_sim.py tests/test_wan_validator.py -v
```

Run the full test suite:

```bash
python3 -m pytest tests/ -v
```

Expected: all 105 tests pass.

---

## 11. Related Documents

- `edge/video-streamer/README.md` — streamer setup and network config
- `shared/video-protocol/UDP_Frame_Format_Documentation.md` — protocol spec
- `docs/architecture/HLS.md` — future HLS/LL-HLS latency targets
- `docs/requirements/PRD.md` — non-functional latency requirements
