"""Snowball corpus-builder tests (interciter seed-corpus).

Semantic Scholar is never hit: ``get_paper`` / ``get_references`` are monkeypatched so the
tests are deterministic and offline. They assert breadth-first growth to the target size,
stub creation, edge creation + idempotency, in-corpus dedup against pre-existing works,
skipping unidentifiable references, and unresolved-seed handling.
"""

from __future__ import annotations

import pytest

from sqlalchemy import func, select

from interciter import models
from interciter.enums import AvailabilityState
from interciter.ingestion import semantic_scholar as s2
from interciter.ingestion import snowball


def _ref(n: int, *, influential: bool = False) -> dict:
    return {
        "isInfluential": influential,
        "intents": ["background"] if not influential else ["methodology"],
        "citedPaper": {
            "externalIds": {"CorpusId": n, "DOI": f"10.1/{n}"},
            "title": f"Paper {n}",
            "year": 2019,
            "authors": [{"name": f"Author {n}"}],
        },
    }


# A small citation graph: seed(1) -> {2,3}; 2 -> {4}; 3 -> {5}.
_PAPERS = {
    "DOI:10.1/seed": {
        "externalIds": {"CorpusId": 1, "DOI": "10.1/seed"},
        "title": "Seed paper",
        "year": 2021,
        "venue": "Journal of Seeds",
        "authors": [{"name": "Ada Root"}],
    },
}
_REFS = {
    "CorpusId:1": [_ref(2), _ref(3, influential=True)],
    "CorpusId:2": [_ref(4)],
    "CorpusId:3": [_ref(5)],
    "CorpusId:4": [],
    "CorpusId:5": [],
}


@pytest.fixture
def fake_s2(monkeypatch):
    def fake_get_paper(paper_id, fields=None, **kwargs):
        if paper_id not in _PAPERS:
            raise s2.S2Error(f"not found: {paper_id}")
        return _PAPERS[paper_id]

    def fake_get_references(paper_id, fields=None, *, max_records=None, **kwargs):
        refs = _REFS.get(paper_id, [])
        return refs[:max_records] if max_records else refs

    monkeypatch.setattr(snowball.s2, "get_paper", fake_get_paper)
    monkeypatch.setattr(snowball.s2, "get_references", fake_get_references)


def _count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_snowball_builds_graph(session, fake_s2):
    result = snowball.build_corpus(
        session, ["DOI:10.1/seed"], target_size=10, use_cache=False
    )
    # seed(1) + {2,3,4,5} = 5 distinct works, all created this run.
    assert result.works_total == 5
    assert result.works_created == 5
    assert _count(session, models.PaperWork) == 5
    # Edges: 1->2, 1->3, 2->4, 3->5.
    assert result.edges_created == 4
    assert _count(session, models.CitationEdge) == 4
    assert result.seeds_resolved == 1
    assert result.seeds_missing == []

    seed = session.scalars(
        select(models.PaperWork).where(models.PaperWork.doi == "10.1/seed")
    ).first()
    assert seed.s2_corpus_id == "1"
    assert seed.venue == "Journal of Seeds"
    assert seed.authors == ["Ada Root"]

    stub = session.scalars(
        select(models.PaperWork).where(models.PaperWork.s2_corpus_id == "2")
    ).first()
    assert stub.availability_state is AvailabilityState.metadata_stub
    assert stub.authors == ["Author 2"]

    # Manifest rows carry identifiers only.
    assert len(result.corpus) == 5
    assert all("corpus_id" in row for row in result.corpus)


def test_snowball_is_idempotent(session, fake_s2):
    snowball.build_corpus(session, ["DOI:10.1/seed"], target_size=10, use_cache=False)
    second = snowball.build_corpus(
        session, ["DOI:10.1/seed"], target_size=10, use_cache=False
    )
    assert second.works_created == 0
    assert second.edges_created == 0
    assert _count(session, models.PaperWork) == 5
    assert _count(session, models.CitationEdge) == 4


def test_target_size_stops_expansion(session, fake_s2):
    result = snowball.build_corpus(
        session, ["DOI:10.1/seed"], target_size=3, use_cache=False
    )
    # Stops as soon as the corpus reaches 3 papers (seed + first two references).
    assert result.works_total == 3
    assert _count(session, models.PaperWork) == 3


def test_resolves_preexisting_work(session, fake_s2):
    # A work already in the corpus for CorpusId:2 must be reused, not duplicated.
    existing = models.PaperWork(
        work_id="work_pre",
        title="Pre-existing 2",
        s2_corpus_id="2",
        availability_state=AvailabilityState.full_text_extracted,
    )
    session.add(existing)
    session.commit()

    result = snowball.build_corpus(
        session, ["DOI:10.1/seed"], target_size=10, use_cache=False
    )
    twos = session.scalars(
        select(models.PaperWork).where(models.PaperWork.s2_corpus_id == "2")
    ).all()
    assert len(twos) == 1
    assert twos[0].work_id == "work_pre"
    # The pre-existing work counts toward the corpus but was not created this run.
    assert result.works_created == 4


def test_skips_unidentifiable_references(session, fake_s2, monkeypatch):
    monkeypatch.setitem(
        _REFS,
        "CorpusId:1",
        [_ref(2), {"isInfluential": False, "intents": [], "citedPaper": {"title": "No ids"}}],
    )
    result = snowball.build_corpus(
        session, ["DOI:10.1/seed"], target_size=10, use_cache=False
    )
    # The id-less reference is skipped: only seed(1) + 2 (+ 4 from expanding 2).
    titles = {w.title for w in session.scalars(select(models.PaperWork))}
    assert "No ids" not in titles


def test_unresolved_seed_is_reported(session, fake_s2):
    result = snowball.build_corpus(
        session, ["DOI:10.1/missing"], target_size=10, use_cache=False
    )
    assert result.seeds_resolved == 0
    assert result.seeds_missing == ["DOI:10.1/missing"]
    assert result.works_total == 0
