'use client';

import { useMemo, useEffect, type ReactNode } from 'react';
import { ThemeProvider as MuiThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { useThemeStore } from '@/stores/themeStore';
import { createWrackTheme } from '../themes/muiTheme';

interface ThemeProviderProps {
  children: ReactNode;
}

export function ThemeProvider({ children }: ThemeProviderProps) {
  const { resolvedMode, _resolveMode } = useThemeStore();

  // Keep resolvedMode in sync when the OS preference changes
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    _resolveMode(mq.matches);

    const handler = (e: MediaQueryListEvent) => _resolveMode(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, [_resolveMode]);

  const theme = useMemo(() => createWrackTheme(resolvedMode), [resolvedMode]);

  return (
    <MuiThemeProvider theme={theme}>
      <CssBaseline />
      {children}
    </MuiThemeProvider>
  );
}
