from .drive_system import DriveSystem
from time import sleep


class TankDriveSystem(DriveSystem):
    """
    Tank-style drive system implementation with independent left and right track motors.
    
    This implementation provides tank-like driving where steering is achieved through
    differential motor speeds between left and right tracks, rather than a separate
    steering mechanism.
    """
    
    def __init__(self, device_manager=None):
        """
        Initialize the tank drive system.
        
        Args:
            device_manager: DeviceManager instance for safe device operations
        """
        super().__init__(device_manager)
        self.left_motor_name = "drive_L_motor"
        self.right_motor_name = "drive_R_motor"
        
        # Default speeds
        self.default_drive_speed = 1000
        self.default_turn_speed = 500
        self.drift_speed = 1000
        
        # Steering sensitivity for joystick control (1.0 = normal, 2.0 = aggressive)
        self.steering_sensitivity = 2.0
    
    def initialize(self):
        """
        Initialize the tank drive system hardware.
        
        Returns:
            bool: True if initialization was successful, False otherwise
        """
        required_devices = [
            self.left_motor_name,
            self.right_motor_name
        ]
        
        available_devices = []
        for device in required_devices:
            if self.is_device_available(device):
                available_devices.append(device)
        
        # System is initialized if both motors are available
        self._is_initialized = len(available_devices) == 2
        
        if __debug__:
            print("TankDriveSystem initialized: {}".format(self._is_initialized))
            print("Available devices: {}".format(available_devices))
        
        return self._is_initialized
    
    def move_forward(self, speed, duration=None):
        """
        Move the robot forward by running both tracks at the same speed.
        
        Args:
            speed: Speed value (-1000 to 1000)
            duration: Optional duration in seconds
        """
        validated_speed = self.validate_speed(speed)
        
        if self.is_device_available(self.left_motor_name):
            self.safe_device_operation(self.left_motor_name, "run", -validated_speed)
        
        if self.is_device_available(self.right_motor_name):
            self.safe_device_operation(self.right_motor_name, "run", -validated_speed)
        
        if duration:
            sleep(duration)
            self.stop()
    
    def move_backward(self, speed, duration=None):
        """
        Move the robot backward by running both tracks in reverse.
        
        Args:
            speed: Speed value (-1000 to 1000)
            duration: Optional duration in seconds
        """
        validated_speed = self.validate_speed(speed)
        
        if self.is_device_available(self.left_motor_name):
            self.safe_device_operation(self.left_motor_name, "run", validated_speed)
        
        if self.is_device_available(self.right_motor_name):
            self.safe_device_operation(self.right_motor_name, "run", validated_speed)
        
        if duration:
            sleep(duration)
            self.stop()
    
    def turn_left(self, speed, duration=None):
        """
        Turn the robot left by running right track faster than left track.
        
        Args:
            speed: Turning speed (-1000 to 1000)
            duration: Optional duration in seconds
        """
        validated_speed = self.validate_speed(speed)
        
        # For aggressive left turn: reverse left track, forward right track
        left_speed = validated_speed // 2   # Reverse left track for sharp turn
        right_speed = -validated_speed      # Forward right track
        
        if self.is_device_available(self.left_motor_name):
            self.safe_device_operation(self.left_motor_name, "run", left_speed)
        
        if self.is_device_available(self.right_motor_name):
            self.safe_device_operation(self.right_motor_name, "run", right_speed)
        
        if duration:
            sleep(duration)
            self.stop()
    
    def turn_right(self, speed, duration=None):
        """
        Turn the robot right by running left track faster than right track.
        
        Args:
            speed: Turning speed (-1000 to 1000)
            duration: Optional duration in seconds
        """
        validated_speed = self.validate_speed(speed)
        
        # For aggressive right turn: forward left track, reverse right track
        left_speed = -validated_speed       # Forward left track
        right_speed = validated_speed // 2  # Reverse right track for sharp turn
        
        if self.is_device_available(self.left_motor_name):
            self.safe_device_operation(self.left_motor_name, "run", left_speed)
        
        if self.is_device_available(self.right_motor_name):
            self.safe_device_operation(self.right_motor_name, "run", right_speed)
        
        if duration:
            sleep(duration)
            self.stop()
    
    def move_with_steering(self, drive_speed, steer_angle):
        """
        Move with simultaneous drive and steering control using differential steering.
        
        Args:
            drive_speed: Forward/backward speed for both tracks
            steer_angle: Steering input (-1000 to 1000, negative = left, positive = right)
        """
        validated_drive_speed = self.validate_speed(drive_speed)
        validated_steer_angle = self.validate_speed(steer_angle)
        
        # Calculate aggressive differential steering for sharper turns
        base_speed = -validated_drive_speed  # Negative for forward direction
        
        # Normalize steering input and increase sensitivity
        steer_factor = validated_steer_angle / 1000.0  # Normalize to -1.0 to 1.0
        
        # Apply steering sensitivity multiplier for more responsive turning
        steer_factor = max(-1.0, min(1.0, steer_factor * self.steering_sensitivity))
        
        # Calculate left and right motor speeds with aggressive differential  
        if abs(steer_factor) < 0.05:  # Going straight (tighter deadzone for steering)
            left_speed = base_speed
            right_speed = base_speed
        elif steer_factor < 0:  # Turning left
            # For sharp left turns: slow/reverse left track, speed up right track
            left_speed = int(base_speed * (1 + steer_factor))   # Reduce/reverse left speed
            right_speed = int(base_speed * (1 - steer_factor/2))  # Slightly increase right speed
        else:  # Turning right
            # For sharp right turns: speed up left track, slow/reverse right track  
            left_speed = int(base_speed * (1 - steer_factor/2))   # Slightly increase left speed
            right_speed = int(base_speed * (1 + steer_factor))    # Reduce/reverse right speed
        
        # Apply speeds to motors
        if self.is_device_available(self.left_motor_name):
            self.safe_device_operation(self.left_motor_name, "run", left_speed)
        
        if self.is_device_available(self.right_motor_name):
            self.safe_device_operation(self.right_motor_name, "run", right_speed)
    
    def stop(self):
        """
        Stop all track movement immediately.
        """
        if self.is_device_available(self.left_motor_name):
            self.safe_device_operation(self.left_motor_name, "stop")
        
        if self.is_device_available(self.right_motor_name):
            self.safe_device_operation(self.right_motor_name, "stop")
    
    def drift_left(self, speed):
        """
        Perform a left drift by running tracks in opposite directions.
        
        Args:
            speed: Speed for the drift maneuver
        """
        validated_speed = self.validate_speed(speed, max_speed=self.drift_speed)
        
        # Left drift: left track backward, right track forward
        if self.is_device_available(self.left_motor_name):
            self.safe_device_operation(self.left_motor_name, "run", validated_speed)
        
        if self.is_device_available(self.right_motor_name):
            self.safe_device_operation(self.right_motor_name, "run", -validated_speed)
    
    def drift_right(self, speed):
        """
        Perform a right drift by running tracks in opposite directions.
        
        Args:
            speed: Speed for the drift maneuver
        """
        validated_speed = self.validate_speed(speed, max_speed=self.drift_speed)
        
        # Right drift: left track forward, right track backward
        if self.is_device_available(self.left_motor_name):
            self.safe_device_operation(self.left_motor_name, "run", -validated_speed)
        
        if self.is_device_available(self.right_motor_name):
            self.safe_device_operation(self.right_motor_name, "run", validated_speed)
    
    def get_status(self):
        """
        Get current status of the tank drive system.
        
        Returns:
            dict: Dictionary containing status information
        """
        status = {
            "initialized": self._is_initialized,
            "devices": {
                "left_motor": self.is_device_available(self.left_motor_name),
                "right_motor": self.is_device_available(self.right_motor_name)
            },
            "drive_system_type": "tank_drive",
            "available_operations": []
        }
        
        # Determine available operations based on device availability
        if status["devices"]["left_motor"] and status["devices"]["right_motor"]:
            status["available_operations"].extend([
                "move_forward", "move_backward", "turn_left", "turn_right",
                "drift_left", "drift_right", "differential_steering"
            ])
        elif status["devices"]["left_motor"] or status["devices"]["right_motor"]:
            status["available_operations"].append("limited_movement")
        
        return status
    
    def pivot_left(self, speed, duration=None):
        """
        Pivot left in place by running tracks in opposite directions.
        
        Args:
            speed: Pivot speed
            duration: Optional duration in seconds
        """
        validated_speed = self.validate_speed(speed)
        
        # Pivot left: left track backward, right track forward at same speed
        if self.is_device_available(self.left_motor_name):
            self.safe_device_operation(self.left_motor_name, "run", validated_speed)
        
        if self.is_device_available(self.right_motor_name):
            self.safe_device_operation(self.right_motor_name, "run", -validated_speed)
        
        if duration:
            sleep(duration)
            self.stop()
    
    def pivot_right(self, speed, duration=None):
        """
        Pivot right in place by running tracks in opposite directions.
        
        Args:
            speed: Pivot speed
            duration: Optional duration in seconds
        """
        validated_speed = self.validate_speed(speed)
        
        # Pivot right: left track forward, right track backward at same speed
        if self.is_device_available(self.left_motor_name):
            self.safe_device_operation(self.left_motor_name, "run", -validated_speed)
        
        if self.is_device_available(self.right_motor_name):
            self.safe_device_operation(self.right_motor_name, "run", validated_speed)
        
        if duration:
            sleep(duration)
            self.stop()
    
    def set_motor_speeds(self, left_speed, right_speed):
        """
        Directly set individual motor speeds for advanced control.
        
        Args:
            left_speed: Speed for left track motor
            right_speed: Speed for right track motor
        """
        validated_left_speed = self.validate_speed(left_speed)
        validated_right_speed = self.validate_speed(right_speed)
        
        if self.is_device_available(self.left_motor_name):
            self.safe_device_operation(self.left_motor_name, "run", validated_left_speed)
        
        if self.is_device_available(self.right_motor_name):
            self.safe_device_operation(self.right_motor_name, "run", validated_right_speed)
    
    def joystick_control(self, forward_speed, turn_speed):
        """
        Control robot using joystick-style input where Y-axis controls forward/backward
        speed and X-axis controls turning speed.
        
        Args:
            forward_speed: Forward/backward speed (-1000 to 1000)
                          Positive = forward, Negative = backward
            turn_speed: Turning speed (-1000 to 1000)  
                       Positive = turn right, Negative = turn left
        """
        # Validate inputs
        forward_speed = self.validate_speed(forward_speed)
        turn_speed = self.validate_speed(turn_speed)
        
        # If both inputs are zero, stop the robot immediately and aggressively
        if forward_speed == 0 and turn_speed == 0:
            self.stop()
            # Force hard stop by setting motor speeds to 0 explicitly
            if self.is_device_available(self.left_motor_name):
                self.safe_device_operation(self.left_motor_name, "run", 0)
            if self.is_device_available(self.right_motor_name): 
                self.safe_device_operation(self.right_motor_name, "run", 0)
            return
        
        # Calculate base motor speeds from forward input
        # Negative values for forward movement (motor convention)
        base_left = -forward_speed
        base_right = -forward_speed
        
        # Add turning component
        # For tank drive: turn by making one side faster/slower
        turn_factor = turn_speed * 0.8  # Scale turning for better control
        
        left_speed = base_left - turn_factor   # Left motor: subtract for right turn
        right_speed = base_right + turn_factor # Right motor: add for right turn
        
        # Debug output removed for better performance
        
        # Apply motor speeds
        self.set_motor_speeds(left_speed, right_speed)
    
    def set_default_speeds(self, drive_speed=None, turn_speed=None, drift_speed=None):
        """
        Set default speeds for various operations.
        
        Args:
            drive_speed: Default speed for forward/backward movement
            turn_speed: Default speed for turning operations
            drift_speed: Default speed for drift operations
        """
        if drive_speed is not None:
            self.default_drive_speed = self.validate_speed(drive_speed)
        
        if turn_speed is not None:
            self.default_turn_speed = self.validate_speed(turn_speed)
        
        if drift_speed is not None:
            self.drift_speed = self.validate_speed(drift_speed)
    
    def set_steering_sensitivity(self, sensitivity):
        """
        Set the steering sensitivity for joystick control.
        
        Args:
            sensitivity: Steering sensitivity multiplier 
                        (1.0 = normal, 2.0 = aggressive, 0.5 = gentle)
        """
        self.steering_sensitivity = max(0.1, min(5.0, sensitivity)) 