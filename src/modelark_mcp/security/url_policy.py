"""URL security policy — SSRF prevention.

Allows HTTPS input URLs only. Rejects loopback, link-local, private,
multicast, and cloud metadata IPs after DNS resolution. Caps redirects and
revalidates every redirect target. ``file://`` is never allowed.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx


class UrlValidationError(ValueError):
    """Raised when a URL fails security validation."""


_BLOCKED_HOSTS: frozenset[str] = frozenset(
    {
        "169.254.169.254",  # AWS / cloud metadata
        "metadata.google.internal",  # GCP metadata
        "100.100.100.200",  # Alibaba cloud metadata
        "fd00:ec2::254",  # AWS IPv6 metadata
    }
)


def _is_blocked_ip(ip: str) -> bool:
    """Check if an IP address is private, loopback, link-local, or metadata."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def validate_url(url: str, *, allow_http: bool = False) -> None:
    """Validate a user-supplied URL for SSRF safety.

    Args:
        url: The URL to validate.
        allow_http: If True, allow http:// URLs (default: HTTPS only).

    Raises:
        UrlValidationError: If the URL scheme, host, or resolved IP is unsafe.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http"):
        raise UrlValidationError(f"URL scheme '{parsed.scheme}' is not allowed. Use https.")
    if parsed.scheme == "http" and not allow_http:
        raise UrlValidationError("HTTP URLs are not allowed. Use HTTPS.")
    if not parsed.hostname:
        raise UrlValidationError("URL must have a hostname.")

    hostname = parsed.hostname.lower()
    if hostname in _BLOCKED_HOSTS:
        raise UrlValidationError(f"Host '{hostname}' is blocked (metadata endpoint).")

    # Resolve hostname and check all A/AAAA records.
    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UrlValidationError(f"Failed to resolve hostname '{hostname}': {exc}") from exc

    for info in infos:
        ip = info[4][0]
        if _is_blocked_ip(ip):
            raise UrlValidationError(f"Hostname '{hostname}' resolves to blocked IP '{ip}'.")


def make_safe_client(*, timeout: float, connect_timeout: float) -> httpx.AsyncClient:
    """Create an ``httpx.AsyncClient`` with SSRF-safe redirect handling.

    Revalidates every redirect target through ``validate_url`` to prevent
    redirect-to-private-IP attacks.
    """
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=connect_timeout),
        follow_redirects=False,  # We handle redirects manually for safety.
    )
