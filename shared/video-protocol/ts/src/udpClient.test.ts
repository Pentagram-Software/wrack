/**
 * Unit tests for UDPVideoClient reconnect logic and computeBackoffDelay.
 *
 * Run via: node --test dist/udpClient.test.js
 * (build first: npm run build)
 */

import assert from "assert/strict";
import { EventEmitter } from "events";
import { test, describe } from "node:test";
import * as dgram from "dgram";
import {
  UDPVideoClient,
  ClientState,
  ReconnectOptions,
  computeBackoffDelay,
} from "./udpClient";
import {
  MSG_REGISTER_CLIENT,
  MSG_REGISTERED,
  MSG_DISCONNECT,
} from "./protocol";

// ---------------------------------------------------------------------------
// computeBackoffDelay unit tests
// ---------------------------------------------------------------------------

describe("computeBackoffDelay", () => {
  test("returns initialMs for attempt 0", () => {
    assert.equal(computeBackoffDelay(0, 1000, 30000, 2), 1000);
  });

  test("doubles on each attempt with factor 2", () => {
    assert.equal(computeBackoffDelay(1, 1000, 30000, 2), 2000);
    assert.equal(computeBackoffDelay(2, 1000, 30000, 2), 4000);
    assert.equal(computeBackoffDelay(3, 1000, 30000, 2), 8000);
  });

  test("never exceeds maxMs", () => {
    assert.equal(computeBackoffDelay(10, 1000, 5000, 2), 5000);
    assert.equal(computeBackoffDelay(20, 1000, 5000, 2), 5000);
  });

  test("works with factor 1 (constant delay)", () => {
    assert.equal(computeBackoffDelay(0, 500, 10000, 1), 500);
    assert.equal(computeBackoffDelay(5, 500, 10000, 1), 500);
  });

  test("respects custom backoff factor", () => {
    assert.equal(computeBackoffDelay(2, 100, 100000, 3), 900);
  });
});

// ---------------------------------------------------------------------------
// Mock socket factory helpers
// ---------------------------------------------------------------------------

interface MockSocket extends EventEmitter {
  simulateMessage(msg: Buffer): void;
  simulateError(err: Error): void;
  sentMessages: Array<{ msg: Buffer; port: number; host: string }>;
  closed: boolean;
}

function createMockSocket(): MockSocket {
  const emitter = new EventEmitter() as MockSocket & {
    bind: (cb?: () => void) => void;
    send: (msg: Buffer, port: number, host: string, cb?: (err: Error | null) => void) => void;
    close: () => void;
  };

  emitter.sentMessages = [];
  emitter.closed = false;

  emitter.bind = (cb?: () => void) => {
    setImmediate(() => cb?.());
  };

  emitter.send = (
    msg: Buffer,
    port: number,
    host: string,
    cb?: (err: Error | null) => void
  ) => {
    if (!emitter.closed) {
      emitter.sentMessages.push({ msg, port, host });
    }
    cb?.(null);
  };

  emitter.close = () => {
    emitter.closed = true;
    emitter.emit("close");
  };

  emitter.simulateMessage = (msg: Buffer) => emitter.emit("message", msg);
  emitter.simulateError = (err: Error) => emitter.emit("error", err);

  return emitter;
}

/** Tracks sockets created by the factory across calls. */
function createSocketTracker() {
  const sockets: MockSocket[] = [];
  const factory = () => {
    const s = createMockSocket();
    sockets.push(s);
    return s;
  };
  return { factory, sockets };
}

/** Build a UDPVideoClient wired to mock sockets with an attached no-op error listener. */
function buildClient(opts: ReconnectOptions = {}) {
  const { factory, sockets } = createSocketTracker();
  const client = new UDPVideoClient(
    "192.168.1.1",
    9999,
    opts,
    factory as unknown as () => dgram.Socket
  );
  // Always attach an error listener so emit("error") doesn't throw.
  const errors: Error[] = [];
  client.on("error", (e: Error) => errors.push(e));
  return { client, sockets, errors };
}

/** Drain the current setImmediate queue. */
const tick = () => new Promise<void>((resolve) => setImmediate(resolve));

// ---------------------------------------------------------------------------
// UDPVideoClient state machine tests
// ---------------------------------------------------------------------------

describe("UDPVideoClient — initial state", () => {
  test("starts in idle state", () => {
    const { client } = buildClient();
    assert.equal(client.state, "idle");
  });

  test("reconnectAttempt starts at 0", () => {
    const { client } = buildClient();
    assert.equal(client.reconnectAttempt, 0);
  });
});

describe("UDPVideoClient — connect()", () => {
  test("transitions to connecting after connect()", async () => {
    const { client } = buildClient({ registrationTimeoutMs: 60000 });
    const states: ClientState[] = [];
    client.on("state", (s: ClientState) => states.push(s));
    client.connect();
    await tick();
    assert.ok(states.includes("connecting"), `Expected connecting in ${states}`);
    client.disconnect();
  });

  test("sends REGISTER_CLIENT message on connect()", async () => {
    const { client, sockets } = buildClient({ registrationTimeoutMs: 60000 });
    client.connect();
    await tick();
    const sent = sockets[0]?.sentMessages ?? [];
    const reg = sent.find((m) => m.msg.equals(MSG_REGISTER_CLIENT));
    assert.ok(reg, "REGISTER_CLIENT not found in sent messages");
    client.disconnect();
  });

  test("transitions to registered when REGISTERED received", async () => {
    const { client, sockets } = buildClient({ registrationTimeoutMs: 60000 });
    const states: ClientState[] = [];
    client.on("state", (s: ClientState) => states.push(s));
    client.connect();
    await tick();
    sockets[0]?.simulateMessage(MSG_REGISTERED);
    assert.ok(states.includes("registered"), `Expected registered in ${states}`);
    client.disconnect();
  });

  test("second connect() is a no-op when already connecting", async () => {
    const { client } = buildClient({ registrationTimeoutMs: 60000 });
    const states: ClientState[] = [];
    client.on("state", (s: ClientState) => states.push(s));
    client.connect();
    // State is set synchronously to "connecting" in _openSocket().
    assert.equal(client.state, "connecting");
    client.connect(); // second call should be a no-op
    assert.equal(client.state, "connecting");
    // No new state transitions should have been emitted by the second call.
    assert.equal(states.length, 1, `Expected 1 state change, got ${states}`);
    client.disconnect();
  });
});

describe("UDPVideoClient — disconnect()", () => {
  test("transitions to disconnected after disconnect()", async () => {
    const { client } = buildClient({ registrationTimeoutMs: 60000 });
    const states: ClientState[] = [];
    client.on("state", (s: ClientState) => states.push(s));
    client.connect();
    await tick();
    client.disconnect();
    await tick();
    assert.ok(states.includes("disconnected"), `Expected disconnected in ${states}`);
  });

  test("sends DISCONNECT message on disconnect()", async () => {
    const { client, sockets } = buildClient({ registrationTimeoutMs: 60000 });
    client.connect();
    await tick();
    client.disconnect();
    await tick();
    const sent = sockets[0]?.sentMessages ?? [];
    const dis = sent.find((m) => m.msg.equals(MSG_DISCONNECT));
    assert.ok(dis, "DISCONNECT not found in sent messages");
  });
});

describe("UDPVideoClient — reconnect on socket error", () => {
  test("transitions to reconnecting after socket error", async () => {
    const { client, sockets } = buildClient({
      maxAttempts: 1,
      initialDelayMs: 60000,
      maxDelayMs: 60000,
      registrationTimeoutMs: 60000,
    });
    const states: ClientState[] = [];
    client.on("state", (s: ClientState) => states.push(s));
    client.connect();
    await tick();
    sockets[0]?.simulateError(new Error("network down"));
    await tick();
    assert.ok(states.includes("reconnecting"), `Expected reconnecting in ${states}`);
    client.disconnect();
  });

  test("emits reconnecting event with attempt number 0 on first error", async () => {
    const { client, sockets } = buildClient({
      maxAttempts: 1,
      initialDelayMs: 60000,
      maxDelayMs: 60000,
      registrationTimeoutMs: 60000,
    });
    const reconnectAttempts: number[] = [];
    client.on("reconnecting", (attempt: number) => reconnectAttempts.push(attempt));
    client.connect();
    await tick();
    sockets[0]?.simulateError(new Error("network down"));
    await tick();
    assert.ok(reconnectAttempts.length > 0, "reconnecting event not emitted");
    assert.equal(reconnectAttempts[0], 0);
    client.disconnect();
  });

  test("reconnect attempt counter increments on successive failures", async () => {
    const { client, sockets } = buildClient({
      maxAttempts: 10,
      initialDelayMs: 10,
      maxDelayMs: 100,
      registrationTimeoutMs: 60000,
    });
    client.connect();
    await tick();
    sockets[0]?.simulateError(new Error("fail 1"));
    await tick();
    // Wait for first reconnect timer to fire and create socket 2.
    await new Promise<void>((r) => setTimeout(r, 30));
    assert.ok(sockets.length >= 2, "Expected at least 2 sockets after first reconnect");
    sockets[1]?.simulateError(new Error("fail 2"));
    await tick();
    assert.equal(client.reconnectAttempt, 2);
    client.disconnect();
  });
});

describe("UDPVideoClient — maxAttempts = 0 disables reconnect", () => {
  test("transitions to disconnected immediately on socket error", async () => {
    const { client, sockets } = buildClient({
      maxAttempts: 0,
      registrationTimeoutMs: 60000,
    });
    const states: ClientState[] = [];
    client.on("state", (s: ClientState) => states.push(s));
    client.connect();
    await tick();
    sockets[0]?.simulateError(new Error("fail"));
    await tick();
    assert.ok(states.includes("disconnected"), `Expected disconnected in ${states}`);
    assert.ok(!states.includes("reconnecting"), "Should not have entered reconnecting state");
  });
});

describe("UDPVideoClient — registration timeout triggers reconnect", () => {
  test("emits error and reconnects when REGISTERED not received in time", async () => {
    const { client, errors } = buildClient({
      maxAttempts: 1,
      initialDelayMs: 60000,
      maxDelayMs: 60000,
      registrationTimeoutMs: 20,  // Very short for test speed
    });
    const reconnectAttempts: number[] = [];
    client.on("reconnecting", (a: number) => reconnectAttempts.push(a));
    client.connect();
    // Wait longer than registrationTimeoutMs but less than reconnect delay.
    await new Promise<void>((r) => setTimeout(r, 100));
    assert.ok(errors.length > 0, "Expected registration timeout error");
    assert.ok(reconnectAttempts.length > 0, "Expected reconnect after timeout");
    client.disconnect();
  });
});

describe("UDPVideoClient — reconnect resets attempt counter on success", () => {
  test("reconnectAttempt resets to 0 after successful REGISTERED", async () => {
    const { client, sockets } = buildClient({
      maxAttempts: 10,
      initialDelayMs: 10,
      maxDelayMs: 100,
      registrationTimeoutMs: 60000,
    });
    client.connect();
    await tick();
    // Trigger reconnect.
    sockets[0]?.simulateError(new Error("fail"));
    await tick();
    // Wait for reconnect timer (10ms) then simulate REGISTERED on new socket.
    await new Promise<void>((r) => setTimeout(r, 30));
    const latest = sockets[sockets.length - 1];
    assert.ok(latest, "Expected a reconnect socket to have been created");
    latest?.simulateMessage(MSG_REGISTERED);
    await tick();
    assert.equal(client.reconnectAttempt, 0, "attempt counter should reset");
    assert.equal(client.state, "registered");
    client.disconnect();
  });
});
