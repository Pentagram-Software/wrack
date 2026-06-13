# Purpose: A class that can be inherited from to provide event handling functionality.
class EventHandler(object):
    callbacks = None
    _telemetry_collector = None
    _telemetry_filter = None

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

        if self._telemetry_collector is not None:
            if self._telemetry_filter is None or event_name in self._telemetry_filter:
                try:
                    self._telemetry_collector.collect(
                        "command_received",
                        command=event_name,
                        controller_type="unknown",
                    )
                except Exception:
                    pass

    def set_telemetry_collector(self, collector, event_filter=None):
        """
        Attach a TelemetryCollector to receive forwarded events.

        When set, each call to :meth:`trigger` will also call
        ``collector.collect("command_received", command=event_name)`` for
        every event that passes *event_filter*.

        Parameters
        ----------
        collector:
            A :class:`telemetry.collector.TelemetryCollector` instance, or
            ``None`` to detach the current collector.
        event_filter:
            Optional iterable of event-name strings.  Only events whose name
            appears in this collection are forwarded.  ``None`` means *all*
            events are forwarded.

        Returns
        -------
        None
        """
        self._telemetry_collector = collector
        self._telemetry_filter = set(event_filter) if event_filter is not None else None
