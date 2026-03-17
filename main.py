#!/usr/bin/env pybricks-micropython

"""
EV3 PS4 Controller Robot with Graceful Device Handling

This program controls an EV3 robot using a PS4 controller with robust
device management that handles missing devices gracefully.

Features:
- Automatic device detection and initialization
- Graceful handling of missing devices
- Safe device operations with error handling
- Device status reporting and debugging
- Conditional feature activation based on device availability

Device Manager:
The DeviceManager class provides a centralized way to handle all EV3 devices
with proper error handling. It automatically detects which devices are
connected and provides safe access methods.

Usage:
- Devices are automatically initialized on startup
- Use device_manager.is_device_available() to check if a device exists
- Use device_manager.safe_device_call() for safe device operations
- Use device_manager.safe_device_operation() for complex operations
"""

from pybricks.hubs import EV3Brick
from robot_controllers import MIN_JOYSTICK_MOVE, PS4Controller
from pixy_camera import Pixy2Camera
from ev3_devices import DeviceManager
from robot_controllers import RemoteController
from ev3_devices import TankDriveSystem
from ev3_devices import Turret
from pybricks.parameters import (Port, Stop, Direction, Button, Color,
                                 SoundFile, ImageFile, Align)

from pybricks.ev3devices import (Motor, TouchSensor, ColorSensor,
                                 InfraredSensor, UltrasonicSensor, GyroSensor)

import sys
import math
from time import sleep

# Import TerrainScanner with error handling
TerrainScanner = None
try:
    from TerrainScanner import TerrainScanner
    print("TerrainScanner module imported successfully")
except ImportError as e:
    print("TerrainScanner module not found: {} - terrain scanning will be disabled".format(e))
    TerrainScanner = None
except Exception as e:
    print("Error importing TerrainScanner: {} - terrain scanning will be disabled".format(e))
    TerrainScanner = None

# Import WakeWordDetector with error handling (Mycroft Precise)
WakeWordDetector = None
try:
    from wake_word import WakeWordDetector
    if WakeWordDetector.is_available():
        print("WakeWordDetector module imported successfully (Mycroft Precise available)")
    else:
        print("WakeWordDetector imported but Mycroft Precise not installed")
        print("Install with: pip install precise-runner")
except ImportError as e:
    print("WakeWordDetector module not found: {} - wake word detection will be disabled".format(e))
    WakeWordDetector = None
except Exception as e:
    print("Error importing WakeWordDetector: {} - wake word detection will be disabled".format(e))
    WakeWordDetector = None



#TODO: Better understand the debug mode
if __debug__:
    print("Debug ON")
else:
    print('Debug OFF');

ev3 = EV3Brick()

# Initialize device manager with EV3Brick reference for battery monitoring
device_manager = DeviceManager(ev3)

# Global state to avoid redundant stop calls
robot_is_stopped = False

# Initialize devices with graceful error handling
drive_L_motor = device_manager.try_init_device(Motor, Port.A, "drive_L_motor")
drive_R_motor = device_manager.try_init_device(Motor, Port.D, "drive_R_motor")
turret_motor = device_manager.try_init_device(Motor, Port.C, "turret_motor")
us_sensor = device_manager.try_init_device(UltrasonicSensor, Port.S2, "us_sensor")
gyro_sensor = device_manager.try_init_device(GyroSensor, Port.S3, "gyro_sensor")
#pixy_camera = device_manager.try_init_device(Pixy2Camera, Port.S1, "pixy_camera")

# Initialize drive system
tank_drive_system = TankDriveSystem(device_manager)
tank_drive_system.initialize()

# Initialize turret system
turret = Turret(device_manager)

# Initialize terrain scanner
if TerrainScanner and device_manager.are_devices_available(["us_sensor", "gyro_sensor"]):
    try:
        terrain_scanner = TerrainScanner(device_manager, tank_drive_system, ev3.speaker)
        print("TerrainScanner initialized successfully")
    except Exception as e:
        print("Error initializing TerrainScanner: {}".format(e))
        terrain_scanner = None
else:
    if not TerrainScanner:
        print("TerrainScanner class not available")
    else:
        print("TerrainScanner not available - missing required sensors")

# Initialize wake word detector (Mycroft Precise for "Hey Wrack")
wake_word_detector = None
if WakeWordDetector and WakeWordDetector.is_available():
    try:
        wake_word_detector = WakeWordDetector(speaker=ev3.speaker)
        print("WakeWordDetector initialized successfully")
    except Exception as e:
        print("Error initializing WakeWordDetector: {}".format(e))
        wake_word_detector = None
else:
    if not WakeWordDetector:
        print("WakeWordDetector class not available")
    else:
        print("WakeWordDetector not available - Mycroft Precise not installed")

# Print device status
device_manager.print_device_status()

def test_device_management():
    """
    Test function to demonstrate device management capabilities.
    This function shows how to safely work with devices.
    """
    print("=== Testing Device Management ===")
    
    # Test individual device availability
    print("Steer motor available: {}".format(device_manager.is_device_available('steer_motor')))
    print("Drive motors available: {}".format(device_manager.are_devices_available(['drive_L_motor', 'drive_R_motor'])))
    
    # Test safe device calls
    device_manager.safe_device_call("steer_motor", "stop")
    device_manager.safe_device_call("pixy_camera", "light", True)
    
    # Test complex operations
    def complex_motor_operation(motor, speed, duration):
        """Example of a complex motor operation"""
        motor.run(speed)
        sleep(duration)
        motor.stop()
        return "Operation completed"
    
    result = device_manager.safe_device_operation(
        "steer_motor", 
        "complex_motor_test", 
        complex_motor_operation, 
        500,  # speed
        1     # duration
    )
    
    if result:
        print("Complex operation result: {}".format(result))
    
    # Get device summary
    summary = device_manager.get_device_summary()
    print("Device summary: {}/{} devices available".format(summary['available'], summary['total']))
    
    print("=== Device Management Test Complete ===\n")

# Uncomment the line below to run device management tests
# test_device_management()

# Global variable for tracking turret angle
last_angle = 0

# Initialize terrain scanner
terrain_scanner = None



def lightoff(value):
    #us_sensor.distance();

    """
    Perform the specified action.

    Args:
        value: The value to be used for the action.

    Returns:
        None
    """

    device_manager.safe_device_call("pixy_camera", "light", False);

def lighton(value):
    #us_sensor.distance();

    """
    Perform the specified action.

    Args:
        value: The value to be used for the action.

    Returns:
        None
    """

    device_manager.safe_device_call("pixy_camera", "light", True);

def sayit(value):
    ev3.speaker.say("Hello, I am Wrack!")

def start_auto_terrain_scanning(value):
    """Start automatic terrain scanning"""
    global terrain_scanner
    if terrain_scanner and TerrainScanner:
        terrain_scanner.start_automatic_scanning()
    else:
        print("TerrainScanner not available")
        ev3.speaker.beep(frequency=300, duration=500)

def stop_auto_terrain_scanning(value):
    """Stop automatic terrain scanning"""
    global terrain_scanner
    if terrain_scanner and TerrainScanner:
        terrain_scanner.stop_automatic_scanning()
    else:
        print("TerrainScanner not available")

def perform_single_terrain_scan(value):
    """Perform a single terrain scan"""
    global terrain_scanner
    if terrain_scanner and TerrainScanner:
        # Run scan in separate thread to avoid blocking
        import threading
        scan_thread = threading.Thread(target=lambda: terrain_scanner.perform_scan("full_360"), daemon=True)
        scan_thread.start()
    else:
        print("TerrainScanner not available")
        ev3.speaker.beep(frequency=300, duration=500)

def perform_quick_terrain_scan(value):
    """Perform a quick 8-point terrain scan"""
    global terrain_scanner
    if terrain_scanner and TerrainScanner:
        # Run scan in separate thread to avoid blocking
        import threading
        scan_thread = threading.Thread(target=lambda: terrain_scanner.perform_scan("quick_8_point"), daemon=True)
        scan_thread.start()
    else:
        print("TerrainScanner not available")
        ev3.speaker.beep(frequency=300, duration=500)

def get_terrain_scan_status(value):
    """Announce terrain scanner status"""
    global terrain_scanner
    if terrain_scanner and TerrainScanner:
        status = terrain_scanner.get_scan_status()
        if status["scan_in_progress"]:
            ev3.speaker.say("Scan in progress")
        elif status["auto_scan_enabled"]:
            ev3.speaker.say("Auto scanning enabled")
        else:
            ev3.speaker.say("Scanner ready")
        
        print("Terrain Scanner Status:")
        print("- Scan in progress: {}".format(status["scan_in_progress"]))
        print("- Auto scan enabled: {}".format(status["auto_scan_enabled"]))
        print("- Total scans: {}".format(status["total_scans"]))
        print("- Pending scans: {}".format(status["pending_scans"]))
    else:
        ev3.speaker.say("Scanner not available")

def cancel_terrain_scan(value):
    """Cancel current terrain scan"""
    global terrain_scanner
    if terrain_scanner and TerrainScanner:
        terrain_scanner.cancel_current_scan()
    else:
        print("TerrainScanner not available")

def quit(value):
    # Stop terrain scanner
    global terrain_scanner
    if terrain_scanner:
        print("Shutting down TerrainScanner...")
        terrain_scanner.cleanup()
    
    # Stop wake word detector
    global wake_word_detector
    if wake_word_detector:
        print("Shutting down WakeWordDetector...")
        wake_word_detector.stop()
    
    # Stop turret and hold position
    if turret:
        turret.stop()
    
    # Stop tank drive system
    tank_drive_system.stop()
    
    # Stop remote controller if it exists
    if 'remote_controller' in globals():
        print("Shutting down Network Remote Controller...")
        remote_controller.stop()
    
    # Cleanup devices
    device_manager.cleanup()
    
    # Stop the PS4 controller
    value.stop()                                                  


def driftLeft(value):
    global robot_is_stopped
    tank_drive_system.drift_left(1000)
    robot_is_stopped = False

def driftRight(value):
    global robot_is_stopped
    tank_drive_system.drift_right(1000)
    robot_is_stopped = False


def driftStop(value):
    global robot_is_stopped
    tank_drive_system.stop()
    robot_is_stopped = True

def moveForward(value):
    global robot_is_stopped
    tank_drive_system.move_forward(1000)  # Full speed forward
    robot_is_stopped = False

def moveBackward(value):
    global robot_is_stopped
    tank_drive_system.move_backward(1000)  # Full speed backward
    robot_is_stopped = False

def moveStop(value):
    global robot_is_stopped
    tank_drive_system.stop()
    robot_is_stopped = True

def move(value): 
    """
    Moves the robot based on joystick input using direct speed/direction control.
    Y-axis controls forward/backward speed, X-axis controls turning speed.

    Args:
        value: The joystick value containing l_left (X-axis turning) and l_forward (Y-axis movement).

    Returns:
        None
    """
    # Apply very aggressive deadzone filtering to prevent race conditions
    LARGE_DEADZONE = 200  # Much larger deadzone for reliable stop detection
    
    # Global state to prevent race conditions
    global robot_is_stopped
    
    # Apply deadzone and ensure true zero when joystick is at rest
    if abs(value.l_forward) < LARGE_DEADZONE:
        forward_speed = 0
    else:
        forward_speed = -1 * value.l_forward
        
    if abs(value.l_left) < LARGE_DEADZONE:
        turn_speed = 0
    else:
        turn_speed = -1 * value.l_left
    
    # Determine if joystick is truly at rest
    is_joystick_at_rest = (forward_speed == 0 and turn_speed == 0)
    
    # Debug output removed for better performance
    
    # Use joystick control method: Y-axis = speed, X-axis = direction
    tank_drive_system.joystick_control(forward_speed, turn_speed)
    
    # Update stopped state
    robot_is_stopped = is_joystick_at_rest

def watch(value):
    """Handle right joystick movement for turret control"""
    if turret:
        # Apply aggressive deadzone filtering similar to tank drive
        TURRET_DEADZONE = 50  # Large deadzone for reliable stop detection
        
        # Apply deadzone and ensure true zero when joystick is at rest
        if abs(value.r_left) < TURRET_DEADZONE:
            x_axis = 0
        else:
            x_axis = value.r_left
            
        if abs(value.r_forward) < TURRET_DEADZONE:
            y_axis = 0
        else:
            y_axis = value.r_forward
        
        # Map right joystick to turret speed control
        # x_axis: left/right rotation with speed
        # y_axis: currently unused
        turret.speed_control(x_axis, y_axis)

    result = 0;
    val_x = value.r_left * -1;
    val_y = value.r_forward;
    
    if(abs(val_x) < 10 and abs(val_y) < 10):
        return
    if(val_x == 0):
        return;
    if(val_y == 0):
        return;  # Prevent divide by zero in math.atan calculations

    quadrant = 1;
    if (val_x < 0 and val_y < 0):
        quadrant = 3
        #result_degrees = result_degrees_orig + 180
        result = math.atan(abs(val_x) / abs(val_y))
    elif(val_y < 0):
        quadrant = 2
        #result_degrees = result_degrees_orig + 90
        result = math.atan(abs(val_y) / abs(val_x))
    elif(val_x < 0):
        quadrant = 4
        #result_degrees = result_degrees_orig + 270
        result = math.atan(abs(val_y) / abs(val_x))
    else:
        quadrant = 1
        result = math.atan(abs(val_x) / abs(val_y))

    result_degrees_orig = math.degrees(result)
    result_degrees = result_degrees_orig

    if(quadrant == 3):
        result_degrees = result_degrees_orig + 180
    elif(quadrant==2):
        result_degrees = result_degrees_orig + 90
    elif(quadrant == 4):
        result_degrees = result_degrees_orig + 270

    # TODO: This code is disabled - old implementation for angle tracking
    # If re-enabling, need to define drive_motor properly
    # 
    # angle_shift = abs(result_degrees - last_angle);
    # speed = 360;
    # result_degrees_final = result_degrees;
    # if(angle_shift > 180):
    #     if(result_degrees > last_angle):
    #         diff = result_degrees - last_angle;
    #         diff = diff - 360;
    #         result_degrees_final = last_angle + diff;
    #     else:
    #         diff = result_degrees - last_angle;
    #         diff = diff + 360;
    #         result_degrees_final = last_angle + diff;
    # 
    #     print("Shift is greater than 180:" + str(result_degrees_final))
    #     speed = -1 * speed;
    # 
    # 
    # if(angle_shift < 5):
    #     return
    # 
    # print(str(result_degrees_final) + " from " + str(last_angle) + " shift: " + str(angle_shift) + " speed: " + str(speed))
    # 
    # # NOTE: drive_motor is not defined - would need to be initialized if this code is re-enabled
    # # drive_motor.track_target(result_degrees_final)
    # last_angle = result_degrees;
    """


def blockDetected(value):
#    if(value.blocks == None or len(value.blocks) == 0):
#        return;
    if not device_manager.is_device_available("pixy_camera"):
        return
        
    block = value.blocks[0];
    if(block.width > 10 or block.height > 10):
        scale_factor = block.x_center - 150;
        device_manager.safe_device_call("turret_motor", "run", scale_factor);


"""

def main():
    # Initialize both PS4 and Network Remote controllers
    controller = PS4Controller()
    remote_controller = RemoteController()
    # Attach device manager so status can include battery/cpu/ip
    remote_controller.device_manager = device_manager
    
    # Start the controller thread first
    controller.start()
    
    # Give the controller a moment to attempt connection
    sleep(0.5)
    
    # Check if controller connected successfully
    if controller.is_connected():
        print("Setting up PS4 controller event handlers...")
        
        # Only set up pixy camera event handler if camera is available
        if device_manager.is_device_available("pixy_camera"):
            pixy_camera.onBlockDetected(blockDetected);

        # Only set up light controls if pixy camera is available
        if device_manager.is_device_available("pixy_camera"):
            controller.onL1Button(lighton)
            controller.onR1Button(lightoff)
        
        # Terrain scanning controls (if available)
        if terrain_scanner:
            controller.onSquareButton(perform_single_terrain_scan)
            controller.onTriangleButton(perform_quick_terrain_scan)
            controller.onL2Button(start_auto_terrain_scanning)
            controller.onR2Button(stop_auto_terrain_scanning)
            controller.onCircleButton(get_terrain_scan_status)
        
        controller.onOptionsButton(quit)
        controller.onLeftJoystickMove(move)
        controller.onCrossButton(sayit)
        
        # Only set up arrow controls if drive motors are available
        if device_manager.are_devices_available(["drive_L_motor", "drive_R_motor"]):
            # Left/Right arrows for drifting
            controller.onLeftArrowPressed(driftLeft)
            controller.onRightArrowPressed(driftRight)
            controller.onLRArrowReleased(driftStop)
            
            # Up/Down arrows for forward/backward movement
            controller.onUpArrowPressed(moveForward)
            controller.onDownArrowPressed(moveBackward)
            controller.onUDArrowReleased(moveStop)
        else:
            print("Drive motors not available - arrow controls disabled")
            
        controller.onRightJoystickMove(watch)
        print("PS4 controller is ready for use!")
    else:
        print("PS4 controller not available - program running in manual mode")
        print("You can still use arrow buttons on the EV3 brick if available")

    # Set up Network Remote Controller event handlers
    print("Setting up Network Remote Controller...")
    
    def remote_forward(remote_ctrl):
        """Handle network forward command"""
        global robot_is_stopped
        speed = getattr(remote_ctrl, 'current_command', {}).get('speed', 1000)
        print("Network command: Moving forward at speed {}".format(speed))
        tank_drive_system.move_forward(speed)
        robot_is_stopped = False

    def remote_backward(remote_ctrl):
        """Handle network backward command"""
        global robot_is_stopped
        speed = getattr(remote_ctrl, 'current_command', {}).get('speed', 1000)
        print("Network command: Moving backward at speed {}".format(speed))
        tank_drive_system.move_backward(speed)
        robot_is_stopped = False

    def remote_left(remote_ctrl):
        """Handle network left turn command"""
        global robot_is_stopped
        speed = getattr(remote_ctrl, 'current_command', {}).get('speed', 1000)
        print("Network command: Turning left at speed {}".format(speed))
        tank_drive_system.drift_left(speed)
        robot_is_stopped = False

    def remote_right(remote_ctrl):
        """Handle network right turn command"""
        global robot_is_stopped
        speed = getattr(remote_ctrl, 'current_command', {}).get('speed', 1000)
        print("Network command: Turning right at speed {}".format(speed))
        tank_drive_system.drift_right(speed)
        robot_is_stopped = False

    def remote_stop(remote_ctrl):
        """Handle network stop command"""
        global robot_is_stopped
        print("Network command: Stopping")
        tank_drive_system.stop()
        if turret:
            turret.stop()
        robot_is_stopped = True

    def remote_fire(remote_ctrl):
        """Handle network fire command"""
        print("Network command: Fire!")
        # Add any fire/action logic here - could trigger lights, sounds, etc.
        ev3.speaker.beep()

    def remote_joystick(remote_ctrl):
        """Handle network joystick control"""
        global robot_is_stopped
        print("Network joystick: L({},{}) R({},{})".format(
            remote_ctrl.l_left, remote_ctrl.l_forward, 
            remote_ctrl.r_left, remote_ctrl.r_forward))
        
        # Use tank drive system's joystick control for left stick
        tank_drive_system.joystick_control(remote_ctrl.l_forward, remote_ctrl.l_left)
        
        # Use turret control for right stick if available
        if turret:
            turret.speed_control(remote_ctrl.r_left, remote_ctrl.r_forward)
        
        # Update stopped state based on joystick position
        is_at_rest = (remote_ctrl.l_forward == 0 and remote_ctrl.l_left == 0)
        robot_is_stopped = is_at_rest

    def remote_camera_left(remote_ctrl):
        """Handle network camera left command"""
        if turret:
            speed = getattr(remote_ctrl, 'current_command', {}).get('speed', 500)
            print("Network command: Camera left at speed {}".format(speed))
            turret.move_left(speed)

    def remote_camera_right(remote_ctrl):
        """Handle network camera right command"""
        if turret:
            speed = getattr(remote_ctrl, 'current_command', {}).get('speed', 500)
            print("Network command: Camera right at speed {}".format(speed))
            turret.move_right(speed)

    def remote_quit(remote_ctrl):
        """Handle network quit command"""
        print("Network command: Shutting down robot...")
        ev3.speaker.say("Goodbye!")
        quit(remote_ctrl)

    def remote_start_auto_scan(remote_ctrl):
        """Handle network start auto terrain scanning command"""
        global terrain_scanner
        if terrain_scanner:
            terrain_scanner.start_automatic_scanning()
            return {
                "status": "success",
                "message": "Automatic terrain scanning started",
                "scan_interval": terrain_scanner.auto_scan_interval
            }
        else:
            return {"status": "error", "message": "TerrainScanner not available"}

    def remote_stop_auto_scan(remote_ctrl):
        """Handle network stop auto terrain scanning command"""
        global terrain_scanner
        if terrain_scanner:
            terrain_scanner.stop_automatic_scanning()
            return {"status": "success", "message": "Automatic terrain scanning stopped"}
        else:
            return {"status": "error", "message": "TerrainScanner not available"}

    def remote_single_scan(remote_ctrl):
        """Handle network single terrain scan command"""
        global terrain_scanner
        if terrain_scanner:
            # Start scan in background thread
            import threading
            scan_thread = threading.Thread(
                target=lambda: terrain_scanner.perform_scan("full_360"), 
                daemon=True
            )
            scan_thread.start()
            
            return {
                "status": "scan_started",
                "scan_type": "full_360",
                "estimated_duration": "60-90 seconds",
                "message": "Single terrain scan initiated"
            }
        else:
            return {"status": "error", "message": "TerrainScanner not available"}

    def remote_quick_scan(remote_ctrl):
        """Handle network quick terrain scan command"""
        global terrain_scanner
        if terrain_scanner:
            # Start scan in background thread
            import threading
            scan_thread = threading.Thread(
                target=lambda: terrain_scanner.perform_scan("quick_8_point"), 
                daemon=True
            )
            scan_thread.start()
            
            return {
                "status": "scan_started",
                "scan_type": "quick_8_point",
                "estimated_duration": "20-30 seconds",
                "message": "Quick terrain scan initiated"
            }
        else:
            return {"status": "error", "message": "TerrainScanner not available"}

    def remote_scan_status(remote_ctrl):
        """Handle network terrain scanner status query"""
        global terrain_scanner
        if terrain_scanner:
            return {
                "status": "success",
                "terrain_scanner_status": terrain_scanner.get_scan_status()
            }
        else:
            return {"status": "error", "message": "TerrainScanner not available"}

    def remote_get_scan_inventory(remote_ctrl):
        """Handle network scan inventory request"""
        global terrain_scanner
        if terrain_scanner:
            return {
                "status": "success",
                "scan_inventory": terrain_scanner.get_scan_inventory()
            }
        else:
            return {"status": "error", "message": "TerrainScanner not available"}

    def remote_get_scan_data(remote_ctrl):
        """Handle network scan data retrieval request"""
        global terrain_scanner
        
        # Extract scan_id from command parameters
        command_data = getattr(remote_ctrl, 'current_command', {})
        scan_id = command_data.get('scan_id')
        
        if not scan_id:
            return {"status": "error", "message": "scan_id parameter required"}
        
        if terrain_scanner:
            scan_data = terrain_scanner.get_scan_data(scan_id)
            if scan_data:
                return {
                    "status": "success",
                    "scan_id": scan_id,
                    "scan_data": scan_data
                }
            else:
                return {"status": "error", "message": "Scan data not found: {}".format(scan_id)}
        else:
            return {"status": "error", "message": "TerrainScanner not available"}

    def remote_confirm_scan_retrieved(remote_ctrl):
        """Handle network scan retrieval confirmation"""
        global terrain_scanner
        
        # Extract scan_id from command parameters
        command_data = getattr(remote_ctrl, 'current_command', {})
        scan_id = command_data.get('scan_id')
        
        if not scan_id:
            return {"status": "error", "message": "scan_id parameter required"}
        
        if terrain_scanner:
            success = terrain_scanner.confirm_scan_retrieved(scan_id)
            if success:
                return {
                    "status": "success",
                    "scan_id": scan_id,
                    "message": "Scan retrieval confirmed"
                }
            else:
                return {"status": "error", "message": "Failed to confirm scan retrieval"}
        else:
            return {"status": "error", "message": "TerrainScanner not available"}

    def remote_turret_left(remote_ctrl):
        """Handle network turret left command - rotate left at specified speed"""
        if turret:
            speed_degrees = getattr(remote_ctrl, 'turret_speed', 360)
            duration = getattr(remote_ctrl, 'turret_duration', 0)
            # Convert speed from degrees/second to joystick scale (-100 to 100)
            # turret.max_speed is 360 degrees/second, so map speed to percentage
            joystick_value = -min(100, (speed_degrees / 360.0) * 100)  # Negative for left
            
            if duration > 0:
                print("Network command: Turret rotating left at {} degrees/second for {} seconds (joystick: {})".format(speed_degrees, duration, joystick_value))
                # Start rotation
                turret.speed_control(joystick_value, 0)
                # Schedule stop after duration (simple implementation)
                import threading
                def stop_turret():
                    sleep(duration)
                    turret.stop()
                    print("Turret auto-stopped after {} seconds".format(duration))
                threading.Thread(target=stop_turret, daemon=True).start()
            else:
                print("Network command: Turret rotating left at {} degrees/second (continuous, joystick: {})".format(speed_degrees, joystick_value))
                turret.speed_control(joystick_value, 0)
        else:
            print("Turret not available")

    def remote_turret_right(remote_ctrl):
        """Handle network turret right command - rotate right at specified speed"""
        if turret:
            speed_degrees = getattr(remote_ctrl, 'turret_speed', 360)
            duration = getattr(remote_ctrl, 'turret_duration', 0)
            # Convert speed from degrees/second to joystick scale (-100 to 100)
            # turret.max_speed is 360 degrees/second, so map speed to percentage
            joystick_value = min(100, (speed_degrees / 360.0) * 100)  # Positive for right
            
            if duration > 0:
                print("Network command: Turret rotating right at {} degrees/second for {} seconds (joystick: {})".format(speed_degrees, duration, joystick_value))
                # Start rotation
                turret.speed_control(joystick_value, 0)
                # Schedule stop after duration (simple implementation)
                import threading
                def stop_turret():
                    sleep(duration)
                    turret.stop()
                    print("Turret auto-stopped after {} seconds".format(duration))
                threading.Thread(target=stop_turret, daemon=True).start()
            else:
                print("Network command: Turret rotating right at {} degrees/second (continuous, joystick: {})".format(speed_degrees, joystick_value))
                turret.speed_control(joystick_value, 0)
        else:
            print("Turret not available")

    def remote_stop_turret(remote_ctrl):
        """Handle network turret stop command - immediately stop turret rotation"""
        if turret:
            print("Network command: Stopping turret rotation")
            turret.stop()
            return {
                "status": "success",
                "message": "Turret rotation stopped",
                "turret_available": True
            }
        else:
            print("Turret not available for stop command")
            return {
                "status": "error", 
                "message": "Turret not available",
                "turret_available": False
            }
    
    def remote_speak(remote_ctrl):
        """Handle network speak command - make EV3 speak text out loud"""
        text = remote_ctrl.speak_text
        if text:
            print("Network command: Speaking text: '{}'".format(text))
            try:
                ev3.speaker.say(text)
                return {
                    "status": "success",
                    "action": "speak",
                    "text": text,
                    "message": "Text spoken successfully"
                }
            except Exception as e:
                print("Error speaking text: {}".format(e))
                return {
                    "status": "error",
                    "action": "speak",
                    "message": "Failed to speak text: {}".format(e)
                }
        else:
            print("Speak command received but no text provided")
            return {
                "status": "error",
                "action": "speak",
                "message": "No text provided to speak"
            }
    
    def remote_beep(remote_ctrl):
        """Handle network beep command - make EV3 play a beep sound"""
        frequency = getattr(remote_ctrl, 'beep_frequency', 800)
        duration = getattr(remote_ctrl, 'beep_duration', 200)
        
        print("Network command: Beep at {} Hz for {} ms".format(frequency, duration))
        try:
            ev3.speaker.beep(frequency=frequency, duration=duration)
            return {
                "status": "success",
                "action": "beep",
                "frequency": frequency,
                "duration": duration,
                "message": "Beep played successfully"
            }
        except Exception as e:
            print("Error playing beep: {}".format(e))
            return {
                "status": "error",
                "action": "beep",
                "message": "Failed to play beep: {}".format(e)
            }
    
    def remote_battery(remote_ctrl):
        """Handle network battery status request"""
        print("Network command: Battery status request")
        try:
            # Get comprehensive battery info from device manager
            battery_info = device_manager.get_battery_info(battery_type="rechargeable")
            
            if battery_info["available"]:
                # Print to console
                print("Battery Status:")
                print("  Voltage: {} mV ({:.2f} V)".format(
                    battery_info["voltage_mv"], 
                    battery_info["voltage_mv"] / 1000.0
                ))
                print("  Current: {} mA".format(battery_info["current_ma"]))
                print("  Percentage: {}%".format(battery_info["percentage"]))
                
                # Prepare detailed response as a single-line JSON string in expected key order
                voltage_mv = battery_info["voltage_mv"] if battery_info["voltage_mv"] is not None else 0
                voltage_v_str = "{:.2f}".format((voltage_mv or 0) / 1000.0)
                current_ma = battery_info["current_ma"] if battery_info["current_ma"] is not None else 0
                percentage = battery_info["percentage"] if battery_info["percentage"] is not None else 0
                battery_type = battery_info["battery_type"]

                # Build JSON string manually to guarantee field order (MicroPython-safe, no f-strings)
                response = (
                    "{" +
                    "\"status\":\"success\"," +
                    "\"action\":\"battery\"," +
                    "\"battery\":{" +
                        "\"voltage_mv\":" + str(voltage_mv) + "," +
                        "\"voltage_v\":" + voltage_v_str + "," +
                        "\"current_ma\":" + str(current_ma) + "," +
                        "\"percentage\":" + str(percentage) + "," +
                        "\"battery_type\":\"" + battery_type + "\"" +
                    "}," +
                    "\"message\":\"Battery at " + str(percentage) + "%\"" +
                    "}"
                )
                # Response string created
            else:
                print("Battery information not available")
                response = {
                    "status": "error",
                    "action": "battery",
                    "message": "Battery information not available"
                }
        except Exception as e:
            print("Error reading battery status: {}".format(e))
            response = {
                "status": "error",
                "action": "battery",
                "message": "Failed to read battery: {}".format(e)
            }
        
        # Store response so RemoteController can return it
        remote_ctrl.last_response = response
        return response

    def remote_unknown(remote_ctrl):
        """Handle unknown network commands"""
        print("Unknown network command received")
        ev3.speaker.beep(frequency=200, duration=100)  # Low beep for unknown command

    # Register all network remote controller event handlers
    remote_controller.onForward(remote_forward)
    remote_controller.onBackward(remote_backward)
    remote_controller.onLeft(remote_left)
    remote_controller.onRight(remote_right)
    remote_controller.onStop(remote_stop)
    remote_controller.onFire(remote_fire)
    remote_controller.onLeftJoystick(remote_joystick)
    remote_controller.onRightJoystick(remote_joystick)
    remote_controller.onCameraLeft(remote_camera_left)
    remote_controller.onCameraRight(remote_camera_right)
    remote_controller.onUnknown(remote_unknown)
    remote_controller.onQuit(remote_quit)
    remote_controller.onTurretLeft(remote_turret_left)
    remote_controller.onTurretRight(remote_turret_right)
    
    # Turret control commands (if turret available)
    if device_manager.is_device_available("turret_motor"):
        remote_controller.on("stop_turret", remote_stop_turret)
    
    # Speak command (always available)
    remote_controller.on("speak", remote_speak)
    
    # Beep command (always available)
    remote_controller.on("beep", remote_beep)
    
    # Battery command (always available)
    remote_controller.on("battery", remote_battery)
    
    # Terrain scanning network commands (if terrain scanner available)
    if terrain_scanner:
        remote_controller.on("start_auto_scan", remote_start_auto_scan)
        remote_controller.on("stop_auto_scan", remote_stop_auto_scan)
        remote_controller.on("single_scan", remote_single_scan)
        remote_controller.on("quick_scan", remote_quick_scan)
        remote_controller.on("scan_status", remote_scan_status)
        remote_controller.on("scan_inventory", remote_get_scan_inventory)
        remote_controller.on("get_scan_data", remote_get_scan_data)
        remote_controller.on("confirm_scan_retrieved", remote_confirm_scan_retrieved)
    
    # Start the network remote controller
    print("Starting Network Remote Controller on port 27700...")
    remote_controller.start()
    
    # Only start pixy camera if available
    if device_manager.is_device_available("pixy_camera"):
        pixy_camera.start()
    
    # Set up wake word detector (Mycroft Precise - "Hey Wrack")
    global wake_word_detector
    if wake_word_detector:
        print("Setting up Wake Word Detector for 'Hey Wrack'...")
        
        def on_wake_word_detected(detector):
            """Handle wake word detection - respond to 'Hey Wrack'"""
            print("Wake word 'Hey Wrack' detected - robot is listening!")
            ev3.speaker.say("Yes, I am here!")
        
        wake_word_detector.on_wake_word(on_wake_word_detected)
        wake_word_detector.start()
        print("Wake Word Detector started - listening for 'Hey Wrack'")
    else:
        print("Wake Word Detector not available")
        
    if __debug__:
        print ("All control threads started")
        print("")
        
        if controller.is_connected():
            print("=== PS4 Controller Commands ===")
            print("Left Stick Y-axis: Forward/backward speed")
            print("Left Stick X-axis: Turning speed left/right")
            print("Right Stick X-axis: Turret speed left/right")
            print("Left/Right Arrows: Drift left/right")
            print("Up/Down Arrows: Move forward/backward")
            print("Cross Button: Say hello")
            print("L1/R1: Light on/off (if camera available)")
            if terrain_scanner:
                print("Square Button: Single terrain scan")
                print("Triangle Button: Quick terrain scan")
                print("Circle Button: Scanner status")
                print("L2 Button: Start auto scanning")
                print("R2 Button: Stop auto scanning")
            print("Options: Quit")
            print("===============================")
        else:
            print("=== PS4 Controller Status ===")
            print("PS4 controller not connected")
            print("To connect PS4 controller:")
            print("- Pair PS4 controller with EV3 Bluetooth")
            print("- Hold PS + Share buttons to enter pairing mode")
            print("- Use EV3 Bluetooth menu to connect")
            print("- Restart this program")
            print("===============================")
        
        print("")
        print("=== Network Remote Controller ===")
        print("Status: Running on port 27700")
        print("Connect to EV3 IP address on port 27700")
        print("")
        print("Simple text commands:")
        print("  forward, backward, left, right, stop, fire")
        print("  camera_left, camera_right, turret_left, turret_right")
        if device_manager.is_device_available("turret_motor"):
            print("  stop_turret")
        if terrain_scanner:
            print("  start_auto_scan, stop_auto_scan, single_scan, quick_scan")
            print("  scan_status, scan_inventory")
        print("  status, help, quit")
        print("")
        print("JSON command examples:")
        print('  {"action": "forward"}')
        print('  {"action": "move", "direction": "left", "speed": 500}')
        print('  {"action": "turret", "direction": "left", "speed": 150, "duration": 1}')
        print('  {"action": "joystick", "l_left": -500, "l_forward": 800}')
        print('  {"action": "status"}')
        if device_manager.is_device_available("turret_motor"):
            print('  {"action": "stop_turret"}')
        if terrain_scanner:
            print('  {"action": "start_auto_scan"}')
            print('  {"action": "single_scan"}')
            print('  {"action": "scan_inventory"}')
            print('  {"action": "get_scan_data", "scan_id": "terrain_scan_1234"}')
        print("")
        if wake_word_detector and wake_word_detector.is_running():
            print("=== Wake Word Detection ===")
            print("Status: Active - listening for 'Hey Wrack'")
            print("Say 'Hey Wrack' to activate the robot!")
            print("===========================")
            print("")
        print("Google Cloud Functions ready!")
        print("=======================================")
    
    # Audio signal to indicate the robot is ready
    print("Robot initialization complete - playing ready signal...")
    ev3.speaker.beep(frequency=800, duration=200)  # High beep
    sleep(0.1)
    ev3.speaker.beep(frequency=600, duration=200)  # Medium beep
    sleep(0.1)
    ev3.speaker.beep(frequency=800, duration=300)  # High beep (longer)
    print("Robot is ready for operation!")
    
    #Wait for controller thread to finish
    #controller.join()
    #pixy_camera.join();


main()
