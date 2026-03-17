'use client';

import { useState } from 'react';
import EV3StatusPanel from '@/components/EV3StatusPanel';
import MapVisualization from '@/components/MapVisualization';
import CameraView from '@/components/CameraView';
import VehicleControls from '@/components/VehicleControls';
import TurretControls from '@/components/TurretControls';
import SpeechControls from '@/components/SpeechControls';
import ConnectionTest from '@/components/ConnectionTest';

export default function Home() {
  const [isCameraExpanded, setIsCameraExpanded] = useState(false);

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      <header className="bg-gray-800 border-b border-gray-700 p-4">
        <div className="max-w-full mx-auto">
          <h1 className="text-2xl font-bold text-blue-400">WRACK Control Center</h1>
          <p className="text-gray-400 text-sm mt-1">EV3 Mindstorms Device Management</p>
        </div>
      </header>

      <main className="flex h-[calc(100vh-80px)]">
        {/* Left Panel - EV3 Device Status */}
        <div className="w-1/2 bg-gray-800 border-r border-gray-700 p-6 overflow-y-auto space-y-4">
          <ConnectionTest />
          <EV3StatusPanel />
          <SpeechControls />
        </div>

        {/* Right Panel - Map and Controls */}
        <div className="w-1/2 flex flex-col">
          {/* Map Section */}
          <div className={`${isCameraExpanded ? 'h-1/2' : 'flex-1'} bg-gray-900 transition-all duration-300`}>
            <MapVisualization />
          </div>

          {/* Camera Section (Expandable) */}
          {isCameraExpanded && (
            <div className="h-1/2 bg-gray-800 border-t border-gray-700">
              <CameraView 
                onClose={() => setIsCameraExpanded(false)} 
                isExpanded={true}
              />
            </div>
          )}

          {/* Controls Section */}
          <div className="bg-gray-800 border-t border-gray-700 p-4">
            <div className="flex justify-between items-start space-x-6">
              {/* Camera Toggle Button */}
              <button
                onClick={() => setIsCameraExpanded(!isCameraExpanded)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isCameraExpanded 
                    ? 'bg-red-600 hover:bg-red-700 text-white' 
                    : 'bg-blue-600 hover:bg-blue-700 text-white'
                }`}
              >
                {isCameraExpanded ? 'Hide Camera' : 'Show Camera'}
              </button>

              {/* Vehicle Controls */}
              <div className="flex-1 max-w-xs">
                <VehicleControls />
              </div>

              {/* Turret Controls */}
              <div className="flex-1 max-w-xs">
                <TurretControls />
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
