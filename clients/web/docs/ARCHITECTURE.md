# WRACK Control Center - Design System Architecture

> **Document Version**: 2.0  
> **Date**: March 2026  
> **Status**: Proposed Architecture

## 1. Executive Summary

WRACK Control Center is a web-based control application for LEGO Mindstorms EV3 robots, providing real-time device control, sensor monitoring, terrain mapping, and camera integration through Google Cloud Functions. This document describes the proposed architecture for implementing Material Design 3 (Material You) in the application, establishing a scalable design system with design tokens and a component library that ensures visual consistency and streamlines the design-to-development workflow.

---

## 2. Architecture Goals

### 2.1 Primary Goals

| Goal | Description | Success Criteria |
|------|-------------|------------------|
| **Design Consistency** | Unified visual language across all components | Zero ad-hoc color/spacing usage |
| **Token Integration** | Design tokens from Material Theme Builder in code | Tokens successfully imported and used |
| **Accessibility** | WCAG 2.1 AA compliance | Pass automated and manual a11y audits |
| **Theming** | Support for light/dark/custom themes | Theme switching without code changes |
| **Maintainability** | Easy to update and extend | Single source of truth for design decisions |

> **Note on Figma Integration**: For the first iteration, we will use a simple manual workflow: export tokens as JSON from Material Theme Builder, then manually copy them into the codebase. Automated bi-directional sync (e.g., MUI Sync Plugin) can be considered in future iterations once the foundation is stable.

### 2.2 Secondary Goals

- Improve developer experience with typed components
- Reduce CSS bundle size through token-based styling
- Enable rapid prototyping and iteration
- Support future mobile/native applications through shared tokens

---

## 3. Technology Stack

### 3.1 Frontend

- **Framework**: Next.js 15 (App Router) with React 19
- **Language**: TypeScript 5
- **Styling**: Tailwind CSS 4 + MUI Theme (design tokens integration)
- **State**: Zustand
- **UI Components**: MUI v6 + Heroicons
- **Notifications**: React Hot Toast → MUI Snackbar (migration target)

### 3.2 Visualization

- **Charts**: Recharts (sensor data, real-time plots)
- **Mapping**: Leaflet + React-Leaflet (terrain visualization)
- **Video Streaming**: HLS.js (camera integration)

### 3.3 Backend Integration

- **Platform**: Google Cloud Functions (Gen2, Node.js 20)
- **Region**: europe-central2 / **Project**: wrack-control
- **Device Protocol**: TCP Socket to EV3
- **Authentication**: API Key (`X-API-Key` header)
- **Real-time Data**: WebSockets
- **Cloud Storage**: Google Cloud Storage (map data, images)
- **IoT Management**: Google Cloud IoT Core

### 3.4 Stack Evolution

| Aspect | Current | Proposed | Rationale |
|--------|---------|----------|-----------|
| UI Components | Custom + Heroicons | MUI v6 + Heroicons | Battle-tested, accessible, MD3-ready |
| Styling | Tailwind utilities | Tailwind + MUI Theme | Design tokens integration |
| Design Tokens | CSS variables (minimal) | Comprehensive token system | Consistency, maintainability |
| Theming | Dark-only (hardcoded) | ThemeProvider | Light/dark/custom support |
| Token Source | None | Material Theme Builder JSON export | Manual import, full control |

---

## 4. Architectural Overview

### 4.1 Application Architecture

```
Web App ←→ GCP Cloud Functions ←→ EV3 Device
        (HTTP REST)           (TCP Socket)
```

**Supported Commands**: `forward`, `backward`, `left`, `right`, `stop`, `turret_left`, `turret_right`, `stop_turret`, `get_status`

### 4.2 Communication Flows

#### Device Control (Immediate)

```
Web Control Panel → Cloud Function → IoT Core → WRACK Device
                    ↓
               Response/Status
```

**API Endpoints**:
- `POST /controlDevice` — Movement commands (forward, backward, turn)
- `POST /deviceAction` — Actions (start scan, stop, emergency)
- `GET /deviceStatus` — Current device state

#### Sensor Data (Real-time)

```
WRACK Device → IoT Core → Cloud Function → WebSocket/SSE → Web App
             → Cloud Storage (historical data)
```

- Device publishes sensor readings; Cloud Function processes and stores
- Real-time updates via WebSocket; historical data from Cloud Storage

#### Terrain Mapping (Persistent)

```
WRACK Device → Scan Data → Cloud Storage ← Web App (display)
             → GPS coords → Cloud Storage ← Web App (mapping)
```

Map data structure:
```json
{
  "scanId": "unique-id",
  "timestamp": "2024-01-01T12:00:00Z",
  "position": {"lat": 52.520, "lng": 13.405},
  "scanData": {
    "points": [],
    "obstacles": [],
    "terrain": ""
  }
}
```

### 4.3 Design System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        MATERIAL THEME BUILDER                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  1. Select source color → Generate MD3 tonal palettes               │   │
│  │  2. Customize light/dark schemes                                     │   │
│  │  3. Export as JSON file (tokens.json)                               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┬────┘
                                                                         │
                                              Manual copy/paste of JSON  │
                                                                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CODE REPOSITORY                                    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      DESIGN TOKENS LAYER                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌────────────────────────┐  │   │
│  │  │ tokens/       │  │ colors.ts     │  │ typography.ts          │  │   │
│  │  │  ├─ base.ts   │  │ spacing.ts    │  │ elevation.ts           │  │   │
│  │  │  ├─ exported/ │  │ radius.ts     │  │ motion.ts              │  │   │
│  │  │  │  └─ mtb.json│ │               │  │                        │  │   │
│  │  │  └─ semantic  │  │               │  │                        │  │   │
│  │  └───────────────┘  └───────────────┘  └────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      THEME PROVIDER LAYER                            │   │
│  │  ┌───────────────────────────────────────────────────────────────┐  │   │
│  │  │  ThemeProvider (MUI + Tailwind CSS Variables)                  │  │   │
│  │  │  ├─ Light Theme                                                │  │   │
│  │  │  ├─ Dark Theme                                                 │  │   │
│  │  │  └─ Custom Themes (Material You dynamic colors)                │  │   │
│  │  └───────────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      COMPONENT LIBRARY LAYER                         │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │   │
│  │  │ MUI Core     │  │ Custom       │  │ Domain Components        │  │   │
│  │  │ Components   │  │ Components   │  │ (EV3-specific)           │  │   │
│  │  │ (Button,     │  │ (RangeSlider,│  │ (MotorCard, SensorCard,  │  │   │
│  │  │  Card, etc.) │  │  StatusDot)  │  │  ControlPad, etc.)       │  │   │
│  │  └──────────────┘  └──────────────┘  └──────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      APPLICATION LAYER                               │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │   │
│  │  │ Pages        │  │ Layouts      │  │ Features                 │  │   │
│  │  │ (Dashboard)  │  │ (Root, etc.) │  │ (Controls, Status, Map)  │  │   │
│  │  └──────────────┘  └──────────────┘  └──────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Project Structure

```
src/
├── app/
│   ├── page.tsx                  # Main dashboard
│   ├── layout.tsx                # Root layout
│   └── globals.css               # Global styles + CSS variable bridge
├── components/
│   ├── EV3StatusPanel.tsx        # Device monitoring
│   ├── VehicleControls.tsx       # Movement controls
│   ├── TurretControls.tsx        # Turret operations
│   ├── MapVisualization.tsx      # Terrain mapping
│   ├── CameraView.tsx            # Video streaming
│   └── ConnectionTest.tsx        # GCP connectivity
├── design-system/
│   ├── tokens/
│   │   ├── exported/
│   │   │   └── material-theme.json   # Manually copied from Material Theme Builder
│   │   ├── colors.generated.ts       # Auto-generated by tokens:transform
│   │   ├── colors.ts                 # Manual overrides/extensions
│   │   ├── typography.ts
│   │   ├── spacing.ts
│   │   ├── radius.ts
│   │   ├── elevation.ts
│   │   ├── motion.ts
│   │   └── index.ts
│   ├── themes/
│   │   ├── index.ts
│   │   ├── muiTheme.ts               # MUI theme using generated tokens
│   │   ├── lightTheme.ts
│   │   ├── darkTheme.ts
│   │   └── types.ts
│   ├── components/
│   │   ├── index.ts
│   │   ├── Button/
│   │   ├── Card/
│   │   ├── StatusIndicator/
│   │   ├── ControlPad/
│   │   └── ...
│   └── providers/
│       ├── ThemeProvider.tsx
│       └── index.ts
├── lib/
│   └── robot-api.ts              # GCP API client
├── stores/
│   ├── device-store.ts           # Device state management
│   ├── sensor-store.ts           # Sensor data state
│   ├── ui-store.ts               # UI state (active tabs, modals)
│   └── theme-store.ts            # Theme mode preference
├── types/
│   ├── device.ts
│   ├── sensor.ts
│   └── api.ts
└── hooks/
    ├── useDeviceControl.ts
    ├── useSensorData.ts
    └── useWebSocket.ts
```

---

## 6. Data Models

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
  parameters?: Record<string, unknown>;
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

---

## 7. Environment Configuration

Required in `.env.local`:

```bash
# Google Cloud Project
NEXT_PUBLIC_GCP_FUNCTION_URL=https://europe-central2-wrack-control.cloudfunctions.net/controlRobot
NEXT_PUBLIC_API_KEY=your-api-key
NEXT_PUBLIC_GCP_PROJECT_ID=wrack-control
NEXT_PUBLIC_GCP_REGION=europe-central2

# Real-time Communication
NEXT_PUBLIC_WEBSOCKET_URL=wss://your-websocket-endpoint

# Cloud Storage
NEXT_PUBLIC_STORAGE_BUCKET=your-storage-bucket
```

Copy `.env.local.example` to `.env.local` to get started.

---

## 8. Design Tokens Architecture

### 8.1 Token Hierarchy

```
Base Tokens (Primitives)
    │
    ├── Colors
    │   ├── Palette: blue-10 to blue-100, gray-10 to gray-100, etc.
    │   └── Semantic: primary, secondary, error, surface, etc.
    │
    ├── Typography
    │   ├── Font Families: sans, mono
    │   ├── Font Sizes: xs, sm, md, lg, xl, 2xl, 3xl
    │   └── Font Weights: regular, medium, semibold, bold
    │
    ├── Spacing
    │   └── Scale: 0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24
    │
    ├── Radius
    │   └── Scale: none, sm, md, lg, xl, full
    │
    └── Elevation
        └── Levels: 0, 1, 2, 3, 4, 5
            │
            ▼
Semantic Tokens (Role-based)
    │
    ├── Surface Colors
    │   ├── surface-container
    │   ├── surface-container-high
    │   └── surface-container-low
    │
    ├── State Colors
    │   ├── on-primary, on-secondary, on-surface
    │   ├── primary-container, secondary-container
    │   └── outline, outline-variant
    │
    └── Interactive Tokens
        ├── hover, focus, active, disabled
        └── ripple, elevation transitions
            │
            ▼
Component Tokens (Component-specific)
    │
    ├── Button
    │   ├── button-padding, button-radius
    │   └── button-elevation-default, button-elevation-hover
    │
    ├── Card
    │   ├── card-radius, card-elevation
    │   └── card-padding
    │
    └── ... (other components)
```

### 8.2 Material Design 3 Color System

```typescript
// tokens/colors.ts

export const md3Colors = {
  // Primary Tonal Palette
  primary: {
    0: '#000000',
    10: '#001f24',
    20: '#003640',
    30: '#00515e',
    40: '#006d7e',  // Primary
    50: '#008a9e',
    60: '#00a7bf',
    70: '#2dc3db',
    80: '#5ddff7',  // Primary Container (dark)
    90: '#b3ebf5',  // Primary Container (light)
    95: '#d9f5fa',
    99: '#f6feff',
    100: '#ffffff',
  },

  // Secondary Tonal Palette
  secondary: {
    // Similar structure...
  },

  // Tertiary Tonal Palette (Material 3 specific)
  tertiary: {
    // Similar structure...
  },

  // Error Tonal Palette
  error: {
    // Similar structure...
  },

  // Neutral Tonal Palette
  neutral: {
    // Used for surfaces and backgrounds
  },

  // Neutral Variant Tonal Palette
  neutralVariant: {
    // Used for outlines and surface variants
  },
};

// Semantic color mappings
export const lightThemeColors = {
  primary: md3Colors.primary[40],
  onPrimary: md3Colors.primary[100],
  primaryContainer: md3Colors.primary[90],
  onPrimaryContainer: md3Colors.primary[10],
  
  surface: md3Colors.neutral[99],
  surfaceContainer: md3Colors.neutral[94],
  surfaceContainerHigh: md3Colors.neutral[92],
  surfaceContainerLow: md3Colors.neutral[96],
  onSurface: md3Colors.neutral[10],
  
  outline: md3Colors.neutralVariant[50],
  outlineVariant: md3Colors.neutralVariant[80],
  
  // ... additional semantic colors
};

export const darkThemeColors = {
  primary: md3Colors.primary[80],
  onPrimary: md3Colors.primary[20],
  primaryContainer: md3Colors.primary[30],
  onPrimaryContainer: md3Colors.primary[90],
  
  surface: md3Colors.neutral[6],
  surfaceContainer: md3Colors.neutral[12],
  surfaceContainerHigh: md3Colors.neutral[17],
  surfaceContainerLow: md3Colors.neutral[10],
  onSurface: md3Colors.neutral[90],
  
  // ... additional semantic colors
};
```

---

## 9. Design Token Export & Import Architecture

> **First Iteration Approach**: This section describes a simple, manual workflow for exporting tokens from Material Theme Builder and importing them into the codebase. This approach gives full control over the token ingestion process and avoids dependencies on automated sync tools. The designer exports the JSON, and the developer manually imports it into the codebase.

### 9.1 Material Theme Builder Export Workflow

The Material Theme Builder (https://m3.material.io/theme-builder) generates MD3-compliant color tokens that are **exported as a JSON file**.

```
┌───────────────────────────────────────────────────────────────────┐
│                   MATERIAL THEME BUILDER (Web)                     │
│                   https://m3.material.io/theme-builder             │
│                                                                    │
│  Step 1: Select Source Color                                       │
│     └── Pick a primary brand color (e.g., #006d7e for WRACK blue) │
│                                                                    │
│  Step 2: Customize Theme                                           │
│     ├── Adjust tonal palettes if needed                           │
│     ├── Configure light and dark schemes                          │
│     └── Add custom/extended colors                                │
│                                                                    │
│  Step 3: Export Tokens                                             │
│     └── Click "Export" → Select "Material Theme (JSON)"           │
│         Downloads: material-theme.json                             │
│                                                                    │
└───────────────────────────────────────────────────────────────────┘
```

### 9.2 Exported JSON Structure

Material Theme Builder exports a JSON file with the following structure. This is the **source of truth** for all color tokens:

```json
{
  "description": "Material Theme exported from Material Theme Builder",
  "seed": "#006d7e",
  "coreColors": {
    "primary": "#006d7e"
  },
  "extendedColors": [],
  "schemes": {
    "light": {
      "primary": "#006d7e",
      "onPrimary": "#ffffff",
      "primaryContainer": "#b3ebf5",
      "onPrimaryContainer": "#001f24",
      "secondary": "#4a6267",
      "onSecondary": "#ffffff",
      "secondaryContainer": "#cde7ec",
      "onSecondaryContainer": "#051f23",
      "tertiary": "#525e7d",
      "onTertiary": "#ffffff",
      "tertiaryContainer": "#dae2ff",
      "onTertiaryContainer": "#0e1b36",
      "error": "#ba1a1a",
      "onError": "#ffffff",
      "errorContainer": "#ffdad6",
      "onErrorContainer": "#410002",
      "background": "#fafdfd",
      "onBackground": "#191c1c",
      "surface": "#fafdfd",
      "onSurface": "#191c1c",
      "surfaceVariant": "#dbe4e6",
      "onSurfaceVariant": "#3f484a",
      "outline": "#6f797a",
      "outlineVariant": "#bfc8ca",
      "shadow": "#000000",
      "scrim": "#000000",
      "inverseSurface": "#2d3131",
      "inverseOnSurface": "#eff1f1",
      "inversePrimary": "#5ddff7"
    },
    "dark": {
      "primary": "#5ddff7",
      "onPrimary": "#00363e",
      "primaryContainer": "#004f5a",
      "onPrimaryContainer": "#b3ebf5",
      "secondary": "#b1cbd0",
      "onSecondary": "#1c3438",
      "secondaryContainer": "#334b4f",
      "onSecondaryContainer": "#cde7ec",
      "tertiary": "#bbc6ea",
      "onTertiary": "#25304d",
      "tertiaryContainer": "#3b4664",
      "onTertiaryContainer": "#dae2ff",
      "error": "#ffb4ab",
      "onError": "#690005",
      "errorContainer": "#93000a",
      "onErrorContainer": "#ffdad6",
      "background": "#191c1c",
      "onBackground": "#e0e3e3",
      "surface": "#191c1c",
      "onSurface": "#e0e3e3",
      "surfaceVariant": "#3f484a",
      "onSurfaceVariant": "#bfc8ca",
      "outline": "#899294",
      "outlineVariant": "#3f484a",
      "shadow": "#000000",
      "scrim": "#000000",
      "inverseSurface": "#e0e3e3",
      "inverseOnSurface": "#191c1c",
      "inversePrimary": "#006d7e"
    }
  },
  "palettes": {
    "primary": {
      "0": "#000000",
      "10": "#001f24",
      "20": "#003640",
      "30": "#00515e",
      "40": "#006d7e",
      "50": "#008a9e",
      "60": "#00a7bf",
      "70": "#2dc3db",
      "80": "#5ddff7",
      "90": "#b3ebf5",
      "95": "#d9f5fa",
      "99": "#f6feff",
      "100": "#ffffff"
    }
  }
}
```

### 9.3 Manual Token Import Process

**Step-by-step process for importing tokens into the codebase:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 1: Download JSON from Material Theme Builder                          │
│  └── Save as: src/design-system/tokens/exported/material-theme.json        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 2: Run Token Transformation Script (or manually update)               │
│  └── npm run tokens:transform                                               │
│      Reads JSON → Generates TypeScript token file                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 3: Verify Theme Changes                                               │
│  └── Run app locally, check Storybook, verify light/dark modes              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 4: Commit Updated Tokens                                              │
│  └── git add . && git commit -m "chore: update design tokens from MTB"     │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 9.4 Token Transformation Script

A simple script transforms the exported JSON into TypeScript token files:

```typescript
// scripts/transform-tokens.ts

import * as fs from 'fs';
import * as path from 'path';

interface MaterialTheme {
  schemes: {
    light: Record<string, string>;
    dark: Record<string, string>;
  };
  palettes: Record<string, Record<string, string>>;
}

const inputPath = path.join(__dirname, '../src/design-system/tokens/exported/material-theme.json');
const outputPath = path.join(__dirname, '../src/design-system/tokens/colors.generated.ts');

const theme: MaterialTheme = JSON.parse(fs.readFileSync(inputPath, 'utf-8'));

const output = `// AUTO-GENERATED FROM material-theme.json
// Do not edit manually. Re-run 'npm run tokens:transform' after updating the JSON.
// Last updated: ${new Date().toISOString()}

export const lightScheme = ${JSON.stringify(theme.schemes.light, null, 2)} as const;

export const darkScheme = ${JSON.stringify(theme.schemes.dark, null, 2)} as const;

export const palettes = ${JSON.stringify(theme.palettes, null, 2)} as const;
`;

fs.writeFileSync(outputPath, output);
console.log('✅ Tokens transformed successfully!');
```

**Add to package.json:**

```json
{
  "scripts": {
    "tokens:transform": "tsx scripts/transform-tokens.ts"
  }
}
```

### 9.5 Token Update Workflow Summary

| Step | Action | Who | Frequency |
|------|--------|-----|-----------|
| 1 | Open Material Theme Builder | Designer | When design changes needed |
| 2 | Modify source color or schemes | Designer | As needed |
| 3 | Export JSON | Designer | After each design session |
| 4 | Copy `material-theme.json` to repo | Developer | Manual copy/paste |
| 5 | Run `npm run tokens:transform` | Developer | After JSON update |
| 6 | Test in browser/Storybook | Developer | After transform |
| 7 | Commit changes | Developer | When satisfied |

> **Important**: This is an intentionally simple, manual process for the first iteration. Each token update requires downloading a new JSON file and running the transform script. This provides full visibility into what changed and when.

### 9.6 Future Enhancements (Optional)

In later iterations, this manual process could be automated:

| Enhancement | Description | Complexity |
|-------------|-------------|------------|
| Figma Variables | Import MTB tokens into Figma as local variables | Low |
| MUI Sync Plugin | Bi-directional Figma ↔ Code sync | Medium |
| CI Token Validation | Automatically validate token changes in PRs | Low |
| Figma API Integration | Pull tokens directly from Figma via API | High |

For now, the manual JSON export/import workflow provides the right balance of simplicity and control.

### 9.7 MUI Theme Integration

Using the tokens generated from the Material Theme Builder JSON:

```typescript
// src/design-system/themes/muiTheme.ts

import { createTheme } from '@mui/material/styles';
// Import from the auto-generated file (created by tokens:transform script)
import { lightScheme, darkScheme } from '../tokens/colors.generated';

export const createWrackTheme = (mode: 'light' | 'dark') => {
  // Use the scheme directly from the transformed Material Theme Builder JSON
  const scheme = mode === 'light' ? lightScheme : darkScheme;
  
  return createTheme({
    palette: {
      mode,
      primary: {
        main: scheme.primary,
        contrastText: scheme.onPrimary,
      },
      secondary: {
        main: scheme.secondary,
        contrastText: scheme.onSecondary,
      },
      error: {
        main: scheme.error,
        contrastText: scheme.onError,
      },
      background: {
        default: scheme.background,
        paper: scheme.surface,
      },
      text: {
        primary: scheme.onBackground,
        secondary: scheme.onSurfaceVariant,
      },
    },
    shape: {
      borderRadius: 12, // MD3 default
    },
    components: {
      MuiButton: {
        styleOverrides: {
          root: {
            textTransform: 'none', // MD3 uses sentence case
            borderRadius: '20px', // MD3 pill shape for buttons
          },
        },
      },
      MuiCard: {
        styleOverrides: {
          root: {
            borderRadius: '12px',
          },
        },
      },
      // ... other component overrides
    },
  });
};
```

---

## 10. Component Architecture

### 10.1 Component Hierarchy

```
Design System Components (Generic, Reusable)
│
├── Primitives
│   ├── Button
│   ├── IconButton
│   ├── Typography
│   └── Box/Stack
│
├── Form Controls
│   ├── TextField
│   ├── Slider (RangeSlider)
│   ├── Switch
│   └── Select
│
├── Data Display
│   ├── Card
│   ├── Chip
│   ├── Badge
│   └── Tooltip
│
├── Feedback
│   ├── Snackbar (Toast replacement)
│   ├── Dialog
│   ├── Progress (Linear, Circular)
│   └── Skeleton
│
└── Navigation
    ├── Tabs
    ├── Menu
    └── Drawer
        │
        ▼
Domain Components (EV3-specific)
│
├── Status Components
│   ├── StatusIndicator     # Connection status dots
│   ├── BatteryIndicator    # Battery level with icon
│   ├── MotorCard           # Single motor status card
│   ├── SensorCard          # Single sensor status card
│   └── DeviceInfoCard      # EV3 brick info panel
│
├── Control Components
│   ├── ControlPad          # D-pad style directional control
│   ├── SpeedSlider         # Speed control with percentage
│   ├── EmergencyStop       # Large stop button
│   └── TurretControl       # Turret-specific controls
│
├── Visualization Components
│   ├── AngleIndicator      # Turret angle visualization
│   ├── TrailMap            # Leaflet map wrapper with trail
│   └── TelemetryChart      # Recharts wrapper for data
│
└── Layout Components
    ├── CollapsibleSection  # Expandable panel
    ├── SplitPane           # Resizable split layout
    └── ControlPanel        # Standardized panel container
```

### 10.2 Component Structure Example

```typescript
// src/design-system/components/StatusIndicator/StatusIndicator.tsx

import { Box } from '@mui/material';
import { SxProps, Theme } from '@mui/system';

export type StatusType = 'online' | 'offline' | 'warning' | 'error' | 'inactive';

interface StatusIndicatorProps {
  status: StatusType;
  size?: 'small' | 'medium' | 'large';
  pulse?: boolean;
  label?: string;
  sx?: SxProps<Theme>;
}

const sizeMap = {
  small: 8,
  medium: 12,
  large: 16,
};

const statusColorMap: Record<StatusType, string> = {
  online: 'success.main',
  offline: 'error.main',
  warning: 'warning.main',
  error: 'error.main',
  inactive: 'action.disabled',
};

export const StatusIndicator = ({
  status,
  size = 'medium',
  pulse = false,
  label,
  sx,
}: StatusIndicatorProps) => {
  const dimension = sizeMap[size];

  return (
    <Box
      component="span"
      sx={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 1,
        ...sx,
      }}
    >
      <Box
        sx={{
          width: dimension,
          height: dimension,
          borderRadius: '50%',
          backgroundColor: statusColorMap[status],
          ...(pulse && {
            animation: 'pulse 2s infinite',
            '@keyframes pulse': {
              '0%': { opacity: 1 },
              '50%': { opacity: 0.5 },
              '100%': { opacity: 1 },
            },
          }),
        }}
      />
      {label && (
        <Box component="span" sx={{ typography: 'body2' }}>
          {label}
        </Box>
      )}
    </Box>
  );
};
```

---

## 11. Tailwind + MUI Integration Strategy

### 11.1 CSS Variables Bridge

```css
/* src/app/globals.css */

@import "tailwindcss";

:root {
  /* Import from MUI theme via CSS custom properties */
  --md-sys-color-primary: theme('colors.primary.main');
  --md-sys-color-on-primary: theme('colors.primary.contrastText');
  --md-sys-color-surface: theme('colors.background.default');
  --md-sys-color-surface-container: theme('colors.background.paper');
  
  /* Spacing */
  --md-sys-spacing-1: 4px;
  --md-sys-spacing-2: 8px;
  --md-sys-spacing-3: 12px;
  --md-sys-spacing-4: 16px;
  
  /* Typography */
  --md-sys-typescale-body-large: 1rem;
  --md-sys-typescale-title-medium: 1.125rem;
}

@theme inline {
  --color-primary: var(--md-sys-color-primary);
  --color-on-primary: var(--md-sys-color-on-primary);
  --color-surface: var(--md-sys-color-surface);
  --color-surface-container: var(--md-sys-color-surface-container);
}
```

### 11.2 Usage Guidelines

| Use Case | Recommended Approach |
|----------|---------------------|
| Complex interactive components | MUI components |
| Simple layout utilities | Tailwind classes |
| Custom domain components | MUI + Tailwind hybrid |
| Typography | MUI Typography component |
| Spacing | Tailwind utilities or MUI sx prop |
| Colors | Design tokens via CSS variables |

---

## 12. State Management Integration

### 12.1 Theme State with Zustand

```typescript
// src/stores/themeStore.ts

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

type ThemeMode = 'light' | 'dark' | 'system';

interface ThemeState {
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
  resolvedMode: 'light' | 'dark';
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      mode: 'system',
      resolvedMode: 'dark', // Default
      setMode: (mode) => {
        const resolved = mode === 'system' 
          ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
          : mode;
        set({ mode, resolvedMode: resolved });
      },
    }),
    {
      name: 'wrack-theme',
    }
  )
);
```

### 12.2 Other Stores

- **`device-store.ts`** — Device connection state, status, position, battery
- **`sensor-store.ts`** — Real-time sensor readings, history, alerts
- **`ui-store.ts`** — Active tabs, modal state, panel expand/collapse

---

## 13. Accessibility Architecture

### 13.1 A11y Requirements

| Requirement | Implementation |
|-------------|----------------|
| Color contrast | Use MD3 semantic colors (built-in 4.5:1 ratio) |
| Focus indicators | MUI built-in focus-visible styling |
| Keyboard navigation | MUI components are keyboard accessible |
| Screen reader support | Proper ARIA labels and roles |
| Reduced motion | Respect `prefers-reduced-motion` |
| Touch targets | Minimum 44x44px interactive areas |

### 13.2 Focus Management Example

```typescript
// Focus ring styling in theme
components: {
  MuiButtonBase: {
    styleOverrides: {
      root: {
        '&:focus-visible': {
          outline: `2px solid ${colors.primary}`,
          outlineOffset: '2px',
        },
      },
    },
  },
}
```

---

## 14. Implementation Roadmap

### Phase 1: Foundation & Basic Control Interface

- [ ] Install MUI dependencies and set up ThemeProvider
- [ ] Create design tokens from Material Theme Builder export
- [ ] Device connection status display
- [ ] Basic movement controls (forward, backward, turn)
- [ ] Emergency stop functionality
- [ ] Real-time device status display

### Phase 2: Design System + Sensor Dashboard

- [ ] Create shared design system components (StatusIndicator, ControlPad, etc.)
- [ ] Migrate existing components to design system primitives
- [ ] Real-time sensor data visualization
- [ ] Battery and system status
- [ ] Data logging and history
- [ ] Alert system for critical values

### Phase 3: Terrain Mapping + Full Migration

- [ ] Map visualization with Leaflet
- [ ] Display scan data overlays
- [ ] Path tracking and history
- [ ] Obstacle detection visualization
- [ ] Migrate all components to design system
- [ ] Complete a11y audit

### Phase 4: Advanced Features

- [ ] Camera stream integration (HLS)
- [ ] Advanced mapping tools
- [ ] Data export capabilities
- [ ] Multi-device support
- [ ] Light/dark theme toggle in UI

---

## 15. Migration Path from Current Architecture

### 15.1 Coexistence Strategy

During migration, the existing Tailwind-based components will coexist with new MUI components:

```
Phase 1: Foundation
├── Install MUI dependencies
├── Set up ThemeProvider
├── Create design tokens
└── Existing components continue working

Phase 2: Shared Components
├── Create StatusIndicator (replaces status dots)
├── Create ControlPad (replaces direction buttons)
├── Update existing components to use new primitives
└── Gradual migration, not big-bang

Phase 3: Full Migration
├── Migrate all components to design system
├── Remove ad-hoc Tailwind utilities for colors
├── Consolidate styling approaches
└── Complete a11y audit
```

### 15.2 Component Migration Example

```typescript
// BEFORE (current)
<div className="w-2 h-2 rounded-full bg-green-500" />

// AFTER (design system)
<StatusIndicator status="online" size="small" />
```

---

## 16. Build and Performance Considerations

### 16.1 Bundle Optimization

| Strategy | Implementation |
|----------|----------------|
| Tree shaking | Import MUI components individually |
| Code splitting | Lazy load non-critical components |
| CSS optimization | Use Tailwind's purge for utilities |
| Font optimization | Continue using Next.js font optimization |

### 16.2 Import Pattern

```typescript
// Preferred: Named imports for tree shaking
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';

// Avoid: Importing entire library
// import { Button, Card } from '@mui/material';
```

### 16.3 Performance Targets

- **Load Time**: ~2 seconds
- **Command Latency**: ~200–500ms
- **Update Interval**: 2–5 seconds
- **Memory**: ~50MB browser

---

## 17. Development Commands

```bash
# Development
npm run dev              # Start development server (localhost:3000)
npm run build            # Build for production
npm run start            # Start production server
npm run lint             # Run ESLint
npm run type-check       # TypeScript checking

# Design Tokens
npm run tokens:transform # Transform Material Theme Builder JSON to TypeScript
```

### GCP Deployment

```bash
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

---

## 18. Security Considerations

- **API Authentication**: API Key via `X-API-Key` header; use service account keys for GCP
- **Environment Variables**: Never commit secrets to repository; use `.env.local`
- **CORS Configuration**: Restrict origins for production (currently localhost-only)
- **Rate Limiting**: Implement for device control endpoints
- **Input Validation**: Validate all commands before sending to device
- **Secure WebSocket**: Use WSS in production
- **HTTPS Enforcement**: Required for production deployments
- **Future**: JWT tokens, user authentication, audit logging

---

## 19. Testing Strategy

### 19.1 Design System Testing

| Test Type | Tools | Coverage |
|-----------|-------|----------|
| Unit tests | Jest + Testing Library | Component behavior |
| Visual regression | Storybook + Chromatic | UI consistency |
| A11y testing | jest-axe, Lighthouse | WCAG compliance |
| Theme testing | Custom theme tests | Light/dark modes |

### 19.2 Storybook Integration

```typescript
// Component stories for documentation and testing
// src/design-system/components/StatusIndicator/StatusIndicator.stories.tsx

import type { Meta, StoryObj } from '@storybook/react';
import { StatusIndicator } from './StatusIndicator';

const meta: Meta<typeof StatusIndicator> = {
  component: StatusIndicator,
  title: 'Design System/StatusIndicator',
  argTypes: {
    status: {
      control: 'select',
      options: ['online', 'offline', 'warning', 'error', 'inactive'],
    },
  },
};

export default meta;
type Story = StoryObj<typeof StatusIndicator>;

export const Online: Story = {
  args: {
    status: 'online',
    label: 'Connected',
  },
};

export const Offline: Story = {
  args: {
    status: 'offline',
    label: 'Disconnected',
  },
};
```

---

## 20. Future Enhancements

### Camera Integration
- HLS video streaming with multiple camera angles
- Recording capabilities
- Real-time image analysis

### Advanced Analytics
- Machine learning for terrain analysis
- Predictive maintenance
- Historical data analysis and export

### Multi-Device Support
- Device fleet management
- Coordinated scanning missions
- Centralized monitoring

### GPS & Mapping
- GPS integration and data persistence
- Advanced mapping overlays

---

## Appendix

### A. Full Dependency List

**Production Dependencies**

```json
{
  "next": "15.5.0",
  "react": "19.1.0",
  "react-dom": "19.1.0",
  "typescript": "^5",
  "tailwindcss": "^4",
  "@mui/material": "^6.0.0",
  "@mui/system": "^6.0.0",
  "@mui/icons-material": "^6.0.0",
  "@emotion/react": "^11.11.0",
  "@emotion/styled": "^11.11.0",
  "zustand": "^5.0.8",
  "socket.io-client": "^4.8.1",
  "react-leaflet": "^5.0.0",
  "leaflet": "^1.9.4",
  "@types/leaflet": "^1.9.20",
  "recharts": "^3.1.2",
  "@google-cloud/storage": "^7.17.0",
  "@google-cloud/iot": "^5.2.0",
  "@heroicons/react": "^2.2.0",
  "react-hot-toast": "^2.6.0",
  "date-fns": "^4.1.0",
  "hls.js": "^1.6.10"
}
```

**Development Dependencies**

```json
{
  "@types/node": "^20",
  "@types/react": "^19",
  "@types/react-dom": "^19",
  "eslint": "^9",
  "eslint-config-next": "15.5.0",
  "@storybook/react": "^8.0.0",
  "@storybook/addon-a11y": "^8.0.0",
  "jest-axe": "^8.0.0"
}
```

### B. Key Configuration Files

| File | Purpose |
|------|---------|
| `src/design-system/tokens/index.ts` | Token exports |
| `src/design-system/themes/index.ts` | Theme configuration |
| `src/design-system/providers/ThemeProvider.tsx` | Theme context |
| `.storybook/main.ts` | Storybook configuration |
| `tailwind.config.ts` | Tailwind token integration |
| `scripts/transform-tokens.ts` | Token transformation script |

### C. References

- [Material Design 3 Guidelines](https://m3.material.io/)
- [MUI Documentation](https://mui.com/)
- [MUI Sync Plugin](https://mui.com/blog/introducing-sync-plugin/)
- [Tailwind CSS](https://tailwindcss.com/docs)
- [Next.js App Router](https://nextjs.org/docs/app)

---

*This architecture document provides the technical foundation for implementing Material Design 3 in the WRACK Control Center. It should be reviewed and refined during the implementation phases.*
