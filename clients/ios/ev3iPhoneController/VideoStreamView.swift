import SwiftUI
import Network
import AVFoundation

class VideoStreamManager: ObservableObject {
    @Published var isConnected = false
    @Published var currentFrame: UIImage?
    @Published var frameCount: Int = 0
    @Published var connectionStatus: String = "Disconnected"
    
    private var udpConnection: NWConnection?
    private var serverEndpoint: NWEndpoint
    private let listenPort: UInt16 = 9999
    
    private var pendingFrames: [UInt32: NSMutableData] = [:]
    private var expectedChunks: [UInt32: UInt32] = [:]
    private var receivedChunks: [UInt32: Set<UInt32>] = [:]
    private let payloadSize: UInt32 = 1200
    
    private var keepAliveTimer: Timer?
    
    init(host: String = "192.168.1.216", port: UInt16 = 9999) {
        self.serverEndpoint = NWEndpoint.hostPort(host: NWEndpoint.Host(host), port: NWEndpoint.Port(rawValue: port)!)
    }
    
    func connect() {
        guard udpConnection == nil else { return }
        
        DispatchQueue.main.async {
            self.connectionStatus = "Connecting to server..."
        }
        
        // Create UDP connection to server
        udpConnection = NWConnection(to: serverEndpoint, using: .udp)
        
        udpConnection?.stateUpdateHandler = { [weak self] state in
            DispatchQueue.main.async {
                switch state {
                case .ready:
                    self?.connectionStatus = "Connected to server"
                    self?.isConnected = true
                    self?.registerWithServer()
                    self?.startReceiving()
                    self?.startKeepAlive()
                case .failed(let error):
                    self?.connectionStatus = "Failed: \(error.localizedDescription)"
                    self?.isConnected = false
                case .cancelled:
                    self?.connectionStatus = "Disconnected"
                    self?.isConnected = false
                default:
                    break
                }
            }
        }
        
        udpConnection?.start(queue: .global(qos: .userInitiated))
    }
    
    func disconnect() {
        keepAliveTimer?.invalidate()
        keepAliveTimer = nil
        
        sendDisconnect()
        
        udpConnection?.cancel()
        udpConnection = nil
        
        DispatchQueue.main.async {
            self.isConnected = false
            self.connectionStatus = "Disconnected"
            self.currentFrame = nil
        }
    }
    
    private func registerWithServer() {
        let registerMessage = "REGISTER_CLIENT".data(using: .utf8)!
        udpConnection?.send(content: registerMessage, completion: .contentProcessed({ _ in }))
    }
    
    private func sendDisconnect() {
        let disconnectMessage = "DISCONNECT".data(using: .utf8)!
        udpConnection?.send(content: disconnectMessage, completion: .contentProcessed({ _ in }))
    }
    
    private func startKeepAlive() {
        keepAliveTimer = Timer.scheduledTimer(withTimeInterval: 5.0, repeats: true) { [weak self] _ in
            let keepAliveMessage = "KEEPALIVE".data(using: .utf8)!
            self?.udpConnection?.send(content: keepAliveMessage, completion: .contentProcessed({ _ in }))
        }
    }
    
    private func startReceiving() {
        receiveMessage()
    }
    
    private func receiveMessage() {
        udpConnection?.receiveMessage { [weak self] (data, _, isComplete, error) in
            if let data = data, !data.isEmpty {
                self?.processReceivedData(data)
            }
            
            if error == nil {
                self?.receiveMessage()
            }
        }
    }
    
    private func processReceivedData(_ data: Data) {
        if data.starts(with: "REGISTERED".data(using: .utf8)!) {
            return
        }
        
        if data.starts(with: "FRAME_START".data(using: .utf8)!) {
            processFrameStart(data)
        } else if data.starts(with: "CHUNK".data(using: .utf8)!) {
            processChunk(data)
        }
    }
    
    private func processFrameStart(_ data: Data) {
        let headerLength = "FRAME_START".count
        
        // Try 64-bit L format first (Pi format: 11 + 8 + 8 + 8 = 35 bytes)
        if data.count >= headerLength + 24 {
            let headerData = data.subdata(in: headerLength..<(headerLength + 24))
            let frameId = headerData.withUnsafeBytes { $0.bindMemory(to: UInt64.self)[0] }
            let frameSize = headerData.withUnsafeBytes { $0.bindMemory(to: UInt64.self)[1] }
            let chunkCount = headerData.withUnsafeBytes { $0.bindMemory(to: UInt64.self)[2] }
            
            
            if frameSize > 0 && frameSize < 10000000 { // Sanity check
                pendingFrames[UInt32(frameId)] = NSMutableData(length: Int(frameSize))
                expectedChunks[UInt32(frameId)] = UInt32(chunkCount)
                receivedChunks[UInt32(frameId)] = Set<UInt32>()
                return
            }
        }
        
        // Try 32-bit I format (fallback: 11 + 4 + 4 + 4 = 23 bytes)
        if data.count >= headerLength + 12 {
            let headerData = data.subdata(in: headerLength..<(headerLength + 12))
            let frameId = headerData.withUnsafeBytes { $0.bindMemory(to: UInt32.self)[0] }
            let frameSize = headerData.withUnsafeBytes { $0.bindMemory(to: UInt32.self)[1] }
            let chunkCount = headerData.withUnsafeBytes { $0.bindMemory(to: UInt32.self)[2] }
            
            
            if frameSize > 0 && frameSize < 10000000 { // Sanity check
                pendingFrames[frameId] = NSMutableData(length: Int(frameSize))
                expectedChunks[frameId] = chunkCount
                receivedChunks[frameId] = Set<UInt32>()
                return
            }
        }
        
    }
    
    private func processChunk(_ data: Data) {
        let headerLength = "CHUNK".count
        
        // Try 64-bit format first (5 + 8 + 8 = 21 bytes header)
        if data.count >= headerLength + 16 {
            let headerData = data.subdata(in: headerLength..<(headerLength + 16))
            let frameId = UInt32(headerData.withUnsafeBytes { $0.bindMemory(to: UInt64.self)[0] })
            let chunkIndex = UInt32(headerData.withUnsafeBytes { $0.bindMemory(to: UInt64.self)[1] })
            let payload = data.subdata(in: (headerLength + 16)..<data.count)
            
            if processChunkData(frameId: frameId, chunkIndex: chunkIndex, payload: payload) {
                return
            }
        }
        
        // Try 32-bit format (5 + 4 + 4 = 13 bytes header)
        if data.count >= headerLength + 8 {
            let headerData = data.subdata(in: headerLength..<(headerLength + 8))
            let frameId = headerData.withUnsafeBytes { $0.bindMemory(to: UInt32.self)[0] }
            let chunkIndex = headerData.withUnsafeBytes { $0.bindMemory(to: UInt32.self)[1] }
            let payload = data.subdata(in: (headerLength + 8)..<data.count)
            
            processChunkData(frameId: frameId, chunkIndex: chunkIndex, payload: payload)
        }
    }
    
    private func processChunkData(frameId: UInt32, chunkIndex: UInt32, payload: Data) -> Bool {
        guard let frameBuffer = pendingFrames[frameId],
              var receivedSet = receivedChunks[frameId] else { 
            return false
        }
        
        if !receivedSet.contains(chunkIndex) {
            let offset = Int(chunkIndex * payloadSize)
            let endOffset = min(offset + payload.count, frameBuffer.length)
            
            if offset < frameBuffer.length {
                frameBuffer.replaceBytes(in: NSRange(location: offset, length: endOffset - offset), 
                                       withBytes: payload.withUnsafeBytes { $0.bindMemory(to: UInt8.self).baseAddress }, 
                                       length: endOffset - offset)
                receivedSet.insert(chunkIndex)
                receivedChunks[frameId] = receivedSet
                
                
                if let expectedCount = expectedChunks[frameId], receivedSet.count >= expectedCount {
                    let frameData = Data(bytes: frameBuffer.bytes, count: frameBuffer.length)
                    processCompleteFrame(frameData)
                    
                    pendingFrames.removeValue(forKey: frameId)
                    expectedChunks.removeValue(forKey: frameId)
                    receivedChunks.removeValue(forKey: frameId)
                }
                return true
            }
        }
        return false
    }
    
    private func processCompleteFrame(_ frameData: Data) {
        // Try direct JPEG decode first
        if let image = UIImage(data: frameData) {
            DispatchQueue.main.async {
                self.currentFrame = image
                self.frameCount += 1
            }
            return
        }
        
        // Try to find JPEG markers within the data
        if let jpegStart = findJPEGData(in: frameData) {
            if let image = UIImage(data: jpegStart.data) {
                DispatchQueue.main.async {
                    self.currentFrame = image
                    self.frameCount += 1
                }
            }
        }
    }
    
    private func findJPEGData(in data: Data) -> (offset: Int, data: Data)? {
        // JPEG starts with 0xFF 0xD8 and ends with 0xFF 0xD9
        let jpegStart: [UInt8] = [0xFF, 0xD8]
        let jpegEnd: [UInt8] = [0xFF, 0xD9]
        
        guard let startIndex = data.range(of: Data(jpegStart))?.lowerBound else {
            return nil
        }
        
        guard let endRange = data.range(of: Data(jpegEnd), in: startIndex..<data.endIndex) else {
            return nil
        }
        
        let jpegData = data[startIndex..<endRange.upperBound]
        return (offset: data.distance(from: data.startIndex, to: startIndex), data: jpegData)
    }
}

struct VideoStreamView: View {
    @StateObject private var videoManager = VideoStreamManager()
    
    var body: some View {
        Group {
            if let frame = videoManager.currentFrame {
                Image(uiImage: frame)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .overlay(
                        VStack {
                            HStack {
                                VStack(alignment: .leading) {
                                    Text("Frames: \(videoManager.frameCount)")
                                        .font(.caption)
                                        .foregroundColor(.green)
                                        .padding(4)
                                        .background(Color.black.opacity(0.7))
                                        .cornerRadius(4)
                                }
                                Spacer()
                            }
                            Spacer()
                        }
                        .padding(8)
                    )
            } else {
                VStack {
                    Circle()
                        .fill(videoManager.isConnected ? Color.blue.opacity(0.3) : Color.gray.opacity(0.5))
                        .frame(width: 64, height: 64)
                        .overlay(
                            Image(systemName: videoManager.isConnected ? "video.fill" : "plus")
                                .foregroundColor(videoManager.isConnected ? .blue : .gray)
                                .font(.title)
                        )
                    
                    Text(videoManager.isConnected ? "Connecting to camera..." : "Camera Feed")
                        .foregroundColor(.gray)
                        .font(.caption)
                    
                    Text(videoManager.connectionStatus)
                        .foregroundColor(videoManager.isConnected ? .green : .gray)
                        .font(.caption2)
                    
                    if !videoManager.isConnected {
                        Button("Connect to Camera") {
                            videoManager.connect()
                        }
                        .padding(.top, 8)
                        .font(.caption)
                        .foregroundColor(.blue)
                    }
                }
            }
        }
        .onAppear {
            videoManager.connect()
        }
        .onDisappear {
            videoManager.disconnect()
        }
    }
}