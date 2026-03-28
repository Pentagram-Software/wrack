import { createTheme, type Theme } from '@mui/material/styles';
import { lightScheme, darkScheme } from '../tokens/colors';
import { typography } from '../tokens/typography';
import { radius } from '../tokens/radius';
import { elevation } from '../tokens/elevation';
import { motion } from '../tokens/motion';

export function createWrackTheme(mode: 'light' | 'dark'): Theme {
  const scheme = mode === 'light' ? lightScheme : darkScheme;

  return createTheme({
    palette: {
      mode,
      primary: {
        main:         scheme.primary,
        contrastText: scheme.onPrimary,
      },
      secondary: {
        main:         scheme.secondary,
        contrastText: scheme.onSecondary,
      },
      error: {
        main:         scheme.error,
        contrastText: scheme.onError,
      },
      background: {
        default: scheme.background,
        paper:   scheme.surfaceContainer,
      },
      text: {
        primary:   scheme.onSurface,
        secondary: scheme.onSurfaceVariant,
      },
      divider: scheme.outlineVariant,
    },

    typography: {
      fontFamily: typography.fontFamily.base,
      // Map MD3 type scale onto MUI variants
      h1:       { ...typography.scale.displayLarge },
      h2:       { ...typography.scale.displayMedium },
      h3:       { ...typography.scale.displaySmall },
      h4:       { ...typography.scale.headlineLarge },
      h5:       { ...typography.scale.headlineMedium },
      h6:       { ...typography.scale.headlineSmall },
      subtitle1:{ ...typography.scale.titleLarge },
      subtitle2:{ ...typography.scale.titleMedium },
      body1:    { ...typography.scale.bodyLarge },
      body2:    { ...typography.scale.bodyMedium },
      caption:  { ...typography.scale.labelMedium },
      overline: { ...typography.scale.labelSmall },
      button:   { ...typography.scale.labelLarge, textTransform: 'none' },
    },

    shape: {
      // MUI uses a single borderRadius multiplier; we set to md (12px)
      borderRadius: parseInt(radius.md, 10),
    },

    shadows: [
      elevation[0],
      elevation[1],
      elevation[2],
      elevation[3],
      elevation[4],
      elevation[5],
      // MUI expects 25 shadow values; fill remaining with level 5
      ...Array(19).fill(elevation[5]),
    ] as Theme['shadows'],

    transitions: {
      easing: {
        easeInOut: motion.easing.standard,
        easeOut:   motion.easing.standardDecelerate,
        easeIn:    motion.easing.standardAccelerate,
        sharp:     motion.easing.emphasized,
      },
      duration: {
        shortest:      parseInt(motion.duration.short2, 10),
        shorter:       parseInt(motion.duration.short3, 10),
        short:         parseInt(motion.duration.short4, 10),
        standard:      parseInt(motion.duration.medium2, 10),
        complex:       parseInt(motion.duration.medium4, 10),
        enteringScreen:parseInt(motion.duration.medium3, 10),
        leavingScreen: parseInt(motion.duration.short4, 10),
      },
    },

    components: {
      MuiButton: {
        styleOverrides: {
          root: {
            borderRadius: radius.full,
          },
        },
      },
      MuiCard: {
        styleOverrides: {
          root: {
            borderRadius: radius.md,
          },
        },
      },
      MuiChip: {
        styleOverrides: {
          root: {
            borderRadius: radius.sm,
          },
        },
      },
    },
  });
}
