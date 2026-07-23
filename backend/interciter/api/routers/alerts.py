"""Monitoring API — saved searches + alerts (scite-parity WP8, F3/F5).

Saved searches and alerts are user-owned; every endpoint is scoped to the caller's own
resources (another user's records are indistinguishable from missing). Writes require
auth (+ CSRF for cookie sessions).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ...auth import Principal
from ...schemas import (
    AlertRunResult,
    AlertView,
    SavedSearchCreate,
    SavedSearchUpdate,
    SavedSearchView,
)
from ...services import alerts
from ...services.projection import NotFound
from ..deps import db_session
from ..security import require_user

router = APIRouter()


@router.post(
    "/saved-searches",
    response_model=SavedSearchView,
    status_code=status.HTTP_201_CREATED,
)
def create_saved_search(
    payload: SavedSearchCreate,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> SavedSearchView:
    return alerts.create_saved_search(session, payload, owner_id=principal.user_id)


@router.get("/saved-searches", response_model=list[SavedSearchView])
def list_saved_searches(
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> list[SavedSearchView]:
    return alerts.list_saved_searches(session, owner_id=principal.user_id)


@router.get("/saved-searches/{saved_search_id}", response_model=SavedSearchView)
def get_saved_search(
    saved_search_id: str,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> SavedSearchView:
    try:
        return alerts.get_saved_search(session, saved_search_id, owner_id=principal.user_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/saved-searches/{saved_search_id}", response_model=SavedSearchView)
def update_saved_search(
    saved_search_id: str,
    payload: SavedSearchUpdate,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> SavedSearchView:
    try:
        return alerts.update_saved_search(
            session, saved_search_id, payload, owner_id=principal.user_id
        )
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete(
    "/saved-searches/{saved_search_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_saved_search(
    saved_search_id: str,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> Response:
    try:
        alerts.delete_saved_search(session, saved_search_id, owner_id=principal.user_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/saved-searches/{saved_search_id}/run", response_model=AlertRunResult)
def run_saved_search(
    saved_search_id: str,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> AlertRunResult:
    try:
        return alerts.run_saved_search(session, saved_search_id, owner_id=principal.user_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/alerts/run", response_model=AlertRunResult)
def run_alerts(
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> AlertRunResult:
    return alerts.run_all(session, owner_id=principal.user_id)


@router.get("/alerts", response_model=list[AlertView])
def list_alerts(
    unread_only: bool = Query(False, description="Only return unread alerts."),
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> list[AlertView]:
    return alerts.list_alerts(
        session, owner_id=principal.user_id, unread_only=unread_only
    )


@router.post("/alerts/read-all")
def mark_all_read(
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> dict[str, int]:
    return {"marked_read": alerts.mark_all_read(session, owner_id=principal.user_id)}


@router.post("/alerts/{alert_id}/read", response_model=AlertView)
def mark_read(
    alert_id: str,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> AlertView:
    try:
        return alerts.mark_read(session, alert_id, owner_id=principal.user_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
