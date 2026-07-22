"""Paper report service + /v1 endpoint tests (scite-parity WP3, F4)."""

from __future__ import annotations

from interciter import enums, ids, models
from interciter.ingestion.pipeline import ingest_paper
from interciter.services import report

from helpers import load_sample


def _ingest_both(session):
    b = ingest_paper(session, xml=load_sample("paper_b.xml"))
    a = ingest_paper(session, xml=load_sample("paper_a.xml"))
    session.commit()
    return b, a


def _clone_assertion(session, assertion: models.RelationAssertion, *, stance):
    clone = models.RelationAssertion(
        assertion_id=ids.new_id("RelationAssertion"),
        citing_occurrence_id=assertion.citing_occurrence_id,
        citation_mention_id=assertion.citation_mention_id,
        evidence_passage_id=assertion.evidence_passage_id,
        cited_work_id=assertion.cited_work_id,
        target_interpretation_id=assertion.target_interpretation_id,
        target_candidates=assertion.target_candidates,
        function=assertion.function,
        stance=stance,
        scope=assertion.scope,
        resolution=assertion.resolution,
        target_link_score=assertion.target_link_score,
        stance_distribution=assertion.stance_distribution,
        extraction_run_id=assertion.extraction_run_id,
        status=assertion.status,
    )
    session.add(clone)
    return clone


def test_report_timeline_buckets_statements_and_dedupes_works(session):
    b, _ = _ingest_both(session)

    base = session.query(models.RelationAssertion).first()
    assert base is not None
    _clone_assertion(session, base, stance=base.stance)

    occurrence = session.get(models.ClaimOccurrence, base.citing_occurrence_id)
    passage = session.get(models.Passage, occurrence.passage_id)
    version = session.get(models.PaperVersion, passage.paper_version_id)
    citing_work = session.get(models.PaperWork, version.work_id)
    # Ensure a year exists so timeline bucketing is deterministic.
    citing_work.year = citing_work.year or 2021
    session.commit()

    result = report.paper_report_for_work(session, b.work_id)
    assert result.work_id == b.work_id
    assert result.filtered_statements == result.tallies.total
    assert result.total_statements >= 2
    assert result.timeline, "expected at least one year bucket"

    first_bucket = result.timeline[0]
    assert first_bucket.statement_count >= 2
    # Two statements from one citing work should dedupe in the work count.
    assert first_bucket.citing_work_count == 1


def test_report_conflict_summary_and_filters(session):
    b, _ = _ingest_both(session)
    base = session.query(models.RelationAssertion).first()
    assert base is not None
    _clone_assertion(session, base, stance=enums.RelationStance.contradict)
    session.commit()

    result = report.paper_report_for_work(session, b.work_id)
    assert result.conflict_summary.has_conflicting_stances is True
    assert result.conflict_summary.supporting_statements >= 1
    assert result.conflict_summary.contradicting_statements >= 1
    assert result.conflict_summary.conflicting_citing_work_count >= 1

    filtered = report.paper_report_for_work(session, b.work_id, stance="contradict")
    assert filtered.filtered_statements >= 1
    assert filtered.tallies.by_stance.get("contradict", 0) >= 1
    assert filtered.conflict_summary.has_conflicting_stances is False


def test_api_paper_report_endpoint(session, client):
    b, _ = _ingest_both(session)

    resp = client.get(f"/v1/papers/{b.work_id}/report")
    assert resp.status_code == 200
    body = resp.json()
    assert body["work_id"] == b.work_id
    assert "timeline" in body
    assert "conflict_summary" in body

    contradict_only = client.get(
        f"/v1/papers/{b.work_id}/report", params={"stance": "contradict"}
    )
    assert contradict_only.status_code == 200

    assert client.get("/v1/papers/work_missing/report").status_code == 404
