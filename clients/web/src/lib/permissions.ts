import type { Permission, UserRole } from '@/types/auth';

export const ROLE_PERMISSIONS: Record<UserRole, Permission[]> = {
  admin: ['VIEW_STATUS', 'STREAM_VIDEO', 'CONTROL_EV3', 'MANAGE_USERS'],
  operator: ['VIEW_STATUS', 'STREAM_VIDEO', 'CONTROL_EV3'],
  viewer: ['VIEW_STATUS', 'STREAM_VIDEO'],
};

export function hasPermission(role: UserRole | undefined, permission: Permission): boolean {
  if (!role) return false;
  return ROLE_PERMISSIONS[role]?.includes(permission) ?? false;
}

export function hasAnyPermission(role: UserRole | undefined, permissions: Permission[]): boolean {
  return permissions.some((p) => hasPermission(role, p));
}

export function getRoleLabel(role: UserRole): string {
  const labels: Record<UserRole, string> = {
    admin: 'Administrator',
    operator: 'Operator',
    viewer: 'Viewer',
  };
  return labels[role];
}

export function getRoleDescription(role: UserRole): string {
  const descriptions: Record<UserRole, string> = {
    admin: 'Full access: control EV3, view camera, manage users and sessions',
    operator: 'Operational access: control EV3, view camera and status',
    viewer: 'Read-only access: view camera feed and device status',
  };
  return descriptions[role];
}

export const PERMISSION_LABELS: Record<Permission, string> = {
  VIEW_STATUS: 'View device status',
  STREAM_VIDEO: 'Stream camera video',
  CONTROL_EV3: 'Control EV3 robot',
  MANAGE_USERS: 'Manage users & sessions',
};

export { type Permission, type UserRole };
