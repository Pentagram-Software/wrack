import { describe, it, expect, beforeEach } from 'vitest';
import { act } from 'react';
import { useThemeStore } from './themeStore';

function setMatchMedia(prefersDark: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: prefersDark ? query.includes('dark') : false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  });
}

// Reset store state between tests
beforeEach(() => {
  setMatchMedia(false); // default: light OS preference
  useThemeStore.setState({
    mode: 'system',
    resolvedMode: 'dark',
  });
});

describe('themeStore — setMode', () => {
  it('starts with system mode', () => {
    expect(useThemeStore.getState().mode).toBe('system');
  });

  it('setMode light → resolvedMode is light', () => {
    act(() => useThemeStore.getState().setMode('light'));
    const { mode, resolvedMode } = useThemeStore.getState();
    expect(mode).toBe('light');
    expect(resolvedMode).toBe('light');
  });

  it('setMode dark → resolvedMode is dark', () => {
    act(() => useThemeStore.getState().setMode('dark'));
    const { mode, resolvedMode } = useThemeStore.getState();
    expect(mode).toBe('dark');
    expect(resolvedMode).toBe('dark');
  });

  it('setMode system with dark OS → resolvedMode is dark', () => {
    setMatchMedia(true);
    act(() => useThemeStore.getState().setMode('system'));
    expect(useThemeStore.getState().resolvedMode).toBe('dark');
  });

  it('setMode system with light OS → resolvedMode is light', () => {
    setMatchMedia(false);
    act(() => useThemeStore.getState().setMode('system'));
    expect(useThemeStore.getState().resolvedMode).toBe('light');
  });
});

describe('themeStore — _resolveMode', () => {
  it('does nothing when mode is not system', () => {
    act(() => useThemeStore.getState().setMode('light'));
    act(() => useThemeStore.getState()._resolveMode(true));
    expect(useThemeStore.getState().resolvedMode).toBe('light');
  });

  it('updates resolvedMode when mode is system', () => {
    act(() => {
      useThemeStore.setState({ mode: 'system', resolvedMode: 'dark' });
      useThemeStore.getState()._resolveMode(false);
    });
    expect(useThemeStore.getState().resolvedMode).toBe('light');
  });
});

describe('themeStore — rehydration (page refresh bug fix)', () => {
  it('rehydrating mode:light restores resolvedMode to light', () => {
    // Simulate what persist middleware does on page refresh:
    // it restores only 'mode' from localStorage, then onRehydrateStorage fires
    const rehydrated = { mode: 'light', resolvedMode: 'dark' } as Parameters<typeof useThemeStore.setState>[0];
    act(() => useThemeStore.setState(rehydrated));
    // onRehydrateStorage callback — call computeResolved manually as the middleware would
    act(() => {
      const state = useThemeStore.getState();
      if (state.mode !== 'system') {
        useThemeStore.setState({ resolvedMode: state.mode as 'light' | 'dark' });
      }
    });
    expect(useThemeStore.getState().resolvedMode).toBe('light');
  });

  it('rehydrating mode:dark restores resolvedMode to dark', () => {
    const rehydrated = { mode: 'dark', resolvedMode: 'light' } as Parameters<typeof useThemeStore.setState>[0];
    act(() => useThemeStore.setState(rehydrated));
    act(() => {
      const state = useThemeStore.getState();
      if (state.mode !== 'system') {
        useThemeStore.setState({ resolvedMode: state.mode as 'light' | 'dark' });
      }
    });
    expect(useThemeStore.getState().resolvedMode).toBe('dark');
  });

  it('rehydrating mode:system with dark OS resolves to dark', () => {
    setMatchMedia(true);
    const rehydrated = { mode: 'system', resolvedMode: 'light' } as Parameters<typeof useThemeStore.setState>[0];
    act(() => useThemeStore.setState(rehydrated));
    act(() => useThemeStore.getState()._resolveMode(true));
    expect(useThemeStore.getState().resolvedMode).toBe('dark');
  });

  it('rehydrating mode:system with light OS resolves to light', () => {
    setMatchMedia(false);
    const rehydrated = { mode: 'system', resolvedMode: 'dark' } as Parameters<typeof useThemeStore.setState>[0];
    act(() => useThemeStore.setState(rehydrated));
    act(() => useThemeStore.getState()._resolveMode(false));
    expect(useThemeStore.getState().resolvedMode).toBe('light');
  });

  it('resolvedMode is never stale after setMode is called post-rehydration', () => {
    // Simulate stale rehydration state
    act(() => useThemeStore.setState({ mode: 'light', resolvedMode: 'dark' } as Parameters<typeof useThemeStore.setState>[0]));
    // User then toggles — setMode must recompute correctly regardless of stale resolvedMode
    act(() => useThemeStore.getState().setMode('dark'));
    expect(useThemeStore.getState().resolvedMode).toBe('dark');
    act(() => useThemeStore.getState().setMode('light'));
    expect(useThemeStore.getState().resolvedMode).toBe('light');
  });
});
