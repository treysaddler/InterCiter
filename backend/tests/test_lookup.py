"""On-demand Semantic Scholar lookup / read-through cache tests.

Semantic Scholar is never hit: ``get_paper`` / ``get_references`` are monkeypatched so
the tests are deterministic and offline. They assert that a cache miss fetches and
persists the paper (metadata + abstract + references as edges), that a second lookup is
served from the DB without a network call, that a partially-populated work is enriched
in place, and that the API endpoint requires auth and round-trips the cached paper.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from interciter import models
from interciter.enums import AvailabilityState
from interciter.ingestion import semantic_scholar as s2
from interciter.services import lookup


def _paper(corpus: int, *, abstract: str | None = "An abstract.") -> dict:
    return {
        "externalIds": {"CorpusId": corpus, "DOI": f"10.1/{corpus}"},
        "title": f"Paper {corpus}",
        "year": 2021,
        "venue": "Journal of Testing",
        "authors": [{"name": "Ada Root"}],
        "abstract": abstract,
        "tldr": {"text": f"TLDR {corpus}"},
    }


def _ref(n: int) -> dict:
    return {
        "isInfluential": False,
        "intents": ["background"],
        "citedPaper": {
            "externalIds": {"CorpusId": n, "DOI": f"10.1/{n}"},
            "title": f"Cited {n}",
            "year": 2019,
            "authors": [{"name": f"Author {n}"}],
        },
    }


@pytest.fixture
def fake_s2(monkeypatch):
    calls = {"get_paper": 0, "get_references": 0}
    papers = {"DOI:10.1/1": _paper(1), "CorpusId:1": _paper(1)}
    refs = {"CorpusId:1": [_ref(2), _ref(3)]}

    def fake_get_paper(paper_id, fields=None, **kwargs):
        calls["get_paper"] += 1
        if paper_id not in papers:
            raise s2.S2Error(f"not found: {paper_id}")
        return papers[paper_id]

    def fake_get_references(paper_id, fields=None, *, max_records=None, **kwargs):
        calls["get_references"] += 1
        out = refs.get(paper_id, [])
        return out[:max_records] if max_records else out

    monkeypatch.setattr(s2, "get_paper", fake_get_paper)
    monkeypatch.setattr(s2, "get_references", fake_get_references)
    return calls


def _count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_fetch_persists_paper_and_references(session, fake_s2):
    result = lookup.fetch_and_cache_paper(session, "DOI:10.1/1", use_cache=False)

    assert result.created is True
    assert result.cache_hit is False
    assert "abstract" in result.fields_filled
    assert "tldr" in result.fields_filled
    # Seed paper + two cited stubs.
    assert result.stubs_created == 2
    assert result.edges_created == 2
    assert _count(session, models.PaperWork) == 3
    assert _count(session, models.CitationEdge) == 2

    work = session.scalars(
        select(models.PaperWork).where(models.PaperWork.doi == "10.1/1")
    ).first()
    assert work.abstract == "An abstract."
    assert work.tldr == "TLDR 1"
    assert work.s2_corpus_id == "1"

    stub = session.scalars(
        select(models.PaperWork).where(models.PaperWork.s2_corpus_id == "2")
    ).first()
    assert stub.availability_state is AvailabilityState.metadata_stub


def test_second_lookup_is_cache_hit_without_fetch(session, fake_s2):
    lookup.fetch_and_cache_paper(session, "DOI:10.1/1", use_cache=False)
    fetches_after_first = fake_s2["get_paper"]

    result = lookup.fetch_and_cache_paper(session, "DOI:10.1/1", use_cache=False)
    assert result.cache_hit is True
    assert result.created is False
    # No new network call and no duplicate rows.
    assert fake_s2["get_paper"] == fetches_after_first
    assert _count(session, models.PaperWork) == 3
    assert _count(session, models.CitationEdge) == 2


def test_partial_work_is_enriched_in_place(session, fake_s2):
    # A stub we already hold (corpusId only, no abstract) is filled, not duplicated.
    existing = models.PaperWork(
        work_id="work_pre",
        s2_corpus_id="1",
        availability_state=AvailabilityState.metadata_stub,
    )
    session.add(existing)
    session.commit()

    result = lookup.fetch_and_cache_paper(session, "CorpusId:1", use_cache=False)
    assert result.created is False
    assert result.work_id == "work_pre"
    assert "abstract" in result.fields_filled

    session.refresh(existing)
    assert existing.abstract == "An abstract."
    assert existing.title == "Paper 1"


def test_without_references_skips_edges(session, fake_s2):
    result = lookup.fetch_and_cache_paper(
        session, "DOI:10.1/1", with_references=False, use_cache=False
    )
    assert result.edges_created == 0
    assert _count(session, models.CitationEdge) == 0
    assert _count(session, models.PaperWork) == 1
    assert fake_s2["get_references"] == 0


def test_unresolvable_id_raises(session, fake_s2):
    with pytest.raises(lookup.LookupError):
        lookup.fetch_and_cache_paper(session, "DOI:10.1/missing", use_cache=False)


def test_lookup_endpoint_requires_auth(client):
    resp = client.post("/v1/papers/lookup", json={"external_id": "DOI:10.1/1"})
    assert resp.status_code == 401


def test_lookup_endpoint_round_trips(client, user_headers, fake_s2):
    resp = client.post(
        "/v1/papers/lookup",
        json={"external_id": "DOI:10.1/1"},
        headers=user_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] is True
    assert body["cache_hit"] is False
    assert body["edges_created"] == 2
    assert body["paper"]["abstract"] == "An abstract."
    assert body["paper"]["doi"] == "10.1/1"


def test_lookup_endpoint_404_for_missing(client, user_headers, fake_s2):
    resp = client.post(
        "/v1/papers/lookup",
        json={"external_id": "DOI:10.1/missing"},
        headers=user_headers,
    )
    assert resp.status_code == 404
