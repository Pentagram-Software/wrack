'use client';

// Placeholder — implemented in PEN-107 (P1.5: Create ThemeProvider component)
// Will wrap the app with MUI ThemeProvider + CssBaseline using the WRACK theme.

import { type ReactNode } from 'react';

interface ThemeProviderProps {
  children: ReactNode;
}

export function ThemeProvider({ children }: ThemeProviderProps) {
  return <>{children}</>;
}
