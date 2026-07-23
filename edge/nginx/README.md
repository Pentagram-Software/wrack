# edge/nginx — Nginx LL-HLS Serving

Nginx reverse-proxy that sits in front of the Python LL-HLS server
(`edge/video-streamer/hls/server.py`) to serve HLS playlists and MPEG-TS
segment files to browsers and native players.

---

## Architecture

```
Browser / hls.js / AVPlayer
        │
        │  HTTP :80 (or custom NGINX_PORT)
        ▼
┌──────────────┐     \.ts$   → long cache (1 year, immutable)
│  Nginx :80   │     \.m3u8$ → no-cache, proxy_read_timeout 15 s
│  (this dir)  │     /health → 200 OK (no upstream)
└──────┬───────┘
       │  proxy_pass http://llhls (HTTP/1.1 keep-alive)
       ▼
┌───────────────────────────────────┐
│  Python LL-HLS server :8888       │
│  edge/video-streamer/hls/server.py│
│  • /index.m3u8  – master playlist │
│  • /stream.m3u8 – media playlist  │
│    (blocking reload via           │
│     ?_HLS_msn=N&_HLS_part=P)      │
│  • /*.ts        – segment files   │
└───────────────────────────────────┘
```

### Why Nginx in front of the Python server?

| Concern | Python server alone | With Nginx |
|---------|--------------------|-----------:|
| Static `.ts` caching | Only in-process | Browser + CDN caching |
| CORS headers | Hardcoded | Configurable per origin |
| TLS termination | Not supported | Add `ssl_certificate` |
| `server_tokens` / security headers | Manual | Centralised |
| Connection keep-alive to backend | Per-request | Up to 32 pooled |
| Readiness probe | Custom endpoint | `/health` (no upstream) |

---

## Directory layout

```
edge/nginx/
├── config.py            # NginxConfigParams dataclass with validation
├── generate_config.py   # Renders nginx.conf from NginxConfigParams
├── nginx.conf           # Generated default config (committed)
├── Dockerfile           # nginx:alpine image
├── docker-compose.yml   # Full LL-HLS stack (llhls + nginx)
├── tests/
│   ├── __init__.py
│   └── test_nginx_config.py   # 88 unit tests (no Nginx binary needed)
└── README.md            # This file
```

---

## Configuration

All parameters have sensible defaults and can be overridden via environment
variables when using Docker Compose or running `generate_config.py` manually.

| Env variable | Default | Description |
|---|---|---|
| `NGINX_UPSTREAM_HOST` | `127.0.0.1` | Python LL-HLS server host |
| `NGINX_UPSTREAM_PORT` | `8888` | Python LL-HLS server port |
| `NGINX_LISTEN_PORT` | `80` | Nginx listen port |
| `NGINX_SEGMENT_CACHE_AGE` | `31536000` | `.ts` `Cache-Control: max-age` (s) |
| `NGINX_PLAYLIST_TIMEOUT` | `15` | `proxy_read_timeout` for `.m3u8` (s) |
| `NGINX_CORS_ORIGIN` | `*` | `Access-Control-Allow-Origin` |
| `NGINX_WORKER_PROCESSES` | `auto` | Nginx worker processes |
| `NGINX_WORKER_CONNECTIONS` | `1024` | Connections per worker |
| `NGINX_KEEPALIVE_UPSTREAM` | `32` | Upstream keepalive connections |

### Key design decisions

**`proxy_read_timeout 15s` for playlists** — The Python LL-HLS server holds
playlist requests open (blocking reload) for up to 10 s while waiting for a
new segment part.  Nginx's timeout must exceed this to prevent premature 504
responses.

**`proxy_buffering off` for playlists** — Ensures Nginx forwards the playlist
bytes to the client as soon as the Python server finishes writing them, without
accumulating them in an internal buffer.

**`Cache-Control: max-age=31536000, public, immutable` for `.ts`** — Segment
files are write-once; once written their content never changes.  The `immutable`
extension tells browsers not to revalidate during the max-age window even on
explicit reload.

**`proxy_hide_header Cache-Control`** — The Python server already sets
`Cache-Control` on its responses.  We hide it and apply Nginx-level headers so
that all caching rules are controlled in one place.

---

## Running locally (Docker Compose)

```bash
# From the repo root
cd edge/nginx

# Start both the Python LL-HLS server and Nginx
docker compose up

# Test
curl http://localhost:8080/health          # → "OK"
curl http://localhost:8080/index.m3u8      # → master playlist
curl http://localhost:8080/stream.m3u8     # → media playlist
```

The Python LL-HLS server is not exposed on the host — only Nginx is.

---

## Running Nginx standalone

When the Python LL-HLS server is already running on `localhost:8888`:

```bash
# Docker
docker build -t wrack-nginx-hls .
docker run --rm -p 8080:80 --network host wrack-nginx-hls

# Or native Nginx
nginx -c $(pwd)/nginx.conf
```

---

## Regenerating `nginx.conf`

The committed `nginx.conf` is generated from `generate_config.py` with default
parameters.  To regenerate after changing the template:

```bash
cd edge/nginx
python3 generate_config.py -o nginx.conf
```

To generate with custom parameters:

```bash
NGINX_UPSTREAM_PORT=9000 NGINX_CORS_ORIGIN="https://myapp.example.com" \
    python3 generate_config.py -o nginx.conf
```

---

## Running tests

```bash
cd edge/nginx
python3 -m pytest tests/ -v
```

The 88 unit tests are purely in-process — no Nginx binary or running server
required.  They cover:

- `NginxConfigParams` default values
- Port range validation (1–65535)
- Proxy-loop guard (same port on loopback)
- Cache max-age / playlist timeout validation
- Worker process / connection validation
- CORS origin validation
- Multi-field error aggregation
- `load_from_env()` environment variable parsing
- `render()` output: upstream block, MIME types, CORS headers, caching
  directives, proxy settings, health endpoint, server tokens
- Static `nginx.conf` integrity (must match rendered output of default params)
