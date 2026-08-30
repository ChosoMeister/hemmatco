from __future__ import annotations

import hashlib
import socket
import ssl
from urllib.parse import urlparse


class CertificatePinError(RuntimeError):
    """Raised when the source certificate does not match the emergency pin."""


def certificate_sha256(url: str, timeout: int) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise CertificatePinError("Certificate pinning requires an HTTPS URL")

    port = parsed.port or 443
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with socket.create_connection((parsed.hostname, port), timeout=timeout) as raw:
        with context.wrap_socket(raw, server_hostname=parsed.hostname) as wrapped:
            certificate = wrapped.getpeercert(binary_form=True)
    if not certificate:
        raise CertificatePinError("The source did not present a TLS certificate")
    return hashlib.sha256(certificate).hexdigest().upper()


def allow_pinned_expired_certificate(
    url: str,
    expected_sha256: str,
    timeout: int,
) -> None:
    if not expected_sha256:
        raise CertificatePinError("No expired-certificate fingerprint is configured")
    actual_sha256 = certificate_sha256(url, timeout)
    if actual_sha256 != expected_sha256:
        raise CertificatePinError(
            "Source certificate fingerprint changed; refusing the insecure fallback "
            f"(expected {expected_sha256}, received {actual_sha256})"
        )


__all__ = ["CertificatePinError", "allow_pinned_expired_certificate", "certificate_sha256"]
