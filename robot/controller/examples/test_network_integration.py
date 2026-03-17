#!/usr/bin/env python3
"""
Test script for network integration in main.py

This script helps verify that the RemoteController integration 
with main.py works correctly by testing basic connectivity 
and command handling.
"""

import socket
import json
import time
import sys

def test_connection(host, port=27700):
    """Test basic connection to the EV3 remote controller"""
    print(f"Testing connection to {host}:{port}...")
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((host, port))
        
        # Receive welcome message
        welcome = sock.recv(4096).decode('utf-8')
        print("✓ Connected successfully!")
        print("Welcome message:")
        try:
            welcome_data = json.loads(welcome)
            print(json.dumps(welcome_data, indent=2))
        except:
            print(welcome)
        
        sock.close()
        return True
        
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False

def test_commands(host, port=27700):
    """Test various commands"""
    print(f"\nTesting commands on {host}:{port}...")
    
    test_commands = [
        # Simple text commands
        "status",
        "help", 
        "forward",
        "stop",
        "turret_left",
        "turret_right",
        
        # JSON commands  
        '{"action": "status"}',
        '{"action": "move", "direction": "forward", "speed": 200}',
        '{"action": "stop"}',
        '{"action": "turret_left"}',
        '{"action": "turret_right"}',
        '{"action": "joystick", "l_left": 0, "l_forward": 300, "r_left": 0}',
        '{"action": "stop"}',
    ]
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10.0)
        sock.connect((host, port))
        
        # Skip welcome message
        welcome = sock.recv(4096)
        
        for i, cmd in enumerate(test_commands):
            print(f"\n--- Test {i+1}: {cmd[:50]}{'...' if len(cmd) > 50 else ''} ---")
            
            # Send command
            sock.send((cmd + '\n').encode('utf-8'))
            
            # Receive response
            response = sock.recv(4096).decode('utf-8')
            
            try:
                response_data = json.loads(response)
                print("Response:")
                print(json.dumps(response_data, indent=2))
            except:
                print(f"Response: {response}")
            
            # Small delay between commands
            time.sleep(0.5)
        
        sock.close()
        print("\n✓ All commands tested successfully!")
        return True
        
    except Exception as e:
        print(f"✗ Command testing failed: {e}")
        return False

def test_google_cloud_simulation(host, port=27700):
    """Simulate how Google Cloud Functions would interact"""
    print(f"\nSimulating Google Cloud Function interaction with {host}:{port}...")
    
    # Simulate a series of commands from a cloud function
    cloud_commands = [
        {"action": "status"},
        {"action": "move", "direction": "forward", "speed": 300, "duration": 1},
        {"action": "move", "direction": "left", "speed": 200, "duration": 0.5}, 
        {"action": "turret_left", "speed": 180},  # Test turret control
        {"action": "turret_right", "speed": 90},
        {"action": "stop"},
        {"action": "joystick", "l_left": -200, "l_forward": 400},
        {"action": "stop"},
    ]
    
    try:
        for i, command in enumerate(cloud_commands):
            print(f"\nCloud Function Command {i+1}: {command}")
            
            # Create new connection for each command (like Cloud Functions)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((host, port))
            
            # Skip welcome
            welcome = sock.recv(4096)
            
            # Send command
            sock.send((json.dumps(command) + '\n').encode('utf-8'))
            
            # Get response
            response = sock.recv(4096).decode('utf-8')
            response_data = json.loads(response)
            
            print(f"Status: {response_data.get('status', 'unknown')}")
            if 'message' in response_data:
                print(f"Message: {response_data['message']}")
            
            sock.close()
            time.sleep(0.8)  # Simulate delay between cloud function calls
        
        print("\n✓ Google Cloud Functions simulation completed!")
        return True
        
    except Exception as e:
        print(f"✗ Cloud simulation failed: {e}")
        return False

def main():
    """Main test function"""
    if len(sys.argv) != 2:
        print("Usage: python test_network_integration.py <EV3_IP_ADDRESS>")
        print("Example: python test_network_integration.py 192.168.1.100")
        sys.exit(1)
    
    host = sys.argv[1]
    
    print("=== EV3 Network Remote Controller Integration Test ===")
    print(f"Target: {host}:27700")
    print("\nMake sure your EV3 is running main.py with RemoteController enabled!")
    print("=" * 60)
    
    # Run tests
    tests_passed = 0
    total_tests = 3
    
    if test_connection(host):
        tests_passed += 1
    
    if test_commands(host):
        tests_passed += 1
    
    if test_google_cloud_simulation(host):
        tests_passed += 1
    
    # Results
    print("\n" + "=" * 60)
    print(f"RESULTS: {tests_passed}/{total_tests} tests passed")
    
    if tests_passed == total_tests:
        print("✓ ALL TESTS PASSED! Your EV3 is ready for network control!")
        print("\nYour robot can now be controlled via:")
        print("- PS4 Controller (Bluetooth)")
        print("- Network commands (IP)")
        print("- Google Cloud Functions")
        print("- Mobile apps")
        print("- Any TCP client")
    else:
        print("✗ Some tests failed. Check your EV3 setup:")
        print("- Is main.py running on the EV3?")
        print("- Is the IP address correct?")
        print("- Are the EV3 and this computer on the same network?")
        print("- Is port 27700 accessible?")

if __name__ == "__main__":
    main()
