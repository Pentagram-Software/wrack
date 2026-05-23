import math
from event_handler import EventHandler
import threading
import struct
# import traceback  # Commented out due to EV3 compatibility issues
from error_reporting import report_controller_error, report_exception

MIN_JOYSTICK_MOVE = 100  # The minimum value of joystick move to be considered as a move (for -1000 to 1000 range)

# Joystick axis ranges reported by Linux evdev (PS4 = 8-bit, PS5/DualSense = 16-bit)
AXIS_RANGE_8BIT = (0, 255)
AXIS_RANGE_16BIT = (0, 65535)
AXIS_SENTINEL_VALUES = (4294967295, 4294967294)

    #const values representing particular events 

#ev_type
EV_SYN = 0;
EV_KEY = 1;
EV_ABS = 3;

#ev_code (for ev_type == EV_KEY)
X_BUTTON = 304;
CIRCLE_BUTTON = 305;
TRIANGLE_BUTTON = 307;
SQUARE_BUTTON = 308;

#ev_code (for ev_type == EV_ABS)
LEFT_STICK_X = 0;
LEFT_STICK_Y = 1;
L2_TRIGGER = 2;    # ABS_Z  (analog L2 axis, range 0-255)
RIGHT_STICK_X = 3;
RIGHT_STICK_Y = 4;
R2_TRIGGER = 5;    # ABS_RZ (analog R2 axis, range 0-255)

# Known PlayStation controller device names as reported by the Linux input subsystem.
# Used to locate the correct /dev/input/event* device by scanning
# /proc/bus/input/devices rather than relying on hardcoded event numbers.
KNOWN_CONTROLLER_NAMES = [
    "DualSense Wireless Controller",                              # PS5 (generic/USB)
    "Sony Interactive Entertainment DualSense Wireless Controller",  # PS5 (Bluetooth)
    "Sony Interactive Entertainment Wireless Controller",         # PS4 (Bluetooth)
    "Sony Computer Entertainment Wireless Controller",            # PS4 (older firmware)
    "Wireless Controller",                                        # Generic fallback (PS4/PS5)
]

# Sub-strings that identify non-gamepad input sub-devices exposed by the Linux
# Bluetooth HID driver (touchpad, motion sensors, accelerometer).  These are
# intentionally excluded so that find_controller_device() only returns the path
# to the main gamepad event node and never the touchpad or IMU node.
EXCLUDED_DEVICE_KEYWORDS = [
    "touchpad",
    "motion sensors",
    "motion sensor",
    "accelerometer",
]


def find_controller_device():
    """Scan /proc/bus/input/devices to find a connected PlayStation controller.

    Tries each name in KNOWN_CONTROLLER_NAMES (most-specific first) and returns
    the first matching /dev/input/event* path.  Non-gamepad sub-devices (touchpad,
    motion sensors) are explicitly skipped.  Returns None when no device is found
    or when the proc file cannot be read (e.g. in unit-test environments).
    """
    try:
        with open("/proc/bus/input/devices", "r") as f:
            content = f.read()

        # Each device entry is separated by a blank line
        blocks = content.strip().split('\n\n')
        for block in blocks:
            lines = block.strip().split('\n')
            device_name = None
            event_file = None

            for line in lines:
                if line.startswith('N: Name='):
                    device_name = line.split('Name=')[1].strip().strip('"')
                elif line.startswith('H: Handlers='):
                    handlers = line.split('Handlers=')[1].strip()
                    for handler in handlers.split():
                        if handler.startswith('event'):
                            event_file = '/dev/input/' + handler
                            break

            if device_name and event_file:
                device_name_lower = device_name.lower()

                # Skip non-gamepad sub-devices (touchpad, IMU, etc.) before
                # checking against KNOWN_CONTROLLER_NAMES.  Without this guard
                # the substring check below would match e.g. "... Wireless
                # Controller Touchpad" and return the wrong event node.
                if any(kw in device_name_lower for kw in EXCLUDED_DEVICE_KEYWORDS):
                    continue

                for known_name in KNOWN_CONTROLLER_NAMES:
                    if known_name.lower() in device_name_lower:
                        return event_file

    except Exception as e:
        print("Warning: Could not scan /proc/bus/input/devices:", e)

    return None


def printIn(x,y,text):
    #Prints text in str value in x,y coordinates on console
    if __debug__:
        print("\033["+str(y)+";"+str(x)+"H"+text)


# Purpose: A class for handling PlayStation controller events (PS4 DualShock 4 and PS5 DualSense).
# Both controllers report identical Linux evdev button/axis codes, so the same
# event-handling logic works for either device.  Device detection is done by
# name via find_controller_device() so that the correct /dev/input/event* file
# is opened regardless of which slot the kernel assigned.
class PS4Controller(EventHandler, threading.Thread):

    # A flag for stopping the main loop of handling PlayStation controller events
    stopped = False;
    connected = False;  # Track connection status
    l_left = 0;
    l_forward = 0;
    r_left = 0;
    r_forward = 0;
    
    # Event throttling to prevent flooding
    last_joystick_event_time = 0;




    # Constructor
    def __init__(self):
        super().__init__()
        # Initialize joystick values to prevent first-event issues
        self.l_left = 0
        self.l_forward = 0
        self.r_left = 0
        self.r_forward = 0
        self.last_joystick_event_time = 0
        self.connected = False
        self._axis_range = None
    def __str__(self):
        return "PlayStation controller (PS4/PS5) for EV3"; 
    
    # This is the main loop of handling PlayStation controller events. It is run in a separate thread.
    def run(self):
       # Open the Gamepad event file.
        # First try to detect the device by name via /proc/bus/input/devices so that
        # this works with both PS4 DualShock 4 and PS5 DualSense controllers without
        # depending on a hardcoded event number.
        # If name-based detection fails, fall back to probing the most common paths.
        infile_path = "/dev/input/event4"
        
        try:
            print("Searching for PlayStation controller (PS4/PS5)...")

            # Primary: detect by device name
            detected_path = find_controller_device()
            if detected_path:
                print("PlayStation controller detected at", detected_path)
                infile_path = detected_path
            else:
                # Fallback: probe fixed event paths
                print("Name-based detection failed, probing fixed event paths...")
                try:
                    test_file = open(infile_path, "rb")
                    test_file.close()
                    print("Controller device found at", infile_path)
                except Exception as e:
                    print("Controller not found at", infile_path)
                    report_controller_error("PS4Controller", "device file check", e, infile_path)
                    print("Trying alternative paths...")
                    for alt_path in ["/dev/input/event3", "/dev/input/event5", "/dev/input/event2"]:
                        try:
                            test_file = open(alt_path, "rb")
                            test_file.close()
                            infile_path = alt_path
                            print("Found controller at", alt_path)
                            break
                        except Exception as e:
                            print("Failed to access", alt_path)
                            report_controller_error("PS4Controller", "alternative path check", e, alt_path)
                            continue
                    else:
                        raise OSError("No PlayStation controller found")
            
            print("Attempting to connect to PlayStation controller at", infile_path)
            # open file in binary mode
            in_file = open(infile_path, "rb")
            print("PlayStation controller connected successfully!")
            self.connected = True  # Mark as connected

            # Read from the file
            # long int, long int, unsigned short, unsigned short, unsigned int
            FORMAT = 'llHHI'    
            EVENT_SIZE = struct.calcsize(FORMAT)
            event = in_file.read(EVENT_SIZE)
            i = 0;
            
            if __debug__:
                print("Starting the PlayStation controller loop...")            
            while event and not self.stopped:
                (tv_sec, tv_usec, ev_type, code, value) = struct.unpack(FORMAT, event)


                #  Handle right joystick
                if ev_type == EV_ABS and (code == RIGHT_STICK_X or code == RIGHT_STICK_Y):
                    if code == RIGHT_STICK_Y:
                        scaled = self._scale_axis(value, (-100, 100))
                        if scaled is not None:
                            self.r_forward = -1 * scaled
                    if code == RIGHT_STICK_X:
                        scaled = self._scale_axis(value, (-100, 100))
                        if scaled is not None:
                            self.r_left = -1 * scaled

                    if abs(self.r_forward) < 50:
                        self.r_forward = 0
                    if abs(self.r_left) < 50:
                        self.r_left = 0

                    self.trigger("right_joystick")

                # Handle left joystick (PS4 8-bit and PS5/DualSense 16-bit axes)
                if ev_type == EV_ABS and (code == LEFT_STICK_X or code == LEFT_STICK_Y):
                    if code == LEFT_STICK_Y:
                        scaled = self._scale_axis(value, (1000, -1000))
                        if scaled is not None:
                            self.l_forward = scaled
                            if abs(self.l_forward) < MIN_JOYSTICK_MOVE:
                                self.l_forward = 0

                    if code == LEFT_STICK_X:
                        scaled = self._scale_axis(value, (-1000, 1000))
                        if scaled is not None:
                            self.l_left = scaled
                            if abs(self.l_left) < MIN_JOYSTICK_MOVE:
                                self.l_left = 0

                    self.trigger("left_joystick")




                #Handle the pad (D-pad)
                if ev_type == 3 and code >15:
                    # Handle left/right arrows (horizontal axis)
                    if(code == 16 and value == 1):
                        self.trigger("left_arrow_pressed");
                    if(code == 16 and value == 0):
                        self.trigger("lr_arrow_released");
                    if(code == 16 and value == 4294967295):
                        self.trigger("right_arrow_pressed");
                    
                    # Handle up/down arrows (vertical axis)
                    if(code == 17 and value == 1):
                        self.trigger("up_arrow_pressed");
                    if(code == 17 and value == 0):
                        self.trigger("ud_arrow_released");
                    if(code == 17 and value == 4294967295):
                        self.trigger("down_arrow_pressed");

                # Handle controller buttons
                # Note: PS4 DualShock 4 and PS5 DualSense use the same evdev key codes
                # for all action buttons, shoulder buttons, triggers, and the d-pad.
                if ev_type == EV_KEY:
                    # Cross (X) button — BTN_SOUTH (304)
                    if code == X_BUTTON and value == 1:
                        self.trigger("cross_button");
                    # Circle button — BTN_EAST (305)
                    if code == CIRCLE_BUTTON and value == 1:
                        self.trigger("circle_button");
                    # Triangle button — BTN_NORTH (307)
                    if code == TRIANGLE_BUTTON and value == 1:
                        self.trigger("triangle_button");
                    # Square button — BTN_WEST (308)
                    if code == SQUARE_BUTTON and value == 1:
                        self.trigger("square_button");

                    # L1 button — BTN_TL (310)
                    if code == 310 and value == 1:
                        self.trigger("l1_button");
                    # L2 button — BTN_TL2 (312)
                    if code == 312 and value == 1:
                        self.trigger("l2_button");
                    # R1 button — BTN_TR (311)
                    if code == 311 and value == 1:
                        self.trigger("r1_button");
                    # R2 button — BTN_TR2 (313)
                    if code == 313 and value == 1:
                        self.trigger("r2_button");

                    # Options button — BTN_START (315)
                    # PS4: Options | PS5: Options
                    if code == 315 and value == 1:
                        self.trigger("options_button");
                    # Share/Create button — BTN_SELECT (314)
                    # PS4: Share | PS5: Create
                    # TODO: Handle Share/Create button (314) if needed
                    # PS/Home button — BTN_MODE (316)
                    # TODO: Handle PS/Home button (316) if needed
                    # L3 (left stick click) — BTN_THUMBL (317)
                    # TODO: Handle L3 (317) if needed
                    # R3 (right stick click) — BTN_THUMBR (318)
                    # TODO: Handle R3 (318) if needed

                # Finally, read another event
                event = in_file.read(EVENT_SIZE)
                

            in_file.close()
        except OSError as e:
            # Handle both FileNotFoundError and PermissionError under OSError
            error_msg = str(e)
            report_controller_error("PS4Controller", "device access", e, infile_path)
            if "No such file" in error_msg or "No PlayStation controller found" in error_msg:
                print("ERROR: PlayStation controller not found!")
                print("Please ensure:")
                print("1. PS4 or PS5 controller is paired with EV3 via Bluetooth")
                print("2. Controller is turned on and connected")
                print("3. Check 'cat /proc/bus/input/devices' for correct event file")
                print("Program will continue without controller input.")
            elif "Permission denied" in error_msg:
                print("ERROR: Permission denied accessing PlayStation controller")
                print("Try running as root or check device permissions")
            else:
                print("ERROR: PlayStation controller access failed:", error_msg)
                print("Check device connection and permissions")
            self.connected = False
        except Exception as e:
            report_exception("PS4Controller.run()", "event processing loop", e, "Main controller event loop")
            print("Check Bluetooth connection and try again")
            self.connected = False

    def handle_event(self, event):
        # Override this method to handle PlayStation controller events
        pass
 
    def stop(self):
        self.stopped = True;
    
    def is_connected(self):
        """Check if the PlayStation controller is connected and working"""
        return self.connected

    def _is_axis_sentinel(self, value):
        """Ignore release sentinel events; 255 is only a sentinel on 8-bit PS4 axes."""
        if value in AXIS_SENTINEL_VALUES:
            return True
        if self._get_axis_range() == AXIS_RANGE_8BIT and value == 255:
            return True
        return False

    def _detect_axis_range(self, value):
        """Auto-detect 8-bit (PS4) vs 16-bit (PS5/DualSense) stick axis range."""
        if self._axis_range is not None or self._is_axis_sentinel(value):
            return
        if value > 1000:
            self._axis_range = AXIS_RANGE_16BIT
        else:
            self._axis_range = AXIS_RANGE_8BIT

    def _get_axis_range(self):
        return self._axis_range or AXIS_RANGE_8BIT

    def _scale_axis(self, value, dst):
        """
        Scale a raw evdev axis value to the requested output range.

        Returns None for sentinel/release values that should be ignored.
        """
        if self._is_axis_sentinel(value):
            return None

        self._detect_axis_range(value)
        return self.scale(value, self._get_axis_range(), dst)

    def scale(self, val, src, dst):
        """
        Scale the given value from the scale of src to the scale of dst.
    
        val: float or int
        src: tuple
        dst: tuple
   
        example: print(scale(99, (0.0, 99.0), (-1.0, +1.0)))
        """
        # Prevent divide by zero if source range is invalid
        src_range = src[1] - src[0]
        if src_range == 0:
            print("Warning: Invalid source range in scale function")
            return dst[0]  # Return destination minimum as fallback
        
        return (float(val-src[0]) / src_range) * (dst[1]-dst[0])+dst[0]

    def onLeftJoystickMove(self, callback):
        self.on("left_joystick", callback)

    def onRightJoystickMove(self, callback):
        self.on("right_joystick", callback)

    def onSquareButton(self, callback):
        self.on("square_button", callback)

    def onCrossButton(self, callback):
        self.on("cross_button", callback)

    def onTriangleButton(self, callback):
        self.on("triangle_button", callback)

    def onCircleButton(self, callback):
        self.on("circle_button", callback)

    def onL1Button(self, callback):
        self.on("l1_button", callback)

    def onR1Button(self, callback):
        self.on("r1_button", callback)

    def onL2Button(self, callback):
        self.on("l2_button", callback)

    def onR2Button(self, callback):
        self.on("r2_button", callback)

    def onOptionsButton(self, callback):
        self.on("options_button", callback)

    def onLeftArrowPressed(self, callback):
        self.on("left_arrow_pressed", callback)

    def onLRArrowReleased(self, callback):
        self.on("lr_arrow_released", callback)

    def onRightArrowPressed(self, callback):
        self.on("right_arrow_pressed", callback)
    
    def onUpArrowPressed(self, callback):
        self.on("up_arrow_pressed", callback)

    def onUDArrowReleased(self, callback):
        self.on("ud_arrow_released", callback)

    def onDownArrowPressed(self, callback):
        self.on("down_arrow_pressed", callback)
