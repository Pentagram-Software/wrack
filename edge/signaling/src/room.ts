import {
  PeerRole,
  PeerSocket,
  ServerMessage,
  WS_OPEN,
  RelayedOffer,
  RelayedAnswer,
  RelayedIceCandidate,
} from './types.js';

export interface RoomPeer {
  id: string;
  role: PeerRole;
  socket: PeerSocket;
}

/**
 * Represents a signaling room that mediates between one publisher (Pi camera)
 * and one subscriber (browser). Additional subscriber connections are rejected
 * to keep the initial implementation minimal.
 */
export class Room {
  readonly id: string;
  private publisher: RoomPeer | null = null;
  private subscriber: RoomPeer | null = null;

  constructor(id: string) {
    this.id = id;
  }

  get publisherPeer(): RoomPeer | null {
    return this.publisher;
  }

  get subscriberPeer(): RoomPeer | null {
    return this.subscriber;
  }

  get isEmpty(): boolean {
    return this.publisher === null && this.subscriber === null;
  }

  get hasPublisher(): boolean {
    return this.publisher !== null;
  }

  get hasSubscriber(): boolean {
    return this.subscriber !== null;
  }

  /**
   * Attempts to add a peer to the room.
   * @returns `null` on success, or an error string on failure.
   */
  addPeer(peer: RoomPeer): string | null {
    if (peer.role === 'publisher') {
      if (this.publisher !== null) {
        return 'Room already has a publisher';
      }
      this.publisher = peer;
    } else {
      if (this.subscriber !== null) {
        return 'Room already has a subscriber';
      }
      this.subscriber = peer;
    }
    return null;
  }

  /**
   * Removes a peer by peer id. Returns the removed peer's role, or null if not found.
   */
  removePeer(peerId: string): PeerRole | null {
    if (this.publisher?.id === peerId) {
      this.publisher = null;
      return 'publisher';
    }
    if (this.subscriber?.id === peerId) {
      this.subscriber = null;
      return 'subscriber';
    }
    return null;
  }

  /**
   * Returns the peer with the opposing role relative to the given peer id.
   */
  getOpposite(peerId: string): RoomPeer | null {
    if (this.publisher?.id === peerId) {
      return this.subscriber;
    }
    if (this.subscriber?.id === peerId) {
      return this.publisher;
    }
    return null;
  }

  /**
   * Returns the role of the peer identified by `peerId`, or null if not in this room.
   */
  getPeerRole(peerId: string): PeerRole | null {
    if (this.publisher?.id === peerId) return 'publisher';
    if (this.subscriber?.id === peerId) return 'subscriber';
    return null;
  }

  /** Checks whether a peer id belongs to this room. */
  hasPeer(peerId: string): boolean {
    return this.publisher?.id === peerId || this.subscriber?.id === peerId;
  }

  /**
   * Forwards a message to the peer that is opposite in role to the sender.
   * @returns true if the message was delivered, false if there is no opposite peer.
   */
  relay(fromPeerId: string, message: ServerMessage): boolean {
    const opposite = this.getOpposite(fromPeerId);
    if (!opposite || opposite.socket.readyState !== WS_OPEN) {
      return false;
    }
    opposite.socket.send(JSON.stringify(message));
    return true;
  }

  /** Sends a message directly to a peer by id. */
  sendTo(peerId: string, message: ServerMessage): boolean {
    const peer =
      this.publisher?.id === peerId
        ? this.publisher
        : this.subscriber?.id === peerId
          ? this.subscriber
          : null;

    if (!peer || peer.socket.readyState !== WS_OPEN) {
      return false;
    }
    peer.socket.send(JSON.stringify(message));
    return true;
  }

  /**
   * Validates that an offer can be forwarded.
   * Only publishers may send offers; a subscriber must be present.
   */
  validateOffer(fromPeerId: string): string | null {
    if (this.publisher?.id !== fromPeerId) {
      return 'Only the publisher may send an offer';
    }
    if (this.subscriber === null) {
      return 'No subscriber in room to receive offer';
    }
    return null;
  }

  /**
   * Validates that an answer can be forwarded.
   * Only subscribers may send answers; a publisher must be present.
   */
  validateAnswer(fromPeerId: string): string | null {
    if (this.subscriber?.id !== fromPeerId) {
      return 'Only the subscriber may send an answer';
    }
    if (this.publisher === null) {
      return 'No publisher in room to receive answer';
    }
    return null;
  }

  /**
   * Builds a `RelayedOffer` payload (without room-level routing info).
   */
  static buildOffer(sdp: RTCSessionDescriptionInit): RelayedOffer {
    return { type: 'offer', sdp };
  }

  static buildAnswer(sdp: RTCSessionDescriptionInit): RelayedAnswer {
    return { type: 'answer', sdp };
  }

  static buildIceCandidate(candidate: RTCIceCandidateInit): RelayedIceCandidate {
    return { type: 'ice-candidate', candidate };
  }
}
