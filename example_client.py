#!/usr/bin/env python3
"""
Example client for testing the RemoteController

This script shows how to send commands to the EV3 robot
from external systems like Google Cloud Functions.
"""

import socket
import json
import time

class EV3RemoteClient:
    def __init__(self, host, port=27700):
        self.host = host
        self.port = port
        self.socket = None
        self.connected = False
    
    def connect(self):
        """Connect to the EV3 remote controller"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.connected = True
            
            # Receive welcome message
            welcome = self.socket.recv(4096).decode('utf-8')
            print("Connected! Welcome message:")
            print(welcome)
            return True
            
        except Exception as e:
            print(f"Failed to connect: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from the remote controller"""
        if self.socket:
            self.socket.close()
            self.socket = None
            self.connected = False
    
    def send_command(self, command):
        """Send a command to the robot"""
        if not self.connected:
            print("Not connected!")
            return None
        
        try:
            # Send command
            if isinstance(command, dict):
                command_str = json.dumps(command)
            else:
                command_str = str(command)
            
            # Print the entire message being sent to the device
            full_message = command_str + '\n'
            print(f"Sending to device: {repr(full_message)}")
            
            self.socket.send(full_message.encode('utf-8'))
            
            # Receive response
            response = self.socket.recv(4096).decode('utf-8')
            
            # Try to parse as JSON
            try:
                return json.loads(response)
            except:
                return response.strip()
                
        except Exception as e:
            print(f"Error sending command: {e}")
            return None
    
    def move_forward(self, speed=1000, duration=0):
        """Move the robot forward"""
        command = {"action": "move", "direction": "forward", "speed": speed}
        if duration > 0:
            command["duration"] = duration
        return self.send_command(command)
    
    def move_backward(self, speed=1000, duration=0):
        """Move the robot backward"""
        command = {"action": "move", "direction": "backward", "speed": speed}
        if duration > 0:
            command["duration"] = duration
        return self.send_command(command)
    
    def turn_left(self, speed=1000, duration=0):
        """Turn the robot left"""
        command = {"action": "move", "direction": "left", "speed": speed}
        if duration > 0:
            command["duration"] = duration
        return self.send_command(command)
    
    def turn_right(self, speed=1000, duration=0):
        """Turn the robot right"""
        command = {"action": "move", "direction": "right", "speed": speed}
        if duration > 0:
            command["duration"] = duration
        return self.send_command(command)
    
    def stop(self):
        """Stop the robot"""
        return self.send_command({"action": "stop"})
    
    def joystick_control(self, l_left=0, l_forward=0, r_left=0, r_forward=0):
        """Send joystick-style control commands"""
        command = {
            "action": "joystick",
            "l_left": l_left,
            "l_forward": l_forward,
            "r_left": r_left,
            "r_forward": r_forward
        }
        return self.send_command(command)
    
    def get_status(self):
        """Get robot status"""
        return self.send_command({"action": "status"})
    
    def get_help(self):
        """Get help information"""
        return self.send_command({"action": "help"})

def demo_simple_commands(client):
    """Demonstrate simple movement commands"""
    print("\n=== Simple Movement Demo ===")
    
    print("Moving forward for 2 seconds...")
    response = client.move_forward(speed=500, duration=2)
    print(f"Response: {response}")
    time.sleep(2.5)
    
    print("Turning left for 1 second...")
    response = client.turn_left(speed=300, duration=1)
    print(f"Response: {response}")
    time.sleep(1.5)
    
    print("Moving backward for 1 second...")
    response = client.move_backward(speed=400, duration=1)
    print(f"Response: {response}")
    time.sleep(1.5)
    
    print("Stopping...")
    response = client.stop()
    print(f"Response: {response}")

def demo_joystick_control(client):
    """Demonstrate joystick-style control"""
    print("\n=== Joystick Control Demo ===")
    
    print("Forward and slight left...")
    client.joystick_control(l_left=-200, l_forward=500)
    time.sleep(1)
    
    print("Turn right on spot...")
    client.joystick_control(l_left=500, l_forward=0)
    time.sleep(1)
    
    print("Backward...")
    client.joystick_control(l_left=0, l_forward=-400)
    time.sleep(1)
    
    print("Stop...")
    client.joystick_control(0, 0, 0, 0)

def demo_text_commands(client):
    """Demonstrate simple text commands"""
    print("\n=== Text Commands Demo ===")
    
    commands = ["forward", "left", "backward", "right", "stop"]
    
    for cmd in commands:
        print(f"Sending: {cmd}")
        response = client.send_command(cmd)
        print(f"Response: {response}")
        time.sleep(1)

def main():
    """Main demo function"""
    # Replace with your EV3's IP address
    EV3_IP = "192.168.1.83"  # Change this to your EV3's IP
    
    print(f"Connecting to EV3 at {EV3_IP}:27700...")
    
    client = EV3RemoteClient(EV3_IP)
    
    if not client.connect():
        print("Failed to connect. Make sure:")
        print("1. The EV3 is running the RemoteController")
        print("2. The IP address is correct")
        print("3. The EV3 and this computer are on the same network")
        return
    
    try:
        # Get help information
        print("\n=== Getting Help ===")
        help_info = client.get_help()
        print(json.dumps(help_info, indent=2))
        
        # Get initial status
        print("\n=== Initial Status ===")
        status = client.get_status()
        print(json.dumps(status, indent=2))
        
        # Run demos
        demo_simple_commands(client)
        demo_joystick_control(client)
        demo_text_commands(client)
        
        # Final status
        print("\n=== Final Status ===")
        status = client.get_status()
        print(json.dumps(status, indent=2))
        
    except KeyboardInterrupt:
        print("\nStopping demo...")
        client.stop()
    finally:
        client.disconnect()
        print("Disconnected.")

# Example for Google Cloud Functions
def google_cloud_function_example(request):
    """
    Example Google Cloud Function that controls the EV3 robot
    
    Usage: Send HTTP POST requests with JSON like:
    {"action": "move", "direction": "forward", "speed": 500, "duration": 2}
    """
    import os
    
    # Get EV3 IP from environment variable
    ev3_ip = os.environ.get('EV3_IP', '192.168.1.83')
    
    try:
        # Parse request
        if request.method == 'POST':
            command = request.get_json()
        else:
            return {"error": "Only POST requests supported"}, 400
        
        # Connect to EV3
        client = EV3RemoteClient(ev3_ip)
        if not client.connect():
            return {"error": "Failed to connect to EV3"}, 500
        
        # Send command
        response = client.send_command(command)
        client.disconnect()
        
        return {"success": True, "response": response}
        
    except Exception as e:
        return {"error": str(e)}, 500

if __name__ == "__main__":
    main()
