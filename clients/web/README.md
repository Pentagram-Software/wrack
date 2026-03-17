# WRACK Control Center

A modern web-based control center for LEGO Mindstorms EV3 robots, providing real-time device monitoring, sensor visualization, terrain mapping, and remote control capabilities through Google Cloud Functions.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Next.js](https://img.shields.io/badge/Next.js-15.5-black)
![React](https://img.shields.io/badge/React-19.1-blue)
![TypeScript](https://img.shields.io/badge/TypeScript-5-blue)

## Features

- **Real-time Device Control**: Control EV3 vehicle movement and turret operations
- **Live Sensor Monitoring**: Real-time readings from ultrasonic, gyro, and camera sensors
- **Motor Status Tracking**: Monitor all connected motors with angle, speed, and stall detection
- **Interactive Map**: Leaflet-based terrain visualization with vehicle tracking
- **Speech Commands**: Send text-to-speech commands to the EV3 device
- **Battery & System Monitoring**: Track battery level, voltage, CPU usage, and network status
- **Camera Integration**: Expandable camera view (HLS streaming ready)
- **Dark Theme UI**: Professional control room aesthetic with responsive design

## Technology Stack

### Frontend
- **Framework**: Next.js 15 (App Router)
- **UI Library**: React 19
- **Language**: TypeScript 5
- **Styling**: Tailwind CSS 4
- **State Management**: Zustand
- **Mapping**: Leaflet + React-Leaflet
- **Charts**: Recharts
- **Notifications**: React Hot Toast
- **Icons**: Heroicons

### Backend
- **Platform**: Google Cloud Functions (Gen2)
- **Runtime**: Node.js 20
- **Region**: europe-central2
- **Protocol**: HTTP REST API
- **Device Protocol**: TCP Socket to EV3

### Communication Architecture

```
┌─────────────┐      HTTP/REST      ┌──────────────────┐      TCP Socket      ┌─────────────┐
│  Web App    │ ◄─────────────────► │  GCP Functions   │ ◄──────────────────► │ EV3 Device  │
│ (Next.js)   │   JSON Commands     │  (Node.js 20)    │   Binary Protocol    │ (ev3dev)    │
└─────────────┘                     └──────────────────┘                      └─────────────┘
```

## Project Structure

```
wrack-control-center/
├── src/
│   ├── app/                        # Next.js App Router
│   │   ├── page.tsx               # Main dashboard
│   │   ├── layout.tsx             # Root layout
│   │   └── globals.css            # Global styles
│   ├── components/                # React components
│   │   ├── EV3StatusPanel.tsx    # Device monitoring & sensor display
│   │   ├── VehicleControls.tsx   # Movement controls
│   │   ├── TurretControls.tsx    # Turret operations
│   │   ├── SpeechControls.tsx    # Text-to-speech commands
│   │   ├── MapVisualization.tsx  # Terrain mapping
│   │   ├── CameraView.tsx        # Video streaming
│   │   └── ConnectionTest.tsx    # GCP connectivity testing
│   └── lib/
│       └── robot-api.ts           # GCP API client
├── public/                        # Static assets
├── DESIGN.md                      # Technical architecture
├── NOTION_STATUS.md              # Project status & roadmap
├── CLAUDE.md                     # AI assistant context
└── README.md                     # This file
```

## Getting Started

### Prerequisites

- **Node.js**: Version 18 or higher
- **npm**: Comes with Node.js
- **Google Cloud Account**: For Cloud Functions (optional for local dev)
- **EV3 Device**: Running ev3dev with network connectivity

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/rkuklins/mindstorms-cloud-controller.git
   cd mindstorms-cloud-controller
   ```

2. **Install dependencies**
   ```bash
   npm install
   ```

3. **Configure environment variables**
   ```bash
   cp .env.local.example .env.local
   ```

   Edit `.env.local` with your configuration:
   ```bash
   NEXT_PUBLIC_GCP_FUNCTION_URL=https://europe-central2-YOUR-PROJECT.cloudfunctions.net/controlRobot
   NEXT_PUBLIC_API_KEY=your-secure-api-key-here
   NEXT_PUBLIC_GCP_PROJECT_ID=your-project-id
   NEXT_PUBLIC_GCP_REGION=europe-central2
   ```

4. **Start development server**
   ```bash
   npm run dev
   ```

   Open [http://localhost:3000](http://localhost:3000) in your browser.

### Development Commands

```bash
npm run dev          # Start development server
npm run build        # Build for production
npm run start        # Start production server
npm run lint         # Run ESLint
```

## API Commands

The application communicates with the EV3 device through the following commands:

### Movement Commands
- `forward` - Move forward with speed and optional duration
- `backward` - Move backward
- `left` - Turn left
- `right` - Turn right
- `stop` - Emergency stop

### Turret Commands
- `turret_left` - Rotate turret left
- `turret_right` - Rotate turret right
- `stop_turret` - Stop turret rotation

### System Commands
- `get_status` - Retrieve device status, sensors, motors, battery
- `speak` - Text-to-speech (max 500 characters)

### Example Request

```bash
POST https://europe-central2-wrack-control.cloudfunctions.net/controlRobot

Headers:
  Content-Type: application/json
  X-API-Key: your-api-key

Body:
{
  "command": "forward",
  "params": {
    "speed": 500,
    "duration": 2
  }
}
```

### Example Response

```json
{
  "success": true,
  "command": "get_status",
  "result": {
    "device_info": {
      "battery": {
        "percentage": 89,
        "voltage_v": 7.79
      },
      "cpu_usage_percent": 58,
      "ip_addresses": ["192.168.1.83"],
      "kernel": "Linux 4.14.117-ev3dev-2.3.5-ev3",
      "motors": {
        "drive_L_motor": {
          "available": true,
          "port": "Port.A",
          "angle_degrees": 0,
          "speed_deg_per_sec": 0
        }
      },
      "sensors": {
        "ultrasonic": {
          "available": true,
          "port": "Port.S2",
          "distance_cm": 229.1
        }
      }
    }
  },
  "timestamp": "2025-10-05T11:06:07.683Z"
}
```

## Deployment

### Deploying the Web App

**Vercel (Recommended)**
```bash
npm i -g vercel
vercel
```

**Netlify**
1. Connect GitHub repository to Netlify
2. Configure environment variables in Netlify dashboard
3. Deploy

**Docker**
```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
CMD ["npm", "start"]
```

### Deploying GCP Cloud Functions

```bash
gcloud functions deploy controlRobot \
  --gen2 \
  --runtime nodejs20 \
  --trigger-http \
  --allow-unauthenticated \
  --source=. \
  --entry-point=controlRobot \
  --region=europe-central2 \
  --set-env-vars API_KEY=your-secure-key,ROBOT_HOST=192.168.1.83,ROBOT_PORT=27700
```

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `NEXT_PUBLIC_GCP_FUNCTION_URL` | GCP Cloud Function endpoint | Yes |
| `NEXT_PUBLIC_API_KEY` | API authentication key | Yes |
| `NEXT_PUBLIC_GCP_PROJECT_ID` | Google Cloud project ID | No |
| `NEXT_PUBLIC_GCP_REGION` | GCP region | No |

### Security Considerations

⚠️ **Important Security Notes:**

1. **API Key**: Replace the placeholder key with a cryptographically secure key
   ```bash
   # Generate secure API key
   openssl rand -hex 32
   ```

2. **CORS**: Configure CORS in GCP function for production domain only

3. **Environment Variables**: Never commit `.env.local` to version control

4. **HTTPS**: Always use HTTPS in production

5. **Rate Limiting**: Implement rate limiting on GCP function

## Troubleshooting

### Common Issues

**Port 3000 Already in Use**
```bash
lsof -ti:3000 | xargs kill -9
# Or use different port
npm run dev -- -p 3001
```

**Connection Timeout / Device Offline**
- App shows "Disconnected" status but remains functional
- Check EV3 device network connectivity
- Verify GCP function is deployed and accessible
- Check API key matches in both web app and GCP function

**Environment Variables Not Loading**
- Ensure `.env.local` exists in project root
- Restart development server after changes
- Variables must start with `NEXT_PUBLIC_` for client-side access

**Hydration Errors**
- Clear browser cache
- Delete `.next` folder: `rm -rf .next`
- Restart dev server

## Performance

- **Initial Load**: ~2 seconds
- **Command Latency**: 200-500ms to device
- **Status Updates**: Every 5 seconds
- **Memory Usage**: ~50MB browser footprint

## Roadmap

### Completed ✅
- [x] Real-time device control
- [x] Sensor monitoring (ultrasonic, gyro)
- [x] Motor status tracking
- [x] Speech commands
- [x] Interactive map
- [x] Battery & system monitoring

### In Progress 🚧
- [ ] Camera streaming (HLS integration)
- [ ] Mobile responsive optimization
- [ ] Historical data logging

### Planned 📋
- [ ] Multi-device support
- [ ] Mission scripting
- [ ] Voice control integration
- [ ] Gamepad support
- [ ] Offline mode
- [ ] User authentication

## Contributing

Contributions are welcome! Please follow these guidelines:

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/your-feature`
3. **Make your changes**
4. **Run linting**: `npm run lint`
5. **Commit with conventional commits**: `git commit -m "feat: add new feature"`
6. **Push to your fork**: `git push origin feature/your-feature`
7. **Create a Pull Request**

### Code Standards
- TypeScript for all components
- ESLint compliance required
- Functional components with hooks
- Meaningful variable names
- Comments for complex logic

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Author

**Rafal Kuklinski**
- GitHub: [@rkuklins](https://github.com/rkuklins)

## Acknowledgments

- LEGO Mindstorms EV3 and ev3dev community
- Next.js and React teams
- Google Cloud Platform
- Leaflet mapping library

## Support

For issues, questions, or contributions:
- **Issues**: [GitHub Issues](https://github.com/rkuklins/mindstorms-cloud-controller/issues)
- **Documentation**: See `DESIGN.md` and `NOTION_STATUS.md`

---

**Built with ❤️ for robotics enthusiasts**
