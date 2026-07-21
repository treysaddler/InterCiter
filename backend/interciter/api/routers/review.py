"""Clusters and review decisions."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from ...schemas import ClusterView, ReviewDecisionCreate, ReviewDecisionView
from ...services import review
from ...services.projection import NotFound
from ..deps import db_session

router = APIRouter()


@router.get("/clusters/{cluster_id}", response_model=ClusterView)
def get_cluster(cluster_id: str, session: Session = Depends(db_session)) -> ClusterView:
    try:
        return review.get_cluster(session, cluster_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/clusters/{cluster_id}/members/{interpretation_id}", response_model=ClusterView)
def remove_member(
    cluster_id: str,
    interpretation_id: str,
    removed_by: str = Body(..., embed=True),
    session: Session = Depends(db_session),
) -> ClusterView:
    """Soft-remove a bad membership (status: removed). Nothing is destroyed."""
    try:
        return review.remove_cluster_member(
            session, cluster_id, interpretation_id, removed_by
        )
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/review-decisions", response_model=ReviewDecisionView, status_code=201)
def create_review_decision(
    payload: ReviewDecisionCreate, session: Session = Depends(db_session)
) -> ReviewDecisionView:
    return review.create_review_decision(session, payload)
