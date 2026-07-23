"""Saved maps API (litmaps-parity WP-L2).

Maps are user-owned, persisted citation-map seed sets plus layout config. Writes
require auth (+ CSRF for cookie sessions). Reads are scoped to the caller's own
maps; a map owned by another user is indistinguishable from a missing one (404).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ...auth import Principal
from ...schemas import (
    AlertRunResult,
    GraphView,
    MapAddMembersRequest,
    MapCreate,
    MapDetailView,
    MapMemberUpdate,
    MapMemberView,
    MapShareView,
    MapUpdate,
    MapView,
    MapWatchRequest,
    SharedMapView,
)
from ...services import alerts, maps
from ...services.projection import NotFound
from ..deps import db_session
from ..security import require_user

router = APIRouter()


@router.post("/maps", response_model=MapDetailView, status_code=status.HTTP_201_CREATED)
def create_map(
    payload: MapCreate,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> MapDetailView:
    return maps.create_map(session, payload, owner_id=principal.user_id)


@router.get("/maps", response_model=list[MapView])
def list_maps(
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> list[MapView]:
    return maps.list_maps(session, owner_id=principal.user_id)


@router.get("/maps/{map_id}", response_model=MapDetailView)
def get_map(
    map_id: str,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> MapDetailView:
    try:
        return maps.get_map(session, map_id, owner_id=principal.user_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/maps/{map_id}/graph", response_model=GraphView)
def map_graph(
    map_id: str,
    include_authors: bool = Query(False),
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> GraphView:
    try:
        return maps.map_graph(
            session, map_id, owner_id=principal.user_id, include_authors=include_authors
        )
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/maps/{map_id}", response_model=MapView)
def update_map(
    map_id: str,
    payload: MapUpdate,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> MapView:
    try:
        return maps.update_map(session, map_id, payload, owner_id=principal.user_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/maps/{map_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_map(
    map_id: str,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> Response:
    try:
        maps.delete_map(session, map_id, owner_id=principal.user_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/maps/{map_id}/members", response_model=MapDetailView)
def add_members(
    map_id: str,
    payload: MapAddMembersRequest,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> MapDetailView:
    try:
        return maps.add_members(session, map_id, payload, owner_id=principal.user_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete(
    "/maps/{map_id}/members/{work_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_member(
    map_id: str,
    work_id: str,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> Response:
    try:
        maps.remove_member(session, map_id, work_id, owner_id=principal.user_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/maps/{map_id}/members/{work_id}", response_model=MapMemberView)
def update_member(
    map_id: str,
    work_id: str,
    payload: MapMemberUpdate,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> MapMemberView:
    try:
        return maps.update_member(
            session, map_id, work_id, payload, owner_id=principal.user_id
        )
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/maps/{map_id}/share", response_model=MapShareView)
def share_map(
    map_id: str,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> MapShareView:
    try:
        return maps.share_map(session, map_id, owner_id=principal.user_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/maps/{map_id}/share", status_code=status.HTTP_204_NO_CONTENT)
def revoke_share(
    map_id: str,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> Response:
    try:
        maps.revoke_share(session, map_id, owner_id=principal.user_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/maps/{map_id}/watch", response_model=MapView)
def set_watch(
    map_id: str,
    payload: MapWatchRequest,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> MapView:
    try:
        return maps.set_watch(
            session, map_id, owner_id=principal.user_id, watch=payload.watch
        )
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/maps/{map_id}/monitor", response_model=AlertRunResult)
def run_monitor(
    map_id: str,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> AlertRunResult:
    """Re-run seed discovery for the map and surface newly connected papers as alerts
    (litmaps-parity WP-L5). Performs a Semantic Scholar read, so it requires auth."""
    try:
        return alerts.run_map(session, map_id, owner_id=principal.user_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------------
# Public read-only shared-map routes (litmaps-parity WP-L4). The token is the sole
# capability; these require NO auth and never expose owner identity.
# ---------------------------------------------------------------------------------


@router.get("/shared-maps/{token}", response_model=SharedMapView)
def shared_map(
    token: str,
    session: Session = Depends(db_session),
) -> SharedMapView:
    try:
        return maps.shared_map(session, token)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/shared-maps/{token}/graph", response_model=GraphView)
def shared_map_graph(
    token: str,
    include_authors: bool = Query(False),
    session: Session = Depends(db_session),
) -> GraphView:
    try:
        return maps.shared_map_graph(
            session, token, include_authors=include_authors
        )
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
