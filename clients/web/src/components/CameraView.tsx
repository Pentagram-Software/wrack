'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { XMarkIcon, PlayIcon, PauseIcon, CameraIcon, SignalIcon } from '@heroicons/react/24/solid';
import { WebSocketVideoClient, VideoStreamState, VideoStreamStats } from '@/lib/videoStream';

// Default bridge URL — override with NEXT_PUBLIC_WS_BRIDGE_URL in .env.local
const DEFAULT_WS_URL =
  process.env.NEXT_PUBLIC_WS_BRIDGE_URL ?? 'ws://localhost:8765';

interface CameraViewProps {
  onClose: () => void;
  isExpanded: boolean;
  /** Override the WebSocket bridge URL (useful for testing). */
  wsBridgeUrl?: string;
}

export default function CameraView({
  onClose,
  isExpanded,
  wsBridgeUrl = DEFAULT_WS_URL,
}: CameraViewProps) {
  const [isStreaming, setIsStreaming] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<VideoStreamState>('idle');
  const [stats, setStats] = useState<VideoStreamStats>({
    fps: 0,
    framesReceived: 0,
    framesDecoded: 0,
    codec: null,
  });
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const clientRef = useRef<WebSocketVideoClient | null>(null);

  // ─── Canvas ref callback ───────────────────────────────────────────────────
  // Keep the canvas element in sync with the video client.
  const canvasCallbackRef = useCallback((node: HTMLCanvasElement | null) => {
    canvasRef.current = node;
  }, []);

  // ─── Stream lifecycle ──────────────────────────────────────────────────────

  const startStream = useCallback(() => {
    if (clientRef.current) return; // already running

    const client = new WebSocketVideoClient({
      url: wsBridgeUrl,
      canvas: canvasRef.current ?? undefined,
      onStateChange: (state) => {
        setConnectionStatus(state);
        if (state === 'connected') setErrorMessage(null);
      },
      onError: (err) => {
        setErrorMessage(err.message);
      },
      onFrame: (s) => {
        setStats(s);
      },
    });

    clientRef.current = client;
    client.connect();
  }, [wsBridgeUrl]);

  const stopStream = useCallback(() => {
    clientRef.current?.disconnect();
    clientRef.current = null;
    setConnectionStatus('idle');
    setStats({ fps: 0, framesReceived: 0, framesDecoded: 0, codec: null });
    setErrorMessage(null);

    // Clear canvas
    const canvas = canvasRef.current;
    if (canvas) {
      const ctx = canvas.getContext('2d');
      ctx?.clearRect(0, 0, canvas.width, canvas.height);
    }
  }, []);

  // ─── Toggle handler ────────────────────────────────────────────────────────

  const toggleStream = () => {
    if (isStreaming) {
      setIsStreaming(false);
      stopStream();
    } else {
      setIsStreaming(true);
      startStream();
    }
  };

  // Disconnect when component unmounts
  useEffect(() => {
    return () => {
      clientRef.current?.disconnect();
      clientRef.current = null;
    };
  }, []);

  // ─── Status helpers ────────────────────────────────────────────────────────

  const getStatusColor = (): string => {
    switch (connectionStatus) {
      case 'connected': return 'text-green-400';
      case 'connecting': return 'text-yellow-400';
      case 'error': return 'text-red-400';
      default: return 'text-gray-400';
    }
  };

  const getStatusDot = (): string => {
    switch (connectionStatus) {
      case 'connected': return 'bg-green-500';
      case 'connecting': return 'bg-yellow-500 animate-pulse';
      case 'error': return 'bg-red-500';
      default: return 'bg-gray-500';
    }
  };

  const getStatusLabel = (): string => {
    switch (connectionStatus) {
      case 'idle': return 'Idle';
      case 'connecting': return 'Connecting…';
      case 'connected': return 'Live';
      case 'error': return 'Error';
      case 'disconnected': return 'Disconnected';
    }
  };

  const isConnecting = connectionStatus === 'connecting';
  const isConnected = connectionStatus === 'connected';
  const hasError = connectionStatus === 'error';

  return (
    <div className="h-full flex flex-col bg-gray-800">
      {/* Header */}
      <div className="bg-gray-700 border-b border-gray-600 p-3 flex justify-between items-center">
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2">
            <CameraIcon className="w-5 h-5 text-blue-400" />
            <h3 className="text-lg font-semibold text-white">Camera Feed</h3>
          </div>

          <div className="flex items-center space-x-2">
            <div className={`w-2 h-2 rounded-full ${getStatusDot()}`} />
            <span className={`text-sm ${getStatusColor()}`}>
              {getStatusLabel()}
            </span>
          </div>

          {isConnected && stats.fps > 0 && (
            <div className="flex items-center space-x-1 text-xs text-gray-400">
              <SignalIcon className="w-3 h-3" />
              <span>{stats.fps} fps</span>
              {stats.codec && (
                <span className="uppercase text-gray-500">{stats.codec}</span>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={toggleStream}
            className={`px-3 py-1 rounded text-sm font-medium flex items-center space-x-1 transition-colors ${
              isStreaming
                ? 'bg-red-600 hover:bg-red-700 text-white'
                : 'bg-green-600 hover:bg-green-700 text-white'
            }`}
          >
            {isStreaming ? (
              <>
                <PauseIcon className="w-4 h-4" />
                <span>Stop</span>
              </>
            ) : (
              <>
                <PlayIcon className="w-4 h-4" />
                <span>Start</span>
              </>
            )}
          </button>

          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-gray-600 text-gray-400 hover:text-white transition-colors"
          >
            <XMarkIcon className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Video area */}
      <div className="flex-1 relative bg-black overflow-hidden">
        {/* Canvas — always mounted so the ref is available before connect() */}
        <canvas
          ref={canvasCallbackRef}
          className={`w-full h-full object-contain ${isConnected ? 'block' : 'hidden'}`}
          data-testid="video-canvas"
        />

        {/* Idle overlay */}
        {!isStreaming && (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-gray-400">
            <CameraIcon className="w-16 h-16 mb-4 text-gray-600" />
            <h4 className="text-lg font-medium mb-2">Camera Feed Disabled</h4>
            <p className="text-sm text-center max-w-md px-4">
              Click &ldquo;Start&rdquo; to begin streaming. Make sure the
              WebSocket bridge is running and the Raspberry Pi is streaming
              video.
            </p>
          </div>
        )}

        {/* Connecting overlay */}
        {isConnecting && (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-gray-400">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400 mb-4" />
            <h4 className="text-lg font-medium mb-2">Connecting…</h4>
            <p className="text-sm text-gray-500">{wsBridgeUrl}</p>
          </div>
        )}

        {/* Error overlay */}
        {hasError && (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-gray-400 px-4">
            <div className="w-12 h-12 rounded-full bg-red-900 flex items-center justify-center mb-4">
              <XMarkIcon className="w-6 h-6 text-red-400" />
            </div>
            <h4 className="text-lg font-medium mb-2 text-red-400">Connection Error</h4>
            {errorMessage && (
              <p className="text-sm text-center text-gray-400 max-w-sm">{errorMessage}</p>
            )}
            <button
              onClick={toggleStream}
              className="mt-4 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm transition-colors"
            >
              Retry
            </button>
          </div>
        )}

        {/* Live badge */}
        {isConnected && (
          <div className="absolute bottom-4 left-4 right-4 pointer-events-none">
            <div className="flex justify-between items-center">
              <div className="flex items-center space-x-2 bg-black bg-opacity-50 rounded px-2 py-1">
                <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse" />
                <span className="text-white text-xs font-medium">LIVE</span>
              </div>

              <div className="bg-black bg-opacity-50 rounded px-2 py-1 text-xs text-gray-300">
                {stats.framesDecoded} frames
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Footer stats */}
      <div className="bg-gray-700 border-t border-gray-600 p-2">
        <div className="flex justify-between items-center text-xs text-gray-400">
          <div className="flex space-x-4">
            <span>Resolution: 640×480</span>
            {isExpanded && <span>Target: 30 FPS</span>}
          </div>
          {isConnected && (
            <span className="text-green-400">
              {stats.fps} fps · {stats.codec?.toUpperCase() ?? '—'}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
