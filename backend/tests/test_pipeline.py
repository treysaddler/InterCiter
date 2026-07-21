"""Pipeline tests: the end-to-end vertical slice at the service level."""

from __future__ import annotations

from interciter.enums import RelationResolution, RelationStance
from interciter.ingestion.pipeline import ingest_paper
from interciter.services import projection

from helpers import load_sample


def _ingest_both(session):
    b = ingest_paper(session, xml=load_sample("paper_b.xml"))
    a = ingest_paper(session, xml=load_sample("paper_a.xml"))
    return b, a


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
