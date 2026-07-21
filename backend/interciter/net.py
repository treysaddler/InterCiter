"""Shared HTTP/TLS helpers for the outbound clients.

All external fetchers (PMC, Semantic Scholar, ROBOKOP) verify TLS against a real trust
store — verification is never disabled. On macOS/Windows the system trust store (the
same one ``curl`` uses) is honored via :mod:`truststore`, which correctly picks up
enterprise/MITM roots installed in the OS keychain that OpenSSL's default bundle may
lack. Where ``truststore`` is unavailable, we fall back to certifi's bundle, then to the
OpenSSL default.
"""

from __future__ import annotations

import ssl
from functools import lru_cache

# HTTP statuses worth retrying with backoff (throttling / transient upstream errors).
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


@lru_cache(maxsize=1)
def ssl_context() -> ssl.SSLContext:
    """Return a verifying SSL context, preferring the OS trust store."""
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:  # noqa: BLE001 — truststore missing or unusable
        try:
            import certifi

            return ssl.create_default_context(cafile=certifi.where())
        except Exception:  # noqa: BLE001 — certifi missing
            return ssl.create_default_context()


def retry_delay(
    attempt: int,
    retry_after: str | None = None,
    *,
    base: float = 2.0,
    cap: float = 30.0,
) -> float:
    """Seconds to wait before ``attempt`` (0-based), honoring a ``Retry-After`` header.

    Falls back to capped exponential backoff (``base * 2**attempt``) when the server
    gives no numeric hint.
    """
    if retry_after:
        try:
            return min(float(retry_after), cap)
        except ValueError:
            pass
    return min(base * (2 ** attempt), cap)

