import NextAuth from 'next-auth';
import Credentials from 'next-auth/providers/credentials';
import bcrypt from 'bcryptjs';
import { authConfig } from './auth.config';
import type { AuthUser, UserRole } from '@/types/auth';

/**
 * Parse users from the AUTH_USERS_JSON environment variable.
 * Format: JSON array of { username, passwordHash, role }
 */
function getConfiguredUsers(): AuthUser[] {
  const raw = process.env.AUTH_USERS_JSON;
  if (!raw) {
    console.warn('[auth] AUTH_USERS_JSON is not set. Authentication will fail.');
    return [];
  }
  try {
    const parsed = JSON.parse(raw) as AuthUser[];
    return parsed.map((u, idx) => ({ ...u, id: u.id ?? String(idx + 1) }));
  } catch {
    console.error('[auth] Failed to parse AUTH_USERS_JSON. Must be valid JSON.');
    return [];
  }
}

async function findUserByCredentials(
  username: string,
  password: string,
): Promise<AuthUser | null> {
  const users = getConfiguredUsers();
  const user = users.find((u) => u.username === username);
  if (!user) return null;
  const valid = await bcrypt.compare(password, user.passwordHash);
  return valid ? user : null;
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  ...authConfig,
  providers: [
    Credentials({
      name: 'Credentials',
      credentials: {
        username: { label: 'Username', type: 'text' },
        password: { label: 'Password', type: 'password' },
      },
      async authorize(credentials) {
        if (!credentials?.username || !credentials?.password) return null;
        const user = await findUserByCredentials(
          credentials.username as string,
          credentials.password as string,
        );
        if (!user) return null;
        return {
          id: user.id,
          name: user.username,
          role: user.role as UserRole,
        };
      },
    }),
  ],
});
