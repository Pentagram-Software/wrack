# WRACK Control Center - Design & Architecture

## Overview
Web-based control center for WRACK device with real-time monitoring, terrain mapping, and device control capabilities. Leverages existing mobile app infrastructure with Google Cloud Functions.

## Technology Stack

### Frontend
- **Framework**: Next.js 15 with React 19
- **Styling**: Tailwind CSS 4
- **Language**: TypeScript
- **State Management**: Zustand
- **UI Components**: Headless UI + Heroicons
- **Notifications**: React Hot Toast

### Visualization
- **Charts**: Recharts (sensor data, real-time plots)
- **Mapping**: Leaflet + React-Leaflet (terrain visualization)
- **Video Streaming**: HLS.js (future camera integration)

### Backend Integration
- **Device Control**: Google Cloud Functions (reuse existing from mobile app)
- **Real-time Data**: Socket.io-client + WebSockets
- **Cloud Storage**: Google Cloud Storage (map data, images)
- **IoT Management**: Google Cloud IoT Core

## Project Structure

```
src/
├── app/                    # Next.js App Router
│   ├── page.tsx           # Main dashboard
│   ├── layout.tsx         # Root layout
│   └── globals.css        # Global styles
├── components/
│   ├── DeviceControls/    # Movement controls, device actions
│   │   ├── index.tsx
│   │   ├── MovementPanel.tsx
│   │   ├── ActionButtons.tsx
│   │   └── EmergencyStop.tsx
│   ├── SensorDashboard/   # Real-time sensor data visualization
│   │   ├── index.tsx
│   │   ├── TemperatureChart.tsx
│   │   ├── BatteryGauge.tsx
│   │   └── SensorGrid.tsx
│   ├── MapVisualization/  # Terrain scanning and mapping
│   │   ├── index.tsx
│   │   ├── TerrainMap.tsx
│   │   ├── ScanOverlay.tsx
│   │   └── PathTracker.tsx
│   ├── CameraView/        # Video streaming (future)
│   │   ├── index.tsx
│   │   ├── StreamPlayer.tsx
│   │   └── CameraControls.tsx
│   ├── ConnectionStatus/  # GCP and device connectivity
│   │   ├── index.tsx
│   │   └── StatusIndicator.tsx
│   └── shared/            # Reusable components
│       ├── Button.tsx
│       ├── Card.tsx
│       └── LoadingSpinner.tsx
├── lib/
│   ├── gcp-client.ts      # Google Cloud Functions API client
│   ├── device-api.ts      # Device control API wrapper
│   ├── websocket.ts       # Real-time WebSocket connection
│   ├── utils.ts           # General utilities
│   └── constants.ts       # App constants
├── stores/
│   ├── device-store.ts    # Device state management
│   ├── sensor-store.ts    # Sensor data state
│   └── ui-store.ts        # UI state (active tabs, modals)
├── types/
│   ├── device.ts          # Device-related types
│   ├── sensor.ts          # Sensor data types
│   └── api.ts             # API response types
└── hooks/
    ├── useDeviceControl.ts
    ├── useSensorData.ts
    └── useWebSocket.ts
```

## Communication Architecture

### Current Setup (Mobile App Pattern)
```
Mobile App ──HTTP──→ Cloud Functions ──IoT Core──→ WRACK Device
Web App   ──HTTP──→       ↑ (reuse)              →      ↑
```

### Enhanced Web App Communication

#### 1. Device Control (Immediate)
```
Web Control Panel → Cloud Function → IoT Core → WRACK Device
                    ↓
               Response/Status
```

**API Endpoints** (reuse existing):
- `POST /controlDevice` - Movement commands (forward, backward, turn)
- `POST /deviceAction` - Actions (start scan, stop, emergency)
- `GET /deviceStatus` - Current device state

#### 2. Sensor Data (Real-time)
```
WRACK Device → IoT Core → Cloud Function → WebSocket/SSE → Web App
             → Cloud Storage (historical data)
```

**Data Flow**:
- Device publishes sensor readings
- Cloud Function processes and stores
- Real-time updates via WebSocket
- Historical data from Cloud Storage

#### 3. Terrain Mapping (Persistent)
```
WRACK Device → Scan Data → Cloud Storage ← Web App (display)
             → GPS coords → Cloud Storage ← Web App (mapping)
```

**Map Data Structure**:
```json
{
  "scanId": "unique-id",
  "timestamp": "2024-01-01T12:00:00Z",
  "position": {"lat": 52.520, "lng": 13.405},
  "scanData": {
    "points": [...],
    "obstacles": [...],
    "terrain": "..."
  }
}
```

## Environment Configuration

### Required Environment Variables
```bash
# Google Cloud Project
GOOGLE_CLOUD_PROJECT_ID=your-project-id
GOOGLE_CLOUD_REGION=your-region

# Cloud Functions (reuse from mobile app)
NEXT_PUBLIC_DEVICE_CONTROL_URL=https://region-project.cloudfunctions.net/controlDevice
NEXT_PUBLIC_SENSOR_DATA_URL=https://region-project.cloudfunctions.net/getSensorData
NEXT_PUBLIC_MAP_DATA_URL=https://region-project.cloudfunctions.net/getMapData

# Real-time Communication
NEXT_PUBLIC_WEBSOCKET_URL=wss://your-websocket-endpoint
NEXT_PUBLIC_SOCKET_IO_URL=http://your-socket-server

# Cloud Storage
NEXT_PUBLIC_STORAGE_BUCKET=your-storage-bucket
```

## Data Models

### Device State
```typescript
interface DeviceState {
  id: string;
  status: 'online' | 'offline' | 'error' | 'scanning';
  position: {
    lat: number;
    lng: number;
    heading: number;
  };
  battery: {
    level: number;
    voltage: number;
    charging: boolean;
  };
  sensors: {
    temperature: number;
    humidity: number;
    pressure: number;
  };
  lastUpdate: Date;
}
```

### Command Structure
```typescript
interface DeviceCommand {
  type: 'movement' | 'action' | 'config';
  command: string;
  parameters?: Record<string, any>;
  timestamp: Date;
  sessionId: string;
}
```

### Terrain Data
```typescript
interface TerrainScan {
  id: string;
  timestamp: Date;
  position: Coordinates;
  scanData: {
    points: Point3D[];
    obstacles: Obstacle[];
    surfaceType: string;
  };
  processed: boolean;
}
```

## Implementation Phases

### Phase 1: Basic Control Interface
- [ ] Device connection status
- [ ] Basic movement controls (forward, backward, turn)
- [ ] Emergency stop functionality
- [ ] Real-time device status display

### Phase 2: Sensor Dashboard
- [ ] Real-time sensor data visualization
- [ ] Battery and system status
- [ ] Data logging and history
- [ ] Alert system for critical values

### Phase 3: Terrain Mapping
- [ ] Map visualization with Leaflet
- [ ] Display scan data overlays
- [ ] Path tracking and history
- [ ] Obstacle detection visualization

### Phase 4: Advanced Features
- [ ] Camera stream integration
- [ ] Advanced mapping tools
- [ ] Data export capabilities
- [ ] Multi-device support

## Development Commands

```bash
# Development
npm run dev          # Start development server (localhost:3000)
npm run build        # Build for production
npm run start        # Start production server
npm run lint         # Run ESLint
npm run type-check   # TypeScript checking

# Deployment
npm run deploy       # Deploy to cloud platform
```

## Security Considerations

- **API Authentication**: Use service account keys for GCP
- **Environment Variables**: Never commit secrets to repository
- **CORS Configuration**: Restrict origins for production
- **Rate Limiting**: Implement for device control endpoints
- **Input Validation**: Validate all commands before sending to device
- **Secure WebSocket**: Use WSS in production

## Future Enhancements

### Camera Integration
- HLS video streaming
- Multiple camera angles
- Recording capabilities
- Real-time image analysis

### Advanced Analytics
- Machine learning for terrain analysis
- Predictive maintenance
- Performance optimization
- Historical data analysis

### Multi-Device Support
- Device fleet management
- Coordinated scanning missions
- Load balancing
- Centralized monitoring

## Dependencies Summary

### Production Dependencies
```json
{
  "next": "15.5.0",
  "react": "19.1.0",
  "react-dom": "19.1.0",
  "typescript": "^5",
  "tailwindcss": "^4",
  "socket.io-client": "^4.8.1",
  "react-leaflet": "^5.0.0",
  "leaflet": "^1.9.4",
  "@types/leaflet": "^1.9.20",
  "recharts": "^3.1.2",
  "@google-cloud/storage": "^7.17.0",
  "@google-cloud/iot": "^5.2.0",
  "@headlessui/react": "^2.2.7",
  "@heroicons/react": "^2.2.0",
  "zustand": "^5.0.8",
  "react-hot-toast": "^2.6.0",
  "date-fns": "^4.1.0",
  "hls.js": "^1.6.10"
}
```

### Development Dependencies
```json
{
  "@types/node": "^20",
  "@types/react": "^19",
  "@types/react-dom": "^19",
  "eslint": "^9",
  "eslint-config-next": "15.5.0"
}
```