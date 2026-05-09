#!/usr/bin/env pybricks-micropython

"""
Port Monitor for EV3 Device Disconnect/Reconnect Handling

This module provides a background thread that monitors the connectivity status
of devices connected to EV3 ports. It detects disconnections and reconnections,
allowing the system to gracefully handle device failures.
"""

import threading
import time
from error_reporting import report_device_error, report_exception


class PortMonitor:
    """
    Monitors EV3 port connectivity and handles device disconnect/reconnect events.
    
    This class runs a background thread that periodically checks the health of
    connected devices. When a device disconnects, it marks the device as unavailable
    and gracefully handles any commands sent to it. When a device reconnects,
    it re-enables the device for normal operation.
    """
    
    def __init__(self, device_manager, check_interval=1.0):
        """
        Initialize the PortMonitor.
        
        Args:
            device_manager: DeviceManager instance to monitor
            check_interval: Time in seconds between connectivity checks (default: 1.0)
        """
        self.device_manager = device_manager
        self.check_interval = check_interval
        
        self._running = False
        self._monitor_thread = None
        self._lock = threading.Lock()
        
        # Track device connectivity status
        # Key: device_name, Value: dict with 'connected', 'port', 'device_type', 'last_check'
        self._device_status = {}
        
        # Track original device references for reconnection
        # Key: device_name, Value: dict with 'device_type', 'port'
        self._device_registry = {}
        
        # Callbacks for disconnect/reconnect events
        self._on_disconnect_callbacks = []
        self._on_reconnect_callbacks = []
    
    def register_device(self, device_name, device_type, port):
        """
        Register a device for monitoring.
        
        Args:
            device_name: Name of the device (e.g., "drive_L_motor")
            device_type: Device class (e.g., Motor, UltrasonicSensor)
            port: Port the device is connected to
        """
        with self._lock:
            self._device_registry[device_name] = {
                'device_type': device_type,
                'port': port
            }
            
            # Initialize status based on current device manager state
            is_connected = self.device_manager.is_device_available(device_name)
            self._device_status[device_name] = {
                'connected': is_connected,
                'port': port,
                'device_type': device_type,
                'last_check': time.time(),
                'consecutive_failures': 0
            }
            
            if __debug__:
                print("PortMonitor: Registered {} on {} (connected: {})".format(
                    device_name, port, is_connected))
    
    def start(self):
        """Start the background monitoring thread."""
        if self._running:
            return
        
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        
        if __debug__:
            print("PortMonitor: Started monitoring thread")
    
    def stop(self):
        """Stop the background monitoring thread."""
        self._running = False
        
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)
        
        if __debug__:
            print("PortMonitor: Stopped monitoring thread")
    
    def _monitor_loop(self):
        """Main monitoring loop that runs in the background thread."""
        while self._running:
            try:
                self._check_all_devices()
            except Exception as e:
                if __debug__:
                    report_exception("port_monitor_loop", e)
            
            time.sleep(self.check_interval)
    
    def _check_all_devices(self):
        """Check connectivity status of all registered devices."""
        with self._lock:
            device_names = list(self._device_registry.keys())
        
        for device_name in device_names:
            self._check_device(device_name)
    
    def _check_device(self, device_name):
        """
        Check the connectivity status of a single device.
        
        Args:
            device_name: Name of the device to check
        """
        with self._lock:
            if device_name not in self._device_registry:
                return
            
            registry_info = self._device_registry[device_name]
            current_status = self._device_status.get(device_name, {})
            was_connected = current_status.get('connected', False)
        
        # Perform health check outside the lock to avoid blocking
        is_healthy = self._perform_health_check(device_name)
        
        with self._lock:
            current_status = self._device_status.get(device_name, {})
            was_connected = current_status.get('connected', False)
            
            if is_healthy:
                # Device is responding
                self._device_status[device_name]['consecutive_failures'] = 0
                
                if not was_connected:
                    # Device reconnected
                    self._handle_reconnect(device_name, registry_info)
            else:
                # Device not responding
                failures = self._device_status[device_name].get('consecutive_failures', 0) + 1
                self._device_status[device_name]['consecutive_failures'] = failures
                
                # Only mark as disconnected after 2 consecutive failures to avoid false positives
                if was_connected and failures >= 2:
                    self._handle_disconnect(device_name)
            
            self._device_status[device_name]['last_check'] = time.time()
    
    def _perform_health_check(self, device_name):
        """
        Perform a health check on a device to determine if it's still connected.
        
        If the device is None (e.g., after disconnect), this method will attempt
        to reinitialize it using the stored device_type and port from the registry.
        
        Args:
            device_name: Name of the device to check
            
        Returns:
            bool: True if device is healthy/connected, False otherwise
        """
        device = self.device_manager.get_device(device_name)
        
        if device is None:
            # Device is None - try to reinitialize it using stored registry info
            return self._try_reinitialize_device(device_name)
        
        try:
            # Try to read a property from the device
            # For motors, try to read the angle
            if hasattr(device, 'angle'):
                device.angle()
                return True
            
            # For sensors, try to read their primary value
            if hasattr(device, 'distance'):
                device.distance()
                return True
            
            if hasattr(device, 'color'):
                device.color()
                return True
            
            if hasattr(device, 'speed'):
                device.speed()
                return True
            
            if hasattr(device, 'pressed'):
                device.pressed()
                return True
            
            # If no known method, assume device is healthy if it exists
            return True
            
        except Exception as e:
            if __debug__:
                print("PortMonitor: Health check failed for {}: {}".format(device_name, e))
            return False
    
    def _try_reinitialize_device(self, device_name):
        """
        Attempt to reinitialize a device that is currently None.
        
        This is used to detect reconnection of a device that was previously
        disconnected (and had its reference set to None).
        
        Args:
            device_name: Name of the device to reinitialize
            
        Returns:
            bool: True if device was successfully reinitialized, False otherwise
        """
        with self._lock:
            if device_name not in self._device_registry:
                return False
            
            registry_info = self._device_registry[device_name]
            device_type = registry_info['device_type']
            port = registry_info['port']
        
        try:
            # Try to create a new device instance
            new_device = device_type(port)
            
            # If successful, update the device manager
            self.device_manager.devices[device_name] = new_device
            
            if __debug__:
                print("PortMonitor: Successfully reinitialized {} on {}".format(
                    device_name, port))
            
            return True
            
        except Exception as e:
            if __debug__:
                # Only log occasionally to avoid spam during reconnect attempts
                pass
            return False
    
    def _handle_disconnect(self, device_name):
        """
        Handle a device disconnection event.
        
        Args:
            device_name: Name of the disconnected device
        """
        self._device_status[device_name]['connected'] = False
        
        if __debug__:
            port = self._device_status[device_name].get('port', 'unknown')
            print("PortMonitor: Device {} disconnected from port {}".format(device_name, port))
        
        # Notify callbacks
        for callback in self._on_disconnect_callbacks:
            try:
                callback(device_name, self._device_status[device_name])
            except Exception as e:
                if __debug__:
                    report_exception("disconnect_callback", e)
    
    def _handle_reconnect(self, device_name, registry_info):
        """
        Handle a device reconnection event.
        
        Args:
            device_name: Name of the reconnected device
            registry_info: Registration info containing device_type and port
        """
        device_type = registry_info['device_type']
        port = registry_info['port']
        
        # Check if the current device in device_manager is already healthy
        # (it may have been replaced externally, e.g., by hot-plug detection)
        current_device = self.device_manager.get_device(device_name)
        device_is_healthy = False
        
        if current_device is not None:
            try:
                # Quick health check on current device
                if hasattr(current_device, 'angle'):
                    current_device.angle()
                    device_is_healthy = True
                elif hasattr(current_device, 'distance'):
                    current_device.distance()
                    device_is_healthy = True
                elif hasattr(current_device, 'speed'):
                    current_device.speed()
                    device_is_healthy = True
            except Exception:
                device_is_healthy = False
        
        if not device_is_healthy:
            # Try to reinitialize the device
            try:
                new_device = device_type(port)
                self.device_manager.devices[device_name] = new_device
            except Exception as e:
                if __debug__:
                    print("PortMonitor: Failed to reinitialize {} on {}: {}".format(
                        device_name, port, e))
                return
        
        # Update available/missing device lists
        if device_name in self.device_manager.missing_devices:
            self.device_manager.missing_devices.remove(device_name)
        if device_name not in self.device_manager.available_devices:
            self.device_manager.available_devices.append(device_name)
        
        self._device_status[device_name]['connected'] = True
        
        if __debug__:
            print("PortMonitor: Device {} reconnected on port {}".format(device_name, port))
        
        # Notify callbacks
        for callback in self._on_reconnect_callbacks:
            try:
                callback(device_name, self._device_status[device_name])
            except Exception as e:
                if __debug__:
                    report_exception("reconnect_callback", e)
    
    def is_device_connected(self, device_name):
        """
        Check if a device is currently connected.
        
        Args:
            device_name: Name of the device to check
            
        Returns:
            bool: True if device is connected, False otherwise
        """
        with self._lock:
            status = self._device_status.get(device_name, {})
            return status.get('connected', False)
    
    def get_device_status(self, device_name):
        """
        Get the full status of a device.
        
        Args:
            device_name: Name of the device
            
        Returns:
            dict: Device status including connected state, port, last check time
        """
        with self._lock:
            return self._device_status.get(device_name, {}).copy()
    
    def get_all_device_statuses(self):
        """
        Get the status of all monitored devices.
        
        Returns:
            dict: Dictionary of device names to their status
        """
        with self._lock:
            return {name: status.copy() for name, status in self._device_status.items()}
    
    def on_disconnect(self, callback):
        """
        Register a callback to be called when a device disconnects.
        
        Args:
            callback: Function to call with (device_name, status_dict) arguments
        """
        self._on_disconnect_callbacks.append(callback)
    
    def on_reconnect(self, callback):
        """
        Register a callback to be called when a device reconnects.
        
        Args:
            callback: Function to call with (device_name, status_dict) arguments
        """
        self._on_reconnect_callbacks.append(callback)
    
    def is_running(self):
        """
        Check if the monitor is currently running.
        
        Returns:
            bool: True if monitoring thread is active
        """
        return self._running and self._monitor_thread and self._monitor_thread.is_alive()


class SafeDeviceProxy:
    """
    A proxy class that wraps device calls and gracefully handles disconnections.
    
    This class intercepts method calls to a device and catches exceptions that
    occur when the device is disconnected, preventing crashes and allowing
    the system to continue operating with degraded functionality.
    """
    
    def __init__(self, device, device_name, port_monitor=None):
        """
        Initialize the SafeDeviceProxy.
        
        Args:
            device: The actual device object to wrap
            device_name: Name of the device for logging
            port_monitor: Optional PortMonitor instance for connectivity checks
        """
        self._device = device
        self._device_name = device_name
        self._port_monitor = port_monitor
        self._enabled = True
    
    def __getattr__(self, name):
        """
        Intercept attribute access and wrap method calls.
        
        Args:
            name: Name of the attribute/method being accessed
            
        Returns:
            Wrapped method or attribute value
        """
        # Get the actual attribute from the wrapped device
        attr = getattr(self._device, name)
        
        # If it's not callable, return it directly
        if not callable(attr):
            return attr
        
        # Wrap the method call with exception handling
        def safe_wrapper(*args, **kwargs):
            if not self._enabled:
                if __debug__:
                    print("SafeDeviceProxy: {} is disabled, ignoring {}".format(
                        self._device_name, name))
                return None
            
            # Check if device is connected via port monitor
            if self._port_monitor and not self._port_monitor.is_device_connected(self._device_name):
                if __debug__:
                    print("SafeDeviceProxy: {} is disconnected, ignoring {}".format(
                        self._device_name, name))
                return None
            
            try:
                return attr(*args, **kwargs)
            except Exception as e:
                if __debug__:
                    report_device_error(self._device_name, name, e, 
                                       "args={}, kwargs={}".format(args, kwargs))
                # Mark device as potentially disconnected
                self._enabled = False
                return None
        
        return safe_wrapper
    
    def enable(self):
        """Re-enable the device proxy after a reconnection."""
        self._enabled = True
    
    def disable(self):
        """Disable the device proxy (e.g., after detecting a disconnection)."""
        self._enabled = False
    
    def is_enabled(self):
        """Check if the device proxy is currently enabled."""
        return self._enabled
    
    def get_wrapped_device(self):
        """Get the underlying device object."""
        return self._device
    
    def set_wrapped_device(self, device):
        """
        Update the wrapped device (e.g., after reconnection).
        
        Args:
            device: New device instance to wrap
        """
        self._device = device
        self._enabled = True
