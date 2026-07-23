"""Corpus bibliometrics service + /v1 endpoint tests (bibliometrix-parity WP-B1).

A synthetic cohort (explicit works + citation edges) exercises the descriptive math —
counts, co-authors/doc, annual production + growth rate, average citations/doc, and the
top-k rankings — and the ingested sample corpus confirms it rolls up over real records.
"""

from __future__ import annotations

from interciter import models
from interciter.enums import AvailabilityState
from interciter.ingestion.pipeline import ingest_paper
from interciter.services import bibliometrics

from helpers import load_sample


def _work(session, work_id, *, title=None, venue=None, year=None, authors=None):
    work = models.PaperWork(
        work_id=work_id,
        title=title,
        venue=venue,
        year=year,
        authors=authors or [],
        availability_state=AvailabilityState.metadata_stub,
    )
    session.add(work)
    return work


def _edge(session, citing, cited):
    session.add(
        models.CitationEdge(
            edge_id=f"edge_{citing}_{cited}",
            citing_work_id=citing,
            cited_work_id=cited,
            source="semantic_scholar",
        )
    )


def _seed_corpus(session):
    # w1 (2019) cited by w2, w3, w4; w2 (2020) cited by w3; w4 (2022) uncited.
    _work(session, "w1", title="Alpha", venue="Journal A", year=2019, authors=["Ada Lovelace"])
    _work(
        session,
        "w2",
        title="Beta",
        venue="Journal A",
        year=2020,
        authors=["Ada Lovelace", "Alan Turing"],
    )
    _work(
        session,
        "w3",
        title="Gamma",
        venue="Journal B",
        year=2021,
        authors=["Alan Turing", "Grace Hopper", "Ada Lovelace"],
    )
    _work(session, "w4", title="Delta", venue="Journal B", year=2022, authors=["Grace Hopper"])
    for citing, cited in [("w2", "w1"), ("w3", "w1"), ("w4", "w1"), ("w3", "w2")]:
        _edge(session, citing, cited)
    session.commit()


def test_summary_counts_and_co_authors(session):
    _seed_corpus(session)
    summary = bibliometrics.corpus_summary(session)

    assert summary.document_count == 4
    assert summary.source_count == 2  # Journal A + Journal B
    # Distinct authors: Ada, Alan, Grace.
    assert summary.author_count == 3
    assert summary.author_appearances == 1 + 2 + 3 + 1  # 7
    assert summary.co_authors_per_doc == round(7 / 4, 2)
    assert summary.single_authored_count == 2  # w1 and w4


def test_annual_production_and_growth_rate(session):
    _seed_corpus(session)
    summary = bibliometrics.corpus_summary(session)

    assert summary.min_year == 2019
    assert summary.max_year == 2022
    assert summary.documents_without_year == 0
    # Dense series over the whole span, one doc per year.
    assert [(p.year, p.document_count) for p in summary.annual_production] == [
        (2019, 1),
        (2020, 1),
        (2021, 1),
        (2022, 1),
    ]
    # first=last=1 over a 3-year span → 0% CAGR.
    assert summary.annual_growth_rate == 0.0


def test_citation_rollup_and_top_cited(session):
    _seed_corpus(session)
    summary = bibliometrics.corpus_summary(session)

    # w1 cited by 3 distinct works, w2 by 1, others 0 → total 4.
    assert summary.total_citations == 4
    assert summary.avg_citations_per_doc == round(4 / 4, 2)
    top = summary.top_cited_documents
    assert [d.work_id for d in top] == ["w1", "w2"]
    assert top[0].citation_count == 3
    assert top[1].citation_count == 1


def test_top_authors_and_sources_ordering(session):
    _seed_corpus(session)
    summary = bibliometrics.corpus_summary(session)

    # Ada appears in w1/w2/w3 (3), Alan w2/w3 (2), Grace w3/w4 (2).
    top_author = summary.top_authors[0]
    assert top_author.name == "Ada Lovelace"
    assert top_author.document_count == 3
    # Both journals publish two documents each.
    assert {s.source: s.document_count for s in summary.top_sources} == {
        "Journal A": 2,
        "Journal B": 2,
    }


def test_cohort_and_year_filters(session):
    _seed_corpus(session)

    cohort = bibliometrics.corpus_summary(session, work_ids=["w1", "w2"])
    assert cohort.document_count == 2
    # In-degree is global: w1 cited by w2/w3/w4 (3) + w2 cited by w3 (1) = 4,
    # even though w3/w4 are outside the cohort.
    assert cohort.total_citations == 4

    ranged = bibliometrics.corpus_summary(session, min_year=2020, max_year=2021)
    assert ranged.document_count == 2
    assert ranged.min_year == 2020
    assert ranged.max_year == 2021

    empty = bibliometrics.corpus_summary(session, work_ids=[])
    assert empty.document_count == 0
    assert empty.avg_citations_per_doc == 0.0


def test_growth_rate_reflects_production_change(session):
    _work(session, "g1", venue="J", year=2018, authors=["A"])
    _work(session, "g2", venue="J", year=2020, authors=["A"])
    _work(session, "g3", venue="J", year=2020, authors=["A"])
    _work(session, "g4", venue="J", year=2020, authors=["A"])
    _work(session, "g5", venue="J", year=2020, authors=["A"])
    session.commit()
    summary = bibliometrics.corpus_summary(session)
    # first=1 (2018), last=4 (2020), span=2 → (4/1)^(1/2)-1 = 100%.
    assert summary.annual_growth_rate == 100.0


def test_summary_over_sample_corpus(session):
    ingest_paper(session, xml=load_sample("paper_b.xml"))
    ingest_paper(session, xml=load_sample("paper_a.xml"))
    session.commit()

    summary = bibliometrics.corpus_summary(session)
    assert summary.document_count >= 2
    # paper_a cites paper_b, so at least one document accrues a citation.
    assert summary.total_citations >= 1
    assert summary.top_cited_documents


def test_summary_endpoint_reads_open(session, client):
    _seed_corpus(session)
    resp = client.get("/v1/bibliometrics/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["document_count"] == 4
    assert body["source_count"] == 2
    assert body["top_cited_documents"][0]["work_id"] == "w1"

    ranged = client.get("/v1/bibliometrics/summary", params={"min_year": 2021})
    assert ranged.status_code == 200
    assert ranged.json()["document_count"] == 2
