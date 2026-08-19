'use client';

import { useEffect, useRef, useState, type RefObject } from 'react';
import Hls, { type ErrorData, Events } from 'hls.js';

export type VideoStreamStatus = 'idle' | 'loading' | 'ready' | 'error';

export interface VideoStreamState {
  status: VideoStreamStatus;
  error: string | null;
}

export interface UseVideoStreamOptions {
  /** HLS stream URL, or null to stop/reset the stream. */
  url: string | null;
  /** Ref to the HTMLVideoElement that will receive the stream. */
  videoRef: RefObject<HTMLVideoElement | null>;
}

/**
 * Manages an HLS.js video stream lifecycle attached to a <video> element.
 *
 * Behaviour:
 * - When `url` is null or the video element is not yet mounted → status is 'idle'.
 * - When `url` is set:
 *   - If Hls.isSupported() → attaches an Hls instance and waits for MANIFEST_PARSED
 *     (status transitions idle → loading → ready).
 *   - Else if the browser supports HLS natively (Safari) → sets video.src directly
 *     (status transitions to 'ready' after the `loadedmetadata` event).
 *   - Else → status is 'error' (browser cannot play HLS).
 * - Fatal HLS errors → status is 'error'.
 * - Cleans up (destroys Hls instance, revokes object URLs) on unmount or url change.
 */
export function useVideoStream({ url, videoRef }: UseVideoStreamOptions): VideoStreamState {
  const [state, setState] = useState<VideoStreamState>({ status: 'idle', error: null });
  const hlsRef = useRef<Hls | null>(null);

  useEffect(() => {
    const video = videoRef.current;

    if (!url || !video) {
      setState({ status: 'idle', error: null });
      return;
    }

    setState({ status: 'loading', error: null });

    function destroyHls() {
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
    }

    if (Hls.isSupported()) {
      destroyHls();
      const hls = new Hls();
      hlsRef.current = hls;

      hls.loadSource(url);
      hls.attachMedia(video);

      hls.on(Events.MANIFEST_PARSED, () => {
        setState({ status: 'ready', error: null });
        video.play().catch(() => {
          // Autoplay may be blocked by browser policy — not a fatal error.
          // The user can start playback manually.
        });
      });

      hls.on(Events.ERROR, (_event: Events.ERROR, data: ErrorData) => {
        if (data.fatal) {
          setState({ status: 'error', error: data.details ?? 'HLS fatal error' });
          destroyHls();
        }
      });

      return () => {
        destroyHls();
        setState({ status: 'idle', error: null });
      };
    }

    // Native HLS support (Safari)
    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = url;
      const onLoaded = () => setState({ status: 'ready', error: null });
      const onError = () => setState({ status: 'error', error: 'Native HLS playback error' });

      video.addEventListener('loadedmetadata', onLoaded);
      video.addEventListener('error', onError);
      video.load();

      return () => {
        video.removeEventListener('loadedmetadata', onLoaded);
        video.removeEventListener('error', onError);
        video.src = '';
        setState({ status: 'idle', error: null });
      };
    }

    setState({ status: 'error', error: 'HLS playback is not supported in this browser' });
  }, [url, videoRef]);

  return state;
}
