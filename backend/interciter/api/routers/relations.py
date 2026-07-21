"""Relation assertions and one-hop traversal."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ... import models
from ...enums import AssertionStatus, RelationResolution, RelationStance
from ...schemas import OneHopTrace, RelationAssertionView
from ...services import projection
from ...services.projection import NotFound, relation_view
from ..deps import db_session

router = APIRouter()


@router.get("/relation-assertions/{assertion_id}", response_model=RelationAssertionView)
def get_relation_assertion(
    assertion_id: str, session: Session = Depends(db_session)
) -> RelationAssertionView:
    assertion = session.get(models.RelationAssertion, assertion_id)
    if assertion is None:
        raise HTTPException(status_code=404, detail="relation assertion not found")
    return relation_view(assertion)


@router.get(
    "/claims/{claim_id}/relationships", response_model=list[RelationAssertionView]
)
def get_relationships(
    claim_id: str,
    stance: RelationStance | None = None,
    resolution: RelationResolution | None = None,
    status: AssertionStatus | None = None,
    session: Session = Depends(db_session),
) -> list[RelationAssertionView]:
    try:
        return projection.relationships_for_claim(
            session, claim_id, stance=stance, resolution=resolution, status=status
        )
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/claims/{claim_id}/trace", response_model=OneHopTrace)
def trace_one_hop(
    claim_id: str, session: Session = Depends(db_session)
) -> OneHopTrace:
    """Trace a claim exactly one hop to its cited antecedents.

    Deep, bounded traversal (`/v1/traces` with max_depth/max_nodes) is phase 2.
    """
    try:
        return projection.one_hop_trace(session, claim_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
