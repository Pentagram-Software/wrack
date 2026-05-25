import { Room } from '../src/room.js';
import { PeerSocket, WS_OPEN } from '../src/types.js';

function makeMockSocket(readyState = WS_OPEN): PeerSocket & { messages: string[] } {
  const messages: string[] = [];
  return {
    readyState,
    send(data: string) {
      messages.push(data);
    },
    messages,
  };
}

function makePeer(id: string, role: 'publisher' | 'subscriber', readyState = WS_OPEN) {
  return { id, role, socket: makeMockSocket(readyState) };
}

describe('Room', () => {
  describe('construction', () => {
    it('creates a room with the given id', () => {
      const room = new Room('cam-1');
      expect(room.id).toBe('cam-1');
    });

    it('starts empty', () => {
      const room = new Room('cam-1');
      expect(room.isEmpty).toBe(true);
      expect(room.hasPublisher).toBe(false);
      expect(room.hasSubscriber).toBe(false);
    });
  });

  describe('addPeer', () => {
    it('accepts a publisher', () => {
      const room = new Room('r1');
      const error = room.addPeer(makePeer('p1', 'publisher'));
      expect(error).toBeNull();
      expect(room.hasPublisher).toBe(true);
      expect(room.isEmpty).toBe(false);
    });

    it('accepts a subscriber', () => {
      const room = new Room('r1');
      const error = room.addPeer(makePeer('s1', 'subscriber'));
      expect(error).toBeNull();
      expect(room.hasSubscriber).toBe(true);
    });

    it('rejects a second publisher', () => {
      const room = new Room('r1');
      room.addPeer(makePeer('p1', 'publisher'));
      const error = room.addPeer(makePeer('p2', 'publisher'));
      expect(error).toMatch(/already has a publisher/i);
    });

    it('rejects a second subscriber', () => {
      const room = new Room('r1');
      room.addPeer(makePeer('s1', 'subscriber'));
      const error = room.addPeer(makePeer('s2', 'subscriber'));
      expect(error).toMatch(/already has a subscriber/i);
    });
  });

  describe('removePeer', () => {
    it('removes the publisher and returns its role', () => {
      const room = new Room('r1');
      room.addPeer(makePeer('p1', 'publisher'));
      const role = room.removePeer('p1');
      expect(role).toBe('publisher');
      expect(room.hasPublisher).toBe(false);
      expect(room.isEmpty).toBe(true);
    });

    it('removes the subscriber and returns its role', () => {
      const room = new Room('r1');
      room.addPeer(makePeer('s1', 'subscriber'));
      const role = room.removePeer('s1');
      expect(role).toBe('subscriber');
      expect(room.hasSubscriber).toBe(false);
    });

    it('returns null when peer is not found', () => {
      const room = new Room('r1');
      expect(room.removePeer('unknown')).toBeNull();
    });
  });

  describe('hasPeer / getPeerRole / getOpposite', () => {
    it('identifies whether a peer is in the room', () => {
      const room = new Room('r1');
      room.addPeer(makePeer('p1', 'publisher'));
      expect(room.hasPeer('p1')).toBe(true);
      expect(room.hasPeer('x')).toBe(false);
    });

    it('returns the correct role for each peer', () => {
      const room = new Room('r1');
      room.addPeer(makePeer('p1', 'publisher'));
      room.addPeer(makePeer('s1', 'subscriber'));
      expect(room.getPeerRole('p1')).toBe('publisher');
      expect(room.getPeerRole('s1')).toBe('subscriber');
      expect(room.getPeerRole('unknown')).toBeNull();
    });

    it('returns the opposite peer', () => {
      const room = new Room('r1');
      const pub = makePeer('p1', 'publisher');
      const sub = makePeer('s1', 'subscriber');
      room.addPeer(pub);
      room.addPeer(sub);

      expect(room.getOpposite('p1')?.id).toBe('s1');
      expect(room.getOpposite('s1')?.id).toBe('p1');
      expect(room.getOpposite('unknown')).toBeNull();
    });

    it('returns null when opposite does not exist', () => {
      const room = new Room('r1');
      room.addPeer(makePeer('p1', 'publisher'));
      expect(room.getOpposite('p1')).toBeNull();
    });
  });

  describe('relay', () => {
    it('sends a message to the opposite peer', () => {
      const room = new Room('r1');
      const pub = makePeer('p1', 'publisher');
      const sub = makePeer('s1', 'subscriber');
      room.addPeer(pub);
      room.addPeer(sub);

      const delivered = room.relay('p1', { type: 'offer', sdp: { type: 'offer', sdp: 'v=0' } });
      expect(delivered).toBe(true);
      expect((sub.socket as ReturnType<typeof makeMockSocket>).messages).toHaveLength(1);
      const parsed = JSON.parse((sub.socket as ReturnType<typeof makeMockSocket>).messages[0]);
      expect(parsed.type).toBe('offer');
    });

    it('returns false when the opposite peer is missing', () => {
      const room = new Room('r1');
      room.addPeer(makePeer('p1', 'publisher'));
      const delivered = room.relay('p1', { type: 'offer', sdp: { type: 'offer', sdp: 'v=0' } });
      expect(delivered).toBe(false);
    });

    it('returns false when the opposite socket is not open', () => {
      const room = new Room('r1');
      room.addPeer(makePeer('p1', 'publisher'));
      room.addPeer(makePeer('s1', 'subscriber', 3 /* CLOSED */));
      const delivered = room.relay('p1', { type: 'offer', sdp: { type: 'offer', sdp: 'v=0' } });
      expect(delivered).toBe(false);
    });
  });

  describe('sendTo', () => {
    it('sends a message directly to the specified peer', () => {
      const room = new Room('r1');
      const pub = makePeer('p1', 'publisher');
      room.addPeer(pub);

      const sent = room.sendTo('p1', { type: 'error', message: 'oops' });
      expect(sent).toBe(true);
      expect((pub.socket as ReturnType<typeof makeMockSocket>).messages).toHaveLength(1);
    });

    it('returns false for an unknown peer', () => {
      const room = new Room('r1');
      expect(room.sendTo('unknown', { type: 'error', message: 'oops' })).toBe(false);
    });
  });

  describe('validateOffer / validateAnswer', () => {
    it('allows publisher to send an offer when subscriber is present', () => {
      const room = new Room('r1');
      room.addPeer(makePeer('p1', 'publisher'));
      room.addPeer(makePeer('s1', 'subscriber'));
      expect(room.validateOffer('p1')).toBeNull();
    });

    it('rejects offer from non-publisher', () => {
      const room = new Room('r1');
      room.addPeer(makePeer('p1', 'publisher'));
      room.addPeer(makePeer('s1', 'subscriber'));
      expect(room.validateOffer('s1')).toMatch(/only the publisher/i);
    });

    it('rejects offer when no subscriber is present', () => {
      const room = new Room('r1');
      room.addPeer(makePeer('p1', 'publisher'));
      expect(room.validateOffer('p1')).toMatch(/no subscriber/i);
    });

    it('allows subscriber to send an answer when publisher is present', () => {
      const room = new Room('r1');
      room.addPeer(makePeer('p1', 'publisher'));
      room.addPeer(makePeer('s1', 'subscriber'));
      expect(room.validateAnswer('s1')).toBeNull();
    });

    it('rejects answer from non-subscriber', () => {
      const room = new Room('r1');
      room.addPeer(makePeer('p1', 'publisher'));
      room.addPeer(makePeer('s1', 'subscriber'));
      expect(room.validateAnswer('p1')).toMatch(/only the subscriber/i);
    });

    it('rejects answer when no publisher is present', () => {
      const room = new Room('r1');
      room.addPeer(makePeer('s1', 'subscriber'));
      expect(room.validateAnswer('s1')).toMatch(/no publisher/i);
    });
  });

  describe('static builders', () => {
    it('builds an offer payload', () => {
      const sdp: RTCSessionDescriptionInit = { type: 'offer', sdp: 'v=0' };
      expect(Room.buildOffer(sdp)).toEqual({ type: 'offer', sdp });
    });

    it('builds an answer payload', () => {
      const sdp: RTCSessionDescriptionInit = { type: 'answer', sdp: 'v=0' };
      expect(Room.buildAnswer(sdp)).toEqual({ type: 'answer', sdp });
    });

    it('builds an ICE candidate payload', () => {
      const candidate: RTCIceCandidateInit = { candidate: 'a=candidate:1', sdpMid: '0' };
      expect(Room.buildIceCandidate(candidate)).toEqual({ type: 'ice-candidate', candidate });
    });
  });
});
