"""Collections service (scite-parity WP4, F5).

User-owned curated sets of works with batch DOI/PMID intake. This is additive and
non-mutating with respect to scientific assertions: it only records membership rows
and, when needed, registers metadata stubs through the existing ingest job path.
"""

from __future__ import annotations

from datetime import datetime
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..auth import NotAuthorized
from ..ids import new_id
from ..schemas import (
    CollectionAddMembersRequest,
    CollectionAddMembersResult,
    CollectionCreate,
    CollectionDetailView,
    CollectionMemberView,
    CitationTallies,
    CollectionUpdate,
    CollectionView,
    PaperSubmission,
)
from . import citation_stats, jobs
from .projection import NotFound

_DOI_LIKE = re.compile(r"10\.\d{4,9}/\S+", flags=re.IGNORECASE)


def _member_view(
    member: models.CollectionMembership,
    work: models.PaperWork,
    *,
    include_tallies: bool,
    session: Session,
) -> CollectionMemberView:
    tallies = None
    if include_tallies:
        try:
            tallies = citation_stats.citation_stats_for_work(session, work.work_id).tallies
        except KeyError:
            tallies = None
    return CollectionMemberView(
        collection_membership_id=member.collection_membership_id,
        work_id=work.work_id,
        title=work.title,
        doi=work.doi,
        pmid=work.pmid,
        year=work.year,
        added_at=member.added_at,
        citation_tallies=tallies,
    )


def _collection_view(session: Session, collection: models.Collection) -> CollectionView:
    member_count = session.query(models.CollectionMembership).filter(
        models.CollectionMembership.collection_id == collection.collection_id
    ).count()
    return CollectionView(
        collection_id=collection.collection_id,
        owner_id=collection.owner_id,
        name=collection.name,
        description=collection.description,
        member_count=member_count,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
    )


def _load_owned_collection(
    session: Session, collection_id: str, *, owner_id: str
) -> models.Collection:
    collection = session.get(models.Collection, collection_id)
    if collection is None:
        raise NotFound(f"collection {collection_id} not found")
    if collection.owner_id != owner_id:
        raise NotAuthorized("collection is owned by a different user")
    return collection


def list_collections(session: Session, *, owner_id: str) -> list[CollectionView]:
    rows = list(
        session.scalars(
            select(models.Collection)
            .where(models.Collection.owner_id == owner_id)
            .order_by(models.Collection.updated_at.desc())
        )
    )
    return [_collection_view(session, row) for row in rows]


def create_collection(
    session: Session, payload: CollectionCreate, *, owner_id: str
) -> CollectionView:
    now = datetime.now().astimezone()
    collection = models.Collection(
        collection_id=new_id("Collection"),
        owner_id=owner_id,
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        created_at=now,
        updated_at=now,
    )
    session.add(collection)
    session.commit()
    return _collection_view(session, collection)


def get_collection(
    session: Session,
    collection_id: str,
    *,
    owner_id: str,
    include_member_tallies: bool = False,
    member_sort: str = "added_desc",
) -> CollectionDetailView:
    collection = _load_owned_collection(session, collection_id, owner_id=owner_id)
    memberships = list(
        session.scalars(
            select(models.CollectionMembership)
            .where(models.CollectionMembership.collection_id == collection.collection_id)
            .order_by(models.CollectionMembership.added_at.desc())
        )
    )
    work_ids = [m.work_id for m in memberships]
    works = {
        w.work_id: w
        for w in session.scalars(select(models.PaperWork).where(models.PaperWork.work_id.in_(work_ids)))
    }
    members = [
        _member_view(
            m,
            works[m.work_id],
            include_tallies=include_member_tallies,
            session=session,
        )
        for m in memberships
        if m.work_id in works
    ]

    aggregate_tallies = _aggregate_tallies(members) if include_member_tallies else None
    members = _sort_members(members, sort_key=member_sort)

    return CollectionDetailView(
        **_collection_view(session, collection).model_dump(),
        aggregate_citation_tallies=aggregate_tallies,
        members=members,
    )


def update_collection(
    session: Session,
    collection_id: str,
    payload: CollectionUpdate,
    *,
    owner_id: str,
) -> CollectionView:
    collection = _load_owned_collection(session, collection_id, owner_id=owner_id)
    if payload.name is not None:
        collection.name = payload.name.strip()
    if payload.description is not None:
        collection.description = payload.description.strip() or None
    session.commit()
    return _collection_view(session, collection)


def delete_collection(session: Session, collection_id: str, *, owner_id: str) -> None:
    collection = _load_owned_collection(session, collection_id, owner_id=owner_id)
    session.delete(collection)
    session.commit()


def _resolve_existing_work(
    session: Session, *, work_id: str | None = None, doi: str | None = None, pmid: str | None = None
) -> models.PaperWork | None:
    if work_id:
        work = session.get(models.PaperWork, work_id)
        if work is not None:
            return work
    if doi:
        work = session.scalar(select(models.PaperWork).where(models.PaperWork.doi == doi))
        if work is not None:
            return work
    if pmid:
        work = session.scalar(select(models.PaperWork).where(models.PaperWork.pmid == pmid))
        if work is not None:
            return work
    return None


def _identifiers_from_csv(text: str) -> tuple[list[str], list[str]]:
    dois: list[str] = []
    pmids: list[str] = []
    for raw in re.split(r"[\s,;]+", text):
        token = raw.strip()
        if not token:
            continue
        if _DOI_LIKE.fullmatch(token):
            dois.append(token)
        elif token.isdigit():
            pmids.append(token)
    return dois, pmids


def add_members(
    session: Session,
    collection_id: str,
    payload: CollectionAddMembersRequest,
    *,
    owner_id: str,
) -> CollectionAddMembersResult:
    collection = _load_owned_collection(session, collection_id, owner_id=owner_id)

    csv_dois: list[str] = []
    csv_pmids: list[str] = []
    if payload.csv_text:
        csv_dois, csv_pmids = _identifiers_from_csv(payload.csv_text)

    work_ids = list(dict.fromkeys(payload.work_ids))
    dois = list(dict.fromkeys([*payload.dois, *csv_dois]))
    pmids = list(dict.fromkeys([*payload.pmids, *csv_pmids]))

    added_members: list[CollectionMemberView] = []
    skipped: list[str] = []
    created_stub_work_ids: list[str] = []

    for work_id in work_ids:
        work = _resolve_existing_work(session, work_id=work_id)
        if work is None:
            skipped.append(work_id)
            continue
        if _membership_exists(session, collection.collection_id, work.work_id):
            continue
        member = _create_membership(
            session, collection_id=collection.collection_id, work_id=work.work_id, added_by=owner_id
        )
        added_members.append(
            _member_view(member, work, include_tallies=False, session=session)
        )

    for doi in dois:
        work = _resolve_existing_work(session, doi=doi)
        if work is None:
            job = jobs.submit_ingest(
                session,
                PaperSubmission(doi=doi),
                owner_id=owner_id,
            )
            if not job.paper_work_id:
                skipped.append(doi)
                continue
            work = session.get(models.PaperWork, job.paper_work_id)
            if work is not None:
                created_stub_work_ids.append(work.work_id)
        if work is None:
            skipped.append(doi)
            continue
        if _membership_exists(session, collection.collection_id, work.work_id):
            continue
        member = _create_membership(
            session, collection_id=collection.collection_id, work_id=work.work_id, added_by=owner_id
        )
        added_members.append(
            _member_view(member, work, include_tallies=False, session=session)
        )

    for pmid in pmids:
        work = _resolve_existing_work(session, pmid=pmid)
        if work is None:
            job = jobs.submit_ingest(
                session,
                PaperSubmission(pmid=pmid),
                owner_id=owner_id,
            )
            if not job.paper_work_id:
                skipped.append(pmid)
                continue
            work = session.get(models.PaperWork, job.paper_work_id)
            if work is not None:
                created_stub_work_ids.append(work.work_id)
        if work is None:
            skipped.append(pmid)
            continue
        if _membership_exists(session, collection.collection_id, work.work_id):
            continue
        member = _create_membership(
            session, collection_id=collection.collection_id, work_id=work.work_id, added_by=owner_id
        )
        added_members.append(
            _member_view(member, work, include_tallies=False, session=session)
        )

    collection.updated_at = datetime.now().astimezone()
    session.commit()

    return CollectionAddMembersResult(
        collection_id=collection.collection_id,
        added_count=len(added_members),
        skipped_identifiers=skipped,
        created_stub_work_ids=list(dict.fromkeys(created_stub_work_ids)),
        members=added_members,
    )


def remove_member(
    session: Session, collection_id: str, work_id: str, *, owner_id: str
) -> None:
    collection = _load_owned_collection(session, collection_id, owner_id=owner_id)
    member = session.scalar(
        select(models.CollectionMembership).where(
            models.CollectionMembership.collection_id == collection.collection_id,
            models.CollectionMembership.work_id == work_id,
        )
    )
    if member is None:
        raise NotFound("collection member not found")
    session.delete(member)
    collection.updated_at = datetime.now().astimezone()
    session.commit()


def _membership_exists(session: Session, collection_id: str, work_id: str) -> bool:
    return (
        session.scalar(
            select(models.CollectionMembership.collection_membership_id).where(
                models.CollectionMembership.collection_id == collection_id,
                models.CollectionMembership.work_id == work_id,
            )
        )
        is not None
    )


def _create_membership(
    session: Session, *, collection_id: str, work_id: str, added_by: str
) -> models.CollectionMembership:
    member = models.CollectionMembership(
        collection_membership_id=new_id("CollectionMembership"),
        collection_id=collection_id,
        work_id=work_id,
        added_by=added_by,
    )
    session.add(member)
    session.flush()
    return member


def _aggregate_tallies(members: list[CollectionMemberView]) -> CitationTallies:
    total = 0
    abstained = 0
    by_stance: dict[str, int] = {}
    by_function: dict[str, int] = {}
    by_resolution: dict[str, int] = {}
    by_section: dict[str, int] = {}

    for member in members:
        tallies = member.citation_tallies
        if tallies is None:
            continue
        total += tallies.total
        abstained += tallies.abstained
        for key, value in tallies.by_stance.items():
            by_stance[key] = by_stance.get(key, 0) + value
        for key, value in tallies.by_function.items():
            by_function[key] = by_function.get(key, 0) + value
        for key, value in tallies.by_resolution.items():
            by_resolution[key] = by_resolution.get(key, 0) + value
        for key, value in tallies.by_section.items():
            by_section[key] = by_section.get(key, 0) + value

    return CitationTallies(
        total=total,
        by_stance=by_stance,
        by_function=by_function,
        by_resolution=by_resolution,
        by_section=by_section,
        abstained=abstained,
    )


def _sort_members(
    members: list[CollectionMemberView], *, sort_key: str
) -> list[CollectionMemberView]:
    if sort_key == "added_asc":
        return sorted(members, key=lambda member: member.added_at)
    if sort_key == "support_desc":
        return sorted(
            members,
            key=lambda member: (
                (member.citation_tallies.by_stance.get("support", 0)
                 if member.citation_tallies
                 else 0),
                member.added_at,
            ),
            reverse=True,
        )
    if sort_key == "contradict_desc":
        return sorted(
            members,
            key=lambda member: (
                (member.citation_tallies.by_stance.get("contradict", 0)
                 if member.citation_tallies
                 else 0),
                member.added_at,
            ),
            reverse=True,
        )
    return sorted(members, key=lambda member: member.added_at, reverse=True)
