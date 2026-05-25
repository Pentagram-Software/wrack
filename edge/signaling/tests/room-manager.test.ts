import { RoomManager } from '../src/room-manager.js';
import { PeerSocket, WS_OPEN } from '../src/types.js';

function makeMockSocket(): PeerSocket {
  return {
    readyState: WS_OPEN,
    send: jest.fn(),
  };
}

function makePeer(id: string, role: 'publisher' | 'subscriber') {
  return { id, role, socket: makeMockSocket() };
}

describe('RoomManager', () => {
  let manager: RoomManager;

  beforeEach(() => {
    manager = new RoomManager();
  });

  describe('join', () => {
    it('creates a room and adds the first peer', () => {
      const { room, error } = manager.join('cam-1', makePeer('p1', 'publisher'));
      expect(error).toBeNull();
      expect(room).not.toBeNull();
      expect(manager.roomCount).toBe(1);
      expect(manager.peerCount).toBe(1);
    });

    it('reuses an existing room for a second peer', () => {
      manager.join('cam-1', makePeer('p1', 'publisher'));
      const { room, error } = manager.join('cam-1', makePeer('s1', 'subscriber'));
      expect(error).toBeNull();
      expect(room).not.toBeNull();
      expect(manager.roomCount).toBe(1);
      expect(manager.peerCount).toBe(2);
    });

    it('creates separate rooms for different room ids', () => {
      manager.join('cam-1', makePeer('p1', 'publisher'));
      manager.join('cam-2', makePeer('p2', 'publisher'));
      expect(manager.roomCount).toBe(2);
    });

    it('returns error when a publisher slot is already taken', () => {
      manager.join('cam-1', makePeer('p1', 'publisher'));
      const { room, error } = manager.join('cam-1', makePeer('p2', 'publisher'));
      expect(error).toMatch(/already has a publisher/i);
      expect(room).toBeNull();
    });

    it('returns error for an empty room id', () => {
      const { room, error } = manager.join('', makePeer('p1', 'publisher'));
      expect(error).toMatch(/room id must not be empty/i);
      expect(room).toBeNull();
    });

    it('returns error for whitespace-only room id', () => {
      const { room, error } = manager.join('   ', makePeer('p1', 'publisher'));
      expect(error).toMatch(/room id must not be empty/i);
      expect(room).toBeNull();
    });

    it('does not create an empty room when join fails', () => {
      manager.join('cam-1', makePeer('p1', 'publisher'));
      manager.join('cam-1', makePeer('p2', 'publisher')); // fails
      expect(manager.roomCount).toBe(1); // only the first room
    });
  });

  describe('leave', () => {
    it('removes a peer and returns room and role', () => {
      manager.join('cam-1', makePeer('p1', 'publisher'));
      const { room, role } = manager.leave('p1');
      expect(role).toBe('publisher');
      expect(room).not.toBeNull();
    });

    it('deletes the room when it becomes empty', () => {
      manager.join('cam-1', makePeer('p1', 'publisher'));
      manager.leave('p1');
      expect(manager.roomCount).toBe(0);
      expect(manager.peerCount).toBe(0);
    });

    it('keeps the room when a peer remains', () => {
      manager.join('cam-1', makePeer('p1', 'publisher'));
      manager.join('cam-1', makePeer('s1', 'subscriber'));
      manager.leave('p1');
      expect(manager.roomCount).toBe(1);
      expect(manager.peerCount).toBe(1);
    });

    it('returns null role for an unknown peer', () => {
      const { room, role } = manager.leave('ghost');
      expect(room).toBeNull();
      expect(role).toBeNull();
    });

    it('decrements peer count', () => {
      manager.join('cam-1', makePeer('p1', 'publisher'));
      manager.join('cam-1', makePeer('s1', 'subscriber'));
      manager.leave('s1');
      expect(manager.peerCount).toBe(1);
    });
  });

  describe('getRoomForPeer / getRoom', () => {
    it('returns the room a peer belongs to', () => {
      manager.join('cam-1', makePeer('p1', 'publisher'));
      const room = manager.getRoomForPeer('p1');
      expect(room).not.toBeNull();
      expect(room?.id).toBe('cam-1');
    });

    it('returns null for an unknown peer', () => {
      expect(manager.getRoomForPeer('unknown')).toBeNull();
    });

    it('returns null after peer leaves', () => {
      manager.join('cam-1', makePeer('p1', 'publisher'));
      manager.leave('p1');
      expect(manager.getRoomForPeer('p1')).toBeNull();
    });

    it('getRoom returns room by id', () => {
      manager.join('cam-1', makePeer('p1', 'publisher'));
      expect(manager.getRoom('cam-1')).not.toBeNull();
      expect(manager.getRoom('non-existent')).toBeNull();
    });
  });

  describe('getPeerRole', () => {
    it('returns publisher for a publisher peer', () => {
      manager.join('cam-1', makePeer('p1', 'publisher'));
      expect(manager.getPeerRole('p1')).toBe('publisher');
    });

    it('returns subscriber for a subscriber peer', () => {
      manager.join('cam-1', makePeer('p1', 'publisher'));
      manager.join('cam-1', makePeer('s1', 'subscriber'));
      expect(manager.getPeerRole('s1')).toBe('subscriber');
    });

    it('returns null for unknown peer', () => {
      expect(manager.getPeerRole('ghost')).toBeNull();
    });
  });

  describe('roomCount / peerCount', () => {
    it('starts at zero', () => {
      expect(manager.roomCount).toBe(0);
      expect(manager.peerCount).toBe(0);
    });

    it('tracks multiple rooms and peers', () => {
      manager.join('room-a', makePeer('p1', 'publisher'));
      manager.join('room-a', makePeer('s1', 'subscriber'));
      manager.join('room-b', makePeer('p2', 'publisher'));
      expect(manager.roomCount).toBe(2);
      expect(manager.peerCount).toBe(3);
    });
  });
});
