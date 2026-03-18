import Foundation

/// Assembles video frames from chunks received via the video protocol.
///
/// Maintains pending frame buffers and tracks which chunks have been received.
/// When all chunks for a frame are received, returns the complete frame data.
final class FrameAssembler {
    
    // MARK: - Properties
    
    private var pendingFrames: [UInt64: PendingFrame] = [:]
    private let staleTimeout: TimeInterval = 5.0
    
    // MARK: - Nested Types
    
    private struct PendingFrame {
        var buffer: Data
        var expectedChunkCount: UInt64
        var receivedChunks: Set<UInt64>
        var timestamp: Date
        
        init(frameSize: UInt64, chunkCount: UInt64) {
            self.buffer = Data(count: Int(frameSize))
            self.expectedChunkCount = chunkCount
            self.receivedChunks = Set<UInt64>()
            self.timestamp = Date()
        }
        
        var isComplete: Bool {
            return receivedChunks.count >= expectedChunkCount
        }
    }
    
    // MARK: - Public API
    
    /// Handle a FRAME_START packet, preparing a buffer for the incoming frame.
    func handleFrameStart(_ packet: FrameStartPacket) {
        guard packet.frameSize > 0 && packet.frameSize < 50_000_000 else {
            print("⚠️ Invalid frame size: \(packet.frameSize)")
            return
        }
        
        pendingFrames[packet.frameID] = PendingFrame(
            frameSize: packet.frameSize,
            chunkCount: packet.chunkCount
        )
        
        print("📦 Frame \(packet.frameID): Expecting \(packet.chunkCount) chunks, \(packet.frameSize) bytes")
    }
    
    /// Handle a CHUNK packet, assembling it into the appropriate frame buffer.
    /// Returns the complete frame data if this was the final chunk.
    func handleChunk(_ packet: ChunkPacket) -> Data? {
        guard var frame = pendingFrames[packet.frameID] else {
            print("⚠️ Received chunk for unknown frame \(packet.frameID)")
            return nil
        }
        
        // Avoid processing duplicate chunks
        guard !frame.receivedChunks.contains(packet.chunkIndex) else {
            return nil
        }
        
        // Calculate offset and copy chunk data into frame buffer
        let offset = Int(packet.chunkIndex) * VideoProtocol.chunkPayloadSize
        guard offset < frame.buffer.count else {
            print("⚠️ Chunk offset \(offset) exceeds frame buffer size \(frame.buffer.count)")
            return nil
        }
        
        let endOffset = min(offset + packet.payload.count, frame.buffer.count)
        let rangeToReplace = offset..<endOffset
        frame.buffer.replaceSubrange(rangeToReplace, with: packet.payload.prefix(endOffset - offset))
        
        // Mark chunk as received
        frame.receivedChunks.insert(packet.chunkIndex)
        pendingFrames[packet.frameID] = frame
        
        // Check if frame is complete
        if frame.isComplete {
            print("✅ Frame \(packet.frameID) complete: \(frame.receivedChunks.count)/\(frame.expectedChunkCount) chunks")
            let completeFrame = frame.buffer
            pendingFrames.removeValue(forKey: packet.frameID)
            return completeFrame
        }
        
        return nil
    }
    
    /// Remove frames that haven't received chunks recently (stale frames).
    func pruneStale() {
        let now = Date()
        let staleFrameIDs = pendingFrames.filter { _, frame in
            now.timeIntervalSince(frame.timestamp) > staleTimeout
        }.map { $0.key }
        
        for frameID in staleFrameIDs {
            print("🗑️ Pruning stale frame \(frameID)")
            pendingFrames.removeValue(forKey: frameID)
        }
    }
    
    /// Clear all pending frames.
    func reset() {
        pendingFrames.removeAll()
    }
}
