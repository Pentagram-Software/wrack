import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { act } from 'react';
import { ThemeToggle } from './ThemeToggle';
import { useThemeStore } from '@/stores/themeStore';

// Stub MUI icons so the test doesn't need a full MUI render pipeline
vi.mock('@mui/icons-material/LightMode',        () => ({ default: () => <span data-testid="icon-light" /> }));
vi.mock('@mui/icons-material/DarkMode',         () => ({ default: () => <span data-testid="icon-dark" /> }));
vi.mock('@mui/icons-material/SettingsBrightness',() => ({ default: () => <span data-testid="icon-system" /> }));

beforeEach(() => {
  act(() => {
    useThemeStore.setState({ mode: 'system', resolvedMode: 'dark' });
  });
});

describe('ThemeToggle', () => {
  it('renders without crashing', () => {
    render(<ThemeToggle />);
    expect(screen.getByRole('button')).toBeInTheDocument();
  });

  it('shows system icon when mode is system', () => {
    render(<ThemeToggle />);
    expect(screen.getByTestId('icon-system')).toBeInTheDocument();
  });

  it('cycles system → light on first click', async () => {
    const user = userEvent.setup();
    render(<ThemeToggle />);
    await user.click(screen.getByRole('button'));
    expect(useThemeStore.getState().mode).toBe('light');
  });

  it('shows light icon after switching to light mode', async () => {
    act(() => useThemeStore.setState({ mode: 'light', resolvedMode: 'light' }));
    render(<ThemeToggle />);
    expect(screen.getByTestId('icon-light')).toBeInTheDocument();
  });

  it('cycles light → dark on click', async () => {
    const user = userEvent.setup();
    act(() => useThemeStore.setState({ mode: 'light', resolvedMode: 'light' }));
    render(<ThemeToggle />);
    await user.click(screen.getByRole('button'));
    expect(useThemeStore.getState().mode).toBe('dark');
  });

  it('shows dark icon after switching to dark mode', async () => {
    act(() => useThemeStore.setState({ mode: 'dark', resolvedMode: 'dark' }));
    render(<ThemeToggle />);
    expect(screen.getByTestId('icon-dark')).toBeInTheDocument();
  });

  it('cycles dark → system on click', async () => {
    const user = userEvent.setup();
    act(() => useThemeStore.setState({ mode: 'dark', resolvedMode: 'dark' }));
    render(<ThemeToggle />);
    await user.click(screen.getByRole('button'));
    expect(useThemeStore.getState().mode).toBe('system');
  });

  it('has accessible aria-label describing next action', () => {
    render(<ThemeToggle />);
    expect(screen.getByRole('button')).toHaveAttribute(
      'aria-label',
      'System theme (click for light)',
    );
  });
});
