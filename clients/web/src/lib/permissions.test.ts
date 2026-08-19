import { describe, it, expect } from 'vitest';
import {
  hasPermission,
  hasAnyPermission,
  getRoleLabel,
  getRoleDescription,
  ROLE_PERMISSIONS,
  PERMISSION_LABELS,
} from './permissions';
import type { UserRole, Permission } from '@/types/auth';

describe('ROLE_PERMISSIONS', () => {
  it('admin has all permissions', () => {
    const allPerms: Permission[] = ['VIEW_STATUS', 'STREAM_VIDEO', 'CONTROL_EV3', 'MANAGE_USERS'];
    allPerms.forEach((p) => {
      expect(ROLE_PERMISSIONS.admin).toContain(p);
    });
  });

  it('operator has CONTROL_EV3 and VIEW_STATUS and STREAM_VIDEO but not MANAGE_USERS', () => {
    expect(ROLE_PERMISSIONS.operator).toContain('VIEW_STATUS');
    expect(ROLE_PERMISSIONS.operator).toContain('STREAM_VIDEO');
    expect(ROLE_PERMISSIONS.operator).toContain('CONTROL_EV3');
    expect(ROLE_PERMISSIONS.operator).not.toContain('MANAGE_USERS');
  });

  it('viewer has VIEW_STATUS and STREAM_VIDEO but not CONTROL_EV3 or MANAGE_USERS', () => {
    expect(ROLE_PERMISSIONS.viewer).toContain('VIEW_STATUS');
    expect(ROLE_PERMISSIONS.viewer).toContain('STREAM_VIDEO');
    expect(ROLE_PERMISSIONS.viewer).not.toContain('CONTROL_EV3');
    expect(ROLE_PERMISSIONS.viewer).not.toContain('MANAGE_USERS');
  });
});

describe('hasPermission', () => {
  it('returns false for undefined role', () => {
    expect(hasPermission(undefined, 'VIEW_STATUS')).toBe(false);
  });

  it('admin can VIEW_STATUS', () => {
    expect(hasPermission('admin', 'VIEW_STATUS')).toBe(true);
  });

  it('admin can MANAGE_USERS', () => {
    expect(hasPermission('admin', 'MANAGE_USERS')).toBe(true);
  });

  it('operator can CONTROL_EV3', () => {
    expect(hasPermission('operator', 'CONTROL_EV3')).toBe(true);
  });

  it('operator cannot MANAGE_USERS', () => {
    expect(hasPermission('operator', 'MANAGE_USERS')).toBe(false);
  });

  it('viewer can VIEW_STATUS', () => {
    expect(hasPermission('viewer', 'VIEW_STATUS')).toBe(true);
  });

  it('viewer can STREAM_VIDEO', () => {
    expect(hasPermission('viewer', 'STREAM_VIDEO')).toBe(true);
  });

  it('viewer cannot CONTROL_EV3', () => {
    expect(hasPermission('viewer', 'CONTROL_EV3')).toBe(false);
  });

  it('viewer cannot MANAGE_USERS', () => {
    expect(hasPermission('viewer', 'MANAGE_USERS')).toBe(false);
  });
});

describe('hasAnyPermission', () => {
  it('returns true when role has at least one of the permissions', () => {
    expect(hasAnyPermission('viewer', ['CONTROL_EV3', 'VIEW_STATUS'])).toBe(true);
  });

  it('returns false when role has none of the permissions', () => {
    expect(hasAnyPermission('viewer', ['CONTROL_EV3', 'MANAGE_USERS'])).toBe(false);
  });

  it('returns false for undefined role', () => {
    expect(hasAnyPermission(undefined, ['VIEW_STATUS'])).toBe(false);
  });

  it('returns false for empty permissions array', () => {
    expect(hasAnyPermission('admin', [])).toBe(false);
  });
});

describe('getRoleLabel', () => {
  it('returns human-readable labels', () => {
    expect(getRoleLabel('admin')).toBe('Administrator');
    expect(getRoleLabel('operator')).toBe('Operator');
    expect(getRoleLabel('viewer')).toBe('Viewer');
  });
});

describe('getRoleDescription', () => {
  it('returns a non-empty description for each role', () => {
    const roles: UserRole[] = ['admin', 'operator', 'viewer'];
    roles.forEach((role) => {
      const desc = getRoleDescription(role);
      expect(typeof desc).toBe('string');
      expect(desc.length).toBeGreaterThan(0);
    });
  });
});

describe('PERMISSION_LABELS', () => {
  it('has a label for every permission', () => {
    const perms: Permission[] = ['VIEW_STATUS', 'STREAM_VIDEO', 'CONTROL_EV3', 'MANAGE_USERS'];
    perms.forEach((p) => {
      expect(PERMISSION_LABELS[p]).toBeDefined();
      expect(PERMISSION_LABELS[p].length).toBeGreaterThan(0);
    });
  });
});
