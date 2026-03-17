# EV3 PS4 Controlled Robot with Terrain Scanning

**🔗 GitHub Repository:** [https://github.com/rafalkuklinski/ev3PS4Controlled](https://github.com/rafalkuklinski/ev3PS4Controlled)

## 📋 Project Status: **Active Development**
**Last Updated:** August 2025  
**Current Phase:** Terrain Scanning Integration & Cloud Connectivity

---

## 🏗️ Architecture Overview

### Core System Components

#### **1. Main Controller (`main.py`)**
- Central orchestration hub for all robot functions
- PS4 controller integration with event handling
- Network remote controller for cloud connectivity
- Device initialization and graceful error handling
- Terrain scanning coordination

#### **2. Modular Library Structure**

**`robot_controllers/`**
- `ps4_controller.py` - PlayStation 4 controller integration
- `remote_controller.py` - Network-based remote control (Port 27700)
- Event-driven architecture with callback handling

**`ev3_devices/`**
- `device_manager.py` - Centralized device initialization & safety
- `drive_system.py` - Base class for movement systems
- `tank_drive_system.py` - Tank drive implementation
- `turret.py` - Turret positioning and speed control
- Graceful handling of missing hardware components

**`pixy_camera/`**
- `pixy2_camera.py` - Pixy2 camera integration
- Block detection and tracking capabilities

**`error_reporting/`**
- Centralized error logging and device failure reporting
- Debug mode integration

**`event_handler/`**
- Event system for decoupled component communication

#### **3. Terrain Scanning System (`TerrainScanner`)**
- **Current Status:** 🟡 **In Development**
- Modular import with fallback handling
- Integration points established in main controller
- Cloud data retrieval endpoints configured

---

## 🔧 Hardware Configuration

### **Connected Devices**
| Device | Port | Status | Purpose |
|--------|------|--------|---------|
| Left Drive Motor | Port A | ✅ Active | Tank drive left wheel |
| Right Drive Motor | Port D | ✅ Active | Tank drive right wheel |
| Turret Motor | Port C | ✅ Active | Camera/sensor positioning |
| Ultrasonic Sensor | Port S2 | ✅ Active | Distance measurement |
| Gyro Sensor | Port S3 | ✅ Active | Heading/rotation tracking |
| Pixy2 Camera | Port S1 | ⚠️ Optional | Object detection |

### **Control Interfaces**
- **PS4 Controller**: Bluetooth pairing for manual control
- **Network Controller**: TCP socket on port 27700 for cloud integration

---

## 🌐 Cloud Integration Architecture

### **Data Flow Design**
```
Cloud Service ←→ Network Controller (Port 27700) ←→ Robot Systems
    ↓                        ↓                         ↓
JSON Commands          TCP Socket Server         Device Actions
Scan Requests          Event Handlers           Terrain Scanning
Data Retrieval         Response Formatting       Local Storage
```

### **Implemented Network Commands**

#### **Movement Control**
- `forward`, `backward`, `left`, `right`, `stop`
- `{"action": "joystick", "l_left": -500, "l_forward": 800}`

#### **Terrain Scanning** 🆕
- `start_auto_scan` - Begin continuous scanning
- `single_scan` - One-time 360° scan
- `quick_scan` - 8-point rapid scan
- `scan_status` - Get current scanning state
- `scan_inventory` - List available scan data
- `get_scan_data` - Retrieve specific scan by ID
- `confirm_scan_retrieved` - Mark scan as transmitted

#### **Turret Control**
- `turret_left`, `turret_right`, `stop_turret`
- JSON: `{"action": "turret", "direction": "left", "speed": 150, "duration": 1}`

---

## 🎯 Current Implementation Status

### ✅ **Completed Features**
- [x] Robust device management with graceful fallbacks
- [x] PS4 controller integration with full event handling
- [x] Network remote controller with JSON command support
- [x] Tank drive system with obstacle detection
- [x] Turret control with precise positioning
- [x] Gyro sensor integration for accurate heading
- [x] Basic terrain scanning framework
- [x] Cloud data retrieval endpoints
- [x] Local scan data storage architecture

### 🟡 **In Progress**
- [ ] `TerrainScanner` class implementation
- [ ] Movement-based scanning patterns (grid, spiral)
- [ ] Position tracking with gyro correction
- [ ] Scan data persistence and cleanup

### 🔴 **Pending**
- [ ] Cloud service authentication
- [ ] Real-time scan data streaming
- [ ] Advanced obstacle mapping
- [ ] Battery monitoring integration

---

## 📊 Gyro Integration Benefits

### **Enhanced Position Accuracy**
- **Problem Solved**: Encoder-only tracking accumulates drift errors
- **Solution**: Gyro provides absolute heading reference
- **Impact**: Sub-degree accuracy for terrain mapping

### **Validation & Correction**
```python
# Encoder calculation vs Gyro truth
encoder_heading = calculate_from_wheel_diff()
actual_heading = gyro.angle()
correction_factor = actual_heading - encoder_heading
```

---

## 🛡️ Vulnerabilities & Security Considerations

### **High Priority**
1. **Network Security**
   - ⚠️ TCP port 27700 unencrypted
   - **Risk**: Command injection, unauthorized control
   - **Mitigation**: Implement authentication tokens, TLS encryption

2. **Command Validation**
   - ⚠️ JSON commands not sanitized
   - **Risk**: Malformed commands crash system
   - **Mitigation**: Input validation, command whitelisting

### **Medium Priority**
3. **Device Safety**
   - ⚠️ No motor speed limits enforcement
   - **Risk**: Hardware damage from excessive speeds
   - **Mitigation**: Hardware-level speed capping

4. **Memory Management**
   - ⚠️ Scan data accumulation without cleanup
   - **Risk**: Memory exhaustion on long-running scans
   - **Mitigation**: Automatic old scan purging (implemented partially)

### **Low Priority**
5. **Error Recovery**
   - ⚠️ Limited graceful degradation options
   - **Risk**: Single sensor failure affects entire system
   - **Mitigation**: Enhanced fallback modes

---

## 🚀 Next Development Priorities

### **Phase 1: Core Terrain Scanning** (2-3 weeks)
1. Complete `TerrainScanner` class implementation
2. Movement-based scanning patterns (grid, spiral)
3. Gyro-corrected position tracking
4. Local data persistence with JSON export

### **Phase 2: Cloud Integration** (2-4 weeks)
1. Authentication system for network commands
2. Real-time scan data streaming
3. Cloud-triggered area scanning with parameters
4. Scan data compression and optimization

### **Phase 3: Advanced Features** (4-6 weeks)
1. Multi-robot coordination capabilities
2. Advanced obstacle mapping and pathfinding
3. Battery monitoring and power management
4. Web dashboard for remote monitoring

---

## 💡 Technical Recommendations

### **Immediate Actions**
1. **Security**: Implement basic authentication for network controller
2. **Testing**: Create comprehensive test suite for TerrainScanner
3. **Documentation**: API documentation for cloud integration
4. **Monitoring**: Add system health reporting endpoints

### **Architecture Improvements**
1. **Configuration**: Move hardcoded values to config file
2. **Logging**: Implement structured logging with levels
3. **Threading**: Enhanced thread safety for concurrent operations
4. **Error Handling**: Centralized exception handling with recovery

---

## 🔍 TerrainScanner Implementation Plan

### **Movement-Based Scanning Architecture**

#### **Position Tracking System**
```python
class PositionTracker:
    def __init__(self, device_manager):
        self.gyro = device_manager.get_device("gyro_sensor")
        self.position = {"x": 0, "y": 0, "heading": 0}
        self.wheel_diameter = 56  # mm
        
    def update_position(self, left_encoder, right_encoder):
        # Combine encoder data with gyro correction
        distance = (left_encoder + right_encoder) / 2 * self.distance_per_degree
        heading = self.gyro.angle() if self.gyro else self.calculate_heading_from_encoders()
        
        # Update global position
        self.position["x"] += distance * math.cos(math.radians(heading))
        self.position["y"] += distance * math.sin(math.radians(heading))
        self.position["heading"] = heading
```

#### **Scanning Patterns**
1. **Grid Pattern**: Systematic back-and-forth coverage
2. **Spiral Pattern**: Outward expansion from center
3. **Perimeter Scan**: Wall-following behavior
4. **Adaptive Scan**: Obstacle-aware path planning

#### **Cloud Data Format**
```json
{
    "scan_metadata": {
        "scan_id": "terrain_scan_20250824_143022",
        "timestamp": 1692884222,
        "robot_id": "ev3_robot_001",
        "scan_type": "grid_movement",
        "parameters": {
            "grid_size_mm": 200,
            "scan_area": {"width": 2000, "height": 2000},
            "movement_speed": 500
        }
    },
    "measurements": [
        {
            "timestamp": 1692884223,
            "robot_position": {"x": 0, "y": 0, "heading": 0},
            "turret_angle": 0,
            "distance_mm": 1200,
            "confidence": 0.95
        }
    ],
    "scan_summary": {
        "total_measurements": 150,
        "scan_duration_seconds": 180,
        "area_covered_sqmm": 4000000,
        "obstacles_detected": 3
    }
}
```

This architecture provides a solid foundation for autonomous terrain scanning with cloud integration while maintaining modularity and extensibility for future enhancements.