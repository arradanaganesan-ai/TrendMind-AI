"""SSRF protection for source extraction.

Every URL (from search results or AI output) must pass `validate_public_url`
before any request is made. DNS resolution is checked for every resolved
address, and redirect destinations are re-validated hop by hop.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

# Only standard web ports are allowed.
ALLOWED_PORTS = {80, 443, 8080, 8443, None}

# Suffixes that resolve inside local networks in practice.
_BLOCKED_HOST_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".lan",
    ".home",
    ".corp",
    ".intranet",
)

_BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain", "ip6-localhost"}


class SsrfError(ValueError):
    """Raised when a URL fails SSRF validation."""

    def __init__(self, message: str, code: str = "url_blocked") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ValidatedUrl:
    url: str
    host: str
    addresses: tuple[str, ...]


def _is_blocked_address(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return True  # Unparseable → block.
    return any(
        (
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_reserved,
            ip.is_unspecified,
            # CGNAT 100.64/10
            (ip.version == 4 and ipaddress.IPv4Address(addr) in ipaddress.IPv4Network("100.64.0.0/10")),
            # IPv6 unique local fc00::/7 (is_private covers it, kept explicit)
            (ip.version == 6 and (ipaddress.IPv6Address(addr).is_private)),
        )
    )


def resolve_host(host: str) -> tuple[str, ...]:
    """Resolve a hostname to IP addresses. Raises SsrfError on failure."""
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise SsrfError(f"Could not resolve host '{host}'.", code="dns_failed") from exc
    except UnicodeError as exc:
        raise SsrfError("Invalid host name.", code="invalid_host") from exc

    addresses = tuple(
        dict.fromkeys(info[4][0] for info in infos)  # dedupe, keep order
    )
    if not addresses:
        raise SsrfError(f"Host '{host}' resolved to no addresses.", code="dns_failed")
    return addresses


def validate_public_url(url: str) -> ValidatedUrl:
    """Validate that `url` targets a public host over http(s).

    Blocks: non-http(s) schemes, credentials in URL, localhost/private/
    loopback/link-local/CGNAT/IPv6-internal addresses, blocked name suffixes,
    and non-standard ports. Performs DNS resolution and checks every address.
    """
    if not url or len(url) > 2048:
        raise SsrfError("URL is missing or too long.", code="invalid_url")

    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise SsrfError("URL could not be parsed.", code="invalid_url") from exc

    if parsed.scheme not in {"http", "https"}:
        raise SsrfError("Only http and https URLs are allowed.", code="scheme_blocked")

    if parsed.username or parsed.password:
        raise SsrfError("URLs with embedded credentials are not allowed.", code="credentials_blocked")

    host = parsed.hostname
    if not host:
        raise SsrfError("URL has no host.", code="invalid_url")

    host_l = host.lower().rstrip(".")
    if host_l in _BLOCKED_HOSTNAMES or any(host_l.endswith(s) for s in _BLOCKED_HOST_SUFFIXES):
        raise SsrfError("URL targets a local address.", code="private_address")

    if parsed.port not in ALLOWED_PORTS:
        raise SsrfError("URL uses a disallowed port.", code="port_blocked")

    # If the host is already a literal IP, check it directly.
    try:
        literal = ipaddress.ip_address(host_l)
    except ValueError:
        literal = None

    if literal is not None:
        if _is_blocked_address(str(literal)):
            raise SsrfError("URL targets a private or internal address.", code="private_address")
        return ValidatedUrl(url=url, host=host_l, addresses=(str(literal),))

    # Domain: resolve and verify every address.
    addresses = resolve_host(host_l)
    for addr in addresses:
        if _is_blocked_address(addr):
            raise SsrfError(
                "URL resolves to a private or internal address.", code="private_address"
            )

    return ValidatedUrl(url=url, host=host_l, addresses=addresses)
