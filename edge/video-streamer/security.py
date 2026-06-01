"""TLS/HTTPS and WebRTC DTLS-SRTP security configuration.

Provides configuration dataclasses and utilities for:
- HTTPS/TLS on the HTTP/MJPEG and HLS video servers
- WebRTC DTLS-SRTP security profile selection
"""

import os
import ssl
from dataclasses import dataclass


SUPPORTED_TLS_VERSIONS: frozenset[str] = frozenset({"TLSv1.2", "TLSv1.3"})
SUPPORTED_DTLS_ROLES: frozenset[str] = frozenset({"auto", "client", "server"})
SUPPORTED_SRTP_PROFILES: frozenset[str] = frozenset(
    {
        "SRTP_AES128_CM_SHA1_80",
        "SRTP_AES128_CM_SHA1_32",
        "SRTP_AEAD_AES_128_GCM",
        "SRTP_AEAD_AES_256_GCM",
    }
)
DEFAULT_SRTP_PROFILES: tuple[str, ...] = (
    "SRTP_AES128_CM_SHA1_80",
    "SRTP_AES128_CM_SHA1_32",
)

_TLS_VERSION_MAP: dict[str, ssl.TLSVersion] = {
    "TLSv1.2": ssl.TLSVersion.TLSv1_2,
    "TLSv1.3": ssl.TLSVersion.TLSv1_3,
}


@dataclass(frozen=True)
class TLSConfig:
    """TLS configuration for an HTTPS server (HLS or MJPEG).

    Attributes:
        cert_path: Path to the PEM-encoded X.509 certificate file.
        key_path:  Path to the PEM-encoded private key file.
        min_tls_version: Minimum accepted TLS version (TLSv1.2 or TLSv1.3).
        ciphers: Optional OpenSSL cipher string; ``None`` uses the platform
                 defaults, which are secure on any modern Python build.
    """

    cert_path: str
    key_path: str
    min_tls_version: str = "TLSv1.2"
    ciphers: str | None = None

    def validate(self) -> None:
        """Raise an appropriate error if the configuration is invalid.

        Raises:
            ValueError: If a field value is logically invalid.
            FileNotFoundError: If a referenced file does not exist.
        """
        if not self.cert_path:
            raise ValueError("cert_path must not be empty")
        if not self.key_path:
            raise ValueError("key_path must not be empty")
        if not os.path.isfile(self.cert_path):
            raise FileNotFoundError(
                f"Certificate file not found: {self.cert_path}"
            )
        if not os.path.isfile(self.key_path):
            raise FileNotFoundError(
                f"Private key file not found: {self.key_path}"
            )
        if self.min_tls_version not in SUPPORTED_TLS_VERSIONS:
            raise ValueError(
                f"Unsupported TLS version '{self.min_tls_version}'. "
                f"Supported versions: {sorted(SUPPORTED_TLS_VERSIONS)}"
            )


@dataclass(frozen=True)
class WebRTCSecurityConfig:
    """DTLS-SRTP security configuration for a WebRTC media stream.

    Attributes:
        dtls_role:      DTLS role for the local endpoint — ``"auto"``,
                        ``"client"``, or ``"server"``.
        srtp_profiles:  Ordered tuple of SRTP protection profiles to advertise
                        during the DTLS-SRTP handshake.
        require_srtp:   When ``True``, reject any DTLS connection that does not
                        negotiate an SRTP profile (mandatory for WebRTC).
    """

    dtls_role: str = "auto"
    srtp_profiles: tuple[str, ...] = DEFAULT_SRTP_PROFILES
    require_srtp: bool = True

    def validate(self) -> None:
        """Raise ValueError if the configuration is invalid.

        Raises:
            ValueError: If ``dtls_role`` is unrecognised, ``srtp_profiles``
                        contains unknown names, or ``srtp_profiles`` is empty.
        """
        if self.dtls_role not in SUPPORTED_DTLS_ROLES:
            raise ValueError(
                f"Unsupported DTLS role '{self.dtls_role}'. "
                f"Supported roles: {sorted(SUPPORTED_DTLS_ROLES)}"
            )
        unknown = set(self.srtp_profiles) - SUPPORTED_SRTP_PROFILES
        if unknown:
            raise ValueError(
                f"Unknown SRTP profiles: {sorted(unknown)}. "
                f"Supported: {sorted(SUPPORTED_SRTP_PROFILES)}"
            )
        if not self.srtp_profiles:
            raise ValueError("srtp_profiles must not be empty")


def build_ssl_context(tls_config: TLSConfig) -> ssl.SSLContext:
    """Create a server-mode :class:`ssl.SSLContext` from a :class:`TLSConfig`.

    Args:
        tls_config: Validated TLS configuration.

    Returns:
        An :class:`ssl.SSLContext` ready to wrap a server socket.

    Raises:
        FileNotFoundError: If the certificate or key file is missing.
        ValueError: If the TLS version is not supported.
        ssl.SSLError: If the certificate/key pair cannot be loaded.
    """
    tls_config.validate()

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(tls_config.cert_path, tls_config.key_path)
    context.minimum_version = _TLS_VERSION_MAP[tls_config.min_tls_version]

    if tls_config.ciphers:
        context.set_ciphers(tls_config.ciphers)

    return context


def get_webrtc_srtp_profiles(
    config: WebRTCSecurityConfig | None = None,
) -> tuple[str, ...]:
    """Return the SRTP profiles to advertise during DTLS-SRTP negotiation.

    Args:
        config: WebRTC security configuration.  When ``None`` the module-level
                :data:`DEFAULT_SRTP_PROFILES` are returned.

    Returns:
        An ordered tuple of SRTP protection profile names.

    Raises:
        ValueError: If *config* is provided but contains invalid values.
    """
    if config is None:
        return DEFAULT_SRTP_PROFILES
    config.validate()
    return config.srtp_profiles
