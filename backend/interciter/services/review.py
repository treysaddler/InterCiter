"""Human-review and authoring operations — all additive, all in the system of record.

Revising is creating (a new interpretation with the old as parent); reviewing appends a
per-dimension ``ReviewDecision``; fixing a bad cluster soft-removes a membership. Nothing
is destroyed or overwritten.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..auth import NotAuthorized, Principal
from ..enums import (
    AssertionStatus,
    MembershipStatus,
    RelationStance,
    ReviewSubjectType,
    Role,
)
from ..ids import new_id
from ..schemas import (
    ClaimInterpretationView,
    ClusterMemberView,
    ClusterView,
    HumanClaimCreate,
    InterpretationRevision,
    ReviewDecisionCreate,
    ReviewDecisionView,
    RevisionResult,
)
from .projection import NotFound


def _interp_view(interp: models.ClaimInterpretation) -> ClaimInterpretationView:
    return ClaimInterpretationView(
        interpretation_id=interp.interpretation_id,
        claim_occurrence_id=interp.claim_occurrence_id,
        normalized_text=interp.normalized_text,
        qualifiers=interp.qualifiers,
        extraction_run_id=interp.extraction_run_id,
        author_id=interp.author_id,
        parent_interpretation_ids=interp.parent_interpretation_ids or [],
        created_by=interp.created_by,
        created_at=interp.created_at,
    )


def create_human_claim(
    session: Session, payload: HumanClaimCreate, actor: Principal
) -> ClaimInterpretationView:
    if payload.occurrence_id:
        occurrence = session.get(models.ClaimOccurrence, payload.occurrence_id)
        if occurrence is None:
            raise NotFound(f"occurrence {payload.occurrence_id} not found")
    elif payload.passage_id:
        passage = session.get(models.Passage, payload.passage_id)
        if passage is None:
            raise NotFound(f"passage {payload.passage_id} not found")
        occurrence = models.ClaimOccurrence(
            occurrence_id=new_id("ClaimOccurrence"),
            passage_id=passage.passage_id,
            span_start=0,
            span_end=len(passage.verbatim_text),
            occurrence_type=payload.occurrence_type,
            extraction_run_id=_human_run(session).run_id,
        )
        session.add(occurrence)
    else:
        raise ValueError("provide either occurrence_id or passage_id")

    interp = models.ClaimInterpretation(
        interpretation_id=new_id("ClaimInterpretation"),
        claim_occurrence_id=occurrence.occurrence_id,
        normalized_text=payload.normalized_text,
        qualifiers=payload.qualifiers,
        author_id=actor.user_id,
        parent_interpretation_ids=[],
        created_by=actor.user_id,
    )
    session.add(interp)
    session.commit()
    return _interp_view(interp)


def revise_interpretation(
    session: Session,
    interpretation_id: str,
    payload: InterpretationRevision,
    actor: Principal,
) -> RevisionResult:
    parent = session.get(models.ClaimInterpretation, interpretation_id)
    if parent is None:
        raise NotFound(f"interpretation {interpretation_id} not found")

    # An edit is a correction claim about someone else's work: allowed only for the
    # original author or a reviewer/admin (docs/data-model.md, scoring-and-review.md).
    is_owner = parent.author_id is not None and parent.author_id == actor.user_id
    if not (is_owner or actor.can_act_as(Role.reviewer)):
        raise NotAuthorized(
            "revising an interpretation requires being its author or a reviewer/admin"
        )

    revision = models.ClaimInterpretation(
        interpretation_id=new_id("ClaimInterpretation"),
        claim_occurrence_id=parent.claim_occurrence_id,
        normalized_text=payload.normalized_text,
        qualifiers=payload.qualifiers if payload.qualifiers is not None else parent.qualifiers,
        author_id=actor.user_id,
        parent_interpretation_ids=[interpretation_id],
        created_by=actor.user_id,
    )
    session.add(revision)

    staled: list[str] = []
    if payload.material:
        # A materially different revision must not silently transfer support: mark
        # assertions that targeted the old interpretation stale_pending_review.
        assertions = session.scalars(
            select(models.RelationAssertion).where(
                models.RelationAssertion.target_interpretation_id == interpretation_id
            )
        )
        for assertion in assertions:
            assertion.status = AssertionStatus.stale_pending_review
            staled.append(assertion.assertion_id)

    session.commit()
    return RevisionResult(
        new_interpretation=_interp_view(revision),
        parent_interpretation_id=interpretation_id,
        staled_assertion_ids=staled,
    )


def create_review_decision(
    session: Session, payload: ReviewDecisionCreate, actor: Principal
) -> ReviewDecisionView:
    decision = models.ReviewDecision(
        review_id=new_id("ReviewDecision"),
        subject_type=payload.subject_type,
        subject_id=payload.subject_id,
        reviewer_id=actor.user_id,
        decision_dimension=payload.decision_dimension,
        label=payload.label,
        rationale=payload.rationale,
    )
    session.add(decision)

    # A review of an assertion flips its status per the design's review workflow.
    if payload.subject_type is ReviewSubjectType.relation_assertion and payload.label:
        assertion = session.get(models.RelationAssertion, payload.subject_id)
        if assertion is not None:
            if payload.label.lower() in {"accept", "accepted"}:
                assertion.status = AssertionStatus.accepted
            elif payload.label.lower() in {"reject", "rejected"}:
                assertion.status = AssertionStatus.rejected

    session.commit()
    return ReviewDecisionView(
        review_id=decision.review_id,
        subject_type=decision.subject_type,
        subject_id=decision.subject_id,
        reviewer_id=decision.reviewer_id,
        decision_dimension=decision.decision_dimension,
        label=decision.label,
        rationale=decision.rationale,
        timestamp=decision.timestamp,
    )


def get_cluster(session: Session, cluster_id: str) -> ClusterView:
    cluster = session.get(models.ClaimCluster, cluster_id)
    if cluster is None:
        raise NotFound(f"cluster {cluster_id} not found")
    memberships = session.scalars(
        select(models.ClusterMembership).where(
            models.ClusterMembership.cluster_id == cluster_id
        )
    )
    members: list[ClusterMemberView] = []
    stances: set[str] = set()
    for m in memberships:
        interp = session.get(models.ClaimInterpretation, m.interpretation_id)
        stance = _dominant_stance(session, m.interpretation_id)
        if stance is not None:
            stances.add(stance.value)
        members.append(
            ClusterMemberView(
                membership_id=m.membership_id,
                interpretation_id=m.interpretation_id,
                normalized_text=interp.normalized_text if interp else "",
                method=m.method,
                membership_confidence=m.membership_confidence,
                status=m.status,
                stance_in_context=stance,
            )
        )
    return ClusterView(
        cluster_id=cluster.cluster_id,
        clustering_method=cluster.clustering_method,
        threshold_version=cluster.threshold_version,
        members=members,
        conflicting_stances=len(stances - {"neutral", "unclear"}) > 1,
    )


def clusters_for_claim(session: Session, claim_id: str) -> list[ClusterView]:
    """Clusters an interpretation belongs to — makes clustering reviewable (US-3.5)."""
    interp = session.get(models.ClaimInterpretation, claim_id)
    if interp is None:
        raise NotFound(f"claim {claim_id} not found")
    cluster_ids = list(
        dict.fromkeys(
            session.scalars(
                select(models.ClusterMembership.cluster_id).where(
                    models.ClusterMembership.interpretation_id == claim_id
                )
            )
        )
    )
    return [get_cluster(session, cid) for cid in cluster_ids]


def remove_cluster_member(
    session: Session, cluster_id: str, interpretation_id: str, actor: Principal
) -> ClusterView:
    membership = session.scalar(
        select(models.ClusterMembership).where(
            models.ClusterMembership.cluster_id == cluster_id,
            models.ClusterMembership.interpretation_id == interpretation_id,
            models.ClusterMembership.status == MembershipStatus.active,
        )
    )
    if membership is None:
        raise NotFound("active membership not found")
    membership.status = MembershipStatus.removed
    membership.removed_by = actor.user_id
    membership.removed_at = datetime.now(timezone.utc)
    session.commit()
    return get_cluster(session, cluster_id)
def _dominant_stance(
    session: Session, interpretation_id: str
) -> RelationStance | None:
    interp = session.get(models.ClaimInterpretation, interpretation_id)
    if interp is None:
        return None
    assertion = session.scalar(
        select(models.RelationAssertion).where(
            models.RelationAssertion.citing_occurrence_id == interp.claim_occurrence_id
        )
    )
    return assertion.stance if assertion else None


def _human_run(session: Session) -> models.ExtractionRun:
    """A sentinel run row so human-authored occurrences still satisfy provenance FKs."""
    run = session.scalar(
        select(models.ExtractionRun).where(models.ExtractionRun.model == "human")
    )
    if run is not None:
        return run
    run = models.ExtractionRun(
        run_id=new_id("ExtractionRun"),
        model="human",
        provider="human",
        model_version="n/a",
    )
    session.add(run)
    session.flush()
    return run
