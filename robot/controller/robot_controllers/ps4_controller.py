import math
from event_handler import EventHandler
import threading
import struct
# import traceback  # Commented out due to EV3 compatibility issues
from time import sleep
from error_reporting import report_controller_error, report_exception

MIN_JOYSTICK_MOVE = 100  # The minimum value of joystick move to be considered as a move (for -1000 to 1000 range)
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
RIGHT_STICK_X = 3;
RIGHT_STICK_Y = 4;
L2_TRIGGER = 3;
R2_TRIGGER = 4;


def printIn(x,y,text):
    #Prints text in str value in x,y coordinates on console
    if __debug__:
        print("\033["+str(y)+";"+str(x)+"H"+text)


# Purpose: A class for handling PS4 controller events.
class PS4Controller(EventHandler, threading.Thread):

    # A flag for stopping the main loop of handling PS4 controller events
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
    def __str__(self):
        return "PS4 controller for EV3"; 
    
    # This is the main loop of handling PS4 controller events. It is run in a separate thread.
    def run(self):
       # Open the Gamepad event file:
        # /dev/input/event3 is for PS3 gamepad
        # /dev/input/event4 is for PS4 gamepad
        # look at contents of /proc/bus/input/devices if either one of them doesn't work.
        # use 'cat /proc/bus/input/devices' and look for the event file.
        infile_path = "/dev/input/event4"
        
        try:
            # Check if PS4 controller device file exists
            print("Checking for PS4 controller...")
            
            # Try to check if file exists (simple way for MicroPython)
            try:
                test_file = open(infile_path, "rb")
                test_file.close()
                print("PS4 controller device found at", infile_path)
            except Exception as e:
                print("PS4 controller device not found at", infile_path)
                report_controller_error("PS4Controller", "device file check", e, infile_path)
                print("Trying alternative paths...")
                # Try alternative event files
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
                    raise OSError("No PS4 controller found")
            
            print("Attempting to connect to PS4 controller at", infile_path)
            # open file in binary mode
            in_file = open(infile_path, "rb")
            print("PS4 controller connected successfully!")
            self.connected = True  # Mark as connected

            # Read from the file
            # long int, long int, unsigned short, unsigned short, unsigned int
            FORMAT = 'llHHI'    
            EVENT_SIZE = struct.calcsize(FORMAT)
            event = in_file.read(EVENT_SIZE)
            i = 0;
            
            if __debug__:
                print("Starting the PS4 loop...")            
            while event and not self.stopped:
                (tv_sec, tv_usec, ev_type, code, value) = struct.unpack(FORMAT, event)


                #  Handle PS4 controller right joystick
                if ev_type == EV_ABS and (code == RIGHT_STICK_X or code == RIGHT_STICK_Y):
                    if(code == RIGHT_STICK_Y):
                        self.r_forward = -1* self.scale(value, (0,255), (-100,100))
                        # printIn(35,11,"Right y-axis:" + str(self.r_forward) + "   ")                        
                    if(code == RIGHT_STICK_X):
                        self.r_left = -1 * self.scale(value, (0,255), (-100,100))
                        # printIn(35,10,"Right x-axis:" + str(self.r_left) + "   ")   

                    # Apply deadzone filtering to right joystick too
                    if abs(self.r_forward) < 50:  # Increased deadzone for right joystick
                        self.r_forward = 0
                    if abs(self.r_left) < 50:
                        self.r_left = 0
                        
                    # Always trigger right joystick events to ensure stop commands are sent
                    # Remove throttling to prevent race conditions with turret control
                    self.trigger("right_joystick");

                # Handle PS4 controller left joystick
                if ev_type == EV_ABS and (code == LEFT_STICK_X or code == LEFT_STICK_Y):
                    # Store previous values to detect significant changes
                    prev_l_forward = self.l_forward
                    prev_l_left = self.l_left
                    
                    if(code == LEFT_STICK_Y and value < 255):                                             
                        # Invert Y-axis: joystick up (value=0) should give positive l_forward
                        self.l_forward = self.scale(value, (0,255), (1000,-1000))
                        # Apply deadzone filtering immediately
                        if abs(self.l_forward) < MIN_JOYSTICK_MOVE:
                            self.l_forward = 0
                        # printIn(1,11,"Left y-axis:" + str(self.l_forward)+ "   ")   
                        
                    if(code == LEFT_STICK_X and value < 255):
                        self.l_left = self.scale(value, (0,255), (-1000,1000))
                        # Apply deadzone filtering immediately
                        if abs(self.l_left) < MIN_JOYSTICK_MOVE:
                            self.l_left = 0
                        # printIn(1,10,"Left x-axis:" + str(self.l_left ) + "   ")                        

                    # Always trigger joystick events to ensure real-time response
                    # Remove throttling to prevent race conditions
                    self.trigger("left_joystick");




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

                # Handle PS4 controller buttons
                if ev_type == EV_KEY:
                    # Button code debug output removed for performance
                    #TODO: Change it all into case statement
                    # Handle PS4 controller X button
                    if code == 304 and value == 1:
                        self.trigger("cross_button");
                    #Handle PS4 controller CIRCLE(305) button
                    if code == 305 and value == 1:
                        self.trigger("triangle_button");
                    #Handle PS4 controller SQUARE(308) button
                    if code == 308 and value == 1:
                        self.trigger("triangle_button");
                    # Handle PS4 controller TRIANGLE(307) button
                    if code == 307 and value == 1:
                        self.trigger("triangle_button");
                    

                    #Handle PS4 controller L1(310) button
                    if code == 310 and value == 1:
                        self.trigger("l1_button");
                    #Handle PS4 controller L2(312) button
                    if code == 312 and value == 1:
                        self.trigger("l2_button");
                    #Handle PS4 controller R1(311) button
                    if code == 311 and value == 1:
                        self.trigger("r1_button");
                    #Handle PS4 controller R2(313) button
                    if code == 313 and value == 1:
                        self.trigger("r2_button");

                    # TODO: Handle PS4 controller SHARE(314) button
                    # TODO: Handle PS4 controller OPTIONS(315) button
                    if code == 315 and value == 1:
                        self.trigger("options_button");
                    # TODO: Handle PS4 controller PS(316) button
                    # TODO: Handle PS4 controller L3(317) button
                    # TODO: Handle PS4 controller R3(318) button

                sleep(0.001)            
                # Finally, read another event
                event = in_file.read(EVENT_SIZE)
                

            in_file.close()
        except OSError as e:
            # Handle both FileNotFoundError and PermissionError under OSError
            error_msg = str(e)
            report_controller_error("PS4Controller", "device access", e, infile_path)
            if "No such file" in error_msg or "No PS4 controller found" in error_msg:
                print("ERROR: PS4 controller not found!")
                print("Please ensure:")
                print("1. PS4 controller is paired with EV3 via Bluetooth")
                print("2. Controller is turned on and connected")
                print("3. Check 'cat /proc/bus/input/devices' for correct event file")
                print("Program will continue without controller input.")
            elif "Permission denied" in error_msg:
                print("ERROR: Permission denied accessing PS4 controller")
                print("Try running as root or check device permissions")
            else:
                print("ERROR: PS4 controller access failed:", error_msg)
                print("Check device connection and permissions")
            self.connected = False
        except Exception as e:
            report_exception("PS4Controller.run()", "event processing loop", e, "Main controller event loop")
            print("Check Bluetooth connection and try again")
            self.connected = False

    def handle_event(self, event):
        # Override this method to handle PS4 controller events
        pass
 
    def stop(self):
        self.stopped = True;
    
    def is_connected(self):
        """Check if the PS4 controller is connected and working"""
        return self.connected

    # A helper function for converting stick values (0 - 255)
    # to more usable numbers (-100 - 100)6
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

