import Foundation

/// Reassembles UDP chunks into complete video frames.
/// Thread-safe — can be called from any queue.
public final class FrameAssembler {

    private struct PendingFrame {
        var buffer:          Data
        var expectedChunks:  Int
        var receivedIndices: Set<UInt64>
    }

    private var pending: [UInt64: PendingFrame] = [:]
    private let lock = NSLock()

    public init() {}

    /// Register a new incoming frame. Call when you receive a FrameStartPacket.
    public func handleFrameStart(_ packet: FrameStartPacket) {
        lock.withLock {
            pending[packet.frameID] = PendingFrame(
                buffer: Data(count: Int(packet.frameSize)),
                expectedChunks: Int(packet.chunkCount),
                receivedIndices: []
            )
        }
    }

    /// Append a chunk. Returns the complete frame data once all chunks have arrived.
    public func handleChunk(_ packet: ChunkPacket) -> Data? {
        lock.withLock {
            guard var frame = pending[packet.frameID] else { return nil }
            guard !frame.receivedIndices.contains(packet.chunkIndex) else { return nil }

            let offset = Int(packet.chunkIndex) * VideoProtocol.chunkPayloadSize
            guard offset < frame.buffer.count else { return nil }

            let end = min(offset + packet.payload.count, frame.buffer.count)
            frame.buffer.replaceSubrange(offset..<end, with: packet.payload.prefix(end - offset))
            frame.receivedIndices.insert(packet.chunkIndex)

            if frame.receivedIndices.count >= frame.expectedChunks {
                let complete = frame.buffer
                pending.removeValue(forKey: packet.frameID)
                return complete
            }

            pending[packet.frameID] = frame
            return nil
        }
    }

    /// Drop stale partial frames, keeping only the newest `count` frame IDs.
    /// Call periodically to bound memory usage on lossy networks.
    public func pruneStale(keepingLast count: Int = 30) {
        lock.withLock {
            guard pending.count > count else { return }
            pending.keys.sorted().prefix(pending.count - count).forEach {
                pending.removeValue(forKey: $0)
            }
        }
    }
}
