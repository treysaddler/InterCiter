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
from interciter import models
from interciter.enums import AvailabilityState
from interciter.services import enrichment
from interciter.services import grounding
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


# --- Enrichment: non-destructive backfill onto PaperWork ------------------------

_FAKE_PAPER = {
    "externalIds": {"CorpusId": 42, "DOI": "10.1/x", "PubMed": "999"},
    "title": "A trial",
    "venue": "Journal",
    "year": 2020,
    "authors": [{"name": "Ada L."}, {"name": "Grace H."}],
    "tldr": {"text": "It works."},
}


def _mk_work(**kw) -> models.PaperWork:
    defaults = dict(work_id="w1", availability_state=AvailabilityState.metadata_stub)
    defaults.update(kw)
    return models.PaperWork(**defaults)


def test_s2_id_for_work_prefers_doi_then_pmid_then_corpus():
    assert enrichment.s2_id_for_work(_mk_work(doi="10.1/x")) == "DOI:10.1/x"
    assert enrichment.s2_id_for_work(_mk_work(pmid="7")) == "PMID:7"
    assert enrichment.s2_id_for_work(_mk_work(s2_corpus_id="42")) == "CorpusId:42"
    assert enrichment.s2_id_for_work(_mk_work()) is None


def test_enrich_work_skips_when_unidentifiable(session, tmp_path):
    settings = Settings(s2_cache_dir=str(tmp_path))
    work = _mk_work()
    session.add(work)
    session.flush()
    result = enrichment.enrich_work(session, work, settings=settings)
    assert result.skipped_reason
    assert result.fields_filled == []


def test_enrich_work_fills_only_gaps(session, tmp_path, monkeypatch):
    settings = Settings(s2_cache_dir=str(tmp_path))
    monkeypatch.setattr(enrichment.s2, "get_paper", lambda *a, **k: dict(_FAKE_PAPER))
    monkeypatch.setattr(enrichment.s2, "get_embedding", lambda *a, **k: [0.1, 0.2, 0.3])
    # Title already present -> preserved; corpusId/authors/year are gaps.
    work = _mk_work(doi="10.1/x", title="Existing title")
    session.add(work)
    session.flush()

    result = enrichment.enrich_work(session, work, settings=settings)

    assert work.s2_corpus_id == "42"
    assert work.title == "Existing title"  # not overwritten
    assert work.authors == ["Ada L.", "Grace H."]
    assert work.year == 2020
    assert "title" not in result.fields_filled
    assert "s2_corpus_id" in result.fields_filled
    assert result.embedding_dims == 3
    assert result.tldr == "It works."
    assert enrichment.load_embedding("42", settings=settings) == [0.1, 0.2, 0.3]


def test_reference_links_normalizes_intents(monkeypatch):
    raw = [
        {
            "citedPaper": {"externalIds": {"CorpusId": 7, "DOI": "10.2/y"}, "title": "Cited"},
            "contexts": ["…as shown by…"],
            "intents": ["background"],
            "isInfluential": True,
        }
    ]
    monkeypatch.setattr(enrichment.s2, "get_references", lambda *a, **k: raw)
    links = enrichment.reference_links("CorpusId:1", use_cache=False)
    assert links[0]["cited_corpus_id"] == "7"
    assert links[0]["intents"] == ["background"]
    assert links[0]["is_influential"] is True


# --- Grounding + corroboration (ROBOKOP, derived) -------------------------------

def test_candidate_terms_picks_non_null_entities():
    quals = {
        "intervention": "metformin",
        "comparator": None,
        "outcome": "HbA1c",
        "population": "  ",
        "effect_direction": "decrease",
    }
    assert grounding.candidate_terms(quals) == [
        ("intervention", "metformin"),
        ("outcome", "HbA1c"),
    ]
    assert grounding.candidate_terms(None) == []


def test_ground_terms_maps_node_records(monkeypatch):
    def _fake_ground(term, **k):
        if term == "metformin":
            return {
                "id": {"identifier": "CHEBI:6801", "label": "metformin"},
                "type": ["biolink:SmallMolecule"],
            }
        return None

    monkeypatch.setattr(grounding.robokop, "ground", _fake_ground)
    results = grounding.ground_terms(
        [("intervention", "metformin"), ("outcome", "nonsense-xyz")], use_cache=False
    )
    assert results[0].curie == "CHEBI:6801"
    assert results[0].types == ["biolink:SmallMolecule"]
    assert results[1].curie is None  # unresolved term retained, not dropped


def test_ground_interpretation_uses_qualifiers(session, monkeypatch):
    monkeypatch.setattr(
        grounding.robokop,
        "ground",
        lambda term, **k: {
            "id": {"identifier": "CHEBI:6801"},
            "type": ["biolink:SmallMolecule"],
        },
    )
    interp = models.ClaimInterpretation(
        interpretation_id="i1",
        claim_occurrence_id="o1",
        normalized_text="metformin lowers HbA1c",
        qualifiers={"intervention": "metformin"},
        parent_interpretation_ids=[],
    )
    session.add(interp)
    session.flush()
    result = grounding.ground_interpretation(session, interp)
    assert result.interpretation_id == "i1"
    assert result.resolved()[0].curie == "CHEBI:6801"


def test_knowledge_sources_splits_roles():
    edge = {
        "sources": [
            {"resource_id": "infores:ctd", "resource_role": "primary_knowledge_source"},
            {"resource_id": "infores:robokop", "resource_role": "aggregator_knowledge_source"},
            {"resource_id": "infores:automat", "resource_role": "aggregator_knowledge_source"},
        ]
    }
    ks = grounding.knowledge_sources(edge)
    assert ks["primary_knowledge_source"] == "infores:ctd"
    assert ks["aggregator_knowledge_source"] == ["infores:robokop", "infores:automat"]


def test_corroborate_attaches_provenance(monkeypatch):
    monkeypatch.setattr(
        grounding.robokop,
        "query_edges",
        lambda *a, **k: [
            {
                "subject": "CHEBI:6801",
                "predicate": "biolink:treats",
                "object": "MONDO:0005148",
                "sources": [
                    {"resource_id": "infores:ctd", "resource_role": "primary_knowledge_source"}
                ],
            }
        ],
    )
    records = grounding.corroborate("CHEBI:6801", "MONDO:0005148", use_cache=False)
    assert records[0]["predicate"] == "biolink:treats"
    assert records[0]["primary_knowledge_source"] == "infores:ctd"
    assert records[0]["aggregator_knowledge_source"] == []


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
