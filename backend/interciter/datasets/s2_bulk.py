"""Semantic Scholar Datasets API (bulk full-corpus snapshots).

Thin client over ``/datasets/v1``. Two concerns live here: talking to the JSON metadata
API (releases, per-dataset download links, incremental diffs), and streaming the
pre-signed S3 shard files to disk with hash verification. The local cache layout,
manifest, and lookup surface live in :mod:`interciter.datasets.store`.

The Datasets API **requires an API key** (``INTERCITER_S2_API_KEY``), sent as
``x-api-key`` on the metadata calls. The download URLs the API returns are pre-signed
S3 links that **expire** (hours) and must be fetched *without* the API-key header —
resolve them and download promptly; persist the release id and file basenames, never
the signed URLs.
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

# Datasets InterCiter builds off of, in rough order of usefulness for our slice.
KNOWN_DATASETS = (
    "papers",
    "citations",
    "abstracts",
    "s2orc",
    "embeddings-specter_v2",
    "tldrs",
)

_DOWNLOAD_CHUNK = 1 << 20  # 1 MiB streamed to disk; bulk shards bypass the response cap.

_lock = threading.Lock()
_last_request = 0.0


class S2DatasetsError(RuntimeError):
    """Raised on a Datasets API failure, missing key, or unexpected response shape."""


def _require_key(settings: Settings) -> str:
    if not settings.s2_api_key:
        raise S2DatasetsError(
            "the Datasets API requires an API key; set INTERCITER_S2_API_KEY"
        )
    return settings.s2_api_key


def _rate_limit(settings: Settings) -> None:
    global _last_request
    min_interval = 1.05 if settings.s2_api_key else 1.1
    with _lock:
        wait = min_interval - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()


def _get_json(url: str, settings: Settings) -> Any:
    _require_key(settings)
    _rate_limit(settings)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "interciter (+https://github.com/treysaddler/InterCiter)",
            "x-api-key": settings.s2_api_key or "",
            "Accept": "application/json",
        },
    )
    max_bytes = 8 * 1024 * 1024  # metadata payloads are small (link lists)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        raise S2DatasetsError(f"HTTP {exc.code} for {url}: {exc.reason}") from exc
    except Exception as exc:  # noqa: BLE001
        raise S2DatasetsError(f"request failed: {exc}") from exc
    if len(raw) > max_bytes:
        raise S2DatasetsError("datasets metadata response unexpectedly large")
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise S2DatasetsError(f"invalid JSON from {url}: {exc}") from exc


def list_releases(settings: Settings | None = None) -> list[str]:
    """Date-stamped release ids, oldest first."""
    settings = settings or get_settings()
    return _get_json(f"{settings.s2_datasets_base}/release", settings)


def get_release(release_id: str = "latest", settings: Settings | None = None) -> dict:
    """Release metadata, including the list of available datasets."""
    settings = settings or get_settings()
    return _get_json(f"{settings.s2_datasets_base}/release/{release_id}", settings)


def latest_release(settings: Settings | None = None) -> dict:
    return get_release("latest", settings)


def dataset_files(
    dataset_name: str, release_id: str = "latest", settings: Settings | None = None
) -> dict:
    """Download links for one dataset in a release (``{name, description, files:[…]}``).

    The ``files`` are pre-signed S3 URLs and expire — download promptly.
    """
    settings = settings or get_settings()
    url = f"{settings.s2_datasets_base}/release/{release_id}/dataset/{dataset_name}"
    return _get_json(url, settings)


def get_diffs(
    dataset_name: str,
    start_release_id: str,
    end_release_id: str = "latest",
    settings: Settings | None = None,
) -> dict:
    """Incremental update/delete file links to catch a dataset up between releases."""
    settings = settings or get_settings()
    url = (
        f"{settings.s2_datasets_base}/diffs/"
        f"{start_release_id}/to/{end_release_id}/{dataset_name}"
    )
    return _get_json(url, settings)


def download_shard(url: str, dest: Path) -> tuple[int, str]:
    """Stream a pre-signed shard URL to ``dest``; return ``(bytes, sha256_hex)``.

    Bulk shards can be gigabytes, so this streams to disk and does **not** apply the
    per-response size cap used for metadata/JSON. The URL is signed, so no API-key
    header is sent.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    hasher = hashlib.sha256()
    total = 0
    request = urllib.request.Request(
        url, headers={"User-Agent": "interciter (+https://github.com/treysaddler/InterCiter)"}
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response, tmp.open("wb") as fh:
            while True:
                chunk = response.read(_DOWNLOAD_CHUNK)
                if not chunk:
                    break
                fh.write(chunk)
                hasher.update(chunk)
                total += len(chunk)
    except Exception as exc:  # noqa: BLE001
        tmp.unlink(missing_ok=True)
        raise S2DatasetsError(f"shard download failed: {exc}") from exc
    tmp.replace(dest)
    return total, hasher.hexdigest()


def shard_basename(url: str) -> str:
    """Stable on-disk filename for a shard, derived from its (unsigned) path."""
    path = urllib.parse.urlparse(url).path
    name = Path(path).name or hashlib.sha256(url.encode()).hexdigest()[:16]
    return name
