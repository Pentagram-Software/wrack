'use client';

import { useState, useRef, useEffect } from 'react';
import { useSession, signOut } from 'next-auth/react';
import Link from 'next/link';
import { getRoleLabel } from '@/lib/permissions';
import { hasPermission } from '@/lib/permissions';
import type { UserRole } from '@/types/auth';

const ROLE_BADGE: Record<UserRole, string> = {
  admin: 'bg-primary/10 text-primary',
  operator: 'bg-secondary/10 text-secondary',
  viewer: 'bg-tertiary/10 text-tertiary',
};

export default function UserMenu() {
  const { data: session, status } = useSession();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  if (status === 'loading') {
    return <div className="w-8 h-8 rounded-full bg-surface-container animate-pulse" />;
  }

  if (!session?.user) return null;

  const { name, role } = session.user as { name: string; role: UserRole };
  const isAdmin = hasPermission(role, 'MANAGE_USERS');
  const initial = name?.charAt(0).toUpperCase() ?? '?';

  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setOpen((prev) => !prev)}
        className="flex items-center gap-2 px-2 py-1 rounded-lg hover:bg-surface-container transition-colors"
        aria-label="User menu"
        aria-expanded={open}
      >
        <div className="w-8 h-8 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center">
          <span className="text-primary font-semibold text-sm">{initial}</span>
        </div>
        <div className="hidden sm:block text-left">
          <p className="text-sm font-medium text-on-surface leading-none">{name}</p>
          <p className={`text-xs font-medium mt-0.5 ${role ? ROLE_BADGE[role].split(' ')[1] : ''}`}>
            {role ? getRoleLabel(role) : ''}
          </p>
        </div>
        <svg
          className={`w-4 h-4 text-on-surface-variant transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-56 rounded-xl bg-surface-container shadow-xl border border-outline-variant z-50 overflow-hidden">
          {/* User info header */}
          <div className="px-4 py-3 border-b border-outline-variant">
            <p className="text-sm font-medium text-on-surface">{name}</p>
            <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium mt-1 ${role ? ROLE_BADGE[role] : ''}`}>
              {role ? getRoleLabel(role) : ''}
            </span>
          </div>

          {/* Admin console link */}
          {isAdmin && (
            <Link
              href="/admin"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 px-4 py-2.5 text-sm text-on-surface hover:bg-surface-container-high transition-colors"
            >
              <svg className="w-4 h-4 text-on-surface-variant" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
                />
              </svg>
              Access Control
            </Link>
          )}

          {/* Sign out */}
          <button
            onClick={() => {
              setOpen(false);
              signOut({ callbackUrl: '/login' });
            }}
            className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-error hover:bg-error-container/20 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
              />
            </svg>
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
