"""Citation-stats service + /v1 endpoint tests (scite-parity WP1).

After ingesting paper B then paper A (A cites a claim in B), B — and the specific
claim in B that A resolves to — should show one citing statement, tallied by stance,
function, resolution, and section, with abstention counted separately.
"""

from __future__ import annotations

import pytest

from interciter.ingestion.pipeline import ingest_paper
from interciter.services import citation_stats

from helpers import load_sample


def _ingest_both(session):
    b = ingest_paper(session, xml=load_sample("paper_b.xml"))
    a = ingest_paper(session, xml=load_sample("paper_a.xml"))
    session.commit()
    return b, a


def test_work_stats_count_the_citing_statement(session):
    b, a = _ingest_both(session)
    stats = citation_stats.citation_stats_for_work(session, b.work_id)

    assert stats.subject_type == "work"
    assert stats.subject_id == b.work_id
    assert stats.tallies.total >= 1
    # The seed corpus resolves A→B as a supporting, direct-evidence claim link.
    assert stats.tallies.by_stance.get("support", 0) >= 1
    assert stats.tallies.by_function.get("direct_evidence", 0) >= 1
    assert stats.tallies.by_resolution.get("claim_resolved", 0) >= 1
    # Every statement carries provenance (section facet + evidence span).
    stmt = stats.statements[0]
    assert stmt.citing_work_id == a.work_id
    assert stmt.evidence is not None
    assert stmt.section in stats.tallies.by_section


def test_claim_stats_target_the_resolved_interpretation(session):
    b, _ = _ingest_both(session)
    work_stats = citation_stats.citation_stats_for_work(session, b.work_id)
    # Find the target claim the resolved statement points at.
    resolved = [
        s for s in work_stats.statements if s.resolution.value == "claim_resolved"
    ]
    assert resolved, "expected a claim-resolved citing statement"

    from interciter import models

    assertion = session.get(models.RelationAssertion, resolved[0].assertion_id)
    target_id = assertion.target_interpretation_id
    assert target_id is not None

    claim_stats = citation_stats.citation_stats_for_claim(session, target_id)
    assert claim_stats.subject_type == "claim"
    assert claim_stats.subject_id == target_id
    assert claim_stats.tallies.total >= 1
    assert claim_stats.tallies.by_stance.get("support", 0) >= 1


def test_work_with_no_citations_has_empty_tallies(session):
    from interciter import models
    from interciter.enums import AvailabilityState

    work = models.PaperWork(
        work_id="work_lonely", availability_state=AvailabilityState.metadata_stub
    )
    session.add(work)
    session.commit()

    stats = citation_stats.citation_stats_for_work(session, "work_lonely")
    assert stats.tallies.total == 0
    assert stats.tallies.by_stance == {}
    assert stats.tallies.abstained == 0
    assert stats.statements == []


def test_missing_subjects_raise_keyerror(session):
    with pytest.raises(KeyError):
        citation_stats.citation_stats_for_work(session, "work_missing")
    with pytest.raises(KeyError):
        citation_stats.citation_stats_for_claim(session, "interp_missing")


def test_api_paper_citation_stats(session, client):
    b, _ = _ingest_both(session)
    resp = client.get(f"/v1/papers/{b.work_id}/citation-stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["subject_type"] == "work"
    assert body["tallies"]["total"] >= 1
    assert body["tallies"]["by_stance"].get("support", 0) >= 1

    assert client.get("/v1/papers/work_missing/citation-stats").status_code == 404


def test_api_claim_citation_stats(session, client):
    b, _ = _ingest_both(session)
    work_stats = citation_stats.citation_stats_for_work(session, b.work_id)
    from interciter import models

    resolved = [
        s for s in work_stats.statements if s.resolution.value == "claim_resolved"
    ][0]
    target_id = session.get(
        models.RelationAssertion, resolved.assertion_id
    ).target_interpretation_id

    resp = client.get(f"/v1/claims/{target_id}/citation-stats")
    assert resp.status_code == 200
    assert resp.json()["subject_type"] == "claim"

    assert client.get("/v1/claims/interp_missing/citation-stats").status_code == 404
