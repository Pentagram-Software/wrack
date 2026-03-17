import {
  FRAME_START_MARKER,
  CHUNK_MARKER,
  CHUNK_PAYLOAD_SIZE,
  detectFrameStartFormat,
} from "./protocol";

// MARK: - FrameStartPacket

export interface FrameStartPacket {
  frameId:    bigint;
  frameSize:  bigint;
  chunkCount: bigint;
}

/**
 * Parse a FRAME_START UDP datagram.
 * Handles both 64-bit (primary, Raspberry Pi 64-bit) and 32-bit (fallback) wire formats.
 * Returns null for unrecognised data.
 */
export function parseFrameStart(buf: Buffer): FrameStartPacket | null {
  if (!buf.subarray(0, FRAME_START_MARKER.length).equals(FRAME_START_MARKER)) {
    return null;
  }

  const fmt = detectFrameStartFormat(buf);
  const body = buf.subarray(FRAME_START_MARKER.length);

  if (fmt === "uint64") {
    return {
      frameId:    body.readBigUInt64LE(0),
      frameSize:  body.readBigUInt64LE(8),
      chunkCount: body.readBigUInt64LE(16),
    };
  }

  if (fmt === "uint32") {
    return {
      frameId:    BigInt(body.readUInt32LE(0)),
      frameSize:  BigInt(body.readUInt32LE(4)),
      chunkCount: BigInt(body.readUInt32LE(8)),
    };
  }

  return null;
}

// MARK: - ChunkPacket

export interface ChunkPacket {
  frameId:    bigint;
  chunkIndex: bigint;
  payload:    Buffer;
}

/**
 * Parse a CHUNK UDP datagram.
 * Handles both 64-bit (primary) and 32-bit (fallback) wire formats.
 */
export function parseChunk(buf: Buffer): ChunkPacket | null {
  if (!buf.subarray(0, CHUNK_MARKER.length).equals(CHUNK_MARKER)) {
    return null;
  }

  const markerLen = CHUNK_MARKER.length;  // 5

  // Try 64-bit first (header = 5 + 16 = 21 bytes)
  if (buf.length >= 21) {
    return {
      frameId:    buf.readBigUInt64LE(markerLen),
      chunkIndex: buf.readBigUInt64LE(markerLen + 8),
      payload:    buf.subarray(21),
    };
  }

  // 32-bit fallback (header = 5 + 8 = 13 bytes)
  if (buf.length >= 13) {
    return {
      frameId:    BigInt(buf.readUInt32LE(markerLen)),
      chunkIndex: BigInt(buf.readUInt32LE(markerLen + 4)),
      payload:    buf.subarray(13),
    };
  }

  return null;
}

// MARK: - FrameAssembler

interface PendingFrame {
  buffer:          Buffer;
  expectedChunks:  number;
  receivedIndices: Set<number>;
}

/**
 * Reassembles UDP chunks into complete video frames.
 */
export class FrameAssembler {
  private pending = new Map<bigint, PendingFrame>();

  handleFrameStart(packet: FrameStartPacket): void {
    this.pending.set(packet.frameId, {
      buffer:          Buffer.alloc(Number(packet.frameSize)),
      expectedChunks:  Number(packet.chunkCount),
      receivedIndices: new Set(),
    });
  }

  /**
   * Returns the complete frame Buffer once all chunks arrive, otherwise null.
   */
  handleChunk(packet: ChunkPacket): Buffer | null {
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
   * Drop stale partial frames, keeping only the newest `count` frame IDs.
   */
  pruneStale(keepLast = 30): void {
    if (this.pending.size <= keepLast) return;
    const sorted = [...this.pending.keys()].sort((a, b) => (a < b ? -1 : 1));
    sorted.slice(0, this.pending.size - keepLast).forEach((k) => this.pending.delete(k));
  }
}
