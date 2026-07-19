# Purpose: A class that can be inherited from to provide event handling functionality.

try:
    from time import time as _time_now
    _HAS_TIME = True
except ImportError:  # pragma: no cover - MicroPython may not have time
    _HAS_TIME = False


class EventHandler(object):
    callbacks = None
    _telemetry_collector = None
    _telemetry_filter = None
    _telemetry_excluded_events = None
    _controller_type = "unknown"

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

        Emits a ``command_received`` telemetry event before callbacks run and a
        ``command_executed`` event (with timing and success flag) after all
        callbacks complete.  Both events are silently swallowed if the collector
        raises.  Any exception raised by a callback is re-raised after
        ``command_executed`` has been emitted so telemetry is never lost.

        Parameters:
        - event_name (str): The name of the event.

        Returns:
        None
        """
        controller_type = getattr(self, '_controller_type', 'unknown')
        collector = self._telemetry_collector
        should_collect = (
            collector is not None
            and (self._telemetry_filter is None or event_name in self._telemetry_filter)
            and (
                self._telemetry_excluded_events is None
                or event_name not in self._telemetry_excluded_events
            )
        )

        # Emit command_received before running callbacks
        if should_collect:
            try:
                collector.collect_command_received(
                    event_name,
                    controller_type=controller_type,
                )
            except Exception:
                pass

        # Run callbacks and measure wall-clock time
        exc = None
        start = _time_now() if _HAS_TIME else 0

        if self.callbacks is not None and event_name in self.callbacks:
            try:
                for callback in self.callbacks[event_name]:
                    callback(self)
            except Exception as e:
                exc = e

        elapsed_ms = (_time_now() - start) * 1000 if _HAS_TIME else None

        # Emit command_executed after callbacks (always, success or failure)
        if should_collect:
            try:
                collector.collect_command_executed(
                    event_name,
                    success=(exc is None),
                    duration_ms=elapsed_ms,
                    controller_type=controller_type,
                    error_message=str(exc) if exc is not None else None,
                )
            except Exception:
                pass

        # Re-raise any callback exception after telemetry has been emitted
        if exc is not None:
            raise exc

    def set_telemetry_collector(self, collector, event_filter=None, excluded_events=None):
        """
        Attach a TelemetryCollector to receive forwarded events.

        When set, each call to :meth:`trigger` will emit a ``command_received``
        event before callbacks run and a ``command_executed`` event (with timing
        and success/failure information) after all callbacks complete.  Only
        events whose name passes *event_filter* are forwarded.

        Parameters
        ----------
        collector:
            A :class:`telemetry.collector.TelemetryCollector` instance, or
            ``None`` to detach the current collector.
        event_filter:
            Optional iterable of event-name strings.  Only events whose name
            appears in this collection are forwarded.  ``None`` means *all*
            events are forwarded.
        excluded_events:
            Optional iterable of event-name strings that must not be
            forwarded. Applied after *event_filter*, allowing high-frequency
            controls to be excluded without omitting other current or future
            event types.

        Returns
        -------
        None
        """
        self._telemetry_collector = collector
        self._telemetry_filter = set(event_filter) if event_filter is not None else None
        self._telemetry_excluded_events = (
            set(excluded_events) if excluded_events is not None else None
        )
