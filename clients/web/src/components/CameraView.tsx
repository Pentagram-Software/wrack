'use client';

import { useState, useRef } from 'react';
import { XMarkIcon, PlayIcon, PauseIcon, CameraIcon } from '@heroicons/react/24/solid';
import { useVideoStream } from '@/lib/useVideoStream';

interface CameraViewProps {
  onClose: () => void;
  isExpanded: boolean;
  /**
   * HLS stream URL served by a bridge/proxy on the same host.
   * When undefined the component renders a static placeholder.
   */
  streamUrl?: string;
}

export default function CameraView({ onClose, isExpanded: _isExpanded, streamUrl }: CameraViewProps) {
  const [isStreaming, setIsStreaming] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  const activeUrl = isStreaming ? (streamUrl ?? null) : null;
  const { status: connectionStatus, error: streamError } = useVideoStream({
    url: activeUrl,
    videoRef,
  });

  const toggleStream = () => {
    setIsStreaming((prev) => !prev);
  };

  const getStatusColor = () => {
    switch (connectionStatus) {
      case 'ready': return 'text-green-400';
      case 'loading': return 'text-yellow-400';
      case 'error':
      case 'idle': return 'text-red-400';
    }
  };

  const getStatusDot = () => {
    switch (connectionStatus) {
      case 'ready': return 'bg-green-500';
      case 'loading': return 'bg-yellow-500 animate-pulse';
      case 'error':
      case 'idle': return 'bg-red-500';
    }
  };

  const statusLabel = connectionStatus === 'idle' ? 'disconnected' : connectionStatus;

  return (
    <div className="h-full flex flex-col bg-gray-800">
      {/* Camera Header */}
      <div className="bg-gray-700 border-b border-gray-600 p-3 flex justify-between items-center">
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2">
            <CameraIcon className="w-5 h-5 text-blue-400" />
            <h3 className="text-lg font-semibold text-white">Camera Feed</h3>
          </div>

          <div className="flex items-center space-x-2">
            <div className={`w-2 h-2 rounded-full ${getStatusDot()}`} />
            <span className={`text-sm capitalize ${getStatusColor()}`}>
              {statusLabel}
            </span>
          </div>
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
            aria-label="Close camera"
            className="p-1 rounded hover:bg-gray-600 text-gray-400 hover:text-white transition-colors"
          >
            <XMarkIcon className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Camera Content */}
      <div className="flex-1 relative bg-black">
        {/* The video element is always mounted so useVideoStream can attach HLS */}
        <video
          ref={videoRef}
          className={`w-full h-full object-contain ${connectionStatus === 'ready' ? 'block' : 'hidden'}`}
          muted
          playsInline
          aria-label="Camera feed"
        />

        {!isStreaming && (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-gray-400">
            <CameraIcon className="w-16 h-16 mb-4 text-gray-600" />
            <h4 className="text-lg font-medium mb-2">Camera Feed Disabled</h4>
            <p className="text-sm text-center max-w-md">
              Click &ldquo;Start&rdquo; to begin streaming from the EV3 camera.
              Make sure the camera is connected to the device.
            </p>
          </div>
        )}

        {isStreaming && connectionStatus === 'loading' && (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-gray-400">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400 mb-4" />
            <h4 className="text-lg font-medium mb-2">Connecting to Camera</h4>
            <p className="text-sm">Establishing connection with EV3 device&hellip;</p>
          </div>
        )}

        {isStreaming && connectionStatus === 'error' && (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-gray-400">
            <CameraIcon className="w-16 h-16 mb-4 text-red-600" />
            <h4 className="text-lg font-medium mb-2 text-red-400">Stream Error</h4>
            <p className="text-sm text-center max-w-md">
              {streamError ?? 'Unable to connect to the camera stream.'}
            </p>
          </div>
        )}

        {connectionStatus === 'ready' && (
          /* Video overlay controls shown only when stream is live */
          <div className="absolute bottom-4 left-4 right-4 pointer-events-none">
            <div className="bg-black bg-opacity-50 rounded p-2 flex justify-between items-center pointer-events-auto">
              <div className="flex items-center space-x-2 text-white text-sm">
                <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse" />
                <span>LIVE</span>
              </div>

              <div className="flex space-x-2">
                <button
                  onClick={() => {
                    const video = videoRef.current;
                    if (video) {
                      const canvas = document.createElement('canvas');
                      canvas.width = video.videoWidth;
                      canvas.height = video.videoHeight;
                      canvas.getContext('2d')?.drawImage(video, 0, 0);
                      const link = document.createElement('a');
                      link.download = `snapshot-${Date.now()}.png`;
                      link.href = canvas.toDataURL('image/png');
                      link.click();
                    }
                  }}
                  className="px-2 py-1 bg-white bg-opacity-20 rounded text-white text-xs hover:bg-opacity-30 transition-colors"
                >
                  Snapshot
                </button>
                <button
                  onClick={() => videoRef.current?.requestFullscreen()}
                  className="px-2 py-1 bg-white bg-opacity-20 rounded text-white text-xs hover:bg-opacity-30 transition-colors"
                >
                  Fullscreen
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Camera Info */}
      <div className="bg-gray-700 border-t border-gray-600 p-2">
        <div className="flex justify-between items-center text-xs text-gray-400">
          <div className="flex space-x-4">
            <span>Resolution: 640x480</span>
            <span>FPS: 30</span>
            <span>Quality: HD</span>
          </div>
          <div>
            {connectionStatus === 'ready' && <span>Latency: ~200ms</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
