# Purpose: A class that can be inherited from to provide event handling functionality.
class EventHandler(object):
    callbacks = None

    def on(self, event_name, callback):
        """
        Adds a callback function to the specified event.

        Parameters:
        - event_name (str): The name of the event.
        - callback (function): The callback function to be executed when the event is triggered.

        Returns:
        None
        """
        if self.callbacks is None:
            self.callbacks = {}

        if event_name not in self.callbacks:
            self.callbacks[event_name] = [callback]
        else:
            self.callbacks[event_name].append(callback)

    def trigger(self, event_name):
        """
        Triggers the specified event, executing all associated callback functions.

        Parameters:
        - event_name (str): The name of the event.

        Returns:
        None
        """
        if self.callbacks is not None and event_name in self.callbacks:
            for callback in self.callbacks[event_name]:
                callback(self)