"""Collections API (scite-parity WP4, F5).

Collections are user-owned curated sets of works. Writes require auth (+ CSRF for
cookie sessions). Reads are scoped to the caller's own collections.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ...auth import NotAuthorized, Principal
from ...schemas import (
    CollectionAddMembersRequest,
    CollectionAddMembersResult,
    CollectionCreate,
    CollectionDetailView,
    CollectionUpdate,
    CollectionView,
)
from ...services import collections
from ...services.projection import NotFound
from ..deps import db_session
from ..security import require_user

router = APIRouter()


@router.post("/collections", response_model=CollectionView, status_code=status.HTTP_201_CREATED)
def create_collection(
    payload: CollectionCreate,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> CollectionView:
    return collections.create_collection(session, payload, owner_id=principal.user_id)


@router.get("/collections", response_model=list[CollectionView])
def list_collections(
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> list[CollectionView]:
    return collections.list_collections(session, owner_id=principal.user_id)


@router.get("/collections/{collection_id}", response_model=CollectionDetailView)
def get_collection(
    collection_id: str,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> CollectionDetailView:
    try:
        return collections.get_collection(session, collection_id, owner_id=principal.user_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotAuthorized as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.patch("/collections/{collection_id}", response_model=CollectionView)
def update_collection(
    collection_id: str,
    payload: CollectionUpdate,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> CollectionView:
    try:
        return collections.update_collection(
            session, collection_id, payload, owner_id=principal.user_id
        )
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotAuthorized as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.delete("/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(
    collection_id: str,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> Response:
    try:
        collections.delete_collection(session, collection_id, owner_id=principal.user_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotAuthorized as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/collections/{collection_id}/members",
    response_model=CollectionAddMembersResult,
)
def add_members(
    collection_id: str,
    payload: CollectionAddMembersRequest,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> CollectionAddMembersResult:
    try:
        return collections.add_members(
            session, collection_id, payload, owner_id=principal.user_id
        )
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotAuthorized as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.delete(
    "/collections/{collection_id}/members/{work_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_member(
    collection_id: str,
    work_id: str,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> Response:
    try:
        collections.remove_member(
            session, collection_id, work_id, owner_id=principal.user_id
        )
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotAuthorized as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
