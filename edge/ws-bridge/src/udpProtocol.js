/**
 * Minimal implementation of the Wrack UDP video streaming protocol for Node.js.
 *
 * Mirrors the logic in shared/video-protocol/ts/src/ without the TypeScript
 * build step, so the bridge server can run with plain `node`.
 *
 * Protocol constants reference: shared/video-protocol/UDP_Frame_Format_Documentation.md
 */

const FRAME_START_MARKER = Buffer.from('FRAME_START'); // 11 bytes
const CHUNK_MARKER = Buffer.from('CHUNK');             //  5 bytes
const CHUNK_PAYLOAD_SIZE = 1200;                        // bytes per chunk

const MSG_REGISTER_CLIENT = Buffer.from('REGISTER_CLIENT');
const MSG_REGISTERED = Buffer.from('REGISTERED');
const MSG_KEEPALIVE = Buffer.from('KEEPALIVE');
const MSG_DISCONNECT = Buffer.from('DISCONNECT');

const SERVER_PORT = 9999;
const KEEPALIVE_INTERVAL_MS = 5_000;
const CLIENT_TIMEOUT_MS = 30_000;

/**
 * Parse a FRAME_START datagram.
 * Supports both 64-bit (Raspberry Pi 64-bit, primary) and 32-bit (legacy) formats.
 *
 * @param {Buffer} buf
 * @returns {{ frameId: bigint, frameSize: bigint, chunkCount: bigint } | null}
 */
function parseFrameStart(buf) {
  if (!buf.subarray(0, FRAME_START_MARKER.length).equals(FRAME_START_MARKER)) return null;

  const body = buf.subarray(FRAME_START_MARKER.length);

  // 64-bit format: FRAME_START(11) + 3×uint64LE = 35 bytes total
  if (buf.length === 35) {
    return {
      frameId: body.readBigUInt64LE(0),
      frameSize: body.readBigUInt64LE(8),
      chunkCount: body.readBigUInt64LE(16),
    };
  }

  // 32-bit format: FRAME_START(11) + 3×uint32LE = 23 bytes total
  if (buf.length >= 23) {
    return {
      frameId: BigInt(body.readUInt32LE(0)),
      frameSize: BigInt(body.readUInt32LE(4)),
      chunkCount: BigInt(body.readUInt32LE(8)),
    };
  }

  return null;
}

/**
 * Parse a CHUNK datagram.
 *
 * @param {Buffer} buf
 * @returns {{ frameId: bigint, chunkIndex: bigint, payload: Buffer } | null}
 */
function parseChunk(buf) {
  if (!buf.subarray(0, CHUNK_MARKER.length).equals(CHUNK_MARKER)) return null;

  const ml = CHUNK_MARKER.length; // 5

  // 64-bit: CHUNK(5) + frameId(8) + chunkIndex(8) = 21-byte header
  if (buf.length >= 21) {
    return {
      frameId: buf.readBigUInt64LE(ml),
      chunkIndex: buf.readBigUInt64LE(ml + 8),
      payload: buf.subarray(21),
    };
  }

  // 32-bit: CHUNK(5) + frameId(4) + chunkIndex(4) = 13-byte header
  if (buf.length >= 13) {
    return {
      frameId: BigInt(buf.readUInt32LE(ml)),
      chunkIndex: BigInt(buf.readUInt32LE(ml + 4)),
      payload: buf.subarray(13),
    };
  }

  return null;
}

/**
 * Reassembles UDP chunks into complete video frames.
 *
 * Emits a complete frame Buffer once all chunks for a given frameId arrive.
 */
class FrameAssembler {
  constructor() {
    /** @type {Map<bigint, { buffer: Buffer, expectedChunks: number, receivedIndices: Set<number> }>} */
    this.pending = new Map();
  }

  /** @param {{ frameId: bigint, frameSize: bigint, chunkCount: bigint }} packet */
  handleFrameStart(packet) {
    this.pending.set(packet.frameId, {
      buffer: Buffer.alloc(Number(packet.frameSize)),
      expectedChunks: Number(packet.chunkCount),
      receivedIndices: new Set(),
    });
  }

  /**
   * @param {{ frameId: bigint, chunkIndex: bigint, payload: Buffer }} packet
   * @returns {Buffer | null}  Complete frame Buffer, or null if not yet complete.
   */
  handleChunk(packet) {
    const frame = this.pending.get(packet.frameId);
    if (!frame) return null;

    const idx = Number(packet.chunkIndex);
    if (frame.receivedIndices.has(idx)) return null;

    const offset = idx * CHUNK_PAYLOAD_SIZE;
    if (offset >= frame.buffer.length) return null;

    packet.payload.copy(frame.buffer, offset, 0, frame.buffer.length - offset);
    frame.receivedIndices.add(idx);

    if (frame.receivedIndices.size >= frame.expectedChunks) {
      const complete = frame.buffer;
      this.pending.delete(packet.frameId);
      return complete;
    }

    return null;
  }

  /**
   * Drop oldest partial frames, keeping at most `keepLast` pending frame IDs.
   * @param {number} keepLast
   */
  pruneStale(keepLast = 30) {
    if (this.pending.size <= keepLast) return;
    const sorted = [...this.pending.keys()].sort((a, b) => (a < b ? -1 : 1));
    sorted.slice(0, this.pending.size - keepLast).forEach((k) => this.pending.delete(k));
  }
}

module.exports = {
  FRAME_START_MARKER,
  CHUNK_MARKER,
  CHUNK_PAYLOAD_SIZE,
  MSG_REGISTER_CLIENT,
  MSG_REGISTERED,
  MSG_KEEPALIVE,
  MSG_DISCONNECT,
  SERVER_PORT,
  KEEPALIVE_INTERVAL_MS,
  CLIENT_TIMEOUT_MS,
  parseFrameStart,
  parseChunk,
  FrameAssembler,
};
