#!/usr/bin/env python3
"""
Example robot server that runs on the Mindstorms robot.
This script should be deployed to your robot and listens for commands over TCP.
"""

import socket
import json
import threading
import time
from datetime import datetime

try:
    import pybricks
    from pybricks.hubs import EV3Brick
    from pybricks.ev3devices import Motor, TouchSensor, ColorSensor, UltrasonicSensor
    from pybricks.parameters import Port, Stop, Direction
    from pybricks.media.ev3dev import SoundFile
    PYBRICKS_AVAILABLE = True
except ImportError:
    PYBRICKS_AVAILABLE = False
    print("Pybricks not available - running in simulation mode")

class MindstormsRobotServer:
    def __init__(self, host='0.0.0.0', port=27700):
        self.host = host
        self.port = port
        self.running = True
        
        if PYBRICKS_AVAILABLE:
            self.ev3 = EV3Brick()
            self.left_motor = Motor(Port.B)
            self.right_motor = Motor(Port.C)
            self.turret_motor = Motor(Port.A)  # Turret motor on Port A
            self.touch_sensor = TouchSensor(Port.S1)
            self.color_sensor = ColorSensor(Port.S3)
            self.ultrasonic_sensor = UltrasonicSensor(Port.S4)
        
        self.speed = 50
        
    def handle_command(self, command_data):
        """Handle incoming command and return response using EV3 RemoteController protocol"""
        try:
            action = command_data.get('action')
            direction = command_data.get('direction')
            speed = command_data.get('speed', 500)
            duration = command_data.get('duration', 0)
            
            print(f"Executing action: {action} with direction: {direction}, speed: {speed}, duration: {duration}")
            
            if action == 'move':
                return self._handle_move(direction, speed, duration)
            elif action == 'turret':
                return self._handle_turret(direction, speed, duration)
            elif action == 'stop':
                return self._stop()
            elif action == 'stop_turret':
                return self._stop_turret()
            elif action == 'status':
                return self._get_status()
            elif action == 'help':
                return self._get_help()
            elif action == 'joystick':
                return self._handle_joystick(command_data)
            elif action == 'speak':
                return self._speak(command_data)
            else:
                return {'success': False, 'error': f'Unknown action: {action}'}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _handle_move(self, direction, speed, duration):
        """Handle movement commands with proper direction mapping"""
        if direction == 'forward':
            return self._move_forward(speed, duration)
        elif direction == 'backward':
            return self._move_backward(speed, duration)
        elif direction == 'left':
            return self._turn_left(speed, duration)
        elif direction == 'right':
            return self._turn_right(speed, duration)
        else:
            return {'success': False, 'error': f'Unknown direction: {direction}'}
    
    def _move_forward(self, speed, duration):
        if PYBRICKS_AVAILABLE:
            self.left_motor.run(speed)
            self.right_motor.run(speed)
            
            if duration > 0:
                time.sleep(duration)
                self.left_motor.stop()
                self.right_motor.stop()
        
        return {'success': True, 'action': 'moved_forward', 'speed': speed, 'duration': duration}
    
    def _move_backward(self, speed, duration):
        if PYBRICKS_AVAILABLE:
            self.left_motor.run(-speed)
            self.right_motor.run(-speed)
            
            if duration > 0:
                time.sleep(duration)
                self.left_motor.stop()
                self.right_motor.stop()
        
        return {'success': True, 'action': 'moved_backward', 'speed': speed, 'duration': duration}
    
    def _turn_left(self, speed, duration):
        if PYBRICKS_AVAILABLE:
            self.left_motor.run(-speed)
            self.right_motor.run(speed)
            
            if duration > 0:
                time.sleep(duration)
                self.left_motor.stop()
                self.right_motor.stop()
        
        return {'success': True, 'action': 'turned_left', 'speed': speed, 'duration': duration}
    
    def _turn_right(self, speed, duration):
        if PYBRICKS_AVAILABLE:
            self.left_motor.run(speed)
            self.right_motor.run(-speed)
            
            if duration > 0:
                time.sleep(duration)
                self.left_motor.stop()
                self.right_motor.stop()
        
        return {'success': True, 'action': 'turned_right', 'speed': speed, 'duration': duration}
    
    def _handle_turret(self, direction, speed, duration):
        """Handle turret movement commands"""
        if direction == 'left':
            return self._turret_left(speed, duration)
        elif direction == 'right':
            return self._turret_right(speed, duration)
        else:
            return {'success': False, 'error': f'Unknown turret direction: {direction}'}
    
    def _turret_left(self, speed, duration):
        if PYBRICKS_AVAILABLE:
            self.turret_motor.run(speed)
            
            if duration > 0:
                time.sleep(duration)
                self.turret_motor.stop()
        
        return {'success': True, 'action': 'turret_left', 'speed': speed, 'duration': duration}
    
    def _turret_right(self, speed, duration):
        if PYBRICKS_AVAILABLE:
            self.turret_motor.run(-speed)
            
            if duration > 0:
                time.sleep(duration)
                self.turret_motor.stop()
        
        return {'success': True, 'action': 'turret_right', 'speed': speed, 'duration': duration}
    
    def _stop(self):
        if PYBRICKS_AVAILABLE:
            self.left_motor.stop()
            self.right_motor.stop()
            self.turret_motor.stop()

        return {'success': True, 'action': 'stopped'}

    def _stop_turret(self):
        if PYBRICKS_AVAILABLE:
            self.turret_motor.stop()

        return {'success': True, 'action': 'stop_turret'}

    def _speak(self, command_data):
        """Handle text-to-speech command"""
        text = command_data.get('text', '')

        if PYBRICKS_AVAILABLE:
            try:
                self.ev3.speaker.say(text)
            except Exception as e:
                return {'success': False, 'error': f'TTS error: {str(e)}'}
        else:
            print(f"[SIMULATION] Would speak: {text}")

        return {'success': True, 'action': 'speak', 'text': text}
    
    def _get_status(self):
        """Return robot status information"""
        status = {
            'success': True,
            'status': 'online',
            'connection': 'connected',
            'timestamp': datetime.now().isoformat(),
            'motors': {
                'left': 'ready',
                'right': 'ready'
            }
        }
        
        if PYBRICKS_AVAILABLE:
            try:
                status['sensors'] = {
                    'touch': self.touch_sensor.pressed(),
                    'color': str(self.color_sensor.color()),
                    'distance': self.ultrasonic_sensor.distance()
                }
            except Exception as e:
                status['sensor_error'] = str(e)
        else:
            status['sensors'] = {
                'touch': False,
                'color': 'Red', 
                'distance': 100
            }
            status['simulation_mode'] = True
            
        return status
    
    def _get_help(self):
        """Return help information about available commands"""
        return {
            'success': True,
            'available_actions': [
                'move', 'turret', 'stop', 'stop_turret', 'status', 'help', 'joystick', 'speak'
            ],
            'move_directions': ['forward', 'backward', 'left', 'right'],
            'turret_directions': ['left', 'right'],
            'parameters': {
                'speed': 'Motor speed (0-2000)',
                'duration': 'Duration in seconds (0 for continuous)',
                'l_left': 'Left joystick left/right (-1000 to 1000)',
                'l_forward': 'Left joystick forward/backward (-1000 to 1000)',
                'r_left': 'Right joystick left/right (-1000 to 1000)',
                'r_forward': 'Right joystick forward/backward (-1000 to 1000)',
                'text': 'Text to speak (max 500 characters)'
            },
            'examples': [
                '{"action": "move", "direction": "forward", "speed": 500, "duration": 2}',
                '{"action": "move", "direction": "left", "speed": 300, "duration": 1}',
                '{"action": "turret", "direction": "left", "speed": 200, "duration": 1}',
                '{"action": "stop"}',
                '{"action": "stop_turret"}',
                '{"action": "joystick", "l_left": -200, "l_forward": 500}',
                '{"action": "speak", "text": "Hello World"}'
            ]
        }
    
    def _handle_joystick(self, command_data):
        """Handle joystick-style control"""
        l_left = command_data.get('l_left', 0)
        l_forward = command_data.get('l_forward', 0)
        r_left = command_data.get('r_left', 0) 
        r_forward = command_data.get('r_forward', 0)
        
        if PYBRICKS_AVAILABLE:
            # Convert joystick values to motor speeds
            # Simple tank drive: left stick controls left motor, right stick controls right motor
            left_speed = l_forward + l_left
            right_speed = r_forward + r_left
            
            # If only left stick is used, apply to both motors for simple control
            if r_left == 0 and r_forward == 0 and (l_left != 0 or l_forward != 0):
                right_speed = l_forward - l_left
            
            # Limit speeds
            left_speed = max(-1000, min(1000, left_speed))
            right_speed = max(-1000, min(1000, right_speed))
            
            self.left_motor.run(left_speed)
            self.right_motor.run(right_speed)
        
        return {
            'success': True,
            'action': 'joystick_control',
            'left_motor': left_speed if PYBRICKS_AVAILABLE else l_forward + l_left,
            'right_motor': right_speed if PYBRICKS_AVAILABLE else r_forward + r_left
        }
    
    def handle_client(self, client_socket, address):
        """Handle individual client connections with welcome message"""
        print(f"Connection from {address}")
        
        try:
            # Send welcome message like the original RemoteController
            welcome_msg = "Welcome to Mindstorms EV3 Remote Controller!\nSend JSON commands to control the robot.\n"
            client_socket.send(welcome_msg.encode('utf-8'))
            
            while self.running:
                data = client_socket.recv(1024).decode('utf-8').strip()
                if not data:
                    break
                
                try:
                    # Handle both JSON commands and simple text commands
                    if data.startswith('{'):
                        # JSON command
                        command_data = json.loads(data)
                        response = self.handle_command(command_data)
                        client_socket.send(json.dumps(response).encode('utf-8') + b'\n')
                    else:
                        # Simple text command (backward compatibility)
                        response = self._handle_text_command(data)
                        if isinstance(response, dict):
                            client_socket.send(json.dumps(response).encode('utf-8') + b'\n')
                        else:
                            client_socket.send(str(response).encode('utf-8') + b'\n')
                    
                except json.JSONDecodeError:
                    error_response = {'success': False, 'error': 'Invalid JSON'}
                    client_socket.send(json.dumps(error_response).encode('utf-8') + b'\n')
                
        except Exception as e:
            print(f"Error handling client {address}: {e}")
        finally:
            client_socket.close()
            print(f"Connection with {address} closed")
    
    def _handle_text_command(self, text_command):
        """Handle simple text commands for backward compatibility"""
        cmd = text_command.lower().strip()
        
        if cmd == 'forward':
            return self._move_forward(500, 1)
        elif cmd == 'backward':
            return self._move_backward(500, 1)
        elif cmd == 'left':
            return self._turn_left(300, 0.5)
        elif cmd == 'right':
            return self._turn_right(300, 0.5)
        elif cmd == 'stop':
            return self._stop()
        elif cmd == 'status':
            return self._get_status()
        elif cmd == 'help':
            return self._get_help()
        else:
            return {'success': False, 'error': f'Unknown text command: {cmd}'}
    
    def start_server(self):
        """Start the TCP server"""
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            server_socket.bind((self.host, self.port))
            server_socket.listen(5)
            
            print(f"Mindstorms EV3 Remote Controller listening on {self.host}:{self.port}")
            print("Compatible with existing example_client.py protocol")
            
            while self.running:
                try:
                    client_socket, address = server_socket.accept()
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, address)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                    
                except KeyboardInterrupt:
                    print("\nShutting down server...")
                    self.running = False
                    break
                    
        except Exception as e:
            print(f"Server error: {e}")
        finally:
            server_socket.close()

if __name__ == "__main__":
    robot_server = MindstormsRobotServer()
    robot_server.start_server()