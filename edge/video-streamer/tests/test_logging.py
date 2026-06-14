"""Unit tests for configure_logging() from health.py."""

from __future__ import annotations

import logging
import os

import pytest

from health import configure_logging


# ---------------------------------------------------------------------------
# Fixture: reset the streamer logger around every test so that handler state
# from one test does not bleed into the next.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_logger():
    """Isolate the 'streamer' logger for each test."""
    logger = logging.getLogger("streamer")
    original_level = logger.level
    original_handlers = logger.handlers[:]
    # Clean slate before the test
    logger.handlers.clear()
    logger.setLevel(logging.NOTSET)
    yield
    # Restore after the test (important for test isolation in a single process)
    for handler in logger.handlers:
        try:
            handler.close()
        except Exception:
            pass
    logger.handlers.clear()
    logger.setLevel(logging.NOTSET)
    for handler in original_handlers:
        logger.addHandler(handler)
    logger.setLevel(original_level)


# ===========================================================================
# configure_logging tests
# ===========================================================================


class TestConfigureLoggingHandlers:
    def test_file_handler_added(self, tmp_path):
        log_path = str(tmp_path / "streamer.log")
        configure_logging(log_path=log_path, console=False)
        logger = logging.getLogger("streamer")
        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1

    def test_console_handler_added_when_enabled(self, tmp_path):
        log_path = str(tmp_path / "streamer.log")
        configure_logging(log_path=log_path, console=True)
        logger = logging.getLogger("streamer")
        stream_handlers = [
            h
            for h in logger.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
        ]
        assert len(stream_handlers) == 1

    def test_no_console_handler_when_disabled(self, tmp_path):
        log_path = str(tmp_path / "streamer.log")
        configure_logging(log_path=log_path, console=False)
        logger = logging.getLogger("streamer")
        stream_handlers = [
            h
            for h in logger.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
        ]
        assert len(stream_handlers) == 0

    def test_console_only_when_no_log_path(self):
        configure_logging(log_path="", console=True)
        logger = logging.getLogger("streamer")
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], logging.StreamHandler)
        assert not isinstance(logger.handlers[0], logging.FileHandler)

    def test_no_handlers_when_no_path_and_no_console(self):
        configure_logging(log_path="", console=False)
        logger = logging.getLogger("streamer")
        assert len(logger.handlers) == 0

    def test_both_handlers_when_path_and_console(self, tmp_path):
        log_path = str(tmp_path / "streamer.log")
        configure_logging(log_path=log_path, console=True)
        logger = logging.getLogger("streamer")
        assert len(logger.handlers) == 2


class TestConfigureLoggingIdempotency:
    def test_second_call_is_no_op(self, tmp_path):
        log_path = str(tmp_path / "streamer.log")
        configure_logging(log_path=log_path, console=True)
        configure_logging(log_path=log_path, console=True)
        logger = logging.getLogger("streamer")
        # Should still have exactly 2 handlers (file + console), not 4
        assert len(logger.handlers) == 2

    def test_second_call_with_different_args_is_no_op(self, tmp_path):
        log_path_1 = str(tmp_path / "first.log")
        log_path_2 = str(tmp_path / "second.log")
        configure_logging(log_path=log_path_1, console=False)
        configure_logging(log_path=log_path_2, console=True)
        logger = logging.getLogger("streamer")
        # Still only the one file handler from the first call
        assert len(logger.handlers) == 1


class TestConfigureLoggingLevel:
    def test_default_level_is_info(self, tmp_path):
        configure_logging(log_path=str(tmp_path / "s.log"), console=False)
        logger = logging.getLogger("streamer")
        assert logger.level == logging.INFO

    def test_custom_level_debug(self, tmp_path):
        configure_logging(log_path=str(tmp_path / "s.log"), level=logging.DEBUG, console=False)
        logger = logging.getLogger("streamer")
        assert logger.level == logging.DEBUG

    def test_custom_level_warning(self, tmp_path):
        configure_logging(log_path=str(tmp_path / "s.log"), level=logging.WARNING, console=False)
        logger = logging.getLogger("streamer")
        assert logger.level == logging.WARNING


class TestConfigureLoggingFileOutput:
    def test_log_directory_created(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        log_path = str(nested / "streamer.log")
        configure_logging(log_path=log_path, console=False)
        assert nested.exists()

    def test_log_file_created(self, tmp_path):
        log_path = str(tmp_path / "streamer.log")
        configure_logging(log_path=log_path, console=False)
        logger = logging.getLogger("streamer")
        logger.info("hello from test")
        logger.handlers[0].flush()
        assert os.path.exists(log_path)

    def test_log_message_written_to_file(self, tmp_path):
        log_path = str(tmp_path / "streamer.log")
        configure_logging(log_path=log_path, console=False)
        logger = logging.getLogger("streamer")
        logger.info("unique-marker-abc123")
        logger.handlers[0].flush()
        content = open(log_path).read()
        assert "unique-marker-abc123" in content

    def test_log_format_includes_level_and_name(self, tmp_path):
        log_path = str(tmp_path / "streamer.log")
        configure_logging(log_path=log_path, console=False)
        logger = logging.getLogger("streamer")
        logger.warning("format-check")
        logger.handlers[0].flush()
        content = open(log_path).read()
        assert "WARNING" in content
        assert "streamer" in content
