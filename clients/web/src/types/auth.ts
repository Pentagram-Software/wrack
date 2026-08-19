export type UserRole = 'admin' | 'operator' | 'viewer';

export type Permission =
  | 'VIEW_STATUS'
  | 'STREAM_VIDEO'
  | 'CONTROL_EV3'
  | 'MANAGE_USERS';

export interface User {
  id: string;
  username: string;
  role: UserRole;
}

export interface AuthUser extends User {
  passwordHash: string;
}

declare module 'next-auth' {
  interface Session {
    user: {
      id: string;
      name: string;
      role: UserRole;
    };
  }

  interface User {
    role: UserRole;
  }
}

declare module 'next-auth/jwt' {
  interface JWT {
    id: string;
    role: UserRole;
  }
}
