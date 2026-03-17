'use client';

import { useState, useRef, useEffect } from 'react';
import { XMarkIcon, PlayIcon, PauseIcon, CameraIcon } from '@heroicons/react/24/solid';

interface CameraViewProps {
  onClose: () => void;
  isExpanded: boolean;
}

export default function CameraView({ onClose, isExpanded }: CameraViewProps) {
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamUrl, setStreamUrl] = useState<string>('');
  const [connectionStatus, setConnectionStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected');
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (isStreaming && videoRef.current) {
      setConnectionStatus('connecting');
      
      setTimeout(() => {
        setConnectionStatus('connected');
        if (videoRef.current) {
          videoRef.current.src = '/api/placeholder/640/480';
        }
      }, 2000);
    } else {
      setConnectionStatus('disconnected');
    }
  }, [isStreaming]);

  const toggleStream = () => {
    setIsStreaming(!isStreaming);
  };

  const getStatusColor = () => {
    switch (connectionStatus) {
      case 'connected': return 'text-green-400';
      case 'connecting': return 'text-yellow-400';
      case 'disconnected': return 'text-red-400';
      default: return 'text-gray-400';
    }
  };

  const getStatusDot = () => {
    switch (connectionStatus) {
      case 'connected': return 'bg-green-500';
      case 'connecting': return 'bg-yellow-500 animate-pulse';
      case 'disconnected': return 'bg-red-500';
      default: return 'bg-gray-500';
    }
  };

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
              {connectionStatus}
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
            className="p-1 rounded hover:bg-gray-600 text-gray-400 hover:text-white transition-colors"
          >
            <XMarkIcon className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Camera Content */}
      <div className="flex-1 relative bg-black">
        {!isStreaming ? (
          <div className="h-full flex flex-col items-center justify-center text-gray-400">
            <CameraIcon className="w-16 h-16 mb-4 text-gray-600" />
            <h4 className="text-lg font-medium mb-2">Camera Feed Disabled</h4>
            <p className="text-sm text-center max-w-md">
              Click "Start" to begin streaming from the EV3 camera. 
              Make sure the camera is connected to the device.
            </p>
          </div>
        ) : connectionStatus === 'connecting' ? (
          <div className="h-full flex flex-col items-center justify-center text-gray-400">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400 mb-4"></div>
            <h4 className="text-lg font-medium mb-2">Connecting to Camera</h4>
            <p className="text-sm">Establishing connection with EV3 device...</p>
          </div>
        ) : (
          <div className="h-full relative">
            {/* Placeholder for actual video stream */}
            <div className="h-full bg-gradient-to-br from-gray-800 to-gray-900 flex items-center justify-center">
              <div className="text-center text-gray-400">
                <div className="w-32 h-24 bg-gray-700 rounded mb-4 mx-auto flex items-center justify-center">
                  <CameraIcon className="w-8 h-8" />
                </div>
                <p className="text-sm">Camera feed will appear here</p>
                <p className="text-xs text-gray-500 mt-1">
                  Future: HLS video stream from EV3
                </p>
              </div>
            </div>

            {/* Video overlay controls */}
            <div className="absolute bottom-4 left-4 right-4">
              <div className="bg-black bg-opacity-50 rounded p-2 flex justify-between items-center">
                <div className="flex items-center space-x-2 text-white text-sm">
                  <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse"></div>
                  <span>LIVE</span>
                </div>
                
                <div className="flex space-x-2">
                  <button className="px-2 py-1 bg-white bg-opacity-20 rounded text-white text-xs hover:bg-opacity-30 transition-colors">
                    Snapshot
                  </button>
                  <button className="px-2 py-1 bg-white bg-opacity-20 rounded text-white text-xs hover:bg-opacity-30 transition-colors">
                    Fullscreen
                  </button>
                </div>
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
            {connectionStatus === 'connected' && <span>Latency: ~200ms</span>}
          </div>
        </div>
      </div>
    </div>
  );
}