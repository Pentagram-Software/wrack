#!/usr/bin/env pybricks-micropython

from pybricks.ev3devices import Motor
from pybricks.parameters import Port, Stop, Direction
from pybricks.tools import wait
from .drive_system import DriveSystem
from error_reporting import report_device_error, report_exception


class Turret(DriveSystem):
    """
    A turret system that provides positional control.
    Maps joystick position directly to turret angle.
    """
    
    def __init__(self, device_manager):
        super().__init__(device_manager)
        self.turret_motor = None
        self.current_target_angle = 0  # Track target position
        self.max_angle = 90  # Maximum rotation in degrees (+/- from center)
        self.min_angle = -90
        self.center_position = 0  # Center/home position
        self.max_speed = 360  # Maximum rotation speed in degrees/second
        
        # Get turret motor from device manager
        if device_manager.is_device_available("turret_motor"):
            self.turret_motor = device_manager.get_device("turret_motor")
            print("Turret motor initialized")
            # Reset motor position to center
            self.home_turret()
        else:
            print("Turret motor not available")
    
    def home_turret(self):
        """Reset turret to center position and set this as angle 0"""
        if self.turret_motor:
            try:
                # Reset the motor angle to 0 at current position
                self.turret_motor.reset_angle(0)
                self.current_target_angle = 0
                print("Turret homed to center position")
            except Exception as e:
                report_device_error("turret_motor", "home_turret", e, "reset_angle(0)")
    
    def joystick_control(self, x_axis, y_axis):
        """
        Control turret position based on joystick input.
        x_axis: -100 to 100 (left/right joystick movement)
        y_axis: -100 to 100 (up/down joystick movement, currently unused)
        """
        if not self.turret_motor:
            return
        
        # Apply deadzone to prevent jitter
        deadzone = 10
        if abs(x_axis) < deadzone:
            x_axis = 0
        
        # Map joystick X-axis (-100 to 100) to turret angle range
        target_angle = self.scale_joystick_to_angle(x_axis)
        
        # Only move if target position has changed significantly
        angle_threshold = 2  # degrees
        if abs(target_angle - self.current_target_angle) > angle_threshold:
            self.move_to_angle(target_angle)
            self.current_target_angle = target_angle
    
    def speed_control(self, x_axis, y_axis):
        """
        Control turret rotation speed based on joystick input.
        x_axis: -100 to 100 (left/right joystick movement)
        - Negative values rotate left
        - Positive values rotate right
        - Magnitude determines speed
        y_axis: -100 to 100 (up/down joystick movement, currently unused)
        """
        if not self.turret_motor:
            return
        
        # Apply aggressive deadzone to prevent jitter and ensure reliable stop
        LARGE_DEADZONE = 50  # Much larger deadzone for reliable stop detection
        if abs(x_axis) < LARGE_DEADZONE:
            # Stop turret when joystick is centered or near center
            try:
                self.turret_motor.stop(Stop.HOLD)
            except Exception as e:
                report_device_error("turret_motor", "speed_control_stop", e, "stop(Stop.HOLD)")
            return
        
        # Scale joystick input to motor speed
        # Map (-100 to 100) to (-max_speed to +max_speed) degrees per second
        speed = int((x_axis / 100.0) * self.max_speed)
        
        # Clamp speed to safe range
        speed = max(-self.max_speed, min(self.max_speed, speed))
        
        try:
            # Use run() for continuous rotation at specified speed
            self.turret_motor.run(speed)
        except Exception as e:
            report_device_error("turret_motor", "speed_control_run", e, "run({})".format(speed))
    
    def scale_joystick_to_angle(self, joystick_value):
        """
        Scale joystick value (-100 to 100) to turret angle range
        """
        # Clamp joystick value to expected range
        joystick_value = max(-100, min(100, joystick_value))
        
        # Map to angle range
        if joystick_value >= 0:
            # Positive joystick (right) maps to positive angle
            angle = (joystick_value / 100.0) * self.max_angle
        else:
            # Negative joystick (left) maps to negative angle  
            angle = (joystick_value / 100.0) * abs(self.min_angle)
        
        return angle
    
    def move_to_angle(self, target_angle):
        """
        Move turret to specific angle position
        """
        if not self.turret_motor:
            return
        
        # Clamp target angle to safe range
        target_angle = max(self.min_angle, min(self.max_angle, target_angle))
        
        try:
            # Use run_target for precise positioning
            # Speed of 200 degrees/second, with smooth stop
            self.turret_motor.run_target(200, target_angle, Stop.HOLD, wait=False)
        except Exception as e:
            report_device_error("turret_motor", "move_to_angle", e, "run_target(200, {}, Stop.HOLD, wait=False)".format(target_angle))
    
    def get_current_angle(self):
        """Get current turret angle"""
        if self.turret_motor:
            try:
                return self.turret_motor.angle()
            except Exception as e:
                report_device_error("turret_motor", "get_current_angle", e, "angle()")
                return 0
        return 0
    
    def stop(self):
        """Stop turret movement and hold position"""
        if self.turret_motor:
            try:
                self.turret_motor.stop(Stop.HOLD)
            except Exception as e:
                report_device_error("turret_motor", "stop", e, "stop(Stop.HOLD)")
    
    def set_angle_limits(self, min_angle, max_angle):
        """Set the movement limits for the turret"""
        self.min_angle = min_angle
        self.max_angle = max_angle
        print("Turret angle limits set to " + str(min_angle) + "° to " + str(max_angle) + "°")
    
    def set_max_speed(self, max_speed):
        """Set the maximum rotation speed for the turret"""
        self.max_speed = max_speed
        print("Turret maximum speed set to " + str(max_speed) + "°/second")
    
    # Required DriveSystem interface methods (not used for turret but required)
    def move_forward(self, distance):
        pass
    
    def move_backward(self, distance):
        pass
    
    def turn_left(self, angle):
        # Could be repurposed for turret left turn
        self.move_to_angle(self.min_angle)
    
    def turn_right(self, angle):
        # Could be repurposed for turret right turn  
        self.move_to_angle(self.max_angle)
    
    def move_with_steering(self, distance, steering):
        pass 