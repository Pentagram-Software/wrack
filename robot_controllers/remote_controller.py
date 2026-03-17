from event_handler import EventHandler
import threading
import struct
import socket
import json
from time import sleep, time

# Purpose: A class for handling commands sent from the network remote controller (from Google Cloud Functions or mobile apps)
class RemoteController(EventHandler, threading.Thread):
    # A flag for stopping the main loop of handling network controller events
    stopped = False
    connected = False
    l_left = 0
    l_forward = 0
    r_left = 0
    r_forward = 0
    
    # Connection management
    server_socket = None
    client_connections = []
    max_connections = 3
    
    # Command timeout for continuous operations
    last_command_time = 0
    command_timeout = 2.0  # Stop after 2 seconds without commands

    # Constructor
    def __init__(self, host="", port=27700):
        super().__init__()
        self.host = host
        self.port = port
        self.stopped = False
        self.connected = False
        self.client_connections = []
        self.turret_speed = 360  # Default turret speed in degrees/second
        self.turret_duration = 0  # Default turret duration (0 = continuous)
        self.speak_text = ""  # Text to be spoken by EV3
        self.last_response = None  # Store last response from event handlers
        self.local_ip = None  # Local IP used for current client connection
        self.hostname = None  # Cached hostname
        
    def __str__(self):
        return "Network Remote Controller"
    
    def is_connected(self):
        """Check if the remote controller has active connections"""
        return self.connected and len(self.client_connections) > 0
    
    # This is the main loop awaiting for incoming commands from the network. Run in a separate thread.
    def run(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            
            print("Network Remote Controller started on {}:{}".format(
                self.host if self.host else "all interfaces", self.port))
            self.server_socket.listen(self.max_connections)
            self.connected = True

            while not self.stopped:
                try:
                    self.establish_connection(self.server_socket)
                except Exception as e:
                    if not self.stopped:
                        # print("Connection error: {}".format(e))
                        sleep(1)  # Brief pause before retry
                        
        except Exception as e:
            print("Failed to start remote controller server: {}".format(e))
        finally:
            self.cleanup()



    def establish_connection(self, server_socket):
        """Handle incoming client connections"""
        try:
            # Set a timeout for accept to allow periodic stopping check
            server_socket.settimeout(1.0)
            conn, address = server_socket.accept()
            
            print("Connection from: {}".format(address))
            
            # Add to connection list
            self.client_connections.append(conn)
            
            # Set timeout for client socket
            conn.settimeout(5.0)
            
            # Capture local IP and hostname for status reporting
            try:
                self.local_ip = conn.getsockname()[0]
            except Exception:
                self.local_ip = None
            try:
                self.hostname = socket.gethostname()
            except Exception:
                self.hostname = None
            
            # Send welcome message as plain text so GCP client will skip it
            welcome_text = (
                "Welcome to Mindstorms EV3 Remote Controller!\n"
                "Send JSON commands to control the robot.\n"
                "Supported: move, turret, speak, beep, battery, status, help, quit"
            )

            self.send_response(conn, welcome_text)
            
            # Handle client communication
            while not self.stopped:
                try:
                    print("Waiting for command...");
                    # Receive data with larger buffer for JSON commands
                    data = conn.recv(4096).decode('utf-8')
                    if not data:
                        break
                        
                    print("Received from {}: {}".format(address, data.strip()))
                    
                    # Process command and send response
                    response = self.process_command(data.strip())
                    if response:
                        self.send_response(conn, response)
                        
                    # Update last command time for timeout tracking
                    self.last_command_time = time()
                    
                except socket.timeout:
                    # Check for command timeout
                    if time() - self.last_command_time > self.command_timeout:
                        # Send stop command if no recent activity
                        self.trigger("stop")
                    continue
                except Exception as e:
                    print("Error handling client {}: {}".format(address, e))
                    break
                    
        except socket.timeout:
            # Normal timeout, continue main loop
            return
        except Exception as e:
            if not self.stopped:
                print("Connection establishment error: {}".format(e))
        finally:
            # Clean up this connection
            if 'conn' in locals():
                try:
                    conn.close()
                    if conn in self.client_connections:
                        self.client_connections.remove(conn)
                    print("Connection from {} closed".format(address))
                except:
                    pass

    def handle_event(self, event):
        # Override this method to handle events
        pass

    def send_response(self, conn, response):
        """Send response back to client"""
        try:
            if isinstance(response, dict):
                response_str = json.dumps(response) + "\n"
            else:
                response_str = str(response) + "\n"
            # MicroPython sockets may not have sendall; ensure full send with a loop
            data = response_str.encode('utf-8')
            total_sent = 0
            while total_sent < len(data):
                sent = conn.send(data[total_sent:])
                if not sent:
                    raise Exception("socket connection broken during send")
                total_sent += sent
        except Exception as e:
            print("Failed to send response: {}".format(e))

    def process_command(self, data):
        """Process incoming command - supports both JSON and simple text formats"""
        try:
            # Try to parse as JSON first
            try:
                command = json.loads(data)
                return self.handle_json_command(command)
            except ValueError:
                # Fall back to simple text command (MicroPython only raises ValueError for JSON errors)
                return self.handle_text_command(data)
                
        except Exception as e:
            error_response = {
                "status": "error",
                "message": "Failed to process command: {}".format(e),
                "received": data
            }
            print("Command processing error: {}".format(e))
            return error_response

    def handle_json_command(self, command):
        """Handle JSON formatted commands with parameters"""
        if not isinstance(command, dict) or "action" not in command:
            return {
                "status": "error",
                "message": "JSON command must have 'action' field",
                "examples": {
                    "simple": {"action": "forward"},
                    "with_speed": {"action": "move", "direction": "forward", "speed": 500},
                    "timed": {"action": "move", "direction": "left", "speed": 300, "duration": 2.0},
                    "joystick": {"action": "joystick", "l_left": -500, "l_forward": 800, "r_left": 200}
                }
            }
        
        action = command.get("action", "").lower()
        speed = command.get("speed", 1000)  # Default speed
        duration = command.get("duration", 0)  # 0 = continuous
        direction = command.get("direction", "")
        
        print("JSON Command - Action: {}, Speed: {}, Duration: {}, Direction: {}".format(action, speed, duration, direction))
        
        # Store command parameters for event handlers to access
        self.current_command = {
            "speed": speed,
            "duration": duration,
            "direction": direction,
            "timestamp": time()
        }
        
        # Execute command based on action type
        if action == "joystick":
            # Handle joystick-style control with direct axis values
            self.l_left = command.get("l_left", 0)
            self.l_forward = command.get("l_forward", 0)
            self.r_left = command.get("r_left", 0)
            self.r_forward = command.get("r_forward", 0)
            
            # Trigger joystick events
            self.trigger("left_joystick")
            self.trigger("right_joystick")
            
            return {
                "status": "success",
                "action": "joystick",
                "joystick_values": {
                    "l_left": self.l_left,
                    "l_forward": self.l_forward,
                    "r_left": self.r_left,
                    "r_forward": self.r_forward
                }
            }
            
        elif action == "move":
            # Handle directional movement with optional speed and duration
            if direction == "left":
                self.trigger("right")     # Fixed: left command should trigger right event
            elif direction == "right":
                self.trigger("left")      # Fixed: right command should trigger left event
            elif direction == "forward":
                self.trigger("backward")  # Fixed: forward command should trigger backward event
            elif direction == "backward":
                self.trigger("forward")   # Fixed: backward command should trigger forward event
            else:
                return {"status": "error", "message": "Move command requires direction: left, right, forward, or backward"}
                
        elif action == "turn_left":
            self.trigger("right")     # Fixed: turn_left command should trigger right event
        elif action == "turn_right":
            self.trigger("left")      # Fixed: turn_right command should trigger left event
        elif action == "forward":
            self.trigger("backward")  # Fixed: forward command should trigger backward event
        elif action == "backward":
            self.trigger("forward")   # Fixed: backward command should trigger forward event
        elif action == "fire":
            self.trigger("fire")
        elif action == "stop":
            self.trigger("stop")
        elif action == "camera_left":
            self.trigger("camera_left")
        elif action == "camera_right":
            self.trigger("camera_right")
        elif action == "turret":
            # Handle unified turret command with direction
            turret_direction = command.get("direction", "").lower()
            if turret_direction not in ["left", "right"]:
                return {"status": "error", "message": "Turret command requires direction: 'left' or 'right'"}
            
            # Store speed and duration for turret control
            self.turret_speed = speed if speed != 1000 else 360  # Default turret speed
            self.turret_duration = duration  # Store duration for timed movements
            
            if turret_direction == "left":
                self.trigger("turret_left")
            else:
                self.trigger("turret_right")
                
        elif action == "turret_left":
            # Store speed for turret control (backward compatibility)
            self.turret_speed = speed if speed != 1000 else 360  # Default turret speed
            self.trigger("turret_left")
        elif action == "turret_right":
            # Store speed for turret control (backward compatibility)
            self.turret_speed = speed if speed != 1000 else 360  # Default turret speed
            self.trigger("turret_right")
        elif action == "stop_turret":
            self.trigger("stop_turret")
        elif action == "speak":
            # Handle speak command with text parameter
            text = command.get("text", "")
            if not text:
                return {"status": "error", "message": "Speak command requires 'text' parameter"}
            
            # Store text for event handler to access
            self.speak_text = text
            self.trigger("speak")
            
            return {
                "status": "success",
                "action": "speak",
                "text": text,
                "executed": True
            }
        elif action == "beep":
            # Handle beep command with optional frequency and duration parameters
            frequency = command.get("frequency", 800)  # Default 800 Hz
            duration_ms = command.get("duration", 200)  # Default 200 ms
            
            # Store parameters for event handler to access
            self.beep_frequency = frequency
            self.beep_duration = duration_ms
            self.trigger("beep")
            
            return {
                "status": "success",
                "action": "beep",
                "frequency": frequency,
                "duration": duration_ms,
                "executed": True
            }
        elif action == "battery":
            # Handle battery status request
            self.last_response = None  # Clear previous response
            self.trigger("battery")
            # Return the response set by the event handler
            if self.last_response:
                return self.last_response
            else:
                # Fallback if no handler registered
                return {
                    "status": "error",
                    "action": "battery",
                    "message": "Battery handler not available"
                }
        elif action == "status" or action == "get_status":
            return self.get_status()
        elif action == "help":
            return self.get_help()
        elif action == "quit" or action == "shutdown":
            self.trigger("quit")
        else:
            self.trigger("unknown")
            return {
                "status": "error", 
                "message": "Unknown action: {}".format(action),
                "supported_actions": ["move", "joystick", "turn_left", "turn_right", "forward", "backward", "fire", "stop", "battery", "beep", "camera_left", "camera_right", "turret", "turret_left", "turret_right", "stop_turret", "speak", "status", "get_status", "help", "quit"]
            }
        
        # Schedule auto-stop if duration is specified
        if duration > 0:
            # Note: In a real implementation, you might want to use threading.Timer
            # For now, we'll rely on the calling system to send stop commands
            response = {
                "status": "success",
                "action": action,
                "executed": True,
                "auto_stop_after": duration,
                "note": "Send 'stop' command or wait {} seconds for automatic timeout".format(self.command_timeout)
            }
        else:
            response = {
                "status": "success",
                "action": action,
                "executed": True,
                "speed": speed
            }
            
        return response

    def handle_text_command(self, data):
        """Handle simple text commands (backwards compatibility)"""
        print("Text Command: {}".format(data))
        
        # Handle legacy commands
        if data == "TurnLeft!":
            self.trigger("right")     # Fixed: TurnLeft should trigger right event
        elif data == "TurnRight!":
            self.trigger("left")      # Fixed: TurnRight should trigger left event
        elif data == "EngineAhead!":
            self.trigger("backward")  # Fixed: EngineAhead should trigger backward event
        elif data == "EngineBack!":
            self.trigger("forward")   # Fixed: EngineBack should trigger forward event
        elif data == "Fire!":
            self.trigger("fire")
        elif data == "Stop!":
            self.trigger("stop")
        # Handle new simple commands
        elif data.lower() in ["left", "turn_left"]:
            self.trigger("right")     # Fixed: left command should trigger right event
        elif data.lower() in ["right", "turn_right"]:
            self.trigger("left")      # Fixed: right command should trigger left event
        elif data.lower() in ["forward", "ahead"]:
            self.trigger("backward")  # Fixed: forward command should trigger backward event
        elif data.lower() in ["backward", "back"]:
            self.trigger("forward")   # Fixed: backward command should trigger forward event
        elif data.lower() == "fire":
            self.trigger("fire")
        elif data.lower() == "stop":
            self.trigger("stop")
        elif data.lower() == "camera_left":
            self.trigger("camera_left")
        elif data.lower() == "camera_right":
            self.trigger("camera_right")
        elif data.lower() == "turret_left":
            self.turret_speed = 360  # Default speed for text commands
            self.trigger("turret_left")
        elif data.lower() == "turret_right":
            self.turret_speed = 360  # Default speed for text commands
            self.trigger("turret_right")
        elif data.lower() == "stop_turret":
            self.trigger("stop_turret")
        elif data.lower().startswith("speak:"):
            # Handle speak command with text after colon
            # Format: "speak:Hello World"
            text = data[6:].strip()  # Remove "speak:" prefix
            if text:
                self.speak_text = text
                self.trigger("speak")
                return {
                    "status": "success",
                    "action": "speak",
                    "text": text,
                    "executed": True
                }
            else:
                return {"status": "error", "message": "Speak command requires text after 'speak:'"}
        elif data.lower() == "battery":
            # Handle battery status request
            self.last_response = None  # Clear previous response
            self.trigger("battery")
            # Return the response set by the event handler
            if self.last_response:
                return self.last_response
            else:
                # Fallback if no handler registered
                return {
                    "status": "error",
                    "action": "battery",
                    "message": "Battery handler not available"
                }
        elif data.lower() in ["status", "get_status"]:
            return self.get_status()
        elif data.lower() in ["quit", "shutdown", "exit"]:
            self.trigger("quit")
        else:
            self.trigger("unknown")
            return {
                "status": "error",
                "message": "Unknown command: {}".format(data),
                "supported_commands": ["left", "right", "forward", "backward", "fire", "stop", "battery", "camera_left", "camera_right", "turret_left", "turret_right", "stop_turret", "speak:text", "status", "quit"]
            }
        
        return {
            "status": "success",
            "command": data,
            "executed": True
        }

    def get_status(self):
        """Return current vehicle status"""
        current_time = time()
        # Optional device info (battery, cpu, system) if device_manager is attached
        device_info = None
        dm = getattr(self, 'device_manager', None)
        if dm is not None:
            try:
                # Get battery info
                battery = dm.get_battery_info("rechargeable")
                voltage_v = None
                if battery and battery.get("voltage_mv") is not None:
                    try:
                        voltage_v = round(battery["voltage_mv"] / 1000.0, 2)
                    except Exception:
                        voltage_v = None
                if battery is None:
                    battery = {}
                battery_details = {
                    "voltage_mv": battery.get("voltage_mv"),
                    "voltage_v": voltage_v,
                    "current_ma": battery.get("current_ma"),
                    "percentage": battery.get("percentage"),
                    "battery_type": battery.get("battery_type"),
                    "available": battery.get("available")
                }
                
                # Get CPU usage
                cpu_usage = dm.get_cpu_usage()
                
                # Get system info (hostname, IP addresses, kernel)
                sys_info = None
                try:
                    sys_info = dm.get_system_info()
                except Exception as e:
                    print("Error getting system info: {}".format(e))
                    sys_info = None
                
                # Get device summary (available/missing devices)
                device_summary = None
                try:
                    device_summary = dm.get_device_summary()
                except Exception as e:
                    print("Error getting device summary: {}".format(e))
                    device_summary = None
                
                # Get sensor readings
                sensor_readings = None
                try:
                    sensor_readings = dm.get_sensor_readings()
                except Exception as e:
                    print("Error getting sensor readings: {}".format(e))
                    sensor_readings = None
                
                # Get motor status
                motor_status = None
                try:
                    motor_status = dm.get_motor_status()
                except Exception as e:
                    print("Error getting motor status: {}".format(e))
                    motor_status = None
                
                # Build device info with system details
                device_info = {
                    "battery": battery_details,
                    "cpu_usage_percent": cpu_usage,
                    "hostname": sys_info.get("hostname") if sys_info else getattr(self, 'hostname', None),
                    "ip_addresses": sys_info.get("ip_addresses") if sys_info else [getattr(self, 'local_ip', None)],
                    "kernel": sys_info.get("kernel") if sys_info else None,
                    "operating_system": sys_info.get("operating_system") if sys_info else None,
                    "architecture": sys_info.get("architecture") if sys_info else None,
                    "devices": device_summary,
                    "sensors": sensor_readings,
                    "motors": motor_status
                }
                
                # Debug: show what will be returned in status for device info
                try:
                    print("Status device_info: hostname={}, ip_addresses={}, kernel={}, cpu=%{}, batt_mv={}, batt_pct={}".format(
                        str(device_info.get("hostname")),
                        str(device_info.get("ip_addresses")),
                        str(device_info.get("kernel")),
                        str(device_info.get("cpu_usage_percent")),
                        str(battery_details.get("voltage_mv")),
                        str(battery_details.get("percentage"))
                    ))
                except Exception:
                    pass
            except Exception as e:
                print("Error building device_info: {}".format(e))
                device_info = None

        return {
            "status": "ok",
            "vehicle_status": {
                "connected": self.is_connected(),
                "active_connections": len(self.client_connections),
                "last_command_time": self.last_command_time,
                "time_since_last_command": current_time - self.last_command_time if self.last_command_time > 0 else 0,
                "auto_stop_in": max(0, self.command_timeout - (current_time - self.last_command_time)) if self.last_command_time > 0 else 0,
                "current_command": getattr(self, 'current_command', None),
                "joystick_state": {
                    "l_left": self.l_left,
                    "l_forward": self.l_forward,
                    "r_left": self.r_left,
                    "r_forward": self.r_forward
                },
                "turret_speed": self.turret_speed,
                "turret_duration": self.turret_duration
            },
            "device_info": device_info
        }

    def get_help(self):
        """Return help information about available commands"""
        return {
            "status": "help",
            "network_remote_controller": {
                "description": "EV3 Network Remote Controller - Control your robot via IP commands",
                "connection": {
                    "host": self.host if self.host else "any interface",
                    "port": self.port,
                    "max_connections": self.max_connections
                },
                "supported_formats": ["simple_text", "json"],
                "simple_commands": [
                    "left", "right", "forward", "backward", "fire", "stop", 
                    "battery", "camera_left", "camera_right", "turret_left", "turret_right", 
                    "stop_turret", "speak:your_text_here", "status", "help", "quit"
                ],
                "json_commands": {
                    "basic_movement": {
                        "description": "Simple directional movement",
                        "example": {"action": "forward"}
                    },
                    "movement_with_speed": {
                        "description": "Movement with custom speed",
                        "example": {"action": "move", "direction": "forward", "speed": 500}
                    },
                    "timed_movement": {
                        "description": "Movement for specific duration",
                        "example": {"action": "move", "direction": "left", "speed": 300, "duration": 2.0}
                    },
                    "joystick_control": {
                        "description": "Direct joystick axis control (-1000 to 1000)",
                        "example": {"action": "joystick", "l_left": -500, "l_forward": 800, "r_left": 200}
                    },
                    "status_query": {
                        "description": "Get vehicle status",
                        "example": {"action": "status"}
                    },
                    "turret_control": {
                        "description": "Rotate turret with direction, speed, and duration",
                        "examples": [
                            {"action": "turret", "direction": "left"},
                            {"action": "turret", "direction": "right", "speed": 180},
                            {"action": "turret", "direction": "left", "speed": 150, "duration": 1},
                            {"action": "turret_left", "speed": 180},
                            {"action": "turret_right", "speed": 500},
                            {"action": "stop_turret"}
                        ]
                    },
                    "speak": {
                        "description": "Make the EV3 robot speak text out loud",
                        "example": {"action": "speak", "text": "Hello from the cloud"}
                    },
                    "battery": {
                        "description": "Get battery status (voltage, current, percentage)",
                        "example": {"action": "battery"}
                    }
                },
                "automatic_features": {
                    "auto_stop_timeout": "{}s after last command".format(self.command_timeout),
                    "connection_management": "Multiple clients supported",
                    "error_handling": "Graceful error responses"
                }
            }
        }
    def stop(self):
        """Stop the remote controller and cleanup resources"""
        print("Stopping Network Remote Controller...")
        self.stopped = True
        self.cleanup()

    def cleanup(self):
        """Clean up all connections and resources"""
        try:
            # Close all client connections
            for conn in self.client_connections[:]:
                try:
                    conn.close()
                except:
                    pass
            self.client_connections.clear()
            
            # Close server socket
            if self.server_socket:
                try:
                    self.server_socket.close()
                except:
                    pass
                self.server_socket = None
            
            self.connected = False
            print("Network Remote Controller cleanup completed")
            
        except Exception as e:
            print("Error during cleanup: {}".format(e))

    # Event handler registration methods
    def onLeft(self, callback):
        self.on("left", callback)

    def onRight(self, callback):
        self.on("right", callback)

    def onForward(self, callback):
        self.on("forward", callback)

    def onBackward(self, callback):
        self.on("backward", callback)

    def onFire(self, callback):
        self.on("fire", callback)

    def onStop(self, callback):
        self.on("stop", callback)

    def onCameraLeft(self, callback):
        self.on("camera_left", callback)

    def onCameraRight(self, callback):
        self.on("camera_right", callback)

    def onUnknown(self, callback):
        self.on("unknown", callback)

    def onLeftJoystick(self, callback):
        self.on("left_joystick", callback)

    def onRightJoystick(self, callback):
        self.on("right_joystick", callback)

    def onQuit(self, callback):
        self.on("quit", callback)

    def onTurretLeft(self, callback):
        self.on("turret_left", callback)

    def onTurretRight(self, callback):
        self.on("turret_right", callback)
