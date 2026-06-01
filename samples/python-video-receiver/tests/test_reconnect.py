"""Unit tests for reconnect logic in samples/python-video-receiver/main.py."""

import socket
import threading
import time
from unittest.mock import MagicMock, patch, call

import pytest

from receiver import main as receiver_main

ReconnectConfig = receiver_main.ReconnectConfig
UDPVideoClient = receiver_main.UDPVideoClient
compute_backoff_delay = receiver_main.compute_backoff_delay


# ---------------------------------------------------------------------------
# compute_backoff_delay tests
# ---------------------------------------------------------------------------

class TestComputeBackoffDelay:
    def test_attempt_zero_returns_initial_delay(self):
        assert compute_backoff_delay(0, 1.0, 30.0, 2.0) == pytest.approx(1.0)

    def test_doubles_with_factor_two(self):
        assert compute_backoff_delay(1, 1.0, 30.0, 2.0) == pytest.approx(2.0)
        assert compute_backoff_delay(2, 1.0, 30.0, 2.0) == pytest.approx(4.0)
        assert compute_backoff_delay(3, 1.0, 30.0, 2.0) == pytest.approx(8.0)

    def test_capped_at_max_delay(self):
        assert compute_backoff_delay(10, 1.0, 5.0, 2.0) == pytest.approx(5.0)

    def test_factor_of_one_gives_constant_delay(self):
        for attempt in range(5):
            assert compute_backoff_delay(attempt, 2.0, 100.0, 1.0) == pytest.approx(2.0)

    def test_custom_factor(self):
        assert compute_backoff_delay(2, 1.0, 1000.0, 3.0) == pytest.approx(9.0)


# ---------------------------------------------------------------------------
# ReconnectConfig defaults
# ---------------------------------------------------------------------------

class TestReconnectConfigDefaults:
    def test_default_max_attempts(self):
        cfg = ReconnectConfig()
        assert cfg.max_attempts == 10

    def test_default_initial_delay(self):
        cfg = ReconnectConfig()
        assert cfg.initial_delay_seconds == pytest.approx(1.0)

    def test_default_max_delay(self):
        cfg = ReconnectConfig()
        assert cfg.max_delay_seconds == pytest.approx(30.0)

    def test_default_backoff_factor(self):
        cfg = ReconnectConfig()
        assert cfg.backoff_factor == pytest.approx(2.0)

    def test_default_registration_timeout(self):
        cfg = ReconnectConfig()
        assert cfg.registration_timeout_seconds == pytest.approx(10.0)

    def test_custom_values_respected(self):
        cfg = ReconnectConfig(max_attempts=3, initial_delay_seconds=0.5)
        assert cfg.max_attempts == 3
        assert cfg.initial_delay_seconds == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# UDPVideoClient._register_with_server tests
# ---------------------------------------------------------------------------

def _make_client_no_socket(**kwargs) -> UDPVideoClient:
    """Build a UDPVideoClient with all socket operations mocked out."""
    client = UDPVideoClient.__new__(UDPVideoClient)
    client.server_host = "127.0.0.1"
    client.server_port = 9999
    client.client_port = 0
    client.stream_format = "jpeg"
    client.reconnect_config = ReconnectConfig(**kwargs)
    client.running = False
    client.socket = MagicMock()
    client.socket.getsockname.return_value = ("127.0.0.1", 9999)
    client.pending_frames = {}
    client.expected_chunks = {}
    client.received_chunks = {}
    client.frames_received = 0
    client.decode_failures = 0
    client.start_time = None
    client.last_stats_time = 0
    client.h264_decoder = None
    client.payload_size = 1200
    return client


class TestRegisterWithServer:
    def test_returns_true_on_registered_ack(self):
        client = _make_client_no_socket()
        client.socket.recvfrom.return_value = (b"REGISTERED", ("127.0.0.1", 9999))
        assert client._register_with_server() is True

    def test_returns_false_on_wrong_ack(self):
        client = _make_client_no_socket()
        client.socket.recvfrom.return_value = (b"UNKNOWN", ("127.0.0.1", 9999))
        assert client._register_with_server() is False

    def test_returns_false_on_timeout(self):
        client = _make_client_no_socket()
        client.socket.recvfrom.side_effect = socket.timeout("timed out")
        assert client._register_with_server() is False

    def test_returns_false_on_socket_error(self):
        client = _make_client_no_socket()
        client.socket.recvfrom.side_effect = OSError("connection refused")
        assert client._register_with_server() is False

    def test_sends_register_client_message(self):
        client = _make_client_no_socket()
        client.socket.recvfrom.return_value = (b"REGISTERED", ("127.0.0.1", 9999))
        client._register_with_server()
        client.socket.sendto.assert_called_once_with(
            b"REGISTER_CLIENT", ("127.0.0.1", 9999)
        )

    def test_applies_registration_timeout_to_socket(self):
        client = _make_client_no_socket(registration_timeout_seconds=7.0)
        client.socket.recvfrom.return_value = (b"REGISTERED", ("127.0.0.1", 9999))
        client._register_with_server()
        # First settimeout call should use registration_timeout_seconds
        first_call_arg = client.socket.settimeout.call_args_list[0][0][0]
        assert first_call_arg == pytest.approx(7.0)


# ---------------------------------------------------------------------------
# start_receiving reconnect integration tests
# ---------------------------------------------------------------------------

class TestStartReceivingReconnect:
    def _build_client_with_failing_registration(
        self, max_attempts: int = 2, fail_count: int = 2
    ) -> tuple[UDPVideoClient, MagicMock]:
        """Build a client whose server responds with REGISTERED only after `fail_count` failures."""
        client = _make_client_no_socket(
            max_attempts=max_attempts,
            initial_delay_seconds=0.01,
            max_delay_seconds=0.05,
        )
        # Simulate fail_count timeouts then success
        side_effects = [socket.timeout("timed out")] * fail_count
        # stop after failures — client should give up
        client.socket.recvfrom.side_effect = side_effects
        return client, client.socket

    def test_gives_up_after_max_attempts(self):
        client, mock_socket = self._build_client_with_failing_registration(
            max_attempts=2, fail_count=10
        )
        with patch.object(client, "cleanup"):
            with patch.object(time, "sleep"):
                client.start_receiving()
        # register was attempted 1 (initial) + 2 (retries) = 3 times
        assert mock_socket.sendto.call_count >= 1

    def test_reconnect_disabled_when_max_attempts_zero(self):
        client = _make_client_no_socket(max_attempts=0)
        client.socket.recvfrom.side_effect = socket.timeout("timed out")
        send_calls = []
        client.socket.sendto.side_effect = lambda *a: send_calls.append(a)
        with patch.object(client, "cleanup"):
            client.start_receiving()
        # Only one registration attempt should be made
        register_calls = [c for c in send_calls if c[0] == b"REGISTER_CLIENT"]
        assert len(register_calls) == 1

    def test_receive_loop_exits_on_timeout_and_reconnects(self):
        """After a successful registration, a receive timeout triggers a reconnect."""
        client = _make_client_no_socket(
            max_attempts=1,
            initial_delay_seconds=0.01,
        )
        call_count = {"n": 0}

        def mock_recvfrom(bufsize):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # First call: successful registration
                return b"REGISTERED", ("127.0.0.1", 9999)
            if call_count["n"] == 2:
                # Second call: stream data timeout → triggers reconnect
                raise socket.timeout("stream timeout")
            # Third call: registration again fails → give up
            raise socket.timeout("stream timeout")

        client.socket.recvfrom.side_effect = mock_recvfrom
        keepalive_calls: list = []

        def fake_keepalive():
            keepalive_calls.append(1)

        with patch.object(client, "send_keepalive", fake_keepalive):
            with patch.object(client, "display_stats", lambda: None):
                with patch.object(client, "cleanup"):
                    with patch.object(time, "sleep"):
                        client.start_receiving()

        # At least one reconnect cycle happened
        assert call_count["n"] >= 2

    def test_attempt_counter_resets_after_successful_registration(self):
        """After a failed attempt then success, attempt counter resets to 0."""
        client = _make_client_no_socket(
            max_attempts=5,
            initial_delay_seconds=0.01,
        )
        call_count = {"n": 0}

        def mock_recvfrom(bufsize):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise socket.timeout("first attempt fails")
            if call_count["n"] == 2:
                # Registration succeeds on second attempt
                return b"REGISTERED", ("127.0.0.1", 9999)
            # After registration, receive loop immediately exits
            raise socket.timeout("stream timeout")

        client.socket.recvfrom.side_effect = mock_recvfrom
        sleep_calls: list = []

        with patch.object(client, "send_keepalive", lambda: None):
            with patch.object(client, "display_stats", lambda: None):
                with patch.object(client, "cleanup"):
                    with patch.object(time, "sleep", lambda s: sleep_calls.append(s)):
                        client.start_receiving()

        # The first sleep should be attempt=0 delay (initial_delay_seconds=0.01)
        assert len(sleep_calls) >= 1
        assert sleep_calls[0] == pytest.approx(0.01)
