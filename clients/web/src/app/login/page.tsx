'use client';

import { useState } from 'react';
import { signIn } from 'next-auth/react';
import { useRouter } from 'next/navigation';

export default function LoginPage() {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsLoading(true);
    setError(null);

    const formData = new FormData(event.currentTarget);
    const username = formData.get('username') as string;
    const password = formData.get('password') as string;

    try {
      const result = await signIn('credentials', {
        username,
        password,
        redirect: false,
      });

      if (result?.error) {
        setError('Invalid username or password.');
      } else {
        router.push('/');
        router.refresh();
      }
    } catch {
      setError('An unexpected error occurred. Please try again.');
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        {/* Logo / Title */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-primary font-[var(--font-bruno-ace)]">
            WRACK
          </h1>
          <p className="text-on-surface-variant text-sm mt-1">Control Center</p>
        </div>

        {/* Card */}
        <div className="bg-surface-container rounded-2xl p-8 shadow-lg border border-outline-variant">
          <h2 className="text-xl font-semibold text-on-surface mb-1">Sign in</h2>
          <p className="text-on-surface-variant text-sm mb-6">
            Enter your credentials to access the control center.
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="username"
                className="block text-sm font-medium text-on-surface mb-1"
              >
                Username
              </label>
              <input
                id="username"
                name="username"
                type="text"
                required
                autoComplete="username"
                autoFocus
                disabled={isLoading}
                className="w-full px-3 py-2 bg-surface border border-outline-variant rounded-lg
                           text-on-surface placeholder-on-surface-variant/50 text-sm
                           focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent
                           disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                placeholder="Enter username"
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="block text-sm font-medium text-on-surface mb-1"
              >
                Password
              </label>
              <input
                id="password"
                name="password"
                type="password"
                required
                autoComplete="current-password"
                disabled={isLoading}
                className="w-full px-3 py-2 bg-surface border border-outline-variant rounded-lg
                           text-on-surface placeholder-on-surface-variant/50 text-sm
                           focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent
                           disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                placeholder="Enter password"
              />
            </div>

            {error && (
              <div className="flex items-start gap-2 p-3 bg-error-container rounded-lg">
                <svg
                  className="w-4 h-4 text-on-error-container mt-0.5 shrink-0"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                  />
                </svg>
                <p className="text-on-error-container text-sm">{error}</p>
              </div>
            )}

            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-2.5 px-4 bg-primary text-on-primary rounded-lg font-medium text-sm
                         hover:opacity-90 active:opacity-80 transition-opacity
                         disabled:opacity-50 disabled:cursor-not-allowed
                         flex items-center justify-center gap-2"
            >
              {isLoading ? (
                <>
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                    />
                  </svg>
                  Signing in…
                </>
              ) : (
                'Sign in'
              )}
            </button>
          </form>
        </div>

        {/* Role hint */}
        <div className="mt-6 p-4 bg-surface-container-low rounded-xl border border-outline-variant">
          <p className="text-xs font-medium text-on-surface-variant mb-2">Access levels</p>
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-primary/10 text-primary">
                admin
              </span>
              <span className="text-xs text-on-surface-variant">Full control + user management</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-secondary/10 text-secondary">
                operator
              </span>
              <span className="text-xs text-on-surface-variant">EV3 control + camera</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-tertiary/10 text-tertiary">
                viewer
              </span>
              <span className="text-xs text-on-surface-variant">Status & camera (read-only)</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
