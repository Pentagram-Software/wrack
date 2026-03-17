class DriveSystem:
    """
    Base class for robot drive systems.
    
    This class defines the interface that all drive system implementations
    should follow. It provides a standardized way to control robot movement
    regardless of the specific drive mechanism (tank drive, mecanum, etc.).
    
    Note: This class serves as a template for drive system implementations.
    All methods should be overridden in child classes.
    """
    
    def __init__(self, device_manager=None):
        """
        Initialize the drive system.
        
        Args:
            device_manager: Optional DeviceManager instance for safe device operations
        """
        self.device_manager = device_manager
        self._is_initialized = False
    
    def initialize(self) -> bool:
        """
        Initialize the drive system hardware.
        
        Returns:
            bool: True if initialization was successful, False otherwise
            
        Note: This method should be overridden in child classes.
        """
        raise NotImplementedError("This method should be implemented in child classes")
    
    def move_forward(self, speed, duration=None):
        """
        Move the robot forward.
        
        Args:
            speed: Speed value (implementation-specific range)
            duration: Optional duration in seconds. If None, move until stopped
            
        Note: This method should be overridden in child classes.
        """
        raise NotImplementedError("This method should be implemented in child classes")
    
    def move_backward(self, speed, duration=None):
        """
        Move the robot backward.
        
        Args:
            speed: Speed value (implementation-specific range)
            duration: Optional duration in seconds. If None, move until stopped
            
        Note: This method should be overridden in child classes.
        """
        raise NotImplementedError("This method should be implemented in child classes")
    
    def turn_left(self, speed, duration=None):
        """
        Turn the robot left.
        
        Args:
            speed: Speed value (implementation-specific range)
            duration: Optional duration in seconds. If None, turn until stopped
            
        Note: This method should be overridden in child classes.
        """
        raise NotImplementedError("This method should be implemented in child classes")
    
    def turn_right(self, speed, duration=None):
        """
        Turn the robot right.
        
        Args:
            speed: Speed value (implementation-specific range)
            duration: Optional duration in seconds. If None, turn until stopped
            
        Note: This method should be overridden in child classes.
        """
        raise NotImplementedError("This method should be implemented in child classes")
    
    def move_with_steering(self, drive_speed, steer_angle):
        """
        Move with simultaneous drive and steering control.
        
        Args:
            drive_speed: Forward/backward speed
            steer_angle: Steering angle or turning speed
            
        Note: This method should be overridden in child classes.
        """
        raise NotImplementedError("This method should be implemented in child classes")
    
    def stop(self):
        """
        Stop all drive system movement immediately.
        
        Note: This method should be overridden in child classes.
        """
        raise NotImplementedError("This method should be implemented in child classes")
    
    def drift_left(self, speed):
        """
        Perform a left drift maneuver.
        
        Args:
            speed: Speed for the drift maneuver
            
        Note: This method should be overridden in child classes.
        """
        raise NotImplementedError("This method should be implemented in child classes")
    
    def drift_right(self, speed):
        """
        Perform a right drift maneuver.
        
        Args:
            speed: Speed for the drift maneuver
            
        Note: This method should be overridden in child classes.
        """
        raise NotImplementedError("This method should be implemented in child classes")
    
    def get_status(self):
        """
        Get current status of the drive system.
        
        Returns:
            dict: Dictionary containing status information
            
        Note: This method should be overridden in child classes.
        """
        raise NotImplementedError("This method should be implemented in child classes")
    
    def is_initialized(self):
        """
        Check if the drive system is properly initialized.
        
        Returns:
            bool: True if initialized, False otherwise
        """
        return self._is_initialized
    
    def validate_speed(self, speed, min_speed=-1000, max_speed=1000):
        """
        Validate and clamp speed values to acceptable range.
        
        Args:
            speed: Input speed value
            min_speed: Minimum allowed speed
            max_speed: Maximum allowed speed
            
        Returns:
            int: Clamped speed value
        """
        return max(min_speed, min(max_speed, speed))
    
    def safe_device_operation(self, device_name, operation_name, *args, **kwargs):
        """
        Safely perform an operation on a device through the device manager.
        
        Args:
            device_name: Name of the device
            operation_name: Name of the operation to perform
            *args: Positional arguments for the operation
            **kwargs: Keyword arguments for the operation
            
        Returns:
            Result of the operation or None if failed
        """
        if self.device_manager:
            return self.device_manager.safe_device_call(
                device_name, operation_name, *args, **kwargs
            )
        return None
    
    def is_device_available(self, device_name):
        """
        Check if a specific device is available.
        
        Args:
            device_name: Name of the device to check
            
        Returns:
            bool: True if device is available, False otherwise
        """
        if self.device_manager:
            return self.device_manager.is_device_available(device_name)
        return False 