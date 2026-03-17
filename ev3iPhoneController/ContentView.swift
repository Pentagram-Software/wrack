import SwiftUI

struct ContentView: View {
    @StateObject private var robotController = RobotController()
    @State private var turretRotation: Double = 0
    @State private var activeDirection: String? = nil
    @State private var isMoving: Bool = false
    @State private var currentSpeed: Int = 0
    @State private var lastTurretDirection: String = ""
    
    private let defaultMoveSpeed: Int = 500
    
    
    var body: some View {
        GeometryReader { geometry in
            let isLandscape = geometry.size.width > geometry.size.height
            
            VStack(spacing: 0) {
                // Status Bar
                statusBar
                
                if isLandscape {
                    // Landscape Layout - Horizontal
                    HStack(spacing: 8) {
                        // Left Side - Turret Controls
                        leftControls
                            .frame(width: geometry.size.width * 0.25)
                        
                        // Center - Camera Feed
                        cameraFeed
                            .frame(maxWidth: 1000)
                        
                        // Right Side - Vehicle Movement Controls
                        rightControls
                            .frame(width: geometry.size.width * 0.25)
                    }
                    .padding(EdgeInsets(top: 0, leading: 8, bottom: 8, trailing: 8))
                    
                    // Vehicle Status at bottom
                    vehicleStatus
                } else {
                    // Portrait Layout - Vertical (Original)
                    VStack(spacing: 0) {
                        // Camera Feed
                        cameraFeedPortrait
                        
                        // Vehicle Status
                        vehicleStatus
                        
                        // Controls Section
                        controlsSectionPortrait
                    }
                }
            }
        }
        .background(Color.black)
        .preferredColorScheme(.dark)
    }
    
    // MARK: - Status Bar
    var statusBar: some View {
        HStack {
            HStack(spacing: 8) {
                Button(action: showSettings) {
                    Image(systemName: "gearshape.fill")
                        .foregroundColor(.white)
                        .frame(width: 32, height: 32)
                        .background(Color.gray.opacity(0.3))
                        .cornerRadius(8)
                }
                
                Image(systemName: "antenna.radiowaves.left.and.right")
                    .foregroundColor(.white)
                Image(systemName: "wifi")
                    .foregroundColor(.white)
                Circle()
                    .fill(connectionStatusColor)
                    .frame(width: 8, height: 8)
            }
            
            Spacer()
            
            HStack(spacing: 8) {
                Image(systemName: "battery.100")
                    .foregroundColor(.white)
                Text("87%")
                    .foregroundColor(.white)
                    .font(.caption)
            }
        }
        .padding(EdgeInsets(top: 8, leading: 8, bottom: 8, trailing: 8))
        .background(Color.gray.opacity(0.2))
    }
    
    // MARK: - Camera Feed (Portrait)
    var cameraFeedPortrait: some View {
        VideoStreamView()
            .frame(maxWidth: 1000, maxHeight: 1000)
            .background(Color.gray.opacity(0.3))
            .cornerRadius(8)
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(Color.gray.opacity(0.5), lineWidth: 2)
            )
            .padding(EdgeInsets(top: 0, leading: 8, bottom: 0, trailing: 8))
    }
    
    // MARK: - Camera Feed (Landscape)
    var cameraFeed: some View {
        VideoStreamView()
            .frame(maxWidth: 1000, maxHeight: 1000)
            .background(Color.gray.opacity(0.3))
            .cornerRadius(8)
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(Color.gray.opacity(0.5), lineWidth: 2)
            )
    }
    
    // MARK: - Vehicle Status
    var vehicleStatus: some View {
        HStack {
            VStack {
                Text("Speed")
                    .foregroundColor(.gray)
                    .font(.caption)
                Text(speedText)
                    .foregroundColor(speedColor)
                    .font(.title2)
                    .fontWeight(.bold)
            }
            
            Spacer()
            
            VStack {
                Text("Direction")
                    .foregroundColor(.gray)
                    .font(.caption)
                Text(directionText)
                    .foregroundColor(.orange)
                    .font(.caption)
            }
            
            Spacer()
            
            VStack {
                Text("Turret")
                    .foregroundColor(.gray)
                    .font(.caption)
                Text("\(Int(turretRotation))°")
                    .foregroundColor(.blue)
                    .font(.caption)
            }
            
            Spacer()
            
            VStack {
                Text("Status")
                    .foregroundColor(.gray)
                    .font(.caption)
                Text(robotController.connectionStatus.capitalized)
                    .foregroundColor(connectionStatusColor)
                    .font(.caption)
            }
        }
        .padding(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
        .background(Color.gray.opacity(0.2))
        .cornerRadius(8)
        .padding(EdgeInsets(top: 0, leading: 8, bottom: 8, trailing: 8))
    }
    
    // MARK: - Left Controls (Turret)
    var leftControls: some View {
        VStack(spacing: 12) {
            Text("Turret Control")
                .foregroundColor(.gray)
                .font(.caption)
                .fontWeight(.semibold)
            
            // Turret Controls
            VStack(spacing: 8) {
                Text("Rotation")
                    .foregroundColor(.gray)
                    .font(.caption2)
                
                HStack(spacing: 8) {
                    Button(action: {}) {
                        Image(systemName: "arrow.counterclockwise")
                            .foregroundColor(.white)
                            .font(.title2)
                            .frame(width: 60, height: 60)
                            .background(activeDirection == "turret_left" ? Color.orange : Color.gray.opacity(0.3))
                            .cornerRadius(8)
                            .overlay(
                                RoundedRectangle(cornerRadius: 8)
                                    .stroke(activeDirection == "turret_left" ? Color.orange.opacity(0.7) : Color.gray.opacity(0.5), lineWidth: 2)
                            )
                    }
                    .scaleEffect(activeDirection == "turret_left" ? 0.95 : 1.0)
                    .onLongPressGesture(minimumDuration: 0, maximumDistance: 50, pressing: { pressing in
                        withAnimation(.easeInOut(duration: 0.1)) {
                            activeDirection = pressing ? "turret_left" : nil
                        }
                        Task {
                            await handleTurretControl(direction: "left", isPressed: pressing)
                        }
                    }, perform: {})
                    
                    Button(action: {}) {
                        Image(systemName: "arrow.clockwise")
                            .foregroundColor(.white)
                            .font(.title2)
                            .frame(width: 60, height: 60)
                            .background(activeDirection == "turret_right" ? Color.orange : Color.gray.opacity(0.3))
                            .cornerRadius(8)
                            .overlay(
                                RoundedRectangle(cornerRadius: 8)
                                    .stroke(activeDirection == "turret_right" ? Color.orange.opacity(0.7) : Color.gray.opacity(0.5), lineWidth: 2)
                            )
                    }
                    .scaleEffect(activeDirection == "turret_right" ? 0.95 : 1.0)
                    .onLongPressGesture(minimumDuration: 0, maximumDistance: 50, pressing: { pressing in
                        withAnimation(.easeInOut(duration: 0.1)) {
                            activeDirection = pressing ? "turret_right" : nil
                        }
                        Task {
                            await handleTurretControl(direction: "right", isPressed: pressing)
                        }
                    }, perform: {})
                }
            }
            
            Spacer()
        }
        .padding(EdgeInsets(top: 8, leading: 0, bottom: 8, trailing: 0))
    }
    
    // MARK: - Right Controls (Vehicle Movement)
    var rightControls: some View {
        VStack(spacing: 12) {
            Text("Vehicle Control")
                .foregroundColor(.gray)
                .font(.caption)
                .fontWeight(.semibold)
            
            // Arrow Key Layout for Movement
            VStack(spacing: 8) {
                // Top row - Forward button
                Button(action: {}) {
                    Image(systemName: "chevron.up")
                        .foregroundColor(.white)
                        .font(.title2)
                        .frame(width: 60, height: 60)
                        .background(activeDirection == "forward" ? Color.green : Color.gray.opacity(0.3))
                        .cornerRadius(8)
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(activeDirection == "forward" ? Color.green.opacity(0.7) : Color.gray.opacity(0.5), lineWidth: 2)
                        )
                }
                .scaleEffect(activeDirection == "forward" ? 0.95 : 1.0)
                .onLongPressGesture(minimumDuration: 0, maximumDistance: 50, pressing: { pressing in
                    withAnimation(.easeInOut(duration: 0.1)) {
                        activeDirection = pressing ? "forward" : nil
                    }
                    Task {
                        await handleForwardBackward(direction: "forward", isPressed: pressing)
                    }
                }, perform: {})
                
                // Middle row - Left and Right buttons
                HStack(spacing: 8) {
                    Button(action: {}) {
                        Image(systemName: "chevron.left")
                            .foregroundColor(.white)
                            .font(.title2)
                            .frame(width: 60, height: 60)
                            .background(activeDirection == "left" ? Color.blue : Color.gray.opacity(0.3))
                            .cornerRadius(8)
                            .overlay(
                                RoundedRectangle(cornerRadius: 8)
                                    .stroke(activeDirection == "left" ? Color.blue.opacity(0.7) : Color.gray.opacity(0.5), lineWidth: 2)
                            )
                    }
                    .scaleEffect(activeDirection == "left" ? 0.95 : 1.0)
                    .onLongPressGesture(minimumDuration: 0, maximumDistance: 50, pressing: { pressing in
                        withAnimation(.easeInOut(duration: 0.1)) {
                            activeDirection = pressing ? "left" : nil
                        }
                        Task {
                            await handleVehicleControl(direction: "left", isPressed: pressing)
                        }
                    }, perform: {})
                    
                    Button(action: {}) {
                        Image(systemName: "chevron.right")
                            .foregroundColor(.white)
                            .font(.title2)
                            .frame(width: 60, height: 60)
                            .background(activeDirection == "right" ? Color.blue : Color.gray.opacity(0.3))
                            .cornerRadius(8)
                            .overlay(
                                RoundedRectangle(cornerRadius: 8)
                                    .stroke(activeDirection == "right" ? Color.blue.opacity(0.7) : Color.gray.opacity(0.5), lineWidth: 2)
                            )
                    }
                    .scaleEffect(activeDirection == "right" ? 0.95 : 1.0)
                    .onLongPressGesture(minimumDuration: 0, maximumDistance: 50, pressing: { pressing in
                        withAnimation(.easeInOut(duration: 0.1)) {
                            activeDirection = pressing ? "right" : nil
                        }
                        Task {
                            await handleVehicleControl(direction: "right", isPressed: pressing)
                        }
                    }, perform: {})
                }
                
                // Bottom row - Backward button
                Button(action: {}) {
                    Image(systemName: "chevron.down")
                        .foregroundColor(.white)
                        .font(.title2)
                        .frame(width: 60, height: 60)
                        .background(activeDirection == "backward" ? Color.red : Color.gray.opacity(0.3))
                        .cornerRadius(8)
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(activeDirection == "backward" ? Color.red.opacity(0.7) : Color.gray.opacity(0.5), lineWidth: 2)
                        )
                }
                .scaleEffect(activeDirection == "backward" ? 0.95 : 1.0)
                .onLongPressGesture(minimumDuration: 0, maximumDistance: 50, pressing: { pressing in
                    withAnimation(.easeInOut(duration: 0.1)) {
                        activeDirection = pressing ? "backward" : nil
                    }
                    Task {
                        await handleForwardBackward(direction: "backward", isPressed: pressing)
                    }
                }, perform: {})
            }
            
            Spacer()
        }
        .padding(EdgeInsets(top: 8, leading: 0, bottom: 8, trailing: 0))
    }
    
    // MARK: - Controls Section (Portrait)
    var controlsSectionPortrait: some View {
        HStack(spacing: 16) {
            // Left Side - Turret Controls
            VStack {
                Text("Turret Control")
                    .foregroundColor(.gray)
                    .font(.caption)
                    .fontWeight(.semibold)
                    .padding(.bottom, 16)
                
                // Turret Controls
                HStack(spacing: 16) {
                    Button(action: {}) {
                        Image(systemName: "arrow.counterclockwise")
                            .foregroundColor(.white)
                            .font(.title2)
                            .frame(width: 80, height: 80)
                            .background(activeDirection == "turret_left" ? Color.orange : Color.gray.opacity(0.3))
                            .cornerRadius(8)
                            .overlay(
                                RoundedRectangle(cornerRadius: 8)
                                    .stroke(activeDirection == "turret_left" ? Color.orange.opacity(0.7) : Color.gray.opacity(0.5), lineWidth: 2)
                            )
                    }
                    .scaleEffect(activeDirection == "turret_left" ? 0.95 : 1.0)
                    .onLongPressGesture(minimumDuration: 0, maximumDistance: 50, pressing: { pressing in
                        withAnimation(.easeInOut(duration: 0.1)) {
                            activeDirection = pressing ? "turret_left" : nil
                        }
                        Task {
                            await handleTurretControl(direction: "left", isPressed: pressing)
                        }
                    }, perform: {})
                    
                    Button(action: {}) {
                        Image(systemName: "arrow.clockwise")
                            .foregroundColor(.white)
                            .font(.title2)
                            .frame(width: 80, height: 80)
                            .background(activeDirection == "turret_right" ? Color.orange : Color.gray.opacity(0.3))
                            .cornerRadius(8)
                            .overlay(
                                RoundedRectangle(cornerRadius: 8)
                                    .stroke(activeDirection == "turret_right" ? Color.orange.opacity(0.7) : Color.gray.opacity(0.5), lineWidth: 2)
                            )
                    }
                    .scaleEffect(activeDirection == "turret_right" ? 0.95 : 1.0)
                    .onLongPressGesture(minimumDuration: 0, maximumDistance: 50, pressing: { pressing in
                        withAnimation(.easeInOut(duration: 0.1)) {
                            activeDirection = pressing ? "turret_right" : nil
                        }
                        Task {
                            await handleTurretControl(direction: "right", isPressed: pressing)
                        }
                    }, perform: {})
                }
            }
            
            // Right Side - Vehicle Movement Controls
            VStack {
                Text("Vehicle Control")
                    .foregroundColor(.gray)
                    .font(.caption)
                    .fontWeight(.semibold)
                    .padding(.bottom, 16)
                
                // Arrow Key Layout for Movement
                VStack(spacing: 12) {
                    // Top row - Forward button
                    Button(action: {}) {
                        VStack(spacing: 4) {
                            Image(systemName: "chevron.up")
                                .foregroundColor(.white)
                                .font(.title2)
                            Text("FWD")
                                .foregroundColor(.white)
                                .font(.caption2)
                                .fontWeight(.semibold)
                        }
                        .frame(width: 80, height: 60)
                        .background(activeDirection == "forward" ? Color.green : Color.gray.opacity(0.3))
                        .cornerRadius(8)
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(activeDirection == "forward" ? Color.green.opacity(0.7) : Color.gray.opacity(0.5), lineWidth: 2)
                        )
                    }
                    .scaleEffect(activeDirection == "forward" ? 0.95 : 1.0)
                    .onLongPressGesture(minimumDuration: 0, maximumDistance: 50, pressing: { pressing in
                        withAnimation(.easeInOut(duration: 0.1)) {
                            activeDirection = pressing ? "forward" : nil
                        }
                        Task {
                            await handleForwardBackward(direction: "forward", isPressed: pressing)
                        }
                    }, perform: {})
                    
                    // Middle row - Left and Right buttons
                    HStack(spacing: 12) {
                        Button(action: {}) {
                            Image(systemName: "chevron.left")
                                .foregroundColor(.white)
                                .font(.title2)
                                .frame(width: 60, height: 60)
                                .background(activeDirection == "left" ? Color.blue : Color.gray.opacity(0.3))
                                .cornerRadius(8)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 8)
                                        .stroke(activeDirection == "left" ? Color.blue.opacity(0.7) : Color.gray.opacity(0.5), lineWidth: 2)
                                )
                        }
                        .scaleEffect(activeDirection == "left" ? 0.95 : 1.0)
                        .onLongPressGesture(minimumDuration: 0, maximumDistance: 50, pressing: { pressing in
                            withAnimation(.easeInOut(duration: 0.1)) {
                                activeDirection = pressing ? "left" : nil
                            }
                            Task {
                                await handleVehicleControl(direction: "left", isPressed: pressing)
                            }
                        }, perform: {})
                        
                        Button(action: {}) {
                            Image(systemName: "chevron.right")
                                .foregroundColor(.white)
                                .font(.title2)
                                .frame(width: 60, height: 60)
                                .background(activeDirection == "right" ? Color.blue : Color.gray.opacity(0.3))
                                .cornerRadius(8)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 8)
                                        .stroke(activeDirection == "right" ? Color.blue.opacity(0.7) : Color.gray.opacity(0.5), lineWidth: 2)
                                )
                        }
                        .scaleEffect(activeDirection == "right" ? 0.95 : 1.0)
                        .onLongPressGesture(minimumDuration: 0, maximumDistance: 50, pressing: { pressing in
                            withAnimation(.easeInOut(duration: 0.1)) {
                                activeDirection = pressing ? "right" : nil
                            }
                            Task {
                                await handleVehicleControl(direction: "right", isPressed: pressing)
                            }
                        }, perform: {})
                    }
                    
                    // Bottom row - Backward button
                    Button(action: {}) {
                        VStack(spacing: 4) {
                            Image(systemName: "chevron.down")
                                .foregroundColor(.white)
                                .font(.title2)
                            Text("REV")
                                .foregroundColor(.white)
                                .font(.caption2)
                                .fontWeight(.semibold)
                        }
                        .frame(width: 80, height: 60)
                        .background(activeDirection == "backward" ? Color.red : Color.gray.opacity(0.3))
                        .cornerRadius(8)
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(activeDirection == "backward" ? Color.red.opacity(0.7) : Color.gray.opacity(0.5), lineWidth: 2)
                        )
                    }
                    .scaleEffect(activeDirection == "backward" ? 0.95 : 1.0)
                    .onLongPressGesture(minimumDuration: 0, maximumDistance: 50, pressing: { pressing in
                        withAnimation(.easeInOut(duration: 0.1)) {
                            activeDirection = pressing ? "backward" : nil
                        }
                        Task {
                            await handleForwardBackward(direction: "backward", isPressed: pressing)
                        }
                    }, perform: {})
                }
            }
        }
        .padding(EdgeInsets(top: 16, leading: 16, bottom: 16, trailing: 16))
    }
    
    // MARK: - Forward/Backward Buttons (Portrait - Full Size)
    var forwardBackwardButtonsPortrait: some View {
        VStack(spacing: 16) {
            Text("MOVEMENT")
                .foregroundColor(.gray)
                .font(.caption)
                .fontWeight(.semibold)
            
            VStack(spacing: 16) {
                // Forward Button
                Button(action: {}) {
                    VStack(spacing: 4) {
                        Image(systemName: "chevron.up")
                            .foregroundColor(.white)
                            .font(.title)
                        Text("FWD")
                            .foregroundColor(.white)
                            .font(.caption2)
                            .fontWeight(.semibold)
                    }
                    .frame(width: 80, height: 80)
                    .background(activeDirection == "forward" ? Color.green : Color.gray.opacity(0.3))
                    .cornerRadius(8)
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(activeDirection == "forward" ? Color.green.opacity(0.7) : Color.gray.opacity(0.5), lineWidth: 2)
                    )
                }
                .scaleEffect(activeDirection == "forward" ? 0.95 : 1.0)
                .onLongPressGesture(minimumDuration: 0, maximumDistance: 50, pressing: { pressing in
                    withAnimation(.easeInOut(duration: 0.1)) {
                        activeDirection = pressing ? "forward" : nil
                    }
                    Task {
                        await handleForwardBackward(direction: "forward", isPressed: pressing)
                    }
                }, perform: {})
                
                // Backward Button
                Button(action: {}) {
                    VStack(spacing: 4) {
                        Image(systemName: "chevron.down")
                            .foregroundColor(.white)
                            .font(.title)
                        Text("REV")
                            .foregroundColor(.white)
                            .font(.caption2)
                            .fontWeight(.semibold)
                    }
                    .frame(width: 80, height: 80)
                    .background(activeDirection == "backward" ? Color.red : Color.gray.opacity(0.3))
                    .cornerRadius(8)
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(activeDirection == "backward" ? Color.red.opacity(0.7) : Color.gray.opacity(0.5), lineWidth: 2)
                    )
                }
                .scaleEffect(activeDirection == "backward" ? 0.95 : 1.0)
                .onLongPressGesture(minimumDuration: 0, maximumDistance: 50, pressing: { pressing in
                    withAnimation(.easeInOut(duration: 0.1)) {
                        activeDirection = pressing ? "backward" : nil
                    }
                    Task {
                        await handleForwardBackward(direction: "backward", isPressed: pressing)
                    }
                }, perform: {})
            }
        }
    }
    
    // MARK: - Forward/Backward Buttons (Landscape - Compact)
    var forwardBackwardButtons: some View {
        VStack(spacing: 8) {
            Text("MOVEMENT")
                .foregroundColor(.gray)
                .font(.caption2)
                .fontWeight(.semibold)
            
            VStack(spacing: 8) {
                // Forward Button
                Button(action: {}) {
                    Image(systemName: "chevron.up")
                        .foregroundColor(.white)
                        .font(.title3)
                        .frame(width: 50, height: 50)
                        .background(activeDirection == "forward" ? Color.green : Color.gray.opacity(0.3))
                        .cornerRadius(8)
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(activeDirection == "forward" ? Color.green.opacity(0.7) : Color.gray.opacity(0.5), lineWidth: 2)
                        )
                }
                .scaleEffect(activeDirection == "forward" ? 0.95 : 1.0)
                .onLongPressGesture(minimumDuration: 0, maximumDistance: 50, pressing: { pressing in
                    withAnimation(.easeInOut(duration: 0.1)) {
                        activeDirection = pressing ? "forward" : nil
                    }
                    Task {
                        await handleForwardBackward(direction: "forward", isPressed: pressing)
                    }
                }, perform: {})
                
                // Backward Button
                Button(action: {}) {
                    Image(systemName: "chevron.down")
                        .foregroundColor(.white)
                        .font(.title3)
                        .frame(width: 50, height: 50)
                        .background(activeDirection == "backward" ? Color.red : Color.gray.opacity(0.3))
                        .cornerRadius(8)
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(activeDirection == "backward" ? Color.red.opacity(0.7) : Color.gray.opacity(0.5), lineWidth: 2)
                        )
                }
                .scaleEffect(activeDirection == "backward" ? 0.95 : 1.0)
                .onLongPressGesture(minimumDuration: 0, maximumDistance: 50, pressing: { pressing in
                    withAnimation(.easeInOut(duration: 0.1)) {
                        activeDirection = pressing ? "backward" : nil
                    }
                    Task {
                        await handleForwardBackward(direction: "backward", isPressed: pressing)
                    }
                }, perform: {})
            }
        }
    }
    
    // MARK: - Computed Properties
    var speedText: String {
        return "\(currentSpeed)"
    }
    
    var speedColor: Color {
        switch activeDirection {
        case "forward":
            return .green
        case "backward":
            return .red
        default:
            return .gray
        }
    }
    
    var connectionStatusColor: Color {
        switch robotController.connectionStatus {
        case "connected":
            return .green
        case "error":
            return .orange
        case "disconnected":
            return .red
        default:
            return .gray
        }
    }
    
    var speedIndicator: String {
        return "\(currentSpeed)"
    }
    
    var directionText: String {
        switch activeDirection {
        case "forward":
            return "Forward"
        case "backward":
            return "Reverse"
        case "left":
            return "Turning Left"
        case "right":
            return "Turning Right"
        case "turret_left":
            return "Turret Left"
        case "turret_right":
            return "Turret Right"
        default:
            return "Stopped"
        }
    }
    
    // MARK: - Functions
    func handleVehicleControl(direction: String, isPressed: Bool) async {
        print("Vehicle \(direction): \(isPressed)")
        
        if isPressed {
            isMoving = true
            do {
                switch direction {
                case "left":
                    try await robotController.turnLeft(speed: Config.defaultTurnSpeed)
                case "right":
                    try await robotController.turnRight(speed: Config.defaultTurnSpeed)
                default:
                    break
                }
            } catch {
                print("Error controlling vehicle: \(error)")
            }
        } else {
            isMoving = false
            do {
                try await robotController.stop()
            } catch {
                print("Error stopping vehicle: \(error)")
            }
        }
    }
    
    func handleTurretControl(direction: String, isPressed: Bool) async {
        print("Turret \(direction): \(isPressed)")
        
        if isPressed {
            let step: Double = 5
            lastTurretDirection = direction
            if direction == "left" {
                turretRotation = max(-180, turretRotation - step)
            } else {
                turretRotation = min(180, turretRotation + step)
            }
            
            do {
                switch direction {
                case "left":
                    try await robotController.turretLeft(speed: Config.defaultTurretSpeed, duration: 0) // Continuous rotation
                case "right":
                    try await robotController.turretRight(speed: Config.defaultTurretSpeed, duration: 0) // Continuous rotation
                default:
                    break
                }
            } catch {
                print("Error controlling turret: \(error)")
            }
        } else {
            // Button released - send stop command
            do {
                try await robotController.stopTurret()
            } catch {
                print("Error stopping turret: \(error)")
            }
        }
    }
    
    func handleTurretRotation(direction: String) {
        let step: Double = 5
        lastTurretDirection = direction
        if direction == "left" {
            turretRotation = max(-180, turretRotation - step)
        } else {
            turretRotation = min(180, turretRotation + step)
        }
    }
    
    func handleForwardBackward(direction: String, isPressed: Bool) async {
        print("Movement \(direction): \(isPressed)")
        
        if isPressed {
            isMoving = true
            currentSpeed = defaultMoveSpeed
            do {
                switch direction {
                case "forward":
                    try await robotController.moveForward(speed: defaultMoveSpeed)
                case "backward":
                    try await robotController.moveBackward(speed: defaultMoveSpeed)
                default:
                    break
                }
            } catch {
                print("Error controlling vehicle: \(error)")
            }
        } else {
            isMoving = false
            currentSpeed = 0
            do {
                try await robotController.stop()
            } catch {
                print("Error stopping vehicle: \(error)")
            }
        }
    }
    
    func sendTurretCommand() async {
        print("Turret rotation: \(turretRotation)° - Direction: \(lastTurretDirection)")
        
        do {
            switch lastTurretDirection {
            case "left":
                try await robotController.turretLeft(speed: Config.defaultTurretSpeed, duration: Config.defaultTurretDuration)
            case "right":
                try await robotController.turretRight(speed: Config.defaultTurretSpeed, duration: Config.defaultTurretDuration)
            default:
                break
            }
        } catch {
            print("Error sending turret command: \(error)")
        }
    }
    
    func stopVehicle() async {
        do {
            try await robotController.stop()
        } catch {
            print("Error stopping vehicle: \(error)")
        }
    }
    
    func showSettings() {
        print("Settings tapped")
        // Could show connection settings, API key configuration, etc.
    }
}



// MARK: - Preview
struct ContentView_Previews: PreviewProvider {
    static var previews: some View {
        ContentView()
            .previewDevice("iPhone 14 Pro")
            .previewInterfaceOrientation(.landscapeLeft)
    }
}
