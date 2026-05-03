import Foundation

/// Namespace for the wrack UDP video streaming protocol constants.
///
/// Wire format overview:
///
/// **Control messages (client → server)**
/// | Message            | Bytes               |
/// |--------------------|---------------------|
/// | `REGISTER_CLIENT`  | UTF-8 string, 15 B  |
/// | `KEEPALIVE`        | UTF-8 string,  9 B  |
/// | `DISCONNECT`       | UTF-8 string, 10 B  |
///
/// **Control messages (server → client)**
/// | Message            | Bytes               |
/// |--------------------|---------------------|
/// | `REGISTERED`       | UTF-8 string, 10 B  |
///
/// **Data packets (server → client)**
///
/// FRAME_START (primary 64-bit, 35 bytes):
///   `FRAME_START` (11 B) | frame_id UInt64 LE | frame_size UInt64 LE | chunk_count UInt64 LE
///
/// FRAME_START (fallback 32-bit, 23 bytes):
///   `FRAME_START` (11 B) | frame_id UInt32 LE | frame_size UInt32 LE | chunk_count UInt32 LE
///
/// CHUNK (primary 64-bit, 21 B header + payload):
///   `CHUNK` (5 B) | frame_id UInt64 LE | chunk_index UInt64 LE | payload (≤ chunkPayloadSize)
///
/// CHUNK (fallback 32-bit, 13 B header + payload):
///   `CHUNK` (5 B) | frame_id UInt32 LE | chunk_index UInt32 LE | payload (≤ chunkPayloadSize)
///
/// See: `shared/video-protocol/UDP_Frame_Format_Documentation.md`
public enum VideoProtocol {

    // MARK: - Network

    /// Default server port.
    public static let serverPort: UInt16 = 9999

    // MARK: - Framing

    /// Maximum payload bytes per CHUNK datagram.
    /// Sized to avoid IP fragmentation on most networks.
    public static let chunkPayloadSize: Int = 1200

    // MARK: - Timings

    /// Seconds before an idle client is evicted by the server.
    public static let clientTimeout: TimeInterval = 30

    /// Seconds between KEEPALIVE messages sent by the client.
    public static let keepaliveInterval: TimeInterval = 5

    // MARK: - Packet markers (internal — used by Packets.swift)

    static let frameStartMarker = Data("FRAME_START".utf8)  // 11 bytes
    static let chunkMarker      = Data("CHUNK".utf8)        //  5 bytes

    // MARK: - Control messages

    /// Sent by the client to register with the server and begin receiving frames.
    public static let registerClient = Data("REGISTER_CLIENT".utf8)

    /// Sent by the server to confirm registration.
    public static let registered     = Data("REGISTERED".utf8)

    /// Sent by the client periodically to prevent server-side timeout eviction.
    public static let keepalive      = Data("KEEPALIVE".utf8)

    /// Sent by the client to gracefully deregister before closing the socket.
    public static let disconnect     = Data("DISCONNECT".utf8)
}
