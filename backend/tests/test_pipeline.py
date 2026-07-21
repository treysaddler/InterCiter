"""Pipeline tests: the end-to-end vertical slice at the service level."""

from __future__ import annotations

from sqlalchemy import select

from interciter import models
from interciter.config import Settings
from interciter.enums import Manifestation, OccurrenceType, RelationResolution, RelationStance
from interciter.ingestion.pipeline import _cluster_new_interpretations, ingest_paper
from interciter.services import enrichment, projection

from helpers import load_sample


def _ingest_both(session):
    b = ingest_paper(session, xml=load_sample("paper_b.xml"))
    a = ingest_paper(session, xml=load_sample("paper_a.xml"))
    return b, a


def _paper_with_claim(session, run_id, work_id, corpus_id, text):
    """Seed a minimal work→version→passage→occurrence→interpretation for clustering."""
    session.add(
        models.PaperWork(work_id=work_id, s2_corpus_id=corpus_id)
    )
    session.add(
        models.PaperVersion(
            version_id=f"v_{work_id}", work_id=work_id, manifestation=Manifestation.published
        )
    )
    session.add(
        models.Passage(
            passage_id=f"p_{work_id}", paper_version_id=f"v_{work_id}", verbatim_text=text
        )
    )
    session.add(
        models.ClaimOccurrence(
            occurrence_id=f"o_{work_id}",
            passage_id=f"p_{work_id}",
            occurrence_type=OccurrenceType.reported_result,
            extraction_run_id=run_id,
        )
    )
    session.add(
        models.ClaimInterpretation(
            interpretation_id=f"i_{work_id}",
            claim_occurrence_id=f"o_{work_id}",
            normalized_text=text,
            extraction_run_id=run_id,
            parent_interpretation_ids=[],
        )
    )


def _memberships(session) -> int:
    return len(session.scalars(select(models.ClusterMembership)).all())


def test_ingest_produces_records(session):
    b, a = _ingest_both(session)
    assert b.interpretations >= 1
    assert a.interpretations >= 1
    assert a.relation_assertions >= 3  # B1, B2, B3 citations


def test_citation_to_b_resolves_at_claim_level(session):
    b, a = _ingest_both(session)
    # A cites B (already ingested), so at least one relation resolves to a target claim.
    assert a.claim_resolved >= 1


def test_stub_cited_works_fall_back_to_paper_level(session):
    _, a = _ingest_both(session)
    assert a.paper_resolved >= 1  # B2 / B3 are metadata stubs


def test_one_hop_trace_reaches_b(session):
    _, a = _ingest_both(session)
    claims = projection.claims_for_paper(session, a.work_id)
    # Find the citing claim that produced a claim-resolved hop.
    resolved_hops = []
    for claim in claims:
        trace = projection.one_hop_trace(session, claim.claim_id)
        resolved_hops += [
            h for h in trace.hops if h.resolution == RelationResolution.claim_resolved
        ]
    assert resolved_hops, "expected a claim-resolved one-hop trace into paper B"
    hop = resolved_hops[0]
    assert hop.target_claim is not None
    assert "glucose" in hop.target_claim.normalized_text.lower()
    assert hop.evidence is not None  # every hop carries evidence


def test_specter2_prefilter_gates_dissimilar_papers(session, tmp_path):
    # Two papers with identical claim text would cluster on token overlap alone; a
    # paper-level SPECTER2 gate (orthogonal embeddings) blocks the cross-paper pair.
    session.add(models.ExtractionRun(run_id="r1"))
    _paper_with_claim(session, "r1", "wa", "100", "metformin reduces fasting glucose")
    _paper_with_claim(session, "r1", "wb", "200", "metformin reduces fasting glucose")
    session.flush()
    settings = Settings(s2_cache_dir=str(tmp_path), embedding_prefilter_threshold=0.9)
    enrichment.cache_embedding("100", [1.0, 0.0], settings=settings)
    enrichment.cache_embedding("200", [0.0, 1.0], settings=settings)  # orthogonal
    _cluster_new_interpretations(session, "r1", settings)
    assert _memberships(session) == 0


def test_specter2_prefilter_allows_similar_papers(session, tmp_path):
    session.add(models.ExtractionRun(run_id="r1"))
    _paper_with_claim(session, "r1", "wa", "100", "metformin reduces fasting glucose")
    _paper_with_claim(session, "r1", "wb", "200", "metformin reduces fasting glucose")
    session.flush()
    settings = Settings(s2_cache_dir=str(tmp_path), embedding_prefilter_threshold=0.9)
    enrichment.cache_embedding("100", [1.0, 0.0], settings=settings)
    enrichment.cache_embedding("200", [1.0, 0.0], settings=settings)  # aligned
    _cluster_new_interpretations(session, "r1", settings)
    assert _memberships(session) >= 2  # both interpretations joined one cluster


def test_prefilter_falls_back_when_embeddings_missing(session, tmp_path):
    # No cached embeddings -> gate defers to token overlap, so identical claims cluster.
    session.add(models.ExtractionRun(run_id="r1"))
    _paper_with_claim(session, "r1", "wa", "100", "metformin reduces fasting glucose")
    _paper_with_claim(session, "r1", "wb", "200", "metformin reduces fasting glucose")
    session.flush()
    settings = Settings(s2_cache_dir=str(tmp_path))
    _cluster_new_interpretations(session, "r1", settings)
    assert _memberships(session) >= 2


def test_scores_are_decomposed(session):
    _, a = _ingest_both(session)
    claims = projection.claims_for_paper(session, a.work_id)
    scores = projection.claim_scores(session, claims[0].claim_id)
    names = {c.name for c in scores.components}
    # Model agreement and literature corroboration are separate signals, never summed.
    assert "model_agreement" in names
    assert "literature_corroboration" in names
    assert "stance_confidence" in names or "extraction_fidelity" in names


def test_abstention_possible(session):
    # The stance vocabulary includes an explicit abstain value.
    assert RelationStance.unclear in set(RelationStance)
