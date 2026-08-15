import math
from event_handler import EventHandler
import threading
import struct
from time import sleep as _sleep
try:
    from time import time as _time
except ImportError:
    _time = None
# import traceback  # Commented out due to EV3 compatibility issues
from error_reporting import report_controller_error, report_exception
from threading_compat import join_thread, thread_is_alive

MIN_JOYSTICK_MOVE = 100  # The minimum value of joystick move to be considered as a move (for -1000 to 1000 range)

# Rate at which cached stick positions are applied to the motors.
#
# Stick events arrive far faster than the EV3 can act on them: applying every
# one measured ~10ms of motor work per event, capping the read loop at roughly
# 96 events/second, well under the burst rate of a stick in motion.  The loop
# then fell behind, the kernel's fixed evdev ring buffer overflowed, and input
# was discarded outright (measured: 58 SYN_DROPPED in one session, with event
# lag reaching 1.9s).
#
# Coalescing decouples the two: the read loop only ever updates cached axis
# values, and this loop applies the most recent ones at a fixed rate.  No stick
# position is lost, because the newest value always wins and is always applied
# on the next tick.  30Hz is a 33ms worst-case delay, below the threshold where
# steering feels laggy and far below the EV3 motors' own response time.
DEFAULT_CONTROL_LOOP_HZ = 30

# Poll interval used while no stick has moved.  A stick that starts moving is
# picked up within this long instead of 1/DEFAULT_CONTROL_LOOP_HZ, which is
# imperceptible, and in exchange an idle robot stops waking this thread 30
# times a second to find nothing to do.
#
# TODO(PR #110 review, 2026-08-15): this contradicts the 33ms worst-case
# delay DEFAULT_CONTROL_LOOP_HZ documents above -- there is currently no
# wakeup when _mark_stick_dirty() sets a flag while the loop is in this
# sleep, so the real worst case is up to DEFAULT_IDLE_POLL_INTERVAL_S
# (100ms), 3x the documented budget. Narrow in practice (only the
# transition from stillness into movement, not a sustained backlog like
# the SYN_DROPPED issue this PR fixes), but real, and likely to recur as
# small stick corrections with pauses between them during normal driving.
# Planned fix: only back off after N consecutive idle ticks at the full
# 30Hz rate (e.g. ~15 ticks / 500ms of true stillness), so the 33ms
# guarantee holds for anything that resumes soon after stopping and the
# GIL-relief benefit only applies once the robot has been still for a
# while. See PR #110 comments 3789908575 / 3789908579.
DEFAULT_IDLE_POLL_INTERVAL_S = 0.1
# Throttle right-stick debug lines; stick events arrive very frequently.
RIGHT_STICK_DEBUG_INTERVAL_S = 0.25

# How long to poll for a controller connection after starting the reader
# thread, and how often.  The Bluetooth device-open handshake takes a
# variable amount of time (observed to occasionally exceed 500ms), so a
# single fixed sleep-then-check can report "not connected" even though the
# controller connects moments later. Polling avoids both a false negative
# and an unnecessarily long fixed wait when the controller connects quickly.
DEFAULT_CONNECT_TIMEOUT_S = 3.0
DEFAULT_CONNECT_POLL_INTERVAL_S = 0.1

# Joystick axis ranges reported by Linux evdev (PS4 = 8-bit, PS5/DualSense = 16-bit)
AXIS_RANGE_8BIT = (0, 255)
AXIS_RANGE_16BIT = (0, 65535)
AXIS_SENTINEL_VALUES = (4294967295, 4294967294)

    #const values representing particular events 

#ev_type
EV_SYN = 0;
EV_KEY = 1;
EV_ABS = 3;

# EV_SYN code 3: the kernel telling us its per-fd buffer overflowed and
# events were discarded before we could read them.
SYN_DROPPED = 3;

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


def wait_for_connection(
    controller,
    timeout=DEFAULT_CONNECT_TIMEOUT_S,
    poll_interval=DEFAULT_CONNECT_POLL_INTERVAL_S,
    sleep_fn=None,
):
    """Poll ``controller.is_connected()`` until it is ``True`` or *timeout* elapses.

    Intended to be called right after starting the controller's reader
    thread, replacing a single fixed sleep-then-check with fine-grained
    polling so callers don't have to guess a safe fixed delay, while still
    returning promptly once connected rather than always blocking for the
    full timeout.

    Parameters
    ----------
    controller:
        Any object exposing an ``is_connected() -> bool`` method.
    timeout:
        Maximum time (seconds) to wait before giving up.
    poll_interval:
        Time (seconds) between successive ``is_connected()`` checks.
    sleep_fn:
        Sleep function used between polls (defaults to ``time.sleep``).
        Overridable in tests to avoid real delays.

    Returns
    -------
    tuple(bool, float)
        Whether the controller reported connected, and the elapsed wait
        time in seconds.
    """
    if sleep_fn is None:
        sleep_fn = _sleep

    elapsed = 0.0
    while True:
        if controller.is_connected():
            return True, elapsed
        if elapsed >= timeout:
            return False, elapsed
        sleep_fn(poll_interval)
        elapsed += poll_interval


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

    _controller_type = "ps4"

    # Optional InputDiagnostics instance; see set_diagnostics().
    _diagnostics = None;
    _control_running = False;

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
        self._diagnostics = None
        self._control_interval = 1.0 / DEFAULT_CONTROL_LOOP_HZ
        self._idle_interval = DEFAULT_IDLE_POLL_INTERVAL_S
        self._control_thread = None
        self._control_running = False
        # Set by the reader thread when a stick's cached value changes,
        # cleared by the control loop when it applies them.
        self._left_dirty = False
        self._right_dirty = False
        self._debug_input = False
        self._last_right_stick_debug_t = 0
        self._right_stick_debug_count = 0
        self._last_right_stick_debug_xy = None
    def __str__(self):
        return "PlayStation controller (PS4/PS5) for EV3"; 

    def _diag_now(self):
        """Wall clock from the diagnostics' clock, or None when not attached.

        Uses the diagnostics' own clock so timings line up with the lag
        figures it computes, and so tests can inject a fake one.
        """
        if self._diagnostics is None:
            return None
        return self._diagnostics.now()

    @staticmethod
    def _elapsed_ms(start, end):
        if start is None or end is None:
            return None
        return (end - start) * 1000.0

    def set_control_rate(self, hz):
        """Set how often cached stick positions are applied to the motors.

        Lower this if the control loop cannot keep up on a loaded EV3;
        raising it past the point where a tick's motor work exceeds the tick
        interval just reintroduces a backlog on the control thread.
        """
        if hz <= 0:
            raise ValueError("control rate must be positive")
        self._control_interval = 1.0 / hz

    def _mark_stick_dirty(self, event_name):
        """Note that a stick's cached value changed, for the control loop.

        Deliberately does not dispatch: doing the motor work here is what
        starved the read loop (see DEFAULT_CONTROL_LOOP_HZ).
        """
        if event_name == "left_joystick":
            self._left_dirty = True
        else:
            self._right_dirty = True
        if self._diagnostics is not None:
            self._diagnostics.record_coalesced(event_name)

    def _control_tick(self):
        """Apply any changed stick positions once.  Returns events dispatched.

        The dirty flag is cleared *before* dispatching so a stick moved while
        this tick is running is picked up by the next one rather than being
        cleared unseen.
        """
        dispatched = 0
        if self._left_dirty:
            self._left_dirty = False
            self._dispatch("left_joystick")
            dispatched += 1
        if self._right_dirty:
            self._right_dirty = False
            self._dispatch("right_joystick")
            dispatched += 1
        return dispatched

    def _control_loop(self):
        while self._control_running and not self.stopped:
            try:
                dispatched = self._control_tick()
                if not dispatched:
                    # Idle: back off rather than waking 30x/second to find
                    # nothing.  Every wake-up is a GIL handoff contended with
                    # the reader thread, and MicroPython holds the GIL across
                    # C calls, so needless wake-ups cost the reader directly.
                    _sleep(self._idle_interval)
                    continue
            except Exception as e:
                # A callback exception must not kill the control loop and
                # leave the sticks permanently dead for the session, which is
                # what happens when one escapes the read loop.
                report_exception(
                    "PS4Controller._control_loop()",
                    "applying joystick state",
                    e,
                    "Coalesced control loop",
                )
            _sleep(self._control_interval)

    def _start_control_loop(self):
        if self._control_thread is not None:
            return
        self._control_running = True
        # Pybricks MicroPython's Thread() accepts only ``target`` - passing
        # ``daemon``/``name`` raises TypeError (PEN-188).
        self._control_thread = threading.Thread(target=self._control_loop)
        self._control_thread.start()

    def stop_control_loop(self, timeout=2.0):
        """Stop applying joystick input without stopping the reader.

        Called first thing during shutdown so the control loop cannot issue a
        fresh motor command after the motors have already been stopped.  The
        in-flight tick is waited for rather than merely signalled, so that
        guarantee holds even if a tick is mid-dispatch.

        Tracked separately from ``stopped`` so the control thread also cannot
        outlive a read loop that ended on its own (EOF or an exception) while
        leaving ``stopped`` untouched for the shutdown logic in ``main()``.
        """
        self._control_running = False
        thread = self._control_thread
        self._control_thread = None
        if thread_is_alive(thread):
            join_thread(thread, timeout=timeout)

    # Retained for internal callers; ``stop_control_loop`` is the public name.
    _stop_control_loop = stop_control_loop

    def set_diagnostics(self, diagnostics):
        """Attach an InputDiagnostics instance to instrument the read loop.

        Purely observational: the read loop behaves identically whether or
        not one is attached.  Pass ``None`` to detach.
        """
        self._diagnostics = diagnostics

    def _dispatch(self, event_name):
        """Fire *event_name*, timing the dispatch when diagnostics are on.

        Exceptions propagate exactly as ``trigger()`` raises them; the
        diagnostics only observe.
        """
        diagnostics = self._diagnostics
        if diagnostics is None:
            self.trigger(event_name)
            return

        start = diagnostics.now()
        failed = False
        try:
            self.trigger(event_name)
        except Exception:
            failed = True
            raise
        finally:
            end = diagnostics.now()
            if start is not None and end is not None:
                diagnostics.record_dispatch(
                    event_name, (end - start) * 1000.0, failed=failed
                )

    def set_debug_input(self, enabled):
        """Enable or disable concise controller input diagnostics."""
        self._debug_input = bool(enabled)
        self._last_right_stick_debug_t = 0
        self._right_stick_debug_count = 0
        self._last_right_stick_debug_xy = None
        if self._debug_input:
            print("PlayStation controller input debug enabled")

    def _debug(self, message):
        if self._debug_input:
            print("PS4 input: {}".format(message))

    def _should_debug_right_stick(self, scaled_x, scaled_y):
        """Rate-limit right-stick debug; always log first event and large moves."""
        if not self._debug_input:
            return False
        self._right_stick_debug_count += 1
        xy = (int(scaled_x), int(scaled_y))
        now = _time() if _time is not None else None
        if self._last_right_stick_debug_xy is None:
            self._last_right_stick_debug_xy = xy
            if now is not None:
                self._last_right_stick_debug_t = now
            return True
        dx = abs(xy[0] - self._last_right_stick_debug_xy[0])
        dy = abs(xy[1] - self._last_right_stick_debug_xy[1])
        if dx >= 10 or dy >= 10:
            self._last_right_stick_debug_xy = xy
            if now is not None:
                self._last_right_stick_debug_t = now
            return True
        if now is not None:
            if (now - self._last_right_stick_debug_t) >= RIGHT_STICK_DEBUG_INTERVAL_S:
                self._last_right_stick_debug_t = now
                self._last_right_stick_debug_xy = xy
                return True
            return False
        # No time module: fall back to every 8th event
        if (self._right_stick_debug_count % 8) == 0:
            self._last_right_stick_debug_xy = xy
            return True
        return False
    
    # This is the main loop of handling PlayStation controller events. It is run in a separate thread.
    def run(self):
       # Open the Gamepad event file.
        # First try to detect the device by name via /proc/bus/input/devices so that
        # this works with both PS4 DualShock 4 and PS5 DualSense controllers without
        # depending on a hardcoded event number.
        # If name-based detection fails, fall back to probing the most common paths.
        infile_path = "/dev/input/event4"
        # Bound before the try block so the loop-exit diagnostics below can
        # reference it even when the failure happens during device discovery.
        last_event_desc = None
        
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

            # Motor work happens here, not in the read loop below, so that a
            # slow motor call can never stall reading and cause the kernel to
            # drop input.
            self._start_control_loop()

            # Read from the file
            # long int, long int, unsigned short, unsigned short, unsigned int
            FORMAT = 'llHHI'    
            EVENT_SIZE = struct.calcsize(FORMAT)
            # Timestamps around the blocking read, so the report can separate
            # "idle, waiting for input" from "starved: data was already
            # waiting and we could not collect it".
            read_started_at = self._diag_now()
            event = in_file.read(EVENT_SIZE)
            read_ended_at = self._diag_now()
            prev_proc_ended_at = None
            i = 0;
            
            if __debug__:
                print("Starting the PlayStation controller loop...")            
            while event and not self.stopped:
                (tv_sec, tv_usec, ev_type, code, value) = struct.unpack(FORMAT, event)

                event_lag_ms = None
                if self._diagnostics is not None:
                    event_lag_ms = self._diagnostics.record_event(
                        ev_type, code, tv_sec, tv_usec
                    )
                    if ev_type == EV_SYN and code == SYN_DROPPED:
                        # How long we had been out of the loop when the kernel
                        # gave up on us: one long stall and many short ones
                        # have very different causes.
                        self._diagnostics.record_drop_stall(
                            self._elapsed_ms(prev_proc_ended_at, read_ended_at) or 0.0
                        )
                    last_event_desc = "type={} code={} value={}".format(
                        ev_type, code, value
                    )


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

                    # The turret owns its deadzone.  Filtering here as well made
                    # small, deliberate right-stick movements indistinguishable
                    # from a centered stick.
                    if self._should_debug_right_stick(self.r_left, self.r_forward):
                        axis_bits = "16bit" if self._get_axis_range() == AXIS_RANGE_16BIT else "8bit"
                        axis_name = "RX" if code == RIGHT_STICK_X else "RY"
                        self._debug(
                            "right stick raw {}={} scaled x={:.0f} y={:.0f} ({})".format(
                                axis_name, value, self.r_left, self.r_forward, axis_bits
                            )
                        )
                    self._mark_stick_dirty("right_joystick")

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

                    self._mark_stick_dirty("left_joystick")




                #Handle the pad (D-pad)
                if ev_type == 3 and code >15:
                    # Handle left/right arrows (horizontal axis)
                    if(code == 16 and value == 1):
                        self._dispatch("left_arrow_pressed");
                    if(code == 16 and value == 0):
                        self._dispatch("lr_arrow_released");
                    if(code == 16 and value == 4294967295):
                        self._dispatch("right_arrow_pressed");
                    
                    # Handle up/down arrows (vertical axis)
                    if(code == 17 and value == 1):
                        self._dispatch("up_arrow_pressed");
                    if(code == 17 and value == 0):
                        self._dispatch("ud_arrow_released");
                    if(code == 17 and value == 4294967295):
                        self._dispatch("down_arrow_pressed");

                # Handle controller buttons
                # Note: PS4 DualShock 4 and PS5 DualSense use the same evdev key codes
                # for all action buttons, shoulder buttons, triggers, and the d-pad.
                if ev_type == EV_KEY:
                    # Cross (X) button — BTN_SOUTH (304)
                    if code == X_BUTTON and value == 1:
                        self._debug("button code=304 event=cross_button")
                        self._dispatch("cross_button");
                    # Circle button — BTN_EAST (305)
                    if code == CIRCLE_BUTTON and value == 1:
                        self._dispatch("circle_button");
                    # Triangle button — BTN_NORTH (307)
                    if code == TRIANGLE_BUTTON and value == 1:
                        self._dispatch("triangle_button");
                    # Square button — BTN_WEST (308)
                    if code == SQUARE_BUTTON and value == 1:
                        self._dispatch("square_button");

                    # L1 button — BTN_TL (310)
                    if code == 310 and value == 1:
                        self._dispatch("l1_button");
                    # L2 button — BTN_TL2 (312)
                    if code == 312 and value == 1:
                        self._dispatch("l2_button");
                    # R1 button — BTN_TR (311)
                    if code == 311 and value == 1:
                        self._dispatch("r1_button");
                    # R2 button — BTN_TR2 (313)
                    if code == 313 and value == 1:
                        self._dispatch("r2_button");

                    # Options button — BTN_START (315)
                    # PS4: Options | PS5: Options
                    if code == 315 and value == 1:
                        self._dispatch("options_button");
                    # Share/Create button — BTN_SELECT (314)
                    # PS4: Share | PS5: Create
                    # TODO: Handle Share/Create button (314) if needed
                    # PS/Home button — BTN_MODE (316)
                    # TODO: Handle PS/Home button (316) if needed
                    # L3 (left stick click) — BTN_THUMBL (317)
                    # TODO: Handle L3 (317) if needed
                    # R3 (right stick click) — BTN_THUMBR (318)
                    # TODO: Handle R3 (318) if needed

                if self._diagnostics is not None:
                    proc_ended_at = self._diag_now()
                    self._diagnostics.record_reader_timing(
                        read_ms=self._elapsed_ms(read_started_at, read_ended_at),
                        proc_ms=self._elapsed_ms(read_ended_at, proc_ended_at),
                        gap_ms=self._elapsed_ms(prev_proc_ended_at, read_started_at),
                        lag_ms=event_lag_ms,
                    )
                    prev_proc_ended_at = proc_ended_at

                # Finally, read another event
                read_started_at = self._diag_now()
                event = in_file.read(EVENT_SIZE)
                read_ended_at = self._diag_now()
                

            in_file.close()
            if self._diagnostics is not None:
                self._diagnostics.record_loop_exit(
                    "stopped by request" if self.stopped else "device reported EOF",
                    last_event=last_event_desc,
                )
        except OSError as e:
            # Handle both FileNotFoundError and PermissionError under OSError
            error_msg = str(e)
            if self._diagnostics is not None:
                self._diagnostics.record_loop_exit(
                    "OSError from controller device",
                    exception=e,
                    last_event=last_event_desc,
                )
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
            if self._diagnostics is not None:
                self._diagnostics.record_loop_exit(
                    "unhandled exception in read loop",
                    exception=e,
                    last_event=last_event_desc,
                )
            report_exception("PS4Controller.run()", "event processing loop", e, "Main controller event loop")
            print("Check Bluetooth connection and try again")
            self.connected = False
        finally:
            # Never leave the control thread spinning against a read loop
            # that has already ended.
            self._stop_control_loop()

    def handle_event(self, event):
        # Override this method to handle PlayStation controller events
        pass
 
    def stop(self):
        self.stopped = True;
        self.stop_control_loop()
    
    def is_connected(self):
        """Check if the PlayStation controller is connected and working"""
        return self.connected

    def _is_axis_sentinel(self, value):
        """Ignore evdev release sentinels (-1/-2 read as unsigned).

        255 is deliberately *not* treated as a sentinel: on a PS4's 8-bit
        axes it is the legitimate maximum, so discarding it made a fully
        deflected stick indistinguishable from no input at all and left the
        robot acting on the last sub-maximum reading.
        """
        return value in AXIS_SENTINEL_VALUES

    def _detect_axis_range(self, value):
        """Auto-detect 8-bit (PS4) vs 16-bit (PS5/DualSense) stick axis range.

        An 8-bit guess is provisional and upgraded as soon as a value beyond
        the 8-bit maximum arrives, because a DualSense's 16-bit axes spend
        plenty of time reporting small values that are indistinguishable
        from 8-bit ones.  A PS4 can never exceed its 8-bit maximum, so the
        upgrade is one-way and cannot mis-detect in the other direction.
        """
        if self._is_axis_sentinel(value):
            return
        if value > AXIS_RANGE_8BIT[1]:
            self._axis_range = AXIS_RANGE_16BIT
        elif self._axis_range is None:
            self._axis_range = AXIS_RANGE_8BIT

    def _get_axis_range(self):
        return self._axis_range or AXIS_RANGE_8BIT

    def _scale_axis(self, value, dst):
        """
        Scale a raw evdev axis value to the requested output range.

        Returns None for sentinel/release values that should be ignored.
        """
        if self._is_axis_sentinel(value):
            if self._diagnostics is not None:
                self._diagnostics.record_axis_rejected(value)
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
