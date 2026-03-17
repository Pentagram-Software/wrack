import Foundation
import Network

// MARK: - Delegate

/// Implement this protocol to receive decoded video frames and connection events.
public protocol VideoStreamClientDelegate: AnyObject {
    /// A complete H.264 bitstream frame is ready for decoding (e.g. with VideoToolbox).
    func videoStreamClient(_ client: VideoStreamClient, didReceiveH264Frame data: Data)

    /// The client connection state changed.
    func videoStreamClient(_ client: VideoStreamClient, didChangeState state: VideoStreamClient.State)
}

// MARK: - VideoStreamClient

/// UDP client for the wrack video streaming protocol.
///
/// Handles registration, keepalive, chunk reassembly, and connection management.
/// Delivers complete H.264 frames to its delegate on the main queue.
///
/// Usage:
/// ```swift
/// let client = VideoStreamClient(host: "192.168.1.42")
/// client.delegate = self
/// client.connect()
/// ```
///
/// Note: JPEG/pickle mode requires Python deserialization and is not supported here.
/// Use H.264 mode on the Raspberry Pi streamer.
public final class VideoStreamClient {

    // MARK: State

    public enum State: Equatable {
        case idle
        case connecting
        case registered
        case disconnected(Error?)

        public static func == (lhs: State, rhs: State) -> Bool {
            switch (lhs, rhs) {
            case (.idle, .idle), (.connecting, .connecting),
                 (.registered, .registered), (.disconnected, .disconnected):
                return true
            default:
                return false
            }
        }
    }

    // MARK: Public

    public weak var delegate: VideoStreamClientDelegate?
    public private(set) var state: State = .idle

    // MARK: Private

    private let host: NWEndpoint.Host
    private let port: NWEndpoint.Port
    private var connection: NWConnection?
    private var keepaliveTimer: Timer?
    private let assembler = FrameAssembler()
    private let queue = DispatchQueue(label: "com.wrack.videostream", qos: .userInteractive)

    // MARK: Init

    public init(host: String, port: UInt16 = VideoProtocol.serverPort) {
        self.host = NWEndpoint.Host(host)
        self.port = NWEndpoint.Port(rawValue: port) ?? NWEndpoint.Port(rawValue: 9999)!
    }

    // MARK: Public API

    public func connect() {
        guard state == .idle || state == .disconnected(nil) else { return }
        let params = NWParameters.udp
        params.allowLocalEndpointReuse = true
        let conn = NWConnection(host: host, port: port, using: params)
        conn.stateUpdateHandler = { [weak self] in self?.handleConnectionState($0) }
        conn.start(queue: queue)
        connection = conn
    }

    public func disconnect() {
        keepaliveTimer?.invalidate()
        keepaliveTimer = nil
        connection?.send(content: VideoProtocol.disconnect, completion: .idempotent)
        connection?.cancel()
        setState(.disconnected(nil))
    }

    // MARK: - Private

    private func handleConnectionState(_ newState: NWConnection.State) {
        switch newState {
        case .ready:
            sendRegistration()
        case .failed(let error):
            setState(.disconnected(error))
        case .cancelled:
            setState(.disconnected(nil))
        default:
            break
        }
    }

    private func sendRegistration() {
        setState(.connecting)
        connection?.send(content: VideoProtocol.registerClient, completion: .contentProcessed { [weak self] error in
            guard error == nil else { return }
            self?.receiveNextPacket()
        })
    }

    private func receiveNextPacket() {
        connection?.receiveMessage { [weak self] data, _, _, error in
            guard let self, error == nil, let data else { return }
            self.handlePacket(data)
            self.receiveNextPacket()
        }
    }

    private func handlePacket(_ data: Data) {
        if data == VideoProtocol.registered {
            setState(.registered)
            scheduleKeepalive()
            return
        }

        if let packet = FrameStartPacket.parse(from: data) {
            assembler.handleFrameStart(packet)
            assembler.pruneStale()
            return
        }

        if let packet = ChunkPacket.parse(from: data),
           let frame = assembler.handleChunk(packet) {
            notifyFrame(frame)
        }
    }

    private func notifyFrame(_ frame: Data) {
        let client = self
        DispatchQueue.main.async {
            client.delegate?.videoStreamClient(client, didReceiveH264Frame: frame)
        }
    }

    private func scheduleKeepalive() {
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            self.keepaliveTimer = Timer.scheduledTimer(
                withTimeInterval: VideoProtocol.keepaliveInterval,
                repeats: true
            ) { [weak self] _ in
                self?.sendKeepalive()
            }
        }
    }

    private func sendKeepalive() {
        queue.async { [weak self] in
            self?.connection?.send(content: VideoProtocol.keepalive, completion: .idempotent)
        }
    }

    private func setState(_ newState: State) {
        state = newState
        let client = self
        DispatchQueue.main.async {
            client.delegate?.videoStreamClient(client, didChangeState: newState)
        }
    }
}
