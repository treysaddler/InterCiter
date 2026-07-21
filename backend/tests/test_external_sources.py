"""Tests for the external-source clients (Semantic Scholar, ROBOKOP, bulk datasets).

Unit tests run offline (pure logic + monkeypatched transport). Live tests hit the real
services and are gated behind ``INTERCITER_NET_TESTS=1``; the datasets live test is
additionally gated on an API key being present.
"""

from __future__ import annotations

import gzip
import json
import os

import pytest

from interciter.config import Settings
from interciter.datasets import s2_bulk, store
from interciter.ingestion import robokop, semantic_scholar

_NET = os.environ.get("INTERCITER_NET_TESTS") == "1"
_netonly = pytest.mark.skipif(not _NET, reason="network test; set INTERCITER_NET_TESTS=1")
_HAS_KEY = bool(os.environ.get("INTERCITER_S2_API_KEY"))


# --- Semantic Scholar id normalization ------------------------------------------

def test_normalize_paper_id_prefixes():
    assert semantic_scholar.normalize_paper_id("DOI:10.1/x") == "DOI:10.1/x"
    assert semantic_scholar.normalize_paper_id("pmid:123") == "PMID:123"
    assert semantic_scholar.normalize_paper_id("corpusid:42") == "CorpusId:42"
    # Raw 40-char paperId passes through.
    raw = "a" * 40
    assert semantic_scholar.normalize_paper_id(raw) == raw


def test_normalize_paper_id_rejects_bad():
    with pytest.raises(semantic_scholar.S2Error):
        semantic_scholar.normalize_paper_id("")
    with pytest.raises(semantic_scholar.S2Error):
        semantic_scholar.normalize_paper_id("BOGUS:1")
    with pytest.raises(semantic_scholar.S2Error):
        semantic_scholar.normalize_paper_id("DOI:")


def test_get_embedding_returns_none_without_vector(monkeypatch):
    monkeypatch.setattr(semantic_scholar, "get_paper", lambda *a, **k: {"paperId": "x"})
    assert semantic_scholar.get_embedding("CorpusId:1", use_cache=False) is None


# --- ROBOKOP TRAPI one-hop construction + flattening ----------------------------

def test_one_hop_query_graph_shape():
    q = robokop._one_hop_query_graph("CHEBI:6801", "MONDO:0005148", "biolink:treats")
    qg = q["message"]["query_graph"]
    assert qg["nodes"]["n0"]["ids"] == ["CHEBI:6801"]
    assert qg["nodes"]["n1"]["ids"] == ["MONDO:0005148"]
    assert qg["edges"]["e0"]["predicates"] == ["biolink:treats"]


def test_one_hop_query_graph_without_predicate():
    q = robokop._one_hop_query_graph("CHEBI:6801", "MONDO:0005148", None)
    assert "predicates" not in q["message"]["query_graph"]["edges"]["e0"]


def test_query_edges_flattens_knowledge_graph(monkeypatch, tmp_path):
    settings = Settings(robokop_cache_dir=str(tmp_path))
    payload = {
        "message": {
            "knowledge_graph": {
                "edges": {
                    "x": {
                        "subject": "CHEBI:6801",
                        "predicate": "biolink:treats",
                        "object": "MONDO:0005148",
                        "sources": [{"resource_id": "infores:robokop"}],
                    }
                }
            }
        }
    }
    monkeypatch.setattr(robokop, "_request", lambda *a, **k: payload)
    edges = robokop.query_edges(
        "CHEBI:6801", "MONDO:0005148", settings=settings, use_cache=False
    )
    assert edges == [
        {
            "subject": "CHEBI:6801",
            "predicate": "biolink:treats",
            "object": "MONDO:0005148",
            "sources": [{"resource_id": "infores:robokop"}],
        }
    ]


def test_ground_curie_skips_name_resolver(monkeypatch, tmp_path):
    settings = Settings(robokop_cache_dir=str(tmp_path))
    called = {"name": False}

    def _fail_name(*a, **k):
        called["name"] = True
        raise AssertionError("name resolver should not be called for a CURIE")

    monkeypatch.setattr(robokop, "lookup_name", _fail_name)
    monkeypatch.setattr(
        robokop, "normalize_nodes", lambda curies, **k: {curies[0]: {"id": {"identifier": curies[0]}}}
    )
    node = robokop.ground("CHEBI:6801", settings=settings, use_cache=False)
    assert node == {"id": {"identifier": "CHEBI:6801"}}
    assert called["name"] is False


# --- Bulk datasets: pure helpers + manifest round-trip --------------------------

def test_shard_basename_from_signed_url():
    url = "https://ai2-s2ag.s3.amazonaws.com/staging/2024-01-09/papers/part-00.jsonl.gz?sig=abc"
    assert s2_bulk.shard_basename(url) == "part-00.jsonl.gz"


def test_datasets_api_requires_key():
    settings = Settings(s2_api_key=None)
    with pytest.raises(s2_bulk.S2DatasetsError):
        s2_bulk.list_releases(settings)


def test_manifest_round_trip(tmp_path):
    settings = Settings(s2_datasets_dir=str(tmp_path))
    manifest = store.Manifest(release_id="2024-01-09")
    manifest.shards.append(
        store.ShardRecord(dataset="papers", basename="p0.jsonl.gz", bytes=10, sha256="ff")
    )
    store.save_manifest(manifest, settings)
    loaded = store.load_manifest(settings)
    assert loaded is not None
    assert loaded.release_id == "2024-01-09"
    assert loaded.datasets() == {"papers"}


def test_lookup_corpusid_scans_local_shard(tmp_path):
    settings = Settings(s2_datasets_dir=str(tmp_path))
    release = "2024-01-09"
    shard_dir = tmp_path / release / "papers"
    shard_dir.mkdir(parents=True)
    shard = shard_dir / "p0.jsonl.gz"
    with gzip.open(shard, "wt", encoding="utf-8") as fh:
        fh.write(json.dumps({"corpusid": 42, "title": "A"}) + "\n")
        fh.write(json.dumps({"corpusid": 99, "title": "B"}) + "\n")
    manifest = store.Manifest(release_id=release)
    manifest.shards.append(
        store.ShardRecord(dataset="papers", basename="p0.jsonl.gz", bytes=1, sha256="x")
    )
    store.save_manifest(manifest, settings)

    assert store.lookup_corpusid(99, settings=settings)["title"] == "B"
    assert store.lookup_corpusid(123, settings=settings) is None


# --- Live (network-gated) -------------------------------------------------------

@_netonly
def test_live_s2_identifier_mapping():
    paper = semantic_scholar.get_paper("PMID:33301246", ("externalIds", "title"))
    assert "externalIds" in paper


@_netonly
def test_live_robokop_ground_metformin():
    node = robokop.ground("metformin")
    assert node is not None
    assert "id" in node


@pytest.mark.skipif(
    not (_NET and _HAS_KEY),
    reason="datasets live test; set INTERCITER_NET_TESTS=1 and INTERCITER_S2_API_KEY",
)
def test_live_datasets_pull_one_shard(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERCITER_S2_DATASETS_DIR", str(tmp_path))
    settings = Settings(s2_datasets_dir=str(tmp_path))
    manifest = store.pull_dataset("papers", max_shards=1, settings=settings)
    assert manifest.shards
    assert manifest.release_id
