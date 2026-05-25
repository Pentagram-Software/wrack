"""Unit tests for edge/nginx Nginx HLS configuration.

Tests cover:
* :class:`~config.NginxConfigParams` validation (valid and invalid combinations)
* :func:`~config.load_from_env` environment variable parsing
* :func:`~generate_config.render` — verifies that generated nginx.conf contains
  all required directives for correct LL-HLS serving

All tests are purely in-process (no Nginx binary required).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path bootstrap: allow importing config and generate_config from parent dir.
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent.parent))

import config as cfg
import generate_config as gen
from config import (
    DEFAULT_CORS_ORIGIN,
    DEFAULT_LISTEN_PORT,
    DEFAULT_PLAYLIST_PROXY_TIMEOUT,
    DEFAULT_SEGMENT_CACHE_MAX_AGE,
    DEFAULT_UPSTREAM_HOST,
    DEFAULT_UPSTREAM_PORT,
    MIME_M3U8,
    MIME_TS,
    NginxConfigParams,
    load_from_env,
)


# ===========================================================================
# NginxConfigParams — defaults
# ===========================================================================


class TestDefaultParams:
    def test_default_upstream_host(self):
        assert NginxConfigParams().upstream_host == DEFAULT_UPSTREAM_HOST

    def test_default_upstream_port(self):
        assert NginxConfigParams().upstream_port == DEFAULT_UPSTREAM_PORT

    def test_default_listen_port(self):
        assert NginxConfigParams().listen_port == DEFAULT_LISTEN_PORT

    def test_default_segment_cache_max_age(self):
        assert NginxConfigParams().segment_cache_max_age == DEFAULT_SEGMENT_CACHE_MAX_AGE

    def test_default_playlist_proxy_timeout(self):
        assert NginxConfigParams().playlist_proxy_timeout == DEFAULT_PLAYLIST_PROXY_TIMEOUT

    def test_default_cors_origin(self):
        assert NginxConfigParams().cors_origin == DEFAULT_CORS_ORIGIN

    def test_default_worker_processes(self):
        assert NginxConfigParams().worker_processes == "auto"

    def test_default_worker_connections(self):
        assert NginxConfigParams().worker_connections == 1024

    def test_default_keepalive_upstream(self):
        assert NginxConfigParams().keepalive_upstream == 32

    def test_defaults_are_valid(self):
        """Default parameters must pass validation without raising."""
        NginxConfigParams().validate()


# ===========================================================================
# NginxConfigParams — port validation
# ===========================================================================


class TestPortValidation:
    def test_upstream_port_zero_is_invalid(self):
        with pytest.raises(ValueError, match="upstream_port"):
            NginxConfigParams(upstream_port=0).validate()

    def test_upstream_port_negative_is_invalid(self):
        with pytest.raises(ValueError, match="upstream_port"):
            NginxConfigParams(upstream_port=-1).validate()

    def test_upstream_port_too_high_is_invalid(self):
        with pytest.raises(ValueError, match="upstream_port"):
            NginxConfigParams(upstream_port=65536).validate()

    def test_upstream_port_max_valid(self):
        NginxConfigParams(upstream_port=65535, listen_port=80).validate()

    def test_upstream_port_min_valid(self):
        NginxConfigParams(upstream_port=1, listen_port=80).validate()

    def test_listen_port_zero_is_invalid(self):
        with pytest.raises(ValueError, match="listen_port"):
            NginxConfigParams(listen_port=0).validate()

    def test_listen_port_negative_is_invalid(self):
        with pytest.raises(ValueError, match="listen_port"):
            NginxConfigParams(listen_port=-100).validate()

    def test_listen_port_too_high_is_invalid(self):
        with pytest.raises(ValueError, match="listen_port"):
            NginxConfigParams(listen_port=70000).validate()

    def test_different_ports_on_loopback_valid(self):
        NginxConfigParams(upstream_host="127.0.0.1", upstream_port=8888, listen_port=80).validate()

    def test_same_ports_on_loopback_causes_proxy_loop(self):
        with pytest.raises(ValueError, match="proxy loop"):
            NginxConfigParams(upstream_host="127.0.0.1", upstream_port=8080, listen_port=8080).validate()

    def test_same_ports_on_localhost_causes_proxy_loop(self):
        with pytest.raises(ValueError, match="proxy loop"):
            NginxConfigParams(upstream_host="localhost", upstream_port=80, listen_port=80).validate()

    def test_same_ports_on_loopback_ipv6_causes_proxy_loop(self):
        with pytest.raises(ValueError, match="proxy loop"):
            NginxConfigParams(upstream_host="::1", upstream_port=80, listen_port=80).validate()

    def test_same_ports_on_external_host_is_valid(self):
        # External upstream host: same port numbers are fine (different machine).
        NginxConfigParams(upstream_host="192.168.1.100", upstream_port=80, listen_port=80).validate()


# ===========================================================================
# NginxConfigParams — cache / timeout validation
# ===========================================================================


class TestCacheAndTimeoutValidation:
    def test_segment_cache_max_age_zero_is_valid(self):
        NginxConfigParams(segment_cache_max_age=0).validate()

    def test_segment_cache_max_age_negative_is_invalid(self):
        with pytest.raises(ValueError, match="segment_cache_max_age"):
            NginxConfigParams(segment_cache_max_age=-1).validate()

    def test_playlist_proxy_timeout_one_is_valid(self):
        NginxConfigParams(playlist_proxy_timeout=1).validate()

    def test_playlist_proxy_timeout_zero_is_invalid(self):
        with pytest.raises(ValueError, match="playlist_proxy_timeout"):
            NginxConfigParams(playlist_proxy_timeout=0).validate()

    def test_playlist_proxy_timeout_negative_is_invalid(self):
        with pytest.raises(ValueError, match="playlist_proxy_timeout"):
            NginxConfigParams(playlist_proxy_timeout=-5).validate()

    def test_playlist_proxy_timeout_exceeds_blocking_reload_default(self):
        """LL-HLS blocking reload waits up to 10 s; timeout must be > 10."""
        params = NginxConfigParams()
        assert params.playlist_proxy_timeout > 10, (
            "playlist_proxy_timeout must exceed the LL-HLS server blocking-"
            "reload wait of 10 s to prevent premature 504 responses"
        )


# ===========================================================================
# NginxConfigParams — worker validation
# ===========================================================================


class TestWorkerValidation:
    def test_worker_processes_auto_is_valid(self):
        NginxConfigParams(worker_processes="auto").validate()

    def test_worker_processes_positive_int_string_is_valid(self):
        NginxConfigParams(worker_processes="4").validate()

    def test_worker_processes_one_is_valid(self):
        NginxConfigParams(worker_processes="1").validate()

    def test_worker_processes_zero_string_is_invalid(self):
        with pytest.raises(ValueError, match="worker_processes"):
            NginxConfigParams(worker_processes="0").validate()

    def test_worker_processes_negative_string_is_invalid(self):
        with pytest.raises(ValueError, match="worker_processes"):
            NginxConfigParams(worker_processes="-1").validate()

    def test_worker_processes_non_numeric_string_is_invalid(self):
        with pytest.raises(ValueError, match="worker_processes"):
            NginxConfigParams(worker_processes="many").validate()

    def test_worker_connections_one_is_valid(self):
        NginxConfigParams(worker_connections=1).validate()

    def test_worker_connections_zero_is_invalid(self):
        with pytest.raises(ValueError, match="worker_connections"):
            NginxConfigParams(worker_connections=0).validate()

    def test_worker_connections_negative_is_invalid(self):
        with pytest.raises(ValueError, match="worker_connections"):
            NginxConfigParams(worker_connections=-10).validate()

    def test_keepalive_upstream_one_is_valid(self):
        NginxConfigParams(keepalive_upstream=1).validate()

    def test_keepalive_upstream_zero_is_invalid(self):
        with pytest.raises(ValueError, match="keepalive_upstream"):
            NginxConfigParams(keepalive_upstream=0).validate()


# ===========================================================================
# NginxConfigParams — CORS validation
# ===========================================================================


class TestCorsValidation:
    def test_wildcard_origin_is_valid(self):
        NginxConfigParams(cors_origin="*").validate()

    def test_specific_origin_is_valid(self):
        NginxConfigParams(cors_origin="https://example.com").validate()

    def test_empty_origin_is_invalid(self):
        with pytest.raises(ValueError, match="cors_origin"):
            NginxConfigParams(cors_origin="").validate()

    def test_whitespace_only_origin_is_invalid(self):
        with pytest.raises(ValueError, match="cors_origin"):
            NginxConfigParams(cors_origin="   ").validate()


# ===========================================================================
# NginxConfigParams — multiple errors
# ===========================================================================


class TestMultipleErrors:
    def test_multiple_invalid_fields_are_all_reported(self):
        """All validation errors should be reported in a single exception."""
        with pytest.raises(ValueError) as exc_info:
            NginxConfigParams(
                upstream_port=0,
                listen_port=0,
                segment_cache_max_age=-1,
                playlist_proxy_timeout=0,
                worker_connections=0,
                keepalive_upstream=0,
                cors_origin="",
            ).validate()
        msg = str(exc_info.value)
        assert "upstream_port" in msg
        assert "listen_port" in msg
        assert "segment_cache_max_age" in msg
        assert "playlist_proxy_timeout" in msg
        assert "worker_connections" in msg
        assert "keepalive_upstream" in msg
        assert "cors_origin" in msg


# ===========================================================================
# load_from_env
# ===========================================================================


class TestLoadFromEnv:
    def test_defaults_when_no_env_set(self, monkeypatch):
        for key in (
            "NGINX_UPSTREAM_HOST",
            "NGINX_UPSTREAM_PORT",
            "NGINX_LISTEN_PORT",
            "NGINX_SEGMENT_CACHE_AGE",
            "NGINX_PLAYLIST_TIMEOUT",
            "NGINX_CORS_ORIGIN",
            "NGINX_WORKER_PROCESSES",
            "NGINX_WORKER_CONNECTIONS",
            "NGINX_KEEPALIVE_UPSTREAM",
        ):
            monkeypatch.delenv(key, raising=False)

        params = load_from_env()
        assert params.upstream_host == DEFAULT_UPSTREAM_HOST
        assert params.upstream_port == DEFAULT_UPSTREAM_PORT
        assert params.listen_port == DEFAULT_LISTEN_PORT
        assert params.segment_cache_max_age == DEFAULT_SEGMENT_CACHE_MAX_AGE
        assert params.playlist_proxy_timeout == DEFAULT_PLAYLIST_PROXY_TIMEOUT
        assert params.cors_origin == DEFAULT_CORS_ORIGIN
        assert params.worker_processes == "auto"
        assert params.worker_connections == 1024
        assert params.keepalive_upstream == 32

    def test_custom_values_from_env(self, monkeypatch):
        monkeypatch.setenv("NGINX_UPSTREAM_HOST", "192.168.1.50")
        monkeypatch.setenv("NGINX_UPSTREAM_PORT", "9000")
        monkeypatch.setenv("NGINX_LISTEN_PORT", "8080")
        monkeypatch.setenv("NGINX_SEGMENT_CACHE_AGE", "3600")
        monkeypatch.setenv("NGINX_PLAYLIST_TIMEOUT", "20")
        monkeypatch.setenv("NGINX_CORS_ORIGIN", "https://myapp.example.com")
        monkeypatch.setenv("NGINX_WORKER_PROCESSES", "2")
        monkeypatch.setenv("NGINX_WORKER_CONNECTIONS", "512")
        monkeypatch.setenv("NGINX_KEEPALIVE_UPSTREAM", "16")

        params = load_from_env()
        assert params.upstream_host == "192.168.1.50"
        assert params.upstream_port == 9000
        assert params.listen_port == 8080
        assert params.segment_cache_max_age == 3600
        assert params.playlist_proxy_timeout == 20
        assert params.cors_origin == "https://myapp.example.com"
        assert params.worker_processes == "2"
        assert params.worker_connections == 512
        assert params.keepalive_upstream == 16

    def test_non_integer_port_env_raises(self, monkeypatch):
        monkeypatch.setenv("NGINX_UPSTREAM_PORT", "not_a_number")
        with pytest.raises(ValueError, match="NGINX_UPSTREAM_PORT"):
            load_from_env()

    def test_non_integer_listen_port_env_raises(self, monkeypatch):
        monkeypatch.setenv("NGINX_LISTEN_PORT", "eighty")
        with pytest.raises(ValueError, match="NGINX_LISTEN_PORT"):
            load_from_env()


# ===========================================================================
# generate_config.render — content checks
# ===========================================================================


class TestRenderUpstream:
    def _conf(self, **kwargs) -> str:
        params = NginxConfigParams(**kwargs)
        params.validate()
        return gen.render(params)

    def test_upstream_block_present(self):
        assert "upstream llhls" in self._conf()

    def test_upstream_host_and_port_in_conf(self):
        conf = self._conf(upstream_host="10.0.0.1", upstream_port=9999, listen_port=80)
        assert "server 10.0.0.1:9999" in conf

    def test_listen_port_in_conf(self):
        conf = self._conf(listen_port=8080)
        assert "listen       8080" in conf

    def test_keepalive_upstream_in_conf(self):
        conf = self._conf(keepalive_upstream=64)
        assert "keepalive 64" in conf

    def test_worker_processes_auto_in_conf(self):
        assert "worker_processes  auto" in self._conf(worker_processes="auto")

    def test_worker_processes_numeric_in_conf(self):
        assert "worker_processes  4" in self._conf(worker_processes="4")

    def test_worker_connections_in_conf(self):
        assert "worker_connections  2048" in self._conf(worker_connections=2048)


class TestRenderMimeTypes:
    def _conf(self) -> str:
        params = NginxConfigParams()
        return gen.render(params)

    def test_ts_mime_type_present(self):
        assert MIME_TS in self._conf()

    def test_m3u8_mime_type_present(self):
        assert MIME_M3U8 in self._conf()

    def test_ts_location_block_present(self):
        assert r"\.ts$" in self._conf()

    def test_m3u8_location_block_present(self):
        assert r"\.m3u8$" in self._conf()


class TestRenderCorsHeaders:
    def test_cors_wildcard_in_conf(self):
        conf = gen.render(NginxConfigParams(cors_origin="*"))
        assert 'Access-Control-Allow-Origin  "*"' in conf

    def test_cors_specific_origin_in_conf(self):
        conf = gen.render(NginxConfigParams(cors_origin="https://example.com"))
        assert 'Access-Control-Allow-Origin  "https://example.com"' in conf

    def test_cors_allow_methods_in_ts_block(self):
        conf = gen.render(NginxConfigParams())
        assert "Access-Control-Allow-Methods" in conf

    def test_cors_allow_headers_range_in_ts_block(self):
        conf = gen.render(NginxConfigParams())
        assert "Range" in conf

    def test_cors_expose_headers_in_ts_block(self):
        conf = gen.render(NginxConfigParams())
        assert "Access-Control-Expose-Headers" in conf

    def test_options_preflight_handled_in_root_location(self):
        conf = gen.render(NginxConfigParams())
        assert "OPTIONS" in conf
        assert "return 204" in conf


class TestRenderCachingDirectives:
    def test_segment_cache_long_max_age(self):
        conf = gen.render(NginxConfigParams(segment_cache_max_age=31_536_000))
        assert "max-age=31536000" in conf

    def test_segment_cache_custom_max_age(self):
        conf = gen.render(NginxConfigParams(segment_cache_max_age=3600))
        assert "max-age=3600" in conf

    def test_segment_cache_immutable_directive(self):
        conf = gen.render(NginxConfigParams())
        # Immutable tells browsers not to revalidate during the max-age window.
        assert "immutable" in conf

    def test_playlist_no_cache(self):
        conf = gen.render(NginxConfigParams())
        assert "no-cache" in conf
        assert "no-store" in conf

    def test_playlist_must_revalidate(self):
        conf = gen.render(NginxConfigParams())
        assert "must-revalidate" in conf

    def test_playlist_pragma_no_cache(self):
        conf = gen.render(NginxConfigParams())
        assert 'Pragma "no-cache"' in conf

    def test_playlist_expires_zero(self):
        conf = gen.render(NginxConfigParams())
        assert 'Expires "0"' in conf


class TestRenderProxySettings:
    def test_proxy_http_version_11(self):
        conf = gen.render(NginxConfigParams())
        assert "proxy_http_version      1.1" in conf

    def test_proxy_set_header_connection_empty(self):
        conf = gen.render(NginxConfigParams())
        # Empty Connection header enables keep-alive to upstream.
        assert 'proxy_set_header        Connection ""' in conf

    def test_playlist_proxy_read_timeout_in_conf(self):
        conf = gen.render(NginxConfigParams(playlist_proxy_timeout=20))
        assert "proxy_read_timeout      20s" in conf

    def test_playlist_proxy_buffering_off(self):
        conf = gen.render(NginxConfigParams())
        assert "proxy_buffering         off" in conf

    def test_proxy_hide_cache_control_header(self):
        conf = gen.render(NginxConfigParams())
        assert "proxy_hide_header       Cache-Control" in conf


class TestRenderHealthEndpoint:
    def test_health_location_present(self):
        conf = gen.render(NginxConfigParams())
        assert "location = /health" in conf

    def test_health_returns_200(self):
        conf = gen.render(NginxConfigParams())
        assert "return 200" in conf

    def test_health_access_log_off(self):
        conf = gen.render(NginxConfigParams())
        assert "access_log  off" in conf


class TestRenderServerTokens:
    def test_server_tokens_off(self):
        conf = gen.render(NginxConfigParams())
        assert "server_tokens off" in conf


class TestRenderStaticNginxConf:
    """Verify the committed static nginx.conf was generated with default params."""

    STATIC_CONF = Path(__file__).parent.parent / "nginx.conf"

    def test_static_conf_file_exists(self):
        assert self.STATIC_CONF.exists(), "nginx.conf must be committed to the repo"

    def test_static_conf_matches_default_render(self):
        expected = gen.render(NginxConfigParams())
        actual = self.STATIC_CONF.read_text(encoding="utf-8")
        assert actual == expected, (
            "nginx.conf is out of date; regenerate with: "
            "cd edge/nginx && python3 generate_config.py -o nginx.conf"
        )

    def test_static_conf_contains_upstream_block(self):
        conf = self.STATIC_CONF.read_text(encoding="utf-8")
        assert "upstream llhls" in conf

    def test_static_conf_has_ts_location(self):
        conf = self.STATIC_CONF.read_text(encoding="utf-8")
        assert r"\.ts$" in conf

    def test_static_conf_has_m3u8_location(self):
        conf = self.STATIC_CONF.read_text(encoding="utf-8")
        assert r"\.m3u8$" in conf

    def test_static_conf_has_health_endpoint(self):
        conf = self.STATIC_CONF.read_text(encoding="utf-8")
        assert "/health" in conf
