from .drive_system import DriveSystem
from time import sleep


class CarDriveSystem(DriveSystem):
    """
    Car-style drive system implementation with steering motor and dual drive motors.
    
    This implementation is based on the existing drive control logic from main.py
    and provides car-like driving with separate steering and drive controls.
    """
    
    def __init__(self, device_manager=None):
        """
        Initialize the car drive system.
        
        Args:
            device_manager: DeviceManager instance for safe device operations
        """
        super().__init__(device_manager)
        self.steer_motor_name = "steer_motor"
        self.drive_L_motor_name = "drive_L_motor"
        self.drive_R_motor_name = "drive_R_motor"
        
        # Default speeds
        self.default_drive_speed = 1000
        self.default_steer_speed = 1000
        self.drift_speed = 1000
    
    def initialize(self):
        """
        Initialize the car drive system hardware.
        
        Returns:
            bool: True if initialization was successful, False otherwise
        """
        required_devices = [
            self.steer_motor_name,
            self.drive_L_motor_name, 
            self.drive_R_motor_name
        ]
        
        available_devices = []
        for device in required_devices:
            if self.is_device_available(device):
                available_devices.append(device)
        
        # Consider system initialized if at least steering is available
        self._is_initialized = self.is_device_available(self.steer_motor_name)
        
        if __debug__:
            print("CarDriveSystem initialized: {}".format(self._is_initialized))
            print("Available devices: {}".format(available_devices))
        
        return self._is_initialized
    
    def move_forward(self, speed, duration=None):
        """
        Move the robot forward using both drive motors.
        
        Args:
            speed: Speed value (-1000 to 1000)
            duration: Optional duration in seconds
        """
        validated_speed = self.validate_speed(speed)
        
        if self.is_device_available(self.drive_L_motor_name):
            self.safe_device_operation(self.drive_L_motor_name, "run", -validated_speed)
        
        if self.is_device_available(self.drive_R_motor_name):
            self.safe_device_operation(self.drive_R_motor_name, "run", -validated_speed)
        
        if duration:
            sleep(duration)
            self.stop_drive_motors()
    
    def move_backward(self, speed, duration=None):
        """
        Move the robot backward using both drive motors.
        
        Args:
            speed: Speed value (-1000 to 1000)
            duration: Optional duration in seconds
        """
        validated_speed = self.validate_speed(speed)
        
        if self.is_device_available(self.drive_L_motor_name):
            self.safe_device_operation(self.drive_L_motor_name, "run", validated_speed)
        
        if self.is_device_available(self.drive_R_motor_name):
            self.safe_device_operation(self.drive_R_motor_name, "run", validated_speed)
        
        if duration:
            sleep(duration)
            self.stop_drive_motors()
    
    def turn_left(self, speed, duration=None):
        """
        Turn the robot left by steering the front wheels.
        
        Args:
            speed: Steering speed (-1000 to 1000)
            duration: Optional duration in seconds
        """
        validated_speed = self.validate_speed(speed)
        
        if self.is_device_available(self.steer_motor_name):
            self.safe_device_operation(self.steer_motor_name, "run", -validated_speed)
        
        if duration:
            sleep(duration)
            self.stop_steering()
    
    def turn_right(self, speed, duration=None):
        """
        Turn the robot right by steering the front wheels.
        
        Args:
            speed: Steering speed (-1000 to 1000)
            duration: Optional duration in seconds
        """
        validated_speed = self.validate_speed(speed)
        
        if self.is_device_available(self.steer_motor_name):
            self.safe_device_operation(self.steer_motor_name, "run", validated_speed)
        
        if duration:
            sleep(duration)
            self.stop_steering()
    
    def move_with_steering(self, drive_speed, steer_angle):
        """
        Move with simultaneous drive and steering control.
        Based on the move() function from main.py.
        
        Args:
            drive_speed: Forward/backward speed for drive motors
            steer_angle: Steering angle/speed for steering motor
        """
        validated_drive_speed = self.validate_speed(drive_speed)
        validated_steer_speed = self.validate_speed(steer_angle)
        
        # Apply steering (based on original move function logic)
        if self.is_device_available(self.steer_motor_name):
            # Original logic: steer_motor.run(value.l_left*2)
            self.safe_device_operation(self.steer_motor_name, "run", validated_steer_speed * 2)
        
        # Apply drive speed if significant enough
        if abs(validated_drive_speed) > 10:  # Minimum movement threshold
            if self.is_device_available(self.drive_L_motor_name):
                self.safe_device_operation(self.drive_L_motor_name, "run", -validated_drive_speed)
            
            if self.is_device_available(self.drive_R_motor_name):
                self.safe_device_operation(self.drive_R_motor_name, "run", -validated_drive_speed)
        else:
            self.stop_drive_motors()
    
    def stop(self):
        """
        Stop all drive system movement immediately.
        Based on driftStop() function from main.py.
        """
        self.stop_steering()
        self.stop_drive_motors()
    
    def drift_left(self, speed: int) -> None:
        """
        Perform a left drift maneuver.
        Based on driftLeft() function from main.py.
        
        Args:
            speed: Speed for the drift maneuver
        """
        validated_speed = self.validate_speed(speed, max_speed=self.drift_speed)
        
        if self.is_device_available(self.steer_motor_name):
            self.safe_device_operation(self.steer_motor_name, "run", -validated_speed)
        
        if self.is_device_available(self.drive_L_motor_name):
            self.safe_device_operation(self.drive_L_motor_name, "run", -validated_speed)
        
        if self.is_device_available(self.drive_R_motor_name):
            self.safe_device_operation(self.drive_R_motor_name, "run", validated_speed)
    
    def drift_right(self, speed: int) -> None:
        """
        Perform a right drift maneuver.
        Based on driftRight() function from main.py.
        
        Args:
            speed: Speed for the drift maneuver
        """
        validated_speed = self.validate_speed(speed, max_speed=self.drift_speed)
        
        if self.is_device_available(self.steer_motor_name):
            self.safe_device_operation(self.steer_motor_name, "run", validated_speed)
        
        if self.is_device_available(self.drive_L_motor_name):
            self.safe_device_operation(self.drive_L_motor_name, "run", validated_speed)
        
        if self.is_device_available(self.drive_R_motor_name):
            self.safe_device_operation(self.drive_R_motor_name, "run", -validated_speed)
    
    def get_status(self) -> dict:
        """
        Get current status of the drive system.
        
        Returns:
            dict: Dictionary containing status information
        """
        status = {
            "initialized": self._is_initialized,
            "devices": {
                "steer_motor": self.is_device_available(self.steer_motor_name),
                "drive_L_motor": self.is_device_available(self.drive_L_motor_name),
                "drive_R_motor": self.is_device_available(self.drive_R_motor_name)
            },
            "drive_system_type": "car_drive",
            "available_operations": []
        }
        
        # Determine available operations based on device availability
        if status["devices"]["steer_motor"]:
            status["available_operations"].extend(["steering", "turn_left", "turn_right"])
        
        if status["devices"]["drive_L_motor"] and status["devices"]["drive_R_motor"]:
            status["available_operations"].extend(["move_forward", "move_backward", "drift"])
        
        if all(status["devices"].values()):
            status["available_operations"].append("full_car_control")
        
        return status
    
    def stop_steering(self) -> None:
        """
        Stop only the steering motor.
        """
        if self.is_device_available(self.steer_motor_name):
            self.safe_device_operation(self.steer_motor_name, "stop")
    
    def stop_drive_motors(self) -> None:
        """
        Stop only the drive motors.
        """
        if self.is_device_available(self.drive_L_motor_name):
            self.safe_device_operation(self.drive_L_motor_name, "stop")
        
        if self.is_device_available(self.drive_R_motor_name):
            self.safe_device_operation(self.drive_R_motor_name, "stop")
    
    def set_drive_speed(self, speed: int) -> None:
        """
        Set the default drive speed for movement operations.
        
        Args:
            speed: New default speed (will be validated)
        """
        self.default_drive_speed = self.validate_speed(speed)
    
    def set_steer_speed(self, speed: int) -> None:
        """
        Set the default steering speed for turning operations.
        
        Args:
            speed: New default steering speed (will be validated)
        """
        self.default_steer_speed = self.validate_speed(speed) 