import Foundation

struct Config {
    static let cloudFunctionURL = "https://europe-central2-wrack-control.cloudfunctions.net/controlRobot"
    static let apiKey = "abc123def456ghi789jkl012mno345pq" // Replace with actual API key
    
    // Robot control constants
    static let defaultTurnSpeed = 300
    static let defaultMoveSpeed = 500
    static let maxSpeed = 2000
    static let speedMultiplier = 20.0 // Convert percentage (-100 to +100) to robot speed (0-2000)
    
    // Turret control constants
    static let defaultTurretSpeed = 200
    static let defaultTurretDuration = 1.0
}
