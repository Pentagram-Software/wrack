'use client';

import { useEffect, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { MapIcon, GlobeAltIcon } from '@heroicons/react/24/solid';

const Map = dynamic(() => import('./Map'), {
  ssr: false,
  loading: () => (
    <div className="h-full flex items-center justify-center bg-gray-800">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400 mx-auto mb-2"></div>
        <p className="text-gray-400">Loading map...</p>
      </div>
    </div>
  )
});

interface TerrainPoint {
  id: string;
  lat: number;
  lng: number;
  type: 'obstacle' | 'clear' | 'unknown' | 'scanned';
  timestamp: Date;
  elevation?: number;
}

interface VehiclePosition {
  lat: number;
  lng: number;
  heading: number;
  speed: number;
  timestamp: Date;
}

export default function MapVisualization() {
  const [vehiclePosition, setVehiclePosition] = useState<VehiclePosition>({
    lat: 52.520008,
    lng: 13.404954,
    heading: 45,
    speed: 0,
    timestamp: new Date('2024-01-01T12:00:00')
  });

  const [terrainPoints, setTerrainPoints] = useState<TerrainPoint[]>([
    { id: '1', lat: 52.520008, lng: 13.404954, type: 'scanned', timestamp: new Date('2024-01-01T12:00:00') },
    { id: '2', lat: 52.520108, lng: 13.405054, type: 'obstacle', timestamp: new Date('2024-01-01T12:00:00') },
    { id: '3', lat: 52.519908, lng: 13.404854, type: 'clear', timestamp: new Date('2024-01-01T12:00:00') },
  ]);

  const [mapMode, setMapMode] = useState<'terrain' | 'satellite'>('terrain');
  const [showTrail, setShowTrail] = useState(true);

  useEffect(() => {
    const interval = setInterval(() => {
      setVehiclePosition(prev => ({
        ...prev,
        lat: prev.lat + (Math.random() - 0.5) * 0.0001,
        lng: prev.lng + (Math.random() - 0.5) * 0.0001,
        heading: (prev.heading + (Math.random() - 0.5) * 10) % 360,
        speed: Math.random() * 2,
        timestamp: new Date()
      }));

      if (Math.random() > 0.7) {
        setTerrainPoints(prev => {
          const newPoint: TerrainPoint = {
            id: Date.now().toString(),
            lat: vehiclePosition.lat + (Math.random() - 0.5) * 0.0005,
            lng: vehiclePosition.lng + (Math.random() - 0.5) * 0.0005,
            type: Math.random() > 0.3 ? 'clear' : 'obstacle',
            timestamp: new Date()
          };
          return [...prev.slice(-50), newPoint];
        });
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [vehiclePosition.lat, vehiclePosition.lng]);

  return (
    <div className="h-full flex flex-col bg-gray-800">
      {/* Map Controls Header */}
      <div className="bg-gray-700 border-b border-gray-600 p-3">
        <div className="flex justify-between items-center">
          <div className="flex items-center space-x-4">
            <h3 className="text-lg font-semibold text-white flex items-center space-x-2">
              <MapIcon className="w-5 h-5 text-blue-400" />
              <span>Terrain Map</span>
            </h3>
            
            <div className="flex items-center space-x-2">
              <button
                onClick={() => setMapMode(mapMode === 'terrain' ? 'satellite' : 'terrain')}
                className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                  mapMode === 'satellite' 
                    ? 'bg-green-600 text-white' 
                    : 'bg-gray-600 text-gray-300 hover:bg-gray-500'
                }`}
              >
                <GlobeAltIcon className="w-4 h-4 inline mr-1" />
                {mapMode === 'terrain' ? 'Satellite' : 'Terrain'}
              </button>
              
              <button
                onClick={() => setShowTrail(!showTrail)}
                className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                  showTrail 
                    ? 'bg-blue-600 text-white' 
                    : 'bg-gray-600 text-gray-300 hover:bg-gray-500'
                }`}
              >
                Trail {showTrail ? 'ON' : 'OFF'}
              </button>
            </div>
          </div>

          <div className="text-right text-xs text-gray-400">
            <div>Lat: {vehiclePosition.lat.toFixed(6)}</div>
            <div>Lng: {vehiclePosition.lng.toFixed(6)}</div>
            <div>Heading: {Math.round(vehiclePosition.heading)}°</div>
          </div>
        </div>
      </div>

      {/* Map Container */}
      <div className="flex-1 relative">
        <Map 
          vehiclePosition={vehiclePosition}
          terrainPoints={terrainPoints}
          mapMode={mapMode}
          showTrail={showTrail}
        />
      </div>

      {/* Map Legend */}
      <div className="bg-gray-700 border-t border-gray-600 p-3">
        <div className="flex justify-between items-center text-xs">
          <div className="flex space-x-4">
            <div className="flex items-center space-x-1">
              <div className="w-3 h-3 bg-blue-500 rounded-full"></div>
              <span className="text-gray-300">Vehicle</span>
            </div>
            <div className="flex items-center space-x-1">
              <div className="w-3 h-3 bg-green-500 rounded-full"></div>
              <span className="text-gray-300">Clear ({terrainPoints.filter(p => p.type === 'clear').length})</span>
            </div>
            <div className="flex items-center space-x-1">
              <div className="w-3 h-3 bg-red-500 rounded-full"></div>
              <span className="text-gray-300">Obstacle ({terrainPoints.filter(p => p.type === 'obstacle').length})</span>
            </div>
            <div className="flex items-center space-x-1">
              <div className="w-3 h-3 bg-yellow-500 rounded-full"></div>
              <span className="text-gray-300">Scanned ({terrainPoints.filter(p => p.type === 'scanned').length})</span>
            </div>
          </div>
          
          <div className="text-gray-400">
            Speed: {vehiclePosition.speed.toFixed(1)} m/s
          </div>
        </div>
      </div>
    </div>
  );
}