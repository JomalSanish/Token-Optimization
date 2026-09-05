"""
validators.py — URL validation for provider base_url and adapter_template.request_url.

Constitution §VIII: Adapter template URLs and openai_compatible base_url values MUST be
validated at save time: HTTPS only and MUST NOT resolve to private/loopback/link-local
addresses (SSRF guard).

This module uses only Python stdlib (socket, ipaddress) — no third-party dependencies.
"""
import ipaddress
import socket
from urllib.parse import urlparse


def validate_provider_url(url: str) -> None:
    """Validate that a provider URL is safe to store and later call.

    Raises:
        ValueError: with a descriptive message identifying the specific violation.

    Rules enforced:
        1. Scheme must be exactly 'https' (not 'http', 'ftp', or any other).
        2. The hostname must resolve via DNS.
        3. Every resolved IP address must be a globally-routable unicast address —
           private (RFC 1918 / RFC 4193), loopback, link-local, multicast,
           reserved, or unspecified ranges are all rejected.
    """
    if not url or not url.strip():
        raise ValueError("Provider URL must not be empty")

    parsed = urlparse(url)

    # Rule 1: HTTPS-only
    if parsed.scheme != "https":
        raise ValueError(
            f"Provider URL must use the 'https' scheme, got '{parsed.scheme}://'. "
            "Plain HTTP and all other schemes are rejected to ensure TLS transport."
        )

    hostname = parsed.hostname
    if not hostname:
        raise ValueError(
            f"Provider URL '{url}' does not contain a valid hostname."
        )

    # Rule 2 + 3: Resolve hostname and check every resulting IP
    try:
        results = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(
            f"Provider URL hostname '{hostname}' could not be resolved: {exc}"
        )

    if not results:
        raise ValueError(
            f"Provider URL hostname '{hostname}' resolved to no addresses."
        )

    for _family, _type, _proto, _canonname, sockaddr in results:
        raw_ip = sockaddr[0]  # first element of sockaddr tuple is the IP string
        try:
            ip = ipaddress.ip_address(raw_ip)
        except ValueError:
            # Shouldn't happen if getaddrinfo returned it, but be defensive
            raise ValueError(
                f"Provider URL hostname '{hostname}' resolved to an unparseable "
                f"address: '{raw_ip}'"
            )

        # Reject any address that is not a globally-routable public unicast address.
        #
        # IMPORTANT — ordering matters here: Python's ipaddress module classifies
        # is_private as a superset that also covers loopback, link-local, reserved
        # (e.g. 240.0.0.0/4), and unspecified (0.0.0.0 / ::) addresses. Only
        # multicast addresses fall outside is_private. So the narrow, more specific
        # categories are checked FIRST, with is_private last as the broad catch-all
        # — otherwise every one of those narrower branches would be unreachable
        # dead code, and callers would only ever see the generic "private address"
        # message instead of the more informative specific one.
        if ip.is_loopback:
            raise ValueError(
                f"Provider URL hostname '{hostname}' resolves to a loopback address "
                f"({raw_ip}). Loopback addresses are rejected as an SSRF guard."
            )
        if ip.is_unspecified:
            raise ValueError(
                f"Provider URL hostname '{hostname}' resolves to an unspecified address "
                f"({raw_ip}). Unspecified addresses are rejected as an SSRF guard."
            )
        if ip.is_link_local:
            raise ValueError(
                f"Provider URL hostname '{hostname}' resolves to a link-local address "
                f"({raw_ip}). Link-local ranges are rejected as an SSRF guard."
            )
        if ip.is_reserved:
            raise ValueError(
                f"Provider URL hostname '{hostname}' resolves to a reserved address "
                f"({raw_ip}). Reserved addresses are rejected as an SSRF guard."
            )
        if ip.is_multicast:
            raise ValueError(
                f"Provider URL hostname '{hostname}' resolves to a multicast address "
                f"({raw_ip}). Multicast addresses are rejected as an SSRF guard."
            )
        if ip.is_private:
            raise ValueError(
                f"Provider URL hostname '{hostname}' resolves to a private address "
                f"({raw_ip}). Private IP ranges are rejected as an SSRF guard."
            )
