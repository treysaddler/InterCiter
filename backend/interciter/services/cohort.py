"""Shared saved-set / cohort base (data-layer unification).

A *cohort* is an interchangeable set of works that any analysis surface can accept:
explicit ``work_ids``, or a saved **Collection** (scite WP4), or a saved **Map**
(litmaps WP-L2). Historically each analysis endpoint resolved a saved set on its
own; this module is the single, owner-scoped seam that turns any saved-set
reference into a list of work ids — the data-layer version of the "cohort" concept
from the UX plan (§4.3).

Collections and Maps keep their own tables and side-state (watch snapshots, layout,
sharing, per-member notes) because those genuinely differ; what is unified here is
the *membership base* — resolving "which works are in this saved set" and the cohort
selection every screen shares. A future ``Corpus`` (bibliometrix WP-B7) registers a
resolver here instead of adding a fourth divergent implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from sqlalchemy.orm import Session

from ..auth import Principal
from . import collections, maps

CohortKind = Literal["collection", "map"]


class CohortAuthRequired(Exception):
    """A saved cohort source was referenced without an authenticated owner."""

    def __init__(self, kind: str) -> None:
        super().__init__(f"authentication required to analyze a saved {kind}")
        self.kind = kind


class AmbiguousCohort(ValueError):
    """More than one saved cohort source was specified at once."""


@dataclass(frozen=True)
class CohortResolver:
    """How one saved-set kind resolves to works and describes itself.

    ``work_ids(session, source_id, owner_id)`` returns the owner-scoped member work
    ids (raising :class:`~interciter.services.projection.NotFound` for a missing or
    non-owned set); ``describe`` returns ``(name, member_count)`` for banners.
    """

    work_ids: Callable[[Session, str, str], list[str]]
    describe: Callable[[Session, str, str], tuple[str, int]]


def _collection_describe(session: Session, source_id: str, owner_id: str) -> tuple[str, int]:
    view = collections.get_collection(session, source_id, owner_id=owner_id)
    return view.name, view.member_count


def _map_describe(session: Session, source_id: str, owner_id: str) -> tuple[str, int]:
    view = maps.get_map(session, source_id, owner_id=owner_id)
    return view.name, view.member_count


# The one place saved-set kinds register. Adding a third kind (e.g. a bibliometrix
# ``Corpus``) is a single entry here; every cohort-aware endpoint inherits it.
_RESOLVERS: dict[str, CohortResolver] = {
    "collection": CohortResolver(
        work_ids=lambda s, sid, owner: collections.member_work_ids(s, sid, owner_id=owner),
        describe=_collection_describe,
    ),
    "map": CohortResolver(
        work_ids=lambda s, sid, owner: maps.member_work_ids_by_id(s, sid, owner_id=owner),
        describe=_map_describe,
    ),
}


@dataclass(frozen=True)
class CohortSource:
    """A resolved saved-set cohort source."""

    kind: CohortKind
    source_id: str
    name: str
    member_count: int


def _selected(collection: str | None, map_id: str | None) -> tuple[str, str] | None:
    refs = [
        (kind, value)
        for kind, value in (("collection", collection), ("map", map_id))
        if value is not None
    ]
    if len(refs) > 1:
        raise AmbiguousCohort(
            "specify at most one saved cohort source (collection or map)"
        )
    return refs[0] if refs else None


def resolve_cohort(
    session: Session,
    *,
    work_ids: list[str] | None = None,
    collection: str | None = None,
    map_id: str | None = None,
    principal: Principal | None = None,
) -> list[str] | None:
    """Resolve an analysis cohort to a list of work ids (``None`` = whole corpus).

    A saved ``collection`` or ``map`` id selects an owner-private set *by reference*
    (so hundreds of ids need not travel in the URL). Owner-scoped: a principal is
    required (else :class:`CohortAuthRequired`) and a set owned by someone else
    raises :class:`~interciter.services.projection.NotFound`. With no saved source,
    the explicit ``work_ids`` (else ``None`` for the whole corpus) is returned.
    """
    selected = _selected(collection, map_id)
    if selected is None:
        return work_ids
    kind, source_id = selected
    if principal is None:
        raise CohortAuthRequired(kind)
    return _RESOLVERS[kind].work_ids(session, source_id, principal.user_id)


def resolve_source(
    session: Session,
    *,
    collection: str | None = None,
    map_id: str | None = None,
    principal: Principal | None = None,
) -> CohortSource:
    """Describe a saved cohort source (kind/id/name/member_count) for banners/labels.

    Raises :class:`AmbiguousCohort` if both a collection and a map are given,
    :class:`CohortAuthRequired` for an anonymous caller, ``ValueError`` if nothing
    was specified, and :class:`~interciter.services.projection.NotFound` for a
    missing or non-owned set.
    """
    selected = _selected(collection, map_id)
    if selected is None:
        raise ValueError("no saved cohort source specified")
    kind, source_id = selected
    if principal is None:
        raise CohortAuthRequired(kind)
    name, count = _RESOLVERS[kind].describe(session, source_id, principal.user_id)
    return CohortSource(
        kind=kind,  # type: ignore[arg-type]
        source_id=source_id,
        name=name,
        member_count=count,
    )
