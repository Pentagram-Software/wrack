# WRACK Control Center - Design System Architecture

> **Document Version**: 1.0  
> **Date**: March 2026  
> **Status**: Proposed Architecture

## 1. Executive Summary

This document describes the proposed architecture for implementing Material Design 3 (Material You) in the WRACK Control Center web application. The architecture focuses on establishing a scalable design system with Figma integration, design tokens, and a component library that ensures visual consistency and streamlines the design-to-development workflow.

---

## 2. Architecture Goals

### 2.1 Primary Goals

| Goal | Description | Success Criteria |
|------|-------------|------------------|
| **Design Consistency** | Unified visual language across all components | Zero ad-hoc color/spacing usage |
| **Figma Integration** | Bi-directional design-to-code workflow | Design changes reflected in code within hours |
| **Accessibility** | WCAG 2.1 AA compliance | Pass automated and manual a11y audits |
| **Theming** | Support for light/dark/custom themes | Theme switching without code changes |
| **Maintainability** | Easy to update and extend | Single source of truth for design decisions |

### 2.2 Secondary Goals

- Improve developer experience with typed components
- Reduce CSS bundle size through token-based styling
- Enable rapid prototyping and iteration
- Support future mobile/native applications through shared tokens

---

## 3. Architectural Overview

### 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FIGMA DESIGN                                    │
│  ┌─────────────────┐    ┌──────────────────┐    ┌───────────────────────┐  │
│  │  Material Theme │───►│  Figma Variables │───►│  MUI Sync Plugin      │  │
│  │  Builder Plugin │    │  (Design Tokens) │    │  (Code Export)        │  │
│  └─────────────────┘    └──────────────────┘    └───────────┬───────────┘  │
└────────────────────────────────────────────────────────────┬────────────────┘
                                                              │ Export
                                                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CODE REPOSITORY                                    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      DESIGN TOKENS LAYER                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌────────────────────────┐  │   │
│  │  │ tokens/       │  │ colors.ts     │  │ typography.ts          │  │   │
│  │  │  ├─ base.ts   │  │ spacing.ts    │  │ elevation.ts           │  │   │
│  │  │  └─ semantic  │  │ radius.ts     │  │ motion.ts              │  │   │
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

### 3.2 Technology Stack Comparison

| Aspect | Current | Proposed | Rationale |
|--------|---------|----------|-----------|
| UI Components | Custom + Heroicons | MUI v6 + Heroicons | Battle-tested, accessible, MD3-ready |
| Styling | Tailwind utilities | Tailwind + MUI Theme | Design tokens integration |
| Design Tokens | CSS variables (minimal) | Comprehensive token system | Figma sync, consistency |
| Theming | Dark-only (hardcoded) | ThemeProvider | Light/dark/custom support |
| Figma Integration | None | MUI Sync Plugin | Design-code synchronization |

---

## 4. Design Tokens Architecture

### 4.1 Token Hierarchy

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

### 4.2 Material Design 3 Color System

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

### 4.3 Token File Structure

```
src/
└── design-system/
    ├── tokens/
    │   ├── index.ts              # Re-exports all tokens
    │   ├── colors.ts             # Color palettes and semantic colors
    │   ├── typography.ts         # Font families, sizes, weights
    │   ├── spacing.ts            # Spacing scale
    │   ├── radius.ts             # Border radius scale
    │   ├── elevation.ts          # Shadow definitions
    │   └── motion.ts             # Animation/transition tokens
    │
    ├── themes/
    │   ├── index.ts              # Theme exports
    │   ├── lightTheme.ts         # Light theme configuration
    │   ├── darkTheme.ts          # Dark theme configuration
    │   └── types.ts              # Theme type definitions
    │
    ├── components/
    │   ├── index.ts              # Component exports
    │   ├── Button/               # Each component in own folder
    │   │   ├── Button.tsx
    │   │   ├── Button.styles.ts
    │   │   └── index.ts
    │   ├── Card/
    │   ├── StatusIndicator/
    │   ├── ControlPad/
    │   └── ... 
    │
    └── providers/
        ├── ThemeProvider.tsx     # Theme context provider
        └── index.ts
```

---

## 5. Figma Integration Architecture

### 5.1 Figma-to-Code Workflow

```
┌───────────────────────────────────────────────────────────────────┐
│                        FIGMA WORKSPACE                             │
│                                                                    │
│  1. Material Theme Builder Plugin                                  │
│     └── Generate MD3 color schemes from source color               │
│                                                                    │
│  2. Figma Variables (Local Variables)                              │
│     ├── Color Variables (primitives + semantic)                   │
│     ├── Spacing Variables                                          │
│     ├── Typography Styles                                          │
│     └── Effect Styles (elevation)                                  │
│                                                                    │
│  3. MUI Design Kit (Component Library)                             │
│     └── Pre-built Material UI components using variables           │
│                                                                    │
│  4. MUI Sync Plugin                                                │
│     └── Export theme code directly from Figma                      │
│                                                                    │
└───────────────────┬───────────────────────────────────────────────┘
                    │
                    │ Export/Sync
                    ▼
┌───────────────────────────────────────────────────────────────────┐
│                        CODE REPOSITORY                             │
│                                                                    │
│  5. Generated Theme File                                           │
│     └── src/design-system/themes/figmaTheme.ts                    │
│                                                                    │
│  6. Tailwind CSS Variables Integration                             │
│     └── Map MUI theme tokens to CSS custom properties             │
│                                                                    │
│  7. Component Implementation                                       │
│     └── Use theme tokens in styled components                      │
│                                                                    │
└───────────────────────────────────────────────────────────────────┘
```

### 5.2 Figma Variable Structure

```
📁 WRACK Design System (Figma File)
│
├── 📁 Variables (Local Variables)
│   │
│   ├── 📁 Color Primitives
│   │   ├── blue/10, blue/20, ... blue/100
│   │   ├── gray/10, gray/20, ... gray/100
│   │   ├── green/10, ... green/100
│   │   ├── red/10, ... red/100
│   │   ├── purple/10, ... purple/100
│   │   └── orange/10, ... orange/100
│   │
│   ├── 📁 Semantic Colors
│   │   ├── primary, on-primary
│   │   ├── primary-container, on-primary-container
│   │   ├── secondary, on-secondary
│   │   ├── tertiary, on-tertiary
│   │   ├── surface, surface-container
│   │   ├── on-surface, on-surface-variant
│   │   ├── error, on-error
│   │   └── outline, outline-variant
│   │
│   ├── 📁 Spacing
│   │   └── space-0, space-1, space-2, ... space-24
│   │
│   └── 📁 Radius
│       └── radius-none, radius-sm, radius-md, radius-lg, radius-xl
│
├── 📁 Typography Styles
│   ├── Display/Large, Display/Medium, Display/Small
│   ├── Headline/Large, Headline/Medium, Headline/Small
│   ├── Title/Large, Title/Medium, Title/Small
│   ├── Body/Large, Body/Medium, Body/Small
│   └── Label/Large, Label/Medium, Label/Small
│
├── 📁 Effect Styles
│   └── Elevation/1, Elevation/2, Elevation/3, Elevation/4, Elevation/5
│
└── 📁 Components (using variables)
    ├── Buttons
    ├── Cards
    ├── Inputs
    ├── Navigation
    └── Custom (EV3-specific)
```

### 5.3 MUI Theme Integration

```typescript
// src/design-system/themes/muiTheme.ts

import { createTheme } from '@mui/material/styles';
import { lightThemeColors, darkThemeColors } from '../tokens/colors';
import { typography } from '../tokens/typography';
import { spacing } from '../tokens/spacing';

export const createWrackTheme = (mode: 'light' | 'dark') => {
  const colors = mode === 'light' ? lightThemeColors : darkThemeColors;
  
  return createTheme({
    palette: {
      mode,
      primary: {
        main: colors.primary,
        contrastText: colors.onPrimary,
      },
      secondary: {
        main: colors.secondary,
        contrastText: colors.onSecondary,
      },
      error: {
        main: colors.error,
        contrastText: colors.onError,
      },
      background: {
        default: colors.surface,
        paper: colors.surfaceContainer,
      },
      text: {
        primary: colors.onSurface,
        secondary: colors.onSurfaceVariant,
      },
    },
    typography: {
      fontFamily: typography.fontFamily.sans,
      // ... typography scale
    },
    spacing: (factor: number) => `${spacing.base * factor}px`,
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

## 6. Component Architecture

### 6.1 Component Hierarchy

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

### 6.2 Component Structure Example

```typescript
// src/design-system/components/StatusIndicator/StatusIndicator.tsx

import { Box } from '@mui/material';
import { useTheme } from '@mui/material/styles';
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
  const theme = useTheme();
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

## 7. Tailwind + MUI Integration Strategy

### 7.1 CSS Variables Bridge

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

### 7.2 Usage Guidelines

| Use Case | Recommended Approach |
|----------|---------------------|
| Complex interactive components | MUI components |
| Simple layout utilities | Tailwind classes |
| Custom domain components | MUI + Tailwind hybrid |
| Typography | MUI Typography component |
| Spacing | Tailwind utilities or MUI sx prop |
| Colors | Design tokens via CSS variables |

---

## 8. State Management Integration

### 8.1 Theme State with Zustand

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
    (set, get) => ({
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

---

## 9. Accessibility Architecture

### 9.1 A11y Requirements

| Requirement | Implementation |
|-------------|----------------|
| Color contrast | Use MD3 semantic colors (built-in 4.5:1 ratio) |
| Focus indicators | MUI built-in focus-visible styling |
| Keyboard navigation | MUI components are keyboard accessible |
| Screen reader support | Proper ARIA labels and roles |
| Reduced motion | Respect `prefers-reduced-motion` |
| Touch targets | Minimum 44x44px interactive areas |

### 9.2 Focus Management Example

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

## 10. Migration Path from Current Architecture

### 10.1 Coexistence Strategy

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

### 10.2 Component Migration Example

```typescript
// BEFORE (current)
<div className="w-2 h-2 rounded-full bg-green-500" />

// AFTER (design system)
<StatusIndicator status="online" size="small" />
```

---

## 11. Build and Performance Considerations

### 11.1 Bundle Optimization

| Strategy | Implementation |
|----------|----------------|
| Tree shaking | Import MUI components individually |
| Code splitting | Lazy load non-critical components |
| CSS optimization | Use Tailwind's purge for utilities |
| Font optimization | Continue using Next.js font optimization |

### 11.2 Import Pattern

```typescript
// Preferred: Named imports for tree shaking
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';

// Avoid: Importing entire library
// import { Button, Card } from '@mui/material';
```

---

## 12. Testing Strategy

### 12.1 Design System Testing

| Test Type | Tools | Coverage |
|-----------|-------|----------|
| Unit tests | Jest + Testing Library | Component behavior |
| Visual regression | Storybook + Chromatic | UI consistency |
| A11y testing | jest-axe, Lighthouse | WCAG compliance |
| Theme testing | Custom theme tests | Light/dark modes |

### 12.2 Storybook Integration

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

## 13. Appendix

### A. Dependency Additions

```json
{
  "dependencies": {
    "@mui/material": "^6.0.0",
    "@mui/system": "^6.0.0",
    "@emotion/react": "^11.11.0",
    "@emotion/styled": "^11.11.0",
    "@mui/icons-material": "^6.0.0"
  },
  "devDependencies": {
    "@storybook/react": "^8.0.0",
    "@storybook/addon-a11y": "^8.0.0",
    "jest-axe": "^8.0.0"
  }
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

### C. References

- [Material Design 3 Guidelines](https://m3.material.io/)
- [MUI Documentation](https://mui.com/)
- [MUI Sync Plugin](https://mui.com/blog/introducing-sync-plugin/)
- [Figma Variables](https://help.figma.com/hc/en-us/articles/15339657135383-Guide-to-variables-in-Figma)
- [Tailwind CSS](https://tailwindcss.com/docs)

---

*This architecture document provides the technical foundation for implementing Material Design 3 in the WRACK Control Center. It should be reviewed and refined during the implementation phases.*
