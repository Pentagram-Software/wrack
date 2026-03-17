#!/usr/bin/env pybricks-micropython

"""
TerrainScanner Class - Movement-Based Terrain Scanning with Local Data Persistence

This class provides comprehensive terrain scanning capabilities using:
- Gyro sensor for precise robot orientation tracking
- Ultrasonic sensor for distance measurements
- Movement-based scanning (robot rotation instead of turret rotation)
- Local data persistence for asynchronous cloud retrieval
- Automatic continuous scanning with configurable intervals

Features:
- Stationary 360° rotation scanning
- Precise gyro-based rotation control
- Local JSON data storage with lifecycle management
- Network API for cloud data retrieval
- Automatic storage capacity management
- Multiple scanning modes and patterns

Author: AI Assistant
Compatible with: EV3 MicroPython
"""

import json
import os
import threading
from time import time, sleep
from pybricks.parameters import Port
from pybricks.ev3devices import UltrasonicSensor, GyroSensor


class TerrainScanner:
    """
    Comprehensive terrain scanning system using movement-based scanning approach.
    
    Uses gyro sensor for orientation and ultrasonic sensor for distance measurements.
    Robot rotates in place to perform 360° scans, storing data locally for 
    asynchronous cloud retrieval.
    """
    
    def __init__(self, device_manager, tank_drive_system, ev3_speaker):
        """
        Initialize the TerrainScanner with required dependencies.
        
        Args:
            device_manager: DeviceManager instance for safe device access
            tank_drive_system: TankDriveSystem instance for robot movement
            ev3_speaker: EV3Brick speaker for audio feedback
        """
        self.device_manager = device_manager
        self.tank_drive = tank_drive_system
        self.speaker = ev3_speaker
        
        # Scanning configuration
        self.scan_step_angle = 10           # degrees between measurements
        self.scan_range_start = 0           # starting angle for scan
        self.scan_range_end = 350           # ending angle for scan (almost 360°)
        self.rotation_speed = 200           # motor speed for rotation
        self.stabilization_time = 0.3       # seconds to wait after rotation
        self.measurement_samples = 3        # multiple samples per point
        self.heading_tolerance = 3.0        # acceptable heading error in degrees
        
        # Automatic scanning configuration
        self.auto_scan_enabled = False
        self.auto_scan_interval = 300       # seconds between auto scans (5 minutes)
        self.auto_scan_thread = None
        
        # Data storage configuration
        self.storage_path = "/home/robot/terrain_scans/"
        self.max_storage_mb = 50            # maximum storage usage
        self.retention_hours = 48           # keep retrieved scans for 48 hours
        
        # Runtime state
        self.current_scan_id = None
        self.scan_in_progress = False
        self.robot_position = {"x": 0.0, "y": 0.0, "heading": 0.0}
        
        # Data management
        self.scan_index = {}
        self.pending_scans = []
        
        # Initialize storage
        self._initialize_storage()
        self._load_scan_index()
        
        print("TerrainScanner initialized")
        print("- Step angle: {}°".format(self.scan_step_angle))
        print("- Storage path: {}".format(self.storage_path))
        print("- Gyro available: {}".format(self.device_manager.is_device_available("gyro_sensor")))
        print("- Ultrasonic available: {}".format(self.device_manager.is_device_available("us_sensor")))

    def _initialize_storage(self):
        """Create storage directory if it doesn't exist"""
        try:
            if not os.path.exists(self.storage_path):
                os.makedirs(self.storage_path)
            
            # Create index file if it doesn't exist
            index_file = os.path.join(self.storage_path, "scan_index.json")
            if not os.path.exists(index_file):
                with open(index_file, 'w') as f:
                    json.dump({"scan_index": {}, "pending_scans": []}, f)
                    
        except Exception as e:
            print("Error initializing storage: {}".format(e))

    def _load_scan_index(self):
        """Load existing scan index from storage"""
        try:
            index_file = os.path.join(self.storage_path, "scan_index.json")
            if os.path.exists(index_file):
                with open(index_file, 'r') as f:
                    data = json.load(f)
                    self.scan_index = data.get("scan_index", {})
                    self.pending_scans = data.get("pending_scans", [])
                    
            print("Loaded scan index: {} scans, {} pending".format(
                len(self.scan_index), len(self.pending_scans)))
                
        except Exception as e:
            print("Error loading scan index: {}".format(e))
            self.scan_index = {}
            self.pending_scans = []

    def _save_scan_index(self):
        """Save current scan index to storage"""
        try:
            index_file = os.path.join(self.storage_path, "scan_index.json")
            with open(index_file, 'w') as f:
                json.dump({
                    "scan_index": self.scan_index,
                    "pending_scans": self.pending_scans
                }, f)
        except Exception as e:
            print("Error saving scan index: {}".format(e))

    def _generate_scan_id(self):
        """Generate unique scan ID based on timestamp"""
        return "terrain_scan_{}".format(int(time()))

    def _get_current_heading(self):
        """Get current robot heading from gyro sensor"""
        if self.device_manager.is_device_available("gyro_sensor"):
            try:
                heading = self.device_manager.safe_device_call("gyro_sensor", "angle")
                return heading if heading is not None else 0.0
            except Exception as e:
                print("Error reading gyro: {}".format(e))
                return 0.0
        return 0.0

    def _get_distance_measurement(self):
        """Get distance measurement from ultrasonic sensor with multiple samples"""
        if not self.device_manager.is_device_available("us_sensor"):
            return None
        
        distances = []
        for _ in range(self.measurement_samples):
            try:
                distance = self.device_manager.safe_device_call("us_sensor", "distance")
                if distance is not None and distance > 0:
                    distances.append(distance)
                sleep(0.05)  # Small delay between samples
            except Exception as e:
                print("Error reading ultrasonic: {}".format(e))
        
        if distances:
            # Return median to filter outliers
            distances.sort()
            return distances[len(distances) // 2]
        return None

    def _rotate_to_heading(self, target_heading):
        """
        Rotate robot to specific heading using gyro feedback.
        
        Args:
            target_heading: Target heading in degrees
            
        Returns:
            tuple: (success, actual_heading, heading_error)
        """
        if not self.device_manager.are_devices_available(["drive_L_motor", "drive_R_motor"]):
            print("Drive motors not available for rotation")
            return False, 0.0, 999.0
        
        max_attempts = 50  # Prevent infinite loops
        attempt = 0
        
        while attempt < max_attempts:
            current_heading = self._get_current_heading()
            error = self._normalize_angle(target_heading - current_heading)
            
            if abs(error) <= self.heading_tolerance:
                # Target reached
                self.tank_drive.stop()
                return True, current_heading, error
            
            # Calculate rotation power based on error (proportional control)
            base_power = min(self.rotation_speed, abs(error) * 5)
            power = max(100, base_power)  # Minimum power for movement
            
            # Rotate in appropriate direction
            if error > 0:
                self.tank_drive.turn_right(power)
            else:
                self.tank_drive.turn_left(power)
            
            sleep(0.1)  # Small delay for motor response
            attempt += 1
        
        # Failed to reach target
        self.tank_drive.stop()
        final_heading = self._get_current_heading()
        final_error = self._normalize_angle(target_heading - final_heading)
        
        print("Warning: Failed to reach target heading {}°, final error: {:.1f}°".format(
            target_heading, final_error))
        
        return False, final_heading, final_error

    def _normalize_angle(self, angle):
        """Normalize angle to [-180, 180] range"""
        while angle > 180:
            angle -= 360
        while angle < -180:
            angle += 360
        return angle

    def _wait_for_stabilization(self):
        """Wait for robot to stabilize after movement"""
        sleep(self.stabilization_time)
        
        # Check gyro stability
        if self.device_manager.is_device_available("gyro_sensor"):
            stability_samples = 5
            gyro_readings = []
            
            for _ in range(stability_samples):
                reading = self._get_current_heading()
                gyro_readings.append(reading)
                sleep(0.1)
            
            # Check if readings are stable (low variance)
            if len(gyro_readings) > 1:
                avg = sum(gyro_readings) / len(gyro_readings)
                variance = sum((x - avg) ** 2 for x in gyro_readings) / len(gyro_readings)
                
                if variance > 2.0:  # High variance indicates instability
                    print("Gyro unstable, extending stabilization time")
                    sleep(0.5)

    def perform_scan(self, scan_type="full_360"):
        """
        Perform terrain scan using robot rotation.
        
        Args:
            scan_type: Type of scan ("full_360", "quick_8_point", "custom")
            
        Returns:
            dict: Scan data with metadata, or None if scan failed
        """
        if self.scan_in_progress:
            print("Scan already in progress")
            return None
        
        if not self.device_manager.are_devices_available(["us_sensor", "gyro_sensor"]):
            print("Required sensors not available for terrain scanning")
            self.speaker.beep(frequency=300, duration=500)
            return None
        
        self.scan_in_progress = True
        self.current_scan_id = self._generate_scan_id()
        
        try:
            print("Starting terrain scan ID: {}".format(self.current_scan_id))
            
            # Audio feedback - scan start
            self.speaker.beep(frequency=800, duration=100)
            sleep(0.1)
            self.speaker.beep(frequency=1000, duration=100)
            
            # Configure scan parameters based on type
            if scan_type == "quick_8_point":
                scan_angles = [0, 45, 90, 135, 180, 225, 270, 315]
            elif scan_type == "custom":
                scan_angles = list(range(self.scan_range_start, self.scan_range_end + 1, self.scan_step_angle))
            else:  # full_360
                scan_angles = list(range(0, 360, self.scan_step_angle))
            
            scan_data = {
                "scan_id": self.current_scan_id,
                "timestamp": time(),
                "scan_type": scan_type,
                "robot_position": self.robot_position.copy(),
                "scan_parameters": {
                    "step_angle": self.scan_step_angle,
                    "measurement_samples": self.measurement_samples,
                    "stabilization_time": self.stabilization_time,
                    "total_angles": len(scan_angles)
                },
                "scan_points": [],
                "scan_quality": {}
            }
            
            start_heading = self._get_current_heading()
            successful_measurements = 0
            failed_measurements = 0
            
            print("Performing {} scan with {} measurement points".format(scan_type, len(scan_angles)))
            
            # Perform scan at each angle
            for i, relative_angle in enumerate(scan_angles):
                if not self.scan_in_progress:  # Allow cancellation
                    print("Scan cancelled by user")
                    break
                
                target_heading = self._normalize_angle(start_heading + relative_angle)
                
                print("Scan point {}/{}: rotating to {}°".format(
                    i + 1, len(scan_angles), target_heading))
                
                # Rotate to target heading
                rotation_success, actual_heading, heading_error = self._rotate_to_heading(target_heading)
                
                # Wait for stabilization
                self._wait_for_stabilization()
                
                # Take distance measurement
                distance = self._get_distance_measurement()
                
                # Create scan point
                scan_point = {
                    "sequence": i,
                    "timestamp": time(),
                    "target_heading": target_heading,
                    "actual_heading": actual_heading,
                    "heading_error": heading_error,
                    "distance_mm": distance,
                    "rotation_success": rotation_success,
                    "measurement_confidence": self._calculate_measurement_confidence(
                        distance, heading_error, rotation_success)
                }
                
                scan_data["scan_points"].append(scan_point)
                
                # Track success/failure
                if distance is not None and rotation_success:
                    successful_measurements += 1
                else:
                    failed_measurements += 1
                
                # Progress feedback
                if (i + 1) % 5 == 0:  # Every 5th measurement
                    self.speaker.beep(frequency=600, duration=50)
                
                sleep(0.1)  # Brief pause between measurements
            
            # Calculate scan quality metrics
            scan_data["scan_quality"] = {
                "successful_measurements": successful_measurements,
                "failed_measurements": failed_measurements,
                "success_rate": successful_measurements / len(scan_angles) if scan_angles else 0,
                "total_duration_seconds": time() - scan_data["timestamp"],
                "avg_heading_error": self._calculate_avg_heading_error(scan_data["scan_points"])
            }
            
            print("Scan complete: {}/{} successful measurements".format(
                successful_measurements, len(scan_angles)))
            
            # Audio feedback - scan complete
            self.speaker.beep(frequency=1200, duration=200)
            sleep(0.1)
            self.speaker.beep(frequency=1400, duration=200)
            
            # Store scan data locally
            self._store_scan_data(scan_data)
            
            return scan_data
            
        except Exception as e:
            print("Error during terrain scan: {}".format(e))
            self.speaker.beep(frequency=200, duration=1000)  # Error beep
            return None
            
        finally:
            self.scan_in_progress = False
            self.tank_drive.stop()  # Ensure robot is stopped

    def _calculate_measurement_confidence(self, distance, heading_error, rotation_success):
        """Calculate confidence score for a measurement"""
        confidence = 1.0
        
        # Distance factor (closer measurements are more reliable)
        if distance is not None:
            if distance < 100:  # Very close
                distance_factor = 0.95
            elif distance < 500:  # Close
                distance_factor = 1.0
            elif distance < 2000:  # Medium
                distance_factor = 0.9
            else:  # Far
                distance_factor = 0.8
        else:
            distance_factor = 0.0  # No measurement
        
        # Heading accuracy factor
        heading_factor = max(0.5, 1.0 - (abs(heading_error) / 10.0))
        
        # Rotation success factor
        rotation_factor = 1.0 if rotation_success else 0.7
        
        return confidence * distance_factor * heading_factor * rotation_factor

    def _calculate_avg_heading_error(self, scan_points):
        """Calculate average heading error for scan quality assessment"""
        if not scan_points:
            return 0.0
        
        errors = [abs(point["heading_error"]) for point in scan_points]
        return sum(errors) / len(errors)

    def _store_scan_data(self, scan_data):
        """Store scan data locally for cloud retrieval"""
        try:
            scan_id = scan_data["scan_id"]
            scan_file = os.path.join(self.storage_path, "{}.json".format(scan_id))
            
            # Write scan data to file
            with open(scan_file, 'w') as f:
                json.dump(scan_data, f, indent=2)
            
            # Update scan index
            self.scan_index[scan_id] = {
                "file_path": scan_file,
                "timestamp": scan_data["timestamp"],
                "status": "pending_cloud_retrieval",
                "scan_type": scan_data["scan_type"],
                "data_points": len(scan_data["scan_points"]),
                "file_size_bytes": os.path.getsize(scan_file),
                "success_rate": scan_data["scan_quality"]["success_rate"]
            }
            
            # Add to pending queue
            self.pending_scans.append(scan_id)
            
            # Save updated index
            self._save_scan_index()
            
            print("Scan data stored: {} ({} bytes)".format(scan_file, os.path.getsize(scan_file)))
            
        except Exception as e:
            print("Error storing scan data: {}".format(e))

    def start_automatic_scanning(self, interval_seconds=None):
        """
        Start automatic terrain scanning at regular intervals.
        
        Args:
            interval_seconds: Seconds between scans (uses default if None)
        """
        if self.auto_scan_enabled:
            print("Automatic scanning already enabled")
            return
        
        if interval_seconds is not None:
            self.auto_scan_interval = interval_seconds
        
        self.auto_scan_enabled = True
        
        # Start automatic scanning thread
        self.auto_scan_thread = threading.Thread(target=self._auto_scan_loop, daemon=True)
        self.auto_scan_thread.start()
        
        print("Automatic terrain scanning started (interval: {}s)".format(self.auto_scan_interval))
        self.speaker.beep(frequency=800, duration=200)

    def stop_automatic_scanning(self):
        """Stop automatic terrain scanning"""
        if not self.auto_scan_enabled:
            print("Automatic scanning not running")
            return
        
        self.auto_scan_enabled = False
        
        # Cancel current scan if in progress
        if self.scan_in_progress:
            self.scan_in_progress = False
            print("Cancelling current scan...")
        
        print("Automatic terrain scanning stopped")
        self.speaker.beep(frequency=400, duration=200)

    def _auto_scan_loop(self):
        """Main loop for automatic scanning"""
        print("Automatic scanning loop started")
        
        while self.auto_scan_enabled:
            try:
                # Perform scan
                scan_result = self.perform_scan("full_360")
                
                if scan_result:
                    print("Automatic scan completed: {}".format(scan_result["scan_id"]))
                else:
                    print("Automatic scan failed")
                
                # Manage storage
                self._manage_storage_capacity()
                
                # Wait for next scan interval
                sleep_time = 0
                while sleep_time < self.auto_scan_interval and self.auto_scan_enabled:
                    sleep(1)
                    sleep_time += 1
                
            except Exception as e:
                print("Error in automatic scan loop: {}".format(e))
                sleep(30)  # Wait before retry

    def cancel_current_scan(self):
        """Cancel the currently running scan"""
        if self.scan_in_progress:
            self.scan_in_progress = False
            self.tank_drive.stop()
            print("Current scan cancelled")
            self.speaker.beep(frequency=400, duration=300)
        else:
            print("No scan in progress to cancel")

    def get_scan_status(self):
        """Get current scanning status and statistics"""
        return {
            "scan_in_progress": self.scan_in_progress,
            "current_scan_id": self.current_scan_id,
            "auto_scan_enabled": self.auto_scan_enabled,
            "auto_scan_interval": self.auto_scan_interval,
            "total_scans": len(self.scan_index),
            "pending_scans": len(self.pending_scans),
            "storage_info": self._get_storage_info(),
            "device_status": {
                "gyro_available": self.device_manager.is_device_available("gyro_sensor"),
                "ultrasonic_available": self.device_manager.is_device_available("us_sensor"),
                "drive_available": self.device_manager.are_devices_available(["drive_L_motor", "drive_R_motor"])
            }
        }

    def get_scan_inventory(self):
        """Get inventory of available scans for cloud retrieval"""
        return {
            "robot_id": "ev3_robot_001",
            "current_timestamp": time(),
            "pending_scans": list(self.pending_scans),
            "scan_summary": {
                scan_id: {
                    "timestamp": self.scan_index[scan_id]["timestamp"],
                    "data_points": self.scan_index[scan_id]["data_points"],
                    "scan_type": self.scan_index[scan_id]["scan_type"],
                    "file_size_bytes": self.scan_index[scan_id]["file_size_bytes"],
                    "success_rate": self.scan_index[scan_id]["success_rate"]
                }
                for scan_id in self.pending_scans if scan_id in self.scan_index
            },
            "storage_status": self._get_storage_info()
        }

    def get_scan_data(self, scan_id):
        """Retrieve specific scan data for cloud retrieval"""
        if scan_id not in self.scan_index:
            return None
        
        try:
            scan_file = self.scan_index[scan_id]["file_path"]
            with open(scan_file, 'r') as f:
                scan_data = json.load(f)
            
            # Mark as being retrieved
            self.scan_index[scan_id]["status"] = "being_retrieved"
            self.scan_index[scan_id]["retrieval_timestamp"] = time()
            self._save_scan_index()
            
            return scan_data
            
        except Exception as e:
            print("Error loading scan data {}: {}".format(scan_id, e))
            return None

    def confirm_scan_retrieved(self, scan_id):
        """Confirm that cloud has successfully retrieved scan data"""
        if scan_id in self.scan_index:
            # Mark as successfully retrieved
            self.scan_index[scan_id]["status"] = "retrieved_by_cloud"
            self.scan_index[scan_id]["cloud_retrieval_timestamp"] = time()
            
            # Remove from pending queue
            if scan_id in self.pending_scans:
                self.pending_scans.remove(scan_id)
            
            self._save_scan_index()
            print("Scan {} confirmed retrieved by cloud".format(scan_id))
            return True
        
        return False

    def _get_storage_info(self):
        """Get current storage usage information"""
        try:
            total_size = 0
            file_count = 0
            
            for scan_id, info in self.scan_index.items():
                if os.path.exists(info["file_path"]):
                    total_size += info["file_size_bytes"]
                    file_count += 1
            
            return {
                "used_mb": round(total_size / (1024 * 1024), 2),
                "total_files": file_count,
                "pending_scans": len(self.pending_scans),
                "storage_path": self.storage_path
            }
            
        except Exception as e:
            print("Error calculating storage info: {}".format(e))
            return {"used_mb": 0, "total_files": 0, "pending_scans": 0}

    def _manage_storage_capacity(self):
        """Manage storage capacity by cleaning up old retrieved scans"""
        try:
            storage_info = self._get_storage_info()
            
            if storage_info["used_mb"] > self.max_storage_mb:
                print("Storage limit exceeded ({:.1f}MB), cleaning up...".format(storage_info["used_mb"]))
                
                # Find old retrieved scans for cleanup
                current_time = time()
                cleanup_candidates = []
                
                for scan_id, info in self.scan_index.items():
                    if (info["status"] == "retrieved_by_cloud" and 
                        "cloud_retrieval_timestamp" in info):
                        
                        age_hours = (current_time - info["cloud_retrieval_timestamp"]) / 3600
                        if age_hours > self.retention_hours:
                            cleanup_candidates.append((scan_id, age_hours))
                
                # Sort by age (oldest first)
                cleanup_candidates.sort(key=lambda x: x[1], reverse=True)
                
                # Remove old scans until under storage limit
                for scan_id, age in cleanup_candidates:
                    if storage_info["used_mb"] <= self.max_storage_mb * 0.8:  # 20% buffer
                        break
                    
                    self._delete_scan_data(scan_id)
                    storage_info = self._get_storage_info()
                    print("Cleaned up scan {} (age: {:.1f}h)".format(scan_id, age))
                    
        except Exception as e:
            print("Error managing storage capacity: {}".format(e))

    def _delete_scan_data(self, scan_id):
        """Delete scan data file and remove from index"""
        try:
            if scan_id in self.scan_index:
                scan_file = self.scan_index[scan_id]["file_path"]
                
                if os.path.exists(scan_file):
                    os.remove(scan_file)
                
                del self.scan_index[scan_id]
                
                if scan_id in self.pending_scans:
                    self.pending_scans.remove(scan_id)
                
                self._save_scan_index()
                
        except Exception as e:
            print("Error deleting scan data {}: {}".format(scan_id, e))

    def cleanup(self):
        """Cleanup resources and stop all scanning activities"""
        print("TerrainScanner cleanup initiated")
        
        # Stop automatic scanning
        self.stop_automatic_scanning()
        
        # Cancel current scan
        self.cancel_current_scan()
        
        # Wait for threads to finish
        if self.auto_scan_thread and self.auto_scan_thread.is_alive():
            self.auto_scan_thread.join(timeout=2.0)
        
        # Final storage save
        self._save_scan_index()
        
        print("TerrainScanner cleanup complete")
