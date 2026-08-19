/**
 * Unit tests for the UDP video streaming protocol packet parsing and reassembly.
 * Covers both 64-bit (Raspberry Pi primary) and 32-bit (legacy) wire formats.
 *
 * Run: npm test  (compiles TypeScript, then node --test dist/packets.test.js)
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  parseFrameStart,
  parseChunk,
  FrameAssembler,
  type FrameStartPacket,
  type ChunkPacket,
} from "./packets";
import {
  FRAME_START_MARKER,
  CHUNK_MARKER,
  CHUNK_PAYLOAD_SIZE,
  detectFrameStartFormat,
  detectChunkFormat,
} from "./protocol";

// ---------------------------------------------------------------------------
// Helpers to build synthetic wire packets
// ---------------------------------------------------------------------------

function makeFrameStart64(frameId: bigint, frameSize: bigint, chunkCount: bigint): Buffer {
  const body = Buffer.alloc(24);  // 3 × uint64LE
  body.writeBigUInt64LE(frameId, 0);
  body.writeBigUInt64LE(frameSize, 8);
  body.writeBigUInt64LE(chunkCount, 16);
  return Buffer.concat([FRAME_START_MARKER, body]);  // 35 bytes total
}

function makeFrameStart32(frameId: number, frameSize: number, chunkCount: number): Buffer {
  const body = Buffer.alloc(12);  // 3 × uint32LE
  body.writeUInt32LE(frameId, 0);
  body.writeUInt32LE(frameSize, 4);
  body.writeUInt32LE(chunkCount, 8);
  return Buffer.concat([FRAME_START_MARKER, body]);  // 23 bytes total
}

function makeChunk64(frameId: bigint, chunkIndex: bigint, payload: Buffer): Buffer {
  const header = Buffer.alloc(16);  // 2 × uint64LE
  header.writeBigUInt64LE(frameId, 0);
  header.writeBigUInt64LE(chunkIndex, 8);
  return Buffer.concat([CHUNK_MARKER, header, payload]);  // 21 + payload
}

function makeChunk32(frameId: number, chunkIndex: number, payload: Buffer): Buffer {
  const header = Buffer.alloc(8);  // 2 × uint32LE
  header.writeUInt32LE(frameId, 0);
  header.writeUInt32LE(chunkIndex, 4);
  return Buffer.concat([CHUNK_MARKER, header, payload]);  // 13 + payload
}

/** Fails the test if value is null, otherwise returns it with a narrowed type. */
function requireNonNull<T>(value: T | null, label: string): T {
  if (value === null) throw new assert.AssertionError({ message: `${label} must not be null` });
  return value;
}

// ---------------------------------------------------------------------------
// detectFrameStartFormat
// ---------------------------------------------------------------------------

describe("detectFrameStartFormat", () => {
  it("returns 'uint64' for a 35-byte buffer", () => {
    assert.equal(detectFrameStartFormat(Buffer.alloc(35)), "uint64");
  });

  it("returns 'uint32' for a 23-byte buffer", () => {
    assert.equal(detectFrameStartFormat(Buffer.alloc(23)), "uint32");
  });

  it("returns 'uint32' for a buffer longer than 23 bytes but not exactly 35", () => {
    assert.equal(detectFrameStartFormat(Buffer.alloc(30)), "uint32");
  });

  it("returns null for a buffer shorter than 23 bytes", () => {
    assert.equal(detectFrameStartFormat(Buffer.alloc(10)), null);
  });

  it("returns null for an empty buffer", () => {
    assert.equal(detectFrameStartFormat(Buffer.alloc(0)), null);
  });
});

// ---------------------------------------------------------------------------
// detectChunkFormat
// ---------------------------------------------------------------------------

describe("detectChunkFormat", () => {
  it("returns 'uint64' for a buffer >= 21 bytes", () => {
    assert.equal(detectChunkFormat(Buffer.alloc(22)), "uint64");
  });

  it("returns 'uint32' for a buffer of exactly 13 bytes", () => {
    assert.equal(detectChunkFormat(Buffer.alloc(13)), "uint32");
  });

  it("returns null for a buffer shorter than 13 bytes", () => {
    assert.equal(detectChunkFormat(Buffer.alloc(5)), null);
  });

  it("returns null for an empty buffer", () => {
    assert.equal(detectChunkFormat(Buffer.alloc(0)), null);
  });
});

// ---------------------------------------------------------------------------
// parseFrameStart — 64-bit
// ---------------------------------------------------------------------------

describe("parseFrameStart — 64-bit wire format", () => {
  it("parses frame ID, size, and chunk count correctly", () => {
    const pkt: FrameStartPacket = requireNonNull(
      parseFrameStart(makeFrameStart64(42n, 2400n, 2n)),
      "FRAME_START 64-bit",
    );
    assert.equal(pkt.frameId, 42n);
    assert.equal(pkt.frameSize, 2400n);
    assert.equal(pkt.chunkCount, 2n);
  });

  it("handles large frame IDs (uint64 range)", () => {
    const bigId = 0xDEAD_BEEF_CAFE_BABEn;
    const pkt = requireNonNull(parseFrameStart(makeFrameStart64(bigId, 100n, 1n)), "large frame ID");
    assert.equal(pkt.frameId, bigId);
  });

  it("returns null for a buffer with wrong marker bytes", () => {
    const buf = makeFrameStart64(1n, 100n, 1n);
    buf.write("BAD_MARKER!", 0, "ascii");
    assert.equal(parseFrameStart(buf), null);
  });

  it("returns null for a CHUNK packet passed by mistake", () => {
    const chunk = makeChunk64(1n, 0n, Buffer.alloc(1200));
    assert.equal(parseFrameStart(chunk), null);
  });
});

// ---------------------------------------------------------------------------
// parseFrameStart — 32-bit
// ---------------------------------------------------------------------------

describe("parseFrameStart — 32-bit wire format", () => {
  it("parses frame ID, size, and chunk count as BigInt", () => {
    const pkt: FrameStartPacket = requireNonNull(
      parseFrameStart(makeFrameStart32(7, 1200, 1)),
      "FRAME_START 32-bit",
    );
    assert.equal(pkt.frameId, 7n);
    assert.equal(pkt.frameSize, 1200n);
    assert.equal(pkt.chunkCount, 1n);
  });

  it("handles maximum uint32 value for all fields", () => {
    const pkt = requireNonNull(
      parseFrameStart(makeFrameStart32(0xFFFF_FFFF, 0xFFFF_FFFF, 0xFFFF_FFFF)),
      "max uint32",
    );
    assert.equal(pkt.frameId, 4294967295n);
  });
});

// ---------------------------------------------------------------------------
// parseFrameStart — invalid inputs
// ---------------------------------------------------------------------------

describe("parseFrameStart — invalid inputs", () => {
  it("returns null for an empty buffer", () => {
    assert.equal(parseFrameStart(Buffer.alloc(0)), null);
  });

  it("returns null for random bytes shorter than any valid format", () => {
    assert.equal(parseFrameStart(Buffer.from([0, 1, 2, 3])), null);
  });
});

// ---------------------------------------------------------------------------
// parseChunk — 64-bit
// ---------------------------------------------------------------------------

describe("parseChunk — 64-bit wire format", () => {
  it("parses frame ID, chunk index, and payload correctly", () => {
    const payload = Buffer.from("hello world");
    const pkt: ChunkPacket = requireNonNull(parseChunk(makeChunk64(5n, 3n, payload)), "CHUNK 64-bit");
    assert.equal(pkt.frameId, 5n);
    assert.equal(pkt.chunkIndex, 3n);
    assert.deepEqual(pkt.payload, payload);
  });

  it("handles full-size 1200-byte payload", () => {
    const payload = Buffer.alloc(CHUNK_PAYLOAD_SIZE, 0xAB);
    const pkt = requireNonNull(parseChunk(makeChunk64(0n, 0n, payload)), "1200-byte chunk");
    assert.equal(pkt.payload.length, CHUNK_PAYLOAD_SIZE);
    assert.equal(pkt.payload[0], 0xAB);
  });
});

// ---------------------------------------------------------------------------
// parseChunk — 32-bit
// ---------------------------------------------------------------------------

describe("parseChunk — 32-bit wire format", () => {
  it("parses frame ID, chunk index, and payload from a 32-bit chunk", () => {
    const payload = Buffer.from([1, 2, 3, 4, 5]);
    const pkt: ChunkPacket = requireNonNull(parseChunk(makeChunk32(9, 0, payload)), "CHUNK 32-bit");
    assert.equal(pkt.frameId, 9n);
    assert.equal(pkt.chunkIndex, 0n);
    assert.deepEqual(pkt.payload, payload);
  });
});

// ---------------------------------------------------------------------------
// parseChunk — invalid inputs
// ---------------------------------------------------------------------------

describe("parseChunk — invalid inputs", () => {
  it("returns null for an empty buffer", () => {
    assert.equal(parseChunk(Buffer.alloc(0)), null);
  });

  it("returns null for a FRAME_START packet passed by mistake", () => {
    const fs = makeFrameStart64(1n, 1200n, 1n);
    assert.equal(parseChunk(fs), null);
  });

  it("returns null for a truncated chunk header (< 13 bytes)", () => {
    const buf = Buffer.concat([CHUNK_MARKER, Buffer.alloc(5)]);
    assert.equal(parseChunk(buf), null);
  });
});

// ---------------------------------------------------------------------------
// FrameAssembler — single-chunk frame
// ---------------------------------------------------------------------------

describe("FrameAssembler — single-chunk frame", () => {
  it("reassembles a 100-byte frame delivered in one chunk", () => {
    const frameData = Buffer.alloc(100, 0x42);
    const assembler = new FrameAssembler();

    assembler.handleFrameStart({ frameId: 1n, frameSize: 100n, chunkCount: 1n });

    const chunkPkt = requireNonNull(
      parseChunk(makeChunk64(1n, 0n, frameData)),
      "single chunk",
    );
    const complete = requireNonNull(assembler.handleChunk(chunkPkt), "complete frame");
    assert.equal(complete.length, 100);
    assert.equal(complete[0], 0x42);
  });
});

// ---------------------------------------------------------------------------
// FrameAssembler — multi-chunk frames
// ---------------------------------------------------------------------------

describe("FrameAssembler — multi-chunk frames", () => {
  it("reassembles a 2500-byte frame across three chunks (in-order)", () => {
    const frameSize = 2500;
    const frameData = Buffer.alloc(frameSize);
    for (let i = 0; i < frameSize; i++) frameData[i] = i % 256;

    const chunkCount = Math.ceil(frameSize / CHUNK_PAYLOAD_SIZE); // 3
    const assembler = new FrameAssembler();
    assembler.handleFrameStart({
      frameId: 10n,
      frameSize: BigInt(frameSize),
      chunkCount: BigInt(chunkCount),
    });

    let result: Buffer | null = null;
    for (let idx = 0; idx < chunkCount; idx++) {
      const start = idx * CHUNK_PAYLOAD_SIZE;
      const end = Math.min(start + CHUNK_PAYLOAD_SIZE, frameSize);
      const chunkPkt = requireNonNull(
        parseChunk(makeChunk64(10n, BigInt(idx), frameData.subarray(start, end))),
        `chunk ${idx}`,
      );
      result = assembler.handleChunk(chunkPkt);
      if (idx < chunkCount - 1) assert.equal(result, null, `frame should not complete after chunk ${idx}`);
    }

    const complete = requireNonNull(result, "complete 2500-byte frame");
    assert.equal(complete.length, frameSize);
    assert.deepEqual(complete, frameData);
  });

  it("returns null when only the first of two chunks has arrived", () => {
    const assembler = new FrameAssembler();
    assembler.handleFrameStart({ frameId: 2n, frameSize: 2400n, chunkCount: 2n });

    const c0 = requireNonNull(
      parseChunk(makeChunk64(2n, 0n, Buffer.alloc(CHUNK_PAYLOAD_SIZE))),
      "first chunk",
    );
    assert.equal(assembler.handleChunk(c0), null);
  });

  it("delivers a complete frame regardless of chunk arrival order", () => {
    const frameSize = CHUNK_PAYLOAD_SIZE * 2;
    const chunk0Data = Buffer.alloc(CHUNK_PAYLOAD_SIZE, 0x01);
    const chunk1Data = Buffer.alloc(CHUNK_PAYLOAD_SIZE, 0x02);

    const assembler = new FrameAssembler();
    assembler.handleFrameStart({ frameId: 3n, frameSize: BigInt(frameSize), chunkCount: 2n });

    // Deliver chunk 1 before chunk 0 (out of order)
    const c1 = requireNonNull(parseChunk(makeChunk64(3n, 1n, chunk1Data)), "chunk 1");
    assert.equal(assembler.handleChunk(c1), null);

    const c0 = requireNonNull(parseChunk(makeChunk64(3n, 0n, chunk0Data)), "chunk 0");
    const frame = requireNonNull(assembler.handleChunk(c0), "out-of-order complete frame");
    assert.equal(frame.length, frameSize);
    assert.equal(frame[0], 0x01);
    assert.equal(frame[CHUNK_PAYLOAD_SIZE], 0x02);
  });
});

// ---------------------------------------------------------------------------
// FrameAssembler — duplicate chunk handling
// ---------------------------------------------------------------------------

describe("FrameAssembler — duplicate chunks", () => {
  it("ignores a duplicate chunk and does not use its data", () => {
    const assembler = new FrameAssembler();
    assembler.handleFrameStart({ frameId: 4n, frameSize: 2400n, chunkCount: 2n });

    const c0a = requireNonNull(
      parseChunk(makeChunk64(4n, 0n, Buffer.alloc(CHUNK_PAYLOAD_SIZE, 0xAA))),
      "chunk 0 first arrival",
    );
    const c0b = requireNonNull(
      parseChunk(makeChunk64(4n, 0n, Buffer.alloc(CHUNK_PAYLOAD_SIZE, 0xBB))),
      "chunk 0 duplicate",
    );

    assert.equal(assembler.handleChunk(c0a), null);  // first arrival
    assert.equal(assembler.handleChunk(c0b), null);  // duplicate — ignored

    const c1 = requireNonNull(
      parseChunk(makeChunk64(4n, 1n, Buffer.alloc(CHUNK_PAYLOAD_SIZE, 0xCC))),
      "chunk 1",
    );
    const frame = requireNonNull(assembler.handleChunk(c1), "frame after duplicate ignored");
    assert.equal(frame[0], 0xAA);  // original data retained, not overwritten by duplicate
  });
});

// ---------------------------------------------------------------------------
// FrameAssembler — chunk for unknown frame ID
// ---------------------------------------------------------------------------

describe("FrameAssembler — unknown frame ID", () => {
  it("returns null when no FRAME_START was received for the frame ID", () => {
    const assembler = new FrameAssembler();
    const c = requireNonNull(parseChunk(makeChunk64(99n, 0n, Buffer.alloc(100))), "orphan chunk");
    assert.equal(assembler.handleChunk(c), null);
  });
});

// ---------------------------------------------------------------------------
// FrameAssembler — pruneStale
// ---------------------------------------------------------------------------

describe("FrameAssembler — pruneStale", () => {
  it("does nothing when pending count is within keepLast", () => {
    const assembler = new FrameAssembler();
    for (let i = 0; i < 5; i++) {
      assembler.handleFrameStart({ frameId: BigInt(i), frameSize: 1200n, chunkCount: 1n });
    }
    assembler.pruneStale(10);

    // frame 4 should still be present
    const c = requireNonNull(parseChunk(makeChunk64(4n, 0n, Buffer.alloc(1200))), "chunk for frame 4");
    assert.ok(assembler.handleChunk(c) !== null, "frame 4 should complete after pruneStale(10)");
  });

  it("removes the oldest frame IDs when count exceeds keepLast", () => {
    const assembler = new FrameAssembler();
    for (let i = 0; i < 35; i++) {
      assembler.handleFrameStart({ frameId: BigInt(i), frameSize: 1200n, chunkCount: 1n });
    }
    assembler.pruneStale(30);

    // Frame 0 should be pruned — chunk should return null (unknown frame)
    const oldChunk = requireNonNull(
      parseChunk(makeChunk64(0n, 0n, Buffer.alloc(1200))),
      "pruned frame chunk",
    );
    assert.equal(assembler.handleChunk(oldChunk), null, "frame 0 should be pruned");

    // Frame 34 (most recent) should still be present
    const recentChunk = requireNonNull(
      parseChunk(makeChunk64(34n, 0n, Buffer.alloc(1200))),
      "recent frame chunk",
    );
    assert.ok(assembler.handleChunk(recentChunk) !== null, "frame 34 should still complete");
  });

  it("multiple concurrent partial frames coexist independently", () => {
    const assembler = new FrameAssembler();
    assembler.handleFrameStart({ frameId: 100n, frameSize: 2400n, chunkCount: 2n });
    assembler.handleFrameStart({ frameId: 200n, frameSize: 1200n, chunkCount: 1n });

    // Complete frame 200 first
    const c200 = requireNonNull(
      parseChunk(makeChunk64(200n, 0n, Buffer.alloc(1200, 0xFF))),
      "frame 200 chunk",
    );
    const f200 = requireNonNull(assembler.handleChunk(c200), "frame 200 complete");
    assert.equal(f200.length, 1200);

    // Frame 100 still pending — first chunk only
    const c100a = requireNonNull(
      parseChunk(makeChunk64(100n, 0n, Buffer.alloc(CHUNK_PAYLOAD_SIZE, 0x11))),
      "frame 100 chunk 0",
    );
    assert.equal(assembler.handleChunk(c100a), null, "frame 100 still incomplete");
  });
});

// ---------------------------------------------------------------------------
// Integration: parse ↔ assemble round-trip
// ---------------------------------------------------------------------------

describe("Integration — parse + assemble round-trip", () => {
  it("reassembles a 3-chunk frame using wire-format buffers end to end (64-bit)", () => {
    const frameId = 77n;
    const totalSize = CHUNK_PAYLOAD_SIZE * 2 + 500;
    const original = Buffer.allocUnsafe(totalSize);
    for (let i = 0; i < totalSize; i++) original[i] = i % 128;

    const fsPacket = requireNonNull(
      parseFrameStart(makeFrameStart64(frameId, BigInt(totalSize), 3n)),
      "FRAME_START parse",
    );

    const assembler = new FrameAssembler();
    assembler.handleFrameStart(fsPacket);

    let result: Buffer | null = null;
    for (let idx = 0; idx < 3; idx++) {
      const start = idx * CHUNK_PAYLOAD_SIZE;
      const end = Math.min(start + CHUNK_PAYLOAD_SIZE, totalSize);
      const chunkPkt = requireNonNull(
        parseChunk(makeChunk64(frameId, BigInt(idx), original.subarray(start, end))),
        `chunk ${idx} parse`,
      );
      result = assembler.handleChunk(chunkPkt);
    }

    const complete = requireNonNull(result, "round-trip 3-chunk frame");
    assert.equal(complete.length, totalSize);
    assert.deepEqual(complete, original);
  });

  it("32-bit parse + assemble round-trip for a frame with tiny payload (payload <= 7 bytes)", () => {
    // NOTE: parseChunk detects format by total packet size. Any 32-bit chunk whose
    // total byte count is >= 21 (i.e. payload >= 8 bytes) is tried as 64-bit first
    // and will be mis-parsed. For the 32-bit fallback to trigger, total must be
    // 13-20 bytes (payload <= 7 bytes). This is a known constraint of the
    // length-heuristic format detection; real deployments rely on caller-level
    // format negotiation based on the FRAME_START packet size.
    const frameId = 3;
    const payload = Buffer.from([0x48, 0x32, 0x36, 0x34]);  // 4 bytes

    const fsPacket = requireNonNull(
      parseFrameStart(makeFrameStart32(frameId, payload.length, 1)),
      "FRAME_START 32-bit parse",
    );

    const assembler = new FrameAssembler();
    assembler.handleFrameStart(fsPacket);

    // Total chunk size = 5 + 8 + 4 = 17 bytes < 21 -> correctly parsed as 32-bit
    const chunkPkt = requireNonNull(
      parseChunk(makeChunk32(frameId, 0, payload)),
      "CHUNK 32-bit parse",
    );
    assert.equal(chunkPkt.frameId, BigInt(frameId));
    assert.equal(chunkPkt.chunkIndex, 0n);

    const frame = requireNonNull(assembler.handleChunk(chunkPkt), "32-bit round-trip frame");
    assert.deepEqual(frame.subarray(0, payload.length), payload);
  });
});
