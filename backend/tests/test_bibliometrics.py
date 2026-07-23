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


def _work(session, work_id, *, title=None, venue=None, year=None, authors=None, affiliations=None):
    work = models.PaperWork(
        work_id=work_id,
        title=title,
        venue=venue,
        year=year,
        authors=authors or [],
        author_affiliations=affiliations or [],
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


def _cite_n(session, cited, n):
    """Give ``cited`` exactly ``n`` citations from distinct stub citing works."""
    for i in range(n):
        citing = f"citing_{cited}_{i}"
        _work(session, citing)
        _edge(session, citing, cited)


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


# --- WP-B2: author / source / country metrics ---


def test_author_metrics_productivity_and_lotka(session):
    _seed_corpus(session)
    result = bibliometrics.author_metrics(session)

    by_name = {a.name: a for a in result.authors}
    ada = by_name["Ada Lovelace"]
    assert ada.document_count == 3  # w1, w2, w3
    assert ada.total_citations == 4  # w1(3) + w2(1) + w3(0)
    assert ada.h_index == 1  # citations [3,1,0] → h=1
    assert result.author_count == 3
    # Lotka distribution: Ada wrote 3 docs; Alan + Grace wrote 2 each.
    dist = {p.documents_written: p.author_count for p in result.lotka.points}
    assert dist == {2: 2, 3: 1}
    assert result.lotka.coefficient is not None


def test_author_h_index(session):
    for wid in ("p1", "p2", "p3"):
        _work(session, wid, venue="J", authors=["Prolific Author"])
    _cite_n(session, "p1", 3)
    _cite_n(session, "p2", 2)
    _cite_n(session, "p3", 1)
    session.commit()

    result = bibliometrics.author_metrics(session, work_ids=["p1", "p2", "p3"])
    author = next(a for a in result.authors if a.name == "Prolific Author")
    assert author.document_count == 3
    assert author.total_citations == 6
    # citations [3,2,1] → h=2 (two papers with ≥2 citations).
    assert author.h_index == 2


def test_source_metrics_impact_and_bradford(session):
    _seed_corpus(session)
    result = bibliometrics.source_metrics(session)

    by_source = {s.source: s for s in result.sources}
    assert by_source["Journal A"].document_count == 2
    assert by_source["Journal A"].total_citations == 4  # w1(3) + w2(1)
    assert by_source["Journal A"].h_index == 1
    assert result.source_count == 2
    # Zones partition every source + article.
    assert sum(z.source_count for z in result.bradford_zones) == 2
    assert sum(z.article_count for z in result.bradford_zones) == 4


def test_bradford_zone_partition(session):
    # 9 articles across 5 sources: S1=3, S2=2, S3=2, S4=1, S5=1 → thirds of 3 each.
    for i in range(3):
        _work(session, f"s1_{i}", venue="S1", authors=["x"])
    for i in range(2):
        _work(session, f"s2_{i}", venue="S2", authors=["x"])
    for i in range(2):
        _work(session, f"s3_{i}", venue="S3", authors=["x"])
    _work(session, "s4_0", venue="S4", authors=["x"])
    _work(session, "s5_0", venue="S5", authors=["x"])
    session.commit()

    result = bibliometrics.source_metrics(session, top_k=50)
    zones = {z.zone: z for z in result.bradford_zones}
    assert zones[1].article_count == 3  # the prolific core (S1)
    assert sum(z.article_count for z in result.bradford_zones) == 9
    assert sum(z.source_count for z in result.bradford_zones) == 5
    core = next(s for s in result.sources if s.source == "S1")
    assert core.bradford_zone == 1


def test_country_metrics_scp_mcp(session):
    _work(
        session,
        "c1",
        venue="J",
        authors=["A"],
        affiliations=["Dept, Univ X, United States"],
    )
    _work(
        session,
        "c2",
        venue="J",
        authors=["A", "B"],
        affiliations=["Univ X, USA", "Univ Y, United Kingdom"],
    )
    _work(session, "c3", venue="J", authors=["C"], affiliations=["Univ Z, Germany"])
    session.commit()

    result = bibliometrics.country_metrics(session)
    by = {c.country: c for c in result.countries}
    # US appears solo in c1 (SCP) and collaboratively in c2 (MCP).
    assert by["United States"].document_count == 2
    assert by["United States"].single_country_pubs == 1
    assert by["United States"].multi_country_pubs == 1
    # UK only collaborates (c2).
    assert by["United Kingdom"].single_country_pubs == 0
    assert by["United Kingdom"].multi_country_pubs == 1
    assert by["Germany"].single_country_pubs == 1
    assert result.country_count == 3
    assert result.documents_with_country == 3
    # One of three documents is multi-country.
    assert result.international_co_authorship_pct == round(1 / 3 * 100, 2)


def test_country_metrics_empty_without_affiliations(session):
    _seed_corpus(session)
    result = bibliometrics.country_metrics(session)
    assert result.documents_with_country == 0
    assert result.countries == []
    assert result.international_co_authorship_pct is None


def test_metric_endpoints_read_open(session, client):
    _seed_corpus(session)
    authors = client.get("/v1/bibliometrics/authors")
    assert authors.status_code == 200
    assert authors.json()["author_count"] == 3

    sources = client.get("/v1/bibliometrics/sources")
    assert sources.status_code == 200
    assert sources.json()["source_count"] == 2

    countries = client.get("/v1/bibliometrics/countries")
    assert countries.status_code == 200
    assert countries.json()["documents_with_country"] == 0


# --- UX-3: cohort by reference (analyze a saved collection / map) ---


def _submit(client, headers, sample: str) -> str:
    resp = client.post("/v1/papers", json={"xml": load_sample(sample)}, headers=headers)
    assert resp.status_code == 202, resp.text
    return resp.json()["result"]["work_id"]


def test_cohort_by_collection_and_map(client, user_headers):
    a = _submit(client, user_headers, "paper_a.xml")
    b = _submit(client, user_headers, "paper_b.xml")

    coll_id = client.post(
        "/v1/collections", json={"name": "cohort"}, headers=user_headers
    ).json()["collection_id"]
    added = client.post(
        f"/v1/collections/{coll_id}/members",
        json={"work_ids": [a, b]},
        headers=user_headers,
    )
    assert added.status_code == 200

    # The collection's two members define the analysis cohort, by reference.
    summary = client.get(
        f"/v1/bibliometrics/summary?collection={coll_id}", headers=user_headers
    )
    assert summary.status_code == 200
    assert summary.json()["document_count"] == 2

    # A saved map's seed set works the same way.
    map_id = client.post(
        "/v1/maps", json={"name": "cohort", "work_ids": [a, b]}, headers=user_headers
    ).json()["map_id"]
    map_summary = client.get(
        f"/v1/bibliometrics/summary?map={map_id}", headers=user_headers
    )
    assert map_summary.status_code == 200
    assert map_summary.json()["document_count"] == 2


def test_cohort_requires_auth_and_ownership(client, user_headers, make_user):
    from interciter.enums import Role

    a = _submit(client, user_headers, "paper_a.xml")
    coll_id = client.post(
        "/v1/collections", json={"name": "private"}, headers=user_headers
    ).json()["collection_id"]
    client.post(
        f"/v1/collections/{coll_id}/members",
        json={"work_ids": [a]},
        headers=user_headers,
    )

    # Anonymous callers cannot analyze a private collection.
    assert (
        client.get(f"/v1/bibliometrics/summary?collection={coll_id}").status_code == 401
    )

    # Another user gets 404 — a collection id must not leak across accounts.
    _, other = make_user(Role.user, "user2")
    assert (
        client.get(
            f"/v1/bibliometrics/summary?collection={coll_id}", headers=other
        ).status_code
        == 404
    )

    # An unknown id is likewise a 404.
    assert (
        client.get(
            "/v1/bibliometrics/summary?collection=coll_missing", headers=user_headers
        ).status_code
        == 404
    )
