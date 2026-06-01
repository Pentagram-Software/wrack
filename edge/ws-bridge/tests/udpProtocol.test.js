'use strict';

const {
  parseFrameStart,
  parseChunk,
  FrameAssembler,
  FRAME_START_MARKER,
  CHUNK_MARKER,
  CHUNK_PAYLOAD_SIZE,
} = require('../src/udpProtocol');

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Build a 32-bit FRAME_START datagram (struct.pack("III", ...)). */
function makeFrameStart32(frameId, frameSize, chunkCount) {
  const buf = Buffer.alloc(23); // 11 + 3×4
  FRAME_START_MARKER.copy(buf);
  buf.writeUInt32LE(frameId, 11);
  buf.writeUInt32LE(frameSize, 15);
  buf.writeUInt32LE(chunkCount, 19);
  return buf;
}

/** Build a 64-bit FRAME_START datagram (struct.pack("LLL", ...) on 64-bit Pi). */
function makeFrameStart64(frameId, frameSize, chunkCount) {
  const buf = Buffer.alloc(35); // 11 + 3×8
  FRAME_START_MARKER.copy(buf);
  buf.writeBigUInt64LE(BigInt(frameId), 11);
  buf.writeBigUInt64LE(BigInt(frameSize), 19);
  buf.writeBigUInt64LE(BigInt(chunkCount), 27);
  return buf;
}

/** Build a 32-bit CHUNK datagram. */
function makeChunk32(frameId, chunkIndex, payload) {
  const buf = Buffer.alloc(13 + payload.length); // 5 + 4 + 4 + payload
  CHUNK_MARKER.copy(buf);
  buf.writeUInt32LE(frameId, 5);
  buf.writeUInt32LE(chunkIndex, 9);
  payload.copy(buf, 13);
  return buf;
}

/** Build a 64-bit CHUNK datagram. */
function makeChunk64(frameId, chunkIndex, payload) {
  const buf = Buffer.alloc(21 + payload.length); // 5 + 8 + 8 + payload
  CHUNK_MARKER.copy(buf);
  buf.writeBigUInt64LE(BigInt(frameId), 5);
  buf.writeBigUInt64LE(BigInt(chunkIndex), 13);
  payload.copy(buf, 21);
  return buf;
}

// ─── parseFrameStart ─────────────────────────────────────────────────────────

describe('parseFrameStart', () => {
  test('parses a 32-bit FRAME_START packet', () => {
    const pkt = makeFrameStart32(42, 5000, 5);
    const result = parseFrameStart(pkt);
    expect(result).not.toBeNull();
    expect(result.frameId).toBe(42n);
    expect(result.frameSize).toBe(5000n);
    expect(result.chunkCount).toBe(5n);
  });

  test('parses a 64-bit FRAME_START packet', () => {
    const pkt = makeFrameStart64(100, 12000, 10);
    const result = parseFrameStart(pkt);
    expect(result).not.toBeNull();
    expect(result.frameId).toBe(100n);
    expect(result.frameSize).toBe(12000n);
    expect(result.chunkCount).toBe(10n);
  });

  test('returns null for an unrelated buffer', () => {
    expect(parseFrameStart(Buffer.from('HELLO_WORLD'))).toBeNull();
  });

  test('returns null for a truncated FRAME_START', () => {
    const short = makeFrameStart32(1, 100, 1).slice(0, 15);
    expect(parseFrameStart(short)).toBeNull();
  });

  test('handles zero-value fields', () => {
    const pkt = makeFrameStart32(0, 0, 0);
    const result = parseFrameStart(pkt);
    expect(result.frameId).toBe(0n);
    expect(result.frameSize).toBe(0n);
    expect(result.chunkCount).toBe(0n);
  });
});

// ─── parseChunk ──────────────────────────────────────────────────────────────

describe('parseChunk', () => {
  test('parses a 32-bit CHUNK packet', () => {
    const payload = Buffer.from([0xaa, 0xbb, 0xcc]);
    const pkt = makeChunk32(7, 3, payload);
    const result = parseChunk(pkt);
    expect(result).not.toBeNull();
    expect(result.frameId).toBe(7n);
    expect(result.chunkIndex).toBe(3n);
    expect(result.payload).toEqual(payload);
  });

  test('parses a 64-bit CHUNK packet', () => {
    const payload = Buffer.from([0x01, 0x02]);
    const pkt = makeChunk64(99, 0, payload);
    const result = parseChunk(pkt);
    expect(result).not.toBeNull();
    expect(result.frameId).toBe(99n);
    expect(result.chunkIndex).toBe(0n);
  });

  test('returns null for an unrelated buffer', () => {
    expect(parseChunk(Buffer.from('FRAME_START'))).toBeNull();
  });

  test('returns null for truncated CHUNK (< 13 bytes)', () => {
    const buf = Buffer.alloc(10);
    CHUNK_MARKER.copy(buf);
    expect(parseChunk(buf)).toBeNull();
  });
});

// ─── FrameAssembler ──────────────────────────────────────────────────────────

describe('FrameAssembler', () => {
  function makeFullFrame(frameId, data) {
    const size = data.length;
    const chunkCount = Math.ceil(size / CHUNK_PAYLOAD_SIZE);
    return { frameId: BigInt(frameId), frameSize: BigInt(size), chunkCount: BigInt(chunkCount), data };
  }

  test('returns null before all chunks arrive', () => {
    const assembler = new FrameAssembler();
    const { frameId, frameSize, chunkCount } = makeFullFrame(1, Buffer.alloc(2400));
    assembler.handleFrameStart({ frameId, frameSize, chunkCount });

    const chunk0 = {
      frameId,
      chunkIndex: 0n,
      payload: Buffer.alloc(CHUNK_PAYLOAD_SIZE),
    };
    expect(assembler.handleChunk(chunk0)).toBeNull();
  });

  test('returns complete frame when all chunks arrive', () => {
    const assembler = new FrameAssembler();
    const content = Buffer.from('Hello, World!');
    const { frameId, frameSize, chunkCount, data } = makeFullFrame(2, content);

    assembler.handleFrameStart({ frameId, frameSize, chunkCount });
    const result = assembler.handleChunk({
      frameId,
      chunkIndex: 0n,
      payload: data,
    });

    expect(result).not.toBeNull();
    expect(result.toString()).toBe('Hello, World!');
  });

  test('reassembles multi-chunk frame correctly', () => {
    const assembler = new FrameAssembler();
    const chunk0Data = Buffer.alloc(CHUNK_PAYLOAD_SIZE, 0xaa);
    const chunk1Data = Buffer.alloc(500, 0xbb);
    const totalSize = chunk0Data.length + chunk1Data.length;

    assembler.handleFrameStart({
      frameId: 5n,
      frameSize: BigInt(totalSize),
      chunkCount: 2n,
    });

    const r1 = assembler.handleChunk({ frameId: 5n, chunkIndex: 0n, payload: chunk0Data });
    expect(r1).toBeNull(); // not complete yet

    const r2 = assembler.handleChunk({ frameId: 5n, chunkIndex: 1n, payload: chunk1Data });
    expect(r2).not.toBeNull();
    expect(r2.length).toBe(totalSize);
    // First 1200 bytes should be 0xaa
    expect(r2[0]).toBe(0xaa);
    expect(r2[CHUNK_PAYLOAD_SIZE - 1]).toBe(0xaa);
    // Remaining bytes should be 0xbb
    expect(r2[CHUNK_PAYLOAD_SIZE]).toBe(0xbb);
  });

  test('ignores duplicate chunks', () => {
    const assembler = new FrameAssembler();
    const content = Buffer.alloc(10, 0x01);

    assembler.handleFrameStart({
      frameId: 10n,
      frameSize: BigInt(content.length),
      chunkCount: 1n,
    });

    // First chunk completes the frame
    const r1 = assembler.handleChunk({ frameId: 10n, chunkIndex: 0n, payload: content });
    expect(r1).not.toBeNull();

    // Duplicate chunk for an already-completed frame — frameId was deleted
    const r2 = assembler.handleChunk({ frameId: 10n, chunkIndex: 0n, payload: content });
    expect(r2).toBeNull();
  });

  test('handles chunks arriving out of order', () => {
    const assembler = new FrameAssembler();
    const chunk0 = Buffer.alloc(CHUNK_PAYLOAD_SIZE, 0x01);
    const chunk1 = Buffer.alloc(CHUNK_PAYLOAD_SIZE, 0x02);

    assembler.handleFrameStart({
      frameId: 20n,
      frameSize: BigInt(chunk0.length + chunk1.length),
      chunkCount: 2n,
    });

    // chunk1 arrives first
    const r1 = assembler.handleChunk({ frameId: 20n, chunkIndex: 1n, payload: chunk1 });
    expect(r1).toBeNull();

    // chunk0 completes the frame
    const r2 = assembler.handleChunk({ frameId: 20n, chunkIndex: 0n, payload: chunk0 });
    expect(r2).not.toBeNull();
    expect(r2[0]).toBe(0x01);
    expect(r2[CHUNK_PAYLOAD_SIZE]).toBe(0x02);
  });

  test('pruneStale removes old frames when limit exceeded', () => {
    const assembler = new FrameAssembler();
    // Add 35 partial frames (no chunks delivered)
    for (let i = 0; i < 35; i++) {
      assembler.handleFrameStart({
        frameId: BigInt(i),
        frameSize: 1200n,
        chunkCount: 1n,
      });
    }
    expect(assembler.pending.size).toBe(35);
    assembler.pruneStale(30);
    expect(assembler.pending.size).toBe(30);
  });

  test('ignores chunk for unknown frameId', () => {
    const assembler = new FrameAssembler();
    const result = assembler.handleChunk({
      frameId: 999n,
      chunkIndex: 0n,
      payload: Buffer.alloc(10),
    });
    expect(result).toBeNull();
  });
});
