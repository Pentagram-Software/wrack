'use strict';

const {
  FRAME_TYPE_H264,
  FRAME_TYPE_JPEG,
  extractJpeg,
  detectFrameType,
  prepareWsPayload,
} = require('../src/frameExtractor');

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Build a minimal JPEG buffer (FF D8 ... FF D9). */
function makeJpeg(payloadBytes = 10) {
  const buf = Buffer.alloc(payloadBytes + 4);
  buf[0] = 0xff; buf[1] = 0xd8;          // SOI
  buf[payloadBytes + 2] = 0xff;
  buf[payloadBytes + 3] = 0xd9;          // EOI
  return buf;
}

/** Build a minimal H.264 NAL unit with a 4-byte start code. */
function makeH264Nal(nalType = 0x01, payloadBytes = 8) {
  const buf = Buffer.alloc(4 + 1 + payloadBytes);
  buf[0] = 0x00; buf[1] = 0x00; buf[2] = 0x00; buf[3] = 0x01; // start code
  buf[4] = nalType & 0x1f;
  return buf;
}

/** Build a minimal H.264 NAL unit with a 3-byte start code. */
function makeH264Nal3(nalType = 0x01, payloadBytes = 8) {
  const buf = Buffer.alloc(3 + 1 + payloadBytes);
  buf[0] = 0x00; buf[1] = 0x00; buf[2] = 0x01; // 3-byte start code
  buf[3] = nalType & 0x1f;
  return buf;
}

/** Build a fake Python pickle buffer containing an embedded JPEG. */
function makePickleWithJpeg(leadingBytes = 20) {
  const jpegContent = makeJpeg(50);
  const buf = Buffer.alloc(leadingBytes + jpegContent.length + 10);
  // Simulate pickle header: starts with 0x80 (pickle protocol byte)
  buf[0] = 0x80;
  buf[1] = 0x02; // protocol 2
  // Copy JPEG somewhere in the middle
  jpegContent.copy(buf, leadingBytes);
  return buf;
}

// ─── extractJpeg ─────────────────────────────────────────────────────────────

describe('extractJpeg', () => {
  test('returns the buffer unchanged when it is already a bare JPEG', () => {
    const jpeg = makeJpeg(100);
    const result = extractJpeg(jpeg);
    expect(result).not.toBeNull();
    expect(result[0]).toBe(0xff);
    expect(result[1]).toBe(0xd8);
    expect(result[result.length - 2]).toBe(0xff);
    expect(result[result.length - 1]).toBe(0xd9);
  });

  test('extracts JPEG embedded in a pickle blob', () => {
    const pickled = makePickleWithJpeg(30);
    const result = extractJpeg(pickled);
    expect(result).not.toBeNull();
    expect(result[0]).toBe(0xff);
    expect(result[1]).toBe(0xd8);
  });

  test('returns null when no JPEG start marker is present', () => {
    const buf = Buffer.from([0x00, 0x01, 0x02, 0x03, 0x04]);
    expect(extractJpeg(buf)).toBeNull();
  });

  test('handles a buffer that is too short', () => {
    const tiny = Buffer.from([0xff]);
    expect(extractJpeg(tiny)).toBeNull();
  });

  test('returns partial JPEG when end marker is absent', () => {
    // JPEG start but no FF D9 end
    const buf = Buffer.from([0xff, 0xd8, 0xaa, 0xbb]);
    const result = extractJpeg(buf);
    expect(result).not.toBeNull(); // returns partial
    expect(result[0]).toBe(0xff);
    expect(result[1]).toBe(0xd8);
  });
});

// ─── detectFrameType ─────────────────────────────────────────────────────────

describe('detectFrameType', () => {
  test('detects H.264 with 4-byte start code', () => {
    expect(detectFrameType(makeH264Nal())).toBe('h264');
  });

  test('detects H.264 with 3-byte start code', () => {
    expect(detectFrameType(makeH264Nal3())).toBe('h264');
  });

  test('detects raw JPEG', () => {
    expect(detectFrameType(makeJpeg(50))).toBe('jpeg');
  });

  test('detects pickle-encoded JPEG (starts with 0x80)', () => {
    const buf = Buffer.from([0x80, 0x02, 0xaa, 0xbb]);
    expect(detectFrameType(buf)).toBe('jpeg');
  });

  test('returns unknown for unrecognised data', () => {
    const buf = Buffer.from([0xde, 0xad, 0xbe, 0xef, 0x00]);
    expect(detectFrameType(buf)).toBe('unknown');
  });

  test('returns unknown for a buffer that is too short', () => {
    expect(detectFrameType(Buffer.from([0x00, 0x01]))).toBe('unknown');
  });
});

// ─── prepareWsPayload ────────────────────────────────────────────────────────

describe('prepareWsPayload', () => {
  test('returns type 0x01 for H.264 frame', () => {
    const nal = makeH264Nal(0x41, 20); // non-IDR slice
    const result = prepareWsPayload(nal);
    expect(result).not.toBeNull();
    expect(result.type).toBe(FRAME_TYPE_H264);
    expect(result.payload[0]).toBe(FRAME_TYPE_H264);
    // Rest of payload should be the original NAL data
    expect(result.payload.length).toBe(1 + nal.length);
  });

  test('type byte is 0x01 for H.264 (constant)', () => {
    expect(FRAME_TYPE_H264).toBe(0x01);
  });

  test('returns type 0x02 for raw JPEG frame', () => {
    const jpeg = makeJpeg(80);
    const result = prepareWsPayload(jpeg);
    expect(result).not.toBeNull();
    expect(result.type).toBe(FRAME_TYPE_JPEG);
    expect(result.payload[0]).toBe(FRAME_TYPE_JPEG);
  });

  test('type byte is 0x02 for JPEG (constant)', () => {
    expect(FRAME_TYPE_JPEG).toBe(0x02);
  });

  test('returns type 0x02 for pickle-wrapped JPEG', () => {
    const pickled = makePickleWithJpeg(15);
    const result = prepareWsPayload(pickled);
    expect(result).not.toBeNull();
    expect(result.type).toBe(FRAME_TYPE_JPEG);
  });

  test('returns null for unrecognised frame data', () => {
    const buf = Buffer.from([0xde, 0xad, 0xbe, 0xef, 0x00, 0x01, 0x02]);
    expect(prepareWsPayload(buf)).toBeNull();
  });

  test('JPEG payload in WsPayload begins with FF D8 after the type byte', () => {
    const jpeg = makeJpeg(60);
    const result = prepareWsPayload(jpeg);
    expect(result.payload[1]).toBe(0xff);
    expect(result.payload[2]).toBe(0xd8);
  });

  test('H.264 payload in WsPayload begins with start code after the type byte', () => {
    const nal = makeH264Nal();
    const result = prepareWsPayload(nal);
    expect(result.payload[1]).toBe(0x00);
    expect(result.payload[2]).toBe(0x00);
    expect(result.payload[3]).toBe(0x00);
    expect(result.payload[4]).toBe(0x01);
  });
});
