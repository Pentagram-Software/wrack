import type { NextAuthConfig } from 'next-auth';

/**
 * Edge-compatible auth config used by middleware.
 * Does NOT include credentials provider (bcrypt is not Edge-safe).
 */
export const authConfig: NextAuthConfig = {
  pages: {
    signIn: '/login',
  },
  session: {
    strategy: 'jwt',
    maxAge: 8 * 60 * 60, // 8 hours
  },
  callbacks: {
    authorized({ auth, request: { nextUrl } }) {
      const isLoggedIn = !!auth?.user;
      const isLoginPage = nextUrl.pathname === '/login';
      const isApiAuth = nextUrl.pathname.startsWith('/api/auth');

      if (isApiAuth) return true;
      if (isLoginPage) {
        if (isLoggedIn) {
          return Response.redirect(new URL('/', nextUrl));
        }
        return true;
      }
      return isLoggedIn;
    },
    async jwt({ token, user }) {
      if (user) {
        token.id = user.id ?? token.sub ?? '';
        token.role = (user as { role: string }).role as import('@/types/auth').UserRole;
      }
      return token;
    },
    async session({ session, token }) {
      if (token) {
        session.user.id = token.id as string;
        session.user.name = token.name ?? '';
        session.user.role = token.role as import('@/types/auth').UserRole;
      }
      return session;
    },
  },
  providers: [],
};
