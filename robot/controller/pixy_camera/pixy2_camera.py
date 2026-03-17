import threading
from time import sleep
from event_handler import EventHandler
from .pixycamev3.pixy2 import Pixy2

class Pixy2Camera(EventHandler, threading.Thread):
    pixy = 0;
    stopped = False
    blocks = None

    def __init__(self, port=1):
        self.pixy = Pixy2(port=1, i2c_address=0x54)
        self.pixy.mode = 'SIG1'

    def __str__(self):
        return "Pixy Camera Controller for EV3";

    def close(self):
        self.pixy.close()

    def light(self, on):
        self.pixy.set_lamp(on,on)

    # This is the main loop of handling PS4 controller events. It is run in a separate thread.
    def run(self):
        while not self.stopped:
            nr_blocks, self.blocks = self.pixy.get_blocks(1,1);
            if(nr_blocks >=1):
                self.trigger("block_detected");

            sleep(0.1)



    def onBlockDetected(self, callback):
        self.on("block_detected", callback)