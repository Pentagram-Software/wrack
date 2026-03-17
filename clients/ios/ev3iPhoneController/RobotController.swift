import Foundation

struct RobotCommand: Codable {
    let command: String
    let params: [String: Any]
    
    enum CodingKeys: String, CodingKey {
        case command, params
    }
    
    init(command: String, params: [String: Any] = [:]) {
        self.command = command
        self.params = params
    }
    
    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(command, forKey: .command)
        
        var paramsContainer = container.nestedContainer(keyedBy: DynamicCodingKeys.self, forKey: .params)
        for (key, value) in params {
            let codingKey = DynamicCodingKeys(stringValue: key)!
            if let intValue = value as? Int {
                try paramsContainer.encode(intValue, forKey: codingKey)
            } else if let doubleValue = value as? Double {
                try paramsContainer.encode(doubleValue, forKey: codingKey)
            } else if let stringValue = value as? String {
                try paramsContainer.encode(stringValue, forKey: codingKey)
            }
        }
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        command = try container.decode(String.self, forKey: .command)
        params = [:]
    }
}

struct DynamicCodingKeys: CodingKey {
    var stringValue: String
    var intValue: Int?
    
    init?(stringValue: String) {
        self.stringValue = stringValue
        self.intValue = nil
    }
    
    init?(intValue: Int) {
        self.stringValue = String(intValue)
        self.intValue = intValue
    }
}

struct RobotResponse: Codable {
    let success: Bool?
    let message: String?
    let error: String?
}

@MainActor
class RobotController: ObservableObject {
    private let baseURL = Config.cloudFunctionURL
    private let apiKey = Config.apiKey
    
    @Published var connectionStatus: String = "disconnected"
    @Published var lastError: String?
    
    private var session: URLSession
    
    init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 10.0
        config.timeoutIntervalForResource = 30.0
        self.session = URLSession(configuration: config)
    }
    
    private func sendCommand(_ command: RobotCommand) async throws -> RobotResponse {
        guard let url = URL(string: baseURL) else {
            throw RobotError.invalidURL
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
        
        do {
            let jsonData = try JSONEncoder().encode(command)
            request.httpBody = jsonData
            
            let (data, response) = try await session.data(for: request)
            
            guard let httpResponse = response as? HTTPURLResponse else {
                throw RobotError.invalidResponse
            }
            
            if httpResponse.statusCode == 200 {
                self.connectionStatus = "connected"
                self.lastError = nil
            } else {
                self.connectionStatus = "error"
                throw RobotError.httpError(httpResponse.statusCode)
            }
            
            let robotResponse = try JSONDecoder().decode(RobotResponse.self, from: data)
            return robotResponse
            
        } catch {
            self.connectionStatus = "disconnected"
            self.lastError = error.localizedDescription
            throw error
        }
    }
    
    func moveForward(speed: Int = 500, duration: Double = 0) async throws {
        let command = RobotCommand(command: "forward", params: ["speed": speed, "duration": duration])
        _ = try await sendCommand(command)
    }
    
    func moveBackward(speed: Int = 500, duration: Double = 0) async throws {
        let command = RobotCommand(command: "backward", params: ["speed": speed, "duration": duration])
        _ = try await sendCommand(command)
    }
    
    func turnLeft(speed: Int = 300, duration: Double = 0) async throws {
        let command = RobotCommand(command: "left", params: ["speed": speed, "duration": duration])
        _ = try await sendCommand(command)
    }
    
    func turnRight(speed: Int = 300, duration: Double = 0) async throws {
        let command = RobotCommand(command: "right", params: ["speed": speed, "duration": duration])
        _ = try await sendCommand(command)
    }
    
    func stop() async throws {
        let command = RobotCommand(command: "stop")
        _ = try await sendCommand(command)
    }
    
    func turretLeft(speed: Int = 200, duration: Double = 1.0) async throws {
        let command = RobotCommand(command: "turret_left", params: ["speed": speed, "duration": duration])
        _ = try await sendCommand(command)
    }
    
    func turretRight(speed: Int = 200, duration: Double = 1.0) async throws {
        let command = RobotCommand(command: "turret_right", params: ["speed": speed, "duration": duration])
        _ = try await sendCommand(command)
    }
    
    func stopTurret() async throws {
        let command = RobotCommand(command: "stop_turret")
        _ = try await sendCommand(command)
    }
    
    func joystickControl(leftMotor: Int, rightMotor: Int) async throws {
        let command = RobotCommand(command: "joystick_control", params: [
            "l_left": 0,
            "l_forward": leftMotor,
            "r_left": 0,
            "r_forward": rightMotor
        ])
        _ = try await sendCommand(command)
    }
    
    func getStatus() async throws -> RobotResponse {
        let command = RobotCommand(command: "get_status")
        return try await sendCommand(command)
    }
}

enum RobotError: Error, LocalizedError {
    case invalidURL
    case invalidResponse
    case httpError(Int)
    case networkError(String)
    
    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid URL"
        case .invalidResponse:
            return "Invalid response"
        case .httpError(let code):
            return "HTTP Error: \(code)"
        case .networkError(let message):
            return "Network Error: \(message)"
        }
    }
}