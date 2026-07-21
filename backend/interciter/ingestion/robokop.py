"""ROBOKOP / NCATS Translator client (entity grounding + one-hop edges).

Three reference services from the Translator stack, all cache-first and network-gated:

* **Name Resolver** — free-text name → candidate CURIEs
  (``name-resolution-sri.renci.org/lookup``);
* **Node Normalizer** — a CURIE → its canonical clique (preferred id, equivalent
  identifiers, BioLink semantic types) (``nodenormalization-sri.renci.org``);
* **ROBOKOP KG (TRAPI)** — a one-hop query between a subject and object CURIE via
  Automat's ``robokopkg`` endpoint, returning knowledge-graph edges with their
  provenance ``sources``.

Grounding produces stable CURIEs so target resolution and clustering key on canonical
identifiers rather than surface strings; TRAPI lookups provide *context/corroboration*
against prior biomedical knowledge and are never treated as a truth oracle that could
override a source-grounded extraction.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ..config import Settings, get_settings

_lock = threading.Lock()
_last_request = 0.0


class RobokopError(RuntimeError):
    """Raised when a Translator/ROBOKOP request fails or returns an unexpected shape."""


def _rate_limit() -> None:
    global _last_request
    min_interval = 0.34  # be a polite neighbor on shared public infrastructure
    with _lock:
        wait = min_interval - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()


def _request(
    url: str,
    settings: Settings,
    *,
    method: str = "GET",
    body: dict | None = None,
) -> Any:
    _rate_limit()
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {
        "User-Agent": "interciter (+https://github.com/treysaddler/InterCiter)",
        "Accept": "application/json",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    max_bytes = settings.max_upload_bytes
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        raise RobokopError(f"HTTP {exc.code} for {url}: {exc.reason}") from exc
    except Exception as exc:  # noqa: BLE001 — urllib raises a variety of errors
        raise RobokopError(f"request failed: {exc}") from exc
    if len(raw) > max_bytes:
        raise RobokopError(f"response exceeds max_upload_bytes ({max_bytes})")
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise RobokopError(f"invalid JSON from {url}: {exc}") from exc


def _cache_path(settings: Settings, key: str) -> Path:
    directory = Path(settings.robokop_cache_dir)
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return directory / f"{digest}.json"


def _cached(settings: Settings, key: str, fetch, use_cache: bool) -> Any:
    path = _cache_path(settings, key)
    if use_cache and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    payload = fetch()
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def lookup_name(
    name: str,
    *,
    limit: int = 10,
    biolink_type: str | None = None,
    settings: Settings | None = None,
    use_cache: bool = True,
) -> list[dict]:
    """Resolve a free-text name to candidate CURIEs (Name Resolver ``/lookup``)."""
    settings = settings or get_settings()
    params: dict[str, str] = {"string": name, "limit": str(limit)}
    if biolink_type:
        params["biolink_type"] = biolink_type
    url = f"{settings.name_res_url.rstrip('/')}/lookup?{urllib.parse.urlencode(params)}"
    key = f"name__{name}__{limit}__{biolink_type or ''}"
    return _cached(settings, key, lambda: _request(url, settings, method="POST"), use_cache)


def normalize_nodes(
    curies: list[str],
    *,
    conflate: bool = True,
    settings: Settings | None = None,
    use_cache: bool = True,
) -> dict[str, dict | None]:
    """Map CURIEs to their canonical clique via the Node Normalizer.

    Returns a mapping ``curie → {"id": {...}, "equivalent_identifiers": [...],
    "type": [...]}`` (or ``None`` when the id is unknown to Babel).
    """
    settings = settings or get_settings()
    if not curies:
        return {}
    url = f"{settings.node_norm_url.rstrip('/')}/get_normalized_nodes"
    body = {"curies": curies, "conflate": conflate}
    key = f"norm__{'|'.join(sorted(curies))}__{conflate}"
    return _cached(settings, key, lambda: _request(url, settings, method="POST", body=body), use_cache)


def ground(
    name_or_curie: str,
    *,
    biolink_type: str | None = None,
    settings: Settings | None = None,
    use_cache: bool = True,
) -> dict | None:
    """Ground a name or CURIE to a single canonical node.

    A CURIE (``prefix:local``) is normalized directly; free text is resolved to its top
    Name-Resolver candidate first, then normalized. Returns the normalized node record
    or ``None`` if nothing resolves.
    """
    settings = settings or get_settings()
    curie = name_or_curie.strip()
    looks_like_curie = ":" in curie and not curie.lower().startswith(("http://", "https://"))
    if not looks_like_curie:
        candidates = lookup_name(
            curie, biolink_type=biolink_type, settings=settings, use_cache=use_cache
        )
        if not candidates:
            return None
        curie = candidates[0]["curie"]
    normalized = normalize_nodes(
        [curie], settings=settings, use_cache=use_cache
    )
    return normalized.get(curie)


def _one_hop_query_graph(
    subject_curie: str,
    object_curie: str,
    predicate: str | None,
) -> dict:
    edge: dict[str, Any] = {"subject": "n0", "object": "n1"}
    if predicate:
        edge["predicates"] = [predicate]
    return {
        "message": {
            "query_graph": {
                "nodes": {
                    "n0": {"ids": [subject_curie]},
                    "n1": {"ids": [object_curie]},
                },
                "edges": {"e0": edge},
            }
        }
    }


def query_edges(
    subject_curie: str,
    object_curie: str,
    *,
    predicate: str | None = None,
    settings: Settings | None = None,
    use_cache: bool = True,
) -> list[dict]:
    """Return ROBOKOP KG edges between a subject and object CURIE (TRAPI one-hop).

    Each edge is flattened to ``{"subject", "predicate", "object", "sources"}`` where
    ``sources`` carries the upstream ``retrieval_source`` provenance suitable for the
    BioLink ``primary_knowledge_source`` / ``aggregator_knowledge_source`` slots.
    """
    settings = settings or get_settings()
    query = _one_hop_query_graph(subject_curie, object_curie, predicate)
    key = f"trapi__{subject_curie}__{predicate or '*'}__{object_curie}"
    payload = _cached(
        settings,
        key,
        lambda: _request(settings.robokop_trapi_url, settings, method="POST", body=query),
        use_cache,
    )
    kg = (payload.get("message") or {}).get("knowledge_graph") or {}
    edges = kg.get("edges") or {}
    out: list[dict] = []
    for edge in edges.values():
        out.append(
            {
                "subject": edge.get("subject"),
                "predicate": edge.get("predicate"),
                "object": edge.get("object"),
                "sources": edge.get("sources", []),
            }
        )
    return out
