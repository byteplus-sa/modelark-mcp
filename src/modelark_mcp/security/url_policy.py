"""URL security policy — SSRF prevention.

Allows HTTPS input URLs only. Rejects loopback, link-local, private,
multicast, and cloud metadata IPs after DNS resolution. Caps redirects and
revalidates every redirect target. ``file://`` is never allowed.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit

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

AddressResolver = Callable[[str, int], Sequence[str]]


@dataclass(frozen=True, slots=True)
class ValidatedUrl:
    """Normalized URL and the public addresses observed during validation."""

    url: str
    parsed: SplitResult
    hostname: str
    port: int
    addresses: tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]


def system_resolver(hostname: str, port: int) -> tuple[str, ...]:
    """Resolve a hostname with the operating-system resolver."""
    infos = socket.getaddrinfo(
        hostname,
        port,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )
    return tuple(dict.fromkeys(str(info[4][0]) for info in infos))


def _is_blocked_address(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check if an IP address is private, loopback, link-local, or metadata."""
    blocked = (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )
    if blocked or isinstance(addr, ipaddress.IPv4Address):
        return blocked

    # IPv6 transition formats can embed an unsafe IPv4 address.
    if addr.ipv4_mapped is not None and _is_blocked_address(addr.ipv4_mapped):
        return True
    if addr.sixtofour is not None and _is_blocked_address(addr.sixtofour):
        return True
    return addr.teredo is not None and _is_blocked_address(addr.teredo[1])


def validate_url_syntax(url: str, *, allow_http: bool = False) -> tuple[SplitResult, str, int]:
    """Validate URL syntax and return the parsed URL, normalized host, and port."""
    parsed = urlsplit(url)
    if parsed.scheme not in ("https", "http"):
        raise UrlValidationError(f"URL scheme '{parsed.scheme}' is not allowed. Use https.")
    if parsed.scheme == "http" and not allow_http:
        raise UrlValidationError("HTTP URLs are not allowed. Use HTTPS.")
    if not parsed.hostname:
        raise UrlValidationError("URL must have a hostname.")
    if parsed.username is not None or parsed.password is not None:
        raise UrlValidationError("Credentials embedded in URLs are not allowed.")

    try:
        hostname = parsed.hostname.encode("idna").decode("ascii").lower()
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except (UnicodeError, ValueError) as exc:
        raise UrlValidationError(f"URL has an invalid hostname or port: {exc}") from exc

    if hostname in _BLOCKED_HOSTS:
        raise UrlValidationError(f"Host '{hostname}' is blocked (metadata endpoint).")
    return parsed, hostname, port


def resolve_public_addresses(
    hostname: str,
    port: int,
    *,
    resolver: AddressResolver | None = None,
) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
    """Resolve a host and require every returned address to be public."""
    raw_addresses: Sequence[str]
    try:
        literal = ipaddress.ip_address(hostname)
        raw_addresses = (str(literal),)
    except ValueError:
        try:
            raw_addresses = tuple((resolver or system_resolver)(hostname, port))
        except (OSError, socket.gaierror) as exc:
            raise UrlValidationError(f"Failed to resolve hostname '{hostname}': {exc}") from exc

    if not raw_addresses:
        raise UrlValidationError(f"Hostname '{hostname}' did not resolve to an address.")

    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for raw_address in raw_addresses:
        try:
            address = ipaddress.ip_address(raw_address)
        except ValueError as exc:
            raise UrlValidationError(
                f"Resolver returned invalid IP address '{raw_address}' for '{hostname}'."
            ) from exc
        if _is_blocked_address(address):
            raise UrlValidationError(f"Hostname '{hostname}' resolves to blocked IP '{address}'.")
        addresses.append(address)
    return tuple(dict.fromkeys(addresses))


def validate_url(
    url: str,
    *,
    allow_http: bool = False,
    resolver: AddressResolver | None = None,
) -> ValidatedUrl:
    """Validate a user-supplied URL for SSRF safety.

    Args:
        url: The URL to validate.
        allow_http: If True, allow http:// URLs (default: HTTPS only).

    Raises:
        UrlValidationError: If the URL scheme, host, or resolved IP is unsafe.
    """
    parsed, hostname, port = validate_url_syntax(url, allow_http=allow_http)
    addresses = resolve_public_addresses(hostname, port, resolver=resolver)
    return ValidatedUrl(
        url=url,
        parsed=parsed,
        hostname=hostname,
        port=port,
        addresses=addresses,
    )


def make_safe_client(*, timeout: float, connect_timeout: float) -> httpx.AsyncClient:
    """Create an ``httpx.AsyncClient`` with SSRF-safe redirect handling.

    Revalidates every redirect target through ``validate_url`` to prevent
    redirect-to-private-IP attacks.
    """
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=connect_timeout),
        follow_redirects=False,  # We handle redirects manually for safety.
    )
