import http from 'http';
import { WebSocket, WebSocketServer } from 'ws';
import { v4 as uuidv4 } from 'uuid';
import { RoomManager } from './room-manager.js';
import {
  ClientMessage,
  ServerMessage,
  WS_OPEN,
} from './types.js';
import { Room } from './room.js';

export interface SignalingServerOptions {
  port?: number;
  /** If provided, only rooms whose ids are listed here are allowed. Empty array = allow all. */
  allowedRooms?: string[];
  /** Suppress console output (useful in tests). */
  silent?: boolean;
}

/**
 * Minimal WebRTC signaling server.
 *
 * Each WebSocket client must first send a `join` message to enter a room.
 * The server then relays `offer`, `answer`, and `ice-candidate` messages
 * between the publisher (Pi camera) and subscriber (browser).
 */
export class SignalingServer {
  private httpServer: http.Server;
  private wss: WebSocketServer;
  private manager: RoomManager;
  private options: Required<SignalingServerOptions>;

  constructor(options: SignalingServerOptions = {}) {
    this.options = {
      port: options.port ?? 3001,
      allowedRooms: options.allowedRooms ?? [],
      silent: options.silent ?? false,
    };

    this.manager = new RoomManager();
    this.httpServer = http.createServer(this.handleHttp.bind(this));
    this.wss = new WebSocketServer({ server: this.httpServer });
    this.wss.on('connection', (ws) => this.handleConnection(ws));
  }

  private log(...args: unknown[]): void {
    if (!this.options.silent) {
      console.log('[signaling]', ...args);
    }
  }

  /** Simple HTTP handler that serves health status and room info. */
  private handleHttp(req: http.IncomingMessage, res: http.ServerResponse): void {
    if (req.url === '/health') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(
        JSON.stringify({
          status: 'ok',
          rooms: this.manager.roomCount,
          peers: this.manager.peerCount,
        }),
      );
      return;
    }
    res.writeHead(404);
    res.end('Not found');
  }

  private handleConnection(ws: WebSocket): void {
    const peerId = uuidv4();
    this.log(`peer connected: ${peerId}`);

    ws.on('message', (raw) => {
      let msg: ClientMessage;
      try {
        msg = JSON.parse(raw.toString()) as ClientMessage;
      } catch {
        this.send(ws, { type: 'error', message: 'Invalid JSON' });
        return;
      }
      this.handleMessage(peerId, ws, msg);
    });

    ws.on('close', () => {
      this.log(`peer disconnected: ${peerId}`);
      this.handleLeave(peerId);
    });

    ws.on('error', (err) => {
      this.log(`error from peer ${peerId}:`, err.message);
    });
  }

  private handleMessage(peerId: string, ws: WebSocket, msg: ClientMessage): void {
    switch (msg.type) {
      case 'join':
        this.handleJoin(peerId, ws, msg.room, msg.role);
        break;
      case 'leave':
        this.handleLeave(peerId);
        break;
      case 'offer':
        this.handleOffer(peerId, msg.room, msg.sdp);
        break;
      case 'answer':
        this.handleAnswer(peerId, msg.room, msg.sdp);
        break;
      case 'ice-candidate':
        this.handleIceCandidate(peerId, msg.room, msg.candidate);
        break;
      default:
        this.send(ws, { type: 'error', message: 'Unknown message type' });
    }
  }

  private handleJoin(
    peerId: string,
    ws: WebSocket,
    roomId: string,
    role: 'publisher' | 'subscriber',
  ): void {
    if (
      this.options.allowedRooms.length > 0 &&
      !this.options.allowedRooms.includes(roomId)
    ) {
      this.send(ws, { type: 'error', message: `Room '${roomId}' is not allowed` });
      return;
    }

    const { room, error } = this.manager.join(roomId, { id: peerId, role, socket: ws });
    if (error || !room) {
      this.send(ws, { type: 'error', message: error ?? 'Join failed' });
      return;
    }

    const hasPeer =
      role === 'publisher' ? room.hasSubscriber : room.hasPublisher;

    this.send(ws, { type: 'joined', room: roomId, role, hasPeer });
    this.log(`peer ${peerId} joined room '${roomId}' as ${role}`);

    // Notify the opposite peer that a new participant has arrived
    room.relay(peerId, {
      type: 'peer-joined',
      room: roomId,
      role,
    });
  }

  private handleLeave(peerId: string): void {
    const { room, role } = this.manager.leave(peerId);
    if (!room || !role) return;

    this.log(`peer ${peerId} left room '${room.id}'`);

    // Notify the remaining peer
    const oppositeRole = role === 'publisher' ? 'subscriber' : 'publisher';
    const remaining =
      oppositeRole === 'publisher' ? room.publisherPeer : room.subscriberPeer;

    if (remaining && remaining.socket.readyState === WS_OPEN) {
      remaining.socket.send(
        JSON.stringify({ type: 'peer-left', room: room.id, role } as ServerMessage),
      );
    }
  }

  private handleOffer(
    peerId: string,
    roomId: string,
    sdp: RTCSessionDescriptionInit,
  ): void {
    const room = this.manager.getRoomForPeer(peerId);
    if (!this.assertRoom(peerId, room, roomId)) return;

    const validationError = room!.validateOffer(peerId);
    if (validationError) {
      this.sendToPeer(peerId, room!, { type: 'error', message: validationError });
      return;
    }

    room!.relay(peerId, Room.buildOffer(sdp));
    this.log(`offer relayed in room '${roomId}'`);
  }

  private handleAnswer(
    peerId: string,
    roomId: string,
    sdp: RTCSessionDescriptionInit,
  ): void {
    const room = this.manager.getRoomForPeer(peerId);
    if (!this.assertRoom(peerId, room, roomId)) return;

    const validationError = room!.validateAnswer(peerId);
    if (validationError) {
      this.sendToPeer(peerId, room!, { type: 'error', message: validationError });
      return;
    }

    room!.relay(peerId, Room.buildAnswer(sdp));
    this.log(`answer relayed in room '${roomId}'`);
  }

  private handleIceCandidate(
    peerId: string,
    roomId: string,
    candidate: RTCIceCandidateInit,
  ): void {
    const room = this.manager.getRoomForPeer(peerId);
    if (!this.assertRoom(peerId, room, roomId)) return;

    room!.relay(peerId, Room.buildIceCandidate(candidate));
  }

  private assertRoom(peerId: string, room: Room | null, roomId: string): boolean {
    if (!room) {
      // Peer is not in a room — we need their socket to send an error, but
      // we no longer have it here. Log and return false.
      this.log(`peer ${peerId} sent message for room '${roomId}' but is not in any room`);
      return false;
    }
    return true;
  }

  private sendToPeer(peerId: string, room: Room, msg: ServerMessage): void {
    room.sendTo(peerId, msg);
  }

  private send(ws: WebSocket, msg: ServerMessage): void {
    if (ws.readyState === WS_OPEN) {
      ws.send(JSON.stringify(msg));
    }
  }

  /** Starts the HTTP + WebSocket server and resolves when listening. */
  listen(): Promise<void> {
    return new Promise((resolve) => {
      this.httpServer.listen(this.options.port, () => {
        this.log(`listening on port ${this.options.port}`);
        resolve();
      });
    });
  }

  /** Closes the server and resolves when all connections are terminated. */
  close(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.wss.close(() => {
        this.httpServer.close((err) => {
          if (err) reject(err);
          else resolve();
        });
      });
    });
  }

  /** Exposed for testing: the underlying RoomManager. */
  get roomManager(): RoomManager {
    return this.manager;
  }

  /** Exposed for testing: the underlying http.Server. */
  get httpServerInstance(): http.Server {
    return this.httpServer;
  }
}
