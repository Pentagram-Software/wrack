/**
 * Unit tests for useVideoStream hook.
 *
 * HLS.js performs real network activity and requires a browser media stack.
 * Both are unavailable in jsdom, so the entire hls.js module is mocked.
 * Tests validate state machine transitions and cleanup logic by controlling
 * when the mocked HLS instance fires its lifecycle events.
 */

import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useRef } from 'react';

// ---------------------------------------------------------------------------
// Mock hls.js before importing the hook
// ---------------------------------------------------------------------------

/** Stores the latest mock Hls instance so tests can trigger events. */
let mockHlsInstance: {
  loadSource: Mock;
  attachMedia: Mock;
  on: Mock;
  destroy: Mock;
  _emit: (event: string, data?: unknown) => void;
} | null = null;

let isHlsSupported = true;

vi.mock('hls.js', () => {
  const Events = {
    MANIFEST_PARSED: 'hlsManifestParsed',
    ERROR: 'hlsError',
  };

  class Hls {
    static isSupported() { return isHlsSupported; }
    static get Events() { return Events; }

    private _listeners: Record<string, ((event: string, data?: unknown) => void)[]> = {};

    loadSource = vi.fn();
    attachMedia = vi.fn();
    destroy = vi.fn();

    on(event: string, cb: (event: string, data?: unknown) => void) {
      (this._listeners[event] = this._listeners[event] ?? []).push(cb);
    }

    /** Test helper — fire a registered event listener. */
    _emit(event: string, data?: unknown) {
      (this._listeners[event] ?? []).forEach((cb) => cb(event, data));
    }

    constructor() {
      mockHlsInstance = this as unknown as typeof mockHlsInstance;
    }
  }

  return { default: Hls, Events };
});

// Import after the mock is set up
import { useVideoStream } from './useVideoStream';

// ---------------------------------------------------------------------------
// Helper to create a mock video element
// ---------------------------------------------------------------------------

function makeMockVideo(): HTMLVideoElement {
  const video = document.createElement('video');
  video.play = vi.fn().mockResolvedValue(undefined);
  video.load = vi.fn();
  video.requestFullscreen = vi.fn();
  return video;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

beforeEach(() => {
  mockHlsInstance = null;
  isHlsSupported = true;
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('useVideoStream — initial state', () => {
  it('starts in idle state when url is null', () => {
    const videoRef = { current: makeMockVideo() };
    const { result } = renderHook(() =>
      useVideoStream({ url: null, videoRef }),
    );
    expect(result.current.status).toBe('idle');
    expect(result.current.error).toBeNull();
  });

  it('starts in idle state when videoRef.current is null', () => {
    const videoRef = { current: null };
    const { result } = renderHook(() =>
      useVideoStream({ url: 'http://example.com/stream.m3u8', videoRef }),
    );
    expect(result.current.status).toBe('idle');
    expect(result.current.error).toBeNull();
  });
});

describe('useVideoStream — HLS.js supported path', () => {
  it('transitions to loading immediately when url is set', () => {
    const videoRef = { current: makeMockVideo() };
    const { result } = renderHook(() =>
      useVideoStream({ url: 'http://example.com/stream.m3u8', videoRef }),
    );
    expect(result.current.status).toBe('loading');
  });

  it('calls Hls.loadSource and Hls.attachMedia with the stream URL', () => {
    const videoRef = { current: makeMockVideo() };
    const url = 'http://example.com/live/stream.m3u8';
    renderHook(() => useVideoStream({ url, videoRef }));

    expect(mockHlsInstance?.loadSource).toHaveBeenCalledWith(url);
    expect(mockHlsInstance?.attachMedia).toHaveBeenCalledWith(videoRef.current);
  });

  it('transitions to ready when MANIFEST_PARSED fires', () => {
    const videoRef = { current: makeMockVideo() };
    const { result } = renderHook(() =>
      useVideoStream({ url: 'http://example.com/stream.m3u8', videoRef }),
    );

    act(() => {
      mockHlsInstance?._emit('hlsManifestParsed');
    });

    expect(result.current.status).toBe('ready');
    expect(result.current.error).toBeNull();
  });

  it('calls video.play() after MANIFEST_PARSED', () => {
    const video = makeMockVideo();
    const videoRef = { current: video };
    renderHook(() => useVideoStream({ url: 'http://example.com/stream.m3u8', videoRef }));

    act(() => {
      mockHlsInstance?._emit('hlsManifestParsed');
    });

    expect(video.play).toHaveBeenCalledOnce();
  });

  it('transitions to error on a fatal HLS error', () => {
    const videoRef = { current: makeMockVideo() };
    const { result } = renderHook(() =>
      useVideoStream({ url: 'http://example.com/stream.m3u8', videoRef }),
    );

    act(() => {
      mockHlsInstance?._emit('hlsError', { fatal: true, details: 'networkError' });
    });

    expect(result.current.status).toBe('error');
    expect(result.current.error).toBe('networkError');
  });

  it('does not change state on non-fatal HLS errors', () => {
    const videoRef = { current: makeMockVideo() };
    const { result } = renderHook(() =>
      useVideoStream({ url: 'http://example.com/stream.m3u8', videoRef }),
    );

    act(() => {
      mockHlsInstance?._emit('hlsError', { fatal: false, details: 'fragmentDecryptError' });
    });

    // Should still be 'loading' — non-fatal error does not change state
    expect(result.current.status).toBe('loading');
  });

  it('destroys the Hls instance when the component unmounts', () => {
    const videoRef = { current: makeMockVideo() };
    const { unmount } = renderHook(() =>
      useVideoStream({ url: 'http://example.com/stream.m3u8', videoRef }),
    );
    const capturedInstance = mockHlsInstance;

    unmount();

    expect(capturedInstance?.destroy).toHaveBeenCalledOnce();
  });

  it('destroys the old Hls instance and creates a new one when url changes', () => {
    const videoRef = { current: makeMockVideo() };
    const { rerender } = renderHook(
      ({ url }: { url: string }) => useVideoStream({ url, videoRef }),
      { initialProps: { url: 'http://example.com/stream1.m3u8' } },
    );
    const firstInstance = mockHlsInstance;
    expect(firstInstance).not.toBeNull();

    act(() => {
      rerender({ url: 'http://example.com/stream2.m3u8' });
    });

    expect(firstInstance?.destroy).toHaveBeenCalledOnce();
    expect(mockHlsInstance).not.toBe(firstInstance);
    expect(mockHlsInstance?.loadSource).toHaveBeenCalledWith('http://example.com/stream2.m3u8');
  });

  it('resets to idle and destroys Hls when url becomes null', () => {
    const videoRef = { current: makeMockVideo() };
    const { result, rerender } = renderHook(
      ({ url }: { url: string | null }) => useVideoStream({ url, videoRef }),
      { initialProps: { url: 'http://example.com/stream.m3u8' as string | null } },
    );
    const capturedInstance = mockHlsInstance;

    act(() => {
      rerender({ url: null });
    });

    expect(capturedInstance?.destroy).toHaveBeenCalledOnce();
    expect(result.current.status).toBe('idle');
  });
});

describe('useVideoStream — native HLS path (e.g. Safari)', () => {
  beforeEach(() => {
    isHlsSupported = false;
  });

  function makeNativeHlsVideo(): HTMLVideoElement {
    const video = makeMockVideo();
    // Simulate Safari's native HLS support
    video.canPlayType = vi.fn().mockImplementation((type: string) =>
      type === 'application/vnd.apple.mpegurl' ? 'probably' : '',
    );
    return video;
  }

  it('sets video.src directly and transitions to loading', () => {
    const video = makeNativeHlsVideo();
    const videoRef = { current: video };
    const url = 'http://example.com/stream.m3u8';

    const { result } = renderHook(() => useVideoStream({ url, videoRef }));

    expect(result.current.status).toBe('loading');
    expect(video.src).toContain('stream.m3u8');
    expect(video.load).toHaveBeenCalled();
  });

  it('transitions to ready after loadedmetadata event', () => {
    const video = makeNativeHlsVideo();
    const videoRef = { current: video };
    const { result } = renderHook(() =>
      useVideoStream({ url: 'http://example.com/stream.m3u8', videoRef }),
    );

    act(() => {
      video.dispatchEvent(new Event('loadedmetadata'));
    });

    expect(result.current.status).toBe('ready');
    expect(result.current.error).toBeNull();
  });

  it('transitions to error after video error event', () => {
    const video = makeNativeHlsVideo();
    const videoRef = { current: video };
    const { result } = renderHook(() =>
      useVideoStream({ url: 'http://example.com/stream.m3u8', videoRef }),
    );

    act(() => {
      video.dispatchEvent(new Event('error'));
    });

    expect(result.current.status).toBe('error');
    expect(result.current.error).toBe('Native HLS playback error');
  });

  it('clears video.src on cleanup', () => {
    const video = makeNativeHlsVideo();
    const videoRef = { current: video };
    const { unmount } = renderHook(() =>
      useVideoStream({ url: 'http://example.com/stream.m3u8', videoRef }),
    );

    unmount();

    expect(video.getAttribute('src')).toBe('');
  });
});

describe('useVideoStream — unsupported browser', () => {
  it('immediately sets error status when neither HLS.js nor native HLS is supported', () => {
    isHlsSupported = false;
    const video = makeMockVideo();
    // Simulate a browser where canPlayType returns empty string for HLS
    video.canPlayType = vi.fn().mockReturnValue('');
    const videoRef = { current: video };

    const { result } = renderHook(() =>
      useVideoStream({ url: 'http://example.com/stream.m3u8', videoRef }),
    );

    expect(result.current.status).toBe('error');
    expect(result.current.error).toMatch(/not supported/i);
  });
});
