# HLS Playback Runbook

**Milestone**: M2-6 HLS Integration Checklist and Runbook
**Integration checklist**: See [HLS_INTEGRATION_CHECKLIST.md](./HLS_INTEGRATION_CHECKLIST.md)

## 1. Overview

This runbook covers day-to-day operations for the LL-HLS live streaming pipeline:
starting, stopping, monitoring, and troubleshooting the stream from the Raspberry Pi to
iOS and web clients. Refer to [HLS.md](./HLS.md) for protocol/architecture background
and [ARC42.md](./ARC42.md) for the full system architecture.

### Quick-reference pipeline

```
Pi Camera v2.1
  → Picamera2 capture
  → H.264 encoder (hardware-accelerated, configured via config.json)
  → HLS segmenter (LL-HLS, ~1 s segments / ~200–500 ms parts)
  → Output directory: <HLS_OUTPUT_DIR>  (e.g. /var/hls)
  → Nginx HTTP server  →  http://<pi-ip>/hls/playlist.m3u8
                        →  iOS AVPlayer / Safari
                        →  Browser hls.js (clients/web)
```

---

## 2. Environment and Configuration

### 2.1 Key paths

| Item | Default path / value |
|------|----------------------|
| Streamer source | `edge/video-streamer/streamer.py` |
| Encoder config | `edge/video-streamer/config/config.json` |
| HLS output directory | `/var/hls` (configure to match Nginx root) |
| Nginx site config | `/etc/nginx/sites-available/hls` |
| Nginx access log | `/var/log/nginx/access.log` |
| Nginx error log | `/var/log/nginx/error.log` |
| Streamer log | stdout / systemd journal (`journalctl -u wrack-streamer`) |

### 2.2 Encoder defaults (`config.json`)

```json
{
  "width": 1280,
  "height": 720,
  "fps": 30,
  "bitrate": 2000000,
  "gop": 30,
  "profile": "main"
}
```

Override any value via CLI flags (see `streamer.py --help`).

### 2.3 Nginx HLS site config (reference)

```nginx
server {
    listen 80;
    server_name _;

    location /hls {
        types {
            application/vnd.apple.mpegurl m3u8;
            video/mp4                     m4s mp4;
        }
        root /var;              # files served from /var/hls/...
        add_header Cache-Control "no-cache" always;
        add_header Access-Control-Allow-Origin "*" always;
    }
}
```

Adjust `root` and `server_name` to match your deployment. For HTTPS, add a `ssl_certificate` / `ssl_certificate_key` block.

---

## 3. Starting the Pipeline

### Step 1 — Verify hardware

```bash
# On the Raspberry Pi
vcgencmd get_camera
# Expected: supported=1 detected=1

# Confirm the camera is not already in use by another process
sudo fuser /dev/video0
# Should return empty or your own PID
```

### Step 2 — Prepare the HLS output directory

```bash
sudo mkdir -p /var/hls
sudo chown pi:pi /var/hls      # replace 'pi' with the service account user
```

### Step 3 — Start Nginx

```bash
sudo nginx -t                  # validate config
sudo systemctl start nginx
sudo systemctl status nginx    # confirm Active: running
```

### Step 4 — Start the streaming process

**Development / ad-hoc run**:

```bash
cd /path/to/wrack/edge/video-streamer
python3 streamer.py --config config/config.json
```

**Production (systemd)**:

```bash
sudo systemctl start wrack-streamer
sudo systemctl status wrack-streamer
```

Expected startup log lines:

```
[INFO]  Camera initialised: 1280x720 @ 30fps
[INFO]  H.264 encoder started (profile=main, bitrate=2000000, gop=30)
[INFO]  HLS segmenter active → /var/hls/playlist.m3u8
[INFO]  Streaming started
```

### Step 5 — Verify playlist is being served

```bash
curl -s http://localhost/hls/playlist.m3u8 | head -20
# Expected: starts with #EXTM3U and contains #EXT-X-TARGETDURATION
```

### Step 6 — Verify from a client

Open on an iOS device or browser:

```
http://<pi-ip>/hls/playlist.m3u8
```

For the web client, set `NEXT_PUBLIC_HLS_STREAM_URL=http://<pi-ip>/hls/playlist.m3u8` in
`clients/web/.env.local`, then start the dev server with `npm run dev`.

---

## 4. Stopping the Pipeline

**Ad-hoc process** (Ctrl-C in the terminal, or):

```bash
kill $(pgrep -f streamer.py)
```

**systemd service**:

```bash
sudo systemctl stop wrack-streamer
```

**Nginx** (stop only if shutting down entirely; not needed for streamer restarts):

```bash
sudo systemctl stop nginx
```

---

## 5. Restarting the Pipeline

```bash
# Restart just the streamer (Nginx stays running)
sudo systemctl restart wrack-streamer

# Full restart (streamer + Nginx)
sudo systemctl restart nginx
sudo systemctl restart wrack-streamer
```

After restart, allow up to 10 s for the first playlist to appear. Connected clients
running hls.js or AVPlayer will stall briefly and then resume once the playlist refreshes.

---

## 6. Health Checks

### 6.1 Quick status

```bash
# Systemd service status
sudo systemctl status wrack-streamer nginx

# Check playlist is being updated (run twice, a few seconds apart)
stat /var/hls/playlist.m3u8
```

### 6.2 Playlist freshness check

```bash
# Poll playlist; compare EXT-X-MEDIA-SEQUENCE across 3 polls
for i in 1 2 3; do
  curl -s http://localhost/hls/playlist.m3u8 | grep MEDIA-SEQUENCE
  sleep 2
done
# Sequence number must increase each time
```

### 6.3 Segment availability

```bash
# Get the latest segment name from the playlist and fetch it
SEGMENT=$(curl -s http://localhost/hls/playlist.m3u8 | grep '\.m4s' | tail -1)
curl -I "http://localhost/hls/${SEGMENT}"
# Expect: HTTP/1.1 200 OK, Content-Type: video/mp4
```

### 6.4 CPU and memory on the Pi

```bash
top -b -n 1 | head -20
# Confirm streamer process CPU < 50% sustained
```

### 6.5 Disk usage for HLS output

```bash
df -h /var/hls
du -sh /var/hls
# Ensure at least 500 MB free; segments should roll over automatically
```

---

## 7. Log Locations and What to Look For

| Log | Location | What to look for |
|-----|----------|------------------|
| Streamer stdout | `journalctl -u wrack-streamer -f` (or terminal) | `[ERROR]` lines; FPS drop warnings; encoder restart events |
| Nginx access | `/var/log/nginx/access.log` | `4xx`/`5xx` status codes; missing segment requests |
| Nginx error | `/var/log/nginx/error.log` | Permission errors; `open() failed` for HLS files |
| Kernel camera | `dmesg \| grep -i camera` | Camera driver failures; ENOMEM on allocation |

**Key log patterns to alert on**:

- `[ERROR] Encoder failed` — encoder crash; streamer must be restarted
- `[WARN] Frame dropped` — consistent drops indicate CPU overload or camera bus issues
- `open() "/var/hls/..." failed` in Nginx error log — file not written; check segmenter
- `5xx` in Nginx access log — Nginx misconfiguration or disk full

---

## 8. Common Failures and Troubleshooting

### 8.1 Client shows a black screen or spinner immediately

**Likely causes:**

1. Playlist not yet generated — wait up to 10 s after starting the streamer.
2. Nginx is not running or not serving the HLS directory.
3. CORS header missing when playing from a different origin (web client).

**Actions:**

```bash
# Is Nginx running?
sudo systemctl status nginx

# Is the playlist file there?
ls -lh /var/hls/playlist.m3u8

# Is Nginx serving it?
curl -I http://localhost/hls/playlist.m3u8
```

---

### 8.2 Playlist is stale (sequence number not advancing)

**Likely cause:** HLS segmenter has crashed or stalled.

**Actions:**

```bash
# Check streamer logs
journalctl -u wrack-streamer -n 50

# Restart the streamer
sudo systemctl restart wrack-streamer
```

---

### 8.3 iOS Safari shows "The operation could not be completed"

**Likely causes:**

1. Incorrect `Content-Type` for `.m3u8` — must be `application/vnd.apple.mpegurl`.
2. `EXT-X-MAP` init segment missing or unreachable.
3. HTTPS required — iOS 14+ blocks mixed-content HTTP streams on HTTPS pages.

**Actions:**

```bash
# Check Content-Type
curl -I http://<pi-ip>/hls/playlist.m3u8 | grep -i content-type

# Check init segment
INIT=$(curl -s http://<pi-ip>/hls/playlist.m3u8 | grep 'EXT-X-MAP' | sed 's/.*URI="\(.*\)".*/\1/')
curl -I "http://<pi-ip>/hls/${INIT}"
```

---

### 8.4 High latency (> 4 s on LAN)

**Likely causes:**

1. Segment duration too long (> 1 s).
2. `EXT-X-PART` partial segments not being produced or not consumed by player.
3. Client-side buffering strategy is too conservative.

**Actions:**

- Inspect `EXT-X-TARGETDURATION` and `EXT-X-PART-INF PART-TARGET` in the playlist; confirm they are ≤ 1 and ≤ 0.5 respectively.
- Confirm `EXT-X-SERVER-CONTROL CAN-BLOCK-RELOAD=YES` is present.
- If using hls.js, set `lowLatencyMode: true` in the `Hls` constructor config.
- Check that GOP in `config.json` = FPS (e.g. `"gop": 30` for 30 FPS) so keyframes align with segment boundaries.

---

### 8.5 Nginx returns 404 for segment files

**Likely causes:**

1. Nginx `root` path does not match HLS output directory.
2. HLS output directory ownership prevents Nginx from reading files.
3. Segments are being deleted before they are served (retention window too short).

**Actions:**

```bash
# Verify Nginx root
grep -r 'root' /etc/nginx/sites-enabled/hls

# Check permissions
ls -la /var/hls/

# Check Nginx error log
sudo tail -50 /var/log/nginx/error.log
```

---

### 8.6 Encoder crash or restart

**Symptoms:** Log shows `[ERROR] Encoder failed`; new segments stop appearing; CPU drops to near zero.

**Actions:**

```bash
# View last 100 lines of streamer log
journalctl -u wrack-streamer -n 100

# Restart and monitor
sudo systemctl restart wrack-streamer
journalctl -u wrack-streamer -f
```

If crashes repeat, check:
- Camera sensor temperature (`vcgencmd measure_temp`)
- Available memory (`free -h`)
- Reduce bitrate in `config.json` (e.g. from 4 Mbps to 2 Mbps)

---

### 8.7 hls.js fatal error in browser console

Common fatal error types and responses:

| `hls.ErrorTypes` | `hls.ErrorDetails` | Response |
|------------------|--------------------|----------|
| `NETWORK_ERROR` | `MANIFEST_LOAD_ERROR` | Pi offline; check streamer and Nginx |
| `NETWORK_ERROR` | `FRAG_LOAD_ERROR` | Segments missing; check disk and segmenter |
| `MEDIA_ERROR` | `BUFFER_STALLED_ERROR` | High latency; call `hls.recoverMediaError()` |
| `MEDIA_ERROR` | `BUFFER_APPEND_ERROR` | Codec mismatch; check H.264 profile in config |

Implement a `hls.on(Hls.Events.ERROR, ...)` handler that:
1. Calls `hls.recoverMediaError()` for recoverable media errors.
2. Calls `hls.destroy()` then re-creates the `Hls` instance for fatal network errors.

---

## 9. Rollback Procedure

If a new version of the streaming pipeline causes playback failures:

1. **Stop the failing service:**
   ```bash
   sudo systemctl stop wrack-streamer
   ```

2. **Identify the previous working version:**
   ```bash
   git -C /path/to/wrack log --oneline edge/video-streamer/ -10
   ```

3. **Check out the previous version:**
   ```bash
   git -C /path/to/wrack checkout <previous-commit> -- edge/video-streamer/
   ```

4. **Restart the service:**
   ```bash
   sudo systemctl restart wrack-streamer
   ```

5. **Verify recovery using the quick health checks** (§ 6.1–6.3).

6. **Revert Nginx config changes if needed:**
   ```bash
   sudo git -C /etc/nginx checkout HEAD  # if Nginx config is in version control
   sudo nginx -t && sudo systemctl reload nginx
   ```

---

## 10. Performance Tuning Reference

| Parameter | Location | Effect |
|-----------|----------|--------|
| `bitrate` | `config.json` | Controls video quality and bandwidth; lower for WAN |
| `gop` | `config.json` | Should equal FPS for 1 s keyframe intervals |
| `fps` | `config.json` | Reduce on constrained hardware (e.g. 15 FPS for < 25% CPU) |
| `EXT-X-TARGETDURATION` | Segmenter config | Lower = lower latency; < 1 s for LL-HLS |
| `PART-TARGET` | Segmenter config | Lower = lower latency; 0.2–0.5 s recommended |
| `lowLatencyMode` | `Hls` constructor (web) | Must be `true` to benefit from LL-HLS parts |

---

## 11. Escalation

| Scenario | Action |
|----------|--------|
| Camera hardware failure | Replace or re-seat Pi Camera; reboot Pi |
| Persistent encoder crashes with no log clue | File a bug in Linear with full `journalctl` output |
| Latency consistently > 8 s despite tuning | Review PRD § 3 latency targets; consider WebRTC (M3) |
| Security incident (unexpected public access) | Immediately stop Nginx (`sudo systemctl stop nginx`); rotate secrets; review Nginx config |

---

## Related Documents

- [HLS Architecture Overview](./HLS.md)
- [HLS Integration Test Checklist](./HLS_INTEGRATION_CHECKLIST.md)
- [System Architecture (ARC42)](./ARC42.md)
- [Product Requirements (PRD)](../requirements/PRD.md)
