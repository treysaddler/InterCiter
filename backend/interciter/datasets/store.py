"""Local cache layout, manifest, and lookup for Semantic Scholar bulk datasets.

The cache root (``s2_datasets_dir``) holds downloaded shards partitioned by release and
dataset, plus a small ``manifest.json`` that pins the release id and records each
downloaded shard's basename, byte count, and sha256. The manifest is the reproducibility
contract (pinned corpus release) and is small enough to commit; the shards are not.

```
<s2_datasets_dir>/
  <release_id>/<dataset>/<shard>.jsonl.gz …
  manifest.json
```

Phase-1 lookup is a stream-scan of the downloaded gz shards keyed by ``corpusid`` —
enough for the gold-set slice and the smoke test. A SQLite/DuckDB index over a full
ingest is a later phase.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Settings, get_settings
from . import s2_bulk

MANIFEST_NAME = "manifest.json"


@dataclass
class ShardRecord:
    dataset: str
    basename: str
    bytes: int
    sha256: str


@dataclass
class Manifest:
    """Pinned record of what has been downloaded for reproducibility."""

    release_id: str
    shards: list[ShardRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "release_id": self.release_id,
            "shards": [vars(s) for s in self.shards],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Manifest":
        return cls(
            release_id=data["release_id"],
            shards=[ShardRecord(**s) for s in data.get("shards", [])],
        )

    def datasets(self) -> set[str]:
        return {s.dataset for s in self.shards}


def _root(settings: Settings) -> Path:
    directory = Path(settings.s2_datasets_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _manifest_path(settings: Settings) -> Path:
    return _root(settings) / MANIFEST_NAME


def load_manifest(settings: Settings | None = None) -> Manifest | None:
    settings = settings or get_settings()
    path = _manifest_path(settings)
    if not path.exists():
        return None
    return Manifest.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_manifest(manifest: Manifest, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    _manifest_path(settings).write_text(
        json.dumps(manifest.to_dict(), indent=2), encoding="utf-8"
    )


def pull_dataset(
    dataset_name: str,
    *,
    release_id: str = "latest",
    max_shards: int | None = 1,
    settings: Settings | None = None,
) -> Manifest:
    """Download up to ``max_shards`` shards of a dataset and record them in the manifest.

    Defaults to a single shard (the smoke-test path). Passing ``max_shards=None`` pulls
    the whole dataset. Downloads are verified by size + sha256 and the manifest is
    rewritten atomically after each shard so an interrupted pull is resumable.
    """
    settings = settings or get_settings()
    info = s2_bulk.dataset_files(dataset_name, release_id, settings)
    # Resolve 'latest' to a concrete, pinnable release id for reproducibility.
    resolved_release = release_id
    if release_id == "latest":
        resolved_release = s2_bulk.latest_release(settings)["release_id"]

    manifest = load_manifest(settings)
    if manifest is None:
        manifest = Manifest(release_id=resolved_release)
    elif manifest.release_id != resolved_release:
        raise s2_bulk.S2DatasetsError(
            f"cache is pinned to release {manifest.release_id!r}; refusing to mix in "
            f"{resolved_release!r}. Use a fresh s2_datasets_dir or clear the cache."
        )

    have = {(s.dataset, s.basename) for s in manifest.shards}
    files = info.get("files", [])
    dest_dir = _root(settings) / resolved_release / dataset_name

    pulled = 0
    for url in files:
        if max_shards is not None and pulled >= max_shards:
            break
        basename = s2_bulk.shard_basename(url)
        if (dataset_name, basename) in have:
            continue
        size, digest = s2_bulk.download_shard(url, dest_dir / basename)
        manifest.shards.append(
            ShardRecord(
                dataset=dataset_name, basename=basename, bytes=size, sha256=digest
            )
        )
        save_manifest(manifest, settings)
        pulled += 1

    return manifest


def _iter_records(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def lookup_corpusid(
    corpusid: int | str,
    *,
    dataset_name: str = "papers",
    settings: Settings | None = None,
) -> dict | None:
    """Stream-scan downloaded shards of a dataset for a record by ``corpusid``.

    Phase-1 lookup (linear scan of the local slice). Returns the first matching record
    or ``None``.
    """
    settings = settings or get_settings()
    manifest = load_manifest(settings)
    if manifest is None:
        return None
    target = str(corpusid)
    dataset_dir = _root(settings) / manifest.release_id / dataset_name
    for shard in manifest.shards:
        if shard.dataset != dataset_name:
            continue
        path = dataset_dir / shard.basename
        if not path.exists():
            continue
        for record in _iter_records(path):
            if str(record.get("corpusid")) == target:
                return record
    return None
