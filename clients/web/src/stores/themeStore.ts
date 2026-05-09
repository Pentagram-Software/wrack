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

function computeResolved(mode: ThemeMode): 'light' | 'dark' {
  if (mode === 'light' || mode === 'dark') return mode;
  if (typeof window !== 'undefined') {
    return resolveFromSystem(window.matchMedia('(prefers-color-scheme: dark)').matches);
  }
  return 'dark';
}

export const useThemeStore = create<ThemeState>()(
  persist<ThemeState>(
    (set) => ({
      mode: 'system' as ThemeMode,
      resolvedMode: 'dark' as 'light' | 'dark',

      setMode: (mode: ThemeMode) =>
        set(() => ({ mode, resolvedMode: computeResolved(mode) })),

      _resolveMode: (systemPrefersDark: boolean) =>
        set((state: ThemeState) => {
          if (state.mode !== 'system') return state;
          return { ...state, resolvedMode: resolveFromSystem(systemPrefersDark) };
        }),
    }),
    {
      name: 'wrack-theme',
      partialize: (state: ThemeState) => ({ mode: state.mode }) as ThemeState,
      // After rehydrating mode from localStorage, recompute resolvedMode correctly
      onRehydrateStorage: () => (state) => {
        if (!state) return;
        state.resolvedMode = computeResolved(state.mode);
      },
    },
  ),
);
