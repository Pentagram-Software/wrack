export type PeerRole = 'publisher' | 'subscriber';

// Messages sent from client to server
export type ClientMessageType =
  | 'join'
  | 'leave'
  | 'offer'
  | 'answer'
  | 'ice-candidate';

// Messages sent from server to client
export type ServerMessageType =
  | 'joined'
  | 'peer-joined'
  | 'peer-left'
  | 'offer'
  | 'answer'
  | 'ice-candidate'
  | 'error';

export interface JoinMessage {
  type: 'join';
  room: string;
  role: PeerRole;
}

export interface LeaveMessage {
  type: 'leave';
  room: string;
}

export interface OfferMessage {
  type: 'offer';
  room: string;
  sdp: RTCSessionDescriptionInit;
}

export interface AnswerMessage {
  type: 'answer';
  room: string;
  sdp: RTCSessionDescriptionInit;
}

export interface IceCandidateMessage {
  type: 'ice-candidate';
  room: string;
  candidate: RTCIceCandidateInit;
}

export type ClientMessage =
  | JoinMessage
  | LeaveMessage
  | OfferMessage
  | AnswerMessage
  | IceCandidateMessage;

export interface JoinedResponse {
  type: 'joined';
  room: string;
  role: PeerRole;
  hasPeer: boolean;
}

export interface PeerJoinedResponse {
  type: 'peer-joined';
  room: string;
  role: PeerRole;
}

export interface PeerLeftResponse {
  type: 'peer-left';
  room: string;
  role: PeerRole;
}

export interface RelayedOffer {
  type: 'offer';
  sdp: RTCSessionDescriptionInit;
}

export interface RelayedAnswer {
  type: 'answer';
  sdp: RTCSessionDescriptionInit;
}

export interface RelayedIceCandidate {
  type: 'ice-candidate';
  candidate: RTCIceCandidateInit;
}

export interface ErrorResponse {
  type: 'error';
  message: string;
}

export type ServerMessage =
  | JoinedResponse
  | PeerJoinedResponse
  | PeerLeftResponse
  | RelayedOffer
  | RelayedAnswer
  | RelayedIceCandidate
  | ErrorResponse;

/** Minimal interface for a WebSocket connection used by Room, enabling easy mocking in tests. */
export interface PeerSocket {
  send(data: string): void;
  readyState: number;
}

export const WS_OPEN = 1;
