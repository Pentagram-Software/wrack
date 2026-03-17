from error_reporting import report_device_error, report_exception
import os  # type: ignore
import time

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
        self.device_ports = {}  # Store port information for each device
        self.ev3_brick = ev3_brick  # Store reference to EV3Brick for battery monitoring
        
    def try_init_device(self, device_type, port, device_name):
        """
        Try to initialize a device on a specific port.
        Returns the device if successful, None if failed.
        """
        try:
            device = device_type(port)
            self.devices[device_name] = device
            self.available_devices.append(device_name)
            self.device_ports[device_name] = str(port)  # Store port info
            if __debug__:
                print("✓ {} initialized on {}".format(device_name, port))
            return device
        except Exception as e:
            self.devices[device_name] = None
            self.missing_devices.append(device_name)
            self.device_ports[device_name] = str(port)  # Store port even if failed
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
        Check if a device is available.
        """
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
        """
        device = self.get_device(device_name)
        if device is not None:
            method = getattr(device, method_name, None)
            if method:
                return method(*args, **kwargs)
        return None
    
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