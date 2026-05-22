import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import AuthGuard from './AuthGuard';

// Mock next-auth/react
vi.mock('next-auth/react', () => ({
  useSession: vi.fn(),
}));

import { useSession } from 'next-auth/react';
const mockUseSession = vi.mocked(useSession);

function makeSession(role: string | undefined) {
  if (!role) {
    return { data: null, status: 'unauthenticated' as const };
  }
  return {
    data: { user: { id: '1', name: 'test', role }, expires: '9999' },
    status: 'authenticated' as const,
  };
}

describe('AuthGuard', () => {
  it('shows loading spinner while session is loading', () => {
    mockUseSession.mockReturnValue({ data: null, status: 'loading' } as ReturnType<typeof useSession>);
    render(
      <AuthGuard permission="VIEW_STATUS">
        <div>Protected</div>
      </AuthGuard>,
    );
    expect(screen.getByText(/loading/i)).toBeDefined();
    expect(screen.queryByText('Protected')).toBeNull();
  });

  it('renders children when user has required permission', () => {
    mockUseSession.mockReturnValue(makeSession('admin') as ReturnType<typeof useSession>);
    render(
      <AuthGuard permission="MANAGE_USERS">
        <div>Admin Panel</div>
      </AuthGuard>,
    );
    expect(screen.getByText('Admin Panel')).toBeDefined();
  });

  it('renders locked panel when user lacks permission', () => {
    mockUseSession.mockReturnValue(makeSession('viewer') as ReturnType<typeof useSession>);
    render(
      <AuthGuard permission="CONTROL_EV3">
        <div>Controls</div>
      </AuthGuard>,
    );
    expect(screen.getByText(/access restricted/i)).toBeDefined();
    expect(screen.queryByText('Controls')).toBeNull();
  });

  it('renders custom fallback when provided and user lacks permission', () => {
    mockUseSession.mockReturnValue(makeSession('viewer') as ReturnType<typeof useSession>);
    render(
      <AuthGuard permission="CONTROL_EV3" fallback={<span>No access</span>}>
        <div>Controls</div>
      </AuthGuard>,
    );
    expect(screen.getByText('No access')).toBeDefined();
    expect(screen.queryByText('Controls')).toBeNull();
  });

  it('renders null fallback (nothing) when passed null for viewer on STREAM_VIDEO', () => {
    mockUseSession.mockReturnValue(makeSession('viewer') as ReturnType<typeof useSession>);
    const { container } = render(
      <AuthGuard permission="STREAM_VIDEO" fallback={null}>
        <div>Camera</div>
      </AuthGuard>,
    );
    // STREAM_VIDEO is allowed for viewer, so children render
    expect(screen.getByText('Camera')).toBeDefined();
  });

  it('operator can access CONTROL_EV3', () => {
    mockUseSession.mockReturnValue(makeSession('operator') as ReturnType<typeof useSession>);
    render(
      <AuthGuard permission="CONTROL_EV3">
        <div>Drive!</div>
      </AuthGuard>,
    );
    expect(screen.getByText('Drive!')).toBeDefined();
  });

  it('shows locked panel for unauthenticated user', () => {
    mockUseSession.mockReturnValue(makeSession(undefined) as ReturnType<typeof useSession>);
    render(
      <AuthGuard permission="VIEW_STATUS">
        <div>Status</div>
      </AuthGuard>,
    );
    expect(screen.getByText(/access restricted/i)).toBeDefined();
  });
});
