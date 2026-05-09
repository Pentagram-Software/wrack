export const typography = {
  fontFamily: {
    base: 'var(--font-bruno-ace), "Helvetica", "Arial", sans-serif',
    mono: 'var(--font-geist-mono), "Courier New", monospace',
  },

  // MD3 type scale — maps to MUI variant names
  scale: {
    displayLarge:   { fontSize: '3.5625rem',  lineHeight: '4rem',     letterSpacing: '-0.015625rem', fontWeight: 400 },
    displayMedium:  { fontSize: '2.8125rem',  lineHeight: '3.25rem',  letterSpacing: '0',            fontWeight: 400 },
    displaySmall:   { fontSize: '2.25rem',    lineHeight: '2.75rem',  letterSpacing: '0',            fontWeight: 400 },
    headlineLarge:  { fontSize: '2rem',       lineHeight: '2.5rem',   letterSpacing: '0',            fontWeight: 400 },
    headlineMedium: { fontSize: '1.75rem',    lineHeight: '2.25rem',  letterSpacing: '0',            fontWeight: 400 },
    headlineSmall:  { fontSize: '1.5rem',     lineHeight: '2rem',     letterSpacing: '0',            fontWeight: 400 },
    titleLarge:     { fontSize: '1.375rem',   lineHeight: '1.75rem',  letterSpacing: '0',            fontWeight: 400 },
    titleMedium:    { fontSize: '1rem',       lineHeight: '1.5rem',   letterSpacing: '0.009375rem',  fontWeight: 500 },
    titleSmall:     { fontSize: '0.875rem',   lineHeight: '1.25rem',  letterSpacing: '0.00625rem',   fontWeight: 500 },
    bodyLarge:      { fontSize: '1rem',       lineHeight: '1.5rem',   letterSpacing: '0.03125rem',   fontWeight: 400 },
    bodyMedium:     { fontSize: '0.875rem',   lineHeight: '1.25rem',  letterSpacing: '0.015625rem',  fontWeight: 400 },
    bodySmall:      { fontSize: '0.75rem',    lineHeight: '1rem',     letterSpacing: '0.025rem',     fontWeight: 400 },
    labelLarge:     { fontSize: '0.875rem',   lineHeight: '1.25rem',  letterSpacing: '0.00625rem',   fontWeight: 500 },
    labelMedium:    { fontSize: '0.75rem',    lineHeight: '1rem',     letterSpacing: '0.03125rem',   fontWeight: 500 },
    labelSmall:     { fontSize: '0.6875rem',  lineHeight: '1rem',     letterSpacing: '0.03125rem',   fontWeight: 500 },
  },
} as const;

export type TypographyScale = typeof typography.scale;
export type TypographyVariant = keyof TypographyScale;
