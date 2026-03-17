# WRACK Control Center - Claude Code Context

## Project Summary

**WRACK Control Center** is a web-based control application for LEGO Mindstorms EV3 robots. It provides real-time device control, sensor monitoring, terrain mapping, and camera integration through Google Cloud Functions.

**Repository**: https://github.com/rkuklins/mindstorms-cloud-controller

## Quick Start

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build
```

**Local Development**: http://localhost:3000

## Technology Stack

### Frontend
- **Framework**: Next.js 15 (App Router) with React 19
- **Language**: TypeScript 5
- **Styling**: Tailwind CSS 4
- **State**: Zustand
- **UI**: Headless UI + Heroicons
- **Notifications**: React Hot Toast
- **Mapping**: Leaflet + React-Leaflet
- **Charts**: Recharts
- **Video**: HLS.js

### Backend
- **Platform**: Google Cloud Functions (Gen2, Node.js 20)
- **Region**: europe-central2
- **Project**: wrack-control
- **Device Protocol**: TCP Socket to EV3 (178.183.200.201:27700)
- **Authentication**: API Key (X-API-Key header)

## Architecture

```
Web App ←→ GCP Cloud Functions ←→ EV3 Device
        (HTTP REST)           (TCP Socket)
```

**Supported Commands**: forward, backward, left, right, stop, turret_left, turret_right, stop_turret, get_status

## Project Structure

```
src/
├── app/
│   ├── page.tsx              # Main dashboard
│   ├── layout.tsx            # Root layout
│   └── globals.css           # Global styles
├── components/
│   ├── EV3StatusPanel.tsx    # Device monitoring
│   ├── VehicleControls.tsx   # Movement controls
│   ├── TurretControls.tsx    # Turret operations
│   ├── MapVisualization.tsx  # Terrain mapping
│   ├── CameraView.tsx        # Video streaming
│   └── ConnectionTest.tsx    # GCP connectivity
└── lib/
    └── robot-api.ts          # GCP API client
```

## Environment Variables

Required in `.env.local`:

```bash
NEXT_PUBLIC_GCP_FUNCTION_URL=https://europe-central2-wrack-control.cloudfunctions.net/controlRobot
NEXT_PUBLIC_API_KEY=abc123def456ghi789jkl012mno345pq
NEXT_PUBLIC_GCP_PROJECT_ID=wrack-control
NEXT_PUBLIC_GCP_REGION=europe-central2
```

## Current Status

### Completed Features
- ✅ Responsive 50/50 split layout (status panels | map & controls)
- ✅ Dark theme UI with expandable panels
- ✅ Vehicle movement controls with speed adjustment (10-100%)
- ✅ Turret control with rotation and duration settings
- ✅ Emergency stop functionality
- ✅ Real-time EV3 status monitoring (battery, CPU, temperature, ports)
- ✅ Interactive Leaflet map with vehicle tracking and trail visualization
- ✅ Toast notifications for user feedback
- ✅ GCP connection testing
- ✅ Camera view placeholder with HLS.js integration

### Key Components

**Device Control**
- Movement: Forward, backward, left, right
- Speed: 10-100% adjustable
- Emergency stop: Immediate halt
- Turret: Left/right rotation with duration control

**Monitoring**
- EV3 Brick: Battery, CPU, temperature, IP, firmware
- Motor Ports: A-D connection status
- Sensor Ports: 1-4 real-time readings
- Connection: GCP function connectivity test

**Visualization**
- Interactive map with satellite/terrain modes
- Real-time vehicle position and heading
- Path history trail
- Terrain points (obstacles and clear areas)

## Data Models

### Device State
```typescript
interface DeviceState {
  id: string;
  status: 'online' | 'offline' | 'error' | 'scanning';
  position: { lat: number; lng: number; heading: number };
  battery: { level: number; voltage: number; charging: boolean };
  sensors: { temperature: number; humidity: number; pressure: number };
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

## Development Guidelines

### Code Standards
- **TypeScript**: All components must be typed
- **ESLint**: Code must pass linting
- **Commits**: Use conventional commit messages (feat:, fix:, docs:, etc.)
- **Components**: Keep components focused and reusable

### Common Tasks

**Adding a new control command**:
1. Add command type to `lib/robot-api.ts`
2. Create/update control component in `components/`
3. Add UI button/control in appropriate panel
4. Update GCP function if needed

**Adding sensor data visualization**:
1. Update data types in `types/`
2. Add chart component using Recharts
3. Integrate into `EV3StatusPanel.tsx`
4. Connect to real-time data source

### Testing
```bash
# Lint code
npm run lint

# Type check
npm run type-check

# Test GCP connection
# Use Connection Test panel in UI
```

## Known Limitations

- 🌐 **CORS**: Currently localhost-only
- 🔑 **API Key**: Placeholder key in use
- 📱 **Mobile**: Not fully optimized for small screens
- 🎥 **Camera**: Placeholder implementation
- 🗄️ **Storage**: No long-term data persistence

## Immediate Priorities

1. **Security**: Generate secure API key, production CORS
2. **Real Testing**: Test with actual EV3 device
3. **Mobile**: Optimize responsive layout
4. **Camera**: Implement HLS streaming
5. **Mapping**: Add GPS integration and data persistence

## GCP Deployment

```bash
# Deploy control function
gcloud functions deploy controlRobot \
  --gen2 \
  --runtime nodejs20 \
  --trigger-http \
  --allow-unauthenticated \
  --source=. \
  --entry-point=controlRobot \
  --region=europe-central2 \
  --set-env-vars API_KEY=your-key,ROBOT_HOST=ip,ROBOT_PORT=27700
```

## Troubleshooting

**Port 3000 in use**:
```bash
lsof -ti:3000 | xargs kill -9
# or
npm run dev -- -p 3001
```

**Environment variables not loading**:
- Ensure `.env.local` exists in project root
- Restart dev server after changes
- Variables must start with `NEXT_PUBLIC_` for client-side

**Module errors**:
```bash
rm -rf node_modules package-lock.json
npm install
```

**TypeScript errors**:
```bash
rm -rf .next
npm run dev
```

## Performance

- **Load Time**: ~2 seconds
- **Command Latency**: ~200-500ms
- **Update Interval**: 2-5 seconds
- **Memory**: ~50MB browser

## Security

**Current**: API Key auth, CORS protection, rate limiting, input validation

**Needed**: HTTPS enforcement, JWT tokens, user authentication, audit logging

## Contact

- **Developer**: Rafal Kuklinski
- **GCP Project**: wrack-control
- **Repository**: Local development

---

*Version: 0.1.0 - Functional Prototype*
*Last Updated: 2025-10-04*
