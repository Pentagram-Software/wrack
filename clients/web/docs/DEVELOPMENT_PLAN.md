# WRACK Control Center - Design System Development Plan

> **Document Version**: 1.0  
> **Date**: March 2026  
> **Status**: Proposed Plan

## 1. Executive Summary

This development plan outlines the phased approach to introduce Material Design 3 (MD3) into the WRACK Control Center web application. The plan prioritizes incremental adoption, minimizing disruption while establishing a robust design system foundation.

---

## 2. Implementation Phases Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          PHASE 0: PREPARATION                            │
│  • Team alignment • Tooling setup • Figma workspace • Design audit      │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          PHASE 1: FOUNDATION                             │
│  • Install MUI • Create tokens • ThemeProvider • CSS variable bridge    │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          PHASE 2: CORE COMPONENTS                        │
│  • Button variants • Card • StatusIndicator • Typography • Icons        │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          PHASE 3: DOMAIN COMPONENTS                      │
│  • ControlPad • MotorCard • SensorCard • CollapsibleSection             │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          PHASE 4: FULL MIGRATION                         │
│  • Migrate all pages • Remove ad-hoc styles • A11y audit • Polish       │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          PHASE 5: FIGMA INTEGRATION                      │
│  • Figma Design Kit • MUI Sync Plugin • Design handoff workflow         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Phase 0: Preparation

### 3.1 Objectives

- Establish team understanding of Material Design 3 principles
- Set up necessary tooling and environments
- Create Figma workspace for design collaboration
- Audit existing components for migration planning

### 3.2 Tasks

| Task | Description | Owner | Dependencies |
|------|-------------|-------|--------------|
| P0.1 | Review MD3 documentation and guidelines | Dev Team | None |
| P0.2 | Install and configure Storybook for component documentation | Developer | None |
| P0.3 | Create Figma workspace with Material Theme Builder | Designer | Figma license |
| P0.4 | Generate initial MD3 color palette from brand colors | Designer | P0.3 |
| P0.5 | Document current component inventory | Developer | None |
| P0.6 | Set up visual regression testing (Chromatic or similar) | Developer | P0.2 |

### 3.3 Deliverables

- [ ] Storybook instance configured and accessible
- [ ] Figma workspace with MD3 theme configured
- [ ] Component audit document
- [ ] Visual regression baseline established

### 3.4 Technical Setup Commands

```bash
# Install Storybook
npx storybook@latest init

# Add a11y addon
npm install @storybook/addon-a11y --save-dev

# Add interactions testing
npm install @storybook/test --save-dev
```

---

## 4. Phase 1: Foundation

### 4.1 Objectives

- Install MUI dependencies
- Create design token structure
- Implement ThemeProvider with light/dark mode support
- Bridge MUI theme with Tailwind CSS variables

### 4.2 Tasks

| Task | Description | Owner | Dependencies |
|------|-------------|-------|--------------|
| P1.1 | Install MUI v6 and Emotion dependencies | Developer | None |
| P1.2 | Create `src/design-system/tokens/` structure | Developer | P1.1 |
| P1.3 | Define color tokens matching MD3 specification | Developer | P0.4 |
| P1.4 | Define typography, spacing, and elevation tokens | Developer | P1.2 |
| P1.5 | Create `ThemeProvider` component | Developer | P1.3, P1.4 |
| P1.6 | Integrate ThemeProvider in root layout | Developer | P1.5 |
| P1.7 | Create CSS variable bridge for Tailwind integration | Developer | P1.5 |
| P1.8 | Implement theme toggle (light/dark/system) | Developer | P1.6 |
| P1.9 | Add Zustand store for theme persistence | Developer | P1.8 |

### 4.3 Deliverables

- [ ] MUI dependencies installed
- [ ] Design tokens defined and exported
- [ ] ThemeProvider wrapping application
- [ ] Theme toggle functional
- [ ] Existing app still works (no regression)

### 4.4 Implementation Details

#### P1.1: Install Dependencies

```bash
cd clients/web

# Install MUI core
npm install @mui/material @emotion/react @emotion/styled

# Install MUI icons (optional, already have Heroicons)
npm install @mui/icons-material

# Install MUI lab for experimental components
npm install @mui/lab
```

#### P1.2: Token Structure

```
src/design-system/
├── tokens/
│   ├── index.ts
│   ├── colors.ts
│   ├── typography.ts
│   ├── spacing.ts
│   ├── radius.ts
│   ├── elevation.ts
│   └── motion.ts
├── themes/
│   ├── index.ts
│   ├── lightTheme.ts
│   ├── darkTheme.ts
│   └── types.ts
├── providers/
│   └── ThemeProvider.tsx
└── index.ts
```

#### P1.5: ThemeProvider Implementation

```typescript
// src/design-system/providers/ThemeProvider.tsx

'use client';

import { ThemeProvider as MuiThemeProvider, CssBaseline } from '@mui/material';
import { ReactNode, useMemo } from 'react';
import { useThemeStore } from '@/stores/themeStore';
import { createWrackTheme } from '../themes';

interface ThemeProviderProps {
  children: ReactNode;
}

export const ThemeProvider = ({ children }: ThemeProviderProps) => {
  const { resolvedMode } = useThemeStore();
  
  const theme = useMemo(
    () => createWrackTheme(resolvedMode),
    [resolvedMode]
  );

  return (
    <MuiThemeProvider theme={theme}>
      <CssBaseline />
      {children}
    </MuiThemeProvider>
  );
};
```

#### P1.6: Root Layout Integration

```typescript
// src/app/layout.tsx

import { ThemeProvider } from '@/design-system/providers';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <ThemeProvider>
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
```

### 4.5 Success Criteria

| Criterion | Validation |
|-----------|------------|
| MUI installed | `npm ls @mui/material` shows version |
| Theme switching works | Toggle between light/dark modes |
| No visual regression | Existing components render correctly |
| Tokens accessible | Can import and use tokens in components |

---

## 5. Phase 2: Core Components

### 5.1 Objectives

- Create foundational design system components
- Establish component patterns and documentation
- Build Storybook stories for all new components

### 5.2 Component Priority List

| Priority | Component | Replaces | Complexity |
|----------|-----------|----------|------------|
| 1 | `Button` (variants) | Tailwind button classes | Low |
| 2 | `IconButton` | Heroicon buttons | Low |
| 3 | `Card` | `bg-gray-700 rounded-lg p-4` | Low |
| 4 | `StatusIndicator` | Status dots | Low |
| 5 | `Typography` | Text with utility classes | Low |
| 6 | `TextField` | textarea/input elements | Medium |
| 7 | `Slider` | Custom range inputs | Medium |
| 8 | `Snackbar` | react-hot-toast | Medium |

### 5.3 Tasks

| Task | Description | Owner | Dependencies |
|------|-------------|-------|--------------|
| P2.1 | Create Button component with MD3 variants | Developer | P1 complete |
| P2.2 | Create IconButton wrapper | Developer | P2.1 |
| P2.3 | Create Card component | Developer | P1 complete |
| P2.4 | Create StatusIndicator component | Developer | P1 complete |
| P2.5 | Create Typography presets | Developer | P1 complete |
| P2.6 | Customize TextField component | Developer | P2.5 |
| P2.7 | Create Slider (replacing styled-jsx sliders) | Developer | P1 complete |
| P2.8 | Configure Snackbar to replace toast | Developer | P1 complete |
| P2.9 | Write Storybook stories for all components | Developer | P2.1-P2.8 |
| P2.10 | Add unit tests for component behavior | Developer | P2.1-P2.8 |

### 5.4 Component Specifications

#### Button Variants

```typescript
// Design system should support these variants:
<Button variant="filled">Primary Action</Button>
<Button variant="outlined">Secondary Action</Button>
<Button variant="text">Tertiary Action</Button>
<Button variant="elevated">Elevated Action</Button>
<Button variant="tonal">Tonal Action</Button>

// Sizes
<Button size="small">Small</Button>
<Button size="medium">Medium</Button>
<Button size="large">Large</Button>

// With icons
<Button startIcon={<PlayIcon />}>Start</Button>
<Button endIcon={<ChevronRightIcon />}>Next</Button>
```

#### Card Variants

```typescript
// Card types matching MD3
<Card variant="filled">...</Card>      // Filled surface
<Card variant="outlined">...</Card>    // Outlined border
<Card variant="elevated">...</Card>    // With shadow

// With clickable behavior
<Card onClick={handleClick} hoverable>
  ...
</Card>
```

#### StatusIndicator

```typescript
// Status types
<StatusIndicator status="online" />    // Green
<StatusIndicator status="offline" />   // Red
<StatusIndicator status="warning" />   // Orange
<StatusIndicator status="inactive" />  // Gray

// With pulse animation
<StatusIndicator status="online" pulse />

// With label
<StatusIndicator status="online" label="Connected" />
```

### 5.5 Deliverables

- [ ] All 8 core components implemented
- [ ] Storybook stories for each component
- [ ] Unit tests passing
- [ ] Components exported from design-system index

---

## 6. Phase 3: Domain Components

### 6.1 Objectives

- Create EV3-specific composite components
- Migrate existing components to use design system
- Maintain backwards compatibility during migration

### 6.2 Component List

| Component | Description | Based On |
|-----------|-------------|----------|
| `ControlPad` | D-pad style movement controls | VehicleControls |
| `SpeedSlider` | Speed control with percentage display | Current range input |
| `MotorCard` | Single motor status display | EV3StatusPanel motor item |
| `SensorCard` | Single sensor status display | EV3StatusPanel sensor item |
| `DeviceInfoCard` | EV3 brick status overview | EV3StatusPanel header |
| `AngleIndicator` | Visual angle display for turret | TurretControls angle viz |
| `CollapsibleSection` | Expandable panel with header | Current collapsible pattern |
| `EmergencyStop` | Prominent stop button | VehicleControls stop |

### 6.3 Tasks

| Task | Description | Owner | Dependencies |
|------|-------------|-------|--------------|
| P3.1 | Create ControlPad component | Developer | P2 complete |
| P3.2 | Create SpeedSlider component | Developer | P2.7 |
| P3.3 | Create MotorCard component | Developer | P2.3, P2.4 |
| P3.4 | Create SensorCard component | Developer | P2.3, P2.4 |
| P3.5 | Create DeviceInfoCard component | Developer | P2.3 |
| P3.6 | Create AngleIndicator component | Developer | P2 complete |
| P3.7 | Create CollapsibleSection component | Developer | P2.3 |
| P3.8 | Create EmergencyStop component | Developer | P2.1 |
| P3.9 | Write Storybook stories | Developer | P3.1-P3.8 |
| P3.10 | Migrate VehicleControls to use ControlPad | Developer | P3.1, P3.2 |
| P3.11 | Migrate TurretControls to use new components | Developer | P3.1, P3.6 |
| P3.12 | Migrate EV3StatusPanel to use new cards | Developer | P3.3-P3.5 |

### 6.4 Migration Strategy

For each existing component:

1. Create new design system component
2. Write stories and tests
3. Update existing component to use new sub-components
4. Verify no visual regression
5. Remove old inline styles

Example migration:

```typescript
// BEFORE: EV3StatusPanel motor display
<div className="flex items-center space-x-3">
  <div className={`w-8 h-8 ${motor.available ? 'bg-blue-500' : 'bg-gray-500'} rounded`}>
    ⚙️
  </div>
  <div>
    <div className="text-white font-medium">{motor.name}</div>
    <div className="text-gray-300 text-sm">{motor.port}</div>
  </div>
  <div className={`w-2 h-2 rounded-full ${getStatusBg(motor.available)}`} />
</div>

// AFTER: Using MotorCard
<MotorCard
  name={motor.name}
  port={motor.port}
  available={motor.available}
  angle={motor.angle}
  speed={motor.speed}
  stalled={motor.stalled}
/>
```

### 6.5 Deliverables

- [ ] All 8 domain components implemented
- [ ] Existing components migrated
- [ ] No visual regression
- [ ] Storybook stories complete

---

## 7. Phase 4: Full Migration

### 7.1 Objectives

- Complete migration of all pages and layouts
- Remove all ad-hoc Tailwind color/spacing usage
- Conduct accessibility audit and fixes
- Final polish and optimization

### 7.2 Tasks

| Task | Description | Owner | Dependencies |
|------|-------------|-------|--------------|
| P4.1 | Migrate main page layout | Developer | P3 complete |
| P4.2 | Migrate header component | Developer | P2 complete |
| P4.3 | Update globals.css to use design tokens | Developer | P1.7 |
| P4.4 | Remove styled-jsx from components | Developer | P2.7 |
| P4.5 | Audit and replace all hardcoded colors | Developer | P4.1-P4.4 |
| P4.6 | Audit and replace all hardcoded spacing | Developer | P4.1-P4.4 |
| P4.7 | Run Lighthouse accessibility audit | Developer | P4.1-P4.6 |
| P4.8 | Fix accessibility issues | Developer | P4.7 |
| P4.9 | Add keyboard navigation to controls | Developer | P4.8 |
| P4.10 | Test with screen reader | Developer | P4.9 |
| P4.11 | Performance optimization | Developer | P4.1-P4.10 |
| P4.12 | Final visual QA | Designer/Dev | P4.11 |

### 7.3 Accessibility Checklist

| Requirement | Implementation | Status |
|-------------|----------------|--------|
| Color contrast 4.5:1 | Use MD3 semantic colors | Pending |
| Focus visible indicators | MUI default + customization | Pending |
| Keyboard navigation | All controls focusable | Pending |
| ARIA labels | Add to all interactive elements | Pending |
| Skip navigation | Add skip link | Pending |
| Reduced motion support | Respect prefers-reduced-motion | Pending |
| Touch targets 44x44px | Verify all interactive elements | Pending |

### 7.4 Color Migration Map

| Current Usage | Replace With |
|---------------|--------------|
| `bg-gray-900` | `surface` |
| `bg-gray-800` | `surfaceContainer` |
| `bg-gray-700` | `surfaceContainerHigh` |
| `bg-gray-600` | `surfaceContainerHighest` |
| `text-white` | `onSurface` |
| `text-gray-400` | `onSurfaceVariant` |
| `bg-blue-600` | `primary` |
| `text-blue-400` | `primary` |
| `bg-red-600` | `error` |
| `bg-green-500` | `success` (custom) |
| `bg-purple-600` | `tertiary` |
| `bg-orange-500` | `warning` (custom) |

### 7.5 Deliverables

- [ ] All pages using design system components
- [ ] No hardcoded colors/spacing
- [ ] Lighthouse accessibility score > 90
- [ ] Keyboard navigation working
- [ ] Performance maintained or improved

---

## 8. Phase 5: Figma Integration

### 8.1 Objectives

- Establish Figma as the source of truth for design
- Set up MUI Sync Plugin for theme export
- Create design handoff workflow

### 8.2 Tasks

| Task | Description | Owner | Dependencies |
|------|-------------|-------|--------------|
| P5.1 | Purchase/set up MUI Design Kit for Figma | Designer | Budget approval |
| P5.2 | Configure Figma Variables matching code tokens | Designer | P5.1, P1 complete |
| P5.3 | Install MUI Sync Plugin in Figma | Designer | P5.2 |
| P5.4 | Test theme export workflow | Designer/Dev | P5.3 |
| P5.5 | Document design-to-code process | Designer/Dev | P5.4 |
| P5.6 | Create component documentation in Figma | Designer | P5.2 |
| P5.7 | Train team on workflow | Designer/Dev | P5.5, P5.6 |

### 8.3 Figma Workspace Structure

```
📁 WRACK Design System
│
├── 📄 Cover
├── 📄 Getting Started
│
├── 📁 Foundations
│   ├── 📄 Colors
│   ├── 📄 Typography
│   ├── 📄 Spacing
│   ├── 📄 Elevation
│   └── 📄 Icons
│
├── 📁 Components
│   ├── 📄 Buttons
│   ├── 📄 Cards
│   ├── 📄 Inputs
│   ├── 📄 Status Indicators
│   └── 📄 Domain Components
│
├── 📁 Patterns
│   ├── 📄 Control Panels
│   ├── 📄 Status Displays
│   └── 📄 Layouts
│
└── 📁 Pages
    ├── 📄 Dashboard - Light
    └── 📄 Dashboard - Dark
```

### 8.4 MUI Sync Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                         DESIGN CHANGE                            │
│  Designer modifies color variable in Figma                       │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                         FIGMA UPDATE                             │
│  Changes propagate to all components using that variable         │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                         MUI SYNC EXPORT                          │
│  Click "Export" in MUI Sync Plugin                               │
│  Generates: createTheme({ palette: { primary: { main: '#...' }}})│
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                         CODE UPDATE                              │
│  Developer copies exported theme to codebase                     │
│  Or: Automated CI pulls from Figma API (advanced)                │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                         VERIFICATION                             │
│  Visual regression tests confirm changes                         │
│  Storybook shows updated components                              │
└─────────────────────────────────────────────────────────────────┘
```

### 8.5 Deliverables

- [ ] Figma Design Kit configured
- [ ] MUI Sync Plugin working
- [ ] Design handoff documentation
- [ ] Team trained on workflow

---

## 9. Risk Assessment

### 9.1 Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| MUI/Tailwind conflicts | Medium | High | Test integration early in P1 |
| Bundle size increase | Medium | Medium | Tree-shaking, code splitting |
| SSR compatibility issues | Low | High | Test with Next.js App Router |
| Breaking changes in MUI v6 | Low | Medium | Pin dependencies, review changelog |

### 9.2 Process Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Design/dev misalignment | Medium | High | Frequent sync meetings |
| Scope creep | High | Medium | Strict phase boundaries |
| Resource constraints | Medium | High | Prioritize critical path |
| Figma license delays | Low | Medium | Start with free tier |

---

## 10. Success Metrics

### 10.1 Quantitative Metrics

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Lighthouse Accessibility | Unknown | > 90 | Lighthouse audit |
| Component coverage in Storybook | 0% | 100% | Story count / component count |
| Design token usage | ~5% | > 95% | Code audit |
| Bundle size | ~300KB | < 400KB | Build output |
| Time to implement new component | - | < 2 hours | Track actual time |

### 10.2 Qualitative Metrics

| Metric | Measurement Method |
|--------|-------------------|
| Developer satisfaction | Survey after Phase 4 |
| Design-to-code consistency | Visual comparison audit |
| Maintainability | Code review feedback |
| Accessibility feedback | User testing |

---

## 11. Resource Requirements

### 11.1 Team Roles

| Role | Responsibility | Allocation |
|------|----------------|------------|
| Frontend Developer | Implementation, testing | Primary |
| UI/UX Designer | Figma design, tokens | 30-40% |
| QA Engineer | Testing, accessibility audit | 20% (Phase 4) |

### 11.2 Tools & Licenses

| Tool | Purpose | Cost |
|------|---------|------|
| Figma | Design workspace | Free tier initially |
| MUI Design Kit | Figma component library | ~$99/seat |
| Chromatic | Visual regression testing | Free tier / ~$149/mo |
| Storybook | Component documentation | Free (open source) |

---

## 12. Appendix

### A. Glossary

| Term | Definition |
|------|------------|
| Design Tokens | Named values representing design decisions (colors, spacing, etc.) |
| Material Design 3 | Google's latest design system (also called Material You) |
| MUI | React component library implementing Material Design |
| Tonal Palette | MD3's approach to generating color variations from a source color |
| Semantic Color | Color name based on usage (primary, error) vs. literal (blue-500) |

### B. Reference Links

- [Material Design 3](https://m3.material.io/)
- [MUI Documentation](https://mui.com/)
- [Material Theme Builder](https://m3.material.io/theme-builder)
- [MUI Sync Plugin](https://mui.com/blog/introducing-sync-plugin/)
- [Figma Variables](https://help.figma.com/hc/en-us/articles/15339657135383)

### C. Phase Checklist Template

```markdown
## Phase X Checklist

### Pre-Phase
- [ ] Previous phase completed
- [ ] Resources allocated
- [ ] Dependencies met

### Execution
- [ ] Task X.1 complete
- [ ] Task X.2 complete
- [ ] ...

### Quality
- [ ] Code review passed
- [ ] Tests passing
- [ ] No visual regression
- [ ] Documentation updated

### Post-Phase
- [ ] Deliverables verified
- [ ] Stakeholder sign-off
- [ ] Lessons learned documented
```

---

*This development plan should be reviewed and updated as the project progresses. Adjust phase boundaries and task assignments based on team capacity and emerging requirements.*
