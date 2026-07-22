"""One-off: measure the on-disk (compressed) size of every S2 dataset in the
latest release by summing each shard's object size via a ranged GET. Throwaway."""

import concurrent.futures as cf
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from interciter.datasets import s2_bulk
from interciter.net import ssl_context

OUT = Path("_ds_sizes.json")


def size_of(url: str) -> int:
    last = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "interciter", "Range": "bytes=0-0"}
            )
            with urllib.request.urlopen(req, timeout=90, context=ssl_context()) as r:
                cr = r.headers.get("Content-Range")  # 'bytes 0-0/12345'
                if cr and "/" in cr:
                    return int(cr.rsplit("/", 1)[1])
                return int(r.headers.get("Content-Length", 0))
        except (urllib.error.URLError, ConnectionError) as exc:  # transient S3 reset
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"size_of failed: {last}")


def human(n: float) -> str:
    x = float(n)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if x < 1024:
            return f"{x:.1f} {unit}"
        x /= 1024
    return f"{x:.1f} PB"


def main() -> None:
    rel = s2_bulk.latest_release()
    release_id = rel["release_id"]
    names = [d["name"] for d in rel["datasets"]]
    descriptions = {d["name"]: d.get("description", "") for d in rel["datasets"]}

    cache = {}
    if OUT.exists():
        cache = json.loads(OUT.read_text())

    rows = cache.get("datasets", {})
    for name in names:
        if name in rows:
            print(f"[cached] {name}")
            continue
        files = s2_bulk.dataset_files(name).get("files", [])
        with cf.ThreadPoolExecutor(max_workers=4) as ex:
            sizes = list(ex.map(size_of, files))
        total = sum(sizes)
        rows[name] = {"shards": len(files), "bytes": total}
        print(f"{name:<24}{len(files):>7}{human(total):>13}")
        OUT.write_text(json.dumps({"release_id": release_id, "datasets": rows}, indent=2))

    grand = sum(v["bytes"] for v in rows.values())
    total_shards = sum(v["shards"] for v in rows.values())
    print("-" * 44)
    print(f"{'TOTAL':<24}{total_shards:>7}{human(grand):>13}")

    print("\nrelease", release_id)
    for name in names:
        v = rows[name]
        print(
            f"| {name} | {v['shards']} | {human(v['bytes'])} | "
            f"{human(v['bytes'] / v['shards'])} | {descriptions[name][:80]} |"
        )
    print("\nGRAND TOTAL bytes:", grand, "=", human(grand))
    OUT.write_text(
        json.dumps(
            {
                "release_id": release_id,
                "grand_total_bytes": grand,
                "total_shards": total_shards,
                "datasets": rows,
                "descriptions": descriptions,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
