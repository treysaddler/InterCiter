"""Collections API (scite-parity WP4, F5).

Collections are user-owned curated sets of works. Writes require auth (+ CSRF for
cookie sessions). Reads are scoped to the caller's own collections; a collection
owned by another user is indistinguishable from a missing one (404).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ...auth import Principal
from ...schemas import (
    CollectionAddMembersRequest,
    CollectionAddMembersResult,
    CollectionBulkRemoveRequest,
    CollectionBulkRemoveResult,
    CollectionCitationDelta,
    CollectionCreate,
    CollectionDetailView,
    CollectionImportRequest,
    CollectionImportResult,
    CollectionUpdate,
    CollectionView,
    CollectionWatchRequest,
    GraphView,
)
from ...services import collections
from ...services.collections import BatchLimitError, MemberSort
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
    include_member_tallies: bool = Query(
        False,
        description="Include per-member citation tallies from /citation-stats.",
    ),
    member_sort: MemberSort = Query(
        "added_desc",
        description=(
            "Member order: added_desc (default), added_asc, support_desc, "
            "contradict_desc."
        ),
    ),
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> CollectionDetailView:
    try:
        return collections.get_collection(
            session,
            collection_id,
            owner_id=principal.user_id,
            include_member_tallies=include_member_tallies,
            member_sort=member_sort,
        )
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/collections/{collection_id}/graph", response_model=GraphView)
def collection_graph(
    collection_id: str,
    include_authors: bool = Query(False),
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> GraphView:
    """Citation graph over the collection's members (UX-3 cohort-by-reference)."""
    try:
        return collections.collection_graph(
            session,
            collection_id,
            owner_id=principal.user_id,
            include_authors=include_authors,
        )
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
    except BatchLimitError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/collections/{collection_id}/import",
    response_model=CollectionImportResult,
)
def import_references(
    collection_id: str,
    payload: CollectionImportRequest,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> CollectionImportResult:
    try:
        return collections.import_references(
            session,
            collection_id,
            text=payload.text,
            fmt=payload.format,
            owner_id=principal.user_id,
        )
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BatchLimitError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/collections/{collection_id}/members/bulk-delete",
    response_model=CollectionBulkRemoveResult,
)
def bulk_remove_members(
    collection_id: str,
    payload: CollectionBulkRemoveRequest,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> CollectionBulkRemoveResult:
    try:
        return collections.bulk_remove_members(
            session, collection_id, payload.work_ids, owner_id=principal.user_id
        )
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/collections/{collection_id}/watch", response_model=CollectionView)
def set_watch(
    collection_id: str,
    payload: CollectionWatchRequest,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> CollectionView:
    try:
        return collections.set_watch(
            session, collection_id, owner_id=principal.user_id, watch=payload.watch
        )
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/collections/{collection_id}/new-citations",
    response_model=CollectionCitationDelta,
)
def new_citations(
    collection_id: str,
    session: Session = Depends(db_session),
    principal: Principal = Depends(require_user),
) -> CollectionCitationDelta:
    try:
        return collections.citation_delta(
            session, collection_id, owner_id=principal.user_id
        )
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

