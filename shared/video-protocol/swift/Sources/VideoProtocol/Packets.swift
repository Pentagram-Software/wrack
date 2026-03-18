import Foundation

// MARK: - FrameStartPacket

/// Parsed FRAME_START packet.
///
/// Wire layout (64-bit / primary):
///   "FRAME_START" (11B) | frame_id (UInt64 LE) | frame_size (UInt64 LE) | chunk_count (UInt64 LE)
///   Total: 35 bytes
///
/// Wire layout (32-bit / fallback):
///   "FRAME_START" (11B) | frame_id (UInt32 LE) | frame_size (UInt32 LE) | chunk_count (UInt32 LE)
///   Total: 23 bytes
public struct FrameStartPacket {
    public let frameID:     UInt64
    public let frameSize:   UInt64
    public let chunkCount:  UInt64

    /// Parse from a raw UDP datagram. Returns nil for unrecognised data.
    public static func parse(from data: Data) -> FrameStartPacket? {
        let marker = VideoProtocol.frameStartMarker
        guard data.starts(with: marker) else { return nil }
        let body = data.dropFirst(marker.count)

        if data.count == 35 {            // 64-bit format (Raspberry Pi 64-bit, primary)
            return body.withUnsafeBytes { ptr -> FrameStartPacket? in
                guard ptr.count >= 24 else { return nil }
                let frameID    = UInt64(littleEndian: ptr.loadUnaligned(fromByteOffset:  0, as: UInt64.self))
                let frameSize  = UInt64(littleEndian: ptr.loadUnaligned(fromByteOffset:  8, as: UInt64.self))
                let chunkCount = UInt64(littleEndian: ptr.loadUnaligned(fromByteOffset: 16, as: UInt64.self))
                return FrameStartPacket(frameID: frameID, frameSize: frameSize, chunkCount: chunkCount)
            }
        } else if data.count >= 23 {    // 32-bit fallback
            return body.withUnsafeBytes { ptr -> FrameStartPacket? in
                guard ptr.count >= 12 else { return nil }
                let frameID    = UInt64(UInt32(littleEndian: ptr.loadUnaligned(fromByteOffset: 0, as: UInt32.self)))
                let frameSize  = UInt64(UInt32(littleEndian: ptr.loadUnaligned(fromByteOffset: 4, as: UInt32.self)))
                let chunkCount = UInt64(UInt32(littleEndian: ptr.loadUnaligned(fromByteOffset: 8, as: UInt32.self)))
                return FrameStartPacket(frameID: frameID, frameSize: frameSize, chunkCount: chunkCount)
            }
        }

        return nil
    }
}

// MARK: - ChunkPacket

/// Parsed CHUNK packet.
///
/// Wire layout (64-bit / primary):
///   "CHUNK" (5B) | frame_id (UInt64 LE) | chunk_index (UInt64 LE) | payload (≤1200B)
///   Header: 21 bytes
///
/// Wire layout (32-bit / fallback):
///   "CHUNK" (5B) | frame_id (UInt32 LE) | chunk_index (UInt32 LE) | payload (≤1200B)
///   Header: 13 bytes
public struct ChunkPacket {
    public let frameID:     UInt64
    public let chunkIndex:  UInt64
    public let payload:     Data

    public static func parse(from data: Data) -> ChunkPacket? {
        let marker = VideoProtocol.chunkMarker
        guard data.starts(with: marker) else { return nil }

        let header64Size = marker.count + 16   // 21 bytes
        let header32Size = marker.count + 8    // 13 bytes

        if data.count >= header64Size {        // Try 64-bit first (primary)
            let parsed: ChunkPacket? = data.dropFirst(marker.count).withUnsafeBytes { ptr in
                guard ptr.count >= 16 else { return nil }
                let frameID    = UInt64(littleEndian: ptr.loadUnaligned(fromByteOffset: 0, as: UInt64.self))
                let chunkIndex = UInt64(littleEndian: ptr.loadUnaligned(fromByteOffset: 8, as: UInt64.self))
                let payload    = data.suffix(from: header64Size)
                return ChunkPacket(frameID: frameID, chunkIndex: chunkIndex, payload: payload)
            }
            if let parsed { return parsed }
        }

        if data.count >= header32Size {        // 32-bit fallback
            return data.dropFirst(marker.count).withUnsafeBytes { ptr in
                guard ptr.count >= 8 else { return nil }
                let frameID    = UInt64(UInt32(littleEndian: ptr.loadUnaligned(fromByteOffset: 0, as: UInt32.self)))
                let chunkIndex = UInt64(UInt32(littleEndian: ptr.loadUnaligned(fromByteOffset: 4, as: UInt32.self)))
                let payload    = data.suffix(from: header32Size)
                return ChunkPacket(frameID: frameID, chunkIndex: chunkIndex, payload: payload)
            }
        }

        return nil
    }
}
