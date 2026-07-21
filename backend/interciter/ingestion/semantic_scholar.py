"""Semantic Scholar Academic Graph API client (per-paper enrichment).

Fetches the enrichment data InterCiter's design assumes from Semantic Scholar's
Academic Graph: identifier mapping (``corpusId``/DOI/PMID/PMCID → ``PaperWork``),
resolved references with inline contexts and citation intents (weak supervision, *not*
InterCiter's function/stance ontology), SPECTER2 paper embeddings (paper-level
candidate narrowing only), and TLDR + core metadata.

This mirrors the etiquette and hardening of :mod:`interciter.ingestion.pmc`:

* an optional API key raises rate limits (unauthenticated traffic shares a global
  pool; a key's introductory limit is ~1 rps), sent as the ``x-api-key`` header;
* requests are rate-limited and responses are size-capped before parsing;
* responses are cached on disk (gitignored) keyed by the normalized id so each paper
  is fetched at most once.

Only identifiers and annotations are ever redistributed with the repo; fetched JSON is
cached locally and respects per-source licensing.
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

# Field sets requested per endpoint. Kept explicit so cached payloads are predictable
# and callers pay only for what they use.
DEFAULT_PAPER_FIELDS = (
    "externalIds",
    "title",
    "year",
    "venue",
    "authors",
    "abstract",
    "tldr",
    "publicationTypes",
    "fieldsOfStudy",
)
EMBEDDING_FIELD = "embedding.specter_v2"
DEFAULT_REFERENCE_FIELDS = (
    "contexts",
    "intents",
    "isInfluential",
    "citedPaper.externalIds",
    "citedPaper.title",
)

# Id prefixes accepted by the Academic Graph API, letting us resolve from what we
# already store on a ``PaperWork``.
_ID_PREFIXES = ("DOI", "PMID", "PMCID", "CORPUSID", "ARXIV", "MAG", "ACL", "URL")

_lock = threading.Lock()
_last_request = 0.0


class S2Error(RuntimeError):
    """Raised when a Semantic Scholar request fails or returns an unexpected shape."""


def normalize_paper_id(paper_id: str) -> str:
    """Return a Graph-API-ready id.

    Passes through already-prefixed ids (``DOI:…``, ``PMID:…``, ``CorpusId:…``, …) and
    raw 40-char S2 ``paperId`` hashes unchanged; bare digits are treated as a PMID only
    when explicitly prefixed by the caller — otherwise ambiguity is rejected.
    """
    value = paper_id.strip()
    if not value:
        raise S2Error("empty paper id")
    if ":" in value:
        prefix, _, rest = value.partition(":")
        if prefix.upper() not in _ID_PREFIXES:
            raise S2Error(f"unknown id prefix: {prefix!r}")
        if not rest:
            raise S2Error(f"id missing value after prefix: {value!r}")
        # Canonicalize the prefix casing the API expects for CorpusId; others uppercase.
        canonical = "CorpusId" if prefix.upper() == "CORPUSID" else prefix.upper()
        return f"{canonical}:{rest}"
    return value


def _rate_limit(settings: Settings) -> None:
    global _last_request
    # Conservative: ~1 rps with a key (introductory limit); slower without.
    min_interval = 1.05 if settings.s2_api_key else 1.1
    with _lock:
        wait = min_interval - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()


def _headers(settings: Settings) -> dict[str, str]:
    headers = {"User-Agent": "interciter (+https://github.com/treysaddler/InterCiter)"}
    if settings.s2_api_key:
        headers["x-api-key"] = settings.s2_api_key
    return headers


def _request(
    url: str,
    settings: Settings,
    *,
    method: str = "GET",
    body: dict | None = None,
) -> Any:
    _rate_limit(settings)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = _headers(settings)
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    max_bytes = settings.max_upload_bytes
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        raise S2Error(f"HTTP {exc.code} for {url}: {exc.reason}") from exc
    except Exception as exc:  # noqa: BLE001 — urllib raises a variety of errors
        raise S2Error(f"request failed: {exc}") from exc
    if len(raw) > max_bytes:
        raise S2Error(f"response exceeds max_upload_bytes ({max_bytes})")
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise S2Error(f"invalid JSON from {url}: {exc}") from exc


def _cache_path(settings: Settings, key: str) -> Path:
    directory = Path(settings.s2_cache_dir)
    directory.mkdir(parents=True, exist_ok=True)
    safe = urllib.parse.quote(key, safe="")
    return directory / f"{safe}.json"


def _cached_json(settings: Settings, key: str, fetch, use_cache: bool) -> Any:
    path = _cache_path(settings, key)
    if use_cache and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    payload = fetch()
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def get_paper(
    paper_id: str,
    fields: tuple[str, ...] = DEFAULT_PAPER_FIELDS,
    *,
    settings: Settings | None = None,
    use_cache: bool = True,
) -> dict:
    """Fetch a single paper's requested fields, caching the response."""
    settings = settings or get_settings()
    pid = normalize_paper_id(paper_id)
    query = urllib.parse.urlencode({"fields": ",".join(fields)})
    url = f"{settings.s2_graph_base}/paper/{urllib.parse.quote(pid, safe=':')}?{query}"
    key = f"paper__{pid}__{'-'.join(fields)}"
    return _cached_json(settings, key, lambda: _request(url, settings), use_cache)


def get_papers_batch(
    paper_ids: list[str],
    fields: tuple[str, ...] = ("externalIds", "title", "year"),
    *,
    settings: Settings | None = None,
) -> list[dict | None]:
    """Resolve up to 500 ids in one call (efficient identifier backfill).

    Returns a list aligned to ``paper_ids``; entries the API could not resolve are
    ``None``. Not cached (the batch key space is unbounded); callers cache downstream.
    """
    settings = settings or get_settings()
    if not paper_ids:
        return []
    if len(paper_ids) > 500:
        raise S2Error("batch endpoint accepts at most 500 ids per call")
    ids = [normalize_paper_id(p) for p in paper_ids]
    query = urllib.parse.urlencode({"fields": ",".join(fields)})
    url = f"{settings.s2_graph_base}/paper/batch?{query}"
    return _request(url, settings, method="POST", body={"ids": ids})


def get_references(
    paper_id: str,
    fields: tuple[str, ...] = DEFAULT_REFERENCE_FIELDS,
    *,
    limit: int = 1000,
    max_records: int | None = None,
    settings: Settings | None = None,
    use_cache: bool = True,
) -> list[dict]:
    """Fetch a paper's resolved references (contexts + intents), paginating fully.

    Each item carries the cited paper's ``externalIds`` (to resolve ``cited_work_id``),
    the inline ``contexts`` that mention it, and Semantic Scholar's ``intents`` — the
    latter stored as weak supervision, never mapped directly onto our ontology.
    """
    settings = settings or get_settings()
    pid = normalize_paper_id(paper_id)
    key = f"refs__{pid}__{'-'.join(fields)}"

    def fetch() -> list[dict]:
        out: list[dict] = []
        offset = 0
        while True:
            page_limit = min(limit, 1000)
            if max_records is not None:
                page_limit = min(page_limit, max_records - len(out))
                if page_limit <= 0:
                    break
            query = urllib.parse.urlencode(
                {"fields": ",".join(fields), "offset": offset, "limit": page_limit}
            )
            url = (
                f"{settings.s2_graph_base}/paper/"
                f"{urllib.parse.quote(pid, safe=':')}/references?{query}"
            )
            payload = _request(url, settings)
            batch = payload.get("data", [])
            out.extend(batch)
            nxt = payload.get("next")
            if not batch or nxt is None:
                break
            offset = nxt
        return out

    return _cached_json(settings, key, fetch, use_cache)


def get_embedding(
    paper_id: str,
    *,
    settings: Settings | None = None,
    use_cache: bool = True,
) -> list[float] | None:
    """Return the paper's SPECTER2 embedding vector, or ``None`` if unavailable.

    Paper-level only — used for candidate narrowing, never claim-level alignment.
    """
    paper = get_paper(
        paper_id, (EMBEDDING_FIELD,), settings=settings, use_cache=use_cache
    )
    embedding = paper.get("embedding")
    if not embedding:
        return None
    return embedding.get("vector")
