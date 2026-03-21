# WRACK Control Center - Requirements Document

> **Document Version**: 1.0  
> **Date**: March 2026  
> **Status**: Draft - Reverse Engineered from Existing Implementation

## 1. Executive Summary

This document captures the functional and non-functional requirements for the WRACK Control Center web application, derived through reverse engineering of the existing codebase. It identifies the current implementation state, gaps, and open topics requiring clarification.

---

## 2. System Overview

### 2.1 Purpose

The WRACK Control Center is a web-based control application for managing and monitoring LEGO Mindstorms EV3 robots remotely. It provides:

- Real-time device status monitoring
- Remote vehicle movement control
- Turret operation management
- Terrain mapping and visualization
- Camera integration (planned)
- Text-to-speech communication

### 2.2 Target Users

| User Type | Description |
|-----------|-------------|
| Robot Operator | Primary user controlling the EV3 robot remotely |
| System Administrator | Manages GCP infrastructure and API access |
| Developer | Extends and maintains the control system |

### 2.3 System Context

```
┌─────────────────┐    HTTPS/REST    ┌──────────────────────┐    TCP Socket    ┌─────────────┐
│   Web Browser   │ ◄──────────────► │  GCP Cloud Functions │ ◄──────────────► │  EV3 Robot  │
│  (Control App)  │                  │   (europe-central2)  │                  │             │
└─────────────────┘                  └──────────────────────┘                  └─────────────┘
```

---

## 3. Functional Requirements

### 3.1 Device Status Monitoring (FR-001)

#### FR-001.1: EV3 Brick Status Display

| Requirement | Description | Status |
|-------------|-------------|--------|
| FR-001.1.1 | Display real-time battery level (percentage) | Implemented |
| FR-001.1.2 | Display battery voltage | Implemented |
| FR-001.1.3 | Display CPU usage percentage | Implemented |
| FR-001.1.4 | Display device IP address | Implemented |
| FR-001.1.5 | Display kernel version | Implemented |
| FR-001.1.6 | Display connection status indicator | Implemented |
| FR-001.1.7 | Display last update timestamp | Implemented |

#### FR-001.2: Motor Status Display

| Requirement | Description | Status |
|-------------|-------------|--------|
| FR-001.2.1 | Display all connected motors | Implemented |
| FR-001.2.2 | Show motor port assignments | Implemented |
| FR-001.2.3 | Display motor angle (degrees) | Implemented |
| FR-001.2.4 | Display motor speed (°/s) | Implemented |
| FR-001.2.5 | Show motor availability status | Implemented |
| FR-001.2.6 | Indicate stalled motor state | Implemented |

#### FR-001.3: Sensor Status Display

| Requirement | Description | Status |
|-------------|-------------|--------|
| FR-001.3.1 | Display ultrasonic sensor readings (cm) | Implemented |
| FR-001.3.2 | Display gyro sensor angle and speed | Implemented |
| FR-001.3.3 | Display Pixy camera status | Implemented |
| FR-001.3.4 | Show sensor availability status | Implemented |

### 3.2 Vehicle Movement Control (FR-002)

| Requirement | Description | Status |
|-------------|-------------|--------|
| FR-002.1 | Forward movement command | Implemented |
| FR-002.2 | Backward movement command | Implemented |
| FR-002.3 | Turn left command | Implemented |
| FR-002.4 | Turn right command | Implemented |
| FR-002.5 | Emergency stop command | Implemented |
| FR-002.6 | Adjustable speed control (10-100%) | Implemented |
| FR-002.7 | Visual feedback during movement | Implemented |
| FR-002.8 | Movement state indication | Implemented |

### 3.3 Turret Control (FR-003)

| Requirement | Description | Status |
|-------------|-------------|--------|
| FR-003.1 | Rotate turret left | Implemented |
| FR-003.2 | Rotate turret right | Implemented |
| FR-003.3 | Stop/center turret | Implemented |
| FR-003.4 | Adjustable rotation speed (10-100%) | Implemented |
| FR-003.5 | Visual angle indicator | Implemented |
| FR-003.6 | 360° scan mode toggle | Implemented (UI only) |

### 3.4 Map Visualization (FR-004)

| Requirement | Description | Status |
|-------------|-------------|--------|
| FR-004.1 | Interactive Leaflet map display | Implemented |
| FR-004.2 | Vehicle position marker | Implemented |
| FR-004.3 | Vehicle heading indicator | Implemented |
| FR-004.4 | Trail/path history visualization | Implemented |
| FR-004.5 | Terrain points display (obstacles) | Implemented |
| FR-004.6 | Map mode toggle (satellite/terrain) | Implemented |
| FR-004.7 | Show/hide trail toggle | Implemented |

### 3.5 Camera Integration (FR-005)

| Requirement | Description | Status |
|-------------|-------------|--------|
| FR-005.1 | HLS video stream display | Placeholder |
| FR-005.2 | Expandable camera view | Implemented |
| FR-005.3 | Camera show/hide toggle | Implemented |
| FR-005.4 | Fullscreen camera mode | Not Implemented |
| FR-005.5 | Camera recording | Not Implemented |

### 3.6 Speech/Communication (FR-006)

| Requirement | Description | Status |
|-------------|-------------|--------|
| FR-006.1 | Text-to-speech input | Implemented |
| FR-006.2 | Character limit validation (500 chars) | Implemented |
| FR-006.3 | Preset quick messages | Implemented |
| FR-006.4 | Speaking state indication | Implemented |

### 3.7 Connectivity Testing (FR-007)

| Requirement | Description | Status |
|-------------|-------------|--------|
| FR-007.1 | GCP function connectivity test | Implemented |
| FR-007.2 | Connection status display | Implemented |
| FR-007.3 | Manual retry capability | Implemented |

---

## 4. Non-Functional Requirements

### 4.1 Performance (NFR-001)

| Requirement | Target | Current Status |
|-------------|--------|----------------|
| NFR-001.1 | Initial page load < 3s | ~2s (acceptable) |
| NFR-001.2 | Command latency < 500ms | 200-500ms (acceptable) |
| NFR-001.3 | Status update interval ≤ 5s | 5s (implemented) |
| NFR-001.4 | Smooth UI transitions | Partial (basic transitions) |

### 4.2 Usability (NFR-002)

| Requirement | Description | Current Status |
|-------------|-------------|----------------|
| NFR-002.1 | Intuitive control layout | Implemented |
| NFR-002.2 | Keyboard shortcuts | Not Implemented |
| NFR-002.3 | Touch-friendly controls | Partial |
| NFR-002.4 | Responsive design | Partial (50/50 split only) |
| NFR-002.5 | Accessibility (WCAG 2.1) | Not Implemented |
| NFR-002.6 | Dark theme | Implemented |
| NFR-002.7 | Light theme option | Not Implemented |

### 4.3 Reliability (NFR-003)

| Requirement | Description | Current Status |
|-------------|-------------|----------------|
| NFR-003.1 | Error handling with user feedback | Implemented (toast notifications) |
| NFR-003.2 | Connection recovery | Partial (manual retry) |
| NFR-003.3 | State persistence | Not Implemented |
| NFR-003.4 | Offline mode | Not Implemented |

### 4.4 Security (NFR-004)

| Requirement | Description | Current Status |
|-------------|-------------|----------------|
| NFR-004.1 | API key authentication | Implemented |
| NFR-004.2 | HTTPS enforcement | Not Enforced |
| NFR-004.3 | User authentication | Not Implemented |
| NFR-004.4 | Audit logging | Not Implemented |
| NFR-004.5 | Rate limiting | Server-side only |

---

## 5. UI Component Inventory

### 5.1 Current Components

| Component | Purpose | Styling Approach |
|-----------|---------|------------------|
| `EV3StatusPanel` | Device monitoring dashboard | Tailwind utilities |
| `VehicleControls` | Movement control pad | Tailwind + styled-jsx |
| `TurretControls` | Turret operation controls | Tailwind + styled-jsx |
| `MapVisualization` | Map wrapper with controls | Tailwind utilities |
| `Map` | Leaflet map integration | Tailwind + inline styles |
| `CameraView` | Video stream placeholder | Tailwind utilities |
| `SpeechControls` | Text-to-speech interface | Tailwind utilities |
| `ConnectionTest` | GCP connectivity test | Tailwind utilities |

### 5.2 UI Patterns Identified

| Pattern | Usage | Consistency |
|---------|-------|-------------|
| Collapsible sections | EV3Status, Speech, Connection | Consistent |
| Status indicators (dots) | Multiple components | Consistent |
| Icon buttons | Controls, headers | Consistent |
| Range sliders | Speed/rotation controls | Custom styled-jsx |
| Toast notifications | User feedback | Consistent (react-hot-toast) |
| Card containers | All panels | `bg-gray-700 rounded-lg p-4` |

### 5.3 Color Usage Analysis

| Color | Semantic Use | Tailwind Class |
|-------|--------------|----------------|
| Blue (#3b82f6) | Primary, vehicle, active | `blue-400`, `blue-600` |
| Purple (#a855f7) | Turret, secondary | `purple-400`, `purple-600` |
| Green (#10b981) | Success, available | `green-400`, `green-500` |
| Red (#ef4444) | Error, stop, danger | `red-500`, `red-600` |
| Orange (#f59e0b) | Warning, scan mode | `orange-500`, `orange-600` |
| Gray | Background, borders, text | `gray-400` to `gray-900` |
| Yellow | Battery indicator | `yellow-400` |

---

## 6. Open Topics / Clarification Needed

### 6.1 Business/Product Questions

| ID | Topic | Question | Priority |
|----|-------|----------|----------|
| OT-001 | User Management | Is multi-user access required? | High |
| OT-002 | Robot Fleet | Will multiple robots be managed? | High |
| OT-003 | Historical Data | Should telemetry be stored and visualized? | Medium |
| OT-004 | Mobile Support | Is native mobile app planned or web-only? | Medium |
| OT-005 | Offline Operation | Should the app work without network? | Low |

### 6.2 Technical Questions

| ID | Topic | Question | Priority |
|----|-------|----------|----------|
| OT-006 | Camera Stream | What is the actual HLS stream source? | High |
| OT-007 | GPS Integration | Is real GPS data available from robot? | Medium |
| OT-008 | WebSocket | Should polling be replaced with real-time WebSocket? | Medium |
| OT-009 | State Management | Should Zustand be utilized (already installed)? | Low |
| OT-010 | Charting | Should Recharts be utilized (already installed)? | Low |

### 6.3 Design Questions

| ID | Topic | Question | Priority |
|----|-------|----------|----------|
| OT-011 | Theme | Is light mode support required? | Medium |
| OT-012 | Branding | Are specific brand colors required? | Medium |
| OT-013 | Accessibility | What WCAG level is required? | High |
| OT-014 | Responsiveness | What is the minimum supported viewport? | High |
| OT-015 | Internationalization | Is multi-language support needed? | Low |

---

## 7. Technology Stack Summary

### 7.1 Current Stack

| Category | Technology | Version |
|----------|------------|---------|
| Framework | Next.js (App Router) | 15.5.0 |
| UI Library | React | 19.1.0 |
| Language | TypeScript | ^5 |
| Styling | Tailwind CSS | ^4 |
| Icons | Heroicons | ^2.2.0 |
| Notifications | react-hot-toast | ^2.6.0 |
| Mapping | Leaflet + react-leaflet | ^1.9.4 / ^5.0.0 |
| Video | HLS.js | ^1.6.10 |
| State (unused) | Zustand | ^5.0.8 |
| Charts (unused) | Recharts | ^3.1.2 |
| UI (unused) | Headless UI | ^2.2.7 |

### 7.2 Backend Integration

| Service | Purpose | Authentication |
|---------|---------|----------------|
| GCP Cloud Functions | Robot command relay | API Key (X-API-Key) |
| EV3 Device | TCP socket connection | None (internal) |

---

## 8. Gap Analysis Summary

### 8.1 Missing from Modern Design System

| Gap | Impact | Recommendation |
|-----|--------|----------------|
| No design tokens | Inconsistent styling | Implement Material Design 3 tokens |
| No component library | Duplicate code | Adopt MUI or similar |
| No theme system | No theme switching | Implement theme context |
| No accessibility | Excludes users | Add WCAG 2.1 AA compliance |
| No responsive design | Poor mobile UX | Implement responsive breakpoints |
| Ad-hoc colors | Visual inconsistency | Standardize color palette |

### 8.2 Installed but Unused Dependencies

| Package | Intended Use | Recommendation |
|---------|--------------|----------------|
| Zustand | State management | Implement for cross-component state |
| Recharts | Data visualization | Add telemetry charts |
| Headless UI | Accessible components | Consider replacing with MUI |
| HLS.js | Video streaming | Implement actual camera stream |

---

## 9. Appendix

### A. File Structure

```
clients/web/
├── src/
│   ├── app/
│   │   ├── page.tsx           # Main dashboard
│   │   ├── layout.tsx         # Root layout
│   │   └── globals.css        # Global styles
│   ├── components/
│   │   ├── EV3StatusPanel.tsx
│   │   ├── MapVisualization.tsx
│   │   ├── Map.tsx
│   │   ├── CameraView.tsx
│   │   ├── VehicleControls.tsx
│   │   ├── TurretControls.tsx
│   │   ├── SpeechControls.tsx
│   │   └── ConnectionTest.tsx
│   └── lib/
│       └── robot-api.ts       # GCP API client
├── public/                    # Static assets
├── docs/                      # Documentation (this folder)
└── package.json
```

### B. API Endpoints

| Command | Method | Endpoint | Parameters |
|---------|--------|----------|------------|
| Forward | POST | `/controlRobot` | `{command: 'forward', speed: number}` |
| Backward | POST | `/controlRobot` | `{command: 'backward', speed: number}` |
| Turn Left | POST | `/controlRobot` | `{command: 'left', speed: number}` |
| Turn Right | POST | `/controlRobot` | `{command: 'right', speed: number}` |
| Stop | POST | `/controlRobot` | `{command: 'stop'}` |
| Turret Left | POST | `/controlRobot` | `{command: 'turret_left', speed, duration}` |
| Turret Right | POST | `/controlRobot` | `{command: 'turret_right', speed, duration}` |
| Stop Turret | POST | `/controlRobot` | `{command: 'stop_turret'}` |
| Get Status | POST | `/controlRobot` | `{command: 'get_status'}` |
| Speak | POST | `/controlRobot` | `{command: 'speak', text: string}` |

---

*Document generated through codebase analysis. Requires stakeholder review and validation.*
