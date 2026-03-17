import * as dgram from "dgram";
import { EventEmitter } from "events";
import {
  SERVER_PORT,
  KEEPALIVE_INTERVAL_MS,
  MSG_REGISTER_CLIENT,
  MSG_REGISTERED,
  MSG_KEEPALIVE,
  MSG_DISCONNECT,
} from "./protocol";
import { parseFrameStart, parseChunk, FrameAssembler } from "./packets";

export type ClientState = "idle" | "connecting" | "registered" | "disconnected";

/**
 * Node.js UDP client for the wrack video streaming protocol.
 *
 * Emits:
 *   "frame"  (data: Buffer)  — complete H.264 (or JPEG/pickle) frame payload
 *   "state"  (state: ClientState)
 *   "error"  (err: Error)
 *
 * NOTE: This is a Node.js-only module. Web browsers cannot use raw UDP.
 * Use this in a server-side WebSocket bridge to forward frames to browser clients.
 *
 * Example:
 * ```ts
 * const client = new UDPVideoClient("192.168.1.42");
 * client.on("frame", (data) => ws.send(data));
 * client.connect();
 * ```
 */
export class UDPVideoClient extends EventEmitter {
  private socket: dgram.Socket | null = null;
  private keepaliveTimer: NodeJS.Timeout | null = null;
  private assembler = new FrameAssembler();
  private _state: ClientState = "idle";

  constructor(
    private readonly serverHost: string,
    private readonly serverPort: number = SERVER_PORT
  ) {
    super();
  }

  get state(): ClientState {
    return this._state;
  }

  connect(): void {
    if (this._state !== "idle" && this._state !== "disconnected") return;

    const socket = dgram.createSocket("udp4");
    this.socket = socket;

    socket.on("error", (err) => {
      this.emit("error", err);
      this.cleanup();
    });

    socket.on("message", (msg) => this.handleMessage(msg));

    socket.bind(() => {
      this.setState("connecting");
      socket.send(MSG_REGISTER_CLIENT, this.serverPort, this.serverHost);
    });
  }

  disconnect(): void {
    if (this.socket) {
      this.socket.send(MSG_DISCONNECT, this.serverPort, this.serverHost, () => {
        this.cleanup();
      });
    } else {
      this.cleanup();
    }
  }

  // MARK: - Private

  private handleMessage(msg: Buffer): void {
    if (msg.equals(MSG_REGISTERED)) {
      this.setState("registered");
      this.startKeepalive();
      return;
    }

    const frameStart = parseFrameStart(msg);
    if (frameStart) {
      this.assembler.handleFrameStart(frameStart);
      this.assembler.pruneStale();
      return;
    }

    const chunk = parseChunk(msg);
    if (chunk) {
      const frame = this.assembler.handleChunk(chunk);
      if (frame) this.emit("frame", frame);
    }
  }

  private startKeepalive(): void {
    this.keepaliveTimer = setInterval(() => {
      this.socket?.send(MSG_KEEPALIVE, this.serverPort, this.serverHost);
    }, KEEPALIVE_INTERVAL_MS);
  }

  private setState(state: ClientState): void {
    this._state = state;
    this.emit("state", state);
  }

  private cleanup(): void {
    if (this.keepaliveTimer) {
      clearInterval(this.keepaliveTimer);
      this.keepaliveTimer = null;
    }
    this.socket?.close();
    this.socket = null;
    this.setState("disconnected");
  }
}
