"""Read-side projection and bounded traversal.

Implements the design's core separation: the write model (normalized, immutable) is the
system of record; reads flatten the occurrence/interpretation/cluster chain into a
composed **Claim** view, with every projected edge pointing back to its evidence-bearing
``RelationAssertion``. The projection is derived and rebuildable — never authoritative.

"Current head" of a revision graph is *derived here at read time*, never stored as a
mutable flag on the record.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..enums import AssertionStatus, MembershipStatus, RelationResolution, RelationStance
from ..schemas import (
    ClaimScores,
    ClaimView,
    EvidenceRef,
    OneHopTrace,
    PaperView,
    RelationAssertionView,
    ScoreComponent,
    TargetCandidate,
    TraceHop,
)


class NotFound(LookupError):
    """Raised when a requested resource does not exist."""


# ---------------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------------


def _evidence_for_passage(session: Session, passage: models.Passage) -> EvidenceRef:
    version = session.get(models.PaperVersion, passage.paper_version_id)
    work_id = version.work_id if version else "unknown"
    return EvidenceRef(
        passage_id=passage.passage_id,
        paper_version_id=passage.paper_version_id,
        work_id=work_id,
        section=passage.section,
        verbatim_text=passage.verbatim_text,
        char_start=passage.char_start,
        char_end=passage.char_end,
    )


def build_claim_view(session: Session, interp: models.ClaimInterpretation) -> ClaimView:
    occurrence = session.get(models.ClaimOccurrence, interp.claim_occurrence_id)
    if occurrence is None:
        raise NotFound(f"occurrence {interp.claim_occurrence_id} missing")
    passage = session.get(models.Passage, occurrence.passage_id)
    evidence = _evidence_for_passage(session, passage)
    return ClaimView(
        claim_id=interp.interpretation_id,
        normalized_text=interp.normalized_text,
        occurrence_id=occurrence.occurrence_id,
        interpretation_id=interp.interpretation_id,
        occurrence_type=occurrence.occurrence_type,
        qualifiers=interp.qualifiers,
        work_id=evidence.work_id,
        evidence=evidence,
    )


def _is_head(session: Session, interpretation_id: str) -> bool:
    """A head is an interpretation no other interpretation lists as a parent."""
    for other in session.scalars(select(models.ClaimInterpretation)):
        if interpretation_id in (other.parent_interpretation_ids or []):
            return False
    return True


def get_claim(session: Session, claim_id: str) -> ClaimView:
    interp = session.get(models.ClaimInterpretation, claim_id)
    if interp is None:
        raise NotFound(f"claim {claim_id} not found")
    return build_claim_view(session, interp)


def claims_for_paper(session: Session, work_id: str) -> list[ClaimView]:
    stmt = (
        select(models.ClaimInterpretation)
        .join(
            models.ClaimOccurrence,
            models.ClaimInterpretation.claim_occurrence_id
            == models.ClaimOccurrence.occurrence_id,
        )
        .join(models.Passage, models.ClaimOccurrence.passage_id == models.Passage.passage_id)
        .join(
            models.PaperVersion,
            models.Passage.paper_version_id == models.PaperVersion.version_id,
        )
        .where(models.PaperVersion.work_id == work_id)
    )
    interps = list(session.scalars(stmt))
    parent_ids: set[str] = set()
    for interp in session.scalars(select(models.ClaimInterpretation)):
        parent_ids.update(interp.parent_interpretation_ids or [])
    return [
        build_claim_view(session, interp)
        for interp in interps
        if interp.interpretation_id not in parent_ids
    ]


# ---------------------------------------------------------------------------------
# Relations & one-hop traversal
# ---------------------------------------------------------------------------------


def relation_view(assertion: models.RelationAssertion) -> RelationAssertionView:
    return RelationAssertionView(
        assertion_id=assertion.assertion_id,
        citing_occurrence_id=assertion.citing_occurrence_id,
        citation_mention_id=assertion.citation_mention_id,
        evidence_passage_id=assertion.evidence_passage_id,
        cited_work_id=assertion.cited_work_id,
        target_interpretation_id=assertion.target_interpretation_id,
        target_candidates=[
            TargetCandidate(**c) for c in (assertion.target_candidates or [])
        ],
        function=assertion.function,
        stance=assertion.stance,
        scope=assertion.scope,
        resolution=assertion.resolution,
        target_link_score=assertion.target_link_score,
        stance_distribution=assertion.stance_distribution,
        extraction_run_id=assertion.extraction_run_id,
        status=assertion.status,
    )


def _relations_for_occurrence(
    session: Session, occurrence_id: str
) -> list[models.RelationAssertion]:
    return list(
        session.scalars(
            select(models.RelationAssertion).where(
                models.RelationAssertion.citing_occurrence_id == occurrence_id
            )
        )
    )


def relationships_for_claim(
    session: Session,
    claim_id: str,
    *,
    stance: RelationStance | None = None,
    resolution: RelationResolution | None = None,
    status: AssertionStatus | None = None,
) -> list[RelationAssertionView]:
    interp = session.get(models.ClaimInterpretation, claim_id)
    if interp is None:
        raise NotFound(f"claim {claim_id} not found")
    rows = _relations_for_occurrence(session, interp.claim_occurrence_id)
    views = []
    for r in rows:
        if stance is not None and r.stance != stance:
            continue
        if resolution is not None and r.resolution != resolution:
            continue
        if status is not None and r.status != status:
            continue
        views.append(relation_view(r))
    return views


def paper_view(work: models.PaperWork) -> PaperView:
    return PaperView(
        work_id=work.work_id,
        title=work.title,
        authors=work.authors or [],
        venue=work.venue,
        year=work.year,
        doi=work.doi,
        pmid=work.pmid,
        s2_corpus_id=work.s2_corpus_id,
        availability_state=work.availability_state,
    )


def list_papers(
    session: Session, *, limit: int = 50, offset: int = 0
) -> list[PaperView]:
    """Ingested works, ordered by title then id — the reader's entry list (US-1.2)."""
    stmt = (
        select(models.PaperWork)
        .order_by(models.PaperWork.title, models.PaperWork.work_id)
        .limit(limit)
        .offset(offset)
    )
    return [paper_view(w) for w in session.scalars(stmt)]


def one_hop_trace(session: Session, claim_id: str) -> OneHopTrace:
    """Trace a claim one hop to its cited antecedents.

    A ``paper_resolved`` hop is labeled as a paper-level continuation and never dressed
    up as a claim-level one (api.md).
    """
    interp = session.get(models.ClaimInterpretation, claim_id)
    if interp is None:
        raise NotFound(f"claim {claim_id} not found")

    hops: list[TraceHop] = []
    for assertion in _relations_for_occurrence(session, interp.claim_occurrence_id):
        target_claim = None
        target_work = None
        if (
            assertion.resolution == RelationResolution.claim_resolved
            and assertion.target_interpretation_id
        ):
            target = session.get(
                models.ClaimInterpretation, assertion.target_interpretation_id
            )
            if target is not None:
                target_claim = build_claim_view(session, target)
        if assertion.cited_work_id:
            work = session.get(models.PaperWork, assertion.cited_work_id)
            if work is not None:
                target_work = paper_view(work)

        evidence = None
        if assertion.evidence_passage_id:
            passage = session.get(models.Passage, assertion.evidence_passage_id)
            if passage is not None:
                evidence = _evidence_for_passage(session, passage)

        hops.append(
            TraceHop(
                assertion_id=assertion.assertion_id,
                function=assertion.function,
                stance=assertion.stance,
                resolution=assertion.resolution,
                target_link_score=assertion.target_link_score,
                target_claim=target_claim,
                target_work=target_work,
                evidence=evidence,
            )
        )

    note = None
    if any(h.resolution == RelationResolution.paper_resolved for h in hops):
        note = (
            "Some hops are paper_resolved: the cited paper is identified but the exact "
            "target claim is not, so they are bibliographic continuations, not "
            "claim-level ones."
        )
    return OneHopTrace(root_claim_id=claim_id, hops=hops, truncated=False, note=note)


# ---------------------------------------------------------------------------------
# Decomposed scores (never a blended scalar)
# ---------------------------------------------------------------------------------


def claim_scores(session: Session, claim_id: str) -> ClaimScores:
    interp = session.get(models.ClaimInterpretation, claim_id)
    if interp is None:
        raise NotFound(f"claim {claim_id} not found")

    components: list[ScoreComponent] = []

    # Extraction fidelity — proxied by normalized certainty in the MVP.
    certainty_map = {"definite": 0.9, "probable": 0.7, "possible": 0.5, "speculative": 0.3}
    certainty = (interp.qualifiers or {}).get("certainty")
    components.append(
        ScoreComponent(
            name="extraction_fidelity",
            value=certainty_map.get(certainty),
            inputs={"certainty": certainty},
        )
    )

    relations = _relations_for_occurrence(session, interp.claim_occurrence_id)
    if relations:
        link = max((r.target_link_score or 0.0) for r in relations)
        stance_conf = max(
            (max((r.stance_distribution or {}).values(), default=0.0)) for r in relations
        )
        components.append(
            ScoreComponent(name="target_link_confidence", value=round(link, 3))
        )
        components.append(
            ScoreComponent(name="stance_confidence", value=round(stance_conf, 3))
        )

    # Review status.
    reviews = list(
        session.scalars(
            select(models.ReviewDecision).where(
                models.ReviewDecision.subject_id == claim_id
            )
        )
    )
    components.append(
        ScoreComponent(
            name="review_status",
            value=1.0 if reviews else 0.0,
            inputs={"review_count": len(reviews)},
        )
    )

    # Model agreement (same occurrence) vs literature corroboration (independent papers).
    model_agreement, corroboration = _agreement_and_corroboration(session, interp)
    components.append(
        ScoreComponent(name="model_agreement", value=float(model_agreement))
    )
    components.append(
        ScoreComponent(name="literature_corroboration", value=float(corroboration))
    )

    return ClaimScores(claim_id=claim_id, components=components)


def _agreement_and_corroboration(
    session: Session, interp: models.ClaimInterpretation
) -> tuple[int, int]:
    # Model agreement: distinct interpretations of the *same* occurrence.
    same_occurrence = list(
        session.scalars(
            select(models.ClaimInterpretation).where(
                models.ClaimInterpretation.claim_occurrence_id
                == interp.claim_occurrence_id
            )
        )
    )
    model_agreement = max(len(same_occurrence) - 1, 0)

    # Literature corroboration: independent papers landing in the same cluster.
    membership = session.scalar(
        select(models.ClusterMembership).where(
            models.ClusterMembership.interpretation_id == interp.interpretation_id,
            models.ClusterMembership.status == MembershipStatus.active,
        )
    )
    if membership is None:
        return model_agreement, 0
    co_members = session.scalars(
        select(models.ClusterMembership).where(
            models.ClusterMembership.cluster_id == membership.cluster_id,
            models.ClusterMembership.status == MembershipStatus.active,
        )
    )
    works: set[str] = set()
    for m in co_members:
        target = session.get(models.ClaimInterpretation, m.interpretation_id)
        if target is None:
            continue
        occurrence = session.get(models.ClaimOccurrence, target.claim_occurrence_id)
        passage = session.get(models.Passage, occurrence.passage_id) if occurrence else None
        version = (
            session.get(models.PaperVersion, passage.paper_version_id)
            if passage
            else None
        )
        if version:
            works.add(version.work_id)
    corroboration = max(len(works) - 1, 0)
    return model_agreement, corroboration
