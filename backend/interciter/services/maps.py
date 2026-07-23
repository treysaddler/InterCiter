"""Saved-maps service (litmaps-parity WP-L2).

A saved map = a named seed set of works + the visualization layout config used to
render it (+ optional per-member annotations, used by WP-L3c). Additive and
non-mutating with respect to the scientific record: it only stores membership rows
and UI state. Reads are owner-scoped; a map owned by another user is reported as
missing (404) so ids never leak across accounts.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models
from ..ids import new_id
from ..schemas import (
    GraphView,
    MapAddMembersRequest,
    MapCreate,
    MapDetailView,
    MapMemberUpdate,
    MapMemberView,
    MapUpdate,
    MapView,
)
from . import graph
from .projection import NotFound


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _member_view(member: models.MapMembership, work: models.PaperWork) -> MapMemberView:
    return MapMemberView(
        map_membership_id=member.map_membership_id,
        work_id=work.work_id,
        title=work.title,
        doi=work.doi,
        pmid=work.pmid,
        year=work.year,
        note=member.member_note,
        position=member.member_position,
        added_at=member.added_at,
    )


def _map_view(
    session: Session, saved_map: models.Map, *, member_count: int | None = None
) -> MapView:
    if member_count is None:
        member_count = (
            session.query(models.MapMembership)
            .filter(models.MapMembership.map_id == saved_map.map_id)
            .count()
        )
    return MapView(
        map_id=saved_map.map_id,
        owner_id=saved_map.owner_id,
        name=saved_map.name,
        description=saved_map.description,
        layout_config=saved_map.layout_config or {},
        member_count=member_count,
        created_at=saved_map.created_at,
        updated_at=saved_map.updated_at,
    )


def _load_owned_map(session: Session, map_id: str, *, owner_id: str) -> models.Map:
    saved_map = session.get(models.Map, map_id)
    if saved_map is None or saved_map.owner_id != owner_id:
        raise NotFound(f"map {map_id} not found")
    return saved_map


def _existing_work_ids(session: Session, work_ids: list[str]) -> list[str]:
    """The subset of work_ids that exist, de-duplicated and order-preserving."""
    unique = list(dict.fromkeys(work_ids))
    if not unique:
        return []
    present = set(
        session.scalars(
            select(models.PaperWork.work_id).where(
                models.PaperWork.work_id.in_(unique)
            )
        )
    )
    return [wid for wid in unique if wid in present]


def _add_memberships(
    session: Session, saved_map: models.Map, work_ids: list[str], *, added_by: str
) -> int:
    """Create memberships for existing, not-yet-member works. Returns count added."""
    existing_members = set(
        session.scalars(
            select(models.MapMembership.work_id).where(
                models.MapMembership.map_id == saved_map.map_id
            )
        )
    )
    added = 0
    for wid in _existing_work_ids(session, work_ids):
        if wid in existing_members:
            continue
        session.add(
            models.MapMembership(
                map_membership_id=new_id("MapMembership"),
                map_id=saved_map.map_id,
                work_id=wid,
                added_by=added_by,
            )
        )
        existing_members.add(wid)
        added += 1
    return added


def list_maps(session: Session, *, owner_id: str) -> list[MapView]:
    rows = list(
        session.scalars(
            select(models.Map)
            .where(models.Map.owner_id == owner_id)
            .order_by(models.Map.updated_at.desc())
        )
    )
    counts = dict(
        session.execute(
            select(models.MapMembership.map_id, func.count())
            .where(models.MapMembership.map_id.in_([row.map_id for row in rows]))
            .group_by(models.MapMembership.map_id)
        ).all()
    )
    return [
        _map_view(session, row, member_count=counts.get(row.map_id, 0)) for row in rows
    ]


def create_map(session: Session, payload: MapCreate, *, owner_id: str) -> MapDetailView:
    now = _utcnow()
    saved_map = models.Map(
        map_id=new_id("Map"),
        owner_id=owner_id,
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        layout_config=payload.layout_config or {},
        created_at=now,
        updated_at=now,
    )
    session.add(saved_map)
    session.flush()
    _add_memberships(session, saved_map, payload.work_ids, added_by=owner_id)
    session.commit()
    return get_map(session, saved_map.map_id, owner_id=owner_id)


def get_map(session: Session, map_id: str, *, owner_id: str) -> MapDetailView:
    saved_map = _load_owned_map(session, map_id, owner_id=owner_id)
    memberships = list(
        session.scalars(
            select(models.MapMembership)
            .where(models.MapMembership.map_id == saved_map.map_id)
            .order_by(models.MapMembership.added_at.desc())
        )
    )
    work_ids = [m.work_id for m in memberships]
    works = {
        w.work_id: w
        for w in session.scalars(
            select(models.PaperWork).where(models.PaperWork.work_id.in_(work_ids))
        )
    }
    members = [
        _member_view(m, works[m.work_id]) for m in memberships if m.work_id in works
    ]
    return MapDetailView(
        **_map_view(session, saved_map, member_count=len(memberships)).model_dump(),
        members=members,
    )


def update_map(
    session: Session, map_id: str, payload: MapUpdate, *, owner_id: str
) -> MapView:
    saved_map = _load_owned_map(session, map_id, owner_id=owner_id)
    provided = payload.model_fields_set
    if "name" in provided and payload.name is not None:
        saved_map.name = payload.name.strip()
    if "description" in provided:
        saved_map.description = (
            payload.description.strip() or None if payload.description else None
        )
    if "layout_config" in provided and payload.layout_config is not None:
        saved_map.layout_config = payload.layout_config
    session.commit()
    return _map_view(session, saved_map)


def delete_map(session: Session, map_id: str, *, owner_id: str) -> None:
    saved_map = _load_owned_map(session, map_id, owner_id=owner_id)
    session.delete(saved_map)
    session.commit()


def add_members(
    session: Session, map_id: str, payload: MapAddMembersRequest, *, owner_id: str
) -> MapDetailView:
    saved_map = _load_owned_map(session, map_id, owner_id=owner_id)
    added = _add_memberships(session, saved_map, payload.work_ids, added_by=owner_id)
    if added:
        saved_map.updated_at = _utcnow()
    session.commit()
    return get_map(session, map_id, owner_id=owner_id)


def remove_member(
    session: Session, map_id: str, work_id: str, *, owner_id: str
) -> None:
    saved_map = _load_owned_map(session, map_id, owner_id=owner_id)
    member = session.scalar(
        select(models.MapMembership).where(
            models.MapMembership.map_id == saved_map.map_id,
            models.MapMembership.work_id == work_id,
        )
    )
    if member is None:
        raise NotFound("map member not found")
    session.delete(member)
    saved_map.updated_at = _utcnow()
    session.commit()


def update_member(
    session: Session,
    map_id: str,
    work_id: str,
    payload: MapMemberUpdate,
    *,
    owner_id: str,
) -> MapMemberView:
    saved_map = _load_owned_map(session, map_id, owner_id=owner_id)
    member = session.scalar(
        select(models.MapMembership).where(
            models.MapMembership.map_id == saved_map.map_id,
            models.MapMembership.work_id == work_id,
        )
    )
    if member is None:
        raise NotFound("map member not found")
    provided = payload.model_fields_set
    if "note" in provided:
        note = payload.note.strip() if payload.note else None
        member.member_note = note or None
    if "position" in provided:
        member.member_position = payload.position
    saved_map.updated_at = _utcnow()
    session.commit()
    work = session.get(models.PaperWork, work_id)
    assert work is not None  # membership FK guarantees the work exists
    return _member_view(member, work)


def map_graph(
    session: Session, map_id: str, *, owner_id: str, include_authors: bool = False
) -> GraphView:
    """Render the map's seed set as a citation graph (owner-scoped)."""
    saved_map = _load_owned_map(session, map_id, owner_id=owner_id)
    work_ids = list(
        session.scalars(
            select(models.MapMembership.work_id).where(
                models.MapMembership.map_id == saved_map.map_id
            )
        )
    )
    return graph.graph_for_works(session, work_ids, include_authors=include_authors)
