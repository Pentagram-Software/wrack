#!/usr/bin/env python3
"""
Example usage of the enhanced RemoteController

This script demonstrates how to integrate the RemoteController
with your EV3 robot control system.
"""

from RemoteController import RemoteController
from DeviceManager import DeviceManager
from TankDriveSystem import TankDriveSystem
from Turret import Turret
from time import sleep

def main():
    """Example main function showing RemoteController integration"""
    
    # Initialize device manager (same as in main.py)
    device_manager = DeviceManager()
    
    # Initialize drive and turret systems
    tank_drive_system = TankDriveSystem(device_manager)
    tank_drive_system.initialize()
    turret = Turret(device_manager)
    
    # Create and configure the remote controller
    remote_controller = RemoteController(host="", port=27700)  # Listen on all interfaces
    
    # Set up event handlers for vehicle control
    def handle_forward(controller):
        print("Remote command: Moving forward")
        # Get speed from current command if available
        speed = getattr(controller, 'current_command', {}).get('speed', 1000)
        tank_drive_system.move_forward(speed)
    
    def handle_backward(controller):
        print("Remote command: Moving backward")
        speed = getattr(controller, 'current_command', {}).get('speed', 1000)
        tank_drive_system.move_backward(speed)
    
    def handle_left(controller):
        print("Remote command: Turning left")
        speed = getattr(controller, 'current_command', {}).get('speed', 1000)
        tank_drive_system.drift_left(speed)
    
    def handle_right(controller):
        print("Remote command: Turning right")
        speed = getattr(controller, 'current_command', {}).get('speed', 1000)
        tank_drive_system.drift_right(speed)
    
    def handle_stop(controller):
        print("Remote command: Stopping")
        tank_drive_system.stop()
        if turret:
            turret.stop()
    
    def handle_fire(controller):
        print("Remote command: Fire!")
        # Add your fire/action logic here
        pass
    
    def handle_joystick(controller):
        """Handle joystick-style movement commands"""
        print("Remote joystick: L({},{}) R({},{})".format(
            controller.l_left, controller.l_forward, 
            controller.r_left, controller.r_forward))
        
        # Use tank drive system's joystick control
        tank_drive_system.joystick_control(controller.l_forward, controller.l_left)
        
        # Use turret control if available
        if turret:
            turret.speed_control(controller.r_left, controller.r_forward)
    
    def handle_camera_control(controller):
        """Handle camera/turret control"""
        if turret:
            speed = getattr(controller, 'current_command', {}).get('speed', 500)
            direction = getattr(controller, 'current_command', {}).get('direction', '')
            
            if direction == 'left':
                turret.move_left(speed)
            elif direction == 'right':
                turret.move_right(speed)
    
    def handle_unknown(controller):
        print("Unknown remote command received")
    
    # Register event handlers
    remote_controller.onForward(handle_forward)
    remote_controller.onBackward(handle_backward)
    remote_controller.onLeft(handle_left)
    remote_controller.onRight(handle_right)
    remote_controller.onStop(handle_stop)
    remote_controller.onFire(handle_fire)
    remote_controller.onLeftJoystick(handle_joystick)
    remote_controller.onRightJoystick(handle_joystick)
    remote_controller.onCameraLeft(handle_camera_control)
    remote_controller.onCameraRight(handle_camera_control)
    remote_controller.onUnknown(handle_unknown)
    
    print("Starting Remote Controller...")
    print("Connect to the robot at port 27700")
    print("Send JSON commands like: {'action': 'forward', 'speed': 500}")
    print("Or simple text commands like: 'forward'")
    print("Use 'status' command to check robot state")
    print("Use 'help' command for full command reference")
    
    # Start the remote controller in a separate thread
    remote_controller.start()
    
    try:
        # Keep the main thread alive
        while True:
            if remote_controller.is_connected():
                print("Remote controller active with {} connections".format(
                    len(remote_controller.client_connections)))
            else:
                print("Remote controller waiting for connections...")
            sleep(10)
            
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Clean shutdown
        remote_controller.stop()
        tank_drive_system.stop()
        if turret:
            turret.stop()
        device_manager.cleanup()
        print("Shutdown complete.")

if __name__ == "__main__":
    main()
