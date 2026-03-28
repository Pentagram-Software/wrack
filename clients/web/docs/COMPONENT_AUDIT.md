# Component Audit — Tailwind → MUI / MD3 Migration

**Date:** 2026-03-28  
**Scope:** `clients/web/src/components/` + `src/app/page.tsx`  
**Purpose:** P0.5 — Document current component inventory for migration planning

---

## Color Token Mapping Reference

All Tailwind color utilities should be replaced with the corresponding MD3 design token:

| Tailwind Class | MD3 Token | Usage |
|---|---|---|
| `bg-gray-900` | `surface` | Page background |
| `bg-gray-800` | `surfaceContainer` | Section backgrounds |
| `bg-gray-700` | `surfaceContainerHigh` | Card / panel backgrounds |
| `bg-gray-600` | `surfaceContainerHighest` | Input / item backgrounds |
| `text-white` | `onSurface` | Primary text |
| `text-gray-300` | `onSurfaceVariant` | Secondary text |
| `text-gray-400` | `outline` | Placeholder / hint text |
| `border-gray-600` / `border-gray-700` | `outlineVariant` | Dividers / borders |
| `bg-blue-600` / `hover:bg-blue-700` | `primary` / `primaryContainer` | Primary actions |
| `text-blue-400` | `primary` | Primary text accents |
| `bg-red-600` / `hover:bg-red-700` | `error` | Destructive / stop actions |
| `bg-green-500` / `bg-green-600` | `tertiary` | Connected / success states |
| `text-green-400` | `tertiary` | Connected text |
| `bg-gray-500` / `text-gray-400` | `outline` | Disconnected / inactive |
| `bg-purple-600` | `secondary` | Turret / secondary actions |
| `text-purple-400` | `secondary` | Turret text accents |
| `bg-orange-500` / `bg-orange-600` | `warning` (custom token) | Scan / warning states |
| `text-yellow-400` | `warning` (custom token) | Battery / warning icons |

---

## Component Inventory

### 1. `page.tsx` — Main Dashboard Layout

**Complexity:** Medium  
**Phase:** Phase 4 (P4.1 + P4.2)

| Area | Current | MUI Replacement |
|---|---|---|
| Page background | `min-h-screen bg-gray-900 text-white` | `Box` with `bgcolor="background.default"` |
| Header | `bg-gray-800 border-b border-gray-700 p-4` | `AppBar` + `Toolbar` |
| Header title | `text-2xl font-bold text-blue-400` | `Typography variant="h5"` with `color="primary"` |
| Left panel | `w-1/2 bg-gray-800 border-r border-gray-700 p-6` | `Box` / `Grid` with design tokens |
| Right panel | `w-1/2 flex flex-col` | `Box` with `display="flex" flexDirection="column"` |
| Camera toggle | `bg-blue-600` / `bg-red-600` inline button | `Button variant="contained"` / `color="error"` |

**Hardcoded colours:** `gray-900`, `gray-800`, `gray-700`, `blue-400`, `gray-400`, `blue-600`, `red-600`  
**styled-jsx:** No  
**Sub-components needed:** MUI `AppBar`, `Toolbar`, `Box`, `Grid`

---

### 2. `EV3StatusPanel.tsx` — Device Monitoring

**Complexity:** High  
**Phase:** Phase 3 (P3.12) + Phase 4 (P4.5)

| Area | Current | MUI / Design System Replacement |
|---|---|---|
| Section wrapper | `bg-gray-700 rounded-lg p-4` | `Card variant="elevated"` |
| Collapsible sections | Manual `useState` + chevron icons | `CollapsibleSection` (P3.7) |
| Status dot | `w-3 h-3 rounded-full bg-green-500/red-500` | `StatusIndicator` (P2.4) |
| Motor availability dot | `w-2 h-2 rounded-full bg-green-500/gray-500` | `StatusIndicator size="small"` |
| Motor item row | `bg-gray-600 rounded` item with manual layout | `MotorCard` (P3.3) |
| Sensor item row | `bg-gray-600 rounded` item with manual layout | `SensorCard` (P3.4) |
| Brick info (battery, CPU, IP) | Manual grid layout | `DeviceInfoCard` (P3.5) |
| Status text (`text-green-400` / `text-gray-400`) | Computed Tailwind | `StatusIndicator label` prop |

**Hardcoded colours:** `gray-700`, `gray-600`, `green-500`, `red-500`, `gray-500`, `gray-400`, `gray-300`, `white`, `blue-400`, `purple-400`, `yellow-400`, `blue-300`  
**styled-jsx:** No  
**Sub-components needed:** `CollapsibleSection`, `DeviceInfoCard`, `MotorCard`, `SensorCard`, `StatusIndicator`

---

### 3. `VehicleControls.tsx` — Movement Controls

**Complexity:** Medium  
**Phase:** Phase 3 (P3.10)

| Area | Current | MUI / Design System Replacement |
|---|---|---|
| Panel wrapper | `bg-gray-700 rounded-lg p-4` | `Card variant="elevated"` |
| Direction buttons (D-pad) | Manual 3×3 CSS grid with Tailwind | `ControlPad` (P3.1) |
| Active direction button | `bg-blue-600 text-white scale-95` | `ControlPad` internal active state |
| Emergency stop button | `bg-red-600 hover:bg-red-700 text-white` | `EmergencyStop` (P3.8) |
| Speed slider | `<input type="range">` + styled-jsx thumb | `SpeedSlider` (P3.2) |
| Speed label | `text-blue-400 font-mono` | `Typography` with `color="primary"` |
| Status dot | `bg-green-500 animate-pulse` / `bg-gray-500` | `StatusIndicator pulse` prop |

**Hardcoded colours:** `gray-700`, `gray-600`, `gray-500`, `blue-600`, `red-600`, `gray-300`, `gray-400`, `blue-400`, `green-500`  
**styled-jsx:** **YES** — slider thumb (`#3b82f6`). Remove in P4.3.  
**Sub-components needed:** `ControlPad`, `SpeedSlider`, `EmergencyStop`

---

### 4. `TurretControls.tsx` — Turret Operations

**Complexity:** Medium  
**Phase:** Phase 3 (P3.11)

| Area | Current | MUI / Design System Replacement |
|---|---|---|
| Panel wrapper | `bg-gray-700 rounded-lg p-4` | `Card variant="elevated"` |
| Left/right rotation buttons | Manual Tailwind buttons | `ControlPad` left/right variant or `IconButton` |
| Center button | `bg-blue-600` inline | `Button variant="tonal"` |
| Scan toggle button | `bg-orange-600` / `bg-green-600` | `Button` with `color="warning"` / `color="success"` |
| Angle indicator | Custom `div` with `transform: rotate()` | `AngleIndicator` (P3.6) |
| Rotation speed slider | `<input type="range">` + styled-jsx thumb | `SpeedSlider` (P3.2) |
| Status dot | `bg-orange-500` / `bg-purple-500` / `bg-gray-500` | `StatusIndicator` with state prop |

**Hardcoded colours:** `gray-700`, `gray-600`, `purple-600`, `blue-600`, `green-600`, `orange-600`, `gray-300`, `gray-400`, `purple-400`, `orange-500`, `purple-500`  
**styled-jsx:** **YES** — slider thumb (`#a855f7`). Remove in P4.3.  
**Sub-components needed:** `SpeedSlider`, `AngleIndicator`, `ControlPad` (rotation variant)

---

### 5. `MapVisualization.tsx` — Terrain Map

**Complexity:** High  
**Phase:** Phase 4 (P4.1 — layout only; Leaflet stays as-is)

| Area | Current | MUI / Design System Replacement |
|---|---|---|
| Outer wrapper | `h-full flex flex-col bg-gray-800` | `Box` with design tokens |
| Header bar | `bg-gray-700 border-b border-gray-600 p-3` | `Toolbar` / `Box` with `surfaceContainerHigh` |
| Mode toggle button | `bg-green-600` / `bg-gray-600` Tailwind | `Button variant="outlined"` / `"contained"` |
| Trail toggle button | `bg-blue-600` / `bg-gray-600` Tailwind | `Button variant="outlined"` / `"contained"` |
| Map container | `flex-1 relative` | `Box flexGrow={1}` |
| Legend bar | `bg-gray-700 border-t border-gray-600 p-3` | `Box` with `surfaceContainerHigh` |
| Legend dots | `w-3 h-3 bg-blue-500/green-500/red-500/yellow-500` | `StatusIndicator` or small coloured `Chip` |
| Map loading state | Manual spinner Tailwind | MUI `CircularProgress` |

**Hardcoded colours:** `gray-800`, `gray-700`, `gray-600`, `blue-400`, `green-600`, `gray-300`, `blue-600`, `blue-500`, `green-500`, `red-500`, `yellow-500`  
**styled-jsx:** No  
**Note:** Leaflet-specific CSS (from `Map.tsx`) must stay in a global stylesheet, not component-scoped.  
**Sub-components needed:** None new; uses MUI layout primitives only

---

### 6. `CameraView.tsx` — Video Feed

**Complexity:** Low  
**Phase:** Phase 4 (P4.1 — layout)

| Area | Current | MUI / Design System Replacement |
|---|---|---|
| Outer wrapper | `h-full flex flex-col bg-gray-800` | `Box` with design tokens |
| Header bar | `bg-gray-700 border-b border-gray-600 p-3` | `Toolbar` / `Box` |
| Status dot | `w-2 h-2 rounded-full bg-green-500/yellow-500/red-500` | `StatusIndicator` |
| Stream toggle button | `bg-green-600` / `bg-red-600` | `Button variant="contained"` |
| Close button | `hover:bg-gray-600 text-gray-400` | `IconButton` |
| Connecting spinner | Manual `animate-spin border-b-2 border-blue-400` | MUI `CircularProgress` |
| Footer info bar | `bg-gray-700 border-t border-gray-600 p-2` | `Box` with `surfaceContainerHigh` |

**Hardcoded colours:** `gray-800`, `gray-700`, `gray-600`, `blue-400`, `green-400`, `yellow-400`, `red-400`, `green-500`, `yellow-500`, `red-500`, `green-600`, `red-600`  
**styled-jsx:** No  
**Sub-components needed:** `StatusIndicator`, MUI `IconButton`, `CircularProgress`

---

### 7. `ConnectionTest.tsx` — GCP Connectivity Diagnostic

**Complexity:** Low  
**Phase:** Phase 4 (P4.1 — layout)

| Area | Current | MUI / Design System Replacement |
|---|---|---|
| Panel wrapper | `bg-gray-700 rounded-lg p-4 mb-4` | `Card variant="elevated"` |
| Collapse toggle | Manual chevron + `useState` | `CollapsibleSection` or MUI `Accordion` |
| Status dot | `w-2 h-2 rounded-full bg-green-500/red-500/gray-500` | `StatusIndicator size="small"` |
| Test button | `bg-blue-600 hover:bg-blue-700` / disabled `bg-gray-600` | `Button variant="contained"` |
| Result pre block | `bg-gray-800 rounded p-3 text-gray-400` | `Box` with `surfaceContainer` + `Typography variant="mono"` |

**Hardcoded colours:** `gray-700`, `gray-800`, `gray-600`, `green-500`, `red-500`, `blue-600`, `blue-700`, `gray-400`, `blue-300`, `red-400`  
**styled-jsx:** No  
**Sub-components needed:** `StatusIndicator`, MUI `Button`, `CollapsibleSection`

---

### 8. `SpeechControls.tsx` — EV3 Text-to-Speech

**Complexity:** Low  
**Phase:** Phase 4 (P4.1 — layout)

> **Note:** This component was not in the original PEN-100 scope but exists in the project and must be included in migration.

| Area | Current | MUI / Design System Replacement |
|---|---|---|
| Panel wrapper | `bg-gray-800 rounded-lg shadow-lg` | `Card variant="elevated"` |
| Header bar | `bg-gray-700 hover:bg-gray-600` collapsible | `CollapsibleSection` (P3.7) |
| Header icon | `text-blue-400` Heroicons | MUI icon or Heroicons with token colour |
| Textarea | `bg-gray-700 border border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500` | `TextField variant="outlined" multiline` (P2.6) |
| Character counter | Manual `text-yellow-400` threshold | `TextField helperText` with MUI |
| Preset buttons | `bg-gray-700 hover:bg-gray-600` grid | `Button variant="tonal"` grid |
| Speak button | `bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600` | `Button variant="contained" loading` |

**Hardcoded colours:** `gray-800`, `gray-700`, `gray-600`, `blue-400`, `gray-300`, `gray-400`, `yellow-400`, `blue-600`, `blue-700`  
**styled-jsx:** No  
**Sub-components needed:** `TextField`, `CollapsibleSection`, MUI `Button`

---

## Migration Complexity Summary

| Component | Complexity | Phase | styled-jsx | New DS Components Required |
|---|---|---|---|---|
| `page.tsx` | Medium | Ph4 | No | `AppBar`, `Box`, `Grid` |
| `EV3StatusPanel.tsx` | **High** | Ph3+4 | No | `CollapsibleSection`, `DeviceInfoCard`, `MotorCard`, `SensorCard`, `StatusIndicator` |
| `VehicleControls.tsx` | Medium | Ph3 | **Yes** | `ControlPad`, `SpeedSlider`, `EmergencyStop` |
| `TurretControls.tsx` | Medium | Ph3 | **Yes** | `SpeedSlider`, `AngleIndicator`, `ControlPad` |
| `MapVisualization.tsx` | **High** | Ph4 | No | MUI layout only; Leaflet CSS stays global |
| `CameraView.tsx` | Low | Ph4 | No | `StatusIndicator`, `IconButton`, `CircularProgress` |
| `ConnectionTest.tsx` | Low | Ph4 | No | `StatusIndicator`, `Button`, `CollapsibleSection` |
| `SpeechControls.tsx` | Low | Ph4 | No | `TextField`, `CollapsibleSection`, `Button` |

**Total components with styled-jsx to remove:** 2 (`VehicleControls`, `TurretControls`)  
**Total new design system components required:** 10 (all covered by Phase 2–3 tickets)
