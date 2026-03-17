import Foundation

/// Constants for the UDP video streaming protocol.
/// See: shared/video-protocol/UDP_Frame_Format_Documentation.md
public enum VideoProtocol {
    public static let serverPort: UInt16 = 9999
    public static let chunkPayloadSize: Int = 1200
    public static let clientTimeout: TimeInterval = 30
    public static let keepaliveInterval: TimeInterval = 5

    // Packet markers
    static let frameStartMarker = Data("FRAME_START".utf8)  // 11 bytes
    static let chunkMarker      = Data("CHUNK".utf8)        //  5 bytes

    // Control messages
    public static let registerClient = Data("REGISTER_CLIENT".utf8)
    public static let registered     = Data("REGISTERED".utf8)
    public static let keepalive      = Data("KEEPALIVE".utf8)
    public static let disconnect     = Data("DISCONNECT".utf8)

    /// Wire format for header integer fields.
    /// Raspberry Pi 64-bit (primary): struct.pack("LLL") → 3 × UInt64 (little-endian)
    /// Legacy 32-bit (fallback):      struct.pack("III") → 3 × UInt32 (little-endian)
    enum HeaderFormat {
        case uint64  // packet size: 11 + 24 = 35 bytes (FRAME_START), 5 + 16 = 21 (CHUNK header)
        case uint32  // packet size: 11 + 12 = 23 bytes (FRAME_START), 5 +  8 = 13 (CHUNK header)
    }
}
