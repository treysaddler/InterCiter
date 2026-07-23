"""Corpus bibliometrics — descriptive "Main Information" analytics (WP-B1).

Reads stay open (no auth), like the rest of the read surface. The cohort is an
optional repeatable ``work_ids`` query parameter (else the whole corpus), narrowed by
optional publication-year bounds.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...auth import Principal
from ...schemas import (
    AuthorMetrics,
    BibliometricsSummary,
    CountryMetrics,
    SourceMetrics,
)
from ...services import bibliometrics, collections, maps
from ...services.projection import NotFound
from ..deps import db_session
from ..security import get_optional_principal

router = APIRouter()

_COHORT_DESC = "Optional repeatable work ids; omit for the whole corpus."
_COLLECTION_DESC = "Analyze a saved collection's members (owner-scoped)."
_MAP_DESC = "Analyze a saved map's members (owner-scoped)."


def _resolve_cohort(
    session: Session,
    *,
    work_ids: list[str] | None,
    collection: str | None,
    map_id: str | None,
    principal: Principal | None,
) -> list[str] | None:
    """Resolve the analysis cohort.

    A ``collection`` or ``map`` id selects a saved, owner-private work set *by
    reference* (so hundreds of ids need not travel in the URL). Those sets are
    owner-scoped: a principal is required and a set owned by someone else 404s.
    With no cohort reference, the explicit ``work_ids`` (else the whole corpus)
    is used.
    """
    if collection is None and map_id is None:
        return work_ids
    if principal is None:
        raise HTTPException(
            status_code=401,
            detail="authentication required to analyze a saved collection or map",
        )
    try:
        if collection is not None:
            return collections.member_work_ids(
                session, collection, owner_id=principal.user_id
            )
        assert map_id is not None
        return maps.member_work_ids_by_id(
            session, map_id, owner_id=principal.user_id
        )
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/bibliometrics/summary", response_model=BibliometricsSummary)
def bibliometrics_summary(
    work_ids: list[str] | None = Query(None, description=_COHORT_DESC),
    collection: str | None = Query(None, description=_COLLECTION_DESC),
    map_id: str | None = Query(None, alias="map", description=_MAP_DESC),
    min_year: int | None = Query(None, description="Earliest publication year."),
    max_year: int | None = Query(None, description="Latest publication year."),
    top_k: int = Query(10, ge=1, le=50, description="Rank-list length for top authors/sources/documents."),
    session: Session = Depends(db_session),
    principal: Principal | None = Depends(get_optional_principal),
) -> BibliometricsSummary:
    """Corpus descriptive rollup (US: see a corpus's Main Information at a glance)."""
    cohort = _resolve_cohort(
        session, work_ids=work_ids, collection=collection, map_id=map_id, principal=principal
    )
    return bibliometrics.corpus_summary(
        session,
        work_ids=cohort,
        min_year=min_year,
        max_year=max_year,
        top_k=top_k,
    )


@router.get("/bibliometrics/authors", response_model=AuthorMetrics)
def bibliometrics_authors(
    work_ids: list[str] | None = Query(None, description=_COHORT_DESC),
    collection: str | None = Query(None, description=_COLLECTION_DESC),
    map_id: str | None = Query(None, alias="map", description=_MAP_DESC),
    min_year: int | None = Query(None, description="Earliest publication year."),
    max_year: int | None = Query(None, description="Latest publication year."),
    top_k: int = Query(10, ge=1, le=50, description="Rank-list length for top authors."),
    session: Session = Depends(db_session),
    principal: Principal | None = Depends(get_optional_principal),
) -> AuthorMetrics:
    """Author analytics: productivity, h-index, and the Lotka-law distribution."""
    cohort = _resolve_cohort(
        session, work_ids=work_ids, collection=collection, map_id=map_id, principal=principal
    )
    return bibliometrics.author_metrics(
        session,
        work_ids=cohort,
        min_year=min_year,
        max_year=max_year,
        top_k=top_k,
    )


@router.get("/bibliometrics/sources", response_model=SourceMetrics)
def bibliometrics_sources(
    work_ids: list[str] | None = Query(None, description=_COHORT_DESC),
    collection: str | None = Query(None, description=_COLLECTION_DESC),
    map_id: str | None = Query(None, alias="map", description=_MAP_DESC),
    min_year: int | None = Query(None, description="Earliest publication year."),
    max_year: int | None = Query(None, description="Latest publication year."),
    top_k: int = Query(10, ge=1, le=50, description="Rank-list length for top sources."),
    session: Session = Depends(db_session),
    principal: Principal | None = Depends(get_optional_principal),
) -> SourceMetrics:
    """Source analytics: productivity, h-index impact, and Bradford's-law zones."""
    cohort = _resolve_cohort(
        session, work_ids=work_ids, collection=collection, map_id=map_id, principal=principal
    )
    return bibliometrics.source_metrics(
        session,
        work_ids=cohort,
        min_year=min_year,
        max_year=max_year,
        top_k=top_k,
    )


@router.get("/bibliometrics/countries", response_model=CountryMetrics)
def bibliometrics_countries(
    work_ids: list[str] | None = Query(None, description=_COHORT_DESC),
    collection: str | None = Query(None, description=_COLLECTION_DESC),
    map_id: str | None = Query(None, alias="map", description=_MAP_DESC),
    min_year: int | None = Query(None, description="Earliest publication year."),
    max_year: int | None = Query(None, description="Latest publication year."),
    top_k: int = Query(10, ge=1, le=50, description="Rank-list length for top countries."),
    session: Session = Depends(db_session),
    principal: Principal | None = Depends(get_optional_principal),
) -> CountryMetrics:
    """Country analytics: production + single/multi-country collaboration (SCP/MCP)."""
    cohort = _resolve_cohort(
        session, work_ids=work_ids, collection=collection, map_id=map_id, principal=principal
    )
    return bibliometrics.country_metrics(
        session,
        work_ids=cohort,
        min_year=min_year,
        max_year=max_year,
        top_k=top_k,
    )
