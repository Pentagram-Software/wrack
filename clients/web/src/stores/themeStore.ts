import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type ThemeMode = 'light' | 'dark' | 'system';

interface ThemeState {
  mode: ThemeMode;
  resolvedMode: 'light' | 'dark';
  setMode: (mode: ThemeMode) => void;
  _resolveMode: (systemPrefersDark: boolean) => void;
}

function resolveFromSystem(systemPrefersDark: boolean): 'light' | 'dark' {
  return systemPrefersDark ? 'dark' : 'light';
}

export const useThemeStore = create<ThemeState>()(
  persist<ThemeState>(
    (set) => ({
      mode: 'system' as ThemeMode,
      resolvedMode: 'dark' as 'light' | 'dark',

      setMode: (mode: ThemeMode) =>
        set(() => {
          const systemPrefersDark =
            typeof window !== 'undefined'
              ? window.matchMedia('(prefers-color-scheme: dark)').matches
              : true;
          const resolvedMode =
            mode === 'system' ? resolveFromSystem(systemPrefersDark) : mode;
          return { mode, resolvedMode };
        }),

      _resolveMode: (systemPrefersDark: boolean) =>
        set((state: ThemeState) => {
          if (state.mode !== 'system') return state;
          return { ...state, resolvedMode: resolveFromSystem(systemPrefersDark) };
        }),
    }),
    {
      name: 'wrack-theme',
      partialize: (state: ThemeState) => ({ mode: state.mode }) as ThemeState,
    },
  ),
);
