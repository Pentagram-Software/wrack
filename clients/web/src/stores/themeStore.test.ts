import { describe, it, expect, beforeEach } from 'vitest';
import { act } from 'react';
import { useThemeStore } from './themeStore';

// Reset store state between tests
beforeEach(() => {
  useThemeStore.setState({
    mode: 'system',
    resolvedMode: 'dark',
  });
});

describe('themeStore', () => {
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
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: (query: string) => ({
        matches: query.includes('dark'),
        media: query,
        addEventListener: () => {},
        removeEventListener: () => {},
      }),
    });
    act(() => useThemeStore.getState().setMode('system'));
    expect(useThemeStore.getState().resolvedMode).toBe('dark');
  });

  it('setMode system with light OS → resolvedMode is light', () => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        addEventListener: () => {},
        removeEventListener: () => {},
      }),
    });
    act(() => useThemeStore.getState().setMode('system'));
    expect(useThemeStore.getState().resolvedMode).toBe('light');
  });

  it('_resolveMode does nothing when mode is not system', () => {
    act(() => useThemeStore.getState().setMode('light'));
    act(() => useThemeStore.getState()._resolveMode(true));
    expect(useThemeStore.getState().resolvedMode).toBe('light');
  });

  it('_resolveMode updates resolvedMode when mode is system', () => {
    act(() => {
      useThemeStore.setState({ mode: 'system', resolvedMode: 'dark' });
      useThemeStore.getState()._resolveMode(false);
    });
    expect(useThemeStore.getState().resolvedMode).toBe('light');
  });
});
