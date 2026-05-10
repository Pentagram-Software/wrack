from error_reporting import report_device_error, report_exception
import os  # type: ignore
import time
import threading


# Exceptions that indicate a device has disconnected
# These are typically I/O-related errors that occur when the device is physically
# unplugged or communication with the device fails
CONNECTIVITY_EXCEPTIONS = (
    OSError,
    IOError,
    ConnectionError,
    TimeoutError,
)


def _is_connectivity_error(exception):
    """
    Determine if an exception is a connectivity-related error.
    
    Args:
        exception: The exception to check
        
    Returns:
        bool: True if the exception indicates a device connectivity problem,
              False if it's likely a programming error or other non-connectivity issue
    """
    # Direct match against known connectivity exception types
    if isinstance(exception, CONNECTIVITY_EXCEPTIONS):
        return True
    
    # Check for EV3-specific connection errors (may have custom exception types)
    # These are identified by common substrings in the exception message
    exception_msg = str(exception).lower()
    connectivity_keywords = [
        'disconnected',
        'connection',
        'no response',
        'timed out',
        'device not found',
        'port not available',
        'communication',
        'i/o error',
        'errno',
    ]
    
    for keyword in connectivity_keywords:
        if keyword in exception_msg:
            return True
    
    return False


class DeviceManager:
    """
    Manages device initialization and provides safe access to devices.
    Handles missing devices gracefully by providing dummy objects.
    Includes battery monitoring capabilities.
    """
    
    def __init__(self, ev3_brick=None):
        self.devices = {}
        self.available_devices = []
        self.missing_devices = []
        self.device_ports = {}  # Store port information (string) for each device
        self.device_types = {}  # Store device type classes for reconnection
        self._raw_ports = {}  # Store actual port objects for reconnection
        self.ev3_brick = ev3_brick  # Store reference to EV3Brick for battery monitoring
        
        # Port monitoring for disconnect/reconnect handling
        self._port_monitor = None
        self._device_lock = threading.Lock()  # Thread-safe device access
        
        # Track disconnected devices that should ignore commands
        self._disconnected_devices = set()
        
    def try_init_device(self, device_type, port, device_name):
        """
        Try to initialize a device on a specific port.
        Returns the device if successful, None if failed.
        
        Note: The port monitor registration is done outside of _device_lock
        to prevent lock-order inversion with PortMonitor._lock.
        """
        try:
            device = device_type(port)
            
            # Update device manager state under lock
            with self._device_lock:
                self.devices[device_name] = device
                self.available_devices.append(device_name)
                self.device_ports[device_name] = str(port)  # Store port info (string)
                self._raw_ports[device_name] = port  # Store actual port object for reconnection
                self.device_types[device_name] = device_type  # Store type for reconnection
                
                # Remove from disconnected set if it was there
                self._disconnected_devices.discard(device_name)
                
                # Capture port_monitor reference while holding the lock
                port_monitor = self._port_monitor
            
            # Register with port monitor OUTSIDE of _device_lock to avoid lock-order inversion
            # (PortMonitor callbacks acquire _device_lock while holding _lock)
            if port_monitor:
                port_monitor.register_device(device_name, device_type, port)
            
            if __debug__:
                print("✓ {} initialized on {}".format(device_name, port))
            return device
        except Exception as e:
            with self._device_lock:
                self.devices[device_name] = None
                self.missing_devices.append(device_name)
                self.device_ports[device_name] = str(port)  # Store port even if failed
                self._raw_ports[device_name] = port  # Store actual port object for reconnection
                self.device_types[device_name] = device_type  # Store type for reconnection
            if __debug__:
                report_device_error(device_name, "initialization", e, port)
                print("✗ {} not found on {}: {}".format(device_name, port, e))
            return None
    
    def init_device_with_fallback(self, device_type, port, device_name, fallback_device=None):
        """
        Initialize a device with an optional fallback device.
        If the main device fails, it will try to use the fallback device.
        """
        device = self.try_init_device(device_type, port, device_name)
        if device is None and fallback_device is not None:
            if __debug__:
                print("Using fallback device for {}".format(device_name))
            self.devices[device_name] = fallback_device
            self.available_devices.append(device_name)
            return fallback_device
        return device
    
    def get_device(self, device_name):
        """
        Get a device safely. Returns the device or None if not available.
        """
        return self.devices.get(device_name)
    
    def is_device_available(self, device_name):
        """
        Check if a device is available and not disconnected.
        
        A device is considered unavailable if:
        - It doesn't exist in the devices dictionary
        - It exists but is None (failed to initialize)
        - It's in the _disconnected_devices set (detected disconnect)
        """
        with self._device_lock:
            # Device is unavailable if it's in the disconnected set
            if device_name in self._disconnected_devices:
                return False
        
        # Also check if device exists and is not None
        return self.devices.get(device_name) is not None
    
    def are_devices_available(self, device_names):
        """
        Check if multiple devices are available.
        Returns True only if ALL specified devices are available.
        """
        return all(self.is_device_available(name) for name in device_names)
    
    def safe_device_call(self, device_name, method_name, *args, **kwargs):
        """
        Safely call a method on a device if it exists.
        Handles device disconnection gracefully by catching connectivity exceptions.
        
        Non-connectivity exceptions (TypeError, ValueError, etc.) are re-raised
        to allow debugging of programming errors.
        """
        # Check if device is marked as disconnected
        with self._device_lock:
            if device_name in self._disconnected_devices:
                if __debug__:
                    print("Device {} is disconnected, ignoring {}".format(device_name, method_name))
                return None
        
        device = self.get_device(device_name)
        if device is not None:
            method = getattr(device, method_name, None)
            if method:
                try:
                    return method(*args, **kwargs)
                except Exception as e:
                    # Only mark as disconnected for connectivity-related exceptions
                    if _is_connectivity_error(e):
                        self._handle_device_error(device_name, method_name, e)
                        return None
                    else:
                        # Re-raise non-connectivity exceptions (programming errors, etc.)
                        # so they can be debugged properly
                        if __debug__:
                            report_device_error(device_name, method_name, e, "Non-connectivity error")
                        raise
        return None
    
    def _handle_device_error(self, device_name, operation, exception):
        """
        Handle a connectivity-related device error by marking the device as disconnected.
        
        This method should only be called for connectivity-related exceptions
        (OSError, IOError, etc.). Non-connectivity exceptions should be handled
        differently to avoid permanently disabling devices due to programming errors.
        
        Args:
            device_name: Name of the device that errored
            operation: Name of the operation that failed
            exception: The exception that was raised (should be a connectivity error)
        """
        # Double-check this is actually a connectivity error
        # This serves as a safety net in case this method is called incorrectly
        if not _is_connectivity_error(exception):
            if __debug__:
                report_device_error(device_name, operation, exception, 
                    "Non-connectivity error - not marking as disconnected")
            return
        
        if __debug__:
            report_device_error(device_name, operation, exception, "Device disconnected")
        
        # Mark device as disconnected to prevent further command attempts
        with self._device_lock:
            self._disconnected_devices.add(device_name)
        
        if __debug__:
            print("Device {} marked as disconnected after connectivity error in {}".format(device_name, operation))
    
    def safe_device_operation(self, device_name, operation_name, operation_func, *args, **kwargs):
        """
        Safely perform an operation on a device with custom error handling.
        
        Args:
            device_name: Name of the device
            operation_name: Name of the operation for logging
            operation_func: Function to call on the device
            *args, **kwargs: Arguments to pass to the operation function
        """
        device = self.get_device(device_name)
        if device is not None:
            try:
                return operation_func(device, *args, **kwargs)
            except Exception as e:
                if __debug__:
                    func_name = operation_func.__name__ if hasattr(operation_func, '__name__') else str(operation_func)
                    report_device_error(device_name, operation_name, e, "Function: {}".format(func_name))
                return None
        else:
            if __debug__:
                print("Cannot perform {} - {} not available".format(operation_name, device_name))
            return None
    
    def print_device_status(self):
        """
        Print the status of all devices.
        """
        print("\n=== Device Status ===")
        if self.available_devices:
            print("Available devices:")
            for device in self.available_devices:
                print("  ✓ {}".format(device))
        
        if self.missing_devices:
            print("Missing devices:")
            for device in self.missing_devices:
                print("  ✗ {}".format(device))
        print("==================\n")
    
    def get_device_summary(self):
        """
        Get a summary of device status.
        """
        total_devices = len(self.devices)
        available_count = len(self.available_devices)
        missing_count = len(self.missing_devices)
        
        return {
            'total': total_devices,
            'available': available_count,
            'missing': missing_count,
            'available_devices': self.available_devices.copy(),
            'missing_devices': self.missing_devices.copy()
        }
    
    def get_sensor_readings(self):
        """
        Get current readings from all available sensors.
        Returns a dictionary with sensor names and their current values.
        """
        readings = {}
        
        # Ultrasonic sensor - distance in mm
        if self.is_device_available("us_sensor"):
            try:
                us = self.get_device("us_sensor")
                distance = us.distance()
                readings["ultrasonic"] = {
                    "available": True,
                    "port": self.device_ports.get("us_sensor", "unknown"),
                    "distance_mm": distance,
                    "distance_cm": round(distance / 10.0, 1) if distance else None
                }
            except Exception as e:
                readings["ultrasonic"] = {
                    "available": True,
                    "port": self.device_ports.get("us_sensor", "unknown"),
                    "error": str(e)
                }
        else:
            readings["ultrasonic"] = {
                "available": False,
                "port": self.device_ports.get("us_sensor", "unknown")
            }
        
        # Gyro sensor - angle and speed
        if self.is_device_available("gyro_sensor"):
            try:
                gyro = self.get_device("gyro_sensor")
                angle = gyro.angle()
                speed = gyro.speed()
                readings["gyro"] = {
                    "available": True,
                    "port": self.device_ports.get("gyro_sensor", "unknown"),
                    "angle_degrees": angle,
                    "speed_deg_per_sec": speed
                }
            except Exception as e:
                readings["gyro"] = {
                    "available": True,
                    "port": self.device_ports.get("gyro_sensor", "unknown"),
                    "error": str(e)
                }
        else:
            readings["gyro"] = {
                "available": False,
                "port": self.device_ports.get("gyro_sensor", "unknown")
            }
        
        # Pixy camera (if available)
        if self.is_device_available("pixy_camera"):
            try:
                pixy = self.get_device("pixy_camera")
                # Note: Pixy camera readings would need specific implementation
                readings["pixy_camera"] = {
                    "available": True,
                    "port": self.device_ports.get("pixy_camera", "unknown"),
                    "note": "Camera active"
                }
            except Exception as e:
                readings["pixy_camera"] = {
                    "available": True,
                    "port": self.device_ports.get("pixy_camera", "unknown"),
                    "error": str(e)
                }
        else:
            readings["pixy_camera"] = {
                "available": False,
                "port": self.device_ports.get("pixy_camera", "unknown")
            }
        
        return readings
    
    def get_motor_status(self):
        """
        Get status of all motors (position, speed, stalled state).
        Returns a dictionary with motor names and their current state.
        """
        motor_status = {}
        
        motor_names = ["drive_L_motor", "drive_R_motor", "turret_motor"]
        
        for motor_name in motor_names:
            if self.is_device_available(motor_name):
                try:
                    motor = self.get_device(motor_name)
                    angle = motor.angle()
                    speed = motor.speed()
                    stalled = motor.stalled()
                    
                    motor_status[motor_name] = {
                        "available": True,
                        "port": self.device_ports.get(motor_name, "unknown"),
                        "angle_degrees": angle,
                        "speed_deg_per_sec": speed,
                        "stalled": stalled
                    }
                except Exception as e:
                    motor_status[motor_name] = {
                        "available": True,
                        "port": self.device_ports.get(motor_name, "unknown"),
                        "error": str(e)
                    }
            else:
                motor_status[motor_name] = {
                    "available": False,
                    "port": self.device_ports.get(motor_name, "unknown")
                }
        
        return motor_status
    
    def _read_proc_stat_cpu(self):
        """
        Internal helper to read aggregate CPU times from /proc/stat.
        Returns a tuple (idle, total) or None if unavailable.
        """
        try:
            # /proc/stat is available on ev3dev (Linux). Not present on Pybricks firmware.
            with open('/proc/stat', 'r') as f:
                first_line = f.readline()
            if not first_line or not first_line.startswith('cpu '):
                return None
            parts = first_line.split()
            # parts[0] == 'cpu'; subsequent numeric fields are jiffies
            # Common fields: user nice system idle iowait irq softirq steal guest guest_nice
            values = []
            for p in parts[1:]:
                try:
                    values.append(int(p))
                except Exception:
                    break
            if not values:
                return None
            idle = 0
            total = 0
            # idle = idle + iowait (indexes 3 and 4 if present)
            if len(values) >= 4:
                idle += values[3]
            if len(values) >= 5:
                idle += values[4]
            # non-idle sum of the remaining known fields
            non_idle_idxs = [0, 1, 2, 5, 6]  # user, nice, system, irq, softirq
            if len(values) >= 8:
                non_idle_idxs.append(7)  # steal
            non_idle = 0
            for idx in non_idle_idxs:
                if idx < len(values):
                    non_idle += values[idx]
            total = idle + non_idle
            return (idle, total)
        except Exception:
            return None

    def get_cpu_usage(self, interval_ms=200):
        """
        Best-effort CPU usage percent over a short sampling window.
        Returns an integer 0-100, or None if unsupported on this firmware.

        On ev3dev (Linux), reads /proc/stat twice and computes usage.
        On Pybricks MicroPython firmware, this will return None.
        """
        start = self._read_proc_stat_cpu()
        if start is None:
            # Not supported on this platform
            return None
        # Sleep for the sampling interval
        try:
            time.sleep(max(0.0, (interval_ms or 0) / 1000.0))
        except Exception:
            # Fallback minimal delay
            time.sleep(0.2)
        end = self._read_proc_stat_cpu()
        if end is None:
            return None
        idle1, total1 = start
        idle2, total2 = end
        total_delta = total2 - total1
        idle_delta = idle2 - idle1
        if total_delta <= 0:
            return None
        usage = 100.0 * (1.0 - (float(idle_delta) / float(total_delta)))
        # Clamp and return integer percentage
        if usage < 0:
            usage = 0.0
        if usage > 100:
            usage = 100.0
        return int(usage)
    
    def get_battery_voltage(self):
        """
        Get the current battery voltage in millivolts (mV).
        
        Returns:
            int: Battery voltage in mV, or None if EV3Brick not available
        """
        if self.ev3_brick is None:
            if __debug__:
                print("EV3Brick not available for battery voltage reading")
            return None
        
        try:
            return self.ev3_brick.battery.voltage()
        except Exception as e:
            if __debug__:
                report_exception("battery_voltage", e)
            return None
    
    def get_battery_current(self):
        """
        Get the current battery current in milliamps (mA).
        
        Returns:
            int: Battery current in mA, or None if EV3Brick not available
        """
        if self.ev3_brick is None:
            if __debug__:
                print("EV3Brick not available for battery current reading")
            return None
        
        try:
            return self.ev3_brick.battery.current()
        except Exception as e:
            if __debug__:
                report_exception("battery_current", e)
            return None
    
    def get_battery_percentage(self, battery_type="rechargeable"):
        """
        Calculate battery percentage based on voltage.
        
        Args:
            battery_type: Type of battery ("rechargeable" or "alkaline")
        
        Returns:
            int: Battery percentage (0-100), or None if voltage unavailable
        """
        voltage = self.get_battery_voltage()
        if voltage is None:
            return None
        
        # Define voltage ranges based on battery type
        if battery_type.lower() == "alkaline":
            voltage_full = 10000  # 10V for 6x AA alkaline batteries
            voltage_empty = 6500   # 6.5V minimum
        else:  # rechargeable (default)
            voltage_full = 8000   # 8V for rechargeable battery
            voltage_empty = 6000   # 6V minimum
        
        # Calculate percentage
        voltage_range = voltage_full - voltage_empty
        voltage_above_empty = max(0, voltage - voltage_empty)
        percentage = min(100, int((voltage_above_empty / voltage_range) * 100))
        
        return percentage
    
    def get_battery_info(self, battery_type="rechargeable"):
        """
        Get comprehensive battery information.
        
        Args:
            battery_type: Type of battery ("rechargeable" or "alkaline")
        
        Returns:
            dict: Battery information including voltage, current, and percentage
        """
        voltage = self.get_battery_voltage()
        current = self.get_battery_current()
        percentage = self.get_battery_percentage(battery_type)
        
        return {
            "voltage_mv": voltage,
            "current_ma": current,
            "percentage": percentage,
            "battery_type": battery_type,
            "available": voltage is not None
        }

    def get_system_info(self):
        """
        Get system information using command line tools.
        Returns a dictionary with hostname, IP addresses, and kernel info.
        """
        system_info = {
            'hostname': None,
            'ip_addresses': [],
            'kernel': None,
            'operating_system': None,
            'architecture': None,
            'static_hostname': None
        }
        
        # Get IP addresses using 'hostname -I'
        try:
            ip_output = os.popen("hostname -I").read().strip()
            if ip_output:
                system_info['ip_addresses'] = ip_output.split()
        except Exception as e:
            system_info['ip_addresses'] = ["Error: " + str(e)]
        
        # Get hostname, kernel and other info using 'hostnamectl'
        try:
            hostnamectl_output = os.popen("hostnamectl").read()
            for line in hostnamectl_output.split('\n'):
                line = line.strip()
                if 'Static hostname:' in line:
                    system_info['static_hostname'] = line.split(':', 1)[1].strip()
                    if not system_info['hostname']:
                        system_info['hostname'] = system_info['static_hostname']
                elif 'Hostname:' in line and 'Static' not in line:
                    system_info['hostname'] = line.split(':', 1)[1].strip()
                elif 'Kernel:' in line:
                    system_info['kernel'] = line.split(':', 1)[1].strip()
                elif 'Operating System:' in line:
                    system_info['operating_system'] = line.split(':', 1)[1].strip()
                elif 'Architecture:' in line:
                    system_info['architecture'] = line.split(':', 1)[1].strip()
        except Exception as e:
            # Fallback to simple hostname command if hostnamectl fails
            try:
                system_info['hostname'] = os.popen("hostname").read().strip()
            except:
                system_info['hostname'] = "Error getting hostname"
        
        # If hostname still not set, try socket method
        if not system_info['hostname']:
            try:
                system_info['hostname'] = socket.gethostname()
            except:
                system_info['hostname'] = "Unknown"
        
        return system_info
    
    def enable_port_monitoring(self, check_interval=1.0):
        """
        Enable port monitoring for device disconnect/reconnect detection.
        
        Args:
            check_interval: Time in seconds between connectivity checks (default: 1.0)
            
        Note: Device registration is done outside of _device_lock to prevent
        lock-order inversion with PortMonitor._lock.
        """
        # Import here to avoid circular imports
        from .port_monitor import PortMonitor
        
        if self._port_monitor is not None:
            if __debug__:
                print("Port monitoring already enabled")
            return
        
        self._port_monitor = PortMonitor(self, check_interval)
        
        # Collect device info under lock, but register outside of lock
        # to prevent lock-order inversion (PortMonitor callbacks acquire _device_lock)
        devices_to_register = []
        with self._device_lock:
            # Combine available and missing devices
            all_known_devices = set(self.available_devices) | set(self.missing_devices)
            
            for device_name in all_known_devices:
                if device_name in self.device_types and device_name in self._raw_ports:
                    device_type = self.device_types[device_name]
                    port = self._raw_ports[device_name]  # Use actual port object
                    devices_to_register.append((device_name, device_type, port))
        
        # Register devices OUTSIDE of _device_lock
        for device_name, device_type, port in devices_to_register:
            self._port_monitor.register_device(device_name, device_type, port)
        
        # Set up callbacks for disconnect/reconnect events
        self._port_monitor.on_disconnect(self._on_device_disconnect)
        self._port_monitor.on_reconnect(self._on_device_reconnect)
        
        # Start the monitoring thread
        self._port_monitor.start()
        
        if __debug__:
            print("Port monitoring enabled with {}s check interval".format(check_interval))
    
    def disable_port_monitoring(self):
        """Disable port monitoring and stop the background thread."""
        if self._port_monitor is not None:
            self._port_monitor.stop()
            self._port_monitor = None
            
            if __debug__:
                print("Port monitoring disabled")
    
    def _on_device_disconnect(self, device_name, status):
        """
        Callback when a device disconnects.
        
        Note: We intentionally do NOT set devices[device_name] = None here.
        Keeping the stale device reference allows the PortMonitor to:
        1. Use the reference for health checks (which will fail and detect disconnection)
        2. Attempt automatic reconnection by creating a new device instance
        
        The is_device_available() method checks _disconnected_devices to properly
        report unavailability, decoupling availability from the devices map value.
        
        Args:
            device_name: Name of the disconnected device
            status: Status dictionary with device info
        """
        with self._device_lock:
            self._disconnected_devices.add(device_name)
            
            # Note: We do NOT set devices[device_name] = None here.
            # The stale reference is kept for reconnection detection.
            # is_device_available() checks _disconnected_devices for availability.
            
            # Move from available to missing
            if device_name in self.available_devices:
                self.available_devices.remove(device_name)
            if device_name not in self.missing_devices:
                self.missing_devices.append(device_name)
        
        if __debug__:
            print("DeviceManager: {} disconnected from {}".format(
                device_name, status.get('port', 'unknown')))
    
    def _on_device_reconnect(self, device_name, status):
        """
        Callback when a device reconnects.
        
        Args:
            device_name: Name of the reconnected device
            status: Status dictionary with device info
        """
        with self._device_lock:
            self._disconnected_devices.discard(device_name)
            
            # Move from missing to available
            if device_name in self.missing_devices:
                self.missing_devices.remove(device_name)
            if device_name not in self.available_devices:
                self.available_devices.append(device_name)
        
        if __debug__:
            print("DeviceManager: {} reconnected on {}".format(
                device_name, status.get('port', 'unknown')))
    
    def is_device_disconnected(self, device_name):
        """
        Check if a device is currently marked as disconnected.
        
        Args:
            device_name: Name of the device to check
            
        Returns:
            bool: True if device is disconnected, False otherwise
        """
        with self._device_lock:
            return device_name in self._disconnected_devices
    
    def get_port_monitor_status(self):
        """
        Get the status of all monitored devices from the port monitor.
        
        Returns:
            dict: Dictionary of device statuses, or None if monitoring is disabled
        """
        if self._port_monitor is None:
            return None
        return self._port_monitor.get_all_device_statuses()
    
    def cleanup(self):
        """
        Clean up resources, including stopping port monitoring.
        Should be called when shutting down the robot.
        """
        # Stop port monitoring
        self.disable_port_monitoring()
        
        # Stop all motors safely
        for device_name in list(self.available_devices):
            device = self.get_device(device_name)
            if device is not None and hasattr(device, 'stop'):
                try:
                    device.stop()
                except Exception as e:
                    if __debug__:
                        report_device_error(device_name, "cleanup_stop", e, "")
        
        if __debug__:
            print("DeviceManager cleanup complete")