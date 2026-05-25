# Wrack — WebRTC Signaling Server

A minimal Node.js/TypeScript WebSocket signaling server that coordinates WebRTC peer connections between the Raspberry Pi camera (publisher) and browser clients (subscribers).

## Architecture

```
Browser (subscriber) ──WS──► Signaling Server ◄──WS── Pi Camera (publisher)
                                    │
                              relays SDP + ICE
                                    │
         Browser ◄─── offer ────────┘
         Browser ──── answer ───────►
         Browser ◄──► ice-candidate ►
```

One publisher (Pi) and one subscriber (browser) share a **room** identified by a string id (e.g. `cam-1`). The server forwards WebRTC signaling messages between them without touching the media.

## Running locally

```bash
cp .env.example .env
npm install
npm run dev          # ts-node dev server
# or build first:
npm run build && npm start
```

The server starts on port **3001** by default (`SIGNALING_PORT` env var overrides this).

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SIGNALING_PORT` | `3001` | TCP port to listen on |
| `ALLOWED_ROOMS` | _(empty)_ | Comma-separated list of permitted room ids. Empty = allow all. |

## WebSocket protocol

All messages are JSON. Connect to `ws://<host>:<port>`.

### Client → Server

#### `join`
```json
{ "type": "join", "room": "cam-1", "role": "publisher" }
{ "type": "join", "room": "cam-1", "role": "subscriber" }
```

#### `leave`
```json
{ "type": "leave", "room": "cam-1" }
```

#### `offer` _(publisher only)_
```json
{ "type": "offer", "room": "cam-1", "sdp": { "type": "offer", "sdp": "..." } }
```

#### `answer` _(subscriber only)_
```json
{ "type": "answer", "room": "cam-1", "sdp": { "type": "answer", "sdp": "..." } }
```

#### `ice-candidate`
```json
{ "type": "ice-candidate", "room": "cam-1", "candidate": { "candidate": "...", "sdpMid": "0" } }
```

### Server → Client

| Message | When |
|---------|------|
| `joined` | Immediate ack after a successful join, includes `hasPeer` flag |
| `peer-joined` | Sent to the existing peer when the opposite side joins |
| `peer-left` | Sent when the opposite peer disconnects |
| `offer` | Relayed offer from publisher to subscriber |
| `answer` | Relayed answer from subscriber to publisher |
| `ice-candidate` | Relayed ICE candidate from either peer |
| `error` | Any validation or protocol error |

## HTTP endpoints

| Path | Method | Description |
|------|--------|-------------|
| `/health` | GET | Returns `{ status, rooms, peers }` — useful for load-balancer probes |

## Testing

```bash
npm test          # run all 65 Jest unit tests
npm run typecheck # TypeScript type check only
```

### Test coverage

| Suite | Tests | What is covered |
|-------|-------|-----------------|
| `room.test.ts` | 28 | `Room` class: peer add/remove, relay, validation, builders |
| `room-manager.test.ts` | 21 | `RoomManager`: join/leave lifecycle, room cleanup, peer lookup |
| `server.test.ts` | 16 | `SignalingServer`: WebSocket protocol, HTTP health, error handling, full offer/answer/ICE relay flow |

## Module structure

```
src/
├── index.ts          Entry point (reads env vars, starts server)
├── server.ts         SignalingServer — HTTP + WebSocket handler
├── room-manager.ts   RoomManager — tracks rooms and peer→room mapping
├── room.ts           Room — per-room peer state and relay logic
└── types.ts          Shared TypeScript types for signaling messages
tests/
├── room.test.ts
├── room-manager.test.ts
└── server.test.ts
```
