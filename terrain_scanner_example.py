#!/usr/bin/env pybricks-micropython

"""
TerrainScanner Usage Example

This example demonstrates how to use the TerrainScanner class
for terrain mapping with movement-based scanning.

Example usage scenarios:
1. Manual single scan
2. Automatic continuous scanning
3. Network-controlled scanning
4. Cloud data retrieval simulation
"""

from pybricks.hubs import EV3Brick
from pybricks.parameters import Port
from pybricks.ev3devices import Motor, UltrasonicSensor, GyroSensor
from time import sleep

# Import your existing modules
from DeviceManager import DeviceManager
from TankDriveSystem import TankDriveSystem
from TerrainScanner import TerrainScanner

def terrain_scanner_demo():
    """Demonstrate TerrainScanner functionality"""
    
    print("=== TerrainScanner Demo ===")
    
    # Initialize EV3 and device manager
    ev3 = EV3Brick()
    device_manager = DeviceManager()
    
    # Initialize required devices
    drive_L_motor = device_manager.try_init_device(Motor, Port.A, "drive_L_motor")
    drive_R_motor = device_manager.try_init_device(Motor, Port.D, "drive_R_motor")
    us_sensor = device_manager.try_init_device(UltrasonicSensor, Port.S2, "us_sensor")
    gyro_sensor = device_manager.try_init_device(GyroSensor, Port.S3, "gyro_sensor")
    
    # Initialize tank drive system
    tank_drive = TankDriveSystem(device_manager)
    tank_drive.initialize()
    
    # Check if required sensors are available
    if not device_manager.are_devices_available(["us_sensor", "gyro_sensor"]):
        print("ERROR: Required sensors not available for terrain scanning")
        print("- Ultrasonic sensor (Port S2): {}".format(
            device_manager.is_device_available("us_sensor")))
        print("- Gyro sensor (Port S3): {}".format(
            device_manager.is_device_available("gyro_sensor")))
        return
    
    # Initialize TerrainScanner
    terrain_scanner = TerrainScanner(device_manager, tank_drive, ev3.speaker)
    
    print("TerrainScanner initialized successfully!")
    print("Available commands:")
    print("1. Single scan")
    print("2. Quick scan")
    print("3. Start automatic scanning")
    print("4. Stop automatic scanning")
    print("5. Get scanner status")
    print("6. Get scan inventory")
    print("7. Simulate cloud data retrieval")
    print("8. Exit")
    
    try:
        while True:
            # Simple menu system using EV3 buttons
            print("\nPress EV3 button to select option:")
            print("UP: Single scan, DOWN: Quick scan, LEFT: Auto scan, RIGHT: Status, CENTER: Exit")
            
            # Wait for button press
            pressed = []
            while not pressed:
                pressed = ev3.buttons.pressed()
                sleep(0.1)
            
            if pressed[0] == "up":
                # Perform single terrain scan
                print("Starting single terrain scan...")
                scan_result = terrain_scanner.perform_scan("full_360")
                if scan_result:
                    print("Scan completed: {} points collected".format(
                        len(scan_result["scan_points"])))
                    print("Success rate: {:.1%}".format(
                        scan_result["scan_quality"]["success_rate"]))
                else:
                    print("Scan failed!")
                    
            elif pressed[0] == "down":
                # Perform quick scan
                print("Starting quick terrain scan...")
                scan_result = terrain_scanner.perform_scan("quick_8_point")
                if scan_result:
                    print("Quick scan completed: {} points collected".format(
                        len(scan_result["scan_points"])))
                else:
                    print("Quick scan failed!")
                    
            elif pressed[0] == "left":
                # Toggle automatic scanning
                status = terrain_scanner.get_scan_status()
                if status["auto_scan_enabled"]:
                    terrain_scanner.stop_automatic_scanning()
                    print("Automatic scanning stopped")
                else:
                    terrain_scanner.start_automatic_scanning(interval_seconds=60)  # 1 minute for demo
                    print("Automatic scanning started (60 second interval)")
                    
            elif pressed[0] == "right":
                # Get scanner status
                status = terrain_scanner.get_scan_status()
                print("=== Scanner Status ===")
                print("Scan in progress: {}".format(status["scan_in_progress"]))
                print("Auto scan enabled: {}".format(status["auto_scan_enabled"]))
                print("Total scans: {}".format(status["total_scans"]))
                print("Pending scans: {}".format(status["pending_scans"]))
                print("Storage: {:.1f}MB".format(status["storage_info"]["used_mb"]))
                
                # Get scan inventory
                inventory = terrain_scanner.get_scan_inventory()
                print("=== Scan Inventory ===")
                for scan_id in inventory["pending_scans"]:
                    scan_info = inventory["scan_summary"][scan_id]
                    print("- {}: {} points, {:.1%} success".format(
                        scan_id, scan_info["data_points"], scan_info["success_rate"]))
                        
            elif pressed[0] == "center":
                # Exit demo
                print("Exiting TerrainScanner demo...")
                break
            
            # Wait for button release
            while ev3.buttons.pressed():
                sleep(0.1)
    
    except KeyboardInterrupt:
        print("Demo interrupted by user")
    
    finally:
        # Cleanup
        print("Cleaning up TerrainScanner...")
        terrain_scanner.cleanup()
        print("Demo complete!")

def simulate_cloud_data_retrieval(terrain_scanner):
    """Simulate cloud service retrieving scan data"""
    
    print("=== Simulating Cloud Data Retrieval ===")
    
    # Get scan inventory (what cloud would do first)
    inventory = terrain_scanner.get_scan_inventory()
    print("Cloud: Found {} pending scans".format(len(inventory["pending_scans"])))
    
    # Retrieve each pending scan
    for scan_id in inventory["pending_scans"]:
        print("Cloud: Retrieving scan data for {}".format(scan_id))
        
        # Get scan data (what cloud would download)
        scan_data = terrain_scanner.get_scan_data(scan_id)
        
        if scan_data:
            print("Cloud: Downloaded {} data points".format(len(scan_data["scan_points"])))
            
            # Simulate cloud processing
            print("Cloud: Processing scan data...")
            sleep(1)  # Simulate processing time
            
            # Confirm retrieval (what cloud would do after successful processing)
            success = terrain_scanner.confirm_scan_retrieved(scan_id)
            if success:
                print("Cloud: Confirmed retrieval of {}".format(scan_id))
            else:
                print("Cloud: Failed to confirm retrieval of {}".format(scan_id))
        else:
            print("Cloud: Failed to retrieve scan data for {}".format(scan_id))
    
    print("Cloud data retrieval simulation complete")

if __name__ == "__main__":
    terrain_scanner_demo()
