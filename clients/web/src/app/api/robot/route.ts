import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import { hasPermission } from '@/lib/permissions';
import type { UserRole } from '@/types/auth';

const GCP_FUNCTION_URL =
  process.env.GCP_FUNCTION_URL ||
  'https://europe-central2-wrack-control.cloudfunctions.net/controlRobot';

const API_KEY = process.env.API_KEY || '';

/** Commands that require CONTROL_EV3 permission */
const CONTROL_COMMANDS = new Set([
  'forward',
  'backward',
  'left',
  'right',
  'stop',
  'turret_left',
  'turret_right',
  'stop_turret',
  'joystick_control',
  'speak',
]);

/** Commands that require VIEW_STATUS permission */
const STATUS_COMMANDS = new Set(['get_status', 'get_help']);

export async function POST(req: NextRequest): Promise<NextResponse> {
  const session = await auth();

  if (!session?.user) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const role = session.user.role as UserRole;
  let body: { command?: string; params?: Record<string, unknown> };

  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'Invalid request body' }, { status: 400 });
  }

  const command = body?.command;

  if (!command || typeof command !== 'string') {
    return NextResponse.json({ error: 'Missing command field' }, { status: 400 });
  }

  // Authorization check
  if (CONTROL_COMMANDS.has(command) && !hasPermission(role, 'CONTROL_EV3')) {
    return NextResponse.json(
      { error: 'Forbidden: CONTROL_EV3 permission required' },
      { status: 403 },
    );
  }
  if (STATUS_COMMANDS.has(command) && !hasPermission(role, 'VIEW_STATUS')) {
    return NextResponse.json(
      { error: 'Forbidden: VIEW_STATUS permission required' },
      { status: 403 },
    );
  }
  if (!CONTROL_COMMANDS.has(command) && !STATUS_COMMANDS.has(command)) {
    return NextResponse.json({ error: 'Unknown command' }, { status: 400 });
  }

  // Forward to Cloud Function
  try {
    const upstream = await fetch(GCP_FUNCTION_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY,
        'X-User-Id': session.user.id,
        'X-User-Role': role,
      },
      body: JSON.stringify(body),
    });

    const data = await upstream.json().catch(() => ({ success: false, error: 'Invalid response' }));
    return NextResponse.json(data, { status: upstream.status });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Upstream connection failed';
    return NextResponse.json({ success: false, error: message }, { status: 502 });
  }
}
