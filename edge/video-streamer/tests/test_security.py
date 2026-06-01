"""Unit tests for security.py — TLSConfig, WebRTCSecurityConfig, and utilities."""

import ssl
import subprocess
import sys
import pytest

from security import (
    DEFAULT_SRTP_PROFILES,
    SUPPORTED_DTLS_ROLES,
    SUPPORTED_SRTP_PROFILES,
    SUPPORTED_TLS_VERSIONS,
    TLSConfig,
    WebRTCSecurityConfig,
    build_ssl_context,
    get_webrtc_srtp_profiles,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def self_signed_certs(tmp_path_factory):
    """Generate a self-signed certificate and matching private key.

    Uses *openssl* (available on all supported platforms) so that
    :func:`~security.build_ssl_context` can actually load them.
    """
    cert_dir = tmp_path_factory.mktemp("certs")
    cert_file = cert_dir / "server.crt"
    key_file = cert_dir / "server.key"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(key_file),
            "-out",
            str(cert_file),
            "-days",
            "1",
            "-nodes",
            "-subj",
            "/CN=localhost",
        ],
        check=True,
        capture_output=True,
    )
    return cert_file, key_file


# ── TLSConfig.validate() ────────────────────────────────────────────────────


class TestTLSConfigValidate:
    def test_valid_config_does_not_raise(self, self_signed_certs):
        cert, key = self_signed_certs
        cfg = TLSConfig(cert_path=str(cert), key_path=str(key))
        cfg.validate()  # must not raise

    def test_empty_cert_path_raises_value_error(self, self_signed_certs):
        _, key = self_signed_certs
        with pytest.raises(ValueError, match="cert_path"):
            TLSConfig(cert_path="", key_path=str(key)).validate()

    def test_empty_key_path_raises_value_error(self, self_signed_certs):
        cert, _ = self_signed_certs
        with pytest.raises(ValueError, match="key_path"):
            TLSConfig(cert_path=str(cert), key_path="").validate()

    def test_missing_cert_file_raises_file_not_found(self, tmp_path, self_signed_certs):
        _, key = self_signed_certs
        with pytest.raises(FileNotFoundError, match="Certificate"):
            TLSConfig(
                cert_path=str(tmp_path / "missing.crt"),
                key_path=str(key),
            ).validate()

    def test_missing_key_file_raises_file_not_found(self, tmp_path, self_signed_certs):
        cert, _ = self_signed_certs
        with pytest.raises(FileNotFoundError, match="Private key"):
            TLSConfig(
                cert_path=str(cert),
                key_path=str(tmp_path / "missing.key"),
            ).validate()

    @pytest.mark.parametrize("bad_version", ["TLSv1.0", "TLSv1.1", "TLS1.2", "1.2", ""])
    def test_unsupported_tls_version_raises(self, self_signed_certs, bad_version):
        cert, key = self_signed_certs
        with pytest.raises(ValueError, match="Unsupported TLS version"):
            TLSConfig(
                cert_path=str(cert),
                key_path=str(key),
                min_tls_version=bad_version,
            ).validate()

    @pytest.mark.parametrize("version", sorted(SUPPORTED_TLS_VERSIONS))
    def test_all_supported_versions_accepted(self, self_signed_certs, version):
        cert, key = self_signed_certs
        TLSConfig(
            cert_path=str(cert),
            key_path=str(key),
            min_tls_version=version,
        ).validate()  # must not raise


# ── TLSConfig defaults ───────────────────────────────────────────────────────


class TestTLSConfigDefaults:
    def test_default_min_version_is_tls12(self, self_signed_certs):
        cert, key = self_signed_certs
        cfg = TLSConfig(cert_path=str(cert), key_path=str(key))
        assert cfg.min_tls_version == "TLSv1.2"

    def test_default_ciphers_is_none(self, self_signed_certs):
        cert, key = self_signed_certs
        cfg = TLSConfig(cert_path=str(cert), key_path=str(key))
        assert cfg.ciphers is None

    def test_frozen_dataclass_cannot_be_mutated(self, self_signed_certs):
        cert, key = self_signed_certs
        cfg = TLSConfig(cert_path=str(cert), key_path=str(key))
        with pytest.raises((AttributeError, TypeError)):
            cfg.cert_path = "/other/path"  # type: ignore[misc]


# ── build_ssl_context() ──────────────────────────────────────────────────────


class TestBuildSslContext:
    def test_returns_ssl_context_instance(self, self_signed_certs):
        cert, key = self_signed_certs
        ctx = build_ssl_context(TLSConfig(cert_path=str(cert), key_path=str(key)))
        assert isinstance(ctx, ssl.SSLContext)

    def test_minimum_version_tls12(self, self_signed_certs):
        cert, key = self_signed_certs
        ctx = build_ssl_context(
            TLSConfig(cert_path=str(cert), key_path=str(key), min_tls_version="TLSv1.2")
        )
        assert ctx.minimum_version == ssl.TLSVersion.TLSv1_2

    def test_minimum_version_tls13(self, self_signed_certs):
        cert, key = self_signed_certs
        ctx = build_ssl_context(
            TLSConfig(cert_path=str(cert), key_path=str(key), min_tls_version="TLSv1.3")
        )
        assert ctx.minimum_version == ssl.TLSVersion.TLSv1_3

    def test_missing_cert_raises_before_ssl(self, tmp_path, self_signed_certs):
        _, key = self_signed_certs
        cfg = TLSConfig(
            cert_path=str(tmp_path / "nope.crt"),
            key_path=str(key),
        )
        with pytest.raises(FileNotFoundError):
            build_ssl_context(cfg)

    def test_missing_key_raises_before_ssl(self, tmp_path, self_signed_certs):
        cert, _ = self_signed_certs
        cfg = TLSConfig(
            cert_path=str(cert),
            key_path=str(tmp_path / "nope.key"),
        )
        with pytest.raises(FileNotFoundError):
            build_ssl_context(cfg)

    def test_custom_ciphers_applied(self, self_signed_certs):
        cert, key = self_signed_certs
        # HIGH cipher suite string is always accepted by OpenSSL
        ctx = build_ssl_context(
            TLSConfig(cert_path=str(cert), key_path=str(key), ciphers="HIGH")
        )
        assert isinstance(ctx, ssl.SSLContext)

    def test_invalid_cipher_string_raises_ssl_error(self, self_signed_certs):
        cert, key = self_signed_certs
        with pytest.raises(ssl.SSLError):
            build_ssl_context(
                TLSConfig(
                    cert_path=str(cert),
                    key_path=str(key),
                    ciphers="NOT_A_VALID_CIPHER_SUITE_STRING_XYZ",
                )
            )

    def test_wrong_key_for_cert_raises_ssl_error(self, tmp_path, self_signed_certs):
        """A key that does not match the certificate must raise ssl.SSLError."""
        cert, _ = self_signed_certs
        # Generate a second, unrelated key
        other_key = tmp_path / "other.key"
        subprocess.run(
            ["openssl", "genrsa", "-out", str(other_key), "2048"],
            check=True,
            capture_output=True,
        )
        with pytest.raises(ssl.SSLError):
            build_ssl_context(TLSConfig(cert_path=str(cert), key_path=str(other_key)))


# ── WebRTCSecurityConfig defaults ───────────────────────────────────────────


class TestWebRTCSecurityConfigDefaults:
    def test_default_dtls_role(self):
        cfg = WebRTCSecurityConfig()
        assert cfg.dtls_role == "auto"

    def test_default_srtp_profiles(self):
        cfg = WebRTCSecurityConfig()
        assert cfg.srtp_profiles == DEFAULT_SRTP_PROFILES

    def test_require_srtp_defaults_true(self):
        cfg = WebRTCSecurityConfig()
        assert cfg.require_srtp is True

    def test_frozen_cannot_be_mutated(self):
        cfg = WebRTCSecurityConfig()
        with pytest.raises((AttributeError, TypeError)):
            cfg.dtls_role = "client"  # type: ignore[misc]


# ── WebRTCSecurityConfig.validate() ─────────────────────────────────────────


class TestWebRTCSecurityConfigValidate:
    def test_defaults_are_valid(self):
        WebRTCSecurityConfig().validate()

    @pytest.mark.parametrize("role", sorted(SUPPORTED_DTLS_ROLES))
    def test_all_supported_roles_accepted(self, role):
        WebRTCSecurityConfig(dtls_role=role).validate()

    def test_invalid_dtls_role_raises(self):
        with pytest.raises(ValueError, match="DTLS role"):
            WebRTCSecurityConfig(dtls_role="master").validate()

    @pytest.mark.parametrize("profile", sorted(SUPPORTED_SRTP_PROFILES))
    def test_each_profile_individually_valid(self, profile):
        WebRTCSecurityConfig(srtp_profiles=(profile,)).validate()

    def test_unknown_srtp_profile_raises(self):
        with pytest.raises(ValueError, match="Unknown SRTP profiles"):
            WebRTCSecurityConfig(
                srtp_profiles=("SRTP_AES128_CM_SHA1_80", "SRTP_UNKNOWN_ALGO")
            ).validate()

    def test_empty_srtp_profiles_raises(self):
        with pytest.raises(ValueError, match="srtp_profiles must not be empty"):
            WebRTCSecurityConfig(srtp_profiles=()).validate()

    def test_require_srtp_false_is_valid(self):
        WebRTCSecurityConfig(require_srtp=False).validate()

    def test_all_profiles_together_is_valid(self):
        WebRTCSecurityConfig(
            srtp_profiles=tuple(sorted(SUPPORTED_SRTP_PROFILES))
        ).validate()


# ── get_webrtc_srtp_profiles() ───────────────────────────────────────────────


class TestGetWebRTCSRTPProfiles:
    def test_none_config_returns_defaults(self):
        assert get_webrtc_srtp_profiles(None) == DEFAULT_SRTP_PROFILES

    def test_no_arg_returns_defaults(self):
        assert get_webrtc_srtp_profiles() == DEFAULT_SRTP_PROFILES

    def test_custom_profiles_returned(self):
        profiles = ("SRTP_AEAD_AES_256_GCM",)
        cfg = WebRTCSecurityConfig(srtp_profiles=profiles)
        assert get_webrtc_srtp_profiles(cfg) == profiles

    def test_invalid_config_raises(self):
        bad_cfg = WebRTCSecurityConfig(srtp_profiles=("SRTP_BOGUS",))
        with pytest.raises(ValueError):
            get_webrtc_srtp_profiles(bad_cfg)

    def test_returns_tuple(self):
        result = get_webrtc_srtp_profiles()
        assert isinstance(result, tuple)
