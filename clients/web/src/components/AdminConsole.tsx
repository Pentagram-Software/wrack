'use client';

import Link from 'next/link';
import {
  getRoleLabel,
  getRoleDescription,
  ROLE_PERMISSIONS,
  PERMISSION_LABELS,
} from '@/lib/permissions';
import type { UserRole, Permission } from '@/types/auth';

const ALL_ROLES: UserRole[] = ['admin', 'operator', 'viewer'];

const ROLE_BADGE_COLORS: Record<UserRole, string> = {
  admin: 'bg-primary/10 text-primary border border-primary/20',
  operator: 'bg-secondary/10 text-secondary border border-secondary/20',
  viewer: 'bg-tertiary/10 text-tertiary border border-tertiary/20',
};

interface AdminConsoleProps {
  currentUser: { name: string; role: UserRole };
}

export default function AdminConsole({ currentUser }: AdminConsoleProps) {
  return (
    <div className="min-h-screen bg-background text-on-background">
      {/* Header */}
      <header className="bg-surface-container-high border-b border-outline-variant p-4">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-primary">Access Control</h1>
            <p className="text-on-surface-variant text-sm mt-1">
              Role definitions and permission matrix
            </p>
          </div>
          <Link
            href="/"
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium
                       bg-surface-container text-on-surface hover:bg-surface-container-high
                       border border-outline-variant transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Back to Dashboard
          </Link>
        </div>
      </header>

      <main className="max-w-5xl mx-auto p-6 space-y-8">
        {/* Current session info */}
        <section className="bg-surface-container rounded-xl p-5 border border-outline-variant">
          <h2 className="text-sm font-semibold text-on-surface-variant uppercase tracking-wider mb-3">
            Current Session
          </h2>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center">
              <span className="text-primary font-semibold text-lg">
                {currentUser.name.charAt(0).toUpperCase()}
              </span>
            </div>
            <div>
              <p className="font-medium text-on-surface">{currentUser.name}</p>
              <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${ROLE_BADGE_COLORS[currentUser.role]}`}>
                {getRoleLabel(currentUser.role)}
              </span>
            </div>
          </div>
        </section>

        {/* Role definitions */}
        <section>
          <h2 className="text-lg font-semibold text-on-surface mb-4">Role Definitions</h2>
          <div className="grid gap-4 md:grid-cols-3">
            {ALL_ROLES.map((role) => (
              <div
                key={role}
                className="bg-surface-container rounded-xl p-5 border border-outline-variant"
              >
                <div className="flex items-center gap-2 mb-2">
                  <span className={`inline-flex items-center px-2.5 py-1 rounded-lg text-sm font-medium ${ROLE_BADGE_COLORS[role]}`}>
                    {getRoleLabel(role)}
                  </span>
                </div>
                <p className="text-xs text-on-surface-variant mb-4">{getRoleDescription(role)}</p>
                <div className="space-y-1.5">
                  {Object.keys(PERMISSION_LABELS).map((p) => {
                    const perm = p as Permission;
                    const granted = ROLE_PERMISSIONS[role].includes(perm);
                    return (
                      <div key={perm} className="flex items-center gap-2">
                        {granted ? (
                          <svg className="w-4 h-4 text-primary shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                          </svg>
                        ) : (
                          <svg className="w-4 h-4 text-on-surface-variant/40 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        )}
                        <span className={`text-xs ${granted ? 'text-on-surface' : 'text-on-surface-variant/50'}`}>
                          {PERMISSION_LABELS[perm]}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Permission matrix */}
        <section>
          <h2 className="text-lg font-semibold text-on-surface mb-4">Permission Matrix</h2>
          <div className="bg-surface-container rounded-xl border border-outline-variant overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-outline-variant">
                  <th className="text-left p-4 font-medium text-on-surface-variant">Permission</th>
                  {ALL_ROLES.map((role) => (
                    <th key={role} className="text-center p-4 font-medium text-on-surface-variant">
                      {getRoleLabel(role)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Object.entries(PERMISSION_LABELS).map(([perm, label], idx) => (
                  <tr
                    key={perm}
                    className={idx % 2 === 0 ? 'bg-surface-container' : 'bg-surface-container-low'}
                  >
                    <td className="p-4 text-on-surface font-medium">{label}</td>
                    {ALL_ROLES.map((role) => {
                      const granted = ROLE_PERMISSIONS[role].includes(perm as Permission);
                      return (
                        <td key={role} className="p-4 text-center">
                          {granted ? (
                            <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-primary/10">
                              <svg className="w-4 h-4 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                              </svg>
                            </span>
                          ) : (
                            <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-surface">
                              <svg className="w-3.5 h-3.5 text-on-surface-variant/30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                              </svg>
                            </span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Configuration instructions */}
        <section className="bg-surface-container rounded-xl p-5 border border-outline-variant">
          <h2 className="text-lg font-semibold text-on-surface mb-3">User Configuration</h2>
          <p className="text-sm text-on-surface-variant mb-4">
            Users are configured via the <code className="bg-surface px-1.5 py-0.5 rounded text-xs font-mono text-primary">AUTH_USERS_JSON</code> environment variable.
            Each entry requires a bcrypt-hashed password.
          </p>
          <div className="bg-surface rounded-lg p-4 font-mono text-xs text-on-surface overflow-x-auto">
            <pre>{`# Generate a bcrypt hash (rounds=10):
node -e "const b=require('bcryptjs');b.hash('your-pass',10).then(console.log)"

# Set env var (JSON array):
AUTH_USERS_JSON='[
  {"id":"1","username":"admin","passwordHash":"<hash>","role":"admin"},
  {"id":"2","username":"operator","passwordHash":"<hash>","role":"operator"},
  {"id":"3","username":"viewer","passwordHash":"<hash>","role":"viewer"}
]'`}</pre>
          </div>
          <p className="text-xs text-on-surface-variant mt-3">
            Session duration: <strong>8 hours</strong>. Users are re-authenticated after session expiry.
          </p>
        </section>
      </main>
    </div>
  );
}
