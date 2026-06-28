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
- **Auth**: NextAuth.js v5 (JWT sessions, credentials provider)
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
- **Authentication**: Server-side API Key (via `/api/robot` proxy)

## Architecture

```
Browser ──(session cookie)──► Next.js /api/robot ──(API_KEY)──► GCP Cloud Function ──► EV3
         ▲
   middleware.ts (NextAuth)
   guards all pages/routes
```

**Supported Commands**: forward, backward, left, right, stop, turret_left, turret_right, stop_turret, get_status, speak

## Authentication & Authorization

### Overview

The app uses NextAuth.js v5 with a Credentials provider. Users log in with username/password; a JWT session cookie is issued (8-hour expiry). All protected routes are enforced by `middleware.ts`.

### Roles & Permissions

| Permission | admin | operator | viewer |
|---|---|---|---|
| VIEW_STATUS | ✓ | ✓ | ✓ |
| STREAM_VIDEO | ✓ | ✓ | ✓ |
| CONTROL_EV3 | ✓ | ✓ | ✗ |
| MANAGE_USERS | ✓ | ✗ | ✗ |

- **admin**: Full access including the `/admin` access-control console
- **operator**: Robot control + camera + status (no user management)
- **viewer**: Read-only — camera and device status only

### Key Files

| File | Purpose |
|------|---------|
| `src/lib/auth.ts` | NextAuth config with bcrypt credentials (Node.js runtime) |
| `src/lib/auth.config.ts` | Edge-compatible config used by middleware (no bcrypt) |
| `src/lib/permissions.ts` | Role → permission mapping + helper functions |
| `src/types/auth.ts` | TypeScript types for User, Role, Permission |
| `middleware.ts` | Redirects unauthenticated users to `/login` |
| `src/app/api/auth/[...nextauth]/route.ts` | NextAuth API handlers |
| `src/app/api/robot/route.ts` | Server-side proxy — validates session + auth, forwards to GCP |
| `src/components/AuthGuard.tsx` | Client component that shows/hides UI based on permission |
| `src/components/UserMenu.tsx` | User avatar dropdown (logout + admin link) |
| `src/app/login/page.tsx` | Login form |
| `src/app/admin/page.tsx` | Access-control console (admin only) |

### User Configuration

Users are defined via the `AUTH_USERS_JSON` environment variable. Generate bcrypt hashes before adding:

```bash
# Generate a bcrypt hash (rounds=10):
node -e "const b=require('bcryptjs'); b.hash('your-password',10).then(console.log)"
```

Example value:
```json
[
  {"id":"1","username":"admin","passwordHash":"$2b$10$...","role":"admin"},
  {"id":"2","username":"operator","passwordHash":"$2b$10$...","role":"operator"},
  {"id":"3","username":"viewer","passwordHash":"$2b$10$...","role":"viewer"}
]
```

## Project Structure

```
src/
├── app/
│   ├── page.tsx                    # Main dashboard (protected)
│   ├── layout.tsx                  # Root layout (SessionProvider + ThemeProvider)
│   ├── globals.css
│   ├── login/
│   │   ├── page.tsx                # Login form
│   │   └── layout.tsx
│   ├── admin/
│   │   └── page.tsx                # Access-control console (admin only)
│   └── api/
│       ├── auth/[...nextauth]/     # NextAuth handlers
│       └── robot/                  # Server-side robot proxy
│           └── route.ts
├── components/
│   ├── AuthGuard.tsx               # Permission wrapper
│   ├── UserMenu.tsx                # User dropdown (logout + admin)
│   ├── AdminConsole.tsx            # Access control UI
│   ├── EV3StatusPanel.tsx          # Device monitoring
│   ├── VehicleControls.tsx         # Movement controls
│   ├── TurretControls.tsx          # Turret operations
│   ├── MapVisualization.tsx        # Terrain mapping
│   ├── CameraView.tsx              # Video streaming
│   └── ConnectionTest.tsx          # GCP connectivity
├── lib/
│   ├── auth.ts                     # Full NextAuth config (Node.js)
│   ├── auth.config.ts              # Edge-safe auth config (middleware)
│   ├── permissions.ts              # RBAC roles/permissions
│   └── robot-api.ts                # Robot API client (calls /api/robot)
└── types/
    └── auth.ts                     # Auth TypeScript types
middleware.ts                       # Route protection (redirects to /login)
```

## Environment Variables

Required in `.env.local` (see `.env.local.example`):

```bash
# NextAuth
AUTH_SECRET=<openssl rand -base64 32>
AUTH_USERS_JSON=[{"id":"1","username":"admin","passwordHash":"<hash>","role":"admin"}]

# Robot API — server-side only (NOT NEXT_PUBLIC_)
GCP_FUNCTION_URL=https://europe-central2-wrack-control.cloudfunctions.net/controlRobot
API_KEY=your-secret-api-key-here

# Optional GCP settings
NEXT_PUBLIC_GCP_PROJECT_ID=wrack-control
NEXT_PUBLIC_GCP_REGION=europe-central2
```

**Security note**: `NEXT_PUBLIC_API_KEY` and `NEXT_PUBLIC_GCP_FUNCTION_URL` are removed. The robot API key is now kept **server-side only** via the `/api/robot` Next.js Route Handler.

## Testing

```bash
# Unit tests only (fast, no browser)
npx vitest run --project unit

# Lint code
npm run lint
```

### New test files
- `src/lib/permissions.test.ts` — RBAC permission logic (19 tests)
- `src/components/AuthGuard.test.tsx` — AuthGuard rendering (7 tests)

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
2. Add command to allowed set in `app/api/robot/route.ts`
3. Create/update control component in `components/`
4. Wrap with `<AuthGuard permission="CONTROL_EV3">` if needed
5. Update GCP function if needed

**Adding sensor data visualization**:
1. Update data types in `types/`
2. Add chart component using Recharts
3. Integrate into `EV3StatusPanel.tsx`
4. Connect to real-time data source

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
- Auth variables (`AUTH_SECRET`, `AUTH_USERS_JSON`, `GCP_FUNCTION_URL`, `API_KEY`) must NOT have `NEXT_PUBLIC_` prefix (server-side only)

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

- **User Auth**: NextAuth.js JWT sessions (8h expiry), bcrypt password hashing
- **API Key**: Moved to server-side only — never exposed in browser bundle
- **Route Protection**: Next.js middleware enforces authentication on all pages
- **Authorization**: Role-based, enforced both in UI (`AuthGuard`) and server (`/api/robot`)
- **CORS**: Cloud Function protected behind server proxy

## Contact

- **Developer**: Rafal Kuklinski
- **GCP Project**: wrack-control
- **Repository**: Local development

---

*Version: 0.2.0 — Authentication & Authorization*
*Last Updated: 2026-05-22*
