import SwiftUI
import AVFoundation
import VideoToolbox
import VideoProtocol

// MARK: - VideoStreamManager

class VideoStreamManager: NSObject, ObservableObject {
    @Published var isConnected = false
    @Published var currentFrame: UIImage?
    @Published var frameCount: Int = 0
    @Published var connectionStatus: String = "Disconnected"

    private var client: VideoStreamClient?
    private var decoder: H264Decoder?
    private let host: String
    private let port: UInt16

//    init(host: String = "192.168.1.216", port: UInt16 = 9999) {
    init(host: String = "178.183.200.201", port: UInt16 = 9999) {
        self.host = host
        self.port = port
        super.init()
        self.decoder = H264Decoder(delegate: self)
    }

    func connect() {
        guard client == nil else { return }
        connectionStatus = "Connecting..."
        let videoClient = VideoStreamClient(host: host, port: port)
        videoClient.delegate = self
        videoClient.connect()
        client = videoClient
    }

    func disconnect() {
        client?.disconnect()
        client = nil
        decoder?.invalidate()
        isConnected = false
        connectionStatus = "Disconnected"
        currentFrame = nil
    }
}

// MARK: - VideoStreamClientDelegate

extension VideoStreamManager: VideoStreamClientDelegate {
    func videoStreamClient(_ client: VideoStreamClient, didReceiveH264Frame data: Data) {
        decoder?.decode(h264Data: data)
    }

    func videoStreamClient(_ client: VideoStreamClient, didChangeState state: VideoStreamClient.State) {
        DispatchQueue.main.async {
            switch state {
            case .idle:
                self.connectionStatus = "Idle"
                self.isConnected = false
            case .connecting:
                self.connectionStatus = "Connecting..."
                self.isConnected = false
            case .registered:
                self.connectionStatus = "Connected"
                self.isConnected = true
            case .disconnected(let error):
                self.connectionStatus = error.map { "Failed: \($0.localizedDescription)" } ?? "Disconnected"
                self.isConnected = false
            }
        }
    }
}

// MARK: - H264DecoderDelegate

extension VideoStreamManager: H264DecoderDelegate {
    func decoder(_ decoder: H264Decoder, didDecodeFrame image: UIImage) {
        DispatchQueue.main.async {
            self.currentFrame = image
            self.frameCount += 1
        }
    }

    func decoder(_ decoder: H264Decoder, didFailWithError error: Error) {
        print("[H264Decoder] \(error)")
    }
}

// MARK: - H264Decoder

protocol H264DecoderDelegate: AnyObject {
    func decoder(_ decoder: H264Decoder, didDecodeFrame image: UIImage)
    func decoder(_ decoder: H264Decoder, didFailWithError error: Error)
}

/// Decodes H.264 Annex B bitstream frames (as produced by picamera2 H264Encoder)
/// into UIImages using VideoToolbox.
///
/// Flow:
///   1. Parse Annex B NAL units from incoming Data
///   2. Accumulate SPS (type 7) + PPS (type 8) → CMVideoFormatDescription
///   3. Convert each frame NAL unit: Annex B → AVCC (4-byte big-endian length prefix)
///   4. Decode via VTDecompressionSession → CVImageBuffer → UIImage
class H264Decoder {
    weak var delegate: H264DecoderDelegate?

    private var decompressionSession: VTDecompressionSession?
    private var formatDescription: CMVideoFormatDescription?

    // Accumulate SPS and PPS — required to build CMVideoFormatDescription
    private var spsData: Data?
    private var ppsData: Data?

    // Created once — CIContext is expensive to initialise
    private let ciContext = CIContext()

    private let queue = DispatchQueue(label: "com.wrack.h264decoder", qos: .userInitiated)
    // Drop incoming frames when the decoder is still busy with the previous one
    private var isDecoding = false

    init(delegate: H264DecoderDelegate?) {
        self.delegate = delegate
    }

    func decode(h264Data: Data) {
        guard !isDecoding else { return }   // Live stream: drop stale frames
        isDecoding = true
        queue.async { [weak self] in
            defer { self?.isDecoding = false }
            do {
                try self?.processH264Data(h264Data)
            } catch {
                guard let self else { return }
                self.delegate?.decoder(self, didFailWithError: error)
            }
        }
    }

    // MARK: - Private

    private func processH264Data(_ data: Data) throws {
        for nalUnit in extractNALUnits(from: data) {
            guard !nalUnit.isEmpty else { continue }
            switch nalUnit[0] & 0x1F {
            case 7:  // SPS — Sequence Parameter Set
                spsData = nalUnit
            case 8:  // PPS — Picture Parameter Set
                ppsData = nalUnit
                try rebuildFormatDescription()  // Rebuild whenever we get fresh PPS
            case 5:  // IDR (keyframe)
                try decodeFrame(nalUnit)
            case 1:  // non-IDR
                try decodeFrame(nalUnit)
            default:
                break
            }
        }
    }

    /// Split Annex B stream on 3-byte or 4-byte start codes into raw NAL unit buffers.
    private func extractNALUnits(from data: Data) -> [Data] {
        let bytes = [UInt8](data)
        var starts: [(offset: Int, scLen: Int)] = []
        var i = 0

        while i < bytes.count - 2 {
            if bytes[i] == 0, bytes[i + 1] == 0 {
                if i + 3 < bytes.count, bytes[i + 2] == 0, bytes[i + 3] == 1 {
                    starts.append((i, 4)); i += 4; continue
                } else if bytes[i + 2] == 1 {
                    starts.append((i, 3)); i += 3; continue
                }
            }
            i += 1
        }

        var units: [Data] = []
        for idx in starts.indices {
            let from = starts[idx].offset + starts[idx].scLen
            let to   = idx + 1 < starts.count ? starts[idx + 1].offset : bytes.count
            if from < to { units.append(Data(bytes[from..<to])) }
        }
        return units
    }

    /// Build CMVideoFormatDescription from stored SPS + PPS NAL units.
    private func rebuildFormatDescription() throws {
        guard let sps = spsData, let pps = ppsData else { return }

        let spsBytes = [UInt8](sps)
        let ppsBytes = [UInt8](pps)

        var desc: CMVideoFormatDescription?
        let status = spsBytes.withUnsafeBufferPointer { spsBuf in
            ppsBytes.withUnsafeBufferPointer { ppsBuf in
                let ptrs: [UnsafePointer<UInt8>] = [spsBuf.baseAddress!, ppsBuf.baseAddress!]
                let sizes: [Int] = [sps.count, pps.count]
                return CMVideoFormatDescriptionCreateFromH264ParameterSets(
                    allocator: nil,
                    parameterSetCount: 2,
                    parameterSetPointers: ptrs,
                    parameterSetSizes: sizes,
                    nalUnitHeaderLength: 4,
                    formatDescriptionOut: &desc
                )
            }
        }

        guard status == noErr, let desc else {
            throw NSError(domain: "H264Decoder", code: Int(status),
                          userInfo: [NSLocalizedDescriptionKey: "CMVideoFormatDescriptionCreateFromH264ParameterSets failed"])
        }

        // Format description changed — invalidate old session so it's recreated next frame
        if let old = decompressionSession {
            VTDecompressionSessionInvalidate(old)
            decompressionSession = nil
        }
        formatDescription = desc
    }

    /// Create VTDecompressionSession from current formatDescription.
    private func createDecompressionSession() throws {
        guard let formatDesc = formatDescription else {
            throw NSError(domain: "H264Decoder", code: -1,
                          userInfo: [NSLocalizedDescriptionKey: "No format description yet — waiting for SPS/PPS"])
        }

        let attrs = [kCVPixelBufferPixelFormatTypeKey: kCVPixelFormatType_32BGRA] as CFDictionary
        var session: VTDecompressionSession?
        let status = VTDecompressionSessionCreate(
            allocator: kCFAllocatorDefault,
            formatDescription: formatDesc,
            decoderSpecification: nil,
            imageBufferAttributes: attrs,
            outputCallback: nil,
            decompressionSessionOut: &session
        )

        guard status == noErr, let session else {
            throw NSError(domain: "H264Decoder", code: Int(status),
                          userInfo: [NSLocalizedDescriptionKey: "VTDecompressionSessionCreate failed: \(status)"])
        }
        decompressionSession = session
    }

    /// Convert NAL unit to AVCC format and decode via VTDecompressionSession.
    private func decodeFrame(_ nalUnit: Data) throws {
        guard formatDescription != nil else { return }  // Still waiting for SPS/PPS

        if decompressionSession == nil {
            try createDecompressionSession()
        }
        guard let session = decompressionSession else { return }

        // Annex B → AVCC: replace start code with 4-byte big-endian NAL length
        var avcc = Data(capacity: 4 + nalUnit.count)
        var length = UInt32(nalUnit.count).bigEndian
        avcc.append(contentsOf: withUnsafeBytes(of: &length) { Array($0) })
        avcc.append(nalUnit)

        // Copy into CMBlockBuffer
        var blockBuffer: CMBlockBuffer?
        var status = CMBlockBufferCreateWithMemoryBlock(
            allocator: kCFAllocatorDefault,
            memoryBlock: nil,
            blockLength: avcc.count,
            blockAllocator: nil,
            customBlockSource: nil,
            offsetToData: 0,
            dataLength: avcc.count,
            flags: 0,
            blockBufferOut: &blockBuffer
        )
        guard status == kCMBlockBufferNoErr, let blockBuffer else {
            throw NSError(domain: "H264Decoder", code: Int(status))
        }
        avcc.withUnsafeBytes { ptr in
            _ = CMBlockBufferReplaceDataBytes(
                with: ptr.baseAddress!,
                blockBuffer: blockBuffer,
                offsetIntoDestination: 0,
                dataLength: avcc.count
            )
        }

        // Wrap in CMSampleBuffer
        var sampleBuffer: CMSampleBuffer?
        status = CMSampleBufferCreate(
            allocator: kCFAllocatorDefault,
            dataBuffer: blockBuffer,
            dataReady: true,
            makeDataReadyCallback: nil,
            refcon: nil,
            formatDescription: formatDescription,
            sampleCount: 1,
            sampleTimingEntryCount: 0,
            sampleTimingArray: nil,
            sampleSizeEntryCount: 0,
            sampleSizeArray: nil,
            sampleBufferOut: &sampleBuffer
        )
        guard status == noErr, let sampleBuffer else {
            throw NSError(domain: "H264Decoder", code: Int(status))
        }

        // Decode
        var flags = VTDecodeInfoFlags()
        let decodeStatus = VTDecompressionSessionDecodeFrame(
            session,
            sampleBuffer: sampleBuffer,
            flags: [._EnableAsynchronousDecompression],
            infoFlagsOut: &flags
        ) { [weak self] status, _, imageBuffer, _, _ in
            guard let self, status == noErr, let imageBuffer else { return }
            self.deliverFrame(imageBuffer)
        }

        if decodeStatus != noErr {
            throw NSError(domain: "H264Decoder", code: Int(decodeStatus),
                          userInfo: [NSLocalizedDescriptionKey: "VTDecompressionSessionDecodeFrame failed: \(decodeStatus)"])
        }
    }

    private func deliverFrame(_ imageBuffer: CVImageBuffer) {
        let ciImage = CIImage(cvImageBuffer: imageBuffer)
        guard let cgImage = ciContext.createCGImage(ciImage, from: ciImage.extent) else { return }
        delegate?.decoder(self, didDecodeFrame: UIImage(cgImage: cgImage))
    }

    func invalidate() {
        decompressionSession.map { VTDecompressionSessionInvalidate($0) }
        decompressionSession = nil
        formatDescription = nil
        spsData = nil
        ppsData = nil
    }

    deinit { invalidate() }
}

// MARK: - SwiftUI View

struct VideoStreamView: View {
    @StateObject private var videoManager = VideoStreamManager()

    var body: some View {
        Group {
            if let frame = videoManager.currentFrame {
                Image(uiImage: frame)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .overlay(alignment: .topLeading) {
                        Text("Frames: \(videoManager.frameCount)")
                            .font(.caption)
                            .foregroundColor(.green)
                            .padding(4)
                            .background(Color.black.opacity(0.7))
                            .cornerRadius(4)
                            .padding(8)
                    }
            } else {
                VStack(spacing: 12) {
                    Image(systemName: videoManager.isConnected ? "video.fill" : "video.slash")
                        .font(.system(size: 48))
                        .foregroundColor(videoManager.isConnected ? .blue : .gray)

                    Text(videoManager.connectionStatus)
                        .foregroundColor(.secondary)
                        .font(.caption)

                    if !videoManager.isConnected {
                        Button("Connect to Camera") { videoManager.connect() }
                            .font(.caption)
                    }
                }
            }
        }
        .onAppear  { videoManager.connect() }
        .onDisappear { videoManager.disconnect() }
    }
}
