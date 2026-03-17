#!/usr/bin/env python3
"""
Example script demonstrating turret control via network commands

This script shows how to control the turret remotely using the new
turret_left and turret_right commands.
"""

import socket
import json
import time
import sys

def connect_to_robot(host, port=27700):
    """Connect to the EV3 robot"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10.0)
        sock.connect((host, port))
        
        # Receive welcome message
        welcome = sock.recv(4096).decode('utf-8')
        print("Connected to robot!")
        
        return sock
    except Exception as e:
        print(f"Failed to connect: {e}")
        return None

def send_command(sock, command):
    """Send a command and get response"""
    try:
        if isinstance(command, dict):
            command_str = json.dumps(command)
        else:
            command_str = str(command)
        
        sock.send((command_str + '\n').encode('utf-8'))
        response = sock.recv(4096).decode('utf-8')
        
        try:
            return json.loads(response)
        except:
            return response.strip()
    except Exception as e:
        print(f"Error sending command: {e}")
        return None

def demo_turret_speed_control(sock):
    """Demonstrate speed-based turret control"""
    print("\n=== Turret Speed Control Demo ===")
    
    # Get initial status
    status = send_command(sock, {"action": "status"})
    print("Initial robot status:", status.get('status', 'unknown'))
    
    print("\nTesting different turret speeds...")
    
    # Test slow speed
    print("Slow rotation right (90 degrees/second):")
    response = send_command(sock, {"action": "turret_right", "speed": 90})
    print(f"  Response: {response.get('status', 'unknown')}")
    time.sleep(2)
    send_command(sock, {"action": "stop"})
    
    time.sleep(1)
    
    # Test medium speed
    print("Medium rotation left (180 degrees/second):")
    response = send_command(sock, {"action": "turret_left", "speed": 180})
    print(f"  Response: {response.get('status', 'unknown')}")
    time.sleep(2)
    send_command(sock, {"action": "stop"})
    
    time.sleep(1)
    
    # Test fast speed
    print("Fast rotation right (360 degrees/second):")
    response = send_command(sock, {"action": "turret_right", "speed": 360})
    print(f"  Response: {response.get('status', 'unknown')}")
    time.sleep(1.5)
    send_command(sock, {"action": "stop"})
    
    time.sleep(1)
    
    # Test very slow precision
    print("Very slow precision left (45 degrees/second):")
    response = send_command(sock, {"action": "turret_left", "speed": 45})
    print(f"  Response: {response.get('status', 'unknown')}")
    time.sleep(3)
    send_command(sock, {"action": "stop"})
    
    print("Turret speed control demo complete!")

def demo_text_commands(sock):
    """Demonstrate simple text commands"""
    print("\n=== Simple Text Commands Demo ===")
    
    print("Testing text commands (default speed: 360 degrees/second):")
    
    commands = [
        ("turret_right", 1.0),  # Command and duration
        ("stop", 0.5),
        ("turret_left", 1.5),
        ("stop", 0.5),
        ("turret_right", 0.8),
        ("stop", 0.5),
        ("turret_left", 1.2),
        ("stop", 0.5)
    ]
    
    for i, (cmd, duration) in enumerate(commands):
        print(f"Command {i+1}: {cmd}")
        response = send_command(sock, cmd)
        print(f"  Response: {response.get('status', 'unknown') if isinstance(response, dict) else response}")
        time.sleep(duration)

def demo_combined_movements(sock):
    """Demonstrate combined robot and turret movements"""
    print("\n=== Combined Movement Demo ===")
    
    # Move forward while scanning with turret
    print("Moving forward while scanning with turret...")
    
    # Start moving forward
    send_command(sock, {"action": "move", "direction": "forward", "speed": 300})
    time.sleep(0.5)
    
    # Scan turret left and right while moving using speed control
    for i in range(2):
        print(f"  Scan cycle {i+1}")
        
        # Slow scan left
        send_command(sock, {"action": "turret_left", "speed": 120})
        time.sleep(2)
        
        # Stop turret briefly
        send_command(sock, {"action": "stop"})
        time.sleep(0.3)
        
        # Slow scan right
        send_command(sock, {"action": "turret_right", "speed": 120})
        time.sleep(4)  # Go past center to the right
        
        # Stop turret briefly
        send_command(sock, {"action": "stop"}) 
        time.sleep(0.3)
        
        # Return to center
        send_command(sock, {"action": "turret_left", "speed": 120})
        time.sleep(2)
        send_command(sock, {"action": "stop"})
        time.sleep(0.5)
    
    # Stop robot
    send_command(sock, {"action": "stop"})
    print("Combined movement demo complete!")

def main():
    """Main demo function"""
    if len(sys.argv) != 2:
        print("Usage: python example_turret_control.py <EV3_IP_ADDRESS>")
        print("Example: python example_turret_control.py 192.168.1.100")
        sys.exit(1)
    
    host = sys.argv[1]
    
    print("=== EV3 Turret Control Demo ===")
    print(f"Connecting to {host}:27700...")
    print("\nMake sure your EV3 has a turret motor connected to port C!")
    print("=" * 50)
    
    sock = connect_to_robot(host)
    if not sock:
        return
    
    try:
        # Run demos
        demo_turret_speed_control(sock)
        time.sleep(2)
        
        demo_text_commands(sock)
        time.sleep(2)
        
        demo_combined_movements(sock)
        
        print("\n" + "=" * 50)
        print("✓ All turret demos completed successfully!")
        print("\nSpeed-based turret commands available:")
        print("  Text commands: 'turret_left', 'turret_right' (default: 360°/s)") 
        print("  JSON commands: {'action': 'turret_left', 'speed': 180}")
        print("  Speed range: 1-360 degrees/second")
        print("  Use 'stop' command to stop turret rotation")
        print("  Turret automatically stops at range limits (-90° to +90°)")
        
    except KeyboardInterrupt:
        print("\nDemo interrupted by user")
    finally:
        sock.close()
        print("Disconnected from robot.")

if __name__ == "__main__":
    main()
