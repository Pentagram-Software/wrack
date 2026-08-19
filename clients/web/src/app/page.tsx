'use client';

import { useState } from 'react';
import EV3StatusPanel from '@/components/EV3StatusPanel';
import MapVisualization from '@/components/MapVisualization';
import CameraView from '@/components/CameraView';
import VehicleControls from '@/components/VehicleControls';
import TurretControls from '@/components/TurretControls';
import SpeechControls from '@/components/SpeechControls';
import ConnectionTest from '@/components/ConnectionTest';
import { ThemeToggle } from '@/components/ThemeToggle';
import UserMenu from '@/components/UserMenu';
import AuthGuard from '@/components/AuthGuard';

export default function Home() {
  const [isCameraExpanded, setIsCameraExpanded] = useState(false);

  return (
    <div className="min-h-screen bg-background text-on-background">
      <header className="bg-surface-container-high border-b border-outline-variant p-4">
        <div className="max-w-full mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-primary">WRACK Control Center</h1>
            <p className="text-on-surface-variant text-sm mt-1">EV3 Mindstorms Device Management</p>
          </div>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <UserMenu />
          </div>
        </div>
      </header>

      <main className="flex h-[calc(100vh-80px)]">
        {/* Left Panel - EV3 Device Status */}
        <div className="w-1/2 bg-surface-container border-r border-outline-variant p-6 overflow-y-auto space-y-4">
          <AuthGuard permission="VIEW_STATUS">
            <ConnectionTest />
            <EV3StatusPanel />
          </AuthGuard>
          <AuthGuard permission="CONTROL_EV3">
            <SpeechControls />
          </AuthGuard>
        </div>

        {/* Right Panel - Map and Controls */}
        <div className="w-1/2 flex flex-col">
          {/* Map Section */}
          <div className={`${isCameraExpanded ? 'h-1/2' : 'flex-1'} bg-background transition-all duration-300`}>
            <MapVisualization />
          </div>

          {/* Camera Section (Expandable) */}
          {isCameraExpanded && (
            <div className="h-1/2 bg-surface-container border-t border-outline-variant">
              <AuthGuard permission="STREAM_VIDEO">
                <CameraView 
                  onClose={() => setIsCameraExpanded(false)} 
                  isExpanded={true}
                />
              </AuthGuard>
            </div>
          )}

          {/* Controls Section */}
          <div className="bg-surface-container-high border-t border-outline-variant p-4">
            <div className="flex justify-between items-start space-x-6">
              {/* Camera Toggle Button */}
              <AuthGuard permission="STREAM_VIDEO" fallback={null}>
                <button
                  onClick={() => setIsCameraExpanded(!isCameraExpanded)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isCameraExpanded 
                      ? 'bg-error text-on-error hover:opacity-90' 
                      : 'bg-primary text-on-primary hover:opacity-90'
                  }`}
                >
                  {isCameraExpanded ? 'Hide Camera' : 'Show Camera'}
                </button>
              </AuthGuard>

              {/* Vehicle Controls */}
              <div className="flex-1 max-w-xs">
                <AuthGuard permission="CONTROL_EV3">
                  <VehicleControls />
                </AuthGuard>
              </div>

              {/* Turret Controls */}
              <div className="flex-1 max-w-xs">
                <AuthGuard permission="CONTROL_EV3">
                  <TurretControls />
                </AuthGuard>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
