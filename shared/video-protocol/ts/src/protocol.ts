/**
 * Constants for the UDP video streaming protocol.
 * See: shared/video-protocol/UDP_Frame_Format_Documentation.md
 *
 * NOTE: Web browsers cannot use raw UDP sockets.
 * This package targets Node.js — use it in a WebSocket bridge that forwards
 * UDP packets from the Raspberry Pi to browser clients.
 */

export const SERVER_PORT = 9999;
export const CHUNK_PAYLOAD_SIZE = 1200;
export const CLIENT_TIMEOUT_MS = 30_000;
export const KEEPALIVE_INTERVAL_MS = 5_000;

// Packet markers (UTF-8 ASCII)
export const FRAME_START_MARKER = Buffer.from("FRAME_START");  // 11 bytes
export const CHUNK_MARKER       = Buffer.from("CHUNK");        //  5 bytes

// Control messages
export const MSG_REGISTER_CLIENT = Buffer.from("REGISTER_CLIENT");
export const MSG_REGISTERED      = Buffer.from("REGISTERED");
export const MSG_KEEPALIVE       = Buffer.from("KEEPALIVE");
export const MSG_DISCONNECT      = Buffer.from("DISCONNECT");

/**
 * Wire format for header integer fields.
 *
 * Raspberry Pi 64-bit (primary):  struct.pack("LLL") → BigUInt64LE
 *   FRAME_START total: 35 bytes  (11 + 3×8)
 *   CHUNK header:      21 bytes  ( 5 + 2×8)
 *
 * Legacy 32-bit (fallback):       struct.pack("III") → UInt32LE
 *   FRAME_START total: 23 bytes  (11 + 3×4)
 *   CHUNK header:      13 bytes  ( 5 + 2×4)
 */
export type HeaderFormat = "uint64" | "uint32";

export function detectFrameStartFormat(buf: Buffer): HeaderFormat | null {
  if (buf.length === 35) return "uint64";
  if (buf.length >= 23) return "uint32";
  return null;
}

export function detectChunkFormat(buf: Buffer): HeaderFormat | null {
  if (buf.length >= 21) return "uint64";  // 5 + 16 + ≥1 payload byte
  if (buf.length >= 13) return "uint32";  // 5 +  8 + ≥1 payload byte (or just header)
  return null;
}
