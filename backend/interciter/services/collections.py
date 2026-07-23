"""Collections service (scite-parity WP4, F5).

User-owned curated sets of works with batch DOI/PMID intake. This is additive and
non-mutating with respect to scientific assertions: it only records membership rows
and, when needed, registers metadata stubs through the existing ingest job path.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models
from ..ids import new_id
from ..schemas import (
    CollectionAddMembersRequest,
    CollectionAddMembersResult,
    CollectionBulkRemoveResult,
    CollectionCitationDelta,
    CollectionCreate,
    CollectionDetailView,
    CollectionMemberDelta,
    CollectionMemberView,
    CitationTallies,
    CollectionUpdate,
    CollectionView,
    PaperSubmission,
)
from . import citation_stats, jobs
from .projection import NotFound

MemberSort = Literal["added_desc", "added_asc", "support_desc", "contradict_desc"]

# Hard cap on identifiers per add-members request: each unknown DOI/PMID runs a
# synchronous ingest job, so an unbounded batch would stall the request.
MAX_BATCH_IDENTIFIERS = 500

_DOI_LIKE = re.compile(r"10\.\d{4,9}/\S+", flags=re.IGNORECASE)
# Accepted wrappers around a DOI; matched case-insensitively against the token.
_DOI_PREFIXES = (
    "doi:",
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
)
_PMID_PREFIXED = re.compile(r"pmid:?\s*(\d{1,8})", flags=re.IGNORECASE)


class BatchLimitError(ValueError):
    """Raised when an add-members batch exceeds MAX_BATCH_IDENTIFIERS."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_doi(token: str) -> str | None:
    """Canonical lowercase DOI from a raw token, or None if not DOI-shaped.

    Accepts doi.org / dx.doi.org URL forms and a ``doi:`` prefix. Trailing
    list/prose punctuation is stripped (it is never part of a real DOI suffix,
    while embedded semicolons/commas — e.g. legacy Wiley SICI DOIs — are kept).
    DOIs are case-insensitive by spec, so the lowercase form is canonical.
    """
    t = token.strip()
    lower = t.lower()
    for prefix in _DOI_PREFIXES:
        if lower.startswith(prefix):
            t = t[len(prefix):]
            break
    t = t.rstrip(".,;:")
    if _DOI_LIKE.fullmatch(t):
        return t.lower()
    return None


def _pmid_from_token(token: str) -> str | None:
    """PMID from a raw token, or None.

    A ``pmid:``-prefixed number is always accepted. A bare 1-8 digit number is
    accepted unless it is a 4-digit value in the publication-year range — pasted
    CSV rows routinely carry year columns, and importing those as PMIDs would
    register garbage metadata stubs.
    """
    if (m := _PMID_PREFIXED.fullmatch(token)) is not None:
        return m.group(1)
    if token.isdigit() and len(token) <= 8:
        if len(token) == 4 and 1500 <= int(token) <= 2099:
            return None
        return token
    return None


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
        is_retracted=work.is_retracted,
        integrity_notice=work.integrity_notice,
    )


def _collection_view(
    session: Session, collection: models.Collection, *, member_count: int | None = None
) -> CollectionView:
    if member_count is None:
        member_count = session.query(models.CollectionMembership).filter(
            models.CollectionMembership.collection_id == collection.collection_id
        ).count()
    return CollectionView(
        collection_id=collection.collection_id,
        owner_id=collection.owner_id,
        name=collection.name,
        description=collection.description,
        member_count=member_count,
        is_watched=collection.is_watched,
        watch_snapshot_at=collection.watch_snapshot_at,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
    )


def _load_owned_collection(
    session: Session, collection_id: str, *, owner_id: str
) -> models.Collection:
    collection = session.get(models.Collection, collection_id)
    # A collection owned by someone else is reported identically to a missing
    # one so collection ids don't leak across accounts.
    if collection is None or collection.owner_id != owner_id:
        raise NotFound(f"collection {collection_id} not found")
    return collection


def list_collections(session: Session, *, owner_id: str) -> list[CollectionView]:
    rows = list(
        session.scalars(
            select(models.Collection)
            .where(models.Collection.owner_id == owner_id)
            .order_by(models.Collection.updated_at.desc())
        )
    )
    counts = dict(
        session.execute(
            select(models.CollectionMembership.collection_id, func.count())
            .where(
                models.CollectionMembership.collection_id.in_(
                    [row.collection_id for row in rows]
                )
            )
            .group_by(models.CollectionMembership.collection_id)
        ).all()
    )
    return [
        _collection_view(
            session, row, member_count=counts.get(row.collection_id, 0)
        )
        for row in rows
    ]


def create_collection(
    session: Session, payload: CollectionCreate, *, owner_id: str
) -> CollectionView:
    now = _utcnow()
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
    return _collection_view(session, collection, member_count=0)


def get_collection(
    session: Session,
    collection_id: str,
    *,
    owner_id: str,
    include_member_tallies: bool = False,
    member_sort: MemberSort = "added_desc",
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
        **_collection_view(
            session, collection, member_count=len(memberships)
        ).model_dump(),
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
    provided = payload.model_fields_set
    if "name" in provided and payload.name is not None:
        collection.name = payload.name.strip()
    # An explicit null clears the description; an omitted field leaves it alone.
    if "description" in provided:
        collection.description = (
            payload.description.strip() or None if payload.description else None
        )
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
        # DOIs are case-insensitive; stored rows may predate lowercase intake.
        work = session.scalar(
            select(models.PaperWork).where(
                func.lower(models.PaperWork.doi) == doi.lower()
            )
        )
        if work is not None:
            return work
    if pmid:
        work = session.scalar(select(models.PaperWork).where(models.PaperWork.pmid == pmid))
        if work is not None:
            return work
    return None


def _identifiers_from_csv(text: str) -> tuple[list[str], list[str], list[str]]:
    """Split pasted text into (dois, pmids, ambiguous) identifier lists.

    Tokens are split on whitespace and commas only: semicolons appear inside
    legacy Wiley/SICI DOIs, so they cannot be treated as separators.
    ``ambiguous`` collects numeric tokens that look like publication years and
    are deliberately not imported (they are reported back as skipped).
    """
    dois: list[str] = []
    pmids: list[str] = []
    ambiguous: list[str] = []
    for raw in re.split(r"[\s,]+", text):
        token = raw.strip()
        if not token:
            continue
        doi = normalize_doi(token)
        if doi is not None:
            dois.append(doi)
            continue
        pmid = _pmid_from_token(token)
        if pmid is not None:
            pmids.append(pmid)
        elif token.isdigit():
            ambiguous.append(token)
    return dois, pmids, ambiguous


def _ingest_stub(
    session: Session, submission: PaperSubmission, *, owner_id: str
) -> models.PaperWork | None:
    """Register an unknown identifier through the ingest path; None on failure."""
    job = jobs.submit_ingest(session, submission, owner_id=owner_id)
    if not job.paper_work_id:
        return None
    return session.get(models.PaperWork, job.paper_work_id)


def add_members(
    session: Session,
    collection_id: str,
    payload: CollectionAddMembersRequest,
    *,
    owner_id: str,
) -> CollectionAddMembersResult:
    collection = _load_owned_collection(session, collection_id, owner_id=owner_id)

    skipped: list[str] = []

    csv_dois: list[str] = []
    csv_pmids: list[str] = []
    if payload.csv_text:
        csv_dois, csv_pmids, ambiguous = _identifiers_from_csv(payload.csv_text)
        skipped.extend(ambiguous)

    explicit_dois: list[str] = []
    for raw in payload.dois:
        doi = normalize_doi(raw)
        if doi is None:
            skipped.append(raw)
        else:
            explicit_dois.append(doi)

    explicit_pmids: list[str] = []
    for raw in payload.pmids:
        pmid = _pmid_from_token(raw.strip())
        if pmid is None:
            skipped.append(raw)
        else:
            explicit_pmids.append(pmid)

    work_ids = list(dict.fromkeys(payload.work_ids))
    dois = list(dict.fromkeys([*explicit_dois, *csv_dois]))
    pmids = list(dict.fromkeys([*explicit_pmids, *csv_pmids]))

    total = len(work_ids) + len(dois) + len(pmids)
    if total > MAX_BATCH_IDENTIFIERS:
        raise BatchLimitError(
            f"batch of {total} identifiers exceeds the limit of "
            f"{MAX_BATCH_IDENTIFIERS} per request"
        )

    # Phase 1 — resolve every identifier to a work, registering metadata stubs
    # for unknown DOIs/PMIDs. Stub ingestion commits per job (stubs are valid
    # standalone works either way); membership writes are deferred to phase 2
    # so they land in a single commit.
    resolved_works: list[models.PaperWork] = []
    created_stub_work_ids: list[str] = []

    for work_id in work_ids:
        work = _resolve_existing_work(session, work_id=work_id)
        if work is None:
            skipped.append(work_id)
        else:
            resolved_works.append(work)

    for doi in dois:
        work = _resolve_existing_work(session, doi=doi)
        if work is None:
            work = _ingest_stub(session, PaperSubmission(doi=doi), owner_id=owner_id)
            if work is not None:
                created_stub_work_ids.append(work.work_id)
        if work is None:
            skipped.append(doi)
        else:
            resolved_works.append(work)

    for pmid in pmids:
        work = _resolve_existing_work(session, pmid=pmid)
        if work is None:
            work = _ingest_stub(session, PaperSubmission(pmid=pmid), owner_id=owner_id)
            if work is not None:
                created_stub_work_ids.append(work.work_id)
        if work is None:
            skipped.append(pmid)
        else:
            resolved_works.append(work)

    # Phase 2 — create memberships in one transaction.
    added_members: list[CollectionMemberView] = []
    added_work_ids: set[str] = set()
    for work in resolved_works:
        if work.work_id in added_work_ids:
            continue
        if _membership_exists(session, collection.collection_id, work.work_id):
            continue
        member = _create_membership(
            session, collection_id=collection.collection_id, work_id=work.work_id, added_by=owner_id
        )
        added_members.append(
            _member_view(member, work, include_tallies=False, session=session)
        )
        added_work_ids.add(work.work_id)

    if added_members:
        collection.updated_at = _utcnow()
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
    collection.updated_at = _utcnow()
    session.commit()


def bulk_remove_members(
    session: Session, collection_id: str, work_ids: list[str], *, owner_id: str
) -> CollectionBulkRemoveResult:
    """Remove several members at once; unknown work_ids are silently ignored."""
    collection = _load_owned_collection(session, collection_id, owner_id=owner_id)
    unique_ids = list(dict.fromkeys(work_ids))
    members = list(
        session.scalars(
            select(models.CollectionMembership).where(
                models.CollectionMembership.collection_id == collection.collection_id,
                models.CollectionMembership.work_id.in_(unique_ids),
            )
        )
    )
    removed_work_ids = [m.work_id for m in members]
    for member in members:
        session.delete(member)
    if members:
        collection.updated_at = _utcnow()
    session.commit()
    return CollectionBulkRemoveResult(
        collection_id=collection.collection_id,
        removed_count=len(removed_work_ids),
        removed_work_ids=removed_work_ids,
    )


def _member_stance_counts(session: Session, work_id: str) -> tuple[int, int]:
    """(support, contradict) citing-statement counts for a work; (0, 0) if none."""
    try:
        tallies = citation_stats.citation_stats_for_work(session, work_id).tallies
    except KeyError:
        return (0, 0)
    return (
        tallies.by_stance.get("support", 0),
        tallies.by_stance.get("contradict", 0),
    )


def _current_stance_snapshot(session: Session, collection_id: str) -> dict[str, dict[str, int]]:
    """Per-member {work_id: {support, contradict, retracted}} for the whole collection."""
    work_ids = list(
        session.scalars(
            select(models.CollectionMembership.work_id).where(
                models.CollectionMembership.collection_id == collection_id
            )
        )
    )
    snapshot: dict[str, dict[str, int]] = {}
    for work_id in work_ids:
        support, contradict = _member_stance_counts(session, work_id)
        work = session.get(models.PaperWork, work_id)
        snapshot[work_id] = {
            "support": support,
            "contradict": contradict,
            "retracted": bool(work.is_retracted) if work is not None else False,
        }
    return snapshot


def set_watch(
    session: Session, collection_id: str, *, owner_id: str, watch: bool
) -> CollectionView:
    """Toggle monitoring. Enabling (re)captures the new-citation baseline."""
    collection = _load_owned_collection(session, collection_id, owner_id=owner_id)
    collection.is_watched = watch
    if watch:
        collection.watch_snapshot = _current_stance_snapshot(
            session, collection.collection_id
        )
        collection.watch_snapshot_at = _utcnow()
    session.commit()
    return _collection_view(session, collection)


def citation_delta(
    session: Session, collection_id: str, *, owner_id: str
) -> CollectionCitationDelta:
    """Newly observed support/contradict signals vs the last watch snapshot.

    Members added after the snapshot (absent from the baseline) contribute their
    full current counts as new. Members whose counts dropped contribute nothing
    (clamped at zero). Only members with a positive delta are returned.
    """
    collection = _load_owned_collection(session, collection_id, owner_id=owner_id)
    baseline = collection.watch_snapshot or {}

    memberships = list(
        session.scalars(
            select(models.CollectionMembership).where(
                models.CollectionMembership.collection_id == collection.collection_id
            )
        )
    )
    works = {
        w.work_id: w
        for w in session.scalars(
            select(models.PaperWork).where(
                models.PaperWork.work_id.in_([m.work_id for m in memberships])
            )
        )
    }

    member_deltas: list[CollectionMemberDelta] = []
    new_support_total = 0
    new_contradict_total = 0
    for member in memberships:
        work = works.get(member.work_id)
        if work is None:
            continue
        support, contradict = _member_stance_counts(session, member.work_id)
        prior = baseline.get(member.work_id, {})
        new_support = max(0, support - int(prior.get("support", 0)))
        new_contradict = max(0, contradict - int(prior.get("contradict", 0)))
        if new_support == 0 and new_contradict == 0:
            continue
        new_support_total += new_support
        new_contradict_total += new_contradict
        member_deltas.append(
            CollectionMemberDelta(
                work_id=work.work_id,
                title=work.title,
                new_support=new_support,
                new_contradict=new_contradict,
            )
        )

    member_deltas.sort(
        key=lambda d: (d.new_support + d.new_contradict), reverse=True
    )
    return CollectionCitationDelta(
        collection_id=collection.collection_id,
        has_snapshot=collection.watch_snapshot is not None,
        snapshot_at=collection.watch_snapshot_at,
        new_support_total=new_support_total,
        new_contradict_total=new_contradict_total,
        members=member_deltas,
    )


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
    members: list[CollectionMemberView], *, sort_key: MemberSort
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
