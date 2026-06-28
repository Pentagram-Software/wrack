/**
 * Browser-side WebSocket video client for the Wrack camera streaming pipeline.
 *
 * Receives binary video frames from the WebSocket bridge server (edge/ws-bridge)
 * and renders them onto an HTMLCanvasElement.  Supports two codecs:
 *   - H.264 via the WebCodecs VideoDecoder API (Chrome 94+, Firefox 130+)
 *   - JPEG  via createObjectURL (universal fallback)
 *
 * Wire protocol (matches edge/ws-bridge/src/frameExtractor.js):
 *   Byte 0  : 0x01 = H.264 NAL bitstream  |  0x02 = raw JPEG bytes
 *   Bytes 1+: frame payload
 */

// ─── Types ────────────────────────────────────────────────────────────────────

export type VideoStreamState =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'error'
  | 'disconnected';

export type VideoCodec = 'h264' | 'jpeg' | null;

export interface VideoStreamStats {
  fps: number;
  framesReceived: number;
  framesDecoded: number;
  codec: VideoCodec;
}

export interface WebSocketVideoClientConfig {
  /** WebSocket URL of the bridge server, e.g. ws://192.168.1.42:8765 */
  url: string;
  /** Canvas element to render video frames onto. */
  canvas?: HTMLCanvasElement | null;
  /** Called whenever the connection state changes. */
  onStateChange?: (state: VideoStreamState, prevState: VideoStreamState) => void;
  /** Called when a non-fatal or fatal error occurs. */
  onError?: (error: Error) => void;
  /** Called each time a frame is successfully rendered. */
  onFrame?: (stats: VideoStreamStats) => void;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const FRAME_TYPE_H264 = 0x01;
const FRAME_TYPE_JPEG = 0x02;

/** H.264 NAL unit types that signal a keyframe (IDR) or parameter sets. */
const H264_NAL_TYPE_IDR = 5;
const H264_NAL_TYPE_SPS = 7;
const H264_NAL_TYPE_PPS = 8;

// ─── Feature detection ────────────────────────────────────────────────────────

/**
 * Returns true if the browser supports the WebCodecs VideoDecoder API.
 */
export function isWebCodecsSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof (window as Window & { VideoDecoder?: unknown }).VideoDecoder === 'function'
  );
}

// ─── H.264 helpers ────────────────────────────────────────────────────────────

/**
 * Scan NAL units in an H.264 bitstream to determine if the frame is a
 * keyframe (contains an IDR NAL unit) or a delta frame.
 *
 * @param data  H.264 NAL bitstream bytes.
 * @returns 'key' if the frame includes an IDR NAL; 'delta' otherwise.
 */
export function detectH264FrameType(data: Uint8Array): 'key' | 'delta' {
  let i = 0;
  while (i < data.length - 4) {
    let offset = 0;
    if (data[i] === 0 && data[i + 1] === 0) {
      if (data[i + 2] === 0 && data[i + 3] === 1) {
        offset = 4; // 4-byte start code
      } else if (data[i + 2] === 1) {
        offset = 3; // 3-byte start code
      }
    }
    if (offset > 0 && i + offset < data.length) {
      const nalType = data[i + offset] & 0x1f;
      if (nalType === H264_NAL_TYPE_IDR) return 'key';
      if (nalType !== H264_NAL_TYPE_SPS && nalType !== H264_NAL_TYPE_PPS) {
        return 'delta';
      }
      i += offset;
    } else {
      i++;
    }
  }
  return 'delta';
}

/**
 * Extract the H.264 codec string from SPS NAL unit data, e.g. "avc1.42001e".
 * Falls back to baseline level 3.0 if the SPS cannot be located.
 *
 * @param data  H.264 NAL bitstream bytes.
 */
export function extractH264Codec(data: Uint8Array): string {
  let i = 0;
  while (i < data.length - 7) {
    let offset = 0;
    if (data[i] === 0 && data[i + 1] === 0) {
      if (data[i + 2] === 0 && data[i + 3] === 1) {
        offset = 4;
      } else if (data[i + 2] === 1) {
        offset = 3;
      }
    }
    if (offset > 0 && i + offset + 3 < data.length) {
      const nalType = data[i + offset] & 0x1f;
      if (nalType === H264_NAL_TYPE_SPS) {
        const profileIdc = data[i + offset + 1];
        const constraintFlags = data[i + offset + 2];
        const levelIdc = data[i + offset + 3];
        return `avc1.${profileIdc.toString(16).padStart(2, '0')}${constraintFlags.toString(16).padStart(2, '0')}${levelIdc.toString(16).padStart(2, '0')}`;
      }
      i += offset;
    } else {
      i++;
    }
  }
  return 'avc1.42001e'; // fallback: baseline profile level 3.0
}

// ─── WebSocketVideoClient ─────────────────────────────────────────────────────

/**
 * Manages the WebSocket connection to the bridge server, decodes incoming
 * video frames, and renders them onto the configured canvas.
 *
 * Usage:
 * ```ts
 * const client = new WebSocketVideoClient({
 *   url: 'ws://192.168.1.42:8765',
 *   canvas: document.getElementById('video') as HTMLCanvasElement,
 *   onStateChange: (state) => console.log(state),
 * });
 * client.connect();
 * // ... later ...
 * client.disconnect();
 * ```
 */
export class WebSocketVideoClient {
  private ws: WebSocket | null = null;
  private decoder: VideoDecoder | null = null;
  private state: VideoStreamState = 'idle';
  private codec: VideoCodec = null;
  private decoderCodecString: string | null = null;

  private framesReceived = 0;
  private framesDecoded = 0;
  private fpsWindowStart = 0;
  private fpsWindowCount = 0;
  private fps = 0;

  constructor(private readonly config: WebSocketVideoClientConfig) {}

  // ─── Public API ────────────────────────────────────────────────────────────

  connect(): void {
    if (this.state !== 'idle' && this.state !== 'disconnected') return;
    this.setState('connecting');
    try {
      this.ws = new WebSocket(this.config.url);
      this.ws.binaryType = 'arraybuffer';
      this.ws.onopen = () => this.handleOpen();
      this.ws.onclose = () => this.handleClose();
      this.ws.onerror = () => this.handleWsError();
      this.ws.onmessage = (ev) => void this.handleMessage(ev);
    } catch (err) {
      this.handleError(err instanceof Error ? err : new Error(String(err)));
    }
  }

  disconnect(): void {
    this.cleanupDecoder();
    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onclose = null;
      this.ws.onerror = null;
      this.ws.onmessage = null;
      this.ws.close();
      this.ws = null;
    }
    this.setState('disconnected');
  }

  getState(): VideoStreamState {
    return this.state;
  }

  getStats(): VideoStreamStats {
    return {
      fps: this.fps,
      framesReceived: this.framesReceived,
      framesDecoded: this.framesDecoded,
      codec: this.codec,
    };
  }

  // ─── WebSocket event handlers ──────────────────────────────────────────────

  private handleOpen(): void {
    this.setState('connected');
    this.fpsWindowStart = performance.now();
    this.fpsWindowCount = 0;
  }

  private handleClose(): void {
    this.cleanupDecoder();
    this.setState('disconnected');
  }

  private handleWsError(): void {
    this.handleError(new Error('WebSocket connection error'));
  }

  private handleError(error: Error): void {
    this.config.onError?.(error);
    this.setState('error');
  }

  private async handleMessage(ev: MessageEvent): Promise<void> {
    if (!(ev.data instanceof ArrayBuffer)) return;
    if (ev.data.byteLength < 2) return;

    const view = new Uint8Array(ev.data);
    const frameType = view[0];
    const payload = ev.data.slice(1);

    this.framesReceived++;

    try {
      if (frameType === FRAME_TYPE_H264) {
        this.codec = 'h264';
        await this.renderH264Frame(payload);
      } else if (frameType === FRAME_TYPE_JPEG) {
        this.codec = 'jpeg';
        this.renderJpegFrame(payload);
      }
      // Unknown frame type — silently skip
    } catch (err) {
      this.config.onError?.(err instanceof Error ? err : new Error(String(err)));
    }
  }

  // ─── Rendering ─────────────────────────────────────────────────────────────

  private async renderH264Frame(payload: ArrayBuffer): Promise<void> {
    const bytes = new Uint8Array(payload);

    if (isWebCodecsSupported()) {
      await this.decodeH264WithWebCodecs(bytes, payload);
    } else {
      // WebCodecs not available — log and skip (H.264 requires decoder support)
      this.config.onError?.(
        new Error('WebCodecs VideoDecoder is not supported in this browser')
      );
    }
  }

  private async decodeH264WithWebCodecs(
    bytes: Uint8Array,
    payload: ArrayBuffer
  ): Promise<void> {
    const codecString = extractH264Codec(bytes);

    // Re-initialise the decoder if the codec changed (e.g. first frame)
    if (!this.decoder || this.decoderCodecString !== codecString) {
      this.cleanupDecoder();
      this.decoderCodecString = codecString;
      this.decoder = new VideoDecoder({
        output: (frame) => {
          this.drawVideoFrame(frame);
          frame.close();
        },
        error: (err) => {
          this.config.onError?.(new Error(`VideoDecoder error: ${err.message}`));
        },
      });
      this.decoder.configure({
        codec: codecString,
        optimizeForLatency: true,
      });
    }

    const frameKind = detectH264FrameType(bytes);
    const chunk = new EncodedVideoChunk({
      type: frameKind,
      timestamp: performance.now() * 1000, // microseconds
      data: payload,
    });

    this.decoder.decode(chunk);

    // Flush to ensure the frame is rendered promptly
    await this.decoder.flush();
  }

  private renderJpegFrame(payload: ArrayBuffer): void {
    // Always track decode stats, even without a canvas.
    this.framesDecoded++;
    this.updateFps();
    this.config.onFrame?.(this.getStats());

    const canvas = this.config.canvas;
    if (!canvas) return;

    const blob = new Blob([payload], { type: 'image/jpeg' });
    const url = URL.createObjectURL(blob);

    const img = new Image();
    img.onload = () => {
      const ctx = canvas.getContext('2d');
      if (ctx) {
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        ctx.drawImage(img, 0, 0);
      }
      URL.revokeObjectURL(url);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
    };
    img.src = url;
  }

  private drawVideoFrame(frame: VideoFrame): void {
    const canvas = this.config.canvas;
    if (!canvas) {
      this.framesDecoded++;
      this.updateFps();
      this.config.onFrame?.(this.getStats());
      return;
    }
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    canvas.width = frame.displayWidth;
    canvas.height = frame.displayHeight;
    ctx.drawImage(frame, 0, 0);

    this.framesDecoded++;
    this.updateFps();
    this.config.onFrame?.(this.getStats());
  }

  // ─── Helpers ───────────────────────────────────────────────────────────────

  private setState(state: VideoStreamState): void {
    const prev = this.state;
    this.state = state;
    if (prev !== state) {
      this.config.onStateChange?.(state, prev);
    }
  }

  private updateFps(): void {
    this.fpsWindowCount++;
    const now = performance.now();
    const elapsed = now - this.fpsWindowStart;
    if (elapsed >= 1000) {
      this.fps = Math.round((this.fpsWindowCount * 1000) / elapsed);
      this.fpsWindowCount = 0;
      this.fpsWindowStart = now;
    }
  }

  private cleanupDecoder(): void {
    if (this.decoder) {
      try {
        if (this.decoder.state !== 'closed') {
          this.decoder.close();
        }
      } catch {
        // ignore errors during cleanup
      }
      this.decoder = null;
      this.decoderCodecString = null;
    }
  }
}
