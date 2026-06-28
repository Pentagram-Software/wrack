import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  isWebCodecsSupported,
  detectH264FrameType,
  extractH264Codec,
  WebSocketVideoClient,
  VideoStreamState,
} from './videoStream';

// ─── Mock helpers ─────────────────────────────────────────────────────────────

/** Build a minimal JPEG ArrayBuffer (FF D8 ... FF D9). */
function makeJpegBuffer(payloadSize = 20): ArrayBuffer {
  const buf = new ArrayBuffer(payloadSize + 4);
  const view = new Uint8Array(buf);
  view[0] = 0xff; view[1] = 0xd8;                        // SOI
  view[payloadSize + 2] = 0xff; view[payloadSize + 3] = 0xd9; // EOI
  return buf;
}

/** Build a minimal H.264 IDR frame (NAL type 5) with 4-byte start code. */
function makeH264IdrBuffer(extraBytes = 8): ArrayBuffer {
  const buf = new ArrayBuffer(5 + extraBytes);
  const view = new Uint8Array(buf);
  view[0] = 0x00; view[1] = 0x00; view[2] = 0x00; view[3] = 0x01; // 4-byte start code
  view[4] = 0x65; // NAL type 5 = IDR
  return buf;
}

/** Build a H.264 non-IDR (delta) frame (NAL type 1). */
function makeH264DeltaBuffer(extraBytes = 8): ArrayBuffer {
  const buf = new ArrayBuffer(5 + extraBytes);
  const view = new Uint8Array(buf);
  view[0] = 0x00; view[1] = 0x00; view[2] = 0x00; view[3] = 0x01;
  view[4] = 0x41; // NAL type 1 = non-IDR slice
  return buf;
}

/**
 * Build a fake SPS NAL unit containing known profile/constraint/level values.
 * profile=0x42, constraint=0x00, level=0x1e → "avc1.42001e" (baseline L3.0)
 */
function makeSpsBuffer(
  profileIdc = 0x42,
  constraintFlags = 0x00,
  levelIdc = 0x1e
): ArrayBuffer {
  const buf = new ArrayBuffer(4 + 1 + 4); // start code + NAL header + 3 SPS bytes + padding
  const view = new Uint8Array(buf);
  view[0] = 0x00; view[1] = 0x00; view[2] = 0x00; view[3] = 0x01;
  view[4] = 0x67; // NAL type 7 = SPS
  view[5] = profileIdc;
  view[6] = constraintFlags;
  view[7] = levelIdc;
  return buf;
}

/** Build a wire-protocol binary message: [typePrefix, ...payload]. */
function makeWsMessage(typePrefix: number, payload: ArrayBuffer): ArrayBuffer {
  const out = new ArrayBuffer(1 + payload.byteLength);
  new Uint8Array(out)[0] = typePrefix;
  new Uint8Array(out).set(new Uint8Array(payload), 1);
  return out;
}

// ─── Mock WebSocket ───────────────────────────────────────────────────────────

class MockWebSocket {
  binaryType: string = 'arraybuffer';
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  readyState = 0; // CONNECTING
  closeCalled = false;

  constructor(public readonly url: string) {}

  close() {
    this.closeCalled = true;
  }

  /** Test helper: simulate connection open. */
  simulateOpen() {
    this.readyState = 1; // OPEN
    this.onopen?.();
  }

  /** Test helper: simulate connection close. */
  simulateClose() {
    this.readyState = 3; // CLOSED
    this.onclose?.();
  }

  /** Test helper: simulate error. */
  simulateError() {
    this.onerror?.(new Event('error'));
  }

  /** Test helper: simulate incoming binary message. */
  simulateMessage(data: ArrayBuffer) {
    this.onmessage?.(new MessageEvent('message', { data }));
  }
}

// ─── Mock VideoDecoder ────────────────────────────────────────────────────────

class MockVideoDecoder {
  static instances: MockVideoDecoder[] = [];
  state = 'unconfigured';
  configuredCodec: string | null = null;
  decodedChunks: EncodedVideoChunk[] = [];
  output: ((frame: VideoFrame) => void) | null = null;
  error: ((err: DOMException) => void) | null = null;

  constructor(init: { output: (f: VideoFrame) => void; error: (e: DOMException) => void }) {
    this.output = init.output;
    this.error = init.error;
    MockVideoDecoder.instances.push(this);
  }

  configure(config: { codec: string }) {
    this.configuredCodec = config.codec;
    this.state = 'configured';
  }

  decode(chunk: EncodedVideoChunk) {
    this.decodedChunks.push(chunk);
    // Simulate a VideoFrame output for each decoded chunk
    const fakeFrame = {
      displayWidth: 640,
      displayHeight: 480,
      close: vi.fn(),
    } as unknown as VideoFrame;
    this.output?.(fakeFrame);
  }

  async flush() {
    // no-op in mock
  }

  close() {
    this.state = 'closed';
  }
}

// ─── Test setup ───────────────────────────────────────────────────────────────

let wsInstance: MockWebSocket | null = null;

beforeEach(() => {
  wsInstance = null;
  MockVideoDecoder.instances = [];

  vi.stubGlobal('WebSocket', class extends MockWebSocket {
    constructor(url: string) {
      super(url);
      wsInstance = this;
    }
  });

  vi.stubGlobal('VideoDecoder', MockVideoDecoder);
  vi.stubGlobal('EncodedVideoChunk', class {
    constructor(public init: { type: string; timestamp: number; data: ArrayBuffer }) {}
  });
  vi.stubGlobal('performance', { now: vi.fn().mockReturnValue(0) });

  // Mock createObjectURL / revokeObjectURL for JPEG tests
  vi.stubGlobal('URL', {
    createObjectURL: vi.fn().mockReturnValue('blob:mock-url'),
    revokeObjectURL: vi.fn(),
  });

  // Mock Image for JPEG decoding tests
  vi.stubGlobal('Image', class {
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    naturalWidth = 640;
    naturalHeight = 480;
    set src(_url: string) {
      // Simulate async image load
      Promise.resolve().then(() => this.onload?.());
    }
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// ─── isWebCodecsSupported ────────────────────────────────────────────────────

describe('isWebCodecsSupported', () => {
  it('returns true when VideoDecoder is available', () => {
    expect(isWebCodecsSupported()).toBe(true);
  });

  it('returns false when VideoDecoder is not defined', () => {
    vi.stubGlobal('VideoDecoder', undefined);
    expect(isWebCodecsSupported()).toBe(false);
  });
});

// ─── detectH264FrameType ─────────────────────────────────────────────────────

describe('detectH264FrameType', () => {
  it('detects IDR (keyframe) with 4-byte start code', () => {
    const data = new Uint8Array(makeH264IdrBuffer());
    expect(detectH264FrameType(data)).toBe('key');
  });

  it('detects IDR (keyframe) with 3-byte start code', () => {
    const buf = new Uint8Array(5);
    buf[0] = 0x00; buf[1] = 0x00; buf[2] = 0x01;
    buf[3] = 0x65; // NAL type 5 = IDR
    expect(detectH264FrameType(buf)).toBe('key');
  });

  it('detects non-IDR (delta frame)', () => {
    const data = new Uint8Array(makeH264DeltaBuffer());
    expect(detectH264FrameType(data)).toBe('delta');
  });

  it('skips SPS/PPS NAL units and keeps scanning', () => {
    // SPS (type 7) followed by IDR (type 5)
    const sps = new Uint8Array([0x00, 0x00, 0x00, 0x01, 0x67, 0x42, 0x00, 0x1e]);
    const idr = new Uint8Array([0x00, 0x00, 0x00, 0x01, 0x65, 0xb8]);
    const combined = new Uint8Array(sps.length + idr.length);
    combined.set(sps, 0);
    combined.set(idr, sps.length);
    expect(detectH264FrameType(combined)).toBe('key');
  });

  it('returns delta for data with no clear IDR', () => {
    const data = new Uint8Array([0x00, 0x00, 0x00, 0x01, 0x41, 0x00]);
    expect(detectH264FrameType(data)).toBe('delta');
  });
});

// ─── extractH264Codec ────────────────────────────────────────────────────────

describe('extractH264Codec', () => {
  it('extracts codec string from a SPS NAL unit (4-byte start code)', () => {
    const data = new Uint8Array(makeSpsBuffer(0x42, 0x00, 0x1e));
    expect(extractH264Codec(data)).toBe('avc1.42001e');
  });

  it('falls back to baseline L3.0 when no SPS is present', () => {
    const data = new Uint8Array(makeH264IdrBuffer());
    expect(extractH264Codec(data)).toBe('avc1.42001e');
  });

  it('extracts high profile codec string', () => {
    // profile=0x64 (High), constraint=0x00, level=0x1f (L3.1)
    const data = new Uint8Array(makeSpsBuffer(0x64, 0x00, 0x1f));
    expect(extractH264Codec(data)).toBe('avc1.64001f');
  });

  it('pads single-digit hex values with leading zeros', () => {
    // profile=0x42, constraint=0x00, level=0x0a
    const data = new Uint8Array(makeSpsBuffer(0x42, 0x00, 0x0a));
    expect(extractH264Codec(data)).toBe('avc1.42000a');
  });
});

// ─── WebSocketVideoClient — state machine ────────────────────────────────────

describe('WebSocketVideoClient — state machine', () => {
  it('starts in idle state', () => {
    const client = new WebSocketVideoClient({ url: 'ws://localhost:8765' });
    expect(client.getState()).toBe('idle');
  });

  it('transitions to connecting on connect()', () => {
    const states: VideoStreamState[] = [];
    const client = new WebSocketVideoClient({
      url: 'ws://localhost:8765',
      onStateChange: (s) => states.push(s),
    });
    client.connect();
    expect(client.getState()).toBe('connecting');
    expect(states).toContain('connecting');
  });

  it('creates WebSocket with the configured URL', () => {
    const client = new WebSocketVideoClient({ url: 'ws://192.168.1.42:8765' });
    client.connect();
    expect(wsInstance?.url).toBe('ws://192.168.1.42:8765');
  });

  it('transitions to connected on WS open', () => {
    const states: VideoStreamState[] = [];
    const client = new WebSocketVideoClient({
      url: 'ws://localhost:8765',
      onStateChange: (s) => states.push(s),
    });
    client.connect();
    wsInstance!.simulateOpen();
    expect(client.getState()).toBe('connected');
    expect(states).toEqual(['connecting', 'connected']);
  });

  it('transitions to disconnected on WS close', () => {
    const client = new WebSocketVideoClient({ url: 'ws://localhost:8765' });
    client.connect();
    wsInstance!.simulateOpen();
    wsInstance!.simulateClose();
    expect(client.getState()).toBe('disconnected');
  });

  it('transitions to error on WS error event', () => {
    const client = new WebSocketVideoClient({ url: 'ws://localhost:8765' });
    client.connect();
    wsInstance!.simulateError();
    expect(client.getState()).toBe('error');
  });

  it('calls onError when WS error occurs', () => {
    const onError = vi.fn();
    const client = new WebSocketVideoClient({
      url: 'ws://localhost:8765',
      onError,
    });
    client.connect();
    wsInstance!.simulateError();
    expect(onError).toHaveBeenCalledWith(expect.any(Error));
  });

  it('does not reconnect if already connecting', () => {
    const client = new WebSocketVideoClient({ url: 'ws://localhost:8765' });
    client.connect();
    const firstWs = wsInstance;
    client.connect(); // second call — should no-op
    expect(wsInstance).toBe(firstWs);
  });

  it('disconnect() closes the WebSocket and transitions to disconnected', () => {
    const states: VideoStreamState[] = [];
    const client = new WebSocketVideoClient({
      url: 'ws://localhost:8765',
      onStateChange: (s) => states.push(s),
    });
    client.connect();
    wsInstance!.simulateOpen();
    client.disconnect();
    expect(wsInstance!.closeCalled).toBe(true);
    expect(client.getState()).toBe('disconnected');
  });

  it('can reconnect after disconnecting', () => {
    const client = new WebSocketVideoClient({ url: 'ws://localhost:8765' });
    client.connect();
    wsInstance!.simulateOpen();
    client.disconnect();
    // Reset mock WebSocket instance
    wsInstance = null;
    client.connect();
    expect(wsInstance).not.toBeNull();
    expect(client.getState()).toBe('connecting');
  });

  it('does not call onStateChange if state is unchanged', () => {
    const onStateChange = vi.fn();
    const client = new WebSocketVideoClient({
      url: 'ws://localhost:8765',
      onStateChange,
    });
    client.connect();
    onStateChange.mockClear();
    // Simulate a second open — state is already 'connecting'→'connected', not re-entering connecting
    wsInstance!.simulateOpen();
    wsInstance!.simulateOpen(); // duplicate — state already connected, no-op
    expect(onStateChange).toHaveBeenCalledTimes(1); // only the first open
  });
});

// ─── WebSocketVideoClient — stats ────────────────────────────────────────────

describe('WebSocketVideoClient — stats', () => {
  it('starts with zero stats', () => {
    const client = new WebSocketVideoClient({ url: 'ws://localhost:8765' });
    expect(client.getStats()).toEqual({
      fps: 0,
      framesReceived: 0,
      framesDecoded: 0,
      codec: null,
    });
  });

  it('increments framesReceived for each binary H.264 message', async () => {
    const client = new WebSocketVideoClient({ url: 'ws://localhost:8765' });
    client.connect();
    wsInstance!.simulateOpen();

    const msg = makeWsMessage(0x01, makeH264IdrBuffer());
    wsInstance!.simulateMessage(msg);
    await Promise.resolve();

    expect(client.getStats().framesReceived).toBe(1);
    expect(client.getStats().codec).toBe('h264');
  });

  it('increments framesReceived for each binary JPEG message', async () => {
    const client = new WebSocketVideoClient({ url: 'ws://localhost:8765' });
    client.connect();
    wsInstance!.simulateOpen();

    const msg = makeWsMessage(0x02, makeJpegBuffer());
    wsInstance!.simulateMessage(msg);
    await Promise.resolve();

    expect(client.getStats().framesReceived).toBe(1);
    expect(client.getStats().codec).toBe('jpeg');
  });

  it('ignores messages that are too short (< 2 bytes)', async () => {
    const client = new WebSocketVideoClient({ url: 'ws://localhost:8765' });
    client.connect();
    wsInstance!.simulateOpen();

    wsInstance!.simulateMessage(new ArrayBuffer(1));
    await Promise.resolve();

    expect(client.getStats().framesReceived).toBe(0);
  });

  it('ignores non-ArrayBuffer messages', async () => {
    const client = new WebSocketVideoClient({ url: 'ws://localhost:8765' });
    client.connect();
    wsInstance!.simulateOpen();

    // Simulate a text message (not ArrayBuffer)
    wsInstance!.onmessage?.(new MessageEvent('message', { data: 'text' }));
    await Promise.resolve();

    expect(client.getStats().framesReceived).toBe(0);
  });
});

// ─── WebSocketVideoClient — H.264 decoding ───────────────────────────────────

describe('WebSocketVideoClient — H.264 decoding', () => {
  it('configures VideoDecoder with codec string from SPS NAL', async () => {
    // Build a frame with SPS then IDR
    const sps = new Uint8Array(makeSpsBuffer(0x42, 0x00, 0x1e));
    const idr = new Uint8Array(makeH264IdrBuffer());
    const combined = new ArrayBuffer(sps.length + idr.length);
    new Uint8Array(combined).set(sps, 0);
    new Uint8Array(combined).set(idr, sps.length);

    const client = new WebSocketVideoClient({ url: 'ws://localhost:8765' });
    client.connect();
    wsInstance!.simulateOpen();

    wsInstance!.simulateMessage(makeWsMessage(0x01, combined));
    await Promise.resolve();

    const decoder = MockVideoDecoder.instances[0];
    expect(decoder).toBeDefined();
    expect(decoder.configuredCodec).toBe('avc1.42001e');
  });

  it('uses key type for IDR frames', async () => {
    const client = new WebSocketVideoClient({ url: 'ws://localhost:8765' });
    client.connect();
    wsInstance!.simulateOpen();

    wsInstance!.simulateMessage(makeWsMessage(0x01, makeH264IdrBuffer()));
    await Promise.resolve();

    const decoder = MockVideoDecoder.instances[0];
    expect(decoder.decodedChunks[0].init.type).toBe('key');
  });

  it('uses delta type for non-IDR frames', async () => {
    const client = new WebSocketVideoClient({ url: 'ws://localhost:8765' });
    client.connect();
    wsInstance!.simulateOpen();

    wsInstance!.simulateMessage(makeWsMessage(0x01, makeH264DeltaBuffer()));
    await Promise.resolve();

    const decoder = MockVideoDecoder.instances[0];
    expect(decoder.decodedChunks[0].init.type).toBe('delta');
  });

  it('calls onFrame callback after decoding', async () => {
    const onFrame = vi.fn();
    const client = new WebSocketVideoClient({
      url: 'ws://localhost:8765',
      onFrame,
    });
    client.connect();
    wsInstance!.simulateOpen();

    wsInstance!.simulateMessage(makeWsMessage(0x01, makeH264IdrBuffer()));
    await Promise.resolve();

    expect(onFrame).toHaveBeenCalledWith(expect.objectContaining({ codec: 'h264' }));
  });

  it('calls onError when WebCodecs is not supported', async () => {
    vi.stubGlobal('VideoDecoder', undefined);

    const onError = vi.fn();
    const client = new WebSocketVideoClient({
      url: 'ws://localhost:8765',
      onError,
    });
    client.connect();
    wsInstance!.simulateOpen();

    wsInstance!.simulateMessage(makeWsMessage(0x01, makeH264IdrBuffer()));
    await Promise.resolve();

    expect(onError).toHaveBeenCalledWith(expect.any(Error));
  });

  it('reuses the same VideoDecoder instance across frames with the same codec', async () => {
    const client = new WebSocketVideoClient({ url: 'ws://localhost:8765' });
    client.connect();
    wsInstance!.simulateOpen();

    wsInstance!.simulateMessage(makeWsMessage(0x01, makeH264IdrBuffer()));
    await Promise.resolve();
    wsInstance!.simulateMessage(makeWsMessage(0x01, makeH264DeltaBuffer()));
    await Promise.resolve();

    // Should only have created one VideoDecoder instance
    expect(MockVideoDecoder.instances.length).toBe(1);
    expect(MockVideoDecoder.instances[0].decodedChunks.length).toBe(2);
  });
});

// ─── WebSocketVideoClient — JPEG decoding ────────────────────────────────────

describe('WebSocketVideoClient — JPEG decoding', () => {
  it('tracks framesDecoded for JPEG frames without a canvas', async () => {
    const client = new WebSocketVideoClient({ url: 'ws://localhost:8765' });
    client.connect();
    wsInstance!.simulateOpen();

    wsInstance!.simulateMessage(makeWsMessage(0x02, makeJpegBuffer()));
    await Promise.resolve();

    expect(client.getStats().framesDecoded).toBe(1);
  });

  it('calls onFrame immediately for JPEG frames (before canvas render)', async () => {
    const onFrame = vi.fn();
    const client = new WebSocketVideoClient({
      url: 'ws://localhost:8765',
      onFrame,
    });
    client.connect();
    wsInstance!.simulateOpen();

    wsInstance!.simulateMessage(makeWsMessage(0x02, makeJpegBuffer()));
    await Promise.resolve();

    expect(onFrame).toHaveBeenCalledWith(expect.objectContaining({ codec: 'jpeg' }));
  });

  it('creates a blob URL when a canvas is configured', async () => {
    const mockCanvas = {
      getContext: vi.fn().mockReturnValue({
        drawImage: vi.fn(),
        clearRect: vi.fn(),
      }),
      width: 0,
      height: 0,
    } as unknown as HTMLCanvasElement;

    const client = new WebSocketVideoClient({
      url: 'ws://localhost:8765',
      canvas: mockCanvas,
    });
    client.connect();
    wsInstance!.simulateOpen();

    wsInstance!.simulateMessage(makeWsMessage(0x02, makeJpegBuffer()));
    await Promise.resolve();

    expect(URL.createObjectURL).toHaveBeenCalled();
  });
});
