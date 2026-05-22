import { redirect } from 'next/navigation';
import { auth } from '@/lib/auth';
import { hasPermission, getRoleLabel, getRoleDescription, ROLE_PERMISSIONS, PERMISSION_LABELS } from '@/lib/permissions';
import type { UserRole } from '@/types/auth';
import AdminConsole from '@/components/AdminConsole';

export const metadata = { title: 'Access Control — WRACK Control Center' };

export default async function AdminPage() {
  const session = await auth();

  if (!session?.user) {
    redirect('/login');
  }

  const role = session.user.role as UserRole;

  if (!hasPermission(role, 'MANAGE_USERS')) {
    redirect('/');
  }

  return <AdminConsole currentUser={{ name: session.user.name, role }} />;
}
