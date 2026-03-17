import XCTest
@testable import VideoProtocol

final class PacketTests: XCTestCase {

    // MARK: - FrameStartPacket (64-bit)

    func testFrameStartPacket_64bit() throws {
        var data = Data("FRAME_START".utf8)
        func appendUInt64LE(_ v: UInt64) {
            var le = v.littleEndian
            data.append(contentsOf: withUnsafeBytes(of: &le) { Array($0) })
        }
        appendUInt64LE(42)      // frameID
        appendUInt64LE(50_000)  // frameSize
        appendUInt64LE(42)      // chunkCount

        XCTAssertEqual(data.count, 35)
        let packet = try XCTUnwrap(FrameStartPacket.parse(from: data))
        XCTAssertEqual(packet.frameID,    42)
        XCTAssertEqual(packet.frameSize,  50_000)
        XCTAssertEqual(packet.chunkCount, 42)
    }

    // MARK: - FrameStartPacket (32-bit fallback)

    func testFrameStartPacket_32bit() throws {
        var data = Data("FRAME_START".utf8)
        func appendUInt32LE(_ v: UInt32) {
            var le = v.littleEndian
            data.append(contentsOf: withUnsafeBytes(of: &le) { Array($0) })
        }
        appendUInt32LE(7)       // frameID
        appendUInt32LE(20_000)  // frameSize
        appendUInt32LE(17)      // chunkCount

        XCTAssertEqual(data.count, 23)
        let packet = try XCTUnwrap(FrameStartPacket.parse(from: data))
        XCTAssertEqual(packet.frameID,    7)
        XCTAssertEqual(packet.frameSize,  20_000)
        XCTAssertEqual(packet.chunkCount, 17)
    }

    // MARK: - ChunkPacket (64-bit)

    func testChunkPacket_64bit() throws {
        var data = Data("CHUNK".utf8)
        func appendUInt64LE(_ v: UInt64) {
            var le = v.littleEndian
            data.append(contentsOf: withUnsafeBytes(of: &le) { Array($0) })
        }
        appendUInt64LE(42)   // frameID
        appendUInt64LE(3)    // chunkIndex
        let payload = Data(repeating: 0xAB, count: 1200)
        data.append(payload)

        let packet = try XCTUnwrap(ChunkPacket.parse(from: data))
        XCTAssertEqual(packet.frameID,    42)
        XCTAssertEqual(packet.chunkIndex, 3)
        XCTAssertEqual(packet.payload,    payload)
    }

    // MARK: - FrameAssembler

    func testFrameAssembler_reassemblesFrame() throws {
        let assembler = FrameAssembler()
        let totalSize = 2500
        let chunkPayload = VideoProtocol.chunkPayloadSize
        let chunkCount = (totalSize + chunkPayload - 1) / chunkPayload  // 3

        // Build fake frame data
        let frameData = Data((0..<totalSize).map { UInt8($0 & 0xFF) })

        // Send FRAME_START
        var startData = Data("FRAME_START".utf8)
        for v: UInt64 in [1, UInt64(totalSize), UInt64(chunkCount)] {
            var le = v.littleEndian
            startData.append(contentsOf: withUnsafeBytes(of: &le) { Array($0) })
        }
        let startPacket = try XCTUnwrap(FrameStartPacket.parse(from: startData))
        assembler.handleFrameStart(startPacket)

        // Send chunks
        var assembled: Data?
        for idx in 0..<chunkCount {
            let offset = idx * chunkPayload
            let end = min(offset + chunkPayload, totalSize)
            let payload = frameData[offset..<end]

            var chunkData = Data("CHUNK".utf8)
            for v: UInt64 in [1, UInt64(idx)] {
                var le = v.littleEndian
                chunkData.append(contentsOf: withUnsafeBytes(of: &le) { Array($0) })
            }
            chunkData.append(payload)

            let chunk = try XCTUnwrap(ChunkPacket.parse(from: chunkData))
            assembled = assembler.handleChunk(chunk)
        }

        XCTAssertEqual(assembled, frameData)
    }

    // MARK: - Unrecognised data returns nil

    func testParseReturnsNilForGarbage() {
        let garbage = Data(repeating: 0xFF, count: 50)
        XCTAssertNil(FrameStartPacket.parse(from: garbage))
        XCTAssertNil(ChunkPacket.parse(from: garbage))
    }
}
