# ws-bridge

WebSocket bridge that forwards UDP video frames from the Raspberry Pi camera streamer to browser clients in real time.

## Architecture

```
Raspberry Pi                     Bridge server              Browser
  streamer.py  ──UDP 9999──►  ws-bridge/server.js  ──WS──►  CameraView
```

The bridge:
1. Registers with the Pi UDP streamer as a client (port 9999).
2. Reassembles chunked UDP frames into complete video frames using the shared Wrack protocol.
3. Detects the codec — H.264 NAL bitstream or JPEG (raw or pickle-encoded).
4. Forwards each frame to all connected WebSocket clients as a binary message.

## Wire protocol (bridge → browser)

Each binary WebSocket message:

| Byte 0 | Bytes 1+          |
|--------|-------------------|
| `0x01` | H.264 NAL bytes   |
| `0x02` | Raw JPEG bytes    |

Text messages (JSON) may be sent in the future for status/health updates.

## Quick start

```bash
# Install dependencies
npm install

# Start the bridge (default: connects to localhost:9999, serves ws on :8765)
npm start

# Or with custom settings:
PI_HOST=192.168.1.42 PI_PORT=9999 WS_PORT=8765 npm start
```

## Environment variables

| Variable   | Default       | Description                               |
|------------|---------------|-------------------------------------------|
| `PI_HOST`  | `127.0.0.1`   | IP or hostname of the Raspberry Pi        |
| `PI_PORT`  | `9999`        | UDP port of the Pi's video streamer       |
| `WS_PORT`  | `8765`        | TCP port to serve the WebSocket server on |
| `LOG_LEVEL`| `info`        | `debug` \| `info` \| `warn` \| `error`   |

## Health check

```
GET http://localhost:8765/health
```

Returns JSON:
```json
{ "status": "ok", "clients": 1, "frames": 42, "pi": "192.168.1.42:9999" }
```

## Browser client

The companion browser library is at `clients/web/src/lib/videoStream.ts`.
Configure the web app with:

```
NEXT_PUBLIC_WS_BRIDGE_URL=ws://<bridge-host>:8765
```

## Supported frame formats

| Format           | How detected                           | Browser rendering       |
|------------------|----------------------------------------|-------------------------|
| H.264 bitstream  | NAL start code `00 00 00 01`           | WebCodecs `VideoDecoder`|
| Raw JPEG         | JPEG magic `FF D8`                     | `<img>` via blob URL    |
| Pickle JPEG      | Pickle byte `0x80` + embedded JPEG     | `<img>` via blob URL    |

> **Note**: The Raspberry Pi streamer defaults to JPEG+pickle mode. Configure it for H.264 mode for best browser performance (WebCodecs, lower latency).

## Running tests

```bash
npm test
```

## Development

```bash
# Watch mode (restarts on file change)
npm run dev
```
