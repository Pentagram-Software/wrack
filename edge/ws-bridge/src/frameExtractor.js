/**
 * Frame type detection and extraction for the UDP video streaming protocol.
 *
 * Supports two payload formats that the Raspberry Pi streamer can produce:
 *   - H.264 NAL bitstream (starts with NAL start code 0x00 0x00 0x00 0x01 or 0x00 0x00 0x01)
 *   - JPEG bytes, either raw (starts with 0xFF 0xD8) or embedded inside a
 *     Python pickle-encoded numpy array (legacy JPEG mode)
 *
 * Wire protocol sent to WebSocket clients (per binary message):
 *   Byte 0  : frame type  0x01 = H.264 | 0x02 = JPEG
 *   Bytes 1+: raw frame payload
 */

/** Wire-protocol type bytes forwarded to browser clients. */
const FRAME_TYPE_H264 = 0x01;
const FRAME_TYPE_JPEG = 0x02;

/**
 * Locate raw JPEG bytes (FF D8 ... FF D9) inside an arbitrary buffer.
 * Returns the slice containing only the JPEG data, or null if not found.
 *
 * @param {Buffer} buf
 * @returns {Buffer | null}
 */
function extractJpeg(buf) {
  // Fast path: buffer already starts with JPEG magic
  if (buf.length >= 2 && buf[0] === 0xff && buf[1] === 0xd8) {
    // Find the JPEG end marker FF D9
    for (let i = buf.length - 2; i >= 2; i--) {
      if (buf[i] === 0xff && buf[i + 1] === 0xd9) {
        return buf.slice(0, i + 2);
      }
    }
    return buf; // no end marker found — return as-is (partial JPEG)
  }

  // Slow path: scan for JPEG start marker embedded inside a pickle blob
  for (let i = 0; i < buf.length - 1; i++) {
    if (buf[i] === 0xff && buf[i + 1] === 0xd8) {
      // Found potential JPEG start; now find the matching FF D9 end marker
      for (let j = i + 2; j < buf.length - 1; j++) {
        if (buf[j] === 0xff && buf[j + 1] === 0xd9) {
          return buf.slice(i, j + 2);
        }
      }
    }
  }

  return null;
}

/**
 * Detect the payload type of a reassembled UDP frame.
 *
 * @param {Buffer} buf  Complete reassembled frame payload.
 * @returns {'h264' | 'jpeg' | 'unknown'}
 */
function detectFrameType(buf) {
  if (buf.length < 4) return 'unknown';

  // H.264 NAL 4-byte start code: 00 00 00 01
  if (buf[0] === 0x00 && buf[1] === 0x00 && buf[2] === 0x00 && buf[3] === 0x01) {
    return 'h264';
  }

  // H.264 NAL 3-byte start code: 00 00 01
  if (buf[0] === 0x00 && buf[1] === 0x00 && buf[2] === 0x01) {
    return 'h264';
  }

  // Raw JPEG magic: FF D8
  if (buf[0] === 0xff && buf[1] === 0xd8) {
    return 'jpeg';
  }

  // Python pickle protocol byte (\x80) — likely pickle-encoded numpy JPEG array
  if (buf[0] === 0x80) {
    return 'jpeg'; // resolved by extractJpeg() at send time
  }

  return 'unknown';
}

/**
 * Prepare a binary WebSocket message from a reassembled UDP frame.
 *
 * Returns a Buffer prefixed with the single-byte frame type (0x01 or 0x02),
 * followed by the raw frame payload, or null if the frame type cannot be
 * determined.
 *
 * @param {Buffer} frameData  Complete reassembled frame payload.
 * @returns {{ type: number, payload: Buffer } | null}
 */
function prepareWsPayload(frameData) {
  const kind = detectFrameType(frameData);

  if (kind === 'h264') {
    const msg = Buffer.allocUnsafe(1 + frameData.length);
    msg[0] = FRAME_TYPE_H264;
    frameData.copy(msg, 1);
    return { type: FRAME_TYPE_H264, payload: msg };
  }

  if (kind === 'jpeg') {
    const jpegBytes = extractJpeg(frameData);
    if (!jpegBytes) return null;
    const msg = Buffer.allocUnsafe(1 + jpegBytes.length);
    msg[0] = FRAME_TYPE_JPEG;
    jpegBytes.copy(msg, 1);
    return { type: FRAME_TYPE_JPEG, payload: msg };
  }

  return null;
}

module.exports = {
  FRAME_TYPE_H264,
  FRAME_TYPE_JPEG,
  extractJpeg,
  detectFrameType,
  prepareWsPayload,
};
