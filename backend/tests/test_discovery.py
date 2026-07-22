"""Seed-based discovery service + /v1/discovery API tests (litmaps-parity WP-L1).

Semantic Scholar is never hit: ``enrichment.reference_links`` is monkeypatched so the
tests are deterministic and offline. They assert the co-reference ranking, seed
self-exclusion, in-corpus resolution, the year filter, and the API contract.
"""

from __future__ import annotations

import pytest

from interciter import models
from interciter.enums import AvailabilityState
from interciter.services import discovery, enrichment


def _work(session, work_id, **kw):
    work = models.PaperWork(
        work_id=work_id,
        availability_state=AvailabilityState.metadata_stub,
        **kw,
    )
    session.add(work)
    session.commit()
    return work


# References keyed by the S2 id each seed resolves to (DOI:<doi>).
_REFS = {
    "DOI:10.1/a": [
        {"cited_corpus_id": "100", "cited_doi": None, "cited_pmid": None,
         "cited_title": "Shared reference", "cited_year": 2020, "is_influential": True},
        {"cited_corpus_id": "101", "cited_doi": None, "cited_pmid": None,
         "cited_title": "Only from A", "cited_year": 2019, "is_influential": False},
        # A reference that IS seed B — must be excluded from recommendations.
        {"cited_corpus_id": None, "cited_doi": "10.1/b", "cited_pmid": None,
         "cited_title": "Seed B", "cited_year": 2018, "is_influential": False},
    ],
    "DOI:10.1/b": [
        {"cited_corpus_id": "100", "cited_doi": None, "cited_pmid": None,
         "cited_title": "Shared reference", "cited_year": 2020, "is_influential": False},
        {"cited_corpus_id": "102", "cited_doi": None, "cited_pmid": None,
         "cited_title": "Only from B", "cited_year": 2021, "is_influential": False},
    ],
}


def _fake_reference_links(paper_id, **kwargs):
    return list(_REFS.get(paper_id, []))


@pytest.fixture
def seeds(session):
    _work(session, "seed1", doi="10.1/a")
    _work(session, "seed2", doi="10.1/b")
    # An existing corpus work matching one candidate, so it resolves in-corpus.
    _work(session, "work_101", title="Local copy", s2_corpus_id="101", year=2019)
    return ["seed1", "seed2"]


def test_shared_reference_ranks_highest(session, seeds, monkeypatch):
    monkeypatch.setattr(enrichment, "reference_links", _fake_reference_links)
    result = discovery.discover_from_seeds(session, seeds, use_cache=False)

    assert result.seeds_resolved == 2
    assert result.skipped_seed_ids == []
    top = result.candidates[0]
    assert top.title == "Shared reference"
    assert top.connection_score == 2
    assert sorted(top.supporting_seed_ids) == ["seed1", "seed2"]
    assert top.is_influential is True
    # Seed B must never be recommended back.
    assert all(c.external_id != "DOI:10.1/b" for c in result.candidates)
    # The others are single-seed connections ("Only from A" resolves to the local
    # copy work_101, so it displays that work's title).
    others = {c.title: c.connection_score for c in result.candidates[1:]}
    assert others == {"Local copy": 1, "Only from B": 1}


def test_in_corpus_candidate_is_resolved(session, seeds, monkeypatch):
    monkeypatch.setattr(enrichment, "reference_links", _fake_reference_links)
    result = discovery.discover_from_seeds(session, seeds, use_cache=False)
    by_title = {c.title: c for c in result.candidates}
    # Corpus id 101 exists locally as work_101 → deep-linkable.
    local = by_title["Local copy"]
    assert local.in_corpus is True
    assert local.work_id == "work_101"
    # A candidate we don't hold is external-only.
    assert by_title["Only from B"].in_corpus is False
    assert by_title["Only from B"].work_id is None
    assert by_title["Only from B"].external_id == "CorpusId:102"


def test_min_year_filters_older_candidates(session, seeds, monkeypatch):
    monkeypatch.setattr(enrichment, "reference_links", _fake_reference_links)
    result = discovery.discover_from_seeds(
        session, seeds, min_year=2021, use_cache=False
    )
    titles = {c.title for c in result.candidates}
    assert titles == {"Only from B"}  # only the 2021 candidate survives


def test_unidentifiable_seed_is_skipped(session, monkeypatch):
    _work(session, "bare")  # no DOI/PMID/corpusId
    monkeypatch.setattr(enrichment, "reference_links", _fake_reference_links)
    result = discovery.discover_from_seeds(session, ["bare"], use_cache=False)
    assert result.seeds_resolved == 0
    assert result.skipped_seed_ids == ["bare"]
    assert result.candidates == []


def test_missing_seed_raises(session):
    with pytest.raises(KeyError):
        discovery.discover_from_seeds(session, ["nope"], use_cache=False)


def test_api_discovery_requires_auth_and_returns_ranking(
    session, client, user_headers, seeds, monkeypatch
):
    monkeypatch.setattr(enrichment, "reference_links", _fake_reference_links)

    # Reads-open does not apply: discovery hits the network, so writes-style auth.
    anon = client.post("/v1/discovery/seeds", json={"seed_work_ids": seeds})
    assert anon.status_code == 401

    resp = client.post(
        "/v1/discovery/seeds",
        json={"seed_work_ids": seeds, "limit": 10},
        headers=user_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["candidates"][0]["title"] == "Shared reference"
    assert body["candidates"][0]["connection_score"] == 2


def test_api_discovery_404_on_missing_seed(session, client, user_headers, monkeypatch):
    monkeypatch.setattr(enrichment, "reference_links", _fake_reference_links)
    resp = client.post(
        "/v1/discovery/seeds",
        json={"seed_work_ids": ["ghost"]},
        headers=user_headers,
    )
    assert resp.status_code == 404
