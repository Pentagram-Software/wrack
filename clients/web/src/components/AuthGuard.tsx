'use client';

import { useSession } from 'next-auth/react';
import { hasPermission } from '@/lib/permissions';
import type { Permission, UserRole } from '@/types/auth';

interface AuthGuardProps {
  permission: Permission;
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

/**
 * Renders children only when the current user has the required permission.
 * Renders `fallback` (or a locked UI hint) otherwise.
 */
export default function AuthGuard({ permission, children, fallback }: AuthGuardProps) {
  const { data: session, status } = useSession();

  if (status === 'loading') {
    return (
      <div className="flex items-center justify-center p-4 text-on-surface-variant text-sm">
        <svg className="animate-spin h-4 w-4 mr-2" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        Loading…
      </div>
    );
  }

  const role = session?.user?.role as UserRole | undefined;
  const allowed = hasPermission(role, permission);

  if (!allowed) {
    if (fallback !== undefined) return <>{fallback}</>;
    return <LockedPanel permission={permission} />;
  }

  return <>{children}</>;
}

function LockedPanel({ permission }: { permission: Permission }) {
  const labels: Record<Permission, string> = {
    VIEW_STATUS: 'View Status',
    STREAM_VIDEO: 'Stream Video',
    CONTROL_EV3: 'Control EV3',
    MANAGE_USERS: 'Manage Users',
  };

  return (
    <div className="flex flex-col items-center justify-center p-6 rounded-xl bg-surface-container border border-outline-variant text-center gap-2">
      <div className="w-10 h-10 rounded-full bg-surface flex items-center justify-center">
        <svg className="w-5 h-5 text-on-surface-variant" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
          />
        </svg>
      </div>
      <p className="text-sm font-medium text-on-surface">Access Restricted</p>
      <p className="text-xs text-on-surface-variant">
        <strong>{labels[permission]}</strong> permission required
      </p>
    </div>
  );
}
