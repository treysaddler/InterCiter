"""Crossref REST API client — retraction / editorial-notice integrity signal (WP5).

Crossref is the first integrity source for the scite-parity retraction feature. A work's
DOI record carries an ``update-to`` block linking it to editorial updates (retractions,
expressions of concern, corrections) via Crossref's Retraction Watch integration. This
client fetches that record; interpretation into flags lives in
:mod:`interciter.services.integrity` so both layers are independently testable.

It mirrors the etiquette and hardening of :mod:`interciter.ingestion.semantic_scholar`:

* the Crossref "polite pool" is requested by identifying a contact ``mailto`` (raises
  priority and rate limits) in both the query string and the ``User-Agent``;
* requests are rate-limited and responses size-capped before parsing;
* responses are cached on disk (gitignored) keyed by the normalized DOI.

Only integrity flags are ever persisted onto the system of record — never Crossref text.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ..config import Settings, get_settings
from ..net import RETRY_STATUSES, retry_delay, ssl_context

_lock = threading.Lock()
_last_request = 0.0


class CrossrefError(RuntimeError):
    """Raised when a Crossref request fails or returns an unexpected shape."""


def normalize_doi(doi: str) -> str:
    """Return a bare, lowercased DOI, unwrapping any doi.org / ``doi:`` prefix."""
    value = doi.strip()
    lower = value.lower()
    for prefix in (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
        "doi:",
    ):
        if lower.startswith(prefix):
            value = value[len(prefix):]
            break
    if not value:
        raise CrossrefError("empty DOI")
    return value.lower()


def _rate_limit() -> None:
    global _last_request
    # Conservative default; Crossref's polite pool is generous but unadvertised.
    min_interval = 1.0
    with _lock:
        wait = min_interval - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()


def _headers(settings: Settings) -> dict[str, str]:
    contact = f"; mailto:{settings.crossref_mailto}" if settings.crossref_mailto else ""
    return {
        "User-Agent": (
            "interciter (+https://github.com/treysaddler/InterCiter"
            f"{contact})"
        ),
        "Accept": "application/json",
    }


def _request(url: str, settings: Settings) -> Any:
    request = urllib.request.Request(url, headers=_headers(settings), method="GET")
    max_bytes = settings.max_upload_bytes
    attempts = 5
    raw = b""
    for attempt in range(attempts):
        _rate_limit()
        try:
            with urllib.request.urlopen(
                request, timeout=30, context=ssl_context()
            ) as response:
                raw = response.read(max_bytes + 1)
            break
        except urllib.error.HTTPError as exc:
            if exc.code in RETRY_STATUSES and attempt < attempts - 1:
                time.sleep(retry_delay(attempt, exc.headers.get("Retry-After")))
                continue
            raise CrossrefError(f"HTTP {exc.code} for {url}: {exc.reason}") from exc
        except Exception as exc:  # noqa: BLE001 — urllib raises a variety of errors
            raise CrossrefError(f"request failed: {exc}") from exc
    if len(raw) > max_bytes:
        raise CrossrefError(f"response exceeds max_upload_bytes ({max_bytes})")
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise CrossrefError(f"invalid JSON from {url}: {exc}") from exc


def _cache_path(settings: Settings, doi: str) -> Path:
    directory = Path(settings.crossref_cache_dir)
    directory.mkdir(parents=True, exist_ok=True)
    safe = urllib.parse.quote(doi, safe="")
    return directory / f"work__{safe}.json"


def get_work(
    doi: str,
    *,
    settings: Settings | None = None,
    use_cache: bool = True,
) -> dict | None:
    """Fetch a work's Crossref ``message`` record, or ``None`` if the DOI is unknown.

    A ``404`` (DOI not registered with Crossref) resolves to ``None`` rather than an
    error, so callers can treat "no integrity data" and "not found" uniformly.
    """
    settings = settings or get_settings()
    normalized = normalize_doi(doi)
    path = _cache_path(settings, normalized)
    if use_cache and path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        return cached.get("message")

    query = urllib.parse.urlencode(
        {"mailto": settings.crossref_mailto} if settings.crossref_mailto else {}
    )
    url = f"{settings.crossref_base}/works/{urllib.parse.quote(normalized, safe='')}"
    if query:
        url = f"{url}?{query}"
    try:
        payload = _request(url, settings)
    except CrossrefError as exc:
        if "HTTP 404" in str(exc):
            return None
        raise
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload.get("message")
