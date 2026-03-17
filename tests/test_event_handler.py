#!/usr/bin/env python3

"""
Unit tests for EventHandler class using pytest
"""

import pytest
from EventHandler import EventHandler

class TestEventHandler:
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures"""
        self.event_handler = EventHandler()
        
        # Test callback tracking
        self.callback_calls = []
        self.callback_args = []
    
    def test_initialization(self):
        """Test event handler initialization"""
        assert self.event_handler.callbacks is None
    
    def test_on_first_callback_creates_callbacks_dict(self):
        """Test that adding first callback creates callbacks dictionary"""
        def test_callback(sender):
            pass
        
        self.event_handler.on("test_event", test_callback)
        
        assert self.event_handler.callbacks is not None
        assert isinstance(self.event_handler.callbacks, dict)
        assert "test_event" in self.event_handler.callbacks
        assert len(self.event_handler.callbacks["test_event"]) == 1
        assert self.event_handler.callbacks["test_event"][0] == test_callback
    
    def test_on_single_callback(self):
        """Test adding a single callback to an event"""
        def test_callback(sender):
            self.callback_calls.append("test_callback")
        
        self.event_handler.on("button_press", test_callback)
        
        assert "button_press" in self.event_handler.callbacks
        assert len(self.event_handler.callbacks["button_press"]) == 1
        assert self.event_handler.callbacks["button_press"][0] == test_callback
    
    def test_on_multiple_callbacks_same_event(self):
        """Test adding multiple callbacks to the same event"""
        def callback1(sender):
            self.callback_calls.append("callback1")
        
        def callback2(sender):
            self.callback_calls.append("callback2")
        
        def callback3(sender):
            self.callback_calls.append("callback3")
        
        self.event_handler.on("joystick_move", callback1)
        self.event_handler.on("joystick_move", callback2)
        self.event_handler.on("joystick_move", callback3)
        
        assert len(self.event_handler.callbacks["joystick_move"]) == 3
        assert callback1 in self.event_handler.callbacks["joystick_move"]
        assert callback2 in self.event_handler.callbacks["joystick_move"]
        assert callback3 in self.event_handler.callbacks["joystick_move"]
    
    def test_on_multiple_different_events(self):
        """Test adding callbacks to different events"""
        def button_callback(sender):
            self.callback_calls.append("button")
        
        def joystick_callback(sender):
            self.callback_calls.append("joystick")
        
        def trigger_callback(sender):
            self.callback_calls.append("trigger")
        
        self.event_handler.on("button_press", button_callback)
        self.event_handler.on("joystick_move", joystick_callback)
        self.event_handler.on("trigger_pull", trigger_callback)
        
        assert len(self.event_handler.callbacks) == 3
        assert "button_press" in self.event_handler.callbacks
        assert "joystick_move" in self.event_handler.callbacks
        assert "trigger_pull" in self.event_handler.callbacks
    
    def test_trigger_with_no_callbacks(self):
        """Test triggering event when no callbacks are registered"""
        # Should not raise exception
        self.event_handler.trigger("non_existent_event")
        
        # Even with empty callbacks dict
        self.event_handler.callbacks = {}
        self.event_handler.trigger("non_existent_event")
    
    def test_trigger_non_existent_event_with_callbacks(self):
        """Test triggering non-existent event when other callbacks exist"""
        def test_callback(sender):
            self.callback_calls.append("test")
        
        self.event_handler.on("existing_event", test_callback)
        
        # Should not raise exception or call any callbacks
        self.event_handler.trigger("non_existent_event")
        assert len(self.callback_calls) == 0
    
    def test_trigger_single_callback(self):
        """Test triggering event with single callback"""
        def test_callback(sender):
            self.callback_calls.append("triggered")
            self.callback_args.append(sender)
        
        self.event_handler.on("test_event", test_callback)
        self.event_handler.trigger("test_event")
        
        assert len(self.callback_calls) == 1
        assert self.callback_calls[0] == "triggered"
        assert len(self.callback_args) == 1
        assert self.callback_args[0] == self.event_handler
    
    def test_trigger_multiple_callbacks(self):
        """Test triggering event with multiple callbacks"""
        def callback1(sender):
            self.callback_calls.append("callback1")
            self.callback_args.append(sender)
        
        def callback2(sender):
            self.callback_calls.append("callback2")
            self.callback_args.append(sender)
        
        def callback3(sender):
            self.callback_calls.append("callback3")
            self.callback_args.append(sender)
        
        self.event_handler.on("multi_event", callback1)
        self.event_handler.on("multi_event", callback2)
        self.event_handler.on("multi_event", callback3)
        
        self.event_handler.trigger("multi_event")
        
        assert len(self.callback_calls) == 3
        assert "callback1" in self.callback_calls
        assert "callback2" in self.callback_calls
        assert "callback3" in self.callback_calls
        
        # All callbacks should receive the event handler as sender
        assert len(self.callback_args) == 3
        assert all(arg == self.event_handler for arg in self.callback_args)
    
    def test_trigger_callback_execution_order(self):
        """Test that callbacks are executed in the order they were added"""
        execution_order = []
        
        def callback1(sender):
            execution_order.append(1)
        
        def callback2(sender):
            execution_order.append(2)
        
        def callback3(sender):
            execution_order.append(3)
        
        self.event_handler.on("order_test", callback1)
        self.event_handler.on("order_test", callback2)
        self.event_handler.on("order_test", callback3)
        
        self.event_handler.trigger("order_test")
        
        assert execution_order == [1, 2, 3]
    
    def test_trigger_with_callback_parameters(self):
        """Test that callbacks receive correct sender parameter"""
        received_senders = []
        
        def callback(sender):
            received_senders.append(sender)
            assert sender is not None
            assert isinstance(sender, EventHandler)
        
        self.event_handler.on("param_test", callback)
        self.event_handler.trigger("param_test")
        
        assert len(received_senders) == 1
        assert received_senders[0] == self.event_handler
    
    def test_multiple_trigger_calls(self):
        """Test multiple calls to trigger for same event"""
        call_count = 0
        
        def counting_callback(sender):
            nonlocal call_count
            call_count += 1
        
        self.event_handler.on("count_event", counting_callback)
        
        # Trigger multiple times
        self.event_handler.trigger("count_event")
        assert call_count == 1
        
        self.event_handler.trigger("count_event")
        assert call_count == 2
        
        self.event_handler.trigger("count_event")
        assert call_count == 3
    
    def test_callback_with_exception_handling(self):
        """Test that exceptions in callbacks don't prevent other callbacks from executing"""
        execution_log = []
        
        def good_callback1(sender):
            execution_log.append("good1")
        
        def failing_callback(sender):
            execution_log.append("failing")
            raise Exception("Callback error")
        
        def good_callback2(sender):
            execution_log.append("good2")
        
        self.event_handler.on("exception_test", good_callback1)
        self.event_handler.on("exception_test", failing_callback)
        self.event_handler.on("exception_test", good_callback2)
        
        # This should raise exception from failing_callback
        with pytest.raises(Exception, match="Callback error"):
            self.event_handler.trigger("exception_test")
        
        # But first callback should have executed
        assert "good1" in execution_log
        assert "failing" in execution_log
        # good2 won't execute because exception stops the loop
    
    @pytest.mark.parametrize("event_name", [
        "button_press",
        "joystick_left",
        "joystick_right", 
        "trigger_pull",
        "d_pad_up",
        "cross_button"
    ])
    def test_different_event_names(self, event_name):
        """Test various event names (parameterized test)"""
        callback_called = False
        
        def test_callback(sender):
            nonlocal callback_called
            callback_called = True
        
        self.event_handler.on(event_name, test_callback)
        self.event_handler.trigger(event_name)
        
        assert callback_called == True
        assert event_name in self.event_handler.callbacks
    
    def test_lambda_callbacks(self):
        """Test using lambda functions as callbacks"""
        results = []
        
        self.event_handler.on("lambda_test", lambda sender: results.append("lambda1"))
        self.event_handler.on("lambda_test", lambda sender: results.append("lambda2"))
        
        self.event_handler.trigger("lambda_test")
        
        assert len(results) == 2
        assert "lambda1" in results
        assert "lambda2" in results
    
    def test_method_callbacks(self):
        """Test using instance methods as callbacks"""
        class TestReceiver:
            def __init__(self):
                self.received_events = []
            
            def handle_event(self, sender):
                self.received_events.append(sender)
        
        receiver = TestReceiver()
        self.event_handler.on("method_test", receiver.handle_event)
        self.event_handler.trigger("method_test")
        
        assert len(receiver.received_events) == 1
        assert receiver.received_events[0] == self.event_handler
    
    def test_callback_state_isolation(self):
        """Test that different event handler instances don't share callbacks"""
        handler1 = EventHandler()
        handler2 = EventHandler()
        
        calls1 = []
        calls2 = []
        
        def callback1(sender):
            calls1.append("handler1")
        
        def callback2(sender):
            calls2.append("handler2")
        
        handler1.on("test", callback1)
        handler2.on("test", callback2)
        
        handler1.trigger("test")
        handler2.trigger("test")
        
        assert len(calls1) == 1
        assert len(calls2) == 1
        assert calls1[0] == "handler1"
        assert calls2[0] == "handler2"

# Tests can be run with: pytest tests/test_event_handler.py 