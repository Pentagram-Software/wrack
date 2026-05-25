import { SignalingServer } from '../src/server.js';
import WebSocket from 'ws';
import http from 'http';

function getPort(server: SignalingServer): number {
  const addr = (server.httpServerInstance.address() as { port: number });
  return addr.port;
}

function wsUrl(port: number): string {
  return `ws://127.0.0.1:${port}`;
}

function httpUrl(port: number, path = '/'): string {
  return `http://127.0.0.1:${port}${path}`;
}

/** Connects a WebSocket and waits for it to open. */
function connect(port: number): Promise<WebSocket> {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl(port));
    ws.once('open', () => resolve(ws));
    ws.once('error', reject);
  });
}

/** Sends a JSON message and waits for the next message from the server. */
function sendAndReceive(ws: WebSocket, msg: object): Promise<object> {
  return new Promise((resolve) => {
    ws.once('message', (raw) => resolve(JSON.parse(raw.toString())));
    ws.send(JSON.stringify(msg));
  });
}

/** Waits for the next message from a WebSocket. */
function nextMessage(ws: WebSocket): Promise<object> {
  return new Promise((resolve) => {
    ws.once('message', (raw) => resolve(JSON.parse(raw.toString())));
  });
}

/** HTTP GET helper. */
function httpGet(url: string): Promise<{ status: number; body: string }> {
  return new Promise((resolve, reject) => {
    http.get(url, (res) => {
      let body = '';
      res.on('data', (chunk) => (body += chunk));
      res.on('end', () => resolve({ status: res.statusCode ?? 0, body }));
    }).on('error', reject);
  });
}

describe('SignalingServer', () => {
  let server: SignalingServer;
  let port: number;

  beforeEach(async () => {
    // Port 0 = OS assigns a free port
    server = new SignalingServer({ port: 0, silent: true });
    await server.listen();
    port = getPort(server);
  });

  afterEach(async () => {
    await server.close();
  });

  describe('HTTP health endpoint', () => {
    it('returns 200 with JSON status on /health', async () => {
      const { status, body } = await httpGet(httpUrl(port, '/health'));
      expect(status).toBe(200);
      const json = JSON.parse(body);
      expect(json.status).toBe('ok');
      expect(typeof json.rooms).toBe('number');
      expect(typeof json.peers).toBe('number');
    });

    it('returns 404 for unknown paths', async () => {
      const { status } = await httpGet(httpUrl(port, '/unknown'));
      expect(status).toBe(404);
    });
  });

  describe('join', () => {
    it('receives a joined response with hasPeer=false when alone', async () => {
      const ws = await connect(port);
      const response = await sendAndReceive(ws, {
        type: 'join',
        room: 'cam-1',
        role: 'publisher',
      });
      expect(response).toMatchObject({ type: 'joined', room: 'cam-1', role: 'publisher', hasPeer: false });
      ws.close();
    });

    it('receives hasPeer=true when the opposite peer is already in the room', async () => {
      const pub = await connect(port);
      await sendAndReceive(pub, { type: 'join', room: 'cam-1', role: 'publisher' });

      const sub = await connect(port);
      const response = await sendAndReceive(sub, { type: 'join', room: 'cam-1', role: 'subscriber' });
      expect(response).toMatchObject({ type: 'joined', hasPeer: true });

      pub.close();
      sub.close();
    });

    it('notifies the existing peer when a new one joins', async () => {
      const pub = await connect(port);
      await sendAndReceive(pub, { type: 'join', room: 'cam-1', role: 'publisher' });

      const peerJoinedPromise = nextMessage(pub);

      const sub = await connect(port);
      sub.send(JSON.stringify({ type: 'join', room: 'cam-1', role: 'subscriber' }));

      const notification = await peerJoinedPromise;
      expect(notification).toMatchObject({ type: 'peer-joined', role: 'subscriber' });

      pub.close();
      sub.close();
    });

    it('returns an error when joining a full publisher slot', async () => {
      const pub1 = await connect(port);
      await sendAndReceive(pub1, { type: 'join', room: 'cam-1', role: 'publisher' });

      const pub2 = await connect(port);
      const response = await sendAndReceive(pub2, { type: 'join', room: 'cam-1', role: 'publisher' });
      expect(response).toMatchObject({ type: 'error' });

      pub1.close();
      pub2.close();
    });
  });

  describe('allowedRooms restriction', () => {
    it('rejects join for a room not in the allow list', async () => {
      const restrictedServer = new SignalingServer({
        port: 0,
        silent: true,
        allowedRooms: ['cam-1'],
      });
      await restrictedServer.listen();
      const restrictedPort = getPort(restrictedServer);

      const ws = await connect(restrictedPort);
      const response = await sendAndReceive(ws, {
        type: 'join',
        room: 'cam-99',
        role: 'publisher',
      });
      expect(response).toMatchObject({ type: 'error' });

      ws.close();
      await restrictedServer.close();
    });

    it('allows join for a room in the allow list', async () => {
      const restrictedServer = new SignalingServer({
        port: 0,
        silent: true,
        allowedRooms: ['cam-1'],
      });
      await restrictedServer.listen();
      const restrictedPort = getPort(restrictedServer);

      const ws = await connect(restrictedPort);
      const response = await sendAndReceive(ws, {
        type: 'join',
        room: 'cam-1',
        role: 'publisher',
      });
      expect(response).toMatchObject({ type: 'joined' });

      ws.close();
      await restrictedServer.close();
    });
  });

  describe('offer / answer relay', () => {
    async function setupRoom() {
      const pub = await connect(port);
      const sub = await connect(port);

      await sendAndReceive(pub, { type: 'join', room: 'room-a', role: 'publisher' });

      // When subscriber joins, publisher gets a peer-joined notification — consume it
      const subJoinedPromise = sendAndReceive(sub, { type: 'join', room: 'room-a', role: 'subscriber' });
      await nextMessage(pub); // peer-joined on publisher side
      await subJoinedPromise;

      return { pub, sub };
    }

    it('relays offer from publisher to subscriber', async () => {
      const { pub, sub } = await setupRoom();

      const offerPromise = nextMessage(sub);
      pub.send(JSON.stringify({
        type: 'offer',
        room: 'room-a',
        sdp: { type: 'offer', sdp: 'v=0' },
      }));

      const relayed = await offerPromise;
      expect(relayed).toMatchObject({ type: 'offer', sdp: { type: 'offer', sdp: 'v=0' } });

      pub.close();
      sub.close();
    });

    it('relays answer from subscriber to publisher', async () => {
      const { pub, sub } = await setupRoom();

      const answerPromise = nextMessage(pub);
      sub.send(JSON.stringify({
        type: 'answer',
        room: 'room-a',
        sdp: { type: 'answer', sdp: 'v=0' },
      }));

      const relayed = await answerPromise;
      expect(relayed).toMatchObject({ type: 'answer', sdp: { type: 'answer', sdp: 'v=0' } });

      pub.close();
      sub.close();
    });

    it('rejects offer sent by subscriber', async () => {
      const { pub, sub } = await setupRoom();

      const errorPromise = nextMessage(sub);
      sub.send(JSON.stringify({
        type: 'offer',
        room: 'room-a',
        sdp: { type: 'offer', sdp: 'v=0' },
      }));

      const error = await errorPromise;
      expect(error).toMatchObject({ type: 'error' });

      pub.close();
      sub.close();
    });

    it('rejects answer sent by publisher', async () => {
      const { pub, sub } = await setupRoom();

      const errorPromise = nextMessage(pub);
      pub.send(JSON.stringify({
        type: 'answer',
        room: 'room-a',
        sdp: { type: 'answer', sdp: 'v=0' },
      }));

      const error = await errorPromise;
      expect(error).toMatchObject({ type: 'error' });

      pub.close();
      sub.close();
    });
  });

  describe('ICE candidate relay', () => {
    it('relays ICE candidate from publisher to subscriber', async () => {
      const pub = await connect(port);
      const sub = await connect(port);

      await sendAndReceive(pub, { type: 'join', room: 'room-b', role: 'publisher' });
      const subJoined = sendAndReceive(sub, { type: 'join', room: 'room-b', role: 'subscriber' });
      await nextMessage(pub); // peer-joined
      await subJoined;

      const candidatePromise = nextMessage(sub);
      pub.send(JSON.stringify({
        type: 'ice-candidate',
        room: 'room-b',
        candidate: { candidate: 'a=candidate:1 1 udp 2130706431 192.168.1.1 54400 typ host', sdpMid: '0' },
      }));

      const relayed = await candidatePromise;
      expect(relayed).toMatchObject({ type: 'ice-candidate' });

      pub.close();
      sub.close();
    });
  });

  describe('peer-left notification', () => {
    it('notifies subscriber when publisher disconnects', async () => {
      const pub = await connect(port);
      const sub = await connect(port);

      await sendAndReceive(pub, { type: 'join', room: 'room-c', role: 'publisher' });
      const subJoined = sendAndReceive(sub, { type: 'join', room: 'room-c', role: 'subscriber' });
      await nextMessage(pub); // peer-joined
      await subJoined;

      const peerLeftPromise = nextMessage(sub);
      pub.close();

      const notification = await peerLeftPromise;
      expect(notification).toMatchObject({ type: 'peer-left', role: 'publisher' });

      sub.close();
    });

    it('notifies publisher when subscriber disconnects', async () => {
      const pub = await connect(port);
      const sub = await connect(port);

      await sendAndReceive(pub, { type: 'join', room: 'room-d', role: 'publisher' });
      const subJoined = sendAndReceive(sub, { type: 'join', room: 'room-d', role: 'subscriber' });
      await nextMessage(pub); // peer-joined
      await subJoined;

      const peerLeftPromise = nextMessage(pub);
      sub.close();

      const notification = await peerLeftPromise;
      expect(notification).toMatchObject({ type: 'peer-left', role: 'subscriber' });

      pub.close();
    });
  });

  describe('invalid messages', () => {
    it('returns an error for malformed JSON', async () => {
      const ws = await connect(port);
      const response = await new Promise<object>((resolve) => {
        ws.once('message', (raw) => resolve(JSON.parse(raw.toString())));
        ws.send('not valid json');
      });
      expect(response).toMatchObject({ type: 'error', message: expect.stringContaining('Invalid JSON') });
      ws.close();
    });
  });

  describe('room management in RoomManager', () => {
    it('rooms are cleaned up after all peers leave', async () => {
      const pub = await connect(port);
      await sendAndReceive(pub, { type: 'join', room: 'cleanup-test', role: 'publisher' });
      expect(server.roomManager.roomCount).toBe(1);

      await new Promise<void>((resolve) => {
        pub.once('close', resolve);
        pub.close();
      });

      // Give the server a tick to process the close event
      await new Promise((r) => setTimeout(r, 50));
      expect(server.roomManager.roomCount).toBe(0);
    });
  });
});
