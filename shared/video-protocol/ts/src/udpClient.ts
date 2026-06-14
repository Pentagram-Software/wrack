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

export type ClientState =
  | "idle"
  | "connecting"
  | "registered"
  | "reconnecting"
  | "disconnected";

/**
 * Options that govern automatic reconnect behaviour.
 *
 * All delays are in milliseconds.
 */
export interface ReconnectOptions {
  /** Maximum number of reconnect attempts before giving up (default: unlimited). */
  maxAttempts?: number;
  /** Delay before the first reconnect attempt (default: 1 000 ms). */
  initialDelayMs?: number;
  /** Upper bound on the computed delay (default: 30 000 ms). */
  maxDelayMs?: number;
  /** Exponential backoff multiplier applied to each successive delay (default: 2). */
  backoffFactor?: number;
  /**
   * How long to wait for a REGISTERED acknowledgement after sending
   * REGISTER_CLIENT before treating the attempt as failed (default: 10 000 ms).
   */
  registrationTimeoutMs?: number;
}

/**
 * Compute the reconnect delay for a given attempt number.
 *
 * @param attempt        Zero-based attempt index.
 * @param initialMs      Delay for attempt 0.
 * @param maxMs          Hard ceiling on the returned value.
 * @param factor         Multiplicative backoff factor.
 */
export function computeBackoffDelay(
  attempt: number,
  initialMs: number,
  maxMs: number,
  factor: number
): number {
  const delay = initialMs * Math.pow(factor, attempt);
  return Math.min(delay, maxMs);
}

/**
 * Node.js UDP client for the wrack video streaming protocol.
 *
 * Emits:
 *   "frame"        (data: Buffer)       — complete H.264 (or JPEG/pickle) frame payload
 *   "state"        (state: ClientState)
 *   "error"        (err: Error)
 *   "reconnecting" (attempt: number)    — fired before each reconnect attempt
 *
 * NOTE: This is a Node.js-only module. Web browsers cannot use raw UDP.
 * Use this in a server-side WebSocket bridge to forward frames to browser clients.
 *
 * Example (auto-reconnect enabled):
 * ```ts
 * const client = new UDPVideoClient("192.168.1.42", SERVER_PORT, {
 *   maxAttempts: 10,
 *   initialDelayMs: 1000,
 *   maxDelayMs: 30000,
 * });
 * client.on("frame", (data) => ws.send(data));
 * client.on("reconnecting", (attempt) => console.log("Reconnecting, attempt", attempt));
 * client.connect();
 * ```
 *
 * To disable automatic reconnect, pass `{ maxAttempts: 0 }`.
 */
export class UDPVideoClient extends EventEmitter {
  private socket: dgram.Socket | null = null;
  private keepaliveTimer: NodeJS.Timeout | null = null;
  private registrationTimer: NodeJS.Timeout | null = null;
  private reconnectTimer: NodeJS.Timeout | null = null;
  private assembler = new FrameAssembler();
  private _state: ClientState = "idle";

  private readonly _reconnect: Required<ReconnectOptions>;
  private _reconnectAttempt = 0;
  private _intentionalDisconnect = false;

  /** Injectable socket factory — override in tests. */
  private readonly _socketFactory: () => dgram.Socket;

  constructor(
    private readonly serverHost: string,
    private readonly serverPort: number = SERVER_PORT,
    reconnectOptions: ReconnectOptions = {},
    socketFactory?: () => dgram.Socket
  ) {
    super();
    this._reconnect = {
      maxAttempts: reconnectOptions.maxAttempts ?? Infinity,
      initialDelayMs: reconnectOptions.initialDelayMs ?? 1_000,
      maxDelayMs: reconnectOptions.maxDelayMs ?? 30_000,
      backoffFactor: reconnectOptions.backoffFactor ?? 2,
      registrationTimeoutMs: reconnectOptions.registrationTimeoutMs ?? 10_000,
    };
    this._socketFactory = socketFactory ?? (() => dgram.createSocket("udp4"));
  }

  get state(): ClientState {
    return this._state;
  }

  /** Current zero-based reconnect attempt counter. */
  get reconnectAttempt(): number {
    return this._reconnectAttempt;
  }

  connect(): void {
    if (this._state !== "idle" && this._state !== "disconnected") return;
    this._intentionalDisconnect = false;
    this._openSocket();
  }

  disconnect(): void {
    this._intentionalDisconnect = true;
    this._cancelReconnect();
    if (this.socket) {
      this.socket.send(MSG_DISCONNECT, this.serverPort, this.serverHost, () => {
        this._cleanup();
      });
    } else {
      this._cleanup();
    }
  }

  // MARK: - Private

  private _openSocket(): void {
    const socket = this._socketFactory();
    this.socket = socket;

    socket.on("error", (err) => {
      // Only emit if there are listeners; EventEmitter throws on 'error' with no listeners.
      if (this.listenerCount("error") > 0) {
        this.emit("error", err);
      }
      this._handleConnectionLost();
    });

    socket.on("message", (msg) => this._handleMessage(msg));

    // Set state synchronously before async bind so the guard in connect() blocks
    // any concurrent connect() call from opening a second socket.
    this.setState("connecting");
    socket.bind(() => {
      socket.send(MSG_REGISTER_CLIENT, this.serverPort, this.serverHost);
      this._startRegistrationTimeout();
    });
  }

  private _handleMessage(msg: Buffer): void {
    if (msg.equals(MSG_REGISTERED)) {
      this._cancelRegistrationTimeout();
      this._reconnectAttempt = 0;
      this.setState("registered");
      this._startKeepalive();
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

  private _startKeepalive(): void {
    this.keepaliveTimer = setInterval(() => {
      this.socket?.send(MSG_KEEPALIVE, this.serverPort, this.serverHost);
    }, KEEPALIVE_INTERVAL_MS);
  }

  private _startRegistrationTimeout(): void {
    this.registrationTimer = setTimeout(() => {
      this.registrationTimer = null;
      if (this._state === "connecting") {
        if (this.listenerCount("error") > 0) {
          this.emit("error", new Error("Registration timed out — server did not respond"));
        }
        this._handleConnectionLost();
      }
    }, this._reconnect.registrationTimeoutMs);
  }

  private _cancelRegistrationTimeout(): void {
    if (this.registrationTimer) {
      clearTimeout(this.registrationTimer);
      this.registrationTimer = null;
    }
  }

  private _handleConnectionLost(): void {
    this._cleanup(/* keepState */ true);
    if (this._intentionalDisconnect) {
      this.setState("disconnected");
      return;
    }
    this._scheduleReconnect();
  }

  private _scheduleReconnect(): void {
    if (this._reconnect.maxAttempts !== Infinity &&
        this._reconnectAttempt >= this._reconnect.maxAttempts) {
      this.setState("disconnected");
      return;
    }

    const delay = computeBackoffDelay(
      this._reconnectAttempt,
      this._reconnect.initialDelayMs,
      this._reconnect.maxDelayMs,
      this._reconnect.backoffFactor
    );

    this.setState("reconnecting");
    this.emit("reconnecting", this._reconnectAttempt);
    this._reconnectAttempt += 1;

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (!this._intentionalDisconnect) {
        this._openSocket();
      }
    }, delay);
  }

  private _cancelReconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this._cancelRegistrationTimeout();
  }

  private setState(state: ClientState): void {
    this._state = state;
    this.emit("state", state);
  }

  private _cleanup(keepState = false): void {
    if (this.keepaliveTimer) {
      clearInterval(this.keepaliveTimer);
      this.keepaliveTimer = null;
    }
    this._cancelRegistrationTimeout();
    this.socket?.close();
    this.socket = null;
    if (!keepState) {
      this.setState("disconnected");
    }
  }
}
