import { Room, RoomPeer } from './room.js';
import { PeerRole } from './types.js';

/**
 * Manages the set of active signaling rooms and the mapping from peer ids to rooms.
 * All methods are synchronous; the server is single-threaded (Node.js event loop).
 */
export class RoomManager {
  private rooms = new Map<string, Room>();
  /** Maps peerId → roomId for fast lookup on disconnect. */
  private peerToRoom = new Map<string, string>();

  /**
   * Adds a peer to a room (creating the room if needed).
   * @returns `{ room, error }` — error is a non-null string when the join fails.
   */
  join(
    roomId: string,
    peer: RoomPeer,
  ): { room: Room | null; error: string | null } {
    if (!roomId || roomId.trim() === '') {
      return { room: null, error: 'Room id must not be empty' };
    }

    let room = this.rooms.get(roomId);
    if (!room) {
      room = new Room(roomId);
      this.rooms.set(roomId, room);
    }

    const error = room.addPeer(peer);
    if (error) {
      // Clean up empty room created just now
      if (room.isEmpty) {
        this.rooms.delete(roomId);
      }
      return { room: null, error };
    }

    this.peerToRoom.set(peer.id, roomId);
    return { room, error: null };
  }

  /**
   * Removes a peer from whichever room they are in.
   * Cleans up empty rooms automatically.
   * @returns `{ room, role }` — the room and the role that was removed, or nulls if not found.
   */
  leave(peerId: string): { room: Room | null; role: PeerRole | null } {
    const roomId = this.peerToRoom.get(peerId);
    if (!roomId) {
      return { room: null, role: null };
    }

    const room = this.rooms.get(roomId);
    if (!room) {
      this.peerToRoom.delete(peerId);
      return { room: null, role: null };
    }

    const role = room.removePeer(peerId);
    this.peerToRoom.delete(peerId);

    if (room.isEmpty) {
      this.rooms.delete(roomId);
    }

    return { room, role };
  }

  /** Returns the room a peer belongs to, or null. */
  getRoomForPeer(peerId: string): Room | null {
    const roomId = this.peerToRoom.get(peerId);
    if (!roomId) return null;
    return this.rooms.get(roomId) ?? null;
  }

  /** Returns a room by id, or null if it does not exist. */
  getRoom(roomId: string): Room | null {
    return this.rooms.get(roomId) ?? null;
  }

  /** Number of active rooms (rooms with at least one peer). */
  get roomCount(): number {
    return this.rooms.size;
  }

  /** Number of peers tracked across all rooms. */
  get peerCount(): number {
    return this.peerToRoom.size;
  }

  /** Returns the role of a peer across all rooms, or null. */
  getPeerRole(peerId: string): PeerRole | null {
    const room = this.getRoomForPeer(peerId);
    if (!room) return null;
    return room.getPeerRole(peerId);
  }
}
