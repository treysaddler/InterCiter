"""Full-text claim search service + /v1/search/claims endpoint tests (WP2, F3).

The sample corpus (paper A cites paper B) yields claims about *metformin reducing
fasting glucose in prediabetes*, across the Results and Discussion sections, so the
keyword and facet behaviour can be exercised end to end offline.
"""

from __future__ import annotations

from interciter.ingestion.pipeline import ingest_paper
from interciter.services import search

from helpers import load_sample


def _ingest_both(session):
    b = ingest_paper(session, xml=load_sample("paper_b.xml"))
    a = ingest_paper(session, xml=load_sample("paper_a.xml"))
    session.commit()
    return b, a


def test_keyword_matches_claim_text(session):
    _ingest_both(session)
    results = search.search_claims(session, q="metformin")
    assert results.total >= 1
    assert all("metformin" in h.normalized_text.lower() for h in results.hits)
    # Every hit carries provenance (a source passage span).
    assert all(h.evidence.verbatim_text for h in results.hits)


def test_keyword_is_case_insensitive_and_hits_passage_text(session):
    _ingest_both(session)
    lower = search.search_claims(session, q="fasting glucose")
    upper = search.search_claims(session, q="FASTING GLUCOSE")
    assert lower.total >= 1
    assert lower.total == upper.total


def test_empty_query_returns_all_head_claims(session):
    _ingest_both(session)
    results = search.search_claims(session, q="")
    assert results.total >= 1
    # Results are head interpretations only — no duplicate claim ids.
    ids = [h.claim_id for h in results.hits]
    assert len(ids) == len(set(ids))


def test_section_facet_and_filter(session):
    _ingest_both(session)
    unfiltered = search.search_claims(session, q="metformin")
    assert "Results" in unfiltered.facets.section

    filtered = search.search_claims(session, q="metformin", section="Results")
    assert filtered.total >= 1
    assert all((h.section or "") == "Results" for h in filtered.hits)
    assert filtered.total <= unfiltered.total


def test_stance_and_function_facets(session):
    _ingest_both(session)
    results = search.search_claims(session, q="metformin")
    # A→B resolves as a supporting, direct-evidence claim link, so those facets exist.
    assert results.facets.stance.get("support", 0) >= 1
    assert results.facets.function.get("direct_evidence", 0) >= 1

    supporting = search.search_claims(session, q="metformin", stance="support")
    assert supporting.total >= 1
    assert all("support" in h.stance for h in supporting.hits)


def test_no_match_returns_empty(session):
    _ingest_both(session)
    results = search.search_claims(session, q="rutherfordium")
    assert results.total == 0
    assert results.hits == []


def test_pagination(session):
    _ingest_both(session)
    everything = search.search_claims(session, q="")
    assert everything.total >= 2

    first = search.search_claims(session, q="", limit=1, offset=0)
    second = search.search_claims(session, q="", limit=1, offset=1)
    assert len(first.hits) == 1
    assert len(second.hits) == 1
    assert first.hits[0].claim_id != second.hits[0].claim_id
    assert first.total == everything.total


def test_api_search_endpoint(session, client):
    _ingest_both(session)
    resp = client.get("/v1/search/claims", params={"q": "metformin"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == "metformin"
    assert body["total"] >= 1
    assert body["hits"][0]["evidence"]["verbatim_text"]
    assert "section" in body["facets"]


def test_api_search_open_to_anonymous(session, client):
    _ingest_both(session)
    # Reads stay open — no auth required.
    assert client.get("/v1/search/claims", params={"q": ""}).status_code == 200
