"""PMC Open Access fetcher.

Acquires real JATS XML for the evaluation gold set from the PMC Open Access subset via
NCBI E-utilities. Only paper *identifiers and annotations* are redistributed with the
repo; fetched full text is cached locally (gitignored), never committed, respecting
per-article licensing.

Etiquette and hardening:
* Requests identify a ``tool`` and contact ``email`` and are rate-limited (3 req/s
  without an API key, 10 with) as NCBI asks.
* Responses are size-capped before parsing (``max_upload_bytes``) and parsed with the
  hardened, ``defusedxml``-based JATS parser elsewhere in the pipeline.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from ..config import Settings, get_settings
from ..net import ssl_context

_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

_lock = threading.Lock()
_last_request = 0.0


class PMCFetchError(RuntimeError):
    """Raised when a paper cannot be fetched or is not in the OA subset."""


def normalize_pmcid(pmcid: str) -> str:
    """Return the bare numeric id from ``PMC123`` / ``pmc123`` / ``123``."""
    value = pmcid.strip().upper()
    if value.startswith("PMC"):
        value = value[3:]
    if not value.isdigit():
        raise PMCFetchError(f"not a valid PMCID: {pmcid!r}")
    return value


def _rate_limit(settings: Settings) -> None:
    global _last_request
    min_interval = 0.1 if settings.ncbi_api_key else 0.34
    with _lock:
        wait = min_interval - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()


def _common_params(settings: Settings) -> dict[str, str]:
    params = {"tool": settings.ncbi_tool}
    if settings.ncbi_email:
        params["email"] = settings.ncbi_email
    if settings.ncbi_api_key:
        params["api_key"] = settings.ncbi_api_key
    return params


def _get(url: str, settings: Settings, max_bytes: int) -> bytes:
    _rate_limit(settings)
    request = urllib.request.Request(
        url, headers={"User-Agent": f"{settings.ncbi_tool} (+{settings.ncbi_email or 'no-email'})"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30, context=ssl_context()) as response:
            data = response.read(max_bytes + 1)
    except Exception as exc:  # urllib raises a variety of errors
        raise PMCFetchError(f"request failed: {exc}") from exc
    if len(data) > max_bytes:
        raise PMCFetchError(f"response exceeds max_upload_bytes ({max_bytes})")
    return data


def _cache_path(settings: Settings, pmcid_numeric: str) -> Path:
    directory = Path(settings.pmc_cache_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"PMC{pmcid_numeric}.xml"


def fetch_jats(
    pmcid: str, settings: Settings | None = None, use_cache: bool = True
) -> str:
    """Fetch (and cache) the JATS XML for an open-access PMC article."""
    settings = settings or get_settings()
    numeric = normalize_pmcid(pmcid)
    cache = _cache_path(settings, numeric)
    if use_cache and cache.exists():
        return cache.read_text(encoding="utf-8")

    params = _common_params(settings) | {
        "db": "pmc",
        "id": numeric,
        "rettype": "xml",
        "retmode": "xml",
    }
    url = f"{_EUTILS}/efetch.fcgi?{urllib.parse.urlencode(params)}"
    raw = _get(url, settings, settings.max_upload_bytes).decode("utf-8", errors="replace")

    # efetch returns an error stub (no <body>/<article-meta>) for non-OA articles.
    if "<article" not in raw or ("The publisher of this article does not allow" in raw):
        raise PMCFetchError(
            f"PMC{numeric} is not available as full-text XML (not in the OA subset?)"
        )

    cache.write_text(raw, encoding="utf-8")
    return raw


def search_pmc(term: str, retmax: int = 20, settings: Settings | None = None) -> list[str]:
    """Search PMC (Open Access filter recommended in ``term``); return ``PMC…`` ids."""
    settings = settings or get_settings()
    params = _common_params(settings) | {
        "db": "pmc",
        "term": term,
        "retmax": str(retmax),
        "retmode": "json",
    }
    url = f"{_EUTILS}/esearch.fcgi?{urllib.parse.urlencode(params)}"
    raw = _get(url, settings, 2 * 1024 * 1024).decode("utf-8", errors="replace")
    try:
        payload = json.loads(raw)
        idlist = payload["esearchresult"]["idlist"]
    except (json.JSONDecodeError, KeyError) as exc:
        raise PMCFetchError(f"unexpected esearch response: {exc}") from exc
    return [f"PMC{uid}" for uid in idlist]
