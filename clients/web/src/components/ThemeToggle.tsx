'use client';

import { useCallback } from 'react';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import LightModeIcon from '@mui/icons-material/LightMode';
import DarkModeIcon from '@mui/icons-material/DarkMode';
import SettingsBrightnessIcon from '@mui/icons-material/SettingsBrightness';
import { useThemeStore, type ThemeMode } from '@/stores/themeStore';

const CYCLE: ThemeMode[] = ['system', 'light', 'dark'];

const LABELS: Record<ThemeMode, string> = {
  system: 'System theme (click for light)',
  light:  'Light theme (click for dark)',
  dark:   'Dark theme (click for system)',
};

function ModeIcon({ mode }: { mode: ThemeMode }) {
  if (mode === 'light')  return <LightModeIcon />;
  if (mode === 'dark')   return <DarkModeIcon />;
  return <SettingsBrightnessIcon />;
}

export function ThemeToggle() {
  const { mode, setMode } = useThemeStore();

  const handleClick = useCallback(() => {
    const next = CYCLE[(CYCLE.indexOf(mode) + 1) % CYCLE.length];
    setMode(next);
  }, [mode, setMode]);

  return (
    <Tooltip title={LABELS[mode]}>
      <IconButton
        onClick={handleClick}
        aria-label={LABELS[mode]}
        color="inherit"
        size="small"
      >
        <ModeIcon mode={mode} />
      </IconButton>
    </Tooltip>
  );
}
