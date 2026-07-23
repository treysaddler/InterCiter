"""Tests for the local bulk-dataset backfill (services/local_enrichment.py).

All offline: each test writes tiny gzipped JSONL "shards" plus a matching
manifest.json into a tmp ``s2_datasets_dir`` and streams them through the same
code path the CLI uses.
"""

from __future__ import annotations

import gzip
import json

import pytest

from sqlalchemy import select

from interciter import models
from interciter.config import Settings
from interciter.ids import new_id
from interciter.services import local_enrichment

RELEASE = "2026-07-14"


def _write_shard(root, dataset: str, basename: str, records: list[dict]) -> dict:
    shard_dir = root / RELEASE / dataset
    shard_dir.mkdir(parents=True, exist_ok=True)
    path = shard_dir / basename
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record) + "\n")
    return {
        "dataset": dataset,
        "basename": basename,
        "bytes": path.stat().st_size,
        "sha256": "0" * 64,
    }


def _make_store(tmp_path, shards_by_dataset: dict[str, list[dict]]) -> Settings:
    """Write mini-shards + manifest; return Settings pointing at the tmp store."""
    shard_entries = []
    for dataset, records in shards_by_dataset.items():
        shard_entries.append(_write_shard(tmp_path, dataset, f"{dataset}-000.gz", records))
    (tmp_path / "manifest.json").write_text(
        json.dumps({"release_id": RELEASE, "shards": shard_entries})
    )
    return Settings(s2_datasets_dir=str(tmp_path))


def _work(**kwargs) -> models.PaperWork:
    defaults = {"work_id": new_id("PaperWork")}
    defaults.update(kwargs)
    return models.PaperWork(**defaults)


# --- papers pass -----------------------------------------------------------------


def test_papers_pass_fills_only_nulls_and_matches_all_identifiers(session, tmp_path):
    by_corpus = _work(s2_corpus_id="111", title="Kept Title")
    by_doi = _work(doi="10.1000/ABC")  # matched case-insensitively
    by_pmid = _work(pmid="777")
    unmatched = _work(doi="10.1000/other")
    session.add_all([by_corpus, by_doi, by_pmid, unmatched])
    session.commit()

    settings = _make_store(
        tmp_path,
        {
            "papers": [
                {
                    "corpusid": 111,
                    "externalids": {"DOI": "10.9/x", "PubMed": None},
                    "title": "New Title",
                    "authors": [{"authorId": "1", "name": "A. Author"}],
                    "venue": "Venue A",
                    "year": 2020,
                },
                {
                    "corpusid": 222,
                    "externalids": {"DOI": "10.1000/abc", "PubMed": None},
                    "title": "Doi Matched",
                    "authors": [],
                    "venue": "",
                    "year": 2021,
                },
                {
                    "corpusid": 333,
                    "externalids": {"DOI": None, "PubMed": "777"},
                    "title": "Pmid Matched",
                    "authors": [],
                    "venue": "Venue C",
                    "year": None,
                },
            ]
        },
    )

    report = local_enrichment.backfill_papers(session, settings=settings)

    assert report.records_scanned == 3
    assert report.works_matched == 3
    # Additive only: existing title kept, gaps filled.
    assert by_corpus.title == "Kept Title"
    assert by_corpus.doi == "10.9/x"
    assert by_corpus.authors == ["A. Author"]
    assert by_corpus.venue == "Venue A"
    assert by_corpus.year == 2020
    # DOI match backfills the corpus id (identifier bridge).
    assert by_doi.s2_corpus_id == "222"
    assert by_doi.title == "Doi Matched"
    # Empty venue string is not written.
    assert by_doi.venue is None
    assert by_pmid.s2_corpus_id == "333"
    assert unmatched.title is None


def test_papers_pass_dry_run_writes_nothing(session, tmp_path):
    work = _work(s2_corpus_id="111")
    session.add(work)
    session.commit()
    settings = _make_store(
        tmp_path,
        {
            "papers": [
                {
                    "corpusid": 111,
                    "externalids": {},
                    "title": "Would Fill",
                    "authors": [],
                    "venue": None,
                    "year": 1999,
                }
            ]
        },
    )

    report = local_enrichment.backfill_papers(session, settings=settings, dry_run=True)
    session.rollback()

    assert report.dry_run is True
    assert report.works_matched == 1
    assert report.fields_filled.get("title") == 1
    assert work.title is None
    assert work.year is None


# --- tldrs / abstracts passes ------------------------------------------------------


def test_tldr_and_abstract_passes_fill_by_corpusid(session, tmp_path):
    enriched = _work(s2_corpus_id="42")
    already = _work(s2_corpus_id="43", tldr="existing", abstract="existing")
    session.add_all([enriched, already])
    session.commit()

    settings = _make_store(
        tmp_path,
        {
            "tldrs": [
                {"corpusid": 42, "model": "tldr@v2.0.0", "text": "A gist."},
                {"corpusid": 43, "model": "tldr@v2.0.0", "text": "Ignored."},
                {"corpusid": 99, "model": "tldr@v2.0.0", "text": "No such work."},
            ],
            "abstracts": [
                {"corpusid": 42, "abstract": "An abstract."},
                {"corpusid": 43, "abstract": "Ignored."},
            ],
        },
    )

    reports = local_enrichment.backfill(session, ["tldrs", "abstracts"], settings=settings)

    assert [r.dataset for r in reports] == ["tldrs", "abstracts"]
    assert enriched.tldr == "A gist."
    assert enriched.abstract == "An abstract."
    # Additive only.
    assert already.tldr == "existing"
    assert already.abstract == "existing"
    assert reports[0].fields_filled == {"tldr": 1}
    assert reports[1].fields_filled == {"abstract": 1}


# --- citations pass ---------------------------------------------------------------


def _citation(citing: int, cited: int, **extra) -> dict:
    record = {
        "citationid": citing * 1000 + cited,
        "citingcorpusid": citing,
        "citedcorpusid": cited,
        "isinfluential": False,
        "contexts": None,
        "intents": None,
    }
    record.update(extra)
    return record


def test_citations_pass_creates_edges_only_for_known_pairs(session, tmp_path):
    citing = _work(s2_corpus_id="1")
    cited = _work(s2_corpus_id="2")
    session.add_all([citing, cited])
    session.commit()

    settings = _make_store(
        tmp_path,
        {
            "citations": [
                _citation(1, 2, isinfluential=True, intents=["methodology"], contexts=["ctx"]),
                _citation(1, 999),  # cited work unknown
                _citation(999, 2),  # citing work unknown
                _citation(1, 1),  # degenerate self-loop guard
            ]
        },
    )

    report = local_enrichment.backfill_citations(session, settings=settings)

    edges = session.scalars(select(models.CitationEdge)).all()
    assert report.records_scanned == 4
    assert report.edges_created == 1
    assert len(edges) == 1
    edge = edges[0]
    assert edge.citing_work_id == citing.work_id
    assert edge.cited_work_id == cited.work_id
    assert edge.source == "semantic_scholar"
    assert edge.is_influential is True
    assert edge.edge_metadata["s2_intents"] == ["methodology"]
    assert edge.edge_metadata["contexts"] == ["ctx"]


def test_citations_pass_is_idempotent_and_respects_snowball_edges(session, tmp_path):
    citing = _work(s2_corpus_id="1")
    cited = _work(s2_corpus_id="2")
    other = _work(s2_corpus_id="3")
    session.add_all([citing, cited, other])
    # Pre-existing snowball edge for the same pair (same provider source).
    session.add(
        models.CitationEdge(
            edge_id=new_id("CitationEdge"),
            citing_work_id=citing.work_id,
            cited_work_id=cited.work_id,
            source="semantic_scholar",
        )
    )
    session.commit()

    settings = _make_store(
        tmp_path,
        {"citations": [_citation(1, 2), _citation(1, 3)]},
    )

    first = local_enrichment.backfill_citations(session, settings=settings)
    second = local_enrichment.backfill_citations(session, settings=settings)

    assert first.edges_created == 1  # only the (1, 3) pair is new
    assert first.edges_existing == 1
    assert second.edges_created == 0
    assert second.edges_existing == 2
    assert len(session.scalars(select(models.CitationEdge)).all()) == 2


def test_citations_dry_run_creates_nothing(session, tmp_path):
    citing = _work(s2_corpus_id="1")
    cited = _work(s2_corpus_id="2")
    session.add_all([citing, cited])
    session.commit()
    settings = _make_store(tmp_path, {"citations": [_citation(1, 2)]})

    report = local_enrichment.backfill_citations(session, settings=settings, dry_run=True)

    assert report.edges_created == 1  # reported, not written
    assert session.scalars(select(models.CitationEdge)).all() == []


# --- dispatcher --------------------------------------------------------------------


def test_backfill_rejects_unknown_dataset(session):
    with pytest.raises(ValueError, match="unsupported dataset"):
        local_enrichment.backfill(session, ["papers", "embeddings-specter_v2"])
