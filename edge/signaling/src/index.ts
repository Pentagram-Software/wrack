import { SignalingServer } from './server.js';

const PORT = parseInt(process.env.SIGNALING_PORT ?? '3001', 10);
const ALLOWED_ROOMS = process.env.ALLOWED_ROOMS
  ? process.env.ALLOWED_ROOMS.split(',').map((r) => r.trim()).filter(Boolean)
  : [];

const server = new SignalingServer({ port: PORT, allowedRooms: ALLOWED_ROOMS });

server.listen().then(() => {
  console.log(`[signaling] WebRTC signaling server running on port ${PORT}`);
});

process.on('SIGTERM', () => {
  console.log('[signaling] shutting down...');
  server.close().then(() => process.exit(0));
});

process.on('SIGINT', () => {
  console.log('[signaling] shutting down...');
  server.close().then(() => process.exit(0));
});
