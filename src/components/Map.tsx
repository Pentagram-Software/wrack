'use client';

import { MapContainer, TileLayer, Marker, CircleMarker, Popup, Polyline } from 'react-leaflet';
import { Icon, LatLngExpression } from 'leaflet';
import { useEffect, useState } from 'react';
import 'leaflet/dist/leaflet.css';

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

interface MapProps {
  vehiclePosition: VehiclePosition;
  terrainPoints: TerrainPoint[];
  mapMode: 'terrain' | 'satellite';
  showTrail: boolean;
}

export default function Map({ vehiclePosition, terrainPoints, mapMode, showTrail }: MapProps) {
  const [vehicleTrail, setVehicleTrail] = useState<LatLngExpression[]>([]);

  useEffect(() => {
    if (showTrail) {
      setVehicleTrail(prev => {
        const newTrail = [...prev, [vehiclePosition.lat, vehiclePosition.lng] as LatLngExpression];
        return newTrail.slice(-100);
      });
    } else {
      setVehicleTrail([]);
    }
  }, [vehiclePosition, showTrail]);

  const vehicleIcon = new Icon({
    iconUrl: 'data:image/svg+xml;base64,' + btoa(`
      <svg width="30" height="30" viewBox="0 0 30 30" fill="none" xmlns="http://www.w3.org/2000/svg">
        <g transform="rotate(${vehiclePosition.heading} 15 15)">
          <path d="M15 5 L25 25 L15 20 L5 25 Z" fill="#3B82F6" stroke="#1E40AF" stroke-width="2"/>
          <circle cx="15" cy="15" r="3" fill="#60A5FA"/>
        </g>
      </svg>
    `),
    iconSize: [30, 30],
    iconAnchor: [15, 15],
    popupAnchor: [0, -15],
  });

  const getPointColor = (type: string) => {
    switch (type) {
      case 'obstacle': return '#EF4444';
      case 'clear': return '#10B981';
      case 'scanned': return '#F59E0B';
      case 'unknown': return '#6B7280';
      default: return '#6B7280';
    }
  };

  const getTileLayerUrl = () => {
    if (mapMode === 'satellite') {
      return 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
    }
    return 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
  };

  return (
    <MapContainer
      center={[vehiclePosition.lat, vehiclePosition.lng]}
      zoom={18}
      style={{ height: '100%', width: '100%' }}
      className="z-0"
    >
      <TileLayer
        url={getTileLayerUrl()}
        attribution={mapMode === 'satellite' ? 
          '&copy; <a href="https://www.esri.com/">Esri</a>' :
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }
      />

      {/* Vehicle Marker */}
      <Marker 
        position={[vehiclePosition.lat, vehiclePosition.lng]} 
        icon={vehicleIcon}
      >
        <Popup>
          <div className="text-sm">
            <div className="font-semibold mb-1">WRACK Vehicle</div>
            <div>Speed: {vehiclePosition.speed.toFixed(1)} m/s</div>
            <div>Heading: {Math.round(vehiclePosition.heading)}°</div>
            <div>Position: {vehiclePosition.lat.toFixed(6)}, {vehiclePosition.lng.toFixed(6)}</div>
            <div>Last Update: {vehiclePosition.timestamp.toLocaleTimeString()}</div>
          </div>
        </Popup>
      </Marker>

      {/* Vehicle Trail */}
      {showTrail && vehicleTrail.length > 1 && (
        <Polyline 
          positions={vehicleTrail} 
          color="#3B82F6" 
          weight={3} 
          opacity={0.7}
        />
      )}

      {/* Terrain Points */}
      {terrainPoints.map((point) => (
        <CircleMarker
          key={point.id}
          center={[point.lat, point.lng]}
          radius={6}
          fillColor={getPointColor(point.type)}
          color={getPointColor(point.type)}
          weight={2}
          opacity={0.8}
          fillOpacity={0.6}
        >
          <Popup>
            <div className="text-sm">
              <div className="font-semibold mb-1">Terrain Point</div>
              <div>Type: <span className="capitalize font-medium">{point.type}</span></div>
              <div>Position: {point.lat.toFixed(6)}, {point.lng.toFixed(6)}</div>
              {point.elevation && <div>Elevation: {point.elevation}m</div>}
              <div>Scanned: {point.timestamp.toLocaleTimeString()}</div>
            </div>
          </Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}